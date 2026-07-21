#!/usr/bin/env python3
"""Build a path-redacted full research-report identity and recovery decision pack.

The command reads the raw archive, PostgreSQL registry, OpenSearch projection,
historical acceptance artifact, and local backup manifests. It writes only the
requested JSON evidence files. It has no execute mode and never mutates source
files, PostgreSQL, OpenSearch, or backup data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research_reports import content_sha256, report_id_for_path


DEFAULT_FILESYSTEM_ROOT = Path("/home/xionglei/文档/6大投行研报汇总")
DEFAULT_REGISTRY_ROOT = Path("/data/local/research_reports")
DEFAULT_EXTENSIONS = (".pdf", ".txt", ".md")
DEFAULT_BASELINE = Path("artifacts/research-report-completion-audit.json")
DEFAULT_BACKUP_DIR = Path("data/local/backups/postgres")
DEFAULT_MANIFEST_OUTPUT = Path("artifacts/t613-full-registry/identity-manifest.json")
DEFAULT_DECISION_OUTPUT = Path("artifacts/t613-full-registry/recovery-decision.json")
DEFAULT_OPENSEARCH_ENDPOINT = "http://127.0.0.1:19200"
DEFAULT_OPENSEARCH_INDEX = "ai_quant_research"

RIGHTS_POLICY = {
    "policy_id": "local-research-reference-restricted-v1",
    "license_class": "local_research_reference",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "restricted",
    "non_display_use": "restricted",
    "derived_data_use": "restricted",
    "fact_source_allowed": False,
    "automated_trading_use_allowed": False,
    "usage_boundary": "manual_opinion_reference_only",
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def payload_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_extensions(values: Iterable[str]) -> set[str]:
    extensions: set[str] = set()
    for value in values:
        item = str(value).strip().lower()
        if not item:
            continue
        extensions.add(item if item.startswith(".") else f".{item}")
    return extensions


def _safe_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return "configured"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _sanitize_error(exc: BaseException) -> str:
    return re.sub(r"(?i)(password|token|secret|key)=?[^\s,;]*", r"\1=redacted", str(exc))[:300]


def _source_key(relative: Path) -> str:
    source_scope = relative.parts[0] if relative.parts else "root"
    return f"source_{hashlib.sha256(source_scope.encode('utf-8')).hexdigest()[:16]}"


def _public_identity_entry(
    *,
    relative: Path,
    logical_path: Path,
    size_bytes: int,
    digest: str,
) -> dict[str, Any]:
    report_id = report_id_for_path(logical_path)
    return {
        "report_id": report_id,
        "document_id": f"doc_{report_id}",
        "content_sha256": digest,
        "relative_path_sha256": hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest(),
        "logical_path_sha256": hashlib.sha256(str(logical_path).encode("utf-8")).hexdigest(),
        "size_bytes": int(size_bytes),
        "file_type": relative.suffix.lower().lstrip("."),
        "source_key": _source_key(relative),
        "rights_policy_id": RIGHTS_POLICY["policy_id"],
    }


def build_identity_manifest(
    filesystem_root: Path,
    *,
    registry_root: Path,
    extensions: set[str],
) -> dict[str, Any]:
    """Hash every eligible file and return a deterministic, path-redacted manifest."""

    resolved_root = filesystem_root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise FileNotFoundError("research-report archive is unavailable")
    public_entries: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    report_ids: dict[str, list[dict[str, Any]]] = defaultdict(list)
    content_groups: dict[str, list[str]] = defaultdict(list)
    source_counts: Counter[str] = Counter()
    total_bytes = 0

    for directory, subdirectories, filenames in os.walk(resolved_root, followlinks=False):
        subdirectories.sort()
        for filename in sorted(filenames):
            host_path = Path(directory) / filename
            if host_path.is_symlink() or host_path.suffix.lower() not in extensions:
                continue
            try:
                if not host_path.is_file():
                    continue
                stat = host_path.stat()
                digest = content_sha256(host_path)
            except OSError as exc:
                relative = host_path.relative_to(resolved_root)
                failures.append(
                    {
                        "relative_path_sha256": hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest(),
                        "error_code": type(exc).__name__,
                    }
                )
                continue
            relative = host_path.relative_to(resolved_root)
            entry = _public_identity_entry(
                relative=relative,
                logical_path=registry_root / relative,
                size_bytes=int(stat.st_size),
                digest=digest,
            )
            public_entries.append(entry)
            report_ids[str(entry["report_id"])].append(entry)
            content_groups[digest].append(str(entry["report_id"]))
            source_counts[str(entry["source_key"])] += 1
            total_bytes += int(stat.st_size)

    public_entries.sort(key=lambda item: str(item["report_id"]))
    collisions = [
        {
            "report_id": report_id,
            "entry_count": len(rows),
            "content_sha256_values": sorted({str(row["content_sha256"]) for row in rows}),
            "relative_path_sha256_values": sorted(str(row["relative_path_sha256"]) for row in rows),
        }
        for report_id, rows in sorted(report_ids.items())
        if len(rows) > 1
    ]
    duplicate_groups = [
        {
            "content_sha256": digest,
            "canonical_report_id": sorted(ids)[0],
            "report_ids": sorted(ids),
            "duplicate_alias_count": len(ids) - 1,
        }
        for digest, ids in sorted(content_groups.items())
        if len(ids) > 1
    ]
    entries_sha256 = payload_sha256(public_entries)
    stable_core = {
        "identity_policy": {
            "report_id": "rr_ + first 16 hex chars of sha256(absolute logical path)",
            "document_id": "doc_ + report_id",
            "content_identity": "sha256(full file bytes)",
            "path_disclosure": "sha256_only",
            "registry_root_sha256": hashlib.sha256(str(registry_root).encode("utf-8")).hexdigest(),
        },
        "rights_policy": RIGHTS_POLICY,
        "entries": public_entries,
        "hash_failures": sorted(failures, key=lambda item: item["relative_path_sha256"]),
    }
    manifest_sha256 = payload_sha256(stable_core)
    return {
        "schema_version": "research-report-full-identity-manifest-v1",
        "related_task": "T-613",
        "generated_at": utc_iso(),
        "mode": "read_only_full_content_hash",
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
        "identity_policy": stable_core["identity_policy"],
        "rights_policy": RIGHTS_POLICY,
        "summary": {
            "eligible_report_files": len(public_entries),
            "eligible_bytes": total_bytes,
            "content_hash_coverage_count": len(public_entries),
            "content_hash_coverage_rate": 1.0 if public_entries and not failures else 0.0,
            "hash_failure_count": len(failures),
            "report_id_collision_count": len(collisions),
            "unique_content_count": len(content_groups),
            "duplicate_content_group_count": len(duplicate_groups),
            "duplicate_alias_count": sum(int(group["duplicate_alias_count"]) for group in duplicate_groups),
            "source_scope_count": len(source_counts),
            "source_scope_counts": dict(sorted(source_counts.items())),
        },
        "integrity": {
            "entries_sha256": entries_sha256,
            "manifest_sha256": manifest_sha256,
            "rerun_identity_fields_exclude_generated_at": True,
        },
        "entries": public_entries,
        "report_id_collisions": collisions,
        "duplicate_content_groups": duplicate_groups,
        "hash_failures": stable_core["hash_failures"],
        "mutation_guard": {
            "source_files_written": False,
            "postgres_written": False,
            "opensearch_written": False,
            "backup_files_written": False,
            "artifact_outputs_only": True,
        },
    }


def inventory_postgres(
    dsn: str,
    *,
    connect: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if not dsn:
        return {"availability": "not_configured", "rows": [], "count": 0}
    try:
        if connect is None:
            import psycopg

            connect = psycopg.connect
        with connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    """
                    SELECT item_id,
                           COALESCE(payload->>'content_sha256', ''),
                           COALESCE(payload->'rights_tag', '{}'::jsonb)
                    FROM ai_quant.records
                    WHERE collection = 'research_reports'
                    ORDER BY item_id
                    """
                )
                rows = cursor.fetchall()
        public_rows = [
            {
                "report_id": str(report_id),
                "content_sha256": str(content_digest or ""),
                "rights_tag": dict(rights_tag or {}),
            }
            for report_id, content_digest, rights_tag in rows
        ]
        return {
            "availability": "available",
            "connection": {"endpoint": _safe_endpoint(dsn), "query_mode": "transaction_read_only"},
            "count": len(public_rows),
            "rows": public_rows,
        }
    except Exception as exc:  # noqa: BLE001 - unavailable evidence is reported, never hidden
        return {
            "availability": "unavailable",
            "connection": {"endpoint": _safe_endpoint(dsn), "query_mode": "transaction_read_only"},
            "count": 0,
            "rows": [],
            "error_code": type(exc).__name__,
            "error": _sanitize_error(exc),
        }


def _http_json(url: str, body: Mapping[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=canonical_json(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("OpenSearch response was not an object")
    return dict(payload)


def inventory_opensearch_ids(
    endpoint: str,
    index: str,
    *,
    page_size: int = 1000,
    timeout: float = 30.0,
    request_json: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if not endpoint:
        return {"availability": "not_configured", "count": 0, "report_ids": []}
    request_json = request_json or (lambda url, body: _http_json(url, body, timeout=timeout))
    report_ids: list[str] = []
    search_after: list[Any] | None = None
    expected_total: int | None = None
    try:
        while True:
            query: dict[str, Any] = {
                "size": max(1, int(page_size)),
                "track_total_hits": True,
                "_source": ["resource_id"],
                "query": {"term": {"resource_type.keyword": "research_report"}},
                "sort": [{"resource_id.keyword": "asc"}],
            }
            if search_after is not None:
                query["search_after"] = search_after
            payload = request_json(f"{endpoint.rstrip('/')}/{index}/_search", query)
            hits_block = payload.get("hits") if isinstance(payload.get("hits"), Mapping) else {}
            total_block = hits_block.get("total")
            if expected_total is None:
                expected_total = int(total_block.get("value") or 0) if isinstance(total_block, Mapping) else int(total_block or 0)
            hits = hits_block.get("hits") if isinstance(hits_block.get("hits"), list) else []
            if not hits:
                break
            for hit in hits:
                source = hit.get("_source") if isinstance(hit, Mapping) and isinstance(hit.get("_source"), Mapping) else {}
                report_id = str(source.get("resource_id") or "")
                if report_id:
                    report_ids.append(report_id)
            last_sort = hits[-1].get("sort") if isinstance(hits[-1], Mapping) else None
            if len(hits) < max(1, int(page_size)):
                break
            if not isinstance(last_sort, list) or last_sort == search_after:
                raise ValueError("OpenSearch pagination did not advance")
            search_after = list(last_sort)
        unique_ids = sorted(set(report_ids))
        return {
            "availability": "available",
            "endpoint": _safe_endpoint(endpoint),
            "index": index,
            "count": len(unique_ids),
            "reported_total": expected_total,
            "duplicate_projection_id_count": len(report_ids) - len(unique_ids),
            "report_ids": unique_ids,
        }
    except Exception as exc:  # noqa: BLE001 - unavailable evidence must block readiness
        return {
            "availability": "unavailable",
            "endpoint": _safe_endpoint(endpoint),
            "index": index,
            "count": 0,
            "report_ids": [],
            "error_code": type(exc).__name__,
            "error": _sanitize_error(exc),
        }


def load_historical_baseline(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        aggregate = list(payload.get("aggregate_counts") or [])
        values = [int(item) for item in str(aggregate[0]).split("|")] if aggregate else []
        if len(values) < 3:
            raise ValueError("aggregate_counts does not contain report/document/evidence counts")
        return {
            "availability": "available",
            "artifact_name": path.name,
            "generated_at": str(payload.get("generated_at") or ""),
            "research_reports": values[0],
            "research_documents": values[1],
            "citation_evidence": values[2],
            "role": "historical_acceptance_evidence_not_current_state_proof",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "availability": "unavailable",
            "artifact_name": path.name,
            "error_code": type(exc).__name__,
            "error": _sanitize_error(exc),
        }


def _active_retention(value: Any, *, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) > now
    except (TypeError, ValueError):
        return False


def inventory_backup_manifests(
    paths: Iterable[Path],
    *,
    expected_reports: int,
    expected_documents: int,
    expected_evidence: int,
    current_reports: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: item.name):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            counts = payload.get("collection_counts") if isinstance(payload.get("collection_counts"), Mapping) else {}
            restored = (
                payload.get("restored_collection_counts")
                if isinstance(payload.get("restored_collection_counts"), Mapping)
                else {}
            )
            reports = int(counts.get("research_reports") or 0)
            documents = int(counts.get("research_documents") or 0)
            evidence = int(counts.get("research_report_citation_evidence") or 0)
            restore_verified = payload.get("restore_verified") is True
            counts_match = bool(counts) and dict(counts) == dict(restored)
            retained = _active_retention(payload.get("retained_until"), now=now)
            coverage = str(payload.get("research_state_coverage") or "unknown")
            baseline_counts_match = (
                reports == expected_reports
                and documents == expected_documents
                and evidence >= expected_evidence
            )
            historical_coverage_proven = baseline_counts_match and "not_historical" not in coverage
            candidates.append(
                {
                    "manifest_name": path.name,
                    "manifest_sha256": file_sha256(path),
                    "generated_at": str(payload.get("generated_at") or ""),
                    "retained_until": str(payload.get("retained_until") or ""),
                    "restore_verified": restore_verified,
                    "collection_restore_counts_match": counts_match,
                    "retention_active": retained,
                    "source_database_role": "clone" if "clone" in str(payload.get("source_db") or "").lower() or "pilot" in str(payload.get("source_db") or "").lower() else "primary_or_unknown",
                    "research_state_coverage": coverage,
                    "collection_counts": {
                        "research_reports": reports,
                        "research_documents": documents,
                        "research_report_citation_evidence": evidence,
                        "structured_research_reports": int(counts.get("structured_research_reports") or 0),
                        "report_viewpoints": int(counts.get("report_viewpoints") or 0),
                        "report_forecasts": int(counts.get("report_forecasts") or 0),
                    },
                    "full_registry_count_match": reports == expected_reports,
                    "historical_complete_counts_match": baseline_counts_match,
                    "historical_complete_state_proven": (
                        restore_verified and counts_match and retained and historical_coverage_proven
                    ),
                    "current_registry_rollback_candidate": (
                        restore_verified and counts_match and retained and reports == current_reports
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            candidates.append(
                {
                    "manifest_name": path.name,
                    "availability": "unavailable",
                    "error_code": type(exc).__name__,
                    "error": _sanitize_error(exc),
                }
            )
    return {
        "candidate_count": len(candidates),
        "historical_complete_state_candidate_count": sum(
            1 for item in candidates if item.get("historical_complete_state_proven") is True
        ),
        "current_registry_rollback_candidate_count": sum(
            1 for item in candidates if item.get("current_registry_rollback_candidate") is True
        ),
        "registry_only_candidate_count": sum(
            1
            for item in candidates
            if item.get("full_registry_count_match") is True
            and item.get("historical_complete_counts_match") is False
        ),
        "candidates": candidates,
    }


def _rights_restricted(rights: Mapping[str, Any]) -> bool:
    return (
        rights.get("license_class") == "local_research_reference"
        and rights.get("training_allowed") is False
        and rights.get("redistribution_allowed") is False
        and rights.get("display_use") == "restricted"
        and rights.get("non_display_use") == "restricted"
        and rights.get("derived_data_use") == "restricted"
    )


def _gate(gate_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "passed": bool(passed), "detail": detail}


def build_recovery_decision(
    manifest: Mapping[str, Any],
    *,
    postgres: Mapping[str, Any],
    opensearch: Mapping[str, Any],
    baseline: Mapping[str, Any],
    backups: Mapping[str, Any],
    batch_size: int,
) -> dict[str, Any]:
    entries = [dict(item) for item in manifest.get("entries", []) if isinstance(item, Mapping)]
    manifest_by_id = {str(item["report_id"]): item for item in entries}
    raw_ids = set(manifest_by_id)
    postgres_rows = [dict(item) for item in postgres.get("rows", []) if isinstance(item, Mapping)]
    postgres_by_id = {str(item.get("report_id") or ""): item for item in postgres_rows if item.get("report_id")}
    postgres_ids = set(postgres_by_id)
    opensearch_ids = {str(item) for item in opensearch.get("report_ids", []) if str(item)}

    exact_primary_ids = sorted(
        report_id
        for report_id in raw_ids & postgres_ids
        if str(manifest_by_id[report_id].get("content_sha256") or "")
        == str(postgres_by_id[report_id].get("content_sha256") or "")
    )
    content_conflict_ids = sorted(
        report_id
        for report_id in raw_ids & postgres_ids
        if report_id not in set(exact_primary_ids)
    )
    duplicate_alias_ids: set[str] = set()
    duplicate_policy: list[dict[str, Any]] = []
    exact_primary_set = set(exact_primary_ids)
    for raw_group in manifest.get("duplicate_content_groups", []):
        if not isinstance(raw_group, Mapping):
            continue
        ids = sorted(str(item) for item in raw_group.get("report_ids", []) if str(item))
        primary_matches = sorted(set(ids) & exact_primary_set)
        canonical = primary_matches[0] if primary_matches else (ids[0] if ids else "")
        aliases = [item for item in ids if item != canonical]
        duplicate_alias_ids.update(aliases)
        duplicate_policy.append(
            {
                "content_sha256": str(raw_group.get("content_sha256") or ""),
                "canonical_report_id": canonical,
                "duplicate_alias_report_ids": aliases,
                "decision": "exclude_aliases_pending_manual_review",
            }
        )

    recovery_ids = sorted(
        raw_ids - exact_primary_set - set(content_conflict_ids) - duplicate_alias_ids
    )
    size = max(1, int(batch_size))
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(recovery_ids), size):
        report_ids = recovery_ids[offset : offset + size]
        batch_number = len(batches) + 1
        batch_core = {
            "identity_manifest_sha256": str(manifest.get("integrity", {}).get("manifest_sha256") or ""),
            "report_ids": report_ids,
        }
        batches.append(
            {
                "batch_id": f"t613-batch-{batch_number:04d}",
                "report_count": len(report_ids),
                "report_ids": report_ids,
                "batch_sha256": payload_sha256(batch_core),
                "idempotency_key": f"t613:{payload_sha256(batch_core)[:24]}",
                "mode": "clone_reparse_insert_only",
            }
        )

    rights_noncompliant_primary = sorted(
        str(item.get("report_id") or "")
        for item in postgres_rows
        if not _rights_restricted(item.get("rights_tag") if isinstance(item.get("rights_tag"), Mapping) else {})
    )
    inventory_gates = [
        _gate(
            "full_content_hash_coverage",
            int(manifest.get("summary", {}).get("content_hash_coverage_count") or 0) == len(entries)
            and not manifest.get("hash_failures"),
            "every eligible raw report must have a full-file SHA-256",
        ),
        _gate(
            "report_id_collision_free",
            not manifest.get("report_id_collisions"),
            "path-derived report IDs must be globally unique",
        ),
        _gate(
            "postgres_snapshot_available",
            postgres.get("availability") == "available",
            "the current PostgreSQL registry must be read in a read-only transaction",
        ),
        _gate(
            "postgres_content_conflict_free",
            not content_conflict_ids,
            "current report IDs must match raw content identity",
        ),
        _gate(
            "postgres_rights_boundary_enforced",
            not rights_noncompliant_primary,
            "current report rows must remain restricted local opinion references",
        ),
        _gate(
            "opensearch_projection_available",
            opensearch.get("availability") == "available",
            "the derived report projection must be available for forensic comparison",
        ),
        _gate(
            "opensearch_identity_coverage_complete",
            opensearch_ids == raw_ids,
            "OpenSearch report projection IDs must exactly cover the raw identity set",
        ),
        _gate(
            "current_rollback_candidate_available",
            int(backups.get("current_registry_rollback_candidate_count") or 0) > 0,
            "at least one retained restore-verified backup must cover the current registry count",
        ),
    ]
    planning_ready = all(bool(item["passed"]) for item in inventory_gates)
    execution_gates = [
        *inventory_gates,
        _gate(
            "new_pre_execute_collection_backup",
            False,
            "a new collection-aware primary backup is mandatory after manual batch approval",
        ),
        _gate(
            "independent_clone_double_run",
            False,
            "the selected full-registry batch has not completed an independent clone double run",
        ),
        _gate(
            "manual_approval_recorded",
            False,
            "no human approval token is accepted or stored by this read-only command",
        ),
    ]
    baseline_reports = int(baseline.get("research_reports") or 0)
    baseline_documents = int(baseline.get("research_documents") or 0)
    baseline_evidence = int(baseline.get("citation_evidence") or 0)
    return {
        "schema_version": "research-report-registry-recovery-decision-v1",
        "related_task": "T-613",
        "generated_at": utc_iso(),
        "mode": "read_only_decision_pack",
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
        "status": "ready_for_manual_strategy_review" if planning_ready else "inventory_review_blocked",
        "execution_authorized": False,
        "automatic_recovery_authorized": False,
        "input_evidence": {
            "identity_manifest_sha256": str(manifest.get("integrity", {}).get("manifest_sha256") or ""),
            "entries_sha256": str(manifest.get("integrity", {}).get("entries_sha256") or ""),
            "historical_baseline": {
                "availability": str(baseline.get("availability") or "unknown"),
                "artifact_name": str(baseline.get("artifact_name") or ""),
                "research_reports": baseline_reports,
                "research_documents": baseline_documents,
                "citation_evidence": baseline_evidence,
            },
        },
        "identity_comparison": {
            "raw_report_count": len(raw_ids),
            "postgres_report_count": len(postgres_ids),
            "postgres_exact_content_match_count": len(exact_primary_ids),
            "postgres_exact_report_ids": exact_primary_ids,
            "postgres_missing_report_count": len(raw_ids - postgres_ids),
            "postgres_extra_report_count": len(postgres_ids - raw_ids),
            "postgres_extra_report_ids": sorted(postgres_ids - raw_ids),
            "postgres_content_conflict_count": len(content_conflict_ids),
            "postgres_content_conflict_report_ids": content_conflict_ids,
            "opensearch_report_count": len(opensearch_ids),
            "opensearch_missing_report_count": len(raw_ids - opensearch_ids),
            "opensearch_extra_report_count": len(opensearch_ids - raw_ids),
            "duplicate_content_group_count": len(duplicate_policy),
            "duplicate_alias_count": len(duplicate_alias_ids),
        },
        "rights_assessment": {
            "recovery_policy": RIGHTS_POLICY,
            "current_primary_noncompliant_count": len(rights_noncompliant_primary),
            "current_primary_noncompliant_report_ids": rights_noncompliant_primary,
            "source_legal_provenance_independently_verified": False,
            "required_human_boundary": "local_manual_opinion_reference_only_no_fact_or_training_promotion",
        },
        "backup_assessment": dict(backups),
        "historical_state_assessment": {
            "historical_complete_backup_available": int(backups.get("historical_complete_state_candidate_count") or 0) > 0,
            "historical_registry_only_backup_available": int(backups.get("registry_only_candidate_count") or 0) > 0,
            "raw_identity_registry_rebuild_possible": planning_ready,
            "historical_document_and_evidence_restore_proven": int(backups.get("historical_complete_state_candidate_count") or 0) > 0,
            "reparse_required": int(backups.get("historical_complete_state_candidate_count") or 0) == 0,
            "decision": "retain_current_slice_and_prepare_bounded_clone_reparse",
            "reason": "no retained restore-verified backup proves the historical report/document/citation state",
        },
        "duplicate_policy": duplicate_policy,
        "recovery_plan": {
            "strategy": "retain_primary_then_clone_reparse_unique_content_batches",
            "batch_size": size,
            "candidate_report_count": len(recovery_ids),
            "excluded_current_exact_count": len(exact_primary_ids),
            "excluded_content_conflict_count": len(content_conflict_ids),
            "excluded_duplicate_alias_count": len(duplicate_alias_ids),
            "batch_count": len(batches),
            "batches": batches,
            "write_contract": {
                "target": "independently_attested_clone_only",
                "insert_only": True,
                "updates_allowed": False,
                "deletes_allowed": False,
                "raw_files_preserved": True,
                "opensearch_preserved": True,
                "primary_writes_allowed": False,
                "paper_only": True,
                "broker_connected": False,
                "live_execution_allowed": False,
            },
        },
        "inventory_gates": inventory_gates,
        "execution_gates": execution_gates,
        "failed_execution_gate_ids": [item["gate_id"] for item in execution_gates if not item["passed"]],
        "mutation_guard": {
            "source_files_written": False,
            "postgres_written": False,
            "opensearch_written": False,
            "backup_files_written": False,
            "artifact_outputs_only": True,
        },
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filesystem-root", type=Path, default=DEFAULT_FILESYSTEM_ROOT)
    parser.add_argument("--registry-root", type=Path, default=DEFAULT_REGISTRY_ROOT)
    parser.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS))
    parser.add_argument("--postgres-dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", ""))
    parser.add_argument(
        "--opensearch-endpoint",
        default=os.environ.get("AI_QUANT_OPENSEARCH_ENDPOINT", DEFAULT_OPENSEARCH_ENDPOINT),
    )
    parser.add_argument("--opensearch-index", default=os.environ.get("AI_QUANT_OPENSEARCH_INDEX", DEFAULT_OPENSEARCH_INDEX))
    parser.add_argument("--baseline-artifact", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--opensearch-page-size", type=int, default=1000)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--decision-output", type=Path, default=DEFAULT_DECISION_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    extensions = _normalize_extensions(str(args.extensions).split(","))
    manifest = build_identity_manifest(
        args.filesystem_root,
        registry_root=args.registry_root,
        extensions=extensions,
    )
    postgres = inventory_postgres(str(args.postgres_dsn))
    opensearch = inventory_opensearch_ids(
        str(args.opensearch_endpoint),
        str(args.opensearch_index),
        page_size=max(1, int(args.opensearch_page_size)),
        timeout=max(1.0, float(args.timeout_seconds)),
    )
    baseline = load_historical_baseline(args.baseline_artifact)
    baseline_reports = int(baseline.get("research_reports") or 0)
    baseline_documents = int(baseline.get("research_documents") or 0)
    baseline_evidence = int(baseline.get("citation_evidence") or 0)
    backups = inventory_backup_manifests(
        args.backup_dir.glob("*.manifest.json"),
        expected_reports=baseline_reports or int(manifest["summary"]["eligible_report_files"]),
        expected_documents=baseline_documents or int(manifest["summary"]["eligible_report_files"]),
        expected_evidence=baseline_evidence,
        current_reports=int(postgres.get("count") or 0),
    )
    decision = build_recovery_decision(
        manifest,
        postgres=postgres,
        opensearch=opensearch,
        baseline=baseline,
        backups=backups,
        batch_size=max(1, int(args.batch_size)),
    )
    _write_json(args.manifest_output, manifest)
    _write_json(args.decision_output, decision)
    print(
        json.dumps(
            {
                "status": decision["status"],
                "execution_authorized": False,
                "identity_manifest_sha256": manifest["integrity"]["manifest_sha256"],
                "eligible_report_files": manifest["summary"]["eligible_report_files"],
                "content_hash_coverage_rate": manifest["summary"]["content_hash_coverage_rate"],
                "recovery_candidate_count": decision["recovery_plan"]["candidate_report_count"],
                "batch_count": decision["recovery_plan"]["batch_count"],
                "manifest_output": str(args.manifest_output),
                "decision_output": str(args.decision_output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if decision["status"] == "ready_for_manual_strategy_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
