from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dynamic_allocation.application import DynamicAllocationApplication
from app.dynamic_allocation.data.public_pipeline import PublicDataPipeline


def run(
    *,
    as_of: datetime,
    market_start: date,
    persist_decision: bool,
    allow_partial: bool,
    application: DynamicAllocationApplication | None = None,
    pipeline: PublicDataPipeline | None = None,
) -> dict[str, Any]:
    app = application or DynamicAllocationApplication()
    worker = pipeline or PublicDataPipeline(app.config)
    collected, upsert = worker.ingest(app.observations, as_of=as_of, market_start=market_start)
    evaluation_as_of = max(as_of, datetime.combine(as_of.date(), datetime.min.time(), timezone.utc))
    evaluation = app.evaluate({"as_of": evaluation_as_of.isoformat()}, persist=persist_decision)
    payload = {
        "status": "ready" if evaluation["ready"] else "incomplete",
        "as_of": evaluation_as_of.isoformat(),
        "pipeline": collected.summary(),
        "upsert": {
            "received": upsert.received,
            "inserted": upsert.inserted,
            "duplicates": upsert.duplicates,
            "conflicts": upsert.conflicts,
        },
        "data_health": evaluation["data_health"],
        "decision": {
            "ready": evaluation["ready"],
            "decision_id": evaluation.get("decision_id"),
            "market_regime": evaluation.get("market_regime"),
            "target_equity_allocation": evaluation.get("target_equity_allocation"),
            "allocations": evaluation.get("allocations", {}),
            "explanation": evaluation.get("explanation"),
            "warnings": evaluation.get("warnings", []),
            "paper_only": True,
            "live_execution_allowed": False,
            "broker_connected": False,
        },
    }
    if not allow_partial and (collected.missing_series or not evaluation["ready"] or upsert.conflicts):
        raise RuntimeError(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill governed public inputs for paper-only dynamic allocation")
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    parser.add_argument("--market-start", default="2000-01-01")
    parser.add_argument("--persist-decision", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        parser.error("--as-of must include a timezone")
    try:
        payload = run(
            as_of=as_of,
            market_start=date.fromisoformat(args.market_start),
            persist_decision=args.persist_decision,
            allow_partial=args.allow_partial,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
