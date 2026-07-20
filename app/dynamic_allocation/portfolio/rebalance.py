"""Turnover controls for paper-only target transitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RebalanceDecision:
    requested_weight: float
    applied_weight: float
    trade_delta: float
    action: str
    explanation: str


class RebalancePolicy:
    def __init__(self, *, no_trade_buffer: float = 0.10, maximum_step: float = 0.15) -> None:
        if not 0 <= no_trade_buffer <= 1 or not 0 < maximum_step <= 1:
            raise ValueError("invalid rebalance controls")
        self.no_trade_buffer = no_trade_buffer
        self.maximum_step = maximum_step

    def apply(self, current_weight: float, requested_weight: float, *, scheduled: bool = True, risk_event: bool = False) -> RebalanceDecision:
        current, requested = float(current_weight), float(requested_weight)
        if not all(0 <= value <= 1 for value in (current, requested)):
            raise ValueError("rebalance weights must be within 0-1")
        delta = requested - current
        if not scheduled and not risk_event:
            return RebalanceDecision(requested, current, 0.0, "hold", "outside scheduled rebalance and no risk event")
        if abs(delta) <= self.no_trade_buffer + 1e-12:
            return RebalanceDecision(requested, current, 0.0, "hold", f"delta {delta:.1%} is within no-trade buffer")
        step = min(abs(delta), self.maximum_step)
        applied = current + (step if delta > 0 else -step)
        action = "increase" if delta > 0 else "decrease"
        return RebalanceDecision(requested, round(applied, 10), round(applied - current, 10), action, f"{action} capped at maximum step {self.maximum_step:.1%}")
