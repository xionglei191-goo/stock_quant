#!/usr/bin/env python3
"""Validate or append one local-only dynamic-allocation paper snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository, build_paper_snapshot  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", required=True, help="decision snapshot input JSON")
    result.add_argument("--execute", action="store_true", help="append to an explicit local JSONL ledger")
    result.add_argument("--output", help="required with --execute; no default write location")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.execute and not args.output:
        parser().error("--output is required with --execute")
    if not args.execute and args.output:
        parser().error("--output is only accepted with --execute")
    input_path = Path(args.input)
    if input_path.is_symlink() or not input_path.is_file():
        raise ValueError("input must be a regular, non-symbolic-link JSON file")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    snapshot = build_paper_snapshot(payload)
    response: dict[str, object] = {
        "status": "validated" if not args.execute else "completed",
        "mode": "dry-run" if not args.execute else "execute",
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "snapshot": snapshot.to_dict(),
    }
    if args.execute:
        append_result = JsonlPaperSnapshotRepository(args.output).append(snapshot)
        response["append"] = {
            "appended": append_result.appended,
            "record_hash": append_result.record_hash,
            "output_path": append_result.output_path,
        }
    print(json.dumps(response, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
