from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.store import COLLECTIONS, PostgreSQLStore, SQLiteStore
from app.utils import to_plain


MIGRATION_MODES = ("preflight", "merge", "exact-replace")


def migrate_sqlite_to_postgres(
    sqlite_path: str | Path,
    postgres_dsn: str,
    *,
    mode: str | None = None,
    replace: bool = False,
    confirm_exact_replace: str = "",
    backup_manifest: str | Path | None = None,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Preflight, merge, or exactly replace PostgreSQL JSON records from SQLite.

    ``replace`` is retained as a compatibility alias for ``mode="exact-replace"``.
    Exact replacement only requires the destructive gate when the preflight finds
    target-only or conflicting records/audit events.
    """

    effective_mode = _resolve_mode(mode=mode, replace=replace)
    source_path = Path(sqlite_path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite migration source does not exist: {source_path}")
    source = SQLiteStore(source_path)
    target = PostgreSQLStore(postgres_dsn, connect=connect)
    preflight = _build_preflight(source, target)
    source_counts = {
        collection: len(getattr(source, collection))
        for collection, _key_field, _model_type in COLLECTIONS
    }
    source_counts["audit_log"] = len(source.audit_log)
    summary: dict[str, Any] = {
        "status": "preflight" if effective_mode == "preflight" else "ready",
        "mode": effective_mode,
        "executed": False,
        "sqlite_path": str(source_path),
        "postgres_dsn": _redact_dsn(postgres_dsn),
        "counts": source_counts,
        "preflight": preflight,
    }

    if effective_mode == "preflight":
        summary["next_action"] = (
            "Use --mode merge for insert-only migration. Review prospective_loss and the exact confirmation token "
            "before considering exact replacement."
        )
        return summary

    if effective_mode == "merge":
        summary["result"] = _merge_source_into_target(source, target)
        summary["status"] = "completed"
        summary["executed"] = True
        return summary

    loss = preflight["prospective_loss"]
    if int(loss["total_affected"]) > 0:
        required_confirmation = str(preflight["required_exact_replace_confirmation"])
        if confirm_exact_replace != required_confirmation:
            raise RuntimeError(
                "exact replacement would delete or overwrite target records/audit events; "
                "run preflight and pass its exact required_exact_replace_confirmation value"
            )
        if backup_manifest is None:
            raise RuntimeError("exact replacement with prospective loss requires --backup-manifest")
        summary["backup_validation"] = validate_backup_manifest(
            backup_manifest,
            target_counts=preflight["target_table_counts"],
            target_database=_postgres_database_name(postgres_dsn),
        )
    elif backup_manifest is not None:
        summary["backup_validation"] = validate_backup_manifest(
            backup_manifest,
            target_counts=preflight["target_table_counts"],
            target_database=_postgres_database_name(postgres_dsn),
        )

    summary["result"] = _exact_replace(source, target)
    summary["status"] = "completed"
    summary["executed"] = True
    return summary


def _resolve_mode(*, mode: str | None, replace: bool) -> str:
    normalized = (mode or "preflight").strip().lower()
    if replace:
        if mode is not None and normalized != "exact-replace":
            raise ValueError("--replace cannot be combined with a mode other than exact-replace")
        normalized = "exact-replace"
    if normalized not in MIGRATION_MODES:
        raise ValueError(f"mode must be one of: {', '.join(MIGRATION_MODES)}")
    return normalized


def _build_preflight(source: SQLiteStore, target: PostgreSQLStore) -> dict[str, Any]:
    typed_market_data = bool(target.market_data_bars_available())
    collections: dict[str, dict[str, Any]] = {}
    deleted_records = 0
    overwritten_records = 0
    source_record_count = 0
    target_record_count = 0

    for collection, _key_field, _model_type in COLLECTIONS:
        source_records = getattr(source, collection)
        target_records = getattr(target, collection)
        source_count = len(source_records)
        target_count = len(target_records)
        if collection == "market_data" and typed_market_data:
            target_count = int(target.count_market_data_points())
            collection_summary = {
                "source_count": source_count,
                "target_count": target_count,
                "source_only_count": None,
                "target_only_count": None,
                "conflict_count": None,
                "exact_replace_behavior": "merge_only_typed_table_target_rows_are_preserved",
            }
        else:
            source_ids = set(source_records)
            target_ids = set(target_records)
            common_ids = source_ids & target_ids
            conflict_count = sum(
                1
                for item_id in common_ids
                if _payload_fingerprint(source_records[item_id]) != _payload_fingerprint(target_records[item_id])
            )
            target_only_count = len(target_ids - source_ids)
            collection_summary = {
                "source_count": source_count,
                "target_count": target_count,
                "source_only_count": len(source_ids - target_ids),
                "target_only_count": target_only_count,
                "conflict_count": conflict_count,
                "exact_replace_behavior": "replace_json_record_collection",
            }
            deleted_records += target_only_count
            overwritten_records += conflict_count
            source_record_count += source_count
            target_record_count += target_count
        collections[collection] = collection_summary

    source_audit = {event.event_id: event for event in source.audit_log}
    target_audit = {event.event_id: event for event in target.audit_log}
    common_audit_ids = set(source_audit) & set(target_audit)
    overwritten_audit = sum(
        1
        for event_id in common_audit_ids
        if _payload_fingerprint(source_audit[event_id]) != _payload_fingerprint(target_audit[event_id])
    )
    deleted_audit = len(set(target_audit) - set(source_audit))
    audit_summary = {
        "source_count": len(source.audit_log),
        "target_count": len(target.audit_log),
        "source_only_count": len(set(source_audit) - set(target_audit)),
        "target_only_count": deleted_audit,
        "conflict_count": overwritten_audit,
        "exact_replace_behavior": "replace_audit_chain",
    }
    total_affected = deleted_records + overwritten_records + deleted_audit + overwritten_audit
    confirmation = _exact_replace_confirmation(
        deleted_records=deleted_records,
        overwritten_records=overwritten_records,
        deleted_audit=deleted_audit,
        overwritten_audit=overwritten_audit,
    )
    target_table_counts = _target_table_counts(
        target,
        typed_market_data=typed_market_data,
        fallback={
            "records": target_record_count,
            "audit_log": len(target.audit_log),
            "market_data_bars": collections["market_data"]["target_count"] if typed_market_data else 0,
        },
    )
    return {
        "collections": collections,
        "audit_log": audit_summary,
        "source_table_scope_counts": {
            "records": source_record_count,
            "audit_log": len(source.audit_log),
            "market_data_bars": len(source.market_data) if typed_market_data else 0,
        },
        "target_table_counts": target_table_counts,
        "registered_target_record_count": target_record_count,
        "prospective_loss": {
            "deleted_records": deleted_records,
            "overwritten_records": overwritten_records,
            "deleted_audit_events": deleted_audit,
            "overwritten_audit_events": overwritten_audit,
            "total_affected": total_affected,
        },
        "requires_loss_acknowledgement": total_affected > 0,
        "required_exact_replace_confirmation": confirmation,
        "storage_boundary": (
            "exact replacement applies to registered ai_quant.records collections and audit_log; "
            "typed market_data_bars are merge-only and target-only rows are preserved"
        ),
    }


def _target_table_counts(
    target: PostgreSQLStore,
    *,
    typed_market_data: bool,
    fallback: Mapping[str, Any],
) -> dict[str, int]:
    queries = {
        "records": "SELECT COUNT(*) FROM ai_quant.records",
        "audit_log": "SELECT COUNT(*) FROM ai_quant.audit_log",
    }
    if typed_market_data:
        queries["market_data_bars"] = "SELECT COUNT(*) FROM ai_quant.market_data_bars"
    counts: dict[str, int] = {}
    with closing(target._connect()) as connection:
        with connection.cursor() as cursor:
            for key, sql in queries.items():
                cursor.execute(sql)
                row = cursor.fetchone()
                counts[key] = int(row[0] or 0) if row else int(fallback[key])
    counts.setdefault("market_data_bars", 0)
    return counts


def _payload_fingerprint(item: Any) -> str:
    return json.dumps(to_plain(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _exact_replace_confirmation(
    *,
    deleted_records: int,
    overwritten_records: int,
    deleted_audit: int,
    overwritten_audit: int,
) -> str:
    return (
        "EXACT_REPLACE:"
        f"DELETE_RECORDS={deleted_records}:"
        f"OVERWRITE_RECORDS={overwritten_records}:"
        f"DELETE_AUDIT={deleted_audit}:"
        f"OVERWRITE_AUDIT={overwritten_audit}"
    )


def _merge_source_into_target(source: SQLiteStore, target: PostgreSQLStore) -> dict[str, Any]:
    inserted_counts: dict[str, int] = {}
    preserved_conflict_counts: dict[str, int] = {}
    changed_collections: list[str] = []
    for collection, _key_field, _model_type in COLLECTIONS:
        source_records = getattr(source, collection)
        target_records = getattr(target, collection)
        inserted = 0
        conflicts = 0
        for item_id, item in source_records.items():
            if item_id not in target_records:
                target_records[item_id] = item
                inserted += 1
            elif _payload_fingerprint(item) != _payload_fingerprint(target_records[item_id]):
                conflicts += 1
        inserted_counts[collection] = inserted
        preserved_conflict_counts[collection] = conflicts
        if inserted:
            target.mark_dirty_for_resource(collection)
            changed_collections.append(collection)

    target_audit_ids = {event.event_id for event in target.audit_log}
    audit_appended = 0
    audit_conflicts = 0
    target_audit_by_id = {event.event_id: event for event in target.audit_log}
    for event in source.audit_log:
        if event.event_id not in target_audit_ids:
            target.audit_log.append(event)
            target_audit_ids.add(event.event_id)
            audit_appended += 1
        elif _payload_fingerprint(event) != _payload_fingerprint(target_audit_by_id[event.event_id]):
            audit_conflicts += 1

    if changed_collections or audit_appended:
        if not changed_collections:
            # A dirty collection suppresses full-store deletion reconciliation.
            target.mark_dirty_for_resource(COLLECTIONS[0][0])
        target.commit()
    return {
        "strategy": "insert_only_target_wins_conflicts",
        "inserted_counts": inserted_counts,
        "preserved_conflict_counts": preserved_conflict_counts,
        "audit_appended": audit_appended,
        "audit_conflicts_preserved": audit_conflicts,
        "target_only_records_preserved": True,
        "target_only_audit_preserved": True,
    }


def _exact_replace(source: SQLiteStore, target: PostgreSQLStore) -> dict[str, Any]:
    replaced_counts: dict[str, int] = {}
    for collection, _key_field, _model_type in COLLECTIONS:
        target_records = getattr(target, collection)
        target_records.clear()
        target_records.update(getattr(source, collection))
        replaced_counts[collection] = len(target_records)
    target.audit_log = list(source.audit_log)
    target.commit()
    return {
        "strategy": "exact_replace_registered_records_and_audit",
        "replaced_counts": replaced_counts,
        "audit_log": len(source.audit_log),
        "typed_market_data_target_only_rows_preserved": True,
    }


def validate_backup_manifest(
    manifest_path: str | Path,
    *,
    target_counts: Mapping[str, Any],
    target_database: str,
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("backup manifest must be a readable JSON file") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("backup manifest must contain a JSON object")
    if payload.get("status") != "passed" or payload.get("restore_verified") is not True:
        raise RuntimeError("backup manifest must contain status=passed and restore_verified=true")
    source_database = str(payload.get("source_db") or "").strip().lower()
    if not source_database or source_database != target_database.strip().lower():
        raise RuntimeError("backup manifest source_db must exactly match the target PostgreSQL database")

    source_counts = _required_count_mapping(payload.get("source_counts"), field_name="source_counts")
    restored_counts = _required_count_mapping(payload.get("restored_counts"), field_name="restored_counts")
    coverage: dict[str, dict[str, int | bool]] = {}
    for key in ("records", "audit_log", "market_data_bars"):
        current = _non_negative_int(target_counts.get(key), field_name=f"target_counts.{key}")
        source = _non_negative_int(source_counts.get(key), field_name=f"source_counts.{key}")
        restored = _non_negative_int(restored_counts.get(key), field_name=f"restored_counts.{key}")
        if source != restored:
            raise RuntimeError(f"backup source/restored count mismatch for {key}")
        if source != current:
            raise RuntimeError(f"backup {key} count does not exactly match the current target snapshot")
        coverage[key] = {
            "current_target": current,
            "backup_source": source,
            "backup_restored": restored,
            "covered": True,
        }

    source_database_manifest = payload.get("source_database_manifest")
    restored_database_manifest = payload.get("restored_database_manifest")
    if (source_database_manifest is None) != (restored_database_manifest is None):
        raise RuntimeError("backup database manifest evidence is incomplete")
    if source_database_manifest is not None and source_database_manifest != restored_database_manifest:
        raise RuntimeError("backup source/restored database manifests do not match")

    dump_path = _resolve_dump_path(path, payload.get("dump_path"))
    expected_sha = str(payload.get("dump_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise RuntimeError("backup manifest must contain a valid dump_sha256")
    actual_sha = _sha256(dump_path)
    if actual_sha != expected_sha:
        raise RuntimeError("backup dump SHA-256 does not match the restore-verified manifest")
    if payload.get("dump_size_bytes") is not None:
        expected_size = _non_negative_int(payload.get("dump_size_bytes"), field_name="dump_size_bytes")
        if dump_path.stat().st_size != expected_size:
            raise RuntimeError("backup dump size does not match the restore-verified manifest")

    retained_until = str(payload.get("retained_until") or "").strip()
    if retained_until:
        retained_at = _parse_manifest_datetime(retained_until)
        if retained_at <= datetime.now(timezone.utc):
            raise RuntimeError("backup manifest retention has expired")

    return {
        "status": "passed",
        "manifest_path": str(path),
        "dump_path": str(dump_path),
        "dump_sha256_verified": True,
        "restore_verified": True,
        "source_database": source_database,
        "target_count_coverage": coverage,
        "retained_until": retained_until or None,
    }


def _required_count_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"backup manifest must contain {field_name}")
    return value


def _postgres_database_name(dsn: str) -> str:
    if "://" in dsn:
        parsed = urlsplit(dsn)
        database = unquote(parsed.path.lstrip("/")).strip().lower()
    else:
        match = re.search(r"(?:^|\s)dbname\s*=\s*(?:'([^']+)'|\"([^\"]+)\"|([^\s]+))", dsn, flags=re.IGNORECASE)
        database = next((group for group in match.groups() if group is not None), "").strip().lower() if match else ""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", database):
        raise RuntimeError("target PostgreSQL DSN must identify a safe database name")
    return database


def _non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise RuntimeError(f"{field_name} must be a non-negative integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be a non-negative integer") from exc
    if normalized < 0:
        raise RuntimeError(f"{field_name} must be a non-negative integer")
    return normalized


def _resolve_dump_path(manifest_path: Path, value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("backup manifest must contain dump_path")
    candidate = Path(raw).expanduser()
    candidates = [candidate] if candidate.is_absolute() else [manifest_path.parent / candidate, candidate]
    for item in candidates:
        resolved = item.resolve()
        if resolved.is_file():
            return resolved
    raise RuntimeError("the restore-verified dump referenced by the backup manifest is missing")


def _parse_manifest_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("backup retained_until must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_dsn(dsn: str) -> str:
    if "://" in dsn:
        try:
            parsed = urlsplit(dsn)
        except ValueError:
            return "***redacted-postgres-dsn***"
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        username = quote(parsed.username or "", safe="")
        if parsed.password is not None:
            userinfo = f"{username}:***@"
        elif username:
            userinfo = f"{username}@"
        else:
            userinfo = ""
        query = "***" if parsed.query else ""
        return urlunsplit((parsed.scheme, f"{userinfo}{host}", parsed.path, query, ""))
    redacted = re.sub(
        r"(?i)\b(password|passfile|sslpassword)\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s]+)",
        lambda match: f"{match.group(1)}=***",
        dsn,
    )
    return redacted if redacted != dsn or "password" not in dsn.lower() else "***redacted-postgres-dsn***"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Safely preflight or migrate AI Quant SQLite state to PostgreSQLStore. "
            "The default mode is read-only preflight."
        )
    )
    parser.add_argument("sqlite_path", help="Path to the SQLite state.db file")
    parser.add_argument("postgres_dsn", help="PostgreSQL DSN; credentials are redacted from output")
    parser.add_argument(
        "--mode",
        choices=MIGRATION_MODES,
        default=None,
        help="preflight (default), insert-only merge, or guarded exact-replace",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Compatibility alias for --mode exact-replace; destructive gates still apply",
    )
    parser.add_argument(
        "--confirm-exact-replace",
        default="",
        help="Exact confirmation token emitted by preflight when target loss is possible",
    )
    parser.add_argument(
        "--backup-manifest",
        help="Restore-verified backup manifest required when exact replacement can lose target state",
    )
    args = parser.parse_args()
    summary = migrate_sqlite_to_postgres(
        args.sqlite_path,
        args.postgres_dsn,
        mode=args.mode,
        replace=args.replace,
        confirm_exact_replace=args.confirm_exact_replace,
        backup_manifest=args.backup_manifest,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
