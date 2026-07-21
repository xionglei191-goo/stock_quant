#!/usr/bin/env python3
"""Safely promote an attested research-report slice from a clone to primary.

The default mode is a read-only preflight. Promotion is deliberately separate
from the clone-only HTTP recovery executor: it copies only the plan-selected,
double-run-verified source/report/document/citation-evidence rows, uses no
DELETE or UPDATE statement, and commits the target changes in one transaction.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.postgres_durable_backup import RESEARCH_STATE_COUNT_KEYS, RESEARCH_STATE_SQL
from scripts.recover_watchlist_research_reports import BOUNDARY, WATCHLIST_SYMBOLS


PRIMARY_DATABASE = "ai_quant"
ALLOWED_COLLECTIONS = ("sources", "research_reports", "documents", "evidence")
PLAN_CORE_KEYS = (
    "schema_version",
    "related_tasks",
    "filesystem_snapshot",
    "input_evidence",
    "settings",
    "companies",
    "candidate_diagnostics",
    "write_contract",
)
BACKUP_MAX_AGE = timedelta(hours=6)
QUIESCENCE_MAX_AGE = timedelta(minutes=15)
PROMOTION_ADVISORY_LOCK = 846120612
SAFE_DATABASE = re.compile(r"^[a-z_][a-z0-9_]*$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PromotionRefused(RuntimeError):
    """Raised before target mutation when a promotion gate is closed."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_json(path: str | Path, *, label: str) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionRefused(f"{label} must be a readable JSON file") from exc
    if not isinstance(payload, dict):
        raise PromotionRefused(f"{label} must contain a JSON object")
    return payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _payload_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: str | Path, *, label: str) -> tuple[Path, dict[str, Any], str]:
    resolved = Path(path).expanduser().resolve()
    payload = _load_json(resolved, label=label)
    return resolved, payload, _file_sha256(resolved)


def _parse_time(value: Any, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionRefused(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recent(value: Any, *, field_name: str, max_age: timedelta, now: datetime) -> datetime:
    parsed = _parse_time(value, field_name=field_name)
    age = now - parsed
    if age < timedelta(minutes=-5) or age > max_age:
        raise PromotionRefused(f"{field_name} is outside the permitted freshness window")
    return parsed


def _non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise PromotionRefused(f"{field_name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PromotionRefused(f"{field_name} must be a non-negative integer") from exc
    if result < 0:
        raise PromotionRefused(f"{field_name} must be a non-negative integer")
    return result


def _count_map(value: Any, *, field_name: str, keys: Iterable[str]) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise PromotionRefused(f"{field_name} must be an object")
    return {key: _non_negative_int(value.get(key), field_name=f"{field_name}.{key}") for key in keys}


def _database_name(dsn: str) -> str:
    if "://" in dsn:
        parsed = urlsplit(dsn)
        name = unquote(parsed.path.lstrip("/")).strip().lower()
    else:
        match = re.search(
            r"(?:^|\s)dbname\s*=\s*(?:'([^']+)'|\"([^\"]+)\"|([^\s]+))",
            dsn,
            flags=re.IGNORECASE,
        )
        name = next((item for item in match.groups() if item is not None), "").lower() if match else ""
    if not SAFE_DATABASE.fullmatch(name):
        raise PromotionRefused("PostgreSQL DSN must identify a safe database name")
    return name


def _redact_dsn(dsn: str) -> str:
    if "://" not in dsn:
        return re.sub(
            r"(?i)\b(password|passfile|sslpassword)\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s]+)",
            lambda match: f"{match.group(1)}=***",
            dsn,
        )
    parsed = urlsplit(dsn)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    user = quote(parsed.username or "", safe="")
    userinfo = f"{user}:{'***'}@" if parsed.password is not None else f"{user}@" if user else ""
    return urlunsplit((parsed.scheme, f"{userinfo}{host}", parsed.path, "***" if parsed.query else "", ""))


def _default_connect(dsn: str) -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("T-612 promotion requires psycopg") from exc
    return psycopg.connect(dsn)


def _json_object(value: Any, *, label: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise PromotionRefused(f"{label} returned invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise PromotionRefused(f"{label} must be a JSON object")
    return dict(value)


def _query_snapshot(cursor: Any) -> dict[str, Any]:
    cursor.execute(
        "SELECT current_database(), oid::text, system_identifier::text "
        "FROM pg_database CROSS JOIN pg_control_system() WHERE datname = current_database()"
    )
    identity_row = cursor.fetchone()
    if not identity_row:
        raise PromotionRefused("database identity query returned no row")
    table_counts: dict[str, int] = {}
    for key, sql in {
        "records": "SELECT COUNT(*) FROM ai_quant.records",
        "audit_log": "SELECT COUNT(*) FROM ai_quant.audit_log",
        "market_data_bars": "SELECT COUNT(*) FROM ai_quant.market_data_bars",
    }.items():
        cursor.execute(sql)
        row = cursor.fetchone()
        table_counts[key] = int(row[0]) if row else -1
    cursor.execute(RESEARCH_STATE_SQL)
    research_row = cursor.fetchone()
    research_payload = _json_object(research_row[0] if research_row else None, label="research-state query")
    research_counts = _count_map(
        research_payload.get("counts"),
        field_name="research_state.counts",
        keys=RESEARCH_STATE_COUNT_KEYS,
    )
    cursor.execute(
        "SELECT COUNT(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid()"
    )
    sessions_row = cursor.fetchone()
    return {
        "identity": {
            "database_name": str(identity_row[0]).strip().lower(),
            "database_oid": str(identity_row[1]),
            "postgres_system_identifier": str(identity_row[2]),
        },
        "table_counts": table_counts,
        "research_counts": research_counts,
        "other_database_sessions": int(sessions_row[0]) if sessions_row else -1,
    }


def _read_snapshot(dsn: str, *, connect: Callable[[str], Any]) -> dict[str, Any]:
    with closing(connect(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return _query_snapshot(cursor)


def _normalize_record(row: Any) -> dict[str, Any]:
    collection, item_id, payload, position = row
    return {
        "collection": str(collection),
        "item_id": str(item_id),
        "payload": _json_object(payload, label=f"{collection}/{item_id}"),
        "position": int(position) if position is not None else None,
    }


def _fetch_records(cursor: Any, collection: str, item_ids: Iterable[str]) -> list[dict[str, Any]]:
    ids = sorted(set(str(item) for item in item_ids))
    if not ids:
        return []
    cursor.execute(
        "SELECT collection, item_id, payload, position FROM ai_quant.records "
        "WHERE collection = %s AND item_id = ANY(%s) ORDER BY item_id",
        (collection, ids),
    )
    return [_normalize_record(row) for row in cursor.fetchall()]


def _fetch_citation_evidence(cursor: Any, document_ids: Iterable[str]) -> list[dict[str, Any]]:
    ids = sorted(set(str(item) for item in document_ids))
    if not ids:
        return []
    cursor.execute(
        "SELECT collection, item_id, payload, position FROM ai_quant.records "
        "WHERE collection = 'evidence' AND payload->>'document_id' = ANY(%s) "
        "AND payload->>'section' = 'research_report_citation' ORDER BY item_id",
        (ids,),
    )
    return [_normalize_record(row) for row in cursor.fetchall()]


def _selected_plan_rows(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    core = {key: plan.get(key) for key in PLAN_CORE_KEYS}
    expected_sha = str(plan.get("plan_sha256") or "")
    if plan.get("schema_version") != "watchlist-research-report-recovery-plan-v1":
        raise PromotionRefused("unsupported recovery plan schema")
    if not SHA256.fullmatch(expected_sha) or _payload_sha256(core) != expected_sha:
        raise PromotionRefused("recovery plan canonical SHA-256 does not match plan_sha256")
    if plan.get("execution_allowed") is not True or plan.get("status") != "ready_for_cloned_pilot":
        raise PromotionRefused("recovery plan is not approved for the clone pilot")
    if list(plan.get("failed_gate_ids") or []):
        raise PromotionRefused("recovery plan contains failed safety gates")
    if plan.get("write_contract", {}).get("fact_opinion_boundary") != BOUNDARY:
        raise PromotionRefused("recovery plan changed the fact/opinion boundary")

    selected: dict[str, dict[str, Any]] = {}
    seen_documents: set[str] = set()
    seen_content: set[str] = set()
    symbols: list[str] = []
    for company in plan.get("companies", []):
        if not isinstance(company, Mapping):
            raise PromotionRefused("recovery plan company entries must be objects")
        symbol = str(company.get("symbol") or "")
        symbols.append(symbol)
        identity = company.get("identity") if isinstance(company.get("identity"), Mapping) else {}
        issuer_id = str(identity.get("issuer_id") or "")
        security_id = str(identity.get("security_id") or "")
        reports = company.get("selected_reports") if isinstance(company.get("selected_reports"), list) else []
        if company.get("status") != "planned" or not issuer_id or not security_id or not reports:
            raise PromotionRefused(f"company {symbol or 'unknown'} is not a fully resolved planned batch")
        for report in reports:
            if not isinstance(report, Mapping):
                raise PromotionRefused("selected report entries must be objects")
            report_id = str(report.get("report_id") or "")
            document_id = str(report.get("document_id") or "")
            content_sha = str(report.get("content_sha256") or "")
            if (
                not SAFE_ID.fullmatch(report_id)
                or document_id != f"doc_{report_id}"
                or str(report.get("evidence_id_prefix") or "") != f"evi_{document_id}_research_"
            ):
                raise PromotionRefused("selected report/document identity is invalid")
            if not SHA256.fullmatch(content_sha):
                raise PromotionRefused(f"selected report {report_id} lacks a valid content SHA-256")
            if report_id in selected or document_id in seen_documents or content_sha in seen_content:
                raise PromotionRefused("selected report, document, and content identities must be unique")
            if report.get("source_boundary") != BOUNDARY:
                raise PromotionRefused(f"selected report {report_id} changed the opinion boundary")
            selected[report_id] = {
                "report_id": report_id,
                "document_id": document_id,
                "content_sha256": content_sha,
                "evidence_id_prefix": str(report.get("evidence_id_prefix") or ""),
                "symbol": symbol,
                "issuer_id": issuer_id,
                "security_id": security_id,
            }
            seen_documents.add(document_id)
            seen_content.add(content_sha)
    if symbols != list(WATCHLIST_SYMBOLS):
        raise PromotionRefused("recovery plan must contain the five watchlist companies in canonical order")
    if not selected:
        raise PromotionRefused("recovery plan contains no selected reports")
    return selected


def _validate_execution(
    payload: Mapping[str, Any],
    *,
    label: str,
    plan: Mapping[str, Any],
    selected: Mapping[str, Mapping[str, Any]],
    require_created: bool,
) -> dict[str, dict[str, Any]]:
    embedded_plan = payload.get("plan") if isinstance(payload.get("plan"), Mapping) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), Mapping) else {}
    if {key: embedded_plan.get(key) for key in PLAN_CORE_KEYS} != {key: plan.get(key) for key in PLAN_CORE_KEYS}:
        raise PromotionRefused(f"{label} embeds a different deterministic plan")
    if execution.get("schema_version") != "watchlist-research-report-recovery-execution-v1":
        raise PromotionRefused(f"{label} has an unsupported execution schema")
    if execution.get("status") != "passed" or execution.get("plan_sha256") != plan.get("plan_sha256"):
        raise PromotionRefused(f"{label} did not pass against the supplied plan")
    if execution.get("environment") != "operator_confirmed_cloned_database_pilot":
        raise PromotionRefused(f"{label} is not clone-pilot evidence")
    if execution.get("fact_opinion_boundary") != BOUNDARY:
        raise PromotionRefused(f"{label} changed the opinion boundary")
    if list(execution.get("delete_operations") or []):
        raise PromotionRefused(f"{label} reports delete operations")
    if execution.get("raw_files_preserved") is not True or execution.get("opensearch_index_preserved") is not True:
        raise PromotionRefused(f"{label} did not preserve raw/search state")
    if int(execution.get("registry_indexed_count") or -1) != int(plan.get("filesystem_snapshot", {}).get("eligible_report_files") or -2):
        raise PromotionRefused(f"{label} registry count differs from the plan")
    results = execution.get("results") if isinstance(execution.get("results"), list) else []
    if len(results) != len(selected) or int(execution.get("selected_report_count") or -1) != len(selected):
        raise PromotionRefused(f"{label} selected-report count is incomplete")
    by_id: dict[str, dict[str, Any]] = {}
    for raw in results:
        if not isinstance(raw, Mapping):
            raise PromotionRefused(f"{label} result entries must be objects")
        result = dict(raw)
        report_id = str(result.get("report_id") or "")
        expected = selected.get(report_id)
        if expected is None or report_id in by_id:
            raise PromotionRefused(f"{label} contains an unexpected or duplicate report ID")
        strict = (
            result.get("document_id") == expected["document_id"]
            and result.get("symbol") == expected["symbol"]
            and result.get("content_sha256") == expected["content_sha256"]
            and result.get("content_identity_verified") is True
            and result.get("status") == "text_indexed"
            and int(result.get("evidence_count") or 0) > 0
            and result.get("manual_review") is False
            and result.get("fact_opinion_boundary") == BOUNDARY
            and bool(result.get("text_source"))
        )
        if not strict:
            raise PromotionRefused(f"{label} strict evidence gate failed for {report_id}")
        if result.get("ingest_created") is not require_created:
            expected_created = "true" if require_created else "false"
            raise PromotionRefused(f"{label} ingest_created must be {expected_created} for every report")
        by_id[report_id] = result
    if set(by_id) != set(selected):
        raise PromotionRefused(f"{label} report IDs do not exactly match the plan")
    evidence_count = sum(int(item["evidence_count"]) for item in by_id.values())
    if int(execution.get("evidence_count") or -1) != evidence_count:
        raise PromotionRefused(f"{label} evidence_count does not match its results")
    if _non_negative_int(
        execution.get("needs_evidence_count"),
        field_name=f"{label}.execution.needs_evidence_count",
    ) != 0:
        raise PromotionRefused(f"{label} reports unresolved evidence")
    if int(execution.get("content_identity_verified_count") or -1) != len(selected):
        raise PromotionRefused(f"{label} content identity count is incomplete")
    return by_id


def _rights_are_restricted(payload: Mapping[str, Any]) -> bool:
    rights = payload.get("rights_tag") if isinstance(payload.get("rights_tag"), Mapping) else {}
    return (
        rights.get("license_class") == "local_research_reference"
        and rights.get("training_allowed") is False
        and rights.get("redistribution_allowed") is False
        and rights.get("display_use") == "restricted"
        and rights.get("non_display_use") == "restricted"
        and rights.get("derived_data_use") == "restricted"
    )


def _validate_source_slice(
    rows: list[dict[str, Any]],
    *,
    selected: Mapping[str, Mapping[str, Any]],
    run1: Mapping[str, Mapping[str, Any]],
    run2: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    by_key = {(row["collection"], row["item_id"]): row for row in rows}
    if len(by_key) != len(rows):
        raise PromotionRefused("source slice contains duplicate record identities")
    if any(row["collection"] not in ALLOWED_COLLECTIONS for row in rows):
        raise PromotionRefused("source slice escaped the collection allowlist")
    required_source_ids: set[str] = set()
    expected_documents = {str(item["document_id"]): item for item in selected.values()}
    evidence_by_document: dict[str, list[dict[str, Any]]] = {item: [] for item in expected_documents}
    for report_id, expected in selected.items():
        report_row = by_key.get(("research_reports", report_id))
        document_row = by_key.get(("documents", str(expected["document_id"])))
        if report_row is None or document_row is None:
            raise PromotionRefused(f"source is missing selected report/document {report_id}")
        report = report_row["payload"]
        document = document_row["payload"]
        source_id = str(report.get("source_id") or "")
        if not SAFE_ID.fullmatch(source_id):
            raise PromotionRefused(f"source ID is invalid for report {report_id}")
        report_valid = (
            report.get("report_id") == report_id
            and report.get("document_id") == expected["document_id"]
            and report.get("content_sha256") == expected["content_sha256"]
            and report.get("issuer_id") == expected["issuer_id"]
            and report.get("security_id") == expected["security_id"]
            and report.get("status") == "text_indexed"
            and _rights_are_restricted(report)
        )
        document_valid = (
            document.get("document_id") == expected["document_id"]
            and document.get("source_id") == source_id
            and document.get("issuer_id") == expected["issuer_id"]
            and document.get("security_id") == expected["security_id"]
            and document.get("document_type") == "research"
            and document.get("source_type") == "local_reference"
            and document.get("source_uri") == f"research-report://{report_id}"
            and document.get("content_sha256") == expected["content_sha256"]
            and bool(str(document.get("body") or "").strip())
            and _rights_are_restricted(document)
        )
        if not report_valid or not document_valid:
            raise PromotionRefused(f"source content/identity boundary failed for {report_id}")
        if int(run1[report_id]["evidence_count"]) != int(run2[report_id]["evidence_count"]):
            raise PromotionRefused(f"clone rerun changed evidence cardinality for {report_id}")
        required_source_ids.add(source_id)

    for row in rows:
        if row["collection"] != "evidence":
            continue
        evidence = row["payload"]
        document_id = str(evidence.get("document_id") or "")
        if document_id not in expected_documents:
            raise PromotionRefused("source slice contains citation evidence outside selected documents")
        report_id = str(expected_documents[document_id]["report_id"])
        prefix = str(expected_documents[document_id]["evidence_id_prefix"])
        if (
            evidence.get("evidence_id") != row["item_id"]
            or not row["item_id"].startswith(prefix)
            or evidence.get("section") != "research_report_citation"
            or not str(evidence.get("bbox") or "").startswith(f"research_report://{document_id};chunk=")
            or not str(evidence.get("span_text") or "").strip()
            or not str(evidence.get("canonical_text") or "").strip()
        ):
            raise PromotionRefused(f"citation evidence identity failed for {report_id}")
        evidence_by_document[document_id].append(row)

    for document_id, evidence_rows in evidence_by_document.items():
        report_id = str(expected_documents[document_id]["report_id"])
        expected_count = int(run2[report_id]["evidence_count"])
        if len(evidence_rows) != expected_count or expected_count < 1:
            raise PromotionRefused(f"database citation count differs from clone runs for {report_id}")

    actual_sources = {row["item_id"] for row in rows if row["collection"] == "sources"}
    if actual_sources != required_source_ids:
        raise PromotionRefused("source slice does not contain exactly the required source definitions")
    for source_id in actual_sources:
        source = by_key[("sources", source_id)]["payload"]
        if (
            source.get("source_id") != source_id
            or source.get("source_type") != "local_reference"
            or source.get("usage_scope") != "local_reference_citation_tracking_only"
            or "research" not in list(source.get("allowed_document_types") or [])
            or not _rights_are_restricted(source)
        ):
            raise PromotionRefused(f"source definition boundary failed for {source_id}")

    counts = {collection: sum(1 for row in rows if row["collection"] == collection) for collection in ALLOWED_COLLECTIONS}
    if counts["research_reports"] != len(selected) or counts["documents"] != len(selected):
        raise PromotionRefused("source slice is not bounded to the selected report/document identities")
    return {"counts": counts, "slice_sha256": _payload_sha256(rows)}


def _read_source_context(
    dsn: str,
    *,
    selected: Mapping[str, Mapping[str, Any]],
    connect: Callable[[str], Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    report_ids = sorted(selected)
    document_ids = sorted(str(item["document_id"]) for item in selected.values())
    with closing(connect(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = _query_snapshot(cursor)
            reports = _fetch_records(cursor, "research_reports", report_ids)
            documents = _fetch_records(cursor, "documents", document_ids)
            source_ids = {
                str(row["payload"].get("source_id") or "")
                for row in reports
                if str(row["payload"].get("source_id") or "")
            }
            sources = _fetch_records(cursor, "sources", source_ids)
            evidence = _fetch_citation_evidence(cursor, document_ids)
    rows = sorted([*sources, *reports, *documents, *evidence], key=lambda row: (row["collection"], row["item_id"]))
    return snapshot, rows


def _read_target_context(
    dsn: str,
    *,
    keys: Mapping[str, Iterable[str]],
    connect: Callable[[str], Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with closing(connect(dsn)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot = _query_snapshot(cursor)
            rows: list[dict[str, Any]] = []
            for collection in ALLOWED_COLLECTIONS:
                rows.extend(_fetch_records(cursor, collection, keys.get(collection, [])))
    return snapshot, sorted(rows, key=lambda row: (row["collection"], row["item_id"]))


def _resolve_dump_path(manifest_path: Path, payload: Mapping[str, Any]) -> Path:
    raw = str(payload.get("dump_path") or "").strip()
    if not raw:
        raise PromotionRefused("backup manifest must contain dump_path")
    configured = Path(raw).expanduser()
    candidates = [configured] if configured.is_absolute() else [manifest_path.parent / configured, configured]
    if configured.name:
        candidates.append(manifest_path.parent / configured.name)
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise PromotionRefused("backup dump referenced by the manifest is missing")


def _validate_backup_manifest(
    manifest_path: Path,
    payload: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    expected_database: str,
    now: datetime,
) -> dict[str, Any]:
    if payload.get("status") != "passed" or payload.get("restore_verified") is not True:
        raise PromotionRefused("backup must have status=passed and restore_verified=true")
    if str(payload.get("source_db") or "").strip().lower() != expected_database:
        raise PromotionRefused("backup source_db does not match the bound database")
    _recent(payload.get("generated_at"), field_name="backup.generated_at", max_age=BACKUP_MAX_AGE, now=now)
    retained_until = _parse_time(payload.get("retained_until"), field_name="backup.retained_until")
    if retained_until <= now:
        raise PromotionRefused("backup retention has expired")
    source_counts = _count_map(payload.get("source_counts"), field_name="backup.source_counts", keys=("records", "audit_log", "market_data_bars"))
    restored_counts = _count_map(payload.get("restored_counts"), field_name="backup.restored_counts", keys=("records", "audit_log", "market_data_bars"))
    source_research = _count_map(payload.get("collection_counts"), field_name="backup.collection_counts", keys=RESEARCH_STATE_COUNT_KEYS)
    restored_research = _count_map(payload.get("restored_collection_counts"), field_name="backup.restored_collection_counts", keys=RESEARCH_STATE_COUNT_KEYS)
    if source_counts != restored_counts or source_research != restored_research:
        raise PromotionRefused("backup source/restored manifests differ")
    if source_counts != dict(snapshot.get("table_counts") or {}) or source_research != dict(snapshot.get("research_counts") or {}):
        raise PromotionRefused("current database state is not exactly bound to the restore-verified backup")
    source_database_manifest = payload.get("source_database_manifest")
    restored_database_manifest = payload.get("restored_database_manifest")
    if not isinstance(source_database_manifest, Mapping) or source_database_manifest != restored_database_manifest:
        raise PromotionRefused("backup database-manifest evidence is missing or unequal")
    internal_table_counts = _count_map(
        source_database_manifest.get("table_counts"),
        field_name="backup.source_database_manifest.table_counts",
        keys=("records", "audit_log", "market_data_bars"),
    )
    internal_research_state = source_database_manifest.get("research_state")
    internal_research_counts = _count_map(
        internal_research_state.get("counts") if isinstance(internal_research_state, Mapping) else None,
        field_name="backup.source_database_manifest.research_state.counts",
        keys=RESEARCH_STATE_COUNT_KEYS,
    )
    if internal_table_counts != source_counts or internal_research_counts != source_research:
        raise PromotionRefused("backup compatibility counts differ from its database manifest")
    dump = _resolve_dump_path(manifest_path, payload)
    expected_sha = str(payload.get("dump_sha256") or "").strip().lower()
    if not SHA256.fullmatch(expected_sha) or _file_sha256(dump) != expected_sha:
        raise PromotionRefused("backup dump SHA-256 does not match the manifest")
    if dump.stat().st_size != _non_negative_int(payload.get("dump_size_bytes"), field_name="backup.dump_size_bytes"):
        raise PromotionRefused("backup dump size does not match the manifest")
    return {
        "manifest_sha256": _file_sha256(manifest_path),
        "dump_sha256": expected_sha,
        "generated_at": str(payload.get("generated_at")),
        "retained_until": str(payload.get("retained_until")),
        "table_counts": source_counts,
        "research_counts": source_research,
    }


def _inspect_writer_containers(names: Iterable[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in sorted(set(str(item).strip() for item in names if str(item).strip())):
        command = ["docker", "inspect", name]
        completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)
        if completed.returncode != 0:
            raise PromotionRefused(f"cannot inspect required writer container {name}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise PromotionRefused(f"docker inspect returned invalid JSON for {name}") from exc
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], Mapping):
            raise PromotionRefused(f"docker inspect returned an unexpected result for {name}")
        container = payload[0]
        state = container.get("State") if isinstance(container.get("State"), Mapping) else {}
        config = container.get("Config") if isinstance(container.get("Config"), Mapping) else {}
        results.append(
            {
                "name": name,
                "container_id": str(container.get("Id") or ""),
                "image_id": str(container.get("Image") or ""),
                "configured_hostname": str(config.get("Hostname") or ""),
                "status": str(state.get("Status") or ""),
                "running": state.get("Running") is True,
            }
        )
    _validate_writer_rows(results)
    return results


def _validate_writer_rows(results: Any) -> None:
    if not isinstance(results, list) or not results:
        raise PromotionRefused("at least one primary writer container must be inspected")
    if any(not isinstance(item, Mapping) for item in results):
        raise PromotionRefused("writer-container proof entries must be objects")
    if any(item.get("running") is not False or item.get("status") not in {"created", "exited", "dead"} for item in results):
        raise PromotionRefused("all primary writer containers must be stopped")
    if any(not str(item.get("name") or "") or not str(item.get("container_id") or "") or not str(item.get("image_id") or "") for item in results):
        raise PromotionRefused("writer-container identity evidence is incomplete")
    names = [str(item["name"]) for item in results]
    container_ids = [str(item["container_id"]) for item in results]
    if len(names) != len(set(names)) or len(container_ids) != len(set(container_ids)):
        raise PromotionRefused("writer-container identity evidence contains duplicates")


def create_quiescence_proof(
    *,
    target_dsn: str,
    target_backup_path: str | Path,
    writer_containers: Iterable[str],
    connect: Callable[[str], Any] | None = None,
    inspect_writer_containers: Callable[[Iterable[str]], list[dict[str, Any]]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    connect = connect or _default_connect
    now = now or _utcnow()
    if _database_name(target_dsn) != PRIMARY_DATABASE:
        raise PromotionRefused("quiescence proof target must be exactly ai_quant")
    target_manifest_path, target_manifest, _ = _artifact(target_backup_path, label="target backup manifest")
    snapshot = _read_snapshot(target_dsn, connect=connect)
    backup = _validate_backup_manifest(
        target_manifest_path,
        target_manifest,
        snapshot=snapshot,
        expected_database=PRIMARY_DATABASE,
        now=now,
    )
    if int(snapshot["other_database_sessions"]) != 0:
        raise PromotionRefused("primary database has sessions other than the quiescence probe")
    inspector = inspect_writer_containers or _inspect_writer_containers
    writers = inspector(writer_containers)
    _validate_writer_rows(writers)
    core = {
        "schema_version": "research-report-primary-quiescence-proof-v1",
        "producer": "scripts/promote_research_report_clone_to_primary.py",
        "generated_at": now.isoformat(),
        "target_database": PRIMARY_DATABASE,
        "target_database_identity": dict(snapshot["identity"]),
        "target_table_counts": dict(snapshot["table_counts"]),
        "target_research_counts": dict(snapshot["research_counts"]),
        "target_backup_dump_sha256": backup["dump_sha256"],
        "other_database_sessions": 0,
        "writer_containers": writers,
        "operator_boundary": "primary_app_and_all_known_schedulers_stopped_for_t612",
    }
    return {
        **core,
        "status": "passed",
        "proof_sha256": _payload_sha256(core),
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
    }


def _validate_quiescence_proof(
    proof: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any],
    target_backup: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    core_keys = (
        "schema_version",
        "producer",
        "generated_at",
        "target_database",
        "target_database_identity",
        "target_table_counts",
        "target_research_counts",
        "target_backup_dump_sha256",
        "other_database_sessions",
        "writer_containers",
        "operator_boundary",
    )
    core = {key: proof.get(key) for key in core_keys}
    if proof.get("schema_version") != "research-report-primary-quiescence-proof-v1" or proof.get("status") != "passed":
        raise PromotionRefused("primary quiescence proof schema/status is invalid")
    if proof.get("producer") != "scripts/promote_research_report_clone_to_primary.py":
        raise PromotionRefused("primary quiescence proof producer is invalid")
    _recent(proof.get("generated_at"), field_name="quiescence.generated_at", max_age=QUIESCENCE_MAX_AGE, now=now)
    if proof.get("proof_sha256") != _payload_sha256(core):
        raise PromotionRefused("primary quiescence proof hash is invalid")
    writers = proof.get("writer_containers") if isinstance(proof.get("writer_containers"), list) else []
    _validate_writer_rows(writers)
    checks = (
        proof.get("target_database") == PRIMARY_DATABASE,
        dict(proof.get("target_database_identity") or {}) == dict(snapshot.get("identity") or {}),
        dict(proof.get("target_table_counts") or {}) == dict(snapshot.get("table_counts") or {}),
        dict(proof.get("target_research_counts") or {}) == dict(snapshot.get("research_counts") or {}),
        proof.get("target_backup_dump_sha256") == target_backup.get("dump_sha256"),
        proof.get("other_database_sessions") == 0,
        snapshot.get("other_database_sessions") == 0,
        proof.get("operator_boundary") == "primary_app_and_all_known_schedulers_stopped_for_t612",
    )
    if not all(checks):
        raise PromotionRefused("primary quiescence proof no longer matches the current target")
    return {"proof_sha256": str(proof["proof_sha256"]), "generated_at": str(proof["generated_at"])}


def _record_keys(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    result = {collection: [] for collection in ALLOWED_COLLECTIONS}
    for row in rows:
        result[str(row["collection"])].append(str(row["item_id"]))
    return {key: sorted(values) for key, values in result.items()}


def _target_diff(source_rows: list[dict[str, Any]], target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    source = {(row["collection"], row["item_id"]): row for row in source_rows}
    target = {(row["collection"], row["item_id"]): row for row in target_rows}
    conflicts = sorted(
        f"{collection}/{item_id}"
        for (collection, item_id), row in source.items()
        if (collection, item_id) in target and target[(collection, item_id)] != row
    )
    if conflicts:
        raise PromotionRefused(f"target contains unequal conflicting rows: {','.join(conflicts[:20])}")
    insert_keys = sorted(key for key in source if key not in target)
    equal_keys = sorted(key for key in source if key in target)
    return {
        "insert_keys": insert_keys,
        "equal_keys": equal_keys,
        "insert_counts": {
            collection: sum(1 for key in insert_keys if key[0] == collection)
            for collection in ALLOWED_COLLECTIONS
        },
        "equal_counts": {
            collection: sum(1 for key in equal_keys if key[0] == collection)
            for collection in ALLOWED_COLLECTIONS
        },
    }


def _audit_event(plan_sha256: str, slice_sha256: str, generated_at: str) -> dict[str, Any]:
    event_id = f"evt_t612_{_payload_sha256({'plan': plan_sha256, 'slice': slice_sha256})[:32]}"
    event = {
        "event_id": event_id,
        "actor": "t612_primary_promotion",
        "action": "promote_research_report_clone_slice",
        "resource_type": "research_report_recovery_slice",
        "resource_id": f"slice:{slice_sha256[:24]}",
        "source": "postgres_clone_insert_only",
        "version": "t612-v1",
        "model_version": "",
        "prompt_version": "",
        "approval_state": "operator_confirmed_insert_only",
        "trace_id": f"t612:{plan_sha256[:24]}",
        "timestamp": _parse_time(generated_at, field_name="run2.execution.generated_at").isoformat(),
    }
    return event


def _read_audit(cursor: Any, event_id: str) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT event_id, actor, action, resource_type, resource_id, source, version, model_version, "
        "prompt_version, approval_state, trace_id, payload, timestamp "
        "FROM ai_quant.audit_log WHERE event_id = %s",
        (event_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    timestamp = row[12]
    normalized_time = timestamp.astimezone(timezone.utc).isoformat() if hasattr(timestamp, "astimezone") else _parse_time(timestamp, field_name="audit.timestamp").isoformat()
    return {
        "event_id": str(row[0]),
        "actor": str(row[1]),
        "action": str(row[2]),
        "resource_type": str(row[3]),
        "resource_id": str(row[4]),
        "source": str(row[5]),
        "version": str(row[6]),
        "model_version": str(row[7]),
        "prompt_version": str(row[8]),
        "approval_state": str(row[9]),
        "trace_id": str(row[10]),
        "payload": _json_object(row[11], label="promotion audit payload"),
        "timestamp": normalized_time,
    }


def _audit_storage_row(event: Mapping[str, Any]) -> dict[str, Any]:
    return {**dict(event), "payload": dict(event)}


def _context_confirmation(context: Mapping[str, Any]) -> str:
    confirmation_core = {
        "schema_version": "research-report-primary-promotion-confirmation-v1",
        "source_identity": context["source_snapshot"]["identity"],
        "target_identity": context["target_snapshot"]["identity"],
        "source_backup_dump_sha256": context["source_backup"]["dump_sha256"],
        "target_backup_dump_sha256": context["target_backup"]["dump_sha256"],
        "plan_sha256": context["plan_sha256"],
        "run1_artifact_sha256": context["artifact_hashes"]["run1"],
        "run2_artifact_sha256": context["artifact_hashes"]["run2"],
        "quiescence_proof_sha256": context["quiescence"]["proof_sha256"],
        "slice_sha256": context["slice"]["slice_sha256"],
        "target_table_counts": context["target_snapshot"]["table_counts"],
        "target_research_counts": context["target_snapshot"]["research_counts"],
        "insert_counts": context["target_diff"]["insert_counts"],
        "equal_counts": context["target_diff"]["equal_counts"],
    }
    return f"T612_PROMOTE:{_payload_sha256(confirmation_core)}"


def prepare_promotion(
    *,
    source_dsn: str,
    target_dsn: str,
    plan_path: str | Path,
    run1_path: str | Path,
    run2_path: str | Path,
    source_backup_path: str | Path,
    target_backup_path: str | Path,
    quiescence_proof_path: str | Path,
    connect: Callable[[str], Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    connect = connect or _default_connect
    now = now or _utcnow()
    source_database = _database_name(source_dsn)
    target_database = _database_name(target_dsn)
    if target_database != PRIMARY_DATABASE:
        raise PromotionRefused("promotion target database must be exactly ai_quant")
    if source_database == PRIMARY_DATABASE or not re.search(r"(?:clone|pilot|restore|test)", source_database):
        raise PromotionRefused("promotion source must be an explicitly named non-primary clone database")

    plan_file, plan, plan_file_sha = _artifact(plan_path, label="recovery plan")
    run1_file, run1_payload, run1_sha = _artifact(run1_path, label="clone run1")
    run2_file, run2_payload, run2_sha = _artifact(run2_path, label="clone run2")
    source_manifest_file, source_manifest, source_manifest_sha = _artifact(source_backup_path, label="source backup")
    target_manifest_file, target_manifest, target_manifest_sha = _artifact(target_backup_path, label="target backup")
    proof_file, proof, proof_file_sha = _artifact(quiescence_proof_path, label="quiescence proof")

    selected = _selected_plan_rows(plan)
    run1 = _validate_execution(run1_payload, label="clone run1", plan=plan, selected=selected, require_created=True)
    run2 = _validate_execution(run2_payload, label="clone run2", plan=plan, selected=selected, require_created=False)
    source_snapshot, source_rows = _read_source_context(source_dsn, selected=selected, connect=connect)
    source_slice = _validate_source_slice(source_rows, selected=selected, run1=run1, run2=run2)
    keys = _record_keys(source_rows)
    target_snapshot, target_rows = _read_target_context(target_dsn, keys=keys, connect=connect)

    source_identity = source_snapshot["identity"]
    target_identity = target_snapshot["identity"]
    if source_identity["database_name"] != source_database or target_identity["database_name"] != target_database:
        raise PromotionRefused("runtime database identity does not match the supplied DSNs")
    if source_identity["database_oid"] == target_identity["database_oid"]:
        raise PromotionRefused("source and target database OIDs must be distinct")
    if source_identity["postgres_system_identifier"] != target_identity["postgres_system_identifier"]:
        raise PromotionRefused("source and target must be distinct databases in the same PostgreSQL cluster")
    if int(source_snapshot["other_database_sessions"]) != 0:
        raise PromotionRefused("clone database has another active session; stop the clone app before promotion")
    if int(target_snapshot["other_database_sessions"]) != 0:
        raise PromotionRefused("primary database has another active session; quiescence is not current")

    source_backup = _validate_backup_manifest(
        source_manifest_file,
        source_manifest,
        snapshot=source_snapshot,
        expected_database=source_database,
        now=now,
    )
    target_backup = _validate_backup_manifest(
        target_manifest_file,
        target_manifest,
        snapshot=target_snapshot,
        expected_database=target_database,
        now=now,
    )
    quiescence = _validate_quiescence_proof(
        proof,
        snapshot=target_snapshot,
        target_backup=target_backup,
        now=now,
    )
    target_diff = _target_diff(source_rows, target_rows)
    context: dict[str, Any] = {
        "source_database": source_database,
        "target_database": target_database,
        "source_dsn_redacted": _redact_dsn(source_dsn),
        "target_dsn_redacted": _redact_dsn(target_dsn),
        "source_snapshot": source_snapshot,
        "target_snapshot": target_snapshot,
        "source_backup": source_backup,
        "target_backup": target_backup,
        "quiescence": quiescence,
        "plan_sha256": str(plan["plan_sha256"]),
        "selected": selected,
        "source_rows": source_rows,
        "target_rows": target_rows,
        "slice": source_slice,
        "target_diff": target_diff,
        "artifact_hashes": {
            "plan": plan_file_sha,
            "run1": run1_sha,
            "run2": run2_sha,
            "source_backup_manifest": source_manifest_sha,
            "target_backup_manifest": target_manifest_sha,
            "quiescence_proof_file": proof_file_sha,
        },
        "artifact_names": {
            "plan": plan_file.name,
            "run1": run1_file.name,
            "run2": run2_file.name,
            "source_backup": source_manifest_file.name,
            "target_backup": target_manifest_file.name,
            "quiescence_proof": proof_file.name,
        },
        "audit_event": _audit_event(str(plan["plan_sha256"]), source_slice["slice_sha256"], str(run2_payload["execution"]["generated_at"])),
    }
    context["required_confirmation"] = _context_confirmation(context)
    return context


def _public_preflight(context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "research-report-primary-promotion-v1",
        "status": "ready",
        "mode": "preflight",
        "executed": False,
        "source_database": context["source_database"],
        "target_database": context["target_database"],
        "source_dsn": context["source_dsn_redacted"],
        "target_dsn": context["target_dsn_redacted"],
        "plan_sha256": context["plan_sha256"],
        "selected_report_count": len(context["selected"]),
        "selected_report_ids": sorted(context["selected"]),
        "slice_sha256": context["slice"]["slice_sha256"],
        "slice_counts": context["slice"]["counts"],
        "insert_counts": context["target_diff"]["insert_counts"],
        "equal_existing_counts": context["target_diff"]["equal_counts"],
        "source_backup_dump_sha256": context["source_backup"]["dump_sha256"],
        "target_backup_dump_sha256": context["target_backup"]["dump_sha256"],
        "quiescence_proof_sha256": context["quiescence"]["proof_sha256"],
        "artifact_hashes": context["artifact_hashes"],
        "required_confirmation": context["required_confirmation"],
        "write_contract": {
            "strategy": "single_target_transaction_insert_only",
            "allowed_record_collections": list(ALLOWED_COLLECTIONS),
            "delete_operations": [],
            "update_operations": [],
            "conflict_policy": "equal_preserved_unequal_refused",
            "audit_events": 1,
            "fact_opinion_boundary": BOUNDARY,
            "real_broker_or_order_execution": False,
        },
        "next_action": "review this exact snapshot and rerun with --mode promote and --confirm equal to required_confirmation",
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
    }


def _same_snapshot(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        dict(left.get("identity") or {}) == dict(right.get("identity") or {})
        and dict(left.get("table_counts") or {}) == dict(right.get("table_counts") or {})
        and dict(left.get("research_counts") or {}) == dict(right.get("research_counts") or {})
        and right.get("other_database_sessions") == 0
    )


def _insert_slice_transaction(
    target_dsn: str,
    *,
    context: Mapping[str, Any],
    connect: Callable[[str], Any],
    before_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    rows = list(context["source_rows"])
    keys = _record_keys(rows)
    expected_audit = _audit_storage_row(context["audit_event"])
    inserted_keys: list[tuple[str, str]] = []
    audit_inserted = False
    with closing(connect(target_dsn)) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (PROMOTION_ADVISORY_LOCK,))
                current_snapshot = _query_snapshot(cursor)
                if not _same_snapshot(context["target_snapshot"], current_snapshot):
                    raise PromotionRefused("target changed after preflight; generate fresh backup, proof, and confirmation")
                current_rows: list[dict[str, Any]] = []
                for collection in ALLOWED_COLLECTIONS:
                    current_rows.extend(_fetch_records(cursor, collection, keys.get(collection, [])))
                diff = _target_diff(rows, current_rows)
                if diff != context["target_diff"]:
                    raise PromotionRefused("target slice changed after preflight")
                existing_audit = _read_audit(cursor, str(context["audit_event"]["event_id"]))
                if existing_audit is not None and existing_audit != expected_audit:
                    raise PromotionRefused("target contains a conflicting T-612 audit event")
                for row in rows:
                    if (row["collection"], row["item_id"]) not in diff["insert_keys"]:
                        continue
                    cursor.execute(
                        "INSERT INTO ai_quant.records (collection, item_id, payload, position) "
                        "VALUES (%s, %s, %s::jsonb, %s) ON CONFLICT (collection, item_id) DO NOTHING",
                        (row["collection"], row["item_id"], _canonical_json(row["payload"]), row["position"]),
                    )
                    if int(cursor.rowcount or 0) != 1:
                        raise PromotionRefused("target record changed concurrently during insert-only promotion")
                    inserted_keys.append((row["collection"], row["item_id"]))
                if existing_audit is None:
                    event = context["audit_event"]
                    cursor.execute(
                        "INSERT INTO ai_quant.audit_log (event_id, actor, action, resource_type, resource_id, source, "
                        "version, model_version, prompt_version, approval_state, trace_id, payload, timestamp) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) "
                        "ON CONFLICT (event_id) DO NOTHING",
                        (
                            event["event_id"], event["actor"], event["action"], event["resource_type"],
                            event["resource_id"], event["source"], event["version"], event["model_version"],
                            event["prompt_version"], event["approval_state"], event["trace_id"],
                            _canonical_json(event), event["timestamp"],
                        ),
                    )
                    if int(cursor.rowcount or 0) != 1:
                        raise PromotionRefused("promotion audit event changed concurrently")
                    audit_inserted = True
                if before_commit is not None:
                    before_commit()
    return {"inserted_keys": inserted_keys, "audit_inserted": audit_inserted}


def _expected_post_snapshot(context: Mapping[str, Any], transaction_result: Mapping[str, Any]) -> dict[str, Any]:
    before = context["target_snapshot"]
    inserted_keys = list(transaction_result["inserted_keys"])
    table_counts = dict(before["table_counts"])
    table_counts["records"] += len(inserted_keys)
    table_counts["audit_log"] += 1 if transaction_result["audit_inserted"] else 0
    research_counts = dict(before["research_counts"])
    research_counts["research_reports"] += sum(1 for collection, _item_id in inserted_keys if collection == "research_reports")
    research_counts["research_documents"] += sum(1 for collection, _item_id in inserted_keys if collection == "documents")
    research_counts["research_report_citation_evidence"] += sum(1 for collection, _item_id in inserted_keys if collection == "evidence")
    return {"identity": dict(before["identity"]), "table_counts": table_counts, "research_counts": research_counts}


def _post_commit_verify(
    target_dsn: str,
    *,
    context: Mapping[str, Any],
    transaction_result: Mapping[str, Any],
    connect: Callable[[str], Any],
) -> dict[str, Any]:
    keys = _record_keys(context["source_rows"])
    snapshot, rows = _read_target_context(target_dsn, keys=keys, connect=connect)
    expected_snapshot = _expected_post_snapshot(context, transaction_result)
    if (
        dict(snapshot["identity"]) != expected_snapshot["identity"]
        or dict(snapshot["table_counts"]) != expected_snapshot["table_counts"]
        or dict(snapshot["research_counts"]) != expected_snapshot["research_counts"]
        or snapshot["other_database_sessions"] != 0
    ):
        raise RuntimeError("post-commit database counts differ from the exact expected promotion result")
    if rows != list(context["source_rows"]):
        raise RuntimeError("post-commit promoted rows do not exactly match the attested clone slice")
    with closing(connect(target_dsn)) as connection:
        with connection.cursor() as cursor:
            stored_audit = _read_audit(cursor, str(context["audit_event"]["event_id"]))
    if stored_audit != _audit_storage_row(context["audit_event"]):
        raise RuntimeError("post-commit promotion audit event verification failed")
    return {
        "status": "passed",
        "table_counts": snapshot["table_counts"],
        "research_counts": snapshot["research_counts"],
        "slice_sha256": _payload_sha256(rows),
        "audit_event_id": context["audit_event"]["event_id"],
    }


def promote(
    *,
    source_dsn: str,
    target_dsn: str,
    plan_path: str | Path,
    run1_path: str | Path,
    run2_path: str | Path,
    source_backup_path: str | Path,
    target_backup_path: str | Path,
    quiescence_proof_path: str | Path,
    confirm: str,
    connect: Callable[[str], Any] | None = None,
    now: datetime | None = None,
    before_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    connect = connect or _default_connect
    context = prepare_promotion(
        source_dsn=source_dsn,
        target_dsn=target_dsn,
        plan_path=plan_path,
        run1_path=run1_path,
        run2_path=run2_path,
        source_backup_path=source_backup_path,
        target_backup_path=target_backup_path,
        quiescence_proof_path=quiescence_proof_path,
        connect=connect,
        now=now,
    )
    if not confirm or confirm != context["required_confirmation"]:
        raise PromotionRefused("--confirm must exactly match the current preflight required_confirmation")
    transaction_result = _insert_slice_transaction(
        target_dsn,
        context=context,
        connect=connect,
        before_commit=before_commit,
    )
    verification = _post_commit_verify(target_dsn, context=context, transaction_result=transaction_result, connect=connect)
    inserted_counts = {
        collection: sum(1 for key in transaction_result["inserted_keys"] if key[0] == collection)
        for collection in ALLOWED_COLLECTIONS
    }
    return {
        **_public_preflight(context),
        "status": "completed",
        "mode": "promote",
        "executed": True,
        "inserted_counts": inserted_counts,
        "audit_inserted": bool(transaction_result["audit_inserted"]),
        "post_commit_verification": verification,
        "required_confirmation": "consumed_and_redacted",
    }


def _required_path(value: Path | None, *, option: str) -> Path:
    if value is None:
        raise PromotionRefused(f"{option} is required for this mode")
    return value


def _dsn_from_env(name: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise PromotionRefused("DSN environment variable names must be uppercase safe identifiers")
    value = os.environ.get(name, "").strip()
    if not value:
        raise PromotionRefused(f"required DSN environment variable {name} is empty")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "prove-quiescence", "promote"), default="preflight")
    parser.add_argument("--source-dsn-env", default="AI_QUANT_T612_SOURCE_DSN")
    parser.add_argument("--target-dsn-env", default="AI_QUANT_POSTGRES_DSN")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--run1", type=Path)
    parser.add_argument("--run2", type=Path)
    parser.add_argument("--source-backup", type=Path)
    parser.add_argument("--target-backup", type=Path)
    parser.add_argument("--quiescence-proof", type=Path)
    parser.add_argument("--writer-container", action="append", default=[])
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dsn = _dsn_from_env(args.target_dsn_env)
    if args.mode == "prove-quiescence":
        result = create_quiescence_proof(
            target_dsn=target_dsn,
            target_backup_path=_required_path(args.target_backup, option="--target-backup"),
            writer_containers=args.writer_container,
        )
    else:
        source_dsn = _dsn_from_env(args.source_dsn_env)
        kwargs = {
            "source_dsn": source_dsn,
            "target_dsn": target_dsn,
            "plan_path": _required_path(args.plan, option="--plan"),
            "run1_path": _required_path(args.run1, option="--run1"),
            "run2_path": _required_path(args.run2, option="--run2"),
            "source_backup_path": _required_path(args.source_backup, option="--source-backup"),
            "target_backup_path": _required_path(args.target_backup, option="--target-backup"),
            "quiescence_proof_path": _required_path(args.quiescence_proof, option="--quiescence-proof"),
        }
        if args.mode == "promote":
            result = promote(**kwargs, confirm=args.confirm)
        else:
            result = _public_preflight(prepare_promotion(**kwargs))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_canonical_json(result) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PromotionRefused as exc:
        raise SystemExit(f"T-612 promotion refused: {exc}") from exc
