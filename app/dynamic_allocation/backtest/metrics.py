"""Dependency-light portfolio performance metrics."""

from __future__ import annotations

from datetime import date, datetime
import math
import statistics
from typing import Sequence


def performance_metrics(
    returns: Sequence[float],
    *,
    dates: Sequence[date | datetime] | None = None,
    turnover: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    values = [float(value) for value in returns]
    if not values:
        return {key: 0.0 for key in ("cagr", "annual_return", "maximum_drawdown", "sharpe", "sortino", "calmar", "win_rate", "turnover")}
    equity = 1.0
    curve: list[float] = []
    for value in values:
        equity *= 1.0 + value
        curve.append(equity)
    if dates and len(dates) == len(values) and len(dates) > 1:
        elapsed_days = max(1, (dates[-1] - dates[0]).days)
        years = max(elapsed_days / 365.25, 1 / periods_per_year)
    else:
        years = len(values) / periods_per_year
    cagr = equity ** (1 / years) - 1 if equity > 0 else -1.0
    annual_return = statistics.fmean(values) * periods_per_year
    volatility = statistics.stdev(values) * math.sqrt(periods_per_year) if len(values) > 1 else 0.0
    sharpe = annual_return / volatility if volatility > 0 else 0.0
    downside = [min(value, 0.0) for value in values]
    downside_dev = math.sqrt(statistics.fmean(value * value for value in downside)) * math.sqrt(periods_per_year)
    sortino = annual_return / downside_dev if downside_dev > 0 else 0.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        maximum_drawdown = min(maximum_drawdown, value / peak - 1.0)
    calmar = cagr / abs(maximum_drawdown) if maximum_drawdown < 0 else 0.0
    return {
        "cagr": round(cagr, 10),
        "annual_return": round(annual_return, 10),
        "maximum_drawdown": round(maximum_drawdown, 10),
        "sharpe": round(sharpe, 10),
        "sortino": round(sortino, 10),
        "calmar": round(calmar, 10),
        "win_rate": round(sum(value > 0 for value in values) / len(values), 10),
        "turnover": round(float(turnover), 10),
    }
