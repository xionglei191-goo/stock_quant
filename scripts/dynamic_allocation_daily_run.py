#!/usr/bin/env python3
"""Run one governed, local-only dynamic-allocation paper operation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.dynamic_allocation.application import DynamicAllocationApplication  # noqa: E402
from app.dynamic_allocation.data.public_pipeline import PublicDataPipeline  # noqa: E402
from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository, build_paper_snapshot  # noqa: E402


PRODUCER = "scripts/dynamic_allocation_daily_run.py"


class DailyRunGateError(RuntimeError):
    """Strict paper-operation failure with non-sensitive health details."""

    def __init__(self, details: dict[str, Any]) -> None:
        super().__init__("daily paper run failed strict data, conflict, or decision readiness gates")
        self.details = details


def run_daily(
    *,
    as_of: datetime,
    market_start: date,
    execute: bool,
    ledger_path: str | Path | None = None,
    application: DynamicAllocationApplication | None = None,
    pipeline: PublicDataPipeline | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    app = application or DynamicAllocationApplication()
    previous_items = app.history({"limit": 1}).get("items", [])
    previous = previous_items[0] if previous_items else None
    refresh: dict[str, Any]
    if execute:
        worker = pipeline or PublicDataPipeline(app.config)
        collected, upsert = worker.ingest(app.observations, as_of=as_of, market_start=market_start)
        refresh = {
            "pipeline": collected.summary(),
            "upsert": asdict(upsert),
        }
    else:
        refresh = {
            "pipeline": {"status": "not_run", "reason": "preview mode is read-only"},
            "upsert": {"received": 0, "inserted": 0, "duplicates": 0, "conflicts": 0},
        }

    evaluation = app.evaluate({"as_of": as_of.isoformat()}, persist=execute)
    if execute:
        missing = refresh["pipeline"].get("missing_series", [])
        errors = refresh["pipeline"].get("source_errors", {})
        if missing or errors or refresh["upsert"]["conflicts"] or not evaluation.get("ready"):
            raise DailyRunGateError(
                {
                    "missing_series": sorted(str(item) for item in missing),
                    "source_error_series": sorted(str(item) for item in errors),
                    "insert_conflicts": int(refresh["upsert"]["conflicts"]),
                    "decision_ready": bool(evaluation.get("ready")),
                }
            )

    append: dict[str, Any] = {"appended": False, "record_hash": None, "ledger_records": 0}
    if execute:
        if ledger_path is None:
            raise ValueError("ledger_path is required in execute mode")
        ledger = JsonlPaperSnapshotRepository(ledger_path)
        snapshot = build_paper_snapshot(evaluation["paper_snapshot"])
        result = ledger.append(snapshot)
        append = {
            "appended": result.appended,
            "record_hash": result.record_hash,
            "output_path": result.output_path,
            "ledger_records": len(ledger.replay()),
        }

    previous_target = previous.get("target_equity_allocation") if isinstance(previous, dict) else None
    current_target = evaluation.get("target_equity_allocation")
    allocation_change = None
    if previous_target is not None and current_target is not None:
        allocation_change = round(float(current_target) - float(previous_target), 10)
    health = evaluation.get("data_health", {})
    health_series = health.get("series", []) if isinstance(health, dict) else []
    fresh_count = sum(item.get("status") == "fresh" for item in health_series if isinstance(item, dict))
    factors = evaluation.get("factors", [])
    ready_factors = sum(bool(item.get("ready")) for item in factors if isinstance(item, dict))
    kelly_input = dict(evaluation.get("kelly_input", {}))
    kelly_source_ids = kelly_input.pop("source_observation_ids", [])
    kelly_input["source_observation_count"] = len(kelly_source_ids)

    return {
        "status": "completed" if execute else "preview",
        "mode": "execute" if execute else "read_only_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": PRODUCER,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "as_of": evaluation.get("as_of", as_of.isoformat()),
        "refresh": refresh,
        "decision": {
            "ready": evaluation.get("ready"),
            "decision_id": evaluation.get("decision_id"),
            "market_regime": evaluation.get("market_regime"),
            "target_equity_allocation": current_target,
            "previous_target_equity_allocation": previous_target,
            "allocation_change": allocation_change,
            "allocations": evaluation.get("allocations", {}),
            "caps": evaluation.get("caps", {}),
            "kelly_input": kelly_input,
            "warnings": evaluation.get("warnings", []),
            "explanation": evaluation.get("explanation"),
        },
        "auditability": {
            "factor_count": len(factors),
            "ready_factor_count": ready_factors,
            "configured_series_count": len(health_series),
            "fresh_series_count": fresh_count,
            "source_observation_count": len(evaluation.get("source_observation_ids", [])),
            "config_hash": evaluation.get("config_hash"),
            "model_version": evaluation.get("model_version"),
            "binding_limit": evaluation.get("caps", {}).get("binding_limit"),
            "paper_snapshot_persisted": execute,
        },
        "paper_ledger": append,
        "efficacy_evidence": {
            "status": "accumulating",
            "minimum_observation_months": 6,
            "financial_benefit_claimed": False,
            "note": "This run proves repeatable governed decisions and risk controls; return and drawdown benefit require a real paper observation window.",
        },
        "runtime_seconds": round(time.monotonic() - started, 3),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--as-of", default=datetime.now(timezone.utc).isoformat())
    result.add_argument("--market-start", default="2000-01-01")
    result.add_argument("--execute", action="store_true", help="refresh data, persist the decision, and append the paper ledger")
    result.add_argument("--ledger", help="required with --execute; append-only local JSONL ledger")
    result.add_argument("--output", help="required with --execute; local-only JSON report")
    result.add_argument("--history-dir", help="optional with --execute; archive one JSON report per as-of timestamp")
    return result


def _write_report(path: str | Path, rendered: str) -> None:
    output = Path(path)
    if output.exists() and output.is_symlink():
        raise ValueError("report output must not be a symbolic link")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")


def _failure_report(as_of: datetime, exc: Exception) -> dict[str, Any]:
    details = exc.details if isinstance(exc, DailyRunGateError) else {}
    return {
        "status": "failed",
        "mode": "execute",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": PRODUCER,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "as_of": as_of.isoformat(),
        "failure": {"reason": str(exc), **details},
        "efficacy_evidence": {
            "status": "not_evaluated",
            "financial_benefit_claimed": False,
        },
    }


def _archive_path(history_dir: str | Path, as_of: datetime) -> Path:
    stamp = as_of.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(history_dir) / f"daily-run-{stamp}.json"


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.execute and (not args.ledger or not args.output):
        parser().error("--ledger and --output are required with --execute")
    if not args.execute and (args.ledger or args.output or args.history_dir):
        parser().error("--ledger, --output, and --history-dir are only accepted with --execute")
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        parser().error("--as-of must include a timezone")
    try:
        report = run_daily(
            as_of=as_of.astimezone(timezone.utc),
            market_start=date.fromisoformat(args.market_start),
            execute=args.execute,
            ledger_path=args.ledger,
        )
    except RuntimeError as exc:
        failure = _failure_report(as_of.astimezone(timezone.utc), exc)
        rendered = json.dumps(failure, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            _write_report(args.output, rendered)
        if args.history_dir:
            _write_report(_archive_path(args.history_dir, as_of), rendered)
        print(rendered, file=sys.stderr)
        return 1
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _write_report(args.output, rendered)
    if args.history_dir:
        _write_report(_archive_path(args.history_dir, as_of), rendered)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
