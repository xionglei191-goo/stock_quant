#!/usr/bin/env python3
"""End-to-end value case: analysis conclusion -> observation -> paper feedback -> market-data review.

This script proves the product's core value claim once, end to end, with real
local market data: it records an analysis conclusion, an observation item, and a
paper-only simulation feedback, then runs realization scoring against real
TongDaXin EOD prices and writes an artifact.

The point is not data coverage. It is that the system can *falsify a wrong
analytical judgement* using real prices. The default demo records a 2023 bullish
call on Ping An Bank (sz000001); the local price series then scores it as
``missed`` with the real interval return.

Everything is paper-only: the SimulationFeedback model hard-locks
``paper_only=True`` / ``live_execution_allowed=False`` / ``broker_connected=False``.
No broker, no live execution, no order placement.

Batch mode: pass ``--symbols sz000001,sh600519,...`` to run the full loop
over several tickers in one shared store, deriving issuer/security ids per
ticker. The artifact then carries a per-symbol list plus a rollup that
counts realized/missed/mixed verdicts across the watchlist -- turning the
single value case into a repeatable analysis-effectiveness batch.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- module import bootstrap ---
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import SystemService  # noqa: E402
from app.store import SQLiteStore  # noqa: E402
from app.tdx_market_data import TDXVipdocAdapter  # noqa: E402


SYMBOL_PATTERN = re.compile(r"^(sh|sz)\d{6}$")
ARTIFACT_PRODUCER = "scripts/value_case_analysis_feedback_loop.py"


def _artifact_metadata() -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "producer": ARTIFACT_PRODUCER,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
    }


def parse_tdx_symbols(value: str) -> list[str]:
    """Normalize, validate, and order-dedupe a comma-separated symbol list."""
    if not value.strip():
        raise ValueError("symbols_empty")
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_symbol in value.split(","):
        symbol = raw_symbol.strip().lower()
        if not symbol:
            raise ValueError("symbol_empty")
        if not SYMBOL_PATTERN.fullmatch(symbol):
            raise ValueError("symbol_invalid")
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def _build_service(db_path: str) -> SystemService:
    if not db_path:
        return SystemService()
    return SystemService(SQLiteStore(db_path))


def _import_market_data(
    service: SystemService,
    *,
    tdx_symbol: str,
    security_id: str,
    issuer_id: str,
    source_id: str,
    start_date: str,
    end_date: str,
    vipdoc_path: str,
) -> dict[str, Any]:
    """Register source + issuer + security and import real TDX EOD prices."""
    if source_id not in service.store.sources:
        service.register_source(
            {
                "source_id": source_id,
                "source_type": "public_market_data",
                "allowed_document_types": [],
                "provenance_ref": "local_tdx_vipdoc",
                "collection_method": "local_file",
                "usage_scope": "local_research_and_simulated_portfolio_only",
                "retention_policy": "local_only",
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="value-case",
        )
    if issuer_id not in service.store.issuers:
        service.register_issuer(
            {"issuer_id": issuer_id, "legal_name": issuer_id, "market": ["A"], "country": "CN"},
            actor="value-case",
        )
    if security_id not in service.store.securities:
        service.register_security(
            {
                "security_id": security_id,
                "issuer_id": issuer_id,
                "ticker": tdx_symbol[-6:],
                "exchange": "SSE" if tdx_symbol.startswith("sh") else "SZSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="value-case",
        )
    if vipdoc_path:
        service.tdx_vipdoc = TDXVipdocAdapter(path=vipdoc_path)
    return service.import_tdx_market_data(
        {
            "symbols": tdx_symbol[-6:],
            "security_map": {tdx_symbol[-6:]: security_id},
            "source_id": source_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": 10000,
        },
        actor="value-case",
    )


def run_value_case(
    *,
    service: SystemService | None = None,
    db_path: str = "",
    tdx_symbol: str,
    issuer_id: str,
    security_id: str,
    source_id: str,
    start_date: str,
    end_date: str,
    vipdoc_path: str,
    entry_hint: float,
) -> dict[str, Any]:
    if service is None:
        service = _build_service(db_path)
    import_summary = _import_market_data(
        service,
        tdx_symbol=tdx_symbol,
        security_id=security_id,
        issuer_id=issuer_id,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
        vipdoc_path=vipdoc_path,
    )
    points = service._market_points_for_security(security_id, limit=10000)
    if not points:
        return {
            "status": "failed",
            "reason": "no_market_data_after_import",
            "import_summary": import_summary,
        }
    entry_price = float(points[0].close)
    entry_date = str(points[0].as_of_date)

    conclusion_id = f"ac_valuecase_{security_id}"
    observation_id = f"obs_valuecase_{security_id}"
    feedback_id = f"sf_valuecase_{security_id}"

    if conclusion_id not in service.store.analysis_conclusions:
        service.create_analysis_conclusion(
            {
            "analysis_conclusion_id": conclusion_id,
            "issuer_id": issuer_id,
            "security_id": security_id,
            "title": f"{start_date} 看多 {tdx_symbol}",
            "conclusion": "基于当时判断看多，预期后续区间上涨。",
            "conclusion_type": "directional_call",
            "horizon": "medium",
            "forecasts": [f"预期 {security_id} 后续区间收益为正"],
            "confidence": 0.6,
            "status": "active",
            },
            actor="value-case",
        )
    if observation_id not in service.store.observation_items:
        service.register_observation_item(
            {
            "observation_id": observation_id,
            "issuer_id": issuer_id,
            "security_id": security_id,
            "title": f"跟踪 {tdx_symbol} 价格是否兑现看多假设",
            "observation_type": "price_realization",
            "related_conclusion_ids": [conclusion_id],
            "status": "open",
            },
            actor="value-case",
        )
    if feedback_id not in service.store.simulation_feedback:
        service.record_simulation_feedback(
            {
            "simulation_feedback_id": feedback_id,
            "analysis_conclusion_id": conclusion_id,
            "issuer_id": issuer_id,
            "security_id": security_id,
            "observation_id": observation_id,
            "feedback_type": "watch_only",
            "simulated_action": "watch",
            "start_at": entry_date,
            "entry_price": entry_price,
            },
            actor="value-case",
        )
    update = service.update_simulation_feedback_performance(
        {"simulation_feedback_id": feedback_id, "execute": True, "dry_run": False},
        actor="value-case",
    )
    feedback = service.store.simulation_feedback[feedback_id]
    return {
        "status": "passed",
        "usage_boundary": "paper_only_analysis_feedback_value_case_no_broker_no_live_execution",
        "paper_only": feedback.paper_only,
        "live_execution_allowed": feedback.live_execution_allowed,
        "broker_connected": feedback.broker_connected,
        "market_data": {
            "security_id": security_id,
            "point_count": len(points),
            "entry_date": entry_date,
            "entry_price": entry_price,
            "entry_hint": entry_hint,
        },
        "import_summary": {
            "created": import_summary.get("created_count", import_summary.get("source_rows")),
        },
        "conclusion_id": conclusion_id,
        "observation_id": observation_id,
        "feedback_id": feedback_id,
        "performance": feedback.performance,
        "validation": feedback.validation,
        "review_result": feedback.review_result,
        "update_summary": update,
    }


def _derive_ids(tdx_symbol: str) -> tuple[str, str, str, str]:
    """Derive (issuer_id, security_id, source_id, code6) from a tdx symbol."""
    code6 = tdx_symbol[-6:]
    issuer_id = f"issuer_valuecase_{tdx_symbol}"
    security_id = f"sec_valuecase_{tdx_symbol}"
    source_id = "public_eod_market_data"
    return issuer_id, security_id, source_id, code6


def run_value_case_batch(
    *,
    db_path: str,
    tdx_symbols: list[str],
    start_date: str,
    end_date: str,
    vipdoc_path: str,
) -> dict[str, Any]:
    """Run the end-to-end value case over several tickers in one shared store."""
    normalized_symbols = parse_tdx_symbols(",".join(tdx_symbols))
    service = _build_service(db_path)
    cases: list[dict[str, Any]] = []
    for tdx_symbol in normalized_symbols:
        issuer_id, security_id, source_id, _code6 = _derive_ids(tdx_symbol)
        try:
            case = run_value_case(
                service=service,
                tdx_symbol=tdx_symbol,
                issuer_id=issuer_id,
                security_id=security_id,
                source_id=source_id,
                start_date=start_date,
                end_date=end_date,
                vipdoc_path=vipdoc_path,
                entry_hint=0.0,
            )
        except Exception as exc:  # keep the batch resilient without leaking exception text
            case = {
                "status": "failed",
                "tdx_symbol": tdx_symbol,
                "reason": "value_case_execution_error",
                "error_type": type(exc).__name__,
            }
        case.setdefault("tdx_symbol", tdx_symbol)
        cases.append(case)

    rollup = {"realized": 0, "missed": 0, "mixed": 0, "pending": 0, "other": 0, "failed": 0}
    returns: list[float] = []
    for case in cases:
        if case.get("status") != "passed":
            rollup["failed"] += 1
            continue
        verdict = str((case.get("performance") or {}).get("realization_status", "")).strip().lower()
        if verdict in rollup:
            rollup[verdict] += 1
        else:
            rollup["other"] += 1
        ret = (case.get("performance") or {}).get("event_window_return")
        if isinstance(ret, (int, float)):
            returns.append(float(ret))
    passed = [c for c in cases if c.get("status") == "passed"]
    avg_return = round(sum(returns) / len(returns), 6) if returns else None
    if len(passed) == len(cases):
        status = "passed"
    elif passed:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        **_artifact_metadata(),
        "usage_boundary": "paper_only_analysis_feedback_value_case_no_broker_no_live_execution",
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "symbol_count": len(normalized_symbols),
        "passed_count": len(passed),
        "verdict_rollup": rollup,
        "average_event_window_return": avg_return,
        "interpretation": (
            "batch scored analysis calls against real local prices; "
            "verdict_rollup shows how many directional calls were realized vs missed"
        ),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="", help="SQLite state DB path for in-process mode (empty=in-memory)")
    parser.add_argument("--tdx-symbol", default="sz000001", help="e.g. sz000001 (Ping An Bank)")
    parser.add_argument("--symbols", default=None, help="Comma-separated tdx symbols for batch mode, e.g. sz000001,sh600519")
    parser.add_argument("--issuer-id", default="issuer_valuecase_pingan")
    parser.add_argument("--security-id", default="sec_valuecase_000001")
    parser.add_argument("--source-id", default="public_eod_market_data")
    parser.add_argument("--start-date", default="2023-01-01")
    parser.add_argument("--end-date", default="2099-12-31")
    parser.add_argument("--vipdoc-path", default=str(ROOT / "data" / "local" / "tdx" / "vipdoc"))
    parser.add_argument("--entry-hint", type=float, default=0.0, help="informational only")
    parser.add_argument("--output", default=str(ROOT / "artifacts" / "value-case" / "analysis-feedback-loop.json"))
    args = parser.parse_args()

    if args.symbols is not None:
        try:
            symbols = parse_tdx_symbols(args.symbols)
        except ValueError as exc:
            parser.error(str(exc))
        result = run_value_case_batch(
            db_path=args.db,
            tdx_symbols=symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            vipdoc_path=args.vipdoc_path,
        )
    else:
        result = run_value_case(
            db_path=args.db,
            tdx_symbol=args.tdx_symbol,
            issuer_id=args.issuer_id,
            security_id=args.security_id,
            source_id=args.source_id,
            start_date=args.start_date,
            end_date=args.end_date,
            vipdoc_path=args.vipdoc_path,
            entry_hint=args.entry_hint,
        )
        result = {**result, **_artifact_metadata()}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    summary = {"status": result.get("status"), "output": str(output_path)}
    if "verdict_rollup" in result:
        summary["verdict_rollup"] = result["verdict_rollup"]
        summary["passed_count"] = result.get("passed_count")
        summary["average_event_window_return"] = result.get("average_event_window_return")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
