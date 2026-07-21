#!/usr/bin/env python3
"""Execute one approved T-613 batch inside an independently attested clone.

The command refuses primary/default URLs, non-clone runtimes, stale or
unbound approvals, changed raw files, and plans that permit updates/deletes.
It never exposes raw paths or report names in its output artifact.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "app" / "models.py").exists() and Path("/app/app/models.py").exists():
    ROOT = Path("/app")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research_reports import content_sha256, report_id_for_path
from scripts.build_research_report_registry_decision import payload_sha256
from scripts.prepare_research_report_clone_batch import inspect_approval
from scripts.recover_watchlist_research_reports import (
    ApiClient,
    BOUNDARY,
    RecoveryRefused,
    _extract_candidate_text,
    validate_clone_attestation_for_plan,
    validate_current_clone_runtime_identity,
)
from scripts.research_report_full_parse import ensure_fallback_issuer, redact_sensitive_contacts


EXPECTED_BATCH_ID_PATTERN = re.compile(r"^t613-batch-00(?:0[1-9]|[1-3][0-9]|4[0-4])$")
FALLBACK_ISSUER_ID = "issuer_local_research_reference"
SAFE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CloneBatchRefused(RuntimeError):
    """Raised before mutation when the approved clone batch is unsafe."""


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloneBatchRefused(f"{label} must be a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise CloneBatchRefused(f"{label} must be a JSON object")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_dump_path(manifest_path: Path, manifest: Mapping[str, Any]) -> Path:
    dump_path = Path(str(manifest.get("dump_path") or ""))
    if not dump_path.is_file() and dump_path.name:
        sibling = manifest_path.parent / dump_path.name
        if sibling.is_file():
            dump_path = sibling
    return dump_path


def validate_execution_bundle(
    *,
    preflight: Mapping[str, Any],
    approval_path: Path,
    attestation_path: Path,
    backup_manifest_path: Path,
    base_url: str,
    confirm_plan_sha256: str,
    confirm_batch_sha256: str,
    acknowledge_opinion_boundary: bool,
    confirm_targeted_registration: bool,
    confirm_clone_target: bool,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    if preflight.get("schema_version") != "research-report-clone-batch-preflight-v1":
        raise CloneBatchRefused("preflight schema is unsupported")
    if preflight.get("status") != "ready_for_separate_clone_executor" or preflight.get("execution_ready") is not True:
        raise CloneBatchRefused("preflight is not ready for the separate clone executor")
    if preflight.get("execution_performed") is not False or preflight.get("automatic_recovery_authorized") is not False:
        raise CloneBatchRefused("preflight execution flags are unsafe")
    if preflight.get("failed_gate_ids"):
        raise CloneBatchRefused("preflight still contains failed gates")

    gates = {
        str(item.get("gate_id") or ""): item.get("passed") is True
        for item in preflight.get("gates", [])
        if isinstance(item, Mapping)
    }
    required_gates = {
        "identity_manifest_verified",
        "decision_batch_verified",
        "raw_batch_content_verified",
        "fresh_primary_backup_verified",
        "exact_human_approval_verified",
        "independent_clone_attestation_verified",
    }
    if not required_gates.issubset(gates) or not all(gates[item] for item in required_gates):
        raise CloneBatchRefused("preflight required gates are incomplete")

    plan = dict(preflight.get("plan") or {})
    if plan.get("schema_version") != "research-report-clone-batch-plan-v1":
        raise CloneBatchRefused("batch plan schema is unsupported")
    plan_sha256 = str(preflight.get("plan_sha256") or "")
    if not SAFE_SHA256.fullmatch(plan_sha256) or payload_sha256(plan) != plan_sha256:
        raise CloneBatchRefused("batch plan SHA-256 is invalid")
    if confirm_plan_sha256 != plan_sha256:
        raise CloneBatchRefused("--confirm-plan-sha256 must match the ready preflight")
    batch_id = str(plan.get("batch_id") or "")
    batch_sha256 = str(plan.get("batch_sha256") or "")
    if not EXPECTED_BATCH_ID_PATTERN.fullmatch(batch_id) or confirm_batch_sha256 != batch_sha256:
        raise CloneBatchRefused("batch ID must be one of the deterministic T-613 batches and SHA must match")

    write_contract = dict(plan.get("write_contract") or {})
    required_contract = {
        "target": "independently_attested_clone_only",
        "primary_writes_allowed": False,
        "insert_only": True,
        "updates_allowed": False,
        "deletes_allowed": False,
        "raw_files_preserved": True,
        "opensearch_preserved": True,
        "local_opinion_reference_only": True,
        "training_allowed": False,
        "broker_connected": False,
        "live_execution_allowed": False,
    }
    if any(write_contract.get(key) != value for key, value in required_contract.items()):
        raise CloneBatchRefused("batch write contract changed")
    if not acknowledge_opinion_boundary or not confirm_targeted_registration or not confirm_clone_target:
        raise CloneBatchRefused("all clone-only execution acknowledgements are required")

    approval = inspect_approval(
        approval_path,
        manifest_sha256=str(plan.get("manifest_sha256") or ""),
        batch_id=batch_id,
        batch_sha256=batch_sha256,
        now=now,
    )
    expected_approval_sha = str((preflight.get("approval_evidence") or {}).get("approval_file_sha256") or "")
    if approval.get("gates_passed") is not True or approval.get("approval_file_sha256") != expected_approval_sha:
        raise CloneBatchRefused("approval is invalid, stale, or not bound to the ready preflight")

    attestation = _load_json(attestation_path, label="clone attestation")
    expected_attestation_sha = str(
        (preflight.get("clone_attestation_evidence") or {}).get("attestation_file_sha256") or ""
    )
    if _file_sha256(attestation_path) != expected_attestation_sha:
        raise CloneBatchRefused("clone attestation file does not match the ready preflight")
    validation_plan = {
        "plan_sha256": plan_sha256,
        "input_evidence": dict(preflight.get("input_evidence") or {}),
    }
    try:
        validate_clone_attestation_for_plan(attestation, base_url=base_url, plan=validation_plan)
    except RecoveryRefused as exc:
        raise CloneBatchRefused(str(exc)) from exc

    backup_manifest = _load_json(backup_manifest_path, label="backup manifest")
    dump_path = _resolve_dump_path(backup_manifest_path, backup_manifest)
    expected_dump_sha = str((preflight.get("input_evidence") or {}).get("backup_dump_sha256") or "")
    if not dump_path.is_file() or _file_sha256(dump_path) != expected_dump_sha:
        raise CloneBatchRefused("backup dump no longer matches the ready preflight")
    if str(backup_manifest.get("dump_sha256") or "") != expected_dump_sha:
        raise CloneBatchRefused("backup manifest does not bind the ready preflight")
    return plan, attestation


def resolve_batch_paths(
    filesystem_root: Path,
    *,
    registry_root: Path,
    entries: list[Mapping[str, Any]],
) -> dict[str, Path]:
    root = filesystem_root.expanduser().resolve()
    if not root.is_dir():
        raise CloneBatchRefused("raw research-report root is unavailable")
    expected = {str(item.get("relative_path_sha256") or ""): item for item in entries}
    if not expected or len(expected) != len(entries):
        raise CloneBatchRefused("batch locators must be non-empty and unique")
    resolved: dict[str, Path] = {}
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories.sort()
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            locator = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()
            entry = expected.get(locator)
            if entry is None:
                continue
            report_id = str(entry.get("report_id") or "")
            if report_id_for_path(registry_root / relative) != report_id:
                raise CloneBatchRefused("raw locator resolved to the wrong report ID")
            if path.stat().st_size != int(entry.get("size_bytes") or -1):
                raise CloneBatchRefused(f"raw size changed for {report_id}")
            if content_sha256(path) != str(entry.get("content_sha256") or ""):
                raise CloneBatchRefused(f"raw content changed for {report_id}")
            resolved[report_id] = path
    expected_ids = {str(item.get("report_id") or "") for item in entries}
    if set(resolved) != expected_ids:
        raise CloneBatchRefused("one or more approved raw reports are unavailable")
    return resolved


def _text_source_category(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith("pdftotext:"):
        return "pdftotext"
    if lowered == "local_text_file":
        return "local_text_file"
    if "timeout" in lowered:
        return "text_extraction_timeout"
    if "empty" in lowered:
        return "no_extractable_text"
    if "unavailable" in lowered:
        return "text_extractor_unavailable"
    return "no_extractable_text" if not value else "text_extraction_failed"


def compare_with_prior_run(current: Mapping[str, Any], prior: Mapping[str, Any]) -> dict[str, Any]:
    current_rows = {str(item.get("report_id") or ""): item for item in current.get("results", [])}
    prior_rows = {str(item.get("report_id") or ""): item for item in prior.get("results", [])}
    identity_fields = (
        "document_id",
        "content_sha256",
        "status",
        "evidence_count",
        "manual_review",
        "text_source",
        "content_identity_verified",
    )
    matching_ids = set(current_rows) == set(prior_rows) and bool(current_rows)
    mismatches: list[str] = []
    for report_id in sorted(set(current_rows) | set(prior_rows)):
        current_row = current_rows.get(report_id, {})
        prior_row = prior_rows.get(report_id, {})
        if any(current_row.get(field) != prior_row.get(field) for field in identity_fields):
            mismatches.append(report_id)
    all_existing = bool(current_rows) and all(item.get("ingest_created") is False for item in current_rows.values())
    return {
        "prior_run_sha256": str(prior.get("artifact_sha256") or ""),
        "same_report_ids": matching_ids,
        "same_identity_and_outcomes": not mismatches and matching_ids,
        "mismatch_count": len(mismatches),
        "mismatch_report_ids": mismatches[:20],
        "all_ingest_created_false": all_existing,
        "passed": matching_ids and not mismatches and all_existing,
    }


def execute_batch(
    plan: Mapping[str, Any],
    *,
    client: ApiClient,
    filesystem_root: Path,
    registry_root: Path,
    api_root: str,
    citation_char_limit: int,
    max_text_chars: int,
    pdf_pages: int,
    pdftotext_timeout: int,
    prior_run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    entries = [dict(item) for item in plan.get("batch_entries", []) if isinstance(item, Mapping)]
    if not entries or len(entries) > 250:
        raise CloneBatchRefused("batch must contain between 1 and 250 entries")
    report_ids = [str(item.get("report_id") or "") for item in entries]
    if len(report_ids) != len(set(report_ids)) or any(not item for item in report_ids):
        raise CloneBatchRefused("batch report IDs must be non-empty and unique")
    resolved = resolve_batch_paths(
        filesystem_root,
        registry_root=registry_root,
        entries=entries,
    )

    scan: dict[str, Any] = {}
    registry_scan_seconds = 0.0
    prior_state: dict[str, Mapping[str, Any]] = {}
    if prior_run is None:
        scan_started = time.monotonic()
        relative_paths = [path.relative_to(filesystem_root.expanduser().resolve()).as_posix() for path in resolved.values()]
        scan = client.request(
            "POST",
            "/api/research-reports/scan",
            {
                "root_path": api_root,
                "relative_paths": relative_paths,
                "extensions": [".pdf"],
                "limit": len(relative_paths),
                "hash_files": False,
                "per_broker_sources": True,
            },
        )
        reports = scan.get("reports") if isinstance(scan.get("reports"), list) else []
        registered_ids = {str(item.get("report_id") or "") for item in reports if isinstance(item, Mapping)}
        missing = sorted(set(report_ids) - registered_ids)
        if missing:
            raise CloneBatchRefused("targeted clone registry scan did not contain every approved report ID")
        ensure_fallback_issuer(client, FALLBACK_ISSUER_ID)
        registry_scan_seconds = round(time.monotonic() - scan_started, 3)
    else:
        state = client.request(
            "GET",
            "/api/research-reports/batch-state?report_ids=" + ",".join(report_ids),
        )
        if state.get("missing_report_ids"):
            raise CloneBatchRefused("clone batch-state is missing an approved report ID")
        rows = state.get("reports") if isinstance(state.get("reports"), list) else []
        prior_state = {str(item.get("report_id") or ""): item for item in rows if isinstance(item, Mapping)}
        if set(prior_state) != set(report_ids):
            raise CloneBatchRefused("clone batch-state did not return every approved report ID")

    entries_by_id = {str(item["report_id"]): item for item in entries}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, report_id in enumerate(report_ids, start=1):
        entry = entries_by_id[report_id]
        path = resolved[report_id]
        try:
            expected_content = str(entry.get("content_sha256") or "")
            text, text_source = _extract_candidate_text(
                path,
                file_type=str(entry.get("file_type") or ""),
                max_text_chars=max_text_chars,
                pdf_pages=pdf_pages,
                pdftotext_timeout=pdftotext_timeout,
            )
            if prior_run is None:
                ingest = client.request(
                    "POST",
                    f"/api/research-reports/{report_id}/ingest",
                    {
                        "issuer_id": FALLBACK_ISSUER_ID,
                        "security_id": "",
                        "document_id": str(entry.get("document_id") or ""),
                        "content_sha256": expected_content,
                        "language": "zh",
                        "version": "t614-clone-batch-pdftotext-v1",
                    },
                )
                report = ingest.get("report") if isinstance(ingest.get("report"), Mapping) else {}
                document = ingest.get("document") if isinstance(ingest.get("document"), Mapping) else {}
                content_identity_verified = (
                    report.get("content_sha256") == expected_content
                    and document.get("content_sha256") == expected_content
                    and document.get("document_id") == entry.get("document_id")
                )
                if not content_identity_verified:
                    raise RuntimeError("persisted content identity mismatch")
                extract_payload: dict[str, Any] = {
                    "citation_char_limit": citation_char_limit,
                    "parser_version": "t614-clone-batch-pdftotext-v1",
                }
                if text:
                    extract_payload["text"] = redact_sensitive_contacts(text)
                extracted = client.request(
                    "POST",
                    f"/api/research-reports/{report_id}/extract",
                    extract_payload,
                )
                persisted = {
                    "document_id": document.get("document_id"),
                    "content_sha256": document.get("content_sha256"),
                    "status": extracted.get("status") or "unknown",
                    "evidence_count": len(extracted.get("evidence") or []),
                    "manual_review": bool(extracted.get("manual_review")),
                }
                content_identity_verified = True
                ingest_created = bool(ingest.get("created"))
            else:
                persisted = dict(prior_state[report_id])
                content_identity_verified = (
                    persisted.get("report_id") == report_id
                    and persisted.get("document_id") == entry.get("document_id")
                    and persisted.get("content_sha256") == expected_content
                    and persisted.get("document_content_sha256") == expected_content
                )
                if not content_identity_verified:
                    raise RuntimeError("read-only persisted content identity mismatch")
                ingest_created = False
            results.append(
                {
                    "report_id": report_id,
                    "document_id": str(entry.get("document_id") or ""),
                    "content_sha256": expected_content,
                    "ingest_created": ingest_created,
                    "status": str(persisted.get("status") or "unknown"),
                    "evidence_count": int(persisted.get("evidence_count") or 0),
                    "manual_review": bool(persisted.get("manual_review")),
                    "text_source": _text_source_category(text_source),
                    "content_identity_verified": True,
                }
            )
        except Exception as exc:  # noqa: BLE001 - per-report failures are classified in the evidence artifact
            errors.append(
                {
                    "report_id": report_id,
                    "error_type": type(exc).__name__,
                    "error_code": "report_processing_failed",
                }
            )
        print(
            json.dumps(
                {
                    "processed": index,
                    "total": len(report_ids),
                    "passed": len(results),
                    "failed": len(errors),
                }
            ),
            flush=True,
        )

    execution_seconds = round(time.monotonic() - started, 3)
    payload: dict[str, Any] = {
        "schema_version": "research-report-clone-batch-execution-v1",
        "related_task": str(plan.get("related_task") or "T-615"),
        "generated_at": utc_iso(),
        "environment": "operator_approved_independently_attested_clone",
        "plan_sha256": str(payload_sha256(plan)),
        "manifest_sha256": str(plan.get("manifest_sha256") or ""),
        "batch_id": str(plan.get("batch_id") or ""),
        "batch_sha256": str(plan.get("batch_sha256") or ""),
        "status": "passed" if not errors and len(results) == len(entries) else "completed_with_failures",
        "registry_indexed_count": int(scan.get("indexed_count") or 0),
        "registry_scan_seconds": registry_scan_seconds,
        "registry_scan_mode": "targeted_relative_paths" if prior_run is None else "read_only_batch_state",
        "selected_report_count": len(entries),
        "processed_count": len(results),
        "failed_count": len(errors),
        "text_indexed_count": sum(item["status"] == "text_indexed" for item in results),
        "manual_review_count": sum(bool(item["manual_review"]) for item in results),
        "evidence_count": sum(int(item["evidence_count"]) for item in results),
        "content_identity_verified_count": sum(bool(item["content_identity_verified"]) for item in results),
        "ingest_created_count": sum(bool(item["ingest_created"]) for item in results),
        "execution_seconds": execution_seconds,
        "results": results,
        "errors": errors,
        "delete_operations": [],
        "raw_files_preserved": True,
        "opensearch_index_preserved": True,
        "primary_writes_allowed": False,
        "fact_opinion_boundary": BOUNDARY,
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
    }
    if prior_run is not None:
        payload["idempotency_comparison"] = compare_with_prior_run(payload, prior_run)
        if payload["status"] == "passed" and payload["idempotency_comparison"]["passed"] is not True:
            payload["status"] = "failed_idempotency_gate"
    artifact_core = dict(payload)
    payload["artifact_sha256"] = payload_sha256(artifact_core)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--clone-attestation", type=Path, required=True)
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument("--filesystem-root", type=Path, default=Path("/data/local/research_reports"))
    parser.add_argument("--registry-root", type=Path, default=Path("/data/local/research_reports"))
    parser.add_argument("--api-root", default="/data/local/research_reports")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-plan-sha256", required=True)
    parser.add_argument("--confirm-batch-sha256", required=True)
    parser.add_argument("--acknowledge-opinion-boundary", action="store_true")
    parser.add_argument("--confirm-targeted-registration", action="store_true")
    parser.add_argument("--confirm-clone-target", action="store_true")
    parser.add_argument("--prior-run", type=Path)
    parser.add_argument("--citation-char-limit", type=int, default=1200)
    parser.add_argument("--max-text-chars", type=int, default=50000)
    parser.add_argument("--pdf-pages", type=int, default=3)
    parser.add_argument("--pdftotext-timeout", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.execute:
        raise SystemExit("execution refused: --execute is required")
    preflight = _load_json(args.preflight, label="ready preflight")
    try:
        plan, attestation = validate_execution_bundle(
            preflight=preflight,
            approval_path=args.approval,
            attestation_path=args.clone_attestation,
            backup_manifest_path=args.backup_manifest,
            base_url=args.base_url,
            confirm_plan_sha256=args.confirm_plan_sha256,
            confirm_batch_sha256=args.confirm_batch_sha256,
            acknowledge_opinion_boundary=args.acknowledge_opinion_boundary,
            confirm_targeted_registration=args.confirm_targeted_registration,
            confirm_clone_target=args.confirm_clone_target,
        )
        validate_current_clone_runtime_identity(attestation)
    except (CloneBatchRefused, RecoveryRefused, OSError, ValueError) as exc:
        raise SystemExit(f"execution refused before API access: {exc}") from exc
    prior = _load_json(args.prior_run, label="prior run") if args.prior_run else None
    execution = execute_batch(
        plan,
        client=ApiClient(args.base_url, timeout=max(1.0, args.timeout)),
        filesystem_root=args.filesystem_root,
        registry_root=args.registry_root,
        api_root=args.api_root,
        citation_char_limit=max(1, min(args.citation_char_limit, 4000)),
        max_text_chars=max(1000, args.max_text_chars),
        pdf_pages=max(1, args.pdf_pages),
        pdftotext_timeout=max(1, args.pdftotext_timeout),
        prior_run=prior,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(execution, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": execution["status"],
                "processed_count": execution["processed_count"],
                "failed_count": execution["failed_count"],
                "text_indexed_count": execution["text_indexed_count"],
                "manual_review_count": execution["manual_review_count"],
                "evidence_count": execution["evidence_count"],
                "ingest_created_count": execution["ingest_created_count"],
                "execution_seconds": execution["execution_seconds"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if execution["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
