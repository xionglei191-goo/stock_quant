"""Explainable factor scoring and five-bucket equity allocation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .regime_rules import MarketRegime


@dataclass(frozen=True)
class AllocationScore:
    raw_score: float
    score_bucket: float
    regime_cap: float
    target_equity_weight: float
    contributions: dict[str, float]
    explanation: str


class AllocationScorer:
    BUCKETS = (0.10, 0.30, 0.50, 0.70, 0.90)
    REGIME_CAPS = {
        MarketRegime.CRISIS: 0.10,
        MarketRegime.RISK_OFF: 0.30,
        MarketRegime.LATE_CYCLE: 0.50,
        MarketRegime.RECOVERY: 0.70,
        MarketRegime.RISK_ON: 0.90,
    }

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        supplied = dict(weights or {})
        self.weights = supplied or {
            "valuation": 0.18, "trend": 0.16, "volatility": 0.12, "credit": 0.12,
            "leverage": 0.10, "macro": 0.12, "liquidity": 0.10, "breadth": 0.10,
        }
        if any(value < 0 for value in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("allocation weights must be non-negative with positive sum")

    def score(self, factors: Mapping[str, float], regime: MarketRegime | str) -> AllocationScore:
        missing = sorted(set(self.weights) - set(factors))
        if missing:
            raise ValueError(f"missing weighted factors: {', '.join(missing)}")
        total_weight = sum(self.weights.values())
        normalized = {key: weight / total_weight for key, weight in self.weights.items()}
        contributions = {key: round(float(factors[key]) * weight, 4) for key, weight in normalized.items()}
        raw = sum(contributions.values())
        if not 0 <= raw <= 100:
            raise ValueError("factor scores must produce a value within 0-100")
        score_bucket = self.BUCKETS[min(int(raw // 20), 4)]
        regime_value = MarketRegime(regime)
        regime_cap = self.REGIME_CAPS[regime_value]
        target = min(score_bucket, regime_cap)
        reason = (
            f"weighted score {raw:.2f} maps to {score_bucket:.0%}; "
            f"{regime_value.value} cap is {regime_cap:.0%}; target is min={target:.0%}"
        )
        return AllocationScore(round(raw, 4), score_bucket, regime_cap, target, contributions, reason)
