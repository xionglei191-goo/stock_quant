"""Append-only JSONL repository with an integrity hash chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol

from .snapshot import PaperDecisionSnapshot, canonical_json


GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class AppendResult:
    run_id: str
    appended: bool
    record_hash: str
    output_path: str


class PaperSnapshotRepository(Protocol):
    def append(self, snapshot: PaperDecisionSnapshot) -> AppendResult: ...

    def replay(self) -> list[PaperDecisionSnapshot]: ...


class JsonlPaperSnapshotRepository:
    """Local adapter; duplicate identical run ids are explicit no-ops."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.exists() and self.path.is_symlink():
            raise ValueError("paper snapshot output must not be a symbolic link")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("paper snapshot output must be a file")

    def append(self, snapshot: PaperDecisionSnapshot) -> AppendResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("paper snapshot output must not be a symbolic link")
        with self.path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            envelopes = self._read_and_validate(handle)
            snapshot_payload = snapshot.to_dict()
            snapshot_hash = hashlib.sha256(canonical_json(snapshot_payload).encode("utf-8")).hexdigest()
            for envelope in envelopes:
                if envelope["snapshot"]["run_id"] == snapshot.run_id:
                    if envelope["snapshot_hash"] != snapshot_hash:
                        raise ValueError(f"immutable paper snapshot conflict: {snapshot.run_id}")
                    return AppendResult(snapshot.run_id, False, envelope["record_hash"], str(self.path))
            previous_hash = envelopes[-1]["record_hash"] if envelopes else GENESIS_HASH
            record_core = {
                "previous_record_hash": previous_hash,
                "snapshot_hash": snapshot_hash,
                "snapshot": snapshot_payload,
            }
            record_hash = hashlib.sha256(canonical_json(record_core).encode("utf-8")).hexdigest()
            envelope = {
                **record_core,
                "record_hash": record_hash,
                "appended_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            handle.seek(0, os.SEEK_END)
            handle.write(canonical_json(envelope) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            return AppendResult(snapshot.run_id, True, record_hash, str(self.path))

    def replay(self) -> list[PaperDecisionSnapshot]:
        if not self.path.exists():
            return []
        if self.path.is_symlink():
            raise ValueError("paper snapshot output must not be a symbolic link")
        with self.path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            envelopes = self._read_and_validate(handle)
        return [build_snapshot_from_record(item["snapshot"]) for item in envelopes]

    @staticmethod
    def _read_and_validate(handle: Any) -> list[dict[str, Any]]:
        handle.seek(0)
        envelopes: list[dict[str, Any]] = []
        expected_previous = GENESIS_HASH
        seen: set[str] = set()
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                envelope = json.loads(line)
                if not isinstance(envelope, dict):
                    raise TypeError("envelope must be an object")
                snapshot = envelope["snapshot"]
                if not isinstance(snapshot, dict):
                    raise TypeError("snapshot must be an object")
                run_id = snapshot["run_id"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"invalid paper snapshot JSONL at line {line_number}") from exc
            if run_id in seen:
                raise ValueError(f"duplicate run id in paper snapshot ledger: {run_id}")
            snapshot_hash = hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
            if envelope.get("snapshot_hash") != snapshot_hash:
                raise ValueError(f"paper snapshot content hash mismatch at line {line_number}")
            record_core = {
                "previous_record_hash": envelope.get("previous_record_hash"),
                "snapshot_hash": snapshot_hash,
                "snapshot": snapshot,
            }
            record_hash = hashlib.sha256(canonical_json(record_core).encode("utf-8")).hexdigest()
            if envelope.get("previous_record_hash") != expected_previous or envelope.get("record_hash") != record_hash:
                raise ValueError(f"paper snapshot hash chain mismatch at line {line_number}")
            envelopes.append(envelope)
            expected_previous = record_hash
            seen.add(run_id)
        return envelopes


def build_snapshot_from_record(payload: dict[str, Any]) -> PaperDecisionSnapshot:
    rebuilt = build_snapshot_payload(payload)
    if rebuilt.run_id != payload.get("run_id"):
        raise ValueError("paper snapshot deterministic run id mismatch")
    return rebuilt


def build_snapshot_payload(payload: dict[str, Any]) -> PaperDecisionSnapshot:
    # Import here to keep the repository adapter lightweight for callers that
    # only append already-built snapshots.
    from .snapshot import build_paper_snapshot

    return build_paper_snapshot(payload)
