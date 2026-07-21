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
from typing import Any, Mapping


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_VERSION = "research-report-clone-segment-state-v1"
QUIESCENCE_SCHEMA_VERSION = "research-report-clone-segment-quiescence-proof-v1"


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
        "active_writer_sessions", "operator_boundary",
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
        proof.get("active_writer_sessions") == 0,
        proof.get("operator_boundary") == "primary_writers_and_known_schedulers_stopped_for_clone_segment",
    )
    if not all(checks):
        raise SegmentStateRefused("quiescence proof does not satisfy clone segment gates")
    return {"proof_sha256": str(proof["proof_sha256"]), "generated_at": generated.isoformat()}


def build_quiescence_proof(
    *,
    plan_sha256: str,
    backup_dump_sha256: str,
    known_scheduler_units: list[str],
    scheduler_units_stopped: bool,
    active_writer_sessions: int,
    primary_service_reachable: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not known_scheduler_units or any(not str(item).strip() for item in known_scheduler_units):
        raise SegmentStateRefused("at least one known scheduler unit is required")
    if not scheduler_units_stopped or active_writer_sessions != 0 or primary_service_reachable:
        raise SegmentStateRefused("quiescence proof requires stopped schedulers, zero writers, and unreachable primary")
    core = {
        "schema_version": QUIESCENCE_SCHEMA_VERSION,
        "producer": "scripts/manage_research_report_clone_segment.py",
        "generated_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "plan_sha256": _required_sha(plan_sha256, "plan_sha256"),
        "backup_dump_sha256": _required_sha(backup_dump_sha256, "backup_dump_sha256"),
        "primary_service_reachable": False,
        "known_scheduler_units": sorted(set(known_scheduler_units)),
        "scheduler_units_stopped": True,
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


def _required_sha(value: Any, label: str) -> str:
    result = str(value or "")
    if not SHA256.fullmatch(result):
        raise SegmentStateRefused(f"{label} must be a SHA-256 hex digest")
    return result


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
    counts: Mapping[str, Any],
) -> dict[str, Any]:
    current = dict(state)
    if current.get("status") != "active":
        raise SegmentStateRefused("only an active segment can accept a checkpoint")
    if not re.fullmatch(r"t613-batch-00(?:0[1-9]|[1-3][0-9]|4[0-4])", batch_id):
        raise SegmentStateRefused("batch_id is outside the governed T-613 range")
    _required_sha(batch_sha256, "batch_sha256")
    if not run1_path.is_file() or not run2_path.is_file():
        raise SegmentStateRefused("run artifacts must exist")
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
    checkpoint_core = {
        "batch_id": batch_id,
        "batch_sha256": batch_sha256,
        "run1_artifact_sha256": run1_sha,
        "run2_artifact_sha256": run2_sha,
        "counts": dict(counts),
        "created_at": utc_iso(),
    }
    checkpoint = dict(checkpoint_core)
    checkpoint["checkpoint_sha256"] = canonical_sha256(checkpoint_core)
    batches.append(checkpoint)
    current["batches"] = batches
    current["latest_checkpoint"] = checkpoint["checkpoint_sha256"]
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
    checkpoint.add_argument("--counts-json", required=True)
    abort = sub.add_parser("abort")
    abort.add_argument("--state", type=Path, required=True)
    abort.add_argument("--reason", required=True)
    proof = sub.add_parser("proof")
    proof.add_argument("--plan-sha256", required=True)
    proof.add_argument("--backup-dump-sha256", required=True)
    proof.add_argument("--scheduler-unit", action="append", required=True)
    proof.add_argument("--active-writer-sessions", type=int, default=0)
    proof.add_argument("--primary-service-reachable", action="store_true")
    proof.add_argument("--confirm-schedulers-stopped", action="store_true")
    proof.add_argument("--output", type=Path, required=True)
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
            counts=json.loads(args.counts_json),
        )
        write_state(args.state, state)
    elif args.command == "abort":
        write_state(args.state, abort_state(load_state(args.state), reason=args.reason))
    else:
        proof = build_quiescence_proof(
            plan_sha256=args.plan_sha256,
            backup_dump_sha256=args.backup_dump_sha256,
            known_scheduler_units=args.scheduler_unit,
            scheduler_units_stopped=args.confirm_schedulers_stopped,
            active_writer_sessions=args.active_writer_sessions,
            primary_service_reachable=args.primary_service_reachable,
        )
        write_state(args.output, proof)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
