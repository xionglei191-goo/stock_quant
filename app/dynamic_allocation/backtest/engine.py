"""No-lookahead paper backtest engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence

from ..portfolio.allocation import AllocationPolicy
from ..portfolio.rebalance import RebalancePolicy
from .benchmarks import benchmark_returns
from .metrics import performance_metrics


@dataclass(frozen=True)
class BacktestPoint:
    as_of: date | datetime
    return_value: float
    equity_curve: float
    requested_equity_weight: float | None
    applied_equity_weight: float
    signal_as_of: date | datetime | None
    turnover: float
    drawdown: float


@dataclass(frozen=True)
class BacktestResult:
    points: tuple[BacktestPoint, ...]
    metrics: dict[str, float]
    benchmark_metrics: dict[str, dict[str, float]]
    stress_periods: dict[str, dict[str, object]]
    proxy_disclosures: tuple[str, ...]
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


class BacktestEngine:
    def __init__(
        self,
        *,
        transaction_cost_bps: float = 0.0,
        rebalance_policy: RebalancePolicy | None = None,
        allocation_policy: AllocationPolicy | None = None,
    ) -> None:
        if transaction_cost_bps < 0:
            raise ValueError("transaction_cost_bps must be non-negative")
        self.transaction_cost = transaction_cost_bps / 10_000
        self.rebalance_policy = rebalance_policy or RebalancePolicy()
        self.allocation_policy = allocation_policy or AllocationPolicy()

    def run(self, rows: Sequence[Mapping[str, object]], *, initial_equity_weight: float = 0.10) -> BacktestResult:
        ordered = list(rows)
        dates = [self._date(row) for row in ordered]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("backtest rows must have unique ascending dates")
        current_weight = float(initial_equity_weight)
        current_assets = self.allocation_policy.allocate(current_weight, require_bucket=False).weights
        pending_signal: tuple[date | datetime, float] | None = None
        equity = peak = 1.0
        total_turnover = 0.0
        points: list[BacktestPoint] = []
        strategy_returns: list[float] = []
        disclosures: set[str] = set()

        for index, (row, row_date) in enumerate(zip(ordered, dates)):
            requested: float | None = None
            signal_as_of: date | datetime | None = None
            point_turnover = 0.0
            if pending_signal is not None:
                signal_as_of, requested = pending_signal
                default_schedule = index == 0 or (row_date.year, row_date.month) != (
                    dates[index - 1].year, dates[index - 1].month
                )
                decision = self.rebalance_policy.apply(
                    current_weight, requested,
                    scheduled=bool(row.get("scheduled_rebalance", default_schedule)),
                    risk_event=bool(row.get("risk_event", False)),
                )
                new_assets = self.allocation_policy.allocate(decision.applied_weight, require_bucket=False).weights
                point_turnover = sum(abs(new_assets[key] - current_assets[key]) for key in new_assets) / 2
                total_turnover += point_turnover
                current_weight = decision.applied_weight
                current_assets = new_assets

            asset_returns = row.get("returns", {})
            if not isinstance(asset_returns, Mapping):
                raise ValueError("each backtest row requires a returns mapping")
            gross = sum(weight * float(asset_returns.get(asset, 0.0)) for asset, weight in current_assets.items())
            net = gross - point_turnover * self.transaction_cost
            equity *= 1 + net
            peak = max(peak, equity)
            strategy_returns.append(net)
            points.append(BacktestPoint(row_date, net, equity, requested, current_weight, signal_as_of, point_turnover, equity / peak - 1))

            new_target = row.get("target_equity_weight")
            pending_signal = None if new_target is None else (row_date, float(new_target))
            if bool(row.get("cash_is_proxy", False)):
                disclosures.add(str(row.get("cash_proxy_name") or "unspecified cash proxy"))

        metrics = performance_metrics(strategy_returns, dates=dates, turnover=total_turnover)
        benchmark_series = benchmark_returns(ordered)
        benchmark_metrics = {
            name: performance_metrics(values, dates=dates, turnover=0.0)
            for name, values in benchmark_series.items()
        }
        stress = self._stress_slices(dates, strategy_returns, (2000, 2008, 2020, 2022))
        return BacktestResult(tuple(points), metrics, benchmark_metrics, stress, tuple(sorted(disclosures)))

    @staticmethod
    def _date(row: Mapping[str, object]) -> date:
        value = row.get("date", row.get("as_of"))
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        raise ValueError("each backtest row requires an ISO date/as_of")

    @staticmethod
    def _stress_slices(
        dates: Sequence[date | datetime], returns: Sequence[float], years: Sequence[int]
    ) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for year in years:
            selected = [(item_date, value) for item_date, value in zip(dates, returns) if item_date.year == year]
            if not selected:
                result[str(year)] = {"available": False, "reason": "no observations in stress period"}
            else:
                result[str(year)] = {
                    "available": True,
                    "metrics": performance_metrics([value for _, value in selected], dates=[item_date for item_date, _ in selected]),
                }
        return result
