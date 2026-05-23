from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run resumable SEC companyfacts batches for US financial summaries.")
    parser.add_argument("--batches", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--min-market-cap", type=float, default=1_000_000_000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sleep-seconds", type=float, default=0.03)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/us-companyfacts-batches"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for index in range(1, args.batches + 1):
        artifact = args.output_dir / f"batch-{index:03d}.json"
        command = [
            sys.executable,
            "scripts/backfill_us_financials_sec_companyfacts.py",
            "--limit",
            str(args.batch_size),
            "--missing-only",
            "--min-market-cap",
            str(args.min_market_cap),
            "--workers",
            str(args.workers),
            "--sleep-seconds",
            str(args.sleep_seconds),
            "--artifact",
            str(artifact),
        ]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            summary = {
                "batch": index,
                "artifact": str(artifact),
                "returncode": completed.returncode,
                "output_tail": completed.stdout[-4000:],
            }
            summaries.append(summary)
            break
        data = json.loads(artifact.read_text(encoding="utf-8"))
        summaries.append({"batch": index, "artifact": str(artifact), "requested": data.get("requested"), "updated_rows": data.get("updated_rows"), "error_count": data.get("error_count"), "coverage": data.get("coverage")})
        if not data.get("requested") or not data.get("updated_rows"):
            break
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch_size": args.batch_size,
        "batches_requested": args.batches,
        "min_market_cap": args.min_market_cap,
        "summaries": summaries,
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not summaries or summaries[-1].get("returncode", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
