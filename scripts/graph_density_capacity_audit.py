#!/usr/bin/env python3
"""Audit governed graph density and renderer capacity without mutating data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.service_modules.graph_density_capacity import build_density_capacity_audit  # noqa: E402


DEFAULT_OUTPUT = ROOT / "artifacts" / "graph-density-capacity-audit.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-db", action="append", type=Path, required=True, help="Existing SQLite state DB; repeat for multiple datasets.")
    parser.add_argument("--browser-artifact", action="append", type=Path, default=[], help="Existing graph browser JSON artifact; treated as seed/fixture evidence.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    missing = [str(path) for path in [*args.state_db, *args.browser_artifact] if not path.is_file()]
    if missing:
        parser.error(f"input files not found: {', '.join(missing)}")
    report = build_density_capacity_audit(args.state_db, browser_artifacts=args.browser_artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] != "no_subjects" else 1


if __name__ == "__main__":
    raise SystemExit(main())
