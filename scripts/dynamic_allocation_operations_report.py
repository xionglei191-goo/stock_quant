#!/usr/bin/env python3
"""Build a read-only longitudinal report from local paper-operation evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dynamic_allocation.operations import (  # noqa: E402
    build_longitudinal_report,
    discover_daily_reports,
    load_daily_reports,
)
from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository  # noqa: E402
from app.dynamic_allocation.performance import build_performance_evidence, load_performance_input  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--ledger", required=True, help="existing local JSONL hash-chain ledger")
    result.add_argument("--daily-reports", help="directory containing archived daily JSON reports")
    result.add_argument("--daily-report", action="append", default=[], help="individual daily JSON report; repeatable")
    result.add_argument("--performance-input", help="versioned forward paper price/session evidence JSON")
    result.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    result.add_argument("--output", help="optional output path; omit for a read-only stdout report")
    result.add_argument("--execute", action="store_true", help="allow writing --output")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if bool(args.output) != bool(args.execute):
        parser().error("--output and --execute must be supplied together")
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        parser().error("--as-of must include a timezone")
    ledger = JsonlPaperSnapshotRepository(args.ledger)
    report_paths = [Path(item) for item in args.daily_report]
    if args.daily_reports:
        report_paths.extend(discover_daily_reports(args.daily_reports))
    snapshots = ledger.replay()
    performance = None
    if args.performance_input:
        performance = build_performance_evidence(
            snapshots,
            load_performance_input(args.performance_input),
            as_of=as_of,
        )
    report = build_longitudinal_report(
        snapshots,
        load_daily_reports(report_paths),
        as_of=as_of,
        performance_evidence=performance,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        if output.exists() and output.is_symlink():
            raise ValueError("operations report output must not be a symbolic link")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
