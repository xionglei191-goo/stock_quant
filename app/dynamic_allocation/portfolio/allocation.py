"""Paper-only allocation policy for the phase-one universe."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetAllocation:
    equity_weight: float
    weights: dict[str, float]
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


class AllocationPolicy:
    ALLOWED_EQUITY_WEIGHTS = (0.10, 0.30, 0.50, 0.70, 0.90)

    def __init__(self, *, spy_share: float = 0.70, qqq_share: float = 0.30) -> None:
        if abs(spy_share + qqq_share - 1.0) > 1e-9 or min(spy_share, qqq_share) < 0:
            raise ValueError("SPY and QQQ shares must be non-negative and sum to one")
        self.spy_share = spy_share
        self.qqq_share = qqq_share

    def allocate(self, equity_weight: float, *, require_bucket: bool = True) -> AssetAllocation:
        equity = float(equity_weight)
        if not 0 <= equity <= 1:
            raise ValueError("equity weight must be within 0-1")
        if require_bucket and not any(abs(equity - item) < 1e-9 for item in self.ALLOWED_EQUITY_WEIGHTS):
            raise ValueError("target equity weight must use a 10/30/50/70/90 bucket")
        return AssetAllocation(equity, {
            "SPY": round(equity * self.spy_share, 10),
            "QQQ": round(equity * self.qqq_share, 10),
            "SGOV": round(1.0 - equity, 10),
        })
