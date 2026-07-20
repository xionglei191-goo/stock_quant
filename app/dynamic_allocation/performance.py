"""Versioned, forward-only paper NAV and performance evidence contract."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .backtest.metrics import performance_metrics
from .paper import PaperDecisionSnapshot


SCHEMA_VERSION = "dynamic-allocation-paper-performance/v1"
METHODOLOGY_VERSION = "paper-nav-next-session-adjusted-close/v1"
ASSETS = ("SPY", "QQQ", "SGOV")
REVIEW_GATES = (3, 6, 12)
BOUNDARY = {
    "classification": "local-only",
    "acceptable_for_non_local_release_gate": False,
    "paper_only": True,
    "live_execution_allowed": False,
    "broker_connected": False,
    "order_execution_allowed": False,
}


def load_performance_input(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("performance input must be an existing non-symlink file")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("performance input must be a JSON object")
    payload["_source_path"] = str(source)
    return payload


def build_performance_evidence(
    snapshots: Sequence[PaperDecisionSnapshot],
    payload: Mapping[str, Any],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    """Calculate forward paper NAV from governed common-session price evidence."""

    calculation_at = _aware(as_of, "as_of")
    _assert_boundary(payload)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"performance input schema_version must be {SCHEMA_VERSION}")
    if payload.get("methodology_version") != METHODOLOGY_VERSION:
        raise ValueError(f"performance methodology_version must be {METHODOLOGY_VERSION}")
    started_at = _aware(payload.get("collection_started_at"), "collection_started_at")
    if started_at > calculation_at:
        raise ValueError("collection_started_at cannot be in the future")

    initial_nav = _positive(payload.get("initial_nav", 1.0), "initial_nav")
    transaction_cost_bps = _non_negative(payload.get("transaction_cost_bps", 5.0), "transaction_cost_bps")
    advisory_fee_bps = _non_negative(payload.get("annual_advisory_fee_bps", 0.0), "annual_advisory_fee_bps")
    calendar = _calendar(payload.get("calendar"), calculation_at)
    sessions, source_catalog = _sessions(payload.get("sessions"), calculation_at)
    ordered_snapshots = sorted(snapshots, key=lambda item: _aware(item.evaluated_at, "snapshot evaluated_at"))
    first_decision_at = _aware(ordered_snapshots[0].evaluated_at, "snapshot evaluated_at") if ordered_snapshots else None
    if first_decision_at and started_at > first_decision_at:
        raise ValueError("forward paper collection must start no later than the first decision")
    if first_decision_at and first_decision_at - started_at > timedelta(days=7):
        raise ValueError("forward paper collection cannot predate the first decision by more than seven days")
    if any(item["available_at"] < started_at for item in sessions):
        raise ValueError("performance sessions cannot predate collection_started_at")

    missing_weekdays = _missing_weekdays(sessions)
    missing_open_sessions = [item["date"] for item in sessions if item["market_status"] == "open" and not item["complete"]]
    future_sessions = [item["date"] for item in sessions if item["available_at"] > calculation_at]
    complete_open = [item for item in sessions if item["market_status"] == "open" and item["complete"] and item["available_at"] <= calculation_at]
    incomplete_open_dates = {item["date"] for item in sessions if item["market_status"] == "open" and not item["complete"]}

    nav = initial_nav
    peak = initial_nav
    current_allocation = {"SPY": 0.0, "QQQ": 0.0, "SGOV": 1.0}
    strategy_returns: list[float] = []
    spy_returns: list[float] = []
    balanced_returns: list[float] = []
    metric_dates: list[date] = []
    nav_points: list[dict[str, Any]] = []
    total_turnover = 0.0
    intervals_without_signal = 0
    previous: dict[str, Any] | None = None

    for session in complete_open:
        if previous is None:
            previous = session
            continue
        if _has_coverage_gap_between(
            previous["date"], session["date"], incomplete_open_dates | set(missing_weekdays)
        ):
            previous = session
            continue
        signal = _latest_signal(ordered_snapshots, previous["available_at"])
        if signal is None:
            if first_decision_at is not None and previous["available_at"] >= first_decision_at:
                intervals_without_signal += 1
            previous = session
            continue
        allocation = dict(signal.allocation)
        turnover = sum(abs(allocation[asset] - current_allocation[asset]) for asset in ASSETS) / 2.0
        returns = {
            asset: session["prices"][asset]["adjusted_close"] / previous["prices"][asset]["adjusted_close"] - 1.0
            for asset in ASSETS
        }
        gross = sum(allocation[asset] * returns[asset] for asset in ASSETS)
        transaction_cost = turnover * transaction_cost_bps / 10_000.0
        advisory_fee = advisory_fee_bps / 10_000.0 / 252.0
        net = gross - transaction_cost - advisory_fee
        if net <= -1:
            raise ValueError("paper NAV return cannot be -100% or lower")
        nav *= 1.0 + net
        peak = max(peak, nav)
        total_turnover += turnover
        strategy_returns.append(net)
        spy_returns.append(returns["SPY"])
        balanced_returns.append(0.60 * returns["SPY"] + 0.40 * returns["SGOV"])
        metric_dates.append(session["date"])
        nav_points.append(
            {
                "date": session["date"].isoformat(),
                "period_start_date": previous["date"].isoformat(),
                "signal_run_id": signal.run_id,
                "signal_evaluated_at": signal.evaluated_at,
                "allocation": allocation,
                "asset_returns": {key: round(value, 10) for key, value in returns.items()},
                "benchmark_returns": {
                    "spy_buy_hold": round(returns["SPY"], 10),
                    "spy_sgov_60_40": round(0.60 * returns["SPY"] + 0.40 * returns["SGOV"], 10),
                },
                "gross_return": round(gross, 10),
                "turnover": round(turnover, 10),
                "transaction_cost": round(transaction_cost, 10),
                "advisory_fee": round(advisory_fee, 10),
                "net_return": round(net, 10),
                "nav": round(nav, 10),
                "drawdown": round(nav / peak - 1.0, 10),
                "price_observation_ids": {
                    asset: {
                        "period_start": previous["prices"][asset]["observation_id"],
                        "period_end": session["prices"][asset]["observation_id"],
                    }
                    for asset in ASSETS
                },
            }
        )
        current_allocation = allocation
        previous = session

    reviews = _reviews(payload.get("reviews", []), calculation_at)
    if first_decision_at:
        for review in reviews:
            if review["status"] == "completed":
                due_at = _add_months(first_decision_at, int(review["gate_months"]))
                if _aware(review["reviewed_at"], "reviewed_at") < due_at:
                    raise ValueError("completed review cannot precede its elapsed gate")
    evidence_start = complete_open[0]["available_at"] if complete_open else None
    evidence_end = complete_open[-1]["available_at"] if complete_open else None
    coverage_complete = not missing_weekdays and not missing_open_sessions and not future_sessions
    evidence_ready = bool(
        ordered_snapshots
        and strategy_returns
        and coverage_complete
        and intervals_without_signal == 0
        and evidence_start is not None
        and first_decision_at is not None
        and evidence_start <= first_decision_at
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        **BOUNDARY,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of": _iso(calculation_at),
        "input_source_path": payload.get("_source_path"),
        "methodology": {
            "evidence_type": "forward_observed_paper_only",
            "signal_effective_timing": "latest decision available by prior common-session price availability; earns only the next complete session return",
            "price_field": "adjusted_close",
            "cash_asset": "SGOV",
            "cash_handling": "SGOV adjusted-close total return; no zero-return cash fill",
            "rebalance_timing": "next_complete_common_session",
            "turnover_formula": "0.5 * sum(abs(new_weight - old_weight))",
            "transaction_cost_bps": transaction_cost_bps,
            "annual_advisory_fee_bps": advisory_fee_bps,
            "etf_expense_handling": "embedded in adjusted-close returns; not deducted again",
            "missing_session_policy": "closed sessions are explicit; missing weekdays or incomplete open sessions block review and no return crosses an incomplete open session",
            "benchmark_policy": "SPY buy-and-hold and 60% SPY / 40% SGOV, aligned to evaluated strategy intervals",
            "initial_nav": initial_nav,
        },
        "calendar": calendar,
        "coverage": {
            "collection_started_at": _iso(started_at),
            "evidence_start_at": _iso(evidence_start),
            "evidence_end_at": _iso(evidence_end),
            "declared_session_count": len(sessions),
            "complete_open_session_count": len(complete_open),
            "evaluated_interval_count": len(strategy_returns),
            "intervals_without_prior_signal": intervals_without_signal,
            "missing_weekdays": [item.isoformat() for item in missing_weekdays],
            "incomplete_open_sessions": [item.isoformat() for item in missing_open_sessions],
            "future_sessions": [item.isoformat() for item in future_sessions],
            "complete": coverage_complete,
        },
        "source_catalog": source_catalog,
        "paper_nav": {
            "initial_nav": initial_nav,
            "latest_nav": round(nav, 10),
            "points": nav_points,
            "metrics": performance_metrics(strategy_returns, dates=metric_dates, turnover=total_turnover),
        },
        "benchmarks": {
            "spy_buy_hold": performance_metrics(spy_returns, dates=metric_dates),
            "spy_sgov_60_40": performance_metrics(balanced_returns, dates=metric_dates),
        },
        "reviews": reviews,
        "performance_evidence_ready": evidence_ready,
        "efficacy_proven": False,
        "financial_benefit_claimed": False,
        "limitations": [
            "This forward paper record is not a historical walk-forward backtest.",
            "A complete effective human review is required before any gate can state efficacy_proven=true.",
        ],
    }


def _sessions(value: Any, as_of: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("sessions must be a non-empty array")
    sessions: list[dict[str, Any]] = []
    sources: dict[tuple[str, str], dict[str, Any]] = {}
    seen_dates: set[date] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("each session must be an object")
        session_date = date.fromisoformat(str(raw.get("date")))
        if session_date in seen_dates:
            raise ValueError(f"duplicate performance session date: {session_date}")
        status = str(raw.get("market_status", ""))
        if status not in {"open", "closed"}:
            raise ValueError("market_status must be open or closed")
        close_at = _aware(raw.get("close_at"), f"session {session_date} close_at")
        available_at = _aware(raw.get("available_at"), f"session {session_date} available_at")
        if close_at.date() != session_date or available_at < close_at:
            raise ValueError(f"session {session_date} has invalid close/availability timing")
        if available_at > as_of:
            raise ValueError(f"session {session_date} is unavailable as of calculation time")
        complete = status == "closed"
        prices: dict[str, dict[str, Any]] = {}
        raw_prices = raw.get("prices", {})
        if not isinstance(raw_prices, Mapping):
            raise ValueError("session prices must be an object")
        if status == "open":
            for asset in ASSETS:
                price = raw_prices.get(asset)
                if not isinstance(price, Mapping):
                    continue
                adjusted_close = _positive(price.get("adjusted_close"), f"{session_date} {asset} adjusted_close")
                observation_id = str(price.get("observation_id", "")).strip()
                source_id = str(price.get("source_id", "")).strip()
                source_uri = str(price.get("source_uri", "")).strip()
                rights = price.get("rights_tag")
                if not observation_id or not source_id or not source_uri or not isinstance(rights, Mapping):
                    raise ValueError(f"{session_date} {asset} requires observation and source lineage")
                if rights.get("paper_performance_eligible") is not True or rights.get("automated_use_allowed") is not True:
                    raise ValueError(f"{session_date} {asset} is not eligible for paper performance")
                prices[asset] = {
                    "adjusted_close": adjusted_close,
                    "observation_id": observation_id,
                    "source_id": source_id,
                    "source_uri": source_uri,
                }
                sources[(source_id, source_uri)] = {
                    "source_id": source_id,
                    "source_uri": source_uri,
                    "paper_performance_eligible": True,
                    "automated_use_allowed": True,
                    "backtest_eligible": rights.get("backtest_eligible"),
                    "usage_scope": "forward_paper_only",
                }
            complete = available_at <= as_of and set(prices) == set(ASSETS)
        sessions.append(
            {
                "date": session_date,
                "market_status": status,
                "close_at": close_at,
                "available_at": available_at,
                "prices": prices,
                "complete": complete,
            }
        )
        seen_dates.add(session_date)
    if [item["date"] for item in sessions] != sorted(item["date"] for item in sessions):
        raise ValueError("sessions must have unique ascending dates")
    return sessions, list(sources.values())


def _calendar(value: Any, as_of: datetime) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("calendar lineage is required")
    result = {
        "calendar_id": str(value.get("calendar_id", "")).strip(),
        "version": str(value.get("version", "")).strip(),
        "source_id": str(value.get("source_id", "")).strip(),
        "source_uri": str(value.get("source_uri", "")).strip(),
        "available_at": _iso(_aware(value.get("available_at"), "calendar available_at")),
    }
    if not all(result.values()) or _aware(result["available_at"], "calendar available_at") > as_of:
        raise ValueError("calendar requires available, versioned source lineage")
    return result


def _reviews(value: Any, as_of: datetime) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("reviews must be an array")
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("each review must be an object")
        gate = int(raw.get("gate_months", 0))
        status = str(raw.get("status", ""))
        outcome = raw.get("outcome")
        if gate not in REVIEW_GATES or gate in seen:
            raise ValueError("reviews require unique 3, 6, or 12 month gates")
        if status not in {"not_started", "pending", "completed"}:
            raise ValueError("review status is invalid")
        normalized = {"gate_months": gate, "status": status, "outcome": outcome}
        if status == "completed":
            if outcome not in {"effective", "not_effective", "inconclusive"}:
                raise ValueError("completed review requires a governed outcome")
            reviewer = str(raw.get("reviewer", "")).strip()
            rationale = str(raw.get("rationale", "")).strip()
            reviewed_at = _aware(raw.get("reviewed_at"), "reviewed_at")
            if not reviewer or not rationale or reviewed_at > as_of:
                raise ValueError("completed review requires reviewer, rationale, and non-future reviewed_at")
            normalized.update({"reviewer": reviewer, "rationale": rationale, "reviewed_at": _iso(reviewed_at)})
        result.append(normalized)
        seen.add(gate)
    return sorted(result, key=lambda item: item["gate_months"])


def _latest_signal(snapshots: Sequence[PaperDecisionSnapshot], available_at: datetime) -> PaperDecisionSnapshot | None:
    eligible = [item for item in snapshots if _aware(item.evaluated_at, "snapshot evaluated_at") <= available_at]
    return eligible[-1] if eligible else None


def _missing_weekdays(sessions: Sequence[Mapping[str, Any]]) -> list[date]:
    dates = {item["date"] for item in sessions}
    current = min(dates)
    end = max(dates)
    missing: list[date] = []
    while current <= end:
        if current.weekday() < 5 and current not in dates:
            missing.append(current)
        current += timedelta(days=1)
    return missing


def _has_coverage_gap_between(start: date, end: date, gaps: set[date]) -> bool:
    return any(start < item <= end for item in gaps)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _assert_boundary(payload: Mapping[str, Any]) -> None:
    for key, expected in BOUNDARY.items():
        if payload.get(key) != expected:
            raise ValueError(f"performance input violates {key} boundary")


def _aware(value: Any, name: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _positive(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _non_negative(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None
