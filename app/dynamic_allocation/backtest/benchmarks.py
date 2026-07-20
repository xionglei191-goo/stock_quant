"""Required transparent dynamic-allocation benchmarks."""

from __future__ import annotations

from typing import Mapping, Sequence


def benchmark_returns(rows: Sequence[Mapping[str, object]]) -> dict[str, list[float]]:
    result = {"spy_buy_hold": [], "spy_sgov_60_40": [], "qqq_buy_hold": [], "spy_200ma": []}
    spy_price = 1.0
    prices: list[float] = []
    pending_200ma_weight = 0.0
    for row in rows:
        returns = row.get("returns", {})
        if not isinstance(returns, Mapping):
            raise ValueError("each backtest row requires a returns mapping")
        spy = float(returns.get("SPY", 0.0))
        qqq = float(returns.get("QQQ", 0.0))
        cash = float(returns.get("SGOV", 0.0))
        result["spy_buy_hold"].append(spy)
        result["qqq_buy_hold"].append(qqq)
        result["spy_sgov_60_40"].append(0.60 * spy + 0.40 * cash)
        # Yesterday's close/MA decision earns today's return. No same-row signal use.
        result["spy_200ma"].append(pending_200ma_weight * spy + (1 - pending_200ma_weight) * cash)
        spy_price *= 1 + spy
        prices.append(spy_price)
        if len(prices) >= 200:
            pending_200ma_weight = 1.0 if spy_price >= sum(prices[-200:]) / 200 else 0.0
    return result
