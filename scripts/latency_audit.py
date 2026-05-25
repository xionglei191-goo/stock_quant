from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.daily_data_update_pipeline import DEFAULT_BASE_URL, _latency_audit


def run_latency_audit(*, base_url: str, output: str | Path, max_ms: float, timeout: float) -> dict[str, Any]:
    return _latency_audit(
        base_url,
        output=Path(output),
        threshold_ms=max_ms,
        timeout=timeout,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local production HTTP latency smoke probes.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", default="artifacts/daily-update-local/latency-audit-smoke.json")
    parser.add_argument("--max-ms", "--threshold-ms", dest="max_ms", type=float, default=7000.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    result = run_latency_audit(
        base_url=args.base_url,
        output=args.output,
        max_ms=args.max_ms,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
