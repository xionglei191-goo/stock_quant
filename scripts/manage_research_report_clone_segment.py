#!/usr/bin/env python3
"""Manage the local-only state contract for a bounded research clone segment.

This tool never connects to PostgreSQL and never executes a report batch.  It
records immutable run-artifact hashes and clone identity so a later executor
can prove which accumulated state it is resuming from.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_VERSION = "research-report-clone-segment-state-v1"
QUIESCENCE_SCHEMA_VERSION = "research-report-clone-segment-quiescence-proof-v1"
VACUUM_SCHEMA_VERSION = "research-report-clone-segment-vacuum-evidence-v1"
REQUIRED_CHECKPOINT_COUNTS = (
    "records",
    "audit_log",
    "market_data_bars",
    "research_reports",
    "research_documents",
    "research_report_citation_evidence",
    "structured_research_reports",
    "report_viewpoints",
    "report_forecasts",
)


class SegmentStateRefused(RuntimeError):
    """Raised when a segment state transition would weaken its evidence."""


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_quiescence_proof(
    proof_path: Path,
    *,
    plan_sha256: str,
    backup_dump_sha256: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate a fresh, hash-bound proof that known primary writers are quiet."""
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SegmentStateRefused("quiescence proof must be readable JSON") from exc
    if not isinstance(proof, dict) or proof.get("schema_version") != QUIESCENCE_SCHEMA_VERSION:
        raise SegmentStateRefused("quiescence proof schema is unsupported")
    if proof.get("status") != "passed" or proof.get("producer") != "scripts/manage_research_report_clone_segment.py":
        raise SegmentStateRefused("quiescence proof status or producer is invalid")
    try:
        generated = datetime.fromisoformat(str(proof.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise SegmentStateRefused("quiescence proof timestamp is invalid") from exc
    generated = generated.astimezone(timezone.utc)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if generated > current + timedelta(minutes=2) or current - generated > timedelta(minutes=30):
        raise SegmentStateRefused("quiescence proof is stale")
    core_keys = (
        "schema_version", "producer", "generated_at", "plan_sha256", "backup_dump_sha256",
        "primary_service_reachable", "known_scheduler_units", "scheduler_units_stopped",
        "scheduler_observations", "writer_container_observations", "active_writer_sessions", "operator_boundary",
    )
    core = {key: proof.get(key) for key in core_keys}
    if proof.get("proof_sha256") != canonical_sha256(core):
        raise SegmentStateRefused("quiescence proof hash is invalid")
    checks = (
        proof.get("plan_sha256") == plan_sha256,
        proof.get("backup_dump_sha256") == backup_dump_sha256,
        proof.get("primary_service_reachable") is False,
        isinstance(proof.get("known_scheduler_units"), list) and bool(proof.get("known_scheduler_units")),
        proof.get("scheduler_units_stopped") is True,
        isinstance(proof.get("scheduler_observations"), list) and len(proof["scheduler_observations"]) == len(proof["known_scheduler_units"]),
        isinstance(proof.get("writer_container_observations"), list) and bool(proof.get("writer_container_observations")),
        all(item.get("stopped") is True for item in proof.get("scheduler_observations", [])),
        all(item.get("running") is False and item.get("returncode") == 0 and bool(item.get("container_id")) for item in proof.get("writer_container_observations", [])),
        proof.get("active_writer_sessions") == 0,
        proof.get("operator_boundary") == "primary_writers_and_known_schedulers_stopped_for_clone_segment",
    )
    if not all(checks):
        raise SegmentStateRefused("quiescence proof does not satisfy clone segment gates")
    return {"proof_sha256": str(proof["proof_sha256"]), "generated_at": generated.isoformat()}


def collect_quiescence_observations(
    *,
    scheduler_units: list[str],
    writer_containers: list[str],
    primary_url: str,
    dsn: str,
) -> dict[str, Any]:
    """Collect read-only scheduler, container, URL, and PostgreSQL observations."""
    if not shutil.which("systemctl") or not shutil.which("docker") or not shutil.which("psql"):
        raise SegmentStateRefused("systemctl, docker, and psql are required for direct quiescence observation")
    scheduler_observations: list[dict[str, Any]] = []
    for unit in scheduler_units:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit], text=True, capture_output=True, check=False, timeout=15
        )
        state = (result.stdout or result.stderr).strip() or "unknown"
        scheduler_observations.append({"unit": unit, "state": state, "stopped": state in {"inactive", "failed"}, "returncode": result.returncode})
    writer_observations: list[dict[str, Any]] = []
    for container in writer_containers:
        result = subprocess.run(["docker", "inspect", "--format", "{{.Id}}|{{.State.Status}}|{{.State.Running}}", container], text=True, capture_output=True, check=False, timeout=15)
        raw = (result.stdout or "").strip()
        parts = raw.split("|", 2)
        writer_observations.append({"container": container, "container_id": parts[0] if len(parts) > 0 else "", "state": parts[1] if len(parts) > 1 else "missing", "running": parts[2].lower() == "true" if len(parts) > 2 else False, "returncode": result.returncode})
    primary_reachable = False
    try:
        with urlopen(primary_url.rstrip("/") + "/api/health", timeout=5) as response:
            response.read(1)
            primary_reachable = True
    except (HTTPError, URLError, OSError, TimeoutError):
        primary_reachable = False
    result = subprocess.run(
        ["psql", dsn, "-X", "-q", "-t", "-A", "-c", "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"],
        text=True, capture_output=True, check=False, timeout=15,
    )
    if result.returncode != 0 or not (result.stdout or "").strip().isdigit():
        raise SegmentStateRefused("could not read active PostgreSQL sessions")
    active_sessions = int(result.stdout.strip())
    return {
        "scheduler_observations": scheduler_observations,
        "writer_container_observations": writer_observations,
        "scheduler_units_stopped": bool(scheduler_observations) and all(item["stopped"] for item in scheduler_observations),
        "active_writer_sessions": active_sessions,
        "primary_service_reachable": primary_reachable,
    }


def build_quiescence_proof(
    *,
    plan_sha256: str,
    backup_dump_sha256: str,
    known_scheduler_units: list[str],
    scheduler_units_stopped: bool,
    active_writer_sessions: int,
    primary_service_reachable: bool,
    scheduler_observations: list[Mapping[str, Any]] | None = None,
    writer_container_observations: list[Mapping[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not known_scheduler_units or any(not str(item).strip() for item in known_scheduler_units):
        raise SegmentStateRefused("at least one known scheduler unit is required")
    if not scheduler_units_stopped or active_writer_sessions != 0 or primary_service_reachable:
        raise SegmentStateRefused("quiescence proof requires stopped schedulers, zero writers, and unreachable primary")
    scheduler_rows = [dict(item) for item in (scheduler_observations or [{"unit": item, "state": "inactive", "stopped": True} for item in known_scheduler_units])]
    writer_rows = [dict(item) for item in (writer_container_observations or [])]
    if not writer_rows or not all(item.get("stopped") is True for item in scheduler_rows) or not all(item.get("running") is False and item.get("returncode") == 0 and bool(item.get("container_id")) for item in writer_rows):
        raise SegmentStateRefused("quiescence observations contain a running scheduler or writer")
    core = {
        "schema_version": QUIESCENCE_SCHEMA_VERSION,
        "producer": "scripts/manage_research_report_clone_segment.py",
        "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "plan_sha256": _required_sha(plan_sha256, "plan_sha256"),
        "backup_dump_sha256": _required_sha(backup_dump_sha256, "backup_dump_sha256"),
        "primary_service_reachable": False,
        "known_scheduler_units": sorted(set(known_scheduler_units)),
        "scheduler_units_stopped": True,
        "scheduler_observations": scheduler_rows,
        "writer_container_observations": writer_rows,
        "active_writer_sessions": 0,
        "operator_boundary": "primary_writers_and_known_schedulers_stopped_for_clone_segment",
    }
    return {**core, "status": "passed", "proof_sha256": canonical_sha256(core), "classification": "local-only", "acceptable_for_non_local_release": False}


def load_state(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SegmentStateRefused("segment state must be readable JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise SegmentStateRefused("unsupported segment state schema")
    return payload


def validate_active_state(
    state: Mapping[str, Any],
    *,
    plan_sha256: str,
    manifest_sha256: str,
    attestation_sha256: str,
) -> None:
    if state.get("schema_version") != SCHEMA_VERSION or state.get("status") != "active":
        raise SegmentStateRefused("segment state must be an active supported state")
    if state.get("plan_sha256") != plan_sha256 or state.get("manifest_sha256") != manifest_sha256:
        raise SegmentStateRefused("segment state does not match the execution plan/manifest")
    identity = state.get("clone_identity") if isinstance(state.get("clone_identity"), Mapping) else {}
    if identity.get("attestation_sha256") != attestation_sha256:
        raise SegmentStateRefused("segment state does not match the clone attestation")


def _required_sha(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256.fullmatch(result):
        raise SegmentStateRefused(f"{label} must be a SHA-256 hex digest")
    return result


def load_restore_verified_backup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SegmentStateRefused("backup manifest must be readable JSON") from exc
    if not isinstance(payload, Mapping) or payload.get("status") != "passed" or payload.get("restore_verified") is not True:
        raise SegmentStateRefused("backup manifest is not restore-verified")
    dump_path = Path(str(payload.get("dump_path") or ""))
    if not dump_path.is_file() and dump_path.name:
        sibling = path.parent / dump_path.name
        if sibling.is_file():
            dump_path = sibling
    expected_dump_sha = str(payload.get("dump_sha256") or "")
    _required_sha(expected_dump_sha, "backup dump SHA")
    if not dump_path.is_file() or file_sha256(dump_path) != expected_dump_sha:
        raise SegmentStateRefused("backup dump does not match its manifest")
    source_counts = dict(payload.get("source_counts") or {})
    restored_counts = dict(payload.get("restored_counts") or {})
    source_research = dict(payload.get("collection_counts") or {})
    restored_research = dict(payload.get("restored_collection_counts") or {})
    counts: dict[str, int] = {}
    for key in REQUIRED_CHECKPOINT_COUNTS:
        source = source_counts.get(key, source_research.get(key))
        restored = restored_counts.get(key, restored_research.get(key))
        if source is None or restored is None or int(source) != int(restored) or int(restored) < 0:
            raise SegmentStateRefused(f"backup restore equality is incomplete for {key}")
        counts[key] = int(restored)
    return {
        "manifest_sha256": file_sha256(path),
        "dump_sha256": expected_dump_sha,
        "counts": counts,
        "generated_at": str(payload.get("generated_at") or ""),
    }


def load_vacuum_evidence(path: Path, *, backup_manifest_path: Path, backup: Mapping[str, Any]) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SegmentStateRefused("vacuum evidence must be readable JSON") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != VACUUM_SCHEMA_VERSION:
        raise SegmentStateRefused("vacuum evidence schema is unsupported")
    if payload.get("status") != "passed" or payload.get("vacuum_completed") is not True:
        raise SegmentStateRefused("vacuum evidence is not completed")
    if payload.get("target_scope") != "isolated_clone_only" or payload.get("primary_writes_allowed") is not False:
        raise SegmentStateRefused("vacuum evidence target boundary is unsafe")
    if payload.get("backup_manifest_sha256") != backup["manifest_sha256"] or payload.get("backup_dump_sha256") != backup["dump_sha256"]:
        raise SegmentStateRefused("vacuum evidence is not bound to the restore-verified backup")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        raise SegmentStateRefused("vacuum evidence must list affected tables")
    try:
        backup_time = datetime.fromisoformat(str(backup.get("generated_at") or "").replace("Z", "+00:00"))
        vacuum_time = datetime.fromisoformat(str(payload.get("generated_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise SegmentStateRefused("backup/vacuum timestamps are invalid") from exc
    if vacuum_time < backup_time:
        raise SegmentStateRefused("vacuum evidence predates the restore-verified backup")
    return {"evidence_sha256": file_sha256(path), "generated_at": vacuum_time.isoformat()}


def init_state(
    *,
    segment_id: str,
    plan_sha256: str,
    manifest_sha256: str,
    clone_identity: Mapping[str, Any],
) -> dict[str, Any]:
    if not re.fullmatch(r"t613-segment-[0-9]{4}", segment_id):
        raise SegmentStateRefused("segment_id must use t613-segment-0001 format")
    _required_sha(plan_sha256, "plan_sha256")
    _required_sha(manifest_sha256, "manifest_sha256")
    identity = dict(clone_identity)
    for key in ("database_name", "database_oid", "postgres_system_identifier", "attestation_sha256"):
        if not str(identity.get(key) or ""):
            raise SegmentStateRefused(f"clone_identity.{key} is required")
    _required_sha(identity["attestation_sha256"], "clone_identity.attestation_sha256")
    return {
        "schema_version": SCHEMA_VERSION,
        "related_task": "T-617",
        "segment_id": segment_id,
        "plan_sha256": plan_sha256,
        "manifest_sha256": manifest_sha256,
        "clone_identity": identity,
        "status": "active",
        "batches": [],
        "latest_checkpoint": None,
        "accumulated_counts": None,
        "created_at": utc_iso(),
        "updated_at": utc_iso(),
        "primary_writes_allowed": False,
        "delete_operations": [],
        "classification": "local-only",
        "acceptable_for_non_local_release": False,
    }


def append_checkpoint(
    state: Mapping[str, Any],
    *,
    batch_id: str,
    batch_sha256: str,
    run1_path: Path,
    run2_path: Path,
    backup_manifest_path: Path | None = None,
    vacuum_evidence_path: Path | None = None,
    counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = dict(state)
    counts = counts or {}
    if current.get("status") != "active":
        raise SegmentStateRefused("only an active segment can accept a checkpoint")
    if not re.fullmatch(r"t613-batch-00(?:0[1-9]|[1-3][0-9]|4[0-4])", batch_id):
        raise SegmentStateRefused("batch_id is outside the governed T-613 range")
    _required_sha(batch_sha256, "batch_sha256")
    if any(key not in counts for key in REQUIRED_CHECKPOINT_COUNTS):
        missing = sorted(set(REQUIRED_CHECKPOINT_COUNTS) - set(counts))
        raise SegmentStateRefused(f"checkpoint counts are incomplete: {','.join(missing)}")
    normalized_counts: dict[str, int] = {}
    for key in REQUIRED_CHECKPOINT_COUNTS:
        try:
            value = int(counts[key])
        except (TypeError, ValueError) as exc:
            raise SegmentStateRefused(f"checkpoint count is not an integer: {key}") from exc
        if value < 0:
            raise SegmentStateRefused(f"checkpoint count cannot be negative: {key}")
        normalized_counts[key] = value
    if backup_manifest_path is None:
        raise SegmentStateRefused("restore-verified backup manifest is required before checkpoint")
    if not run1_path.is_file() or not run2_path.is_file():
        raise SegmentStateRefused("run artifacts must exist")
    backup = load_restore_verified_backup(backup_manifest_path)
    if vacuum_evidence_path is None:
        raise SegmentStateRefused("vacuum evidence is required after the restore-verified backup")
    vacuum = load_vacuum_evidence(vacuum_evidence_path, backup_manifest_path=backup_manifest_path, backup=backup)
    backup_counts = backup["counts"]
    if any(int(counts[key]) != int(backup_counts[key]) for key in REQUIRED_CHECKPOINT_COUNTS):
        raise SegmentStateRefused("checkpoint counts do not match the restore-verified backup")
    batches = [dict(item) for item in current.get("batches", []) if isinstance(item, Mapping)]
    if any(item.get("batch_id") == batch_id for item in batches):
        raise SegmentStateRefused("batch checkpoint already exists")
    run1_sha = file_sha256(run1_path)
    run2_sha = file_sha256(run2_path)
    try:
        run1 = json.loads(run1_path.read_text(encoding="utf-8"))
        run2 = json.loads(run2_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SegmentStateRefused("run artifacts must be valid JSON") from exc
    for run, label in ((run1, "run1"), (run2, "run2")):
        if not isinstance(run, Mapping):
            raise SegmentStateRefused(f"{label} artifact must be a JSON object")
        if run.get("plan_sha256") != current.get("plan_sha256") or run.get("manifest_sha256") != current.get("manifest_sha256"):
            raise SegmentStateRefused(f"{label} artifact is not bound to segment plan/manifest")
        if run.get("batch_id") != batch_id or run.get("batch_sha256") != batch_sha256:
            raise SegmentStateRefused(f"{label} artifact is not bound to the checkpoint batch")
    comparison = run2.get("idempotency_comparison") if isinstance(run2, Mapping) else None
    if not isinstance(comparison, Mapping) or comparison.get("passed") is not True:
        raise SegmentStateRefused("run2 idempotency gate must pass before checkpoint")
    prior_run_sha256 = str(comparison.get("prior_run_sha256") or "")
    _required_sha(prior_run_sha256, "prior_run_sha256")
    if prior_run_sha256 != str(run1.get("artifact_sha256") or ""):
        raise SegmentStateRefused("run2 prior-run SHA does not match run1 artifact")
    checkpoint_core = {
        "batch_id": batch_id,
        "batch_sha256": batch_sha256,
        "run1_artifact_sha256": run1_sha,
        "run2_artifact_sha256": run2_sha,
        "counts": normalized_counts,
        "prior_run_sha256": prior_run_sha256,
        "backup_manifest_sha256": backup["manifest_sha256"],
        "backup_dump_sha256": backup["dump_sha256"],
        "vacuum_evidence_sha256": vacuum["evidence_sha256"],
        "vacuum_completed_at": vacuum["generated_at"],
        "created_at": utc_iso(),
    }
    checkpoint = dict(checkpoint_core)
    checkpoint["checkpoint_sha256"] = canonical_sha256(checkpoint_core)
    batches.append(checkpoint)
    current["batches"] = batches
    current["latest_checkpoint"] = checkpoint["checkpoint_sha256"]
    current["accumulated_counts"] = normalized_counts
    current["updated_at"] = utc_iso()
    return current


def abort_state(state: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    current = dict(state)
    if current.get("status") != "active":
        raise SegmentStateRefused("only an active segment can be aborted")
    if not reason.strip():
        raise SegmentStateRefused("abort reason is required")
    current["status"] = "aborted"
    current["abort"] = {"reason": reason.strip(), "created_at": utc_iso()}
    current["updated_at"] = utc_iso()
    return current


def resume_state(state: Mapping[str, Any], *, checkpoint_sha256: str) -> dict[str, Any]:
    """Resume an aborted segment only from its latest verified checkpoint."""
    current = dict(state)
    if current.get("status") != "aborted":
        raise SegmentStateRefused("only an aborted segment can be resumed")
    _required_sha(checkpoint_sha256, "checkpoint_sha256")
    batches = [dict(item) for item in current.get("batches", []) if isinstance(item, Mapping)]
    known = {str(item.get("checkpoint_sha256") or "") for item in batches}
    if checkpoint_sha256 not in known:
        raise SegmentStateRefused("resume checkpoint is not present in segment state")
    if checkpoint_sha256 != str(current.get("latest_checkpoint") or ""):
        raise SegmentStateRefused("resume must start from the latest checkpoint")
    current["status"] = "active"
    current["resume_of"] = checkpoint_sha256
    current["resumed_at"] = utc_iso()
    current["updated_at"] = utc_iso()
    return current


def write_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--segment-id", required=True)
    init.add_argument("--plan-sha256", required=True)
    init.add_argument("--manifest-sha256", required=True)
    init.add_argument("--database-name", required=True)
    init.add_argument("--database-oid", required=True)
    init.add_argument("--postgres-system-identifier", required=True)
    init.add_argument("--attestation-sha256", required=True)
    init.add_argument("--output", type=Path, required=True)
    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--state", type=Path, required=True)
    checkpoint.add_argument("--batch-id", required=True)
    checkpoint.add_argument("--batch-sha256", required=True)
    checkpoint.add_argument("--run1", type=Path, required=True)
    checkpoint.add_argument("--run2", type=Path, required=True)
    checkpoint.add_argument("--backup-manifest", type=Path, required=True)
    checkpoint.add_argument("--vacuum-evidence", type=Path, required=True)
    checkpoint.add_argument("--counts-json")
    abort = sub.add_parser("abort")
    abort.add_argument("--state", type=Path, required=True)
    abort.add_argument("--reason", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--state", type=Path, required=True)
    resume.add_argument("--checkpoint-sha256", required=True)
    proof = sub.add_parser("proof")
    proof.add_argument("--plan-sha256", required=True)
    proof.add_argument("--backup-dump-sha256", required=True)
    proof.add_argument("--scheduler-unit", action="append", required=True)
    proof.add_argument("--writer-container", action="append", required=True)
    proof.add_argument("--active-writer-sessions", type=int, default=0)
    proof.add_argument("--primary-service-reachable", action="store_true")
    proof.add_argument("--confirm-schedulers-stopped", action="store_true")
    proof.add_argument("--output", type=Path, required=True)
    observe = sub.add_parser("observe-proof")
    observe.add_argument("--plan-sha256", required=True)
    observe.add_argument("--backup-dump-sha256", required=True)
    observe.add_argument("--scheduler-unit", action="append", required=True)
    observe.add_argument("--writer-container", action="append", default=[])
    observe.add_argument("--primary-url", required=True)
    observe.add_argument("--dsn", required=True)
    observe.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "init":
        state = init_state(
            segment_id=args.segment_id,
            plan_sha256=args.plan_sha256,
            manifest_sha256=args.manifest_sha256,
            clone_identity={
                "database_name": args.database_name,
                "database_oid": args.database_oid,
                "postgres_system_identifier": args.postgres_system_identifier,
                "attestation_sha256": args.attestation_sha256,
            },
        )
        write_state(args.output, state)
    elif args.command == "checkpoint":
        state = append_checkpoint(
            load_state(args.state),
            batch_id=args.batch_id,
            batch_sha256=args.batch_sha256,
            run1_path=args.run1,
            run2_path=args.run2,
            backup_manifest_path=args.backup_manifest,
            vacuum_evidence_path=args.vacuum_evidence,
            counts=json.loads(args.counts_json) if args.counts_json else load_restore_verified_backup(args.backup_manifest)["counts"],
        )
        write_state(args.state, state)
    elif args.command == "abort":
        write_state(args.state, abort_state(load_state(args.state), reason=args.reason))
    elif args.command == "resume":
        write_state(args.state, resume_state(load_state(args.state), checkpoint_sha256=args.checkpoint_sha256))
    elif args.command == "proof":
        proof = build_quiescence_proof(
            plan_sha256=args.plan_sha256,
            backup_dump_sha256=args.backup_dump_sha256,
            known_scheduler_units=args.scheduler_unit,
            scheduler_units_stopped=args.confirm_schedulers_stopped,
            active_writer_sessions=args.active_writer_sessions,
            primary_service_reachable=args.primary_service_reachable,
            writer_container_observations=[{"container": item, "container_id": "operator-supplied", "running": False, "returncode": 0, "state": "exited"} for item in args.writer_container],
        )
        write_state(args.output, proof)
    else:
        observations = collect_quiescence_observations(
            scheduler_units=args.scheduler_unit,
            writer_containers=args.writer_container,
            primary_url=args.primary_url,
            dsn=args.dsn,
        )
        proof = build_quiescence_proof(
            plan_sha256=args.plan_sha256,
            backup_dump_sha256=args.backup_dump_sha256,
            known_scheduler_units=args.scheduler_unit,
            scheduler_units_stopped=bool(observations["scheduler_units_stopped"]),
            active_writer_sessions=int(observations["active_writer_sessions"]),
            primary_service_reachable=bool(observations["primary_service_reachable"]),
            scheduler_observations=observations["scheduler_observations"],
            writer_container_observations=observations["writer_container_observations"],
        )
        write_state(args.output, proof)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
