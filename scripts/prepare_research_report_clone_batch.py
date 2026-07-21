#!/usr/bin/env python3
"""Prepare and gate one T-613 research-report batch for a clone-only pilot.

This command has no execute mode. It validates the identity manifest, decision
pack, selected raw file content, a fresh primary backup, optional human
approval, and optional clone attestation. It writes only local evidence JSON.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research_reports import content_sha256, report_id_for_path
from scripts.build_research_report_registry_decision import RIGHTS_POLICY, payload_sha256
from scripts.recover_watchlist_research_reports import RecoveryRefused, validate_clone_attestation_for_plan


DEFAULT_MANIFEST = Path("artifacts/t613-full-registry/identity-manifest.json")
DEFAULT_DECISION = Path("artifacts/t613-full-registry/recovery-decision.json")
DEFAULT_OUTPUT = Path("artifacts/t614-clone-batch/batch-0001-preflight.json")
DEFAULT_APPROVAL_OUTPUT = Path("artifacts/t614-clone-batch/batch-0001-approval-request.json")
DEFAULT_FILESYSTEM_ROOT = Path("/home/xionglei/文档/6大投行研报汇总")
DEFAULT_REGISTRY_ROOT = Path("/data/local/research_reports")
EXPECTED_MANIFEST_SHA256 = "e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e"
EXPECTED_BATCH_ID = "t613-batch-0001"
EXPECTED_BATCH_SHA256 = "2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_MAX_AGE = timedelta(hours=24)
ATTESTATION_MAX_AGE = timedelta(minutes=30)


class BatchPreparationRefused(RuntimeError):
    """Raised when immutable T-613 evidence is invalid or tampered."""


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchPreparationRefused(f"{label} must be a readable JSON object") from exc
    if not isinstance(payload, dict):
        raise BatchPreparationRefused(f"{label} must be a JSON object")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_time(value: Any, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise BatchPreparationRefused(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _gate(gate_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "passed": bool(passed), "detail": detail}


def verify_identity_manifest(
    manifest: Mapping[str, Any],
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    if manifest.get("schema_version") != "research-report-full-identity-manifest-v1":
        raise BatchPreparationRefused("identity manifest schema is unsupported")
    entries = [dict(item) for item in manifest.get("entries", []) if isinstance(item, Mapping)]
    hash_failures = [dict(item) for item in manifest.get("hash_failures", []) if isinstance(item, Mapping)]
    stable_core = {
        "identity_policy": dict(manifest.get("identity_policy") or {}),
        "rights_policy": dict(manifest.get("rights_policy") or {}),
        "entries": entries,
        "hash_failures": hash_failures,
    }
    actual_manifest_sha256 = payload_sha256(stable_core)
    recorded = str(manifest.get("integrity", {}).get("manifest_sha256") or "")
    entries_sha256 = payload_sha256(entries)
    recorded_entries = str(manifest.get("integrity", {}).get("entries_sha256") or "")
    if actual_manifest_sha256 != recorded or recorded != expected_manifest_sha256:
        raise BatchPreparationRefused("identity manifest SHA-256 does not match the approved T-613 value")
    if entries_sha256 != recorded_entries:
        raise BatchPreparationRefused("identity manifest entries SHA-256 is invalid")
    if hash_failures or manifest.get("report_id_collisions"):
        raise BatchPreparationRefused("identity manifest contains hash failures or report-ID collisions")
    if dict(manifest.get("rights_policy") or {}) != RIGHTS_POLICY:
        raise BatchPreparationRefused("identity manifest rights policy changed")
    entry_ids = [str(item.get("report_id") or "") for item in entries]
    if not entries or len(entry_ids) != len(set(entry_ids)) or any(not item for item in entry_ids):
        raise BatchPreparationRefused("identity manifest report IDs must be non-empty and unique")
    return {
        "manifest_sha256": recorded,
        "entries_sha256": entries_sha256,
        "entry_count": len(entries),
        "entries_by_id": {str(item["report_id"]): item for item in entries},
    }


def verify_decision_batch(
    decision: Mapping[str, Any],
    *,
    manifest_sha256: str,
    batch_id: str,
    expected_batch_sha256: str,
) -> dict[str, Any]:
    if decision.get("schema_version") != "research-report-registry-recovery-decision-v1":
        raise BatchPreparationRefused("recovery decision schema is unsupported")
    if decision.get("execution_authorized") is not False or decision.get("automatic_recovery_authorized") is not False:
        raise BatchPreparationRefused("T-613 decision must keep execution and automatic recovery disabled")
    if str(decision.get("input_evidence", {}).get("identity_manifest_sha256") or "") != manifest_sha256:
        raise BatchPreparationRefused("recovery decision does not bind the identity manifest")
    if int(decision.get("identity_comparison", {}).get("postgres_content_conflict_count") or 0) != 0:
        raise BatchPreparationRefused("recovery decision contains PostgreSQL content conflicts")
    batches = decision.get("recovery_plan", {}).get("batches", [])
    selected = next(
        (dict(item) for item in batches if isinstance(item, Mapping) and item.get("batch_id") == batch_id),
        None,
    )
    if selected is None:
        raise BatchPreparationRefused("requested batch is absent from the T-613 decision")
    report_ids = [str(item) for item in selected.get("report_ids", [])]
    batch_core = {"identity_manifest_sha256": manifest_sha256, "report_ids": report_ids}
    actual_batch_sha256 = payload_sha256(batch_core)
    if actual_batch_sha256 != str(selected.get("batch_sha256") or "") or actual_batch_sha256 != expected_batch_sha256:
        raise BatchPreparationRefused("batch SHA-256 does not match the approved T-613 value")
    if len(report_ids) != int(selected.get("report_count") or -1) or len(report_ids) != len(set(report_ids)):
        raise BatchPreparationRefused("batch report IDs are not complete and unique")
    if len(report_ids) > int(decision.get("recovery_plan", {}).get("batch_size") or 0):
        raise BatchPreparationRefused("batch exceeds the T-613 batch-size limit")
    return {
        "batch_id": batch_id,
        "batch_sha256": actual_batch_sha256,
        "report_ids": report_ids,
        "report_count": len(report_ids),
        "decision_generated_at": str(decision.get("generated_at") or ""),
    }


def bind_batch_to_raw_files(
    filesystem_root: Path,
    *,
    registry_root: Path,
    entries_by_id: Mapping[str, Mapping[str, Any]],
    report_ids: Iterable[str],
) -> dict[str, Any]:
    target_ids = set(report_ids)
    expected_by_locator = {
        str(entries_by_id[report_id]["relative_path_sha256"]): entries_by_id[report_id]
        for report_id in target_ids
    }
    found: dict[str, dict[str, Any]] = {}
    root = filesystem_root.expanduser().resolve()
    if not root.is_dir():
        raise BatchPreparationRefused("raw research-report root is unavailable")
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        subdirectories.sort()
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root)
            locator = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()
            expected = expected_by_locator.get(locator)
            if expected is None:
                continue
            logical_path = registry_root / relative
            report_id = report_id_for_path(logical_path)
            digest = content_sha256(path)
            if report_id != expected.get("report_id"):
                raise BatchPreparationRefused(f"raw locator resolved to the wrong report ID: {report_id}")
            if digest != expected.get("content_sha256"):
                raise BatchPreparationRefused(f"raw content changed after T-613: {report_id}")
            stat = path.stat()
            if int(stat.st_size) != int(expected.get("size_bytes") or -1):
                raise BatchPreparationRefused(f"raw size changed after T-613: {report_id}")
            found[report_id] = {
                "report_id": report_id,
                "document_id": str(expected.get("document_id") or ""),
                "content_sha256": digest,
                "relative_path_sha256": locator,
                "size_bytes": int(stat.st_size),
                "file_type": str(expected.get("file_type") or ""),
                "source_key": str(expected.get("source_key") or ""),
                "rights_policy_id": str(expected.get("rights_policy_id") or ""),
            }
    missing = sorted(target_ids - set(found))
    if missing:
        raise BatchPreparationRefused(f"batch raw files are missing: {','.join(missing[:10])}")
    rows = [found[report_id] for report_id in sorted(found)]
    return {
        "report_count": len(rows),
        "total_bytes": sum(int(item["size_bytes"]) for item in rows),
        "file_type_counts": dict(sorted(Counter(str(item["file_type"]) for item in rows).items())),
        "source_scope_counts": dict(sorted(Counter(str(item["source_key"]) for item in rows).items())),
        "content_identity_sha256": payload_sha256(
            [{"report_id": item["report_id"], "content_sha256": item["content_sha256"]} for item in rows]
        ),
        "entries": rows,
    }


def inspect_backup(
    manifest_path: Path | None,
    *,
    decision_generated_at: str,
    now: datetime,
) -> dict[str, Any]:
    if manifest_path is None:
        return {"availability": "not_supplied", "gates_passed": False}
    try:
        payload = _load_json(manifest_path, label="backup manifest")
        generated_at = _parse_time(payload.get("generated_at"), label="backup generated_at")
        decision_time = _parse_time(decision_generated_at, label="decision generated_at")
        retained_until = _parse_time(payload.get("retained_until"), label="backup retained_until")
        counts = dict(payload.get("collection_counts") or {})
        restored = dict(payload.get("restored_collection_counts") or {})
        dump_path = Path(str(payload.get("dump_path") or ""))
        if not dump_path.is_file() and dump_path.name:
            sibling = manifest_path.parent / dump_path.name
            if sibling.is_file():
                dump_path = sibling
        recorded_dump_sha256 = str(payload.get("dump_sha256") or "")
        actual_dump_sha256 = _file_sha256(dump_path) if dump_path.is_file() else ""
        checks = {
            "status_passed": payload.get("status") == "passed",
            "restore_verified": payload.get("restore_verified") is True,
            "source_is_primary": str(payload.get("source_db") or "") == "ai_quant",
            "generated_after_t613_decision": generated_at > decision_time,
            "retention_active": retained_until > now,
            "aggregate_counts_match": bool(payload.get("source_counts"))
            and dict(payload.get("source_counts") or {}) == dict(payload.get("restored_counts") or {}),
            "collection_counts_match": bool(counts) and counts == restored,
            "current_slice_covered": (
                int(counts.get("research_reports") or 0) >= 15
                and int(counts.get("research_documents") or 0) >= 15
                and int(counts.get("research_report_citation_evidence") or 0) >= 112
            ),
            "dump_exists": dump_path.is_file(),
            "dump_size_matches": dump_path.is_file()
            and dump_path.stat().st_size == int(payload.get("dump_size_bytes") or -1),
            "dump_sha256_recorded": bool(SHA256.fullmatch(recorded_dump_sha256)),
            "dump_sha256_matches": bool(recorded_dump_sha256)
            and actual_dump_sha256 == recorded_dump_sha256,
        }
        return {
            "availability": "available",
            "manifest_name": manifest_path.name,
            "manifest_file_sha256": _file_sha256(manifest_path),
            "generated_at": generated_at.isoformat(),
            "retained_until": retained_until.isoformat(),
            "dump_sha256": recorded_dump_sha256,
            "dump_size_bytes": int(payload.get("dump_size_bytes") or 0),
            "source_counts": dict(payload.get("source_counts") or {}),
            "collection_counts": counts,
            "checks": checks,
            "gates_passed": all(checks.values()),
        }
    except (BatchPreparationRefused, OSError, TypeError, ValueError) as exc:
        return {
            "availability": "unavailable",
            "manifest_name": manifest_path.name,
            "error_code": type(exc).__name__,
            "error": str(exc)[:300],
            "gates_passed": False,
        }


def inspect_approval(
    approval_path: Path | None,
    *,
    manifest_sha256: str,
    batch_id: str,
    batch_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    if approval_path is None:
        return {"availability": "not_supplied", "gates_passed": False}
    try:
        payload = _load_json(approval_path, label="human approval")
        approved_at = _parse_time(payload.get("approved_at"), label="approval approved_at")
        age = now - approved_at
        checks = {
            "schema_supported": payload.get("schema_version") == "research-report-clone-batch-approval-v1",
            "status_approved": payload.get("status") == "approved",
            "manifest_bound": payload.get("manifest_sha256") == manifest_sha256,
            "batch_id_bound": payload.get("batch_id") == batch_id,
            "batch_sha_bound": payload.get("batch_sha256") == batch_sha256,
            "scope_clone_only": payload.get("scope") == "isolated_clone_double_run_only",
            "primary_writes_denied": payload.get("primary_writes_allowed") is False,
            "deletes_denied": payload.get("delete_operations_allowed") is False,
            "fresh": timedelta(minutes=-5) <= age <= APPROVAL_MAX_AGE,
            "approver_recorded": bool(str(payload.get("approved_by") or "").strip()),
        }
        return {
            "availability": "available",
            "approval_file_sha256": _file_sha256(approval_path),
            "approved_at": approved_at.isoformat(),
            "approved_by": str(payload.get("approved_by") or ""),
            "checks": checks,
            "gates_passed": all(checks.values()),
        }
    except (BatchPreparationRefused, OSError, TypeError, ValueError) as exc:
        return {
            "availability": "unavailable",
            "error_code": type(exc).__name__,
            "error": str(exc)[:300],
            "gates_passed": False,
        }


def inspect_clone_attestation(
    attestation_path: Path | None,
    *,
    plan_sha256: str,
    backup_dump_sha256: str,
    backup_source_counts: Mapping[str, Any],
    backup_collection_counts: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if attestation_path is None:
        return {"availability": "not_supplied", "gates_passed": False}
    try:
        payload = _load_json(attestation_path, label="clone attestation")
        generated_at = _parse_time(payload.get("generated_at"), label="attestation generated_at")
        age = now - generated_at
        base_url = str(payload.get("base_url") or "")
        validation_plan = {
            "plan_sha256": plan_sha256,
            "input_evidence": {
                "backup_dump_sha256": backup_dump_sha256,
                "backup_source_counts": dict(backup_source_counts),
                "backup_collection_counts": dict(backup_collection_counts),
            },
        }
        validator_passed = True
        validator_error = ""
        try:
            validate_clone_attestation_for_plan(payload, base_url=base_url, plan=validation_plan)
        except RecoveryRefused as exc:
            validator_passed = False
            validator_error = str(exc)
        checks = {
            "existing_clone_validator_passed": validator_passed,
            "fresh": timedelta(minutes=-5) <= age <= ATTESTATION_MAX_AGE,
        }
        result = {
            "availability": "available",
            "attestation_file_sha256": _file_sha256(attestation_path),
            "generated_at": generated_at.isoformat(),
            "database_name": str(payload.get("database_name") or ""),
            "checks": checks,
            "gates_passed": all(checks.values()),
        }
        if validator_error:
            result["validator_error"] = validator_error[:500]
        return result
    except (BatchPreparationRefused, OSError, TypeError, ValueError) as exc:
        return {
            "availability": "unavailable",
            "error_code": type(exc).__name__,
            "error": str(exc)[:300],
            "gates_passed": False,
        }


def build_preflight(
    *,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    decision_path: Path,
    decision: Mapping[str, Any],
    filesystem_root: Path,
    registry_root: Path,
    backup_manifest_path: Path | None,
    approval_path: Path | None,
    clone_attestation_path: Path | None,
    expected_manifest_sha256: str,
    batch_id: str,
    expected_batch_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    manifest_verification = verify_identity_manifest(
        manifest,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    batch = verify_decision_batch(
        decision,
        manifest_sha256=manifest_verification["manifest_sha256"],
        batch_id=batch_id,
        expected_batch_sha256=expected_batch_sha256,
    )
    raw_binding = bind_batch_to_raw_files(
        filesystem_root,
        registry_root=registry_root,
        entries_by_id=manifest_verification["entries_by_id"],
        report_ids=batch["report_ids"],
    )
    backup = inspect_backup(
        backup_manifest_path,
        decision_generated_at=batch["decision_generated_at"],
        now=now,
    )
    plan_core = {
        "schema_version": "research-report-clone-batch-plan-v1",
        "related_task": "T-614",
        "manifest_sha256": manifest_verification["manifest_sha256"],
        "batch_id": batch["batch_id"],
        "batch_sha256": batch["batch_sha256"],
        "raw_content_identity_sha256": raw_binding["content_identity_sha256"],
        "backup_dump_sha256": str(backup.get("dump_sha256") or ""),
        "batch_entries": raw_binding["entries"],
        "write_contract": {
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
        },
    }
    plan_sha256 = payload_sha256(plan_core)
    plan_input_evidence = {
        "backup_dump_sha256": str(backup.get("dump_sha256") or ""),
        "backup_source_counts": dict(backup.get("source_counts") or {}),
        "backup_collection_counts": dict(backup.get("collection_counts") or {}),
    }
    approval = inspect_approval(
        approval_path,
        manifest_sha256=manifest_verification["manifest_sha256"],
        batch_id=batch["batch_id"],
        batch_sha256=batch["batch_sha256"],
        now=now,
    )
    attestation = inspect_clone_attestation(
        clone_attestation_path,
        plan_sha256=plan_sha256,
        backup_dump_sha256=str(backup.get("dump_sha256") or ""),
        backup_source_counts=plan_input_evidence["backup_source_counts"],
        backup_collection_counts=plan_input_evidence["backup_collection_counts"],
        now=now,
    )
    gates = [
        _gate("identity_manifest_verified", True, "T-613 manifest and entries hashes match"),
        _gate("decision_batch_verified", True, "T-613 batch ID and batch SHA match"),
        _gate("raw_batch_content_verified", raw_binding["report_count"] == batch["report_count"], "all selected raw files match full content identity"),
        _gate("fresh_primary_backup_verified", backup.get("gates_passed") is True, "a post-decision restore-verified primary backup is required"),
        _gate("exact_human_approval_verified", approval.get("gates_passed") is True, "approval must bind manifest and batch SHA values"),
        _gate("independent_clone_attestation_verified", attestation.get("gates_passed") is True, "a fresh isolated clone attestation must bind this plan and backup"),
    ]
    execution_ready = all(bool(item["passed"]) for item in gates)
    return {
        "schema_version": "research-report-clone-batch-preflight-v1",
        "related_task": "T-614",
        "generated_at": now.isoformat(),
        "mode": "read_only_preflight_no_execute_mode",
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
        "status": "ready_for_separate_clone_executor" if execution_ready else "blocked_pre_execution",
        "execution_ready": execution_ready,
        "execution_performed": False,
        "automatic_recovery_authorized": False,
        "input_artifacts": {
            "identity_manifest_name": manifest_path.name,
            "identity_manifest_file_sha256": _file_sha256(manifest_path),
            "decision_name": decision_path.name,
            "decision_file_sha256": _file_sha256(decision_path),
        },
        "plan_sha256": plan_sha256,
        "input_evidence": plan_input_evidence,
        "plan": plan_core,
        "batch_summary": {
            "batch_id": batch["batch_id"],
            "batch_sha256": batch["batch_sha256"],
            "report_count": raw_binding["report_count"],
            "total_bytes": raw_binding["total_bytes"],
            "file_type_counts": raw_binding["file_type_counts"],
            "source_scope_counts": raw_binding["source_scope_counts"],
            "raw_content_identity_sha256": raw_binding["content_identity_sha256"],
        },
        "backup_evidence": backup,
        "approval_evidence": approval,
        "clone_attestation_evidence": attestation,
        "gates": gates,
        "failed_gate_ids": [item["gate_id"] for item in gates if not item["passed"]],
        "mutation_guard": {
            "source_files_written": False,
            "postgres_written": False,
            "opensearch_written": False,
            "backup_files_written": False,
            "clone_created": False,
            "artifact_outputs_only": True,
        },
    }


def build_approval_request(preflight: Mapping[str, Any]) -> dict[str, Any]:
    summary = preflight.get("batch_summary") if isinstance(preflight.get("batch_summary"), Mapping) else {}
    plan = preflight.get("plan") if isinstance(preflight.get("plan"), Mapping) else {}
    manifest_sha256 = str(plan.get("manifest_sha256") or "")
    batch_id = str(summary.get("batch_id") or "")
    batch_sha256 = str(summary.get("batch_sha256") or "")
    return {
        "schema_version": "research-report-clone-batch-approval-request-v1",
        "related_task": "T-614",
        "generated_at": utc_iso(),
        "status": "pending_human_approval",
        "manifest_sha256": manifest_sha256,
        "batch_id": batch_id,
        "batch_sha256": batch_sha256,
        "plan_sha256": str(preflight.get("plan_sha256") or ""),
        "scope": "isolated_clone_double_run_only",
        "primary_writes_allowed": False,
        "delete_operations_allowed": False,
        "required_confirmation": (
            f"批准 T-614 {batch_id} 仅在独立 clone 中双跑；"
            f"manifest={manifest_sha256}；batch={batch_sha256}；禁止主库写入和删除。"
        ),
        "approval_record_template": {
            "schema_version": "research-report-clone-batch-approval-v1",
            "status": "approved",
            "approved_at": "<ISO-8601 timestamp>",
            "approved_by": "<human operator>",
            "manifest_sha256": manifest_sha256,
            "batch_id": batch_id,
            "batch_sha256": batch_sha256,
            "scope": "isolated_clone_double_run_only",
            "primary_writes_allowed": False,
            "delete_operations_allowed": False,
        },
        "classification": "local-only",
        "contains_sensitive_data": False,
        "acceptable_for_non_local_release": False,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--decision", type=Path, default=DEFAULT_DECISION)
    parser.add_argument("--filesystem-root", type=Path, default=DEFAULT_FILESYSTEM_ROOT)
    parser.add_argument("--registry-root", type=Path, default=DEFAULT_REGISTRY_ROOT)
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--clone-attestation", type=Path)
    parser.add_argument("--expected-manifest-sha256", default=EXPECTED_MANIFEST_SHA256)
    parser.add_argument("--batch-id", default=EXPECTED_BATCH_ID)
    parser.add_argument("--expected-batch-sha256", default=EXPECTED_BATCH_SHA256)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--approval-output", type=Path, default=DEFAULT_APPROVAL_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    preflight = build_preflight(
        manifest_path=args.manifest,
        manifest=_load_json(args.manifest, label="identity manifest"),
        decision_path=args.decision,
        decision=_load_json(args.decision, label="recovery decision"),
        filesystem_root=args.filesystem_root,
        registry_root=args.registry_root,
        backup_manifest_path=args.backup_manifest,
        approval_path=args.approval,
        clone_attestation_path=args.clone_attestation,
        expected_manifest_sha256=str(args.expected_manifest_sha256),
        batch_id=str(args.batch_id),
        expected_batch_sha256=str(args.expected_batch_sha256),
    )
    approval_request = build_approval_request(preflight)
    _write_json(args.output, preflight)
    _write_json(args.approval_output, approval_request)
    print(
        json.dumps(
            {
                "status": preflight["status"],
                "execution_ready": preflight["execution_ready"],
                "execution_performed": False,
                "batch_id": preflight["batch_summary"]["batch_id"],
                "report_count": preflight["batch_summary"]["report_count"],
                "total_bytes": preflight["batch_summary"]["total_bytes"],
                "plan_sha256": preflight["plan_sha256"],
                "failed_gate_ids": preflight["failed_gate_ids"],
                "output": str(args.output),
                "approval_output": str(args.approval_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
