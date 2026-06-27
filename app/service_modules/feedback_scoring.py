from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable

from app.models import AnalysisConclusion, MarketDataPoint, SimulationFeedback
from app.utils import parse_datetime, utcnow


@dataclass(frozen=True)
class FeedbackScore:
    performance: dict[str, Any]
    validation: dict[str, Any]
    review_result: dict[str, Any]
    result_row: dict[str, Any]


def _close(point: MarketDataPoint) -> float:
    return float(point.close or point.adjusted_close or 0.0)


def _date(point: MarketDataPoint) -> date:
    return date.fromisoformat(str(point.as_of_date))


def _round(value: float) -> float:
    return round(value, 6)


def _window(points: Iterable[MarketDataPoint], *, start_at: datetime, end_at: datetime | None = None) -> list[MarketDataPoint]:
    start_date = start_at.date()
    end_date = end_at.date() if end_at else None
    rows = []
    for point in points:
        try:
            point_date = _date(point)
        except ValueError:
            continue
        if point_date < start_date:
            continue
        if end_date and point_date > end_date:
            continue
        rows.append(point)
    rows.sort(key=lambda item: (_date(item), item.data_id))
    return rows


def _sorted_points(points: Iterable[MarketDataPoint]) -> list[MarketDataPoint]:
    rows = []
    for point in points:
        try:
            _date(point)
        except ValueError:
            continue
        rows.append(point)
    rows.sort(key=lambda item: (_date(item), item.data_id))
    return rows


def _max_drawdown(points: list[MarketDataPoint], *, entry_price: float) -> float:
    peak = entry_price
    max_drawdown = 0.0
    for point in points:
        price = _close(point)
        if price <= 0:
            continue
        peak = max(peak, price)
        if peak > 0:
            max_drawdown = min(max_drawdown, (price - peak) / peak)
    return max_drawdown


def _realization_status(action: str, absolute_return: float, relative_return: float | None) -> str:
    normalized = action.lower()
    if normalized in {"avoid", "reduce", "sell", "short"}:
        score = -absolute_return
    elif normalized in {"buy", "increase", "overweight", "long"}:
        score = absolute_return
    else:
        score = relative_return if relative_return is not None else absolute_return
    if score >= 0.03:
        return "realized"
    if score <= -0.03:
        return "missed"
    return "mixed"


def _error_attribution(*, status: str, absolute_return: float, relative_return: float | None, window_points: int, benchmark_points: int) -> str:
    if window_points <= 1:
        return "market_data_gap"
    if relative_return is None and benchmark_points == 0:
        return "benchmark_gap"
    if status == "missed" and relative_return is not None and relative_return < -0.03:
        return "thesis_wrong_or_timing_lag"
    if status == "mixed":
        return "signal_inconclusive"
    return "no_material_error_identified"


def score_simulation_feedback(
    feedback: SimulationFeedback,
    conclusion: AnalysisConclusion | None,
    security_points: Iterable[MarketDataPoint],
    *,
    benchmark_points: Iterable[MarketDataPoint] = (),
) -> FeedbackScore | None:
    if not feedback.paper_only or feedback.live_execution_allowed or feedback.broker_connected:
        raise ValueError("simulation feedback scoring only supports paper-only feedback")
    start_at = parse_datetime(feedback.start_at)
    end_at = parse_datetime(feedback.end_at) if feedback.end_at else None
    all_points = _sorted_points(security_points)
    points = _window(all_points, start_at=start_at, end_at=end_at)
    window_fallback_used = False
    if not points and all_points:
        points = [all_points[-1]]
        window_fallback_used = True
    if not points:
        return None
    latest = points[-1]
    latest_price = _close(latest)
    entry_price = float(feedback.entry_price or 0.0) or _close(points[0])
    if entry_price <= 0 or latest_price <= 0:
        return None
    event_window_return = (latest_price - entry_price) / entry_price
    benchmark_all = _sorted_points(benchmark_points)
    benchmark_rows = _window(benchmark_all, start_at=start_at, end_at=end_at)
    if not benchmark_rows and benchmark_all and window_fallback_used:
        benchmark_rows = [benchmark_all[-1]]
    benchmark_return: float | None = None
    relative_return: float | None = None
    if len(benchmark_rows) >= 2:
        benchmark_entry = _close(benchmark_rows[0])
        benchmark_latest = _close(benchmark_rows[-1])
        if benchmark_entry > 0 and benchmark_latest > 0:
            benchmark_return = (benchmark_latest - benchmark_entry) / benchmark_entry
            relative_return = event_window_return - benchmark_return
    realization_status = _realization_status(feedback.simulated_action, event_window_return, relative_return)
    drawdown = _max_drawdown(points, entry_price=entry_price)
    attribution = _error_attribution(
        status=realization_status,
        absolute_return=event_window_return,
        relative_return=relative_return,
        window_points=1 if window_fallback_used else len(points),
        benchmark_points=len(benchmark_rows),
    )
    checked_at = utcnow().isoformat()
    holding_days = max(0, (_date(latest) - start_at.date()).days)
    performance = dict(feedback.performance)
    performance.update(
        {
            "status": "measured",
            "realization_status": realization_status,
            "entry_price": _round(entry_price),
            "latest_price": _round(latest_price),
            "latest_date": latest.as_of_date,
            "latest_market_data_id": latest.data_id,
            "return_abs": _round(latest_price - entry_price),
            "return_pct": _round(event_window_return),
            "event_window_return": _round(event_window_return),
            "benchmark_return": _round(benchmark_return) if benchmark_return is not None else None,
            "relative_benchmark_return": _round(relative_return) if relative_return is not None else None,
            "max_drawdown": _round(drawdown),
            "holding_days": holding_days,
            "window_points": len(points),
            "window_fallback_used": window_fallback_used,
            "realization_checked_at": checked_at,
            "paper_only": True,
        }
    )
    validation = dict(feedback.validation)
    validation.update(
        {
            "performance_measured": True,
            "paper_only": True,
            "live_execution_allowed": False,
            "broker_connected": False,
            "market_data_source_id": latest.source_id,
            "metric": "event_window_close_vs_entry_price",
            "benchmark_security_id": feedback.benchmark_security_id,
            "benchmark_points": len(benchmark_rows),
            "window_fallback_used": window_fallback_used,
        }
    )
    manual_score = dict(feedback.review_result).get("manual_review_score")
    review_result = dict(feedback.review_result)
    review_result.update(
        {
            "status": "pending_review" if manual_score is None else "reviewed",
            "realization_status": realization_status,
            "manual_review_score": manual_score,
            "prediction_error_attribution": attribution,
            "summary": f"{realization_status}: event window return {_round(event_window_return)}"
            + (f", relative benchmark {_round(relative_return)}" if relative_return is not None else ", benchmark unavailable"),
            "next_action": "人工复盘评分并记录是否调整观察假设" if manual_score is None else "保留评分并继续观察",
            "requires_human_review": manual_score is None,
            "conclusion_title": conclusion.title if conclusion else "",
        }
    )
    result_row = {
        "simulation_feedback_id": feedback.simulation_feedback_id,
        "analysis_conclusion_id": feedback.analysis_conclusion_id,
        "issuer_id": feedback.issuer_id,
        "security_id": feedback.security_id,
        "status": "scored",
        "realization_status": realization_status,
        "entry_price": _round(entry_price),
        "latest_price": _round(latest_price),
        "latest_date": latest.as_of_date,
        "event_window_return": _round(event_window_return),
        "relative_benchmark_return": _round(relative_return) if relative_return is not None else None,
        "max_drawdown": _round(drawdown),
        "window_fallback_used": window_fallback_used,
        "prediction_error_attribution": attribution,
        "manual_review_score": manual_score,
        "paper_only": True,
        "live_execution_allowed": False,
    }
    return FeedbackScore(performance=performance, validation=validation, review_result=review_result, result_row=result_row)
