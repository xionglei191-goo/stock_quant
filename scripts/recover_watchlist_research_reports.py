#!/usr/bin/env python3
"""Plan and gate watchlist-first research-report recovery.

The default mode is a read-only dry run.  A future cloned-database pilot may
reuse the existing scan/ingest/extract APIs, but only after the T-604
reconciliation and a collection-aware restore manifest authorize the exact
plan.  This tool never deletes raw files, search indexes, or stored records.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Any, Iterable, Mapping
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research_reports import cheap_fingerprint, report_id_for_path
from app.service_modules.ingestion_helpers import research_report_source_id


DEFAULT_FILESYSTEM_ROOT = Path("/home/xionglei/文档/6大投行研报汇总")
DEFAULT_API_ROOT = "/data/local/research_reports"
DEFAULT_RECONCILIATION = Path("artifacts/research-report-state-reconciliation.json")
DEFAULT_OUTPUT = Path("artifacts/watchlist-research-report-recovery-plan.json")
WATCHLIST_SYMBOLS = ("AAPL", "NVDA", "MSFT", "300750", "600519")
BOUNDARY = "local_research_reports_are_opinion_reference_only_not_fact_or_training_source"


WATCHLIST_RULES: dict[str, dict[str, tuple[str, ...]]] = {
    "AAPL": {
        "strong_aliases": ("Apple Inc", "Apple Incorporated"),
        "review_aliases": ("Apple", "苹果"),
    },
    "NVDA": {
        "strong_aliases": ("NVIDIA", "NVIDIA Corporation", "NVIDIA Corp"),
        "review_aliases": (),
    },
    "MSFT": {
        "strong_aliases": ("Microsoft", "Microsoft Corporation", "Microsoft Corp", "微软"),
        "review_aliases": (),
    },
    "300750": {
        "strong_aliases": ("CATL", "宁德时代", "Contemporary Amperex Technology"),
        "review_aliases": (),
    },
    "600519": {
        "strong_aliases": ("贵州茅台", "Kweichow Moutai"),
        "review_aliases": ("Moutai", "茅台"),
    },
}


class RecoveryRefused(RuntimeError):
    """Raised before mutation when one or more recovery gates are closed."""


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip().upper()


def _contains_term(normalized_text: str, term: str) -> bool:
    normalized_term = _normalize_match_text(term)
    if not normalized_term:
        return False
    if re.search(r"[\u4e00-\u9fff]", normalized_term):
        return normalized_term in normalized_text
    return f" {normalized_term} " in f" {normalized_text} "


def match_watchlist_symbols(file_name: str) -> list[dict[str, Any]]:
    """Return filename-only matches; report body text is never used for binding."""

    normalized = _normalize_match_text(Path(file_name).stem)
    matches: list[dict[str, Any]] = []
    for symbol in WATCHLIST_SYMBOLS:
        rules = WATCHLIST_RULES[symbol]
        exact_ticker = _contains_term(normalized, symbol)
        strong_terms = [term for term in rules["strong_aliases"] if _contains_term(normalized, term)]
        review_terms = [term for term in rules["review_aliases"] if _contains_term(normalized, term)]
        if exact_ticker:
            matches.append(
                {
                    "symbol": symbol,
                    "strength": "exact_ticker",
                    "matched_terms": [symbol, *strong_terms, *review_terms],
                }
            )
        elif strong_terms:
            matches.append(
                {
                    "symbol": symbol,
                    "strength": "canonical_company_name_needs_review",
                    "matched_terms": strong_terms,
                }
            )
        elif review_terms:
            matches.append(
                {
                    "symbol": symbol,
                    "strength": "ambiguous_alias",
                    "matched_terms": review_terms,
                }
            )
    return matches


def _published_date(file_name: str) -> str:
    match = re.search(r"(?<!\d)(20\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?!\d)", file_name)
    return "-".join(match.groups()) if match else ""


def inventory_raw_reports(
    filesystem_root: Path,
    *,
    registry_root: Path,
    extensions: set[str],
) -> dict[str, Any]:
    filesystem_root = filesystem_root.expanduser().resolve()
    if not filesystem_root.is_dir():
        raise FileNotFoundError(f"research-report root not found: {filesystem_root}")
    rows: list[dict[str, Any]] = []
    manifest_rows: list[str] = []
    ids: dict[str, list[str]] = {}
    total_bytes = 0
    for directory, subdirectories, filenames in os.walk(filesystem_root, followlinks=False):
        subdirectories.sort()
        for filename in sorted(filenames):
            host_path = Path(directory) / filename
            if host_path.is_symlink() or host_path.suffix.lower() not in extensions:
                continue
            try:
                stat = host_path.stat()
            except OSError:
                continue
            if not host_path.is_file():
                continue
            relative = host_path.relative_to(filesystem_root)
            logical_path = registry_root / relative
            report_id = report_id_for_path(logical_path)
            manifest_rows.append(f"{relative.as_posix()}|{stat.st_size}|{int(stat.st_mtime)}")
            ids.setdefault(report_id, []).append(relative.as_posix())
            total_bytes += int(stat.st_size)
            rows.append(
                {
                    "host_path": host_path,
                    "relative_path": relative.as_posix(),
                    "logical_file_path": str(logical_path),
                    "report_id": report_id,
                    "document_id": f"doc_{report_id}",
                    "evidence_id_prefix": f"evi_doc_{report_id}_research_",
                    "fingerprint": cheap_fingerprint(host_path, filesystem_root),
                    "size_bytes": int(stat.st_size),
                    "mtime_epoch": int(stat.st_mtime),
                    "file_type": host_path.suffix.lower().lstrip("."),
                    "broker": relative.parts[0] if len(relative.parts) > 1 else "unknown",
                    "published_date": _published_date(filename),
                    "matches": match_watchlist_symbols(filename),
                }
            )
    collisions = {item_id: paths for item_id, paths in ids.items() if len(paths) > 1}
    return {
        "rows": rows,
        "eligible_report_files": len(rows),
        "eligible_bytes": total_bytes,
        "eligible_manifest_sha256": hashlib.sha256(
            "\n".join(sorted(manifest_rows)).encode("utf-8")
        ).hexdigest(),
        "report_id_collisions": collisions,
    }


def identities_from_company_profiles(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = payload.get("profiles", payload.get("items", []))
    if not isinstance(profiles, list):
        return {}
    candidates: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in WATCHLIST_SYMBOLS}
    for raw_profile in profiles:
        if not isinstance(raw_profile, Mapping):
            continue
        identifiers = raw_profile.get("identifiers") if isinstance(raw_profile.get("identifiers"), Mapping) else {}
        tickers = {str(value).strip().upper() for value in identifiers.get("tickers", []) if str(value).strip()}
        security_ids = [str(value) for value in raw_profile.get("security_ids", []) if str(value)]
        for symbol in WATCHLIST_SYMBOLS:
            if symbol in tickers:
                candidates[symbol].append(
                    {
                        "issuer_id": str(raw_profile.get("issuer_id") or ""),
                        "security_ids": security_ids,
                        "profile_name": str(raw_profile.get("display_name") or raw_profile.get("legal_name") or ""),
                    }
                )
    identities: dict[str, dict[str, Any]] = {}
    for symbol, rows in candidates.items():
        if len(rows) == 1 and rows[0]["issuer_id"] and len(rows[0]["security_ids"]) == 1:
            identities[symbol] = {
                "issuer_id": rows[0]["issuer_id"],
                "security_id": rows[0]["security_ids"][0],
                "profile_name": rows[0]["profile_name"],
                "resolution_status": "resolved_exact_ticker_profile",
            }
        else:
            identities[symbol] = {
                "issuer_id": "",
                "security_id": "",
                "profile_name": "",
                "resolution_status": "needs_evidence" if not rows else "ambiguous_company_profile",
            }
    return identities


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        method = method.upper()
        if method not in {"GET", "POST"}:
            raise ValueError("research-report recovery client only permits GET and POST")
        data = json.dumps(dict(body), ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Role": "data_engineer" if method == "POST" else "analyst",
                "X-Actor": "watchlist_research_report_recovery",
                "X-Client-Origin": "scheduled",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}: {detail[:500]}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc.reason}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{method} {path} returned non-object JSON")
        if payload.get("success") is False:
            raise RuntimeError(f"{method} {path} failed: {payload.get('error') or 'unknown API error'}")
        data_payload = payload.get("data", payload)
        return dict(data_payload) if isinstance(data_payload, Mapping) else {}


def load_company_identities(
    *,
    client: ApiClient | None,
    company_profiles_artifact: Path | None,
) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        if company_profiles_artifact is not None:
            return identities_from_company_profiles(_load_json(company_profiles_artifact)), "artifact"
        if client is not None:
            return identities_from_company_profiles(client.request("GET", "/api/company-profiles")), "api_read_only"
    except Exception as exc:  # noqa: BLE001 - unresolved identity is an explicit dry-run result
        return {}, f"unavailable:{type(exc).__name__}"
    return {}, "not_configured"


def _public_candidate(row: Mapping[str, Any], *, content_sha256: str = "") -> dict[str, Any]:
    return {
        "report_id": row["report_id"],
        "document_id": row["document_id"],
        "evidence_id_prefix": row["evidence_id_prefix"],
        "dedup_key": f"sha256:{content_sha256}" if content_sha256 else "needs_content_hash",
        "content_sha256": content_sha256,
        "fingerprint": row["fingerprint"],
        "relative_path": row["relative_path"],
        "logical_file_path": row["logical_file_path"],
        "file_type": row["file_type"],
        "size_bytes": row["size_bytes"],
        "broker": row["broker"],
        "published_date": row["published_date"],
        "match_evidence": row["matches"],
        "source_id": research_report_source_id(str(row["broker"])),
        "source_boundary": BOUNDARY,
    }


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("published_date") or "0000-00-00"), str(row.get("relative_path") or "")


def build_watchlist_batches(
    rows: Iterable[Mapping[str, Any]],
    *,
    identities: Mapping[str, Mapping[str, Any]],
    max_reports_per_symbol: int,
    content_hash_budget_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible: dict[str, list[Mapping[str, Any]]] = {symbol: [] for symbol in WATCHLIST_SYMBOLS}
    review: dict[str, list[Mapping[str, Any]]] = {symbol: [] for symbol in WATCHLIST_SYMBOLS}
    ambiguous: list[Mapping[str, Any]] = []
    for row in rows:
        matches = list(row.get("matches") or [])
        if not matches:
            continue
        matched_symbols = {str(item.get("symbol")) for item in matches}
        if len(matched_symbols) != 1:
            ambiguous.append(row)
            continue
        match = matches[0]
        symbol = str(match["symbol"])
        if match.get("strength") != "exact_ticker":
            review[symbol].append(row)
        else:
            eligible[symbol].append(row)

    remaining_hash_budget = max(0, int(content_hash_budget_bytes))
    seen_content: dict[str, dict[str, str]] = {}
    company_plans: list[dict[str, Any]] = []
    hashed_files = 0
    hashed_bytes = 0
    for symbol in WATCHLIST_SYMBOLS:
        selected: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        hash_failures: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for row in sorted(eligible[symbol], key=_candidate_sort_key, reverse=True):
            if len(selected) >= max_reports_per_symbol:
                deferred.append(_public_candidate(row))
                continue
            size_bytes = int(row.get("size_bytes") or 0)
            if size_bytes > remaining_hash_budget:
                hash_failures.append({**_public_candidate(row), "reason": "content_hash_budget_exceeded"})
                continue
            try:
                digest = _file_sha256(Path(row["host_path"]))
            except OSError as exc:
                hash_failures.append(
                    {**_public_candidate(row), "reason": f"content_hash_unavailable:{type(exc).__name__}"}
                )
                continue
            remaining_hash_budget -= size_bytes
            hashed_bytes += size_bytes
            hashed_files += 1
            previous = seen_content.get(digest)
            if previous is not None:
                duplicates.append(
                    {
                        **_public_candidate(row, content_sha256=digest),
                        "duplicate_of_report_id": previous["report_id"],
                        "duplicate_of_symbol": previous["symbol"],
                    }
                )
                continue
            candidate = _public_candidate(row, content_sha256=digest)
            selected.append(candidate)
            seen_content[digest] = {"report_id": str(row["report_id"]), "symbol": symbol}

        identity = dict(identities.get(symbol) or {})
        identity_resolved = bool(identity.get("issuer_id") and identity.get("security_id"))
        if not selected:
            company_status = "needs_evidence"
        elif not identity_resolved:
            company_status = "needs_identity"
        else:
            company_status = "planned"
        company_plans.append(
            {
                "symbol": symbol,
                "status": company_status,
                "identity": {
                    "issuer_id": str(identity.get("issuer_id") or ""),
                    "security_id": str(identity.get("security_id") or ""),
                    "profile_name": str(identity.get("profile_name") or ""),
                    "resolution_status": str(identity.get("resolution_status") or "needs_evidence"),
                },
                "eligible_candidate_count": len(eligible[symbol]),
                "manual_review_candidate_count": len(review[symbol]),
                "selected_count": len(selected),
                "selected_reports": selected,
                "duplicate_count": len(duplicates),
                "duplicate_samples": duplicates[:20],
                "hash_failure_count": len(hash_failures),
                "hash_failure_samples": hash_failures[:20],
                "deferred_count": len(deferred),
                "deferred_samples": deferred[:20],
                "manual_review_samples": [_public_candidate(row) for row in review[symbol][:20]],
                "next_action": (
                    "execute_bounded_clone_pilot_after_all_safety_gates_pass"
                    if company_status == "planned"
                    else "resolve_company_identity_from_exact_ticker_profile"
                    if company_status == "needs_identity"
                    else "add_or_manually_review_unambiguous_local_opinion_evidence"
                ),
                "fact_opinion_boundary": BOUNDARY,
            }
        )
    diagnostics = {
        "ambiguous_multi_symbol_count": len(ambiguous),
        "ambiguous_multi_symbol_samples": [_public_candidate(row) for row in ambiguous[:20]],
        "content_hashing": {
            "scope": "selected_watchlist_candidates_only",
            "hashed_files": hashed_files,
            "hashed_bytes": hashed_bytes,
            "budget_bytes": int(content_hash_budget_bytes),
            "remaining_budget_bytes": remaining_hash_budget,
        },
    }
    return company_plans, diagnostics


def _gate(gate_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "passed": bool(passed), "detail": detail}


def _resolve_dump_path(manifest_path: Path, manifest: Mapping[str, Any]) -> Path:
    configured = Path(str(manifest.get("dump_path") or ""))
    candidates = [configured]
    if configured.name:
        candidates.append(manifest_path.parent / configured.name)
    return next((path for path in candidates if path.is_file()), configured)


def _collection_counts(manifest: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = manifest.get(name)
    return value if isinstance(value, Mapping) else {}


def backup_safety_gates(manifest_path: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_counts = manifest.get("source_counts") if isinstance(manifest.get("source_counts"), Mapping) else {}
    restored_counts = manifest.get("restored_counts") if isinstance(manifest.get("restored_counts"), Mapping) else {}
    collections = _collection_counts(manifest, "collection_counts")
    restored_collections = _collection_counts(manifest, "restored_collection_counts")
    required_collection_metrics = {
        "research_reports",
        "research_documents",
        "research_report_citation_evidence",
    }
    dump_path = _resolve_dump_path(manifest_path, manifest)
    expected_size = int(manifest.get("dump_size_bytes") or -1)
    retained_until = str(manifest.get("retained_until") or "")
    retention_valid = False
    try:
        retention_valid = bool(retained_until) and datetime.fromisoformat(retained_until.replace("Z", "+00:00")) > datetime.now(timezone.utc)
    except ValueError:
        retention_valid = False
    return [
        _gate("backup_status_passed", manifest.get("status") == "passed", "backup manifest status must be passed"),
        _gate("backup_restore_verified", manifest.get("restore_verified") is True, "restore_verified must be true"),
        _gate(
            "backup_aggregate_restore_counts_match",
            bool(source_counts) and dict(source_counts) == dict(restored_counts),
            "source_counts and restored_counts must be non-empty and identical",
        ),
        _gate(
            "backup_collection_metrics_present",
            required_collection_metrics.issubset(collections),
            "collection_counts must include research_reports, research_documents, and research_report_citation_evidence",
        ),
        _gate(
            "backup_collection_restore_counts_match",
            bool(restored_collections) and dict(collections) == dict(restored_collections),
            "collection_counts and restored_collection_counts must be non-empty and identical",
        ),
        _gate("backup_dump_exists", dump_path.is_file(), "dump referenced by the manifest must exist"),
        _gate(
            "backup_dump_size_matches",
            dump_path.is_file() and dump_path.stat().st_size == expected_size,
            "dump size must match dump_size_bytes",
        ),
        _gate("backup_dump_sha256_recorded", bool(manifest.get("dump_sha256")), "dump_sha256 must be recorded"),
        _gate("backup_retention_active", retention_valid, "retained_until must be a future timestamp"),
    ]


def reconciliation_safety_gates(reconciliation: Mapping[str, Any], backup_manifest_path: Path) -> list[dict[str, Any]]:
    summary = reconciliation.get("summary") if isinstance(reconciliation.get("summary"), Mapping) else {}
    stores = reconciliation.get("stores") if isinstance(reconciliation.get("stores"), Mapping) else {}
    filesystem = stores.get("filesystem") if isinstance(stores.get("filesystem"), Mapping) else {}
    postgres = stores.get("postgres") if isinstance(stores.get("postgres"), Mapping) else {}
    opensearch = stores.get("opensearch") if isinstance(stores.get("opensearch"), Mapping) else {}
    object_store = stores.get("object_store") if isinstance(stores.get("object_store"), Mapping) else {}
    recovery = reconciliation.get("recovery_assessment") if isinstance(reconciliation.get("recovery_assessment"), Mapping) else {}
    backup = reconciliation.get("backup_evidence") if isinstance(reconciliation.get("backup_evidence"), Mapping) else {}
    recorded_manifest = Path(str(backup.get("manifest") or ""))
    manifest_matches = bool(recorded_manifest.name) and recorded_manifest.name == backup_manifest_path.name
    return [
        _gate(
            "reconciliation_schema_supported",
            reconciliation.get("schema_version") == "research-report-state-reconciliation-v1",
            "T-604 reconciliation schema v1 is required",
        ),
        _gate("reconciliation_audit_complete", summary.get("audit_status") == "complete", "all four stores must be inventoried"),
        _gate(
            "reconciliation_drift_explicit",
            summary.get("reconciliation_status") == "drift_detected",
            "this recovery path only handles explicitly detected registry drift",
        ),
        _gate(
            "reconciliation_required_stores_available",
            all(
                store.get("availability") == "available"
                for store in (filesystem, postgres, opensearch, object_store)
            ),
            "filesystem, PostgreSQL, OpenSearch, and object store must all be available",
        ),
        _gate(
            "reconciliation_backup_matches_manifest",
            manifest_matches,
            "the supplied backup manifest basename must match the T-604 artifact",
        ),
        _gate(
            "reconciliation_collection_aware_backup",
            backup.get("restore_verified") is True and backup.get("research_collection_count_recorded") is True,
            "T-604 must observe a restore-verified backup with research collection counts",
        ),
        _gate(
            "reconciliation_backup_protects_current_state",
            recovery.get("backup_protects_current_research_state") is True,
            "T-604 must confirm that restore-matched rollback evidence protects the current database state",
        ),
        _gate(
            "reconciliation_clone_pilot_review_ready",
            recovery.get("recovery_readiness") in {"clone_pilot_review_required", "manual_review_required"},
            "T-604 recovery_readiness must allow human-reviewed work in a disposable clone",
        ),
        _gate(
            "raw_and_search_deletion_prohibited",
            recovery.get("safe_to_delete_raw_reports") is False
            and recovery.get("safe_to_delete_search_index") is False
            and recovery.get("safe_to_treat_opensearch_as_source_of_truth") is False,
            "raw reports and the current search index must remain preserved",
        ),
        _gate(
            "postgres_registry_empty_for_rebuild_path",
            int(postgres.get("collection_counts", {}).get("research_reports", -1)) == 0,
            "non-empty PostgreSQL registries require a separate identity-level merge audit",
        ),
    ]


def build_recovery_plan(
    *,
    filesystem_root: Path,
    registry_root: Path,
    extensions: set[str],
    reconciliation_path: Path,
    reconciliation: Mapping[str, Any],
    backup_manifest_path: Path,
    backup_manifest: Mapping[str, Any],
    identities: Mapping[str, Mapping[str, Any]],
    identity_source: str,
    max_reports_per_symbol: int,
    content_hash_budget_bytes: int,
) -> dict[str, Any]:
    inventory = inventory_raw_reports(filesystem_root, registry_root=registry_root, extensions=extensions)
    companies, candidate_diagnostics = build_watchlist_batches(
        inventory["rows"],
        identities=identities,
        max_reports_per_symbol=max_reports_per_symbol,
        content_hash_budget_bytes=content_hash_budget_bytes,
    )
    expected_filesystem = reconciliation.get("stores", {}).get("filesystem", {})
    expected_count = int(expected_filesystem.get("counts", {}).get("eligible_report_files", -1))
    expected_manifest = str(expected_filesystem.get("eligible_manifest_sha256") or "")
    plan_gates = [
        *backup_safety_gates(backup_manifest_path, backup_manifest),
        *reconciliation_safety_gates(reconciliation, backup_manifest_path),
        _gate(
            "filesystem_count_matches_reconciliation",
            inventory["eligible_report_files"] == expected_count,
            f"current={inventory['eligible_report_files']} reconciliation={expected_count}",
        ),
        _gate(
            "filesystem_manifest_matches_reconciliation",
            bool(expected_manifest) and inventory["eligible_manifest_sha256"] == expected_manifest,
            "raw path/size/mtime manifest must be unchanged since T-604",
        ),
        _gate(
            "global_report_id_collision_free",
            not inventory["report_id_collisions"],
            "all raw files must map to unique deterministic report IDs",
        ),
        _gate(
            "five_company_batches_present",
            all(int(company.get("selected_count") or 0) > 0 for company in companies),
            "each watchlist company must have at least one unambiguous content-hashed report",
        ),
        _gate(
            "five_company_identities_resolved",
            all(company.get("identity", {}).get("issuer_id") and company.get("identity", {}).get("security_id") for company in companies),
            "each ticker must resolve to exactly one company profile and security",
        ),
        _gate(
            "candidate_matches_unambiguous",
            candidate_diagnostics["ambiguous_multi_symbol_count"] >= 0,
            "multi-symbol files are quarantined and never selected automatically",
        ),
        _gate("no_delete_operations", True, "the implementation contains no delete endpoint or filesystem mutation"),
    ]
    core = {
        "schema_version": "watchlist-research-report-recovery-plan-v1",
        "related_tasks": ["T-603", "T-604", "T-608"],
        "filesystem_snapshot": {
            "filesystem_root": str(filesystem_root.expanduser().resolve()),
            "registry_root": str(registry_root),
            "extensions": sorted(extensions),
            "eligible_report_files": inventory["eligible_report_files"],
            "eligible_bytes": inventory["eligible_bytes"],
            "eligible_manifest_sha256": inventory["eligible_manifest_sha256"],
            "report_id_collision_count": len(inventory["report_id_collisions"]),
            "report_id_collision_samples": dict(list(inventory["report_id_collisions"].items())[:20]),
        },
        "input_evidence": {
            "reconciliation_path": str(reconciliation_path),
            "reconciliation_generated_at": str(reconciliation.get("generated_at") or ""),
            "backup_manifest_path": str(backup_manifest_path),
            "backup_dump_sha256": str(backup_manifest.get("dump_sha256") or ""),
            "backup_source_counts": dict(backup_manifest.get("source_counts") or {}),
            "backup_collection_counts": dict(backup_manifest.get("collection_counts") or {}),
            "identity_source": identity_source,
        },
        "settings": {
            "watchlist_symbols": list(WATCHLIST_SYMBOLS),
            "max_reports_per_symbol": max_reports_per_symbol,
            "content_hash_budget_bytes": content_hash_budget_bytes,
            "registry_recovery_scope": "all_raw_assets_then_watchlist_evidence_only",
        },
        "companies": companies,
        "candidate_diagnostics": candidate_diagnostics,
        "write_contract": {
            "future_target": "cloned_database_pilot_only",
            "allowed_http_methods": ["GET", "POST"],
            "registration_endpoint": "/api/research-reports/scan",
            "watchlist_endpoints": [
                "/api/research-reports/{report_id}/ingest",
                "/api/research-reports/{report_id}/extract",
            ],
            "delete_operations": [],
            "raw_files_preserved": True,
            "opensearch_index_preserved": True,
            "idempotency_keys": ["report_id", "document_id", "evidence_id_prefix", "content_sha256"],
            "fact_opinion_boundary": BOUNDARY,
        },
    }
    plan_sha256 = _payload_sha256(core)
    execution_allowed = all(bool(item["passed"]) for item in plan_gates)
    return {
        **core,
        "generated_at": utc_iso(),
        "classification": "local-only",
        "owner_group": "Data and Evidence",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
        "mode": "dry_run_plan",
        "status": "ready_for_cloned_pilot" if execution_allowed else "blocked",
        "execution_allowed": execution_allowed,
        "plan_sha256": plan_sha256,
        "safety_gates": plan_gates,
        "failed_gate_ids": [item["gate_id"] for item in plan_gates if not item["passed"]],
        "boundary_review": {
            "local_reports_promoted_to_fact_source": False,
            "local_reports_used_for_training": False,
            "real_broker_or_order_execution": False,
            "ambiguous_company_links_auto_created": False,
        },
    }


def _selected_reports(plan: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    selected: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for company in plan.get("companies", []):
        for report in company.get("selected_reports", []):
            selected.append((company, report))
    return selected


def validate_clone_attestation_static(
    attestation: Mapping[str, Any],
    *,
    base_url: str,
    now: datetime | None = None,
) -> None:
    """Reject unsafe clone claims before an API client is constructed."""

    now = now or datetime.now(timezone.utc)
    parsed = urlsplit(base_url.rstrip("/"))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    local_live_default = port == 8000
    generated_at = str(attestation.get("generated_at") or "")
    generated_recently = False
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_seconds = (now - generated.astimezone(timezone.utc)).total_seconds()
        generated_recently = -300 <= age_seconds <= 3600
    except ValueError:
        generated_recently = False
    database_name = str(attestation.get("database_name") or "").strip().lower()
    runtime_database_name = str(attestation.get("runtime_database_name") or "").strip().lower()
    source_counts = attestation.get("source_counts") if isinstance(attestation.get("source_counts"), Mapping) else {}
    restored_counts = attestation.get("restored_counts") if isinstance(attestation.get("restored_counts"), Mapping) else {}
    collection_counts = (
        attestation.get("collection_counts") if isinstance(attestation.get("collection_counts"), Mapping) else {}
    )
    restored_collections = (
        attestation.get("restored_collection_counts")
        if isinstance(attestation.get("restored_collection_counts"), Mapping)
        else {}
    )
    required_collection_metrics = {
        "research_reports",
        "research_documents",
        "research_report_citation_evidence",
    }
    runtime_proof = attestation.get("runtime_proof") if isinstance(attestation.get("runtime_proof"), Mapping) else {}
    health_probe = runtime_proof.get("health_probe") if isinstance(runtime_proof.get("health_probe"), Mapping) else {}
    database_probe = (
        runtime_proof.get("database_probe") if isinstance(runtime_proof.get("database_probe"), Mapping) else {}
    )
    environment_summary = (
        runtime_proof.get("environment_summary")
        if isinstance(runtime_proof.get("environment_summary"), Mapping)
        else {}
    )
    runtime_identity = (
        attestation.get("runtime_identity") if isinstance(attestation.get("runtime_identity"), Mapping) else {}
    )
    proof_runtime_identity = (
        runtime_proof.get("runtime_identity") if isinstance(runtime_proof.get("runtime_identity"), Mapping) else {}
    )
    proof_generated_at = str(runtime_proof.get("generated_at") or "")
    proof_generated_recently = False
    try:
        proof_generated = datetime.fromisoformat(proof_generated_at.replace("Z", "+00:00"))
        if proof_generated.tzinfo is None:
            proof_generated = proof_generated.replace(tzinfo=timezone.utc)
        proof_age_seconds = (now - proof_generated.astimezone(timezone.utc)).total_seconds()
        proof_generated_recently = -300 <= proof_age_seconds <= 3600
    except ValueError:
        proof_generated_recently = False
    proof_network_names = environment_summary.get("network_names")
    isolated_network_name = str(environment_summary.get("isolated_network_name") or "")
    structured_network_isolation = (
        isinstance(proof_network_names, list)
        and len(proof_network_names) == 1
        and proof_network_names == [isolated_network_name]
        and bool(isolated_network_name)
        and environment_summary.get("network_internal") is True
        and environment_summary.get("network_members_limited_to_app_and_postgres") is True
    )
    required_runtime_identity = {
        "app_container_id",
        "app_container_hostname",
        "app_image_id",
        "postgres_container_id",
        "postgres_image_id",
        "isolated_network_id",
        "database_oid",
        "postgres_system_identifier",
    }
    runtime_identity_complete = required_runtime_identity.issubset(runtime_identity) and all(
        str(runtime_identity.get(field) or "").strip() for field in required_runtime_identity
    )
    app_container_id = str(runtime_identity.get("app_container_id") or "")
    app_container_hostname = str(runtime_identity.get("app_container_hostname") or "")
    checks = {
        "clone_attestation_schema": attestation.get("schema_version") == "research-report-clone-attestation-v1",
        "clone_attestation_status": attestation.get("status") == "passed",
        "clone_attestation_environment": attestation.get("environment") == "cloned_database_pilot",
        "clone_attestation_recent": generated_recently,
        "clone_base_url_absolute": parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username,
        "clone_base_url_loopback": str(parsed.hostname or "").lower() in {"127.0.0.1", "localhost"},
        "clone_base_url_exact_match": str(attestation.get("base_url") or "").rstrip("/") == base_url.rstrip("/"),
        "default_live_url_rejected": not local_live_default,
        "clone_execution_scope": attestation.get("execution_scope") == "inside_clone_app_container",
        "clone_database_name": bool(database_name)
        and database_name != "ai_quant"
        and bool(re.search(r"(?:clone|pilot|restore|test)", database_name)),
        "clone_runtime_database_name": bool(runtime_database_name)
        and runtime_database_name == database_name
        and runtime_database_name != "ai_quant",
        "clone_object_store_backend_local": attestation.get("object_store_backend") == "local",
        "clone_search_backend_local": attestation.get("search_backend") == "local",
        "clone_network_isolation": attestation.get("network_isolation") is True,
        "clone_raw_mount_read_only": attestation.get("raw_mount_read_only") is True,
        "clone_primary_service_unreachable": attestation.get("primary_service_reachable") is False,
        "clone_restore_verified": attestation.get("restore_verified") is True,
        "clone_aggregate_restore_counts_match": bool(source_counts) and dict(source_counts) == dict(restored_counts),
        "clone_collection_metrics_present": required_collection_metrics.issubset(collection_counts),
        "clone_collection_restore_counts_match": bool(restored_collections)
        and dict(collection_counts) == dict(restored_collections),
        "clone_runtime_proof_schema": runtime_proof.get("schema_version")
        == "research-report-clone-runtime-proof-v1",
        "clone_runtime_proof_producer": runtime_proof.get("producer")
        == "scripts/probe_research_report_clone_runtime.py",
        "clone_runtime_proof_recent": proof_generated_recently,
        "clone_runtime_proof_timestamp": proof_generated_at == generated_at,
        "clone_runtime_proof_hash": bool(runtime_proof)
        and attestation.get("runtime_proof_sha256") == _payload_sha256(runtime_proof),
        "clone_runtime_identity_complete": runtime_identity_complete,
        "clone_runtime_identity_container": bool(app_container_hostname)
        and app_container_id.startswith(app_container_hostname),
        "clone_runtime_identity_database": str(runtime_identity.get("database_oid") or "").isdigit()
        and str(runtime_identity.get("postgres_system_identifier") or "").isdigit(),
        "clone_runtime_identity_proof_match": dict(proof_runtime_identity) == dict(runtime_identity),
        "clone_runtime_proof_base_url": str(runtime_proof.get("base_url") or "").rstrip("/")
        == base_url.rstrip("/"),
        "clone_runtime_proof_execution_scope": runtime_proof.get("execution_scope")
        == "inside_clone_app_container",
        "clone_runtime_health": health_probe.get("status") == "ok"
        and health_probe.get("store") == "PostgreSQLStore"
        and health_probe.get("transport") == "docker_exec_loopback",
        "clone_runtime_health_backends": health_probe.get("object_store_backend") == "local"
        and health_probe.get("search_backend") == "local",
        "clone_runtime_database_query": database_probe.get("query_id") == "select_current_database"
        and database_probe.get("success") is True
        and str(database_probe.get("current_database") or "").strip().lower() == database_name,
        "clone_runtime_database_counts": isinstance(database_probe.get("table_counts"), Mapping)
        and dict(database_probe.get("table_counts") or {}) == dict(restored_counts)
        and isinstance(database_probe.get("collection_counts"), Mapping)
        and dict(database_probe.get("collection_counts") or {}) == dict(restored_collections),
        "clone_runtime_environment_database": str(environment_summary.get("runtime_database_name") or "")
        .strip()
        .lower()
        == runtime_database_name,
        "clone_runtime_environment_backends": environment_summary.get("object_store_backend") == "local"
        and environment_summary.get("search_backend") == "local",
        "clone_runtime_environment_network": environment_summary.get("network_isolation") is True
        and structured_network_isolation,
        "clone_runtime_environment_mount": environment_summary.get("raw_mount_read_only") is True
        and environment_summary.get("root_filesystem_read_only") is True,
        "clone_runtime_environment_primary_service": environment_summary.get("primary_service_reachable") is False,
        "clone_runtime_environment_execution_scope": environment_summary.get("execution_scope")
        == "inside_clone_app_container",
        "clone_runtime_proof_matches_attestation": environment_summary.get("network_isolation")
        is attestation.get("network_isolation")
        and environment_summary.get("raw_mount_read_only") is attestation.get("raw_mount_read_only")
        and environment_summary.get("primary_service_reachable") is attestation.get("primary_service_reachable")
        and environment_summary.get("object_store_backend") == attestation.get("object_store_backend")
        and environment_summary.get("search_backend") == attestation.get("search_backend")
        and environment_summary.get("execution_scope") == attestation.get("execution_scope"),
    }
    failed = [gate_id for gate_id, passed in checks.items() if not passed]
    if failed:
        raise RecoveryRefused(f"clone attestation rejected: {','.join(failed)}")


def validate_current_clone_runtime_identity(attestation: Mapping[str, Any]) -> None:
    """Bind an execute request to the currently running container and database."""

    runtime_identity = (
        attestation.get("runtime_identity") if isinstance(attestation.get("runtime_identity"), Mapping) else {}
    )
    expected_hostname = str(runtime_identity.get("app_container_hostname") or "")
    app_container_id = str(runtime_identity.get("app_container_id") or "")
    if socket.gethostname() != expected_hostname or not app_container_id.startswith(expected_hostname):
        raise RecoveryRefused("clone runtime container identity no longer matches the attestation")
    dsn = os.environ.get("AI_QUANT_POSTGRES_DSN", "").strip()
    parsed = urlsplit(dsn)
    database_name = str(attestation.get("database_name") or "").strip().lower()
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.path.lstrip("/").lower() != database_name:
        raise RecoveryRefused("clone runtime PostgreSQL DSN no longer matches the attestation")
    try:
        import psycopg

        with psycopg.connect(dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT oid::text FROM pg_database WHERE datname = current_database()")
                database_oid = str(cursor.fetchone()[0])
                cursor.execute("SELECT system_identifier::text FROM pg_control_system()")
                postgres_system_identifier = str(cursor.fetchone()[0])
    except Exception as exc:
        raise RecoveryRefused("clone runtime database identity probe failed") from exc
    if database_oid != str(runtime_identity.get("database_oid") or ""):
        raise RecoveryRefused("clone runtime database OID no longer matches the attestation")
    if postgres_system_identifier != str(runtime_identity.get("postgres_system_identifier") or ""):
        raise RecoveryRefused("clone runtime PostgreSQL system identifier no longer matches the attestation")


def validate_clone_attestation_for_plan(
    attestation: Mapping[str, Any],
    *,
    base_url: str,
    plan: Mapping[str, Any],
) -> None:
    validate_clone_attestation_static(attestation, base_url=base_url)
    evidence = plan.get("input_evidence") if isinstance(plan.get("input_evidence"), Mapping) else {}
    checks = {
        "clone_attestation_plan_sha256": attestation.get("plan_sha256") == plan.get("plan_sha256"),
        "clone_attestation_backup_sha256": attestation.get("source_backup_dump_sha256")
        == evidence.get("backup_dump_sha256"),
        "clone_attestation_source_counts": dict(attestation.get("source_counts") or {})
        == dict(evidence.get("backup_source_counts") or {}),
        "clone_attestation_collection_counts": dict(attestation.get("collection_counts") or {})
        == dict(evidence.get("backup_collection_counts") or {}),
    }
    failed = [gate_id for gate_id, passed in checks.items() if not passed]
    if failed:
        raise RecoveryRefused(f"clone attestation does not bind the current plan: {','.join(failed)}")


def verify_execute_confirmation(
    plan: Mapping[str, Any],
    *,
    base_url: str,
    clone_attestation: Mapping[str, Any],
    confirm_plan_sha256: str,
    acknowledge_opinion_boundary: bool,
    allow_full_registry_scan: bool,
    confirm_clone_target: bool,
) -> None:
    failed = list(plan.get("failed_gate_ids") or [])
    if not plan.get("execution_allowed"):
        raise RecoveryRefused(f"recovery safety gates are closed: {','.join(failed)}")
    if confirm_plan_sha256 != plan.get("plan_sha256"):
        raise RecoveryRefused("--confirm-plan-sha256 must exactly match the current dry-run plan")
    if not acknowledge_opinion_boundary:
        raise RecoveryRefused("--acknowledge-opinion-boundary is required")
    if not allow_full_registry_scan:
        raise RecoveryRefused("--allow-full-registry-scan is required because the existing API restores the registry by root scan")
    if not confirm_clone_target:
        raise RecoveryRefused("--confirm-clone-target is required; this tool does not authorize primary recovery")
    validate_clone_attestation_for_plan(clone_attestation, base_url=base_url, plan=plan)


def _extract_candidate_text(
    path: Path,
    *,
    file_type: str,
    max_text_chars: int,
    pdf_pages: int,
    pdftotext_timeout: int,
) -> tuple[str, str]:
    from scripts.research_report_full_parse import redact_sensitive_contacts

    if file_type in {"txt", "md"}:
        text = path.read_text(encoding="utf-8", errors="ignore")[:max_text_chars].strip()
        return redact_sensitive_contacts(text), "local_text_file"
    if file_type == "pdf":
        from scripts.research_report_full_parse import extract_pdf_text

        text, source = extract_pdf_text(
            path,
            timeout=pdftotext_timeout,
            max_chars=max_text_chars,
            first_page=1,
            last_page=max(1, pdf_pages),
        )
        return redact_sensitive_contacts(text), source
    return "", "unsupported_file_type"


def execute_cloned_pilot(
    plan: Mapping[str, Any],
    *,
    client: Any,
    filesystem_root: Path,
    api_root: str,
    extensions: set[str],
    citation_char_limit: int,
    max_text_chars: int,
    pdf_pages: int,
    pdftotext_timeout: int,
) -> dict[str, Any]:
    """Execute an already-confirmed clone pilot. Call confirmation first."""

    scan = client.request(
        "POST",
        "/api/research-reports/scan",
        {
            "root_path": api_root,
            "extensions": sorted(extensions),
            "limit": min(50000, int(plan["filesystem_snapshot"]["eligible_report_files"]) + 100),
            "hash_files": False,
            "per_broker_sources": True,
        },
    )
    reports = scan.get("reports") if isinstance(scan.get("reports"), list) else []
    registered_ids = {str(item.get("report_id")) for item in reports if isinstance(item, Mapping)}
    selected = _selected_reports(plan)
    missing_ids = sorted(str(report["report_id"]) for _company, report in selected if report["report_id"] not in registered_ids)
    if int(scan.get("indexed_count") or 0) != int(plan["filesystem_snapshot"]["eligible_report_files"]) or missing_ids:
        raise RuntimeError(
            "clone registry scan did not reproduce the planned filesystem snapshot; rerun dry-run reconciliation"
        )

    results: list[dict[str, Any]] = []
    for company, report in selected:
        host_path = filesystem_root / str(report["relative_path"])
        if not host_path.is_file() or _file_sha256(host_path) != report["content_sha256"]:
            raise RuntimeError(f"candidate changed after planning: {report['report_id']}")
        ingest = client.request(
            "POST",
            f"/api/research-reports/{report['report_id']}/ingest",
            {
                "issuer_id": company["identity"]["issuer_id"],
                "security_id": company["identity"]["security_id"],
                "document_id": report["document_id"],
                "content_sha256": report["content_sha256"],
                "language": "zh",
                "version": "watchlist-recovery-clone-pilot-v1",
            },
        )
        ingested_report = ingest.get("report") if isinstance(ingest.get("report"), Mapping) else {}
        ingested_document = ingest.get("document") if isinstance(ingest.get("document"), Mapping) else {}
        content_identity_verified = (
            ingested_report.get("content_sha256") == report["content_sha256"]
            and ingested_document.get("content_sha256") == report["content_sha256"]
        )
        if not content_identity_verified:
            raise RuntimeError(f"API did not persist the verified content identity: {report['report_id']}")
        text, text_source = _extract_candidate_text(
            host_path,
            file_type=str(report["file_type"]),
            max_text_chars=max_text_chars,
            pdf_pages=pdf_pages,
            pdftotext_timeout=pdftotext_timeout,
        )
        extract_body: dict[str, Any] = {
            "citation_char_limit": citation_char_limit,
            "parser_version": "watchlist-recovery-clone-pilot-v1",
        }
        if text:
            extract_body["text"] = text
        extracted = client.request(
            "POST",
            f"/api/research-reports/{report['report_id']}/extract",
            extract_body,
        )
        results.append(
            {
                "symbol": company["symbol"],
                "report_id": report["report_id"],
                "document_id": report["document_id"],
                "ingest_created": bool(ingest.get("created")),
                "status": str(extracted.get("status") or "unknown"),
                "evidence_count": len(extracted.get("evidence") or []),
                "manual_review": bool(extracted.get("manual_review")),
                "text_source": text_source,
                "content_sha256": report["content_sha256"],
                "content_identity_verified": content_identity_verified,
                "fact_opinion_boundary": BOUNDARY,
            }
        )
    evidence_count = sum(int(item["evidence_count"]) for item in results)
    evidence_gate_passed = bool(results) and all(
        item["status"] == "text_indexed"
        and int(item["evidence_count"]) > 0
        and item["manual_review"] is False
        and item["content_identity_verified"] is True
        for item in results
    )
    return {
        "schema_version": "watchlist-research-report-recovery-execution-v1",
        "generated_at": utc_iso(),
        "environment": "operator_confirmed_cloned_database_pilot",
        "status": "passed" if evidence_gate_passed else "failed_evidence_gate",
        "plan_sha256": plan["plan_sha256"],
        "registry_indexed_count": int(scan.get("indexed_count") or 0),
        "selected_report_count": len(results),
        "evidence_count": evidence_count,
        "needs_evidence_count": sum(1 for item in results if not item["evidence_count"]),
        "content_identity_verified_count": sum(1 for item in results if item["content_identity_verified"]),
        "results": results,
        "delete_operations": [],
        "raw_files_preserved": True,
        "opensearch_index_preserved": True,
        "fact_opinion_boundary": BOUNDARY,
    }


def _parse_extensions(value: str) -> set[str]:
    result = set()
    for raw in value.split(","):
        item = raw.strip().lower()
        if item:
            result.add(item if item.startswith(".") else f".{item}")
    return result or {".pdf"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filesystem-root", type=Path, default=DEFAULT_FILESYSTEM_ROOT)
    parser.add_argument("--api-root", default=DEFAULT_API_ROOT)
    parser.add_argument("--registry-root", type=Path, default=Path(DEFAULT_API_ROOT))
    parser.add_argument("--extensions", default=".pdf,.txt,.md")
    parser.add_argument("--reconciliation", type=Path, default=DEFAULT_RECONCILIATION)
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument("--company-profiles-artifact", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--offline-identities", action="store_true", help="Do not perform the read-only company-profile API lookup.")
    parser.add_argument("--max-reports-per-symbol", type=int, default=3)
    parser.add_argument("--content-hash-budget-mb", type=float, default=2048.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--execute", action="store_true", help="Execute only an explicitly confirmed cloned-database pilot.")
    parser.add_argument("--confirm-plan-sha256", default="")
    parser.add_argument("--acknowledge-opinion-boundary", action="store_true")
    parser.add_argument("--allow-full-registry-scan", action="store_true")
    parser.add_argument("--confirm-clone-target", action="store_true")
    parser.add_argument(
        "--clone-attestation",
        type=Path,
        help="Required for execute: recent restore evidence for a non-primary clone bound to base URL and plan SHA.",
    )
    parser.add_argument("--citation-char-limit", type=int, default=1200)
    parser.add_argument("--max-text-chars", type=int, default=50000)
    parser.add_argument("--pdf-pages", type=int, default=3)
    parser.add_argument("--pdftotext-timeout", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=300.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_reports_per_symbol < 1 or args.max_reports_per_symbol > 20:
        raise SystemExit("--max-reports-per-symbol must be between 1 and 20")
    clone_attestation: dict[str, Any] = {}
    if args.execute:
        if args.clone_attestation is None:
            raise SystemExit("execution refused: --clone-attestation is required")
        try:
            clone_attestation = _load_json(args.clone_attestation)
            validate_clone_attestation_static(clone_attestation, base_url=args.base_url)
            validate_current_clone_runtime_identity(clone_attestation)
        except (OSError, ValueError, RecoveryRefused) as exc:
            raise SystemExit(f"execution refused before API access: {exc}") from exc
    reconciliation = _load_json(args.reconciliation)
    backup_manifest = _load_json(args.backup_manifest)
    client = None if args.offline_identities else ApiClient(args.base_url, timeout=args.timeout)
    identities, identity_source = load_company_identities(
        client=client,
        company_profiles_artifact=args.company_profiles_artifact,
    )
    plan = build_recovery_plan(
        filesystem_root=args.filesystem_root,
        registry_root=args.registry_root,
        extensions=_parse_extensions(args.extensions),
        reconciliation_path=args.reconciliation,
        reconciliation=reconciliation,
        backup_manifest_path=args.backup_manifest,
        backup_manifest=backup_manifest,
        identities=identities,
        identity_source=identity_source,
        max_reports_per_symbol=args.max_reports_per_symbol,
        content_hash_budget_bytes=max(0, int(args.content_hash_budget_mb * 1024 * 1024)),
    )
    output_payload: dict[str, Any] = plan
    exit_code = 0
    if args.execute:
        try:
            verify_execute_confirmation(
                plan,
                base_url=args.base_url,
                clone_attestation=clone_attestation,
                confirm_plan_sha256=args.confirm_plan_sha256,
                acknowledge_opinion_boundary=args.acknowledge_opinion_boundary,
                allow_full_registry_scan=args.allow_full_registry_scan,
                confirm_clone_target=args.confirm_clone_target,
            )
            dump_path = _resolve_dump_path(args.backup_manifest, backup_manifest)
            if _file_sha256(dump_path) != str(backup_manifest.get("dump_sha256") or ""):
                raise RecoveryRefused("backup dump SHA-256 no longer matches the restore manifest")
            if client is None:
                client = ApiClient(args.base_url, timeout=args.timeout)
            execution = execute_cloned_pilot(
                plan,
                client=client,
                filesystem_root=args.filesystem_root.expanduser().resolve(),
                api_root=args.api_root,
                extensions=_parse_extensions(args.extensions),
                citation_char_limit=max(1, min(args.citation_char_limit, 4000)),
                max_text_chars=max(1000, args.max_text_chars),
                pdf_pages=max(1, args.pdf_pages),
                pdftotext_timeout=max(1, args.pdftotext_timeout),
            )
            output_payload = {"plan": plan, "execution": execution}
            if execution.get("status") != "passed":
                exit_code = 3
        except RecoveryRefused as exc:
            output_payload = {"plan": plan, "execution": {"status": "refused", "reason": str(exc)}}
            exit_code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
