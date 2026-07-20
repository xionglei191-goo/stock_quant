"""Deterministic, explainable market-regime rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class MarketRegime(str, Enum):
    RISK_ON = "risk_on"
    LATE_CYCLE = "late_cycle"
    RISK_OFF = "risk_off"
    CRISIS = "crisis"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class RegimeResult:
    regime: MarketRegime
    raw_regime: MarketRegime
    composite_score: float
    matched_rules: tuple[str, ...]
    retained_by_hysteresis: bool
    explanation: str
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


class RuleRegimeClassifier:
    """Classify factor scores whose direction is high = risk supportive.

    The caller owns state persistence and supplies the previous regime and its
    residence count. Thresholds are intentionally explicit and immutable over a
    test window, making the classifier suitable for point-in-time backtests.
    """

    REQUIRED = ("valuation", "trend", "volatility", "credit", "leverage", "macro", "liquidity", "breadth")

    def __init__(self, *, minimum_residence_periods: int = 2, transition_margin: float = 5.0) -> None:
        if minimum_residence_periods < 0:
            raise ValueError("minimum_residence_periods must be non-negative")
        if transition_margin < 0:
            raise ValueError("transition_margin must be non-negative")
        self.minimum_residence_periods = minimum_residence_periods
        self.transition_margin = float(transition_margin)

    def classify(
        self,
        factors: Mapping[str, float],
        *,
        previous_regime: MarketRegime | str | None = None,
        periods_in_regime: int = 0,
    ) -> RegimeResult:
        scores = self._validated_scores(factors)
        composite = sum(scores.values()) / len(scores)
        risk_environment = sum(scores[key] for key in ("volatility", "credit", "liquidity")) / 3
        participation = (scores["trend"] + scores["breadth"]) / 2
        weak_risk_count = sum(scores[key] <= 25 for key in ("volatility", "credit", "liquidity", "breadth"))
        weak_count = sum(value <= 35 for value in scores.values())

        rules: list[str] = []
        if risk_environment <= 25 or weak_risk_count >= 2:
            raw = MarketRegime.CRISIS
            rules.append(f"crisis: risk_environment={risk_environment:.1f}, weak_risk_count={weak_risk_count}")
        elif previous_regime in (MarketRegime.CRISIS, MarketRegime.RISK_OFF, "crisis", "risk_off") and participation >= 55 and scores["valuation"] >= 50:
            raw = MarketRegime.RECOVERY
            rules.append(f"recovery: participation={participation:.1f}, valuation={scores['valuation']:.1f}")
        elif weak_count >= 3 or (participation < 40 and risk_environment < 45):
            raw = MarketRegime.RISK_OFF
            rules.append(f"risk_off: weak_count={weak_count}, participation={participation:.1f}")
        elif scores["valuation"] <= 40 and scores["trend"] >= 50 and (scores["macro"] <= 50 or scores["leverage"] <= 40):
            raw = MarketRegime.LATE_CYCLE
            rules.append(
                f"late_cycle: valuation={scores['valuation']:.1f}, trend={scores['trend']:.1f}, "
                f"macro={scores['macro']:.1f}, leverage={scores['leverage']:.1f}"
            )
        elif composite >= 60 and participation >= 50 and risk_environment >= 50:
            raw = MarketRegime.RISK_ON
            rules.append(f"risk_on: composite={composite:.1f}, participation={participation:.1f}")
        elif composite >= 50:
            raw = MarketRegime.LATE_CYCLE
            rules.append(f"late_cycle fallback: composite={composite:.1f}")
        else:
            raw = MarketRegime.RISK_OFF
            rules.append(f"risk_off fallback: composite={composite:.1f}")

        previous = MarketRegime(previous_regime) if previous_regime is not None else None
        retained = False
        final = raw
        if previous is not None and raw != MarketRegime.CRISIS and raw != previous:
            score_near_boundary = self._near_transition_boundary(composite)
            if periods_in_regime < self.minimum_residence_periods or score_near_boundary:
                final = previous
                retained = True
                rules.append(
                    f"hysteresis: retained {previous.value}; residence={periods_in_regime}, "
                    f"minimum={self.minimum_residence_periods}, boundary_margin={self.transition_margin:.1f}"
                )

        explanation = f"{final.value}: " + "; ".join(rules)
        return RegimeResult(final, raw, round(composite, 4), tuple(rules), retained, explanation)

    def _near_transition_boundary(self, composite: float) -> bool:
        return any(abs(composite - boundary) < self.transition_margin for boundary in (40.0, 50.0, 60.0))

    def _validated_scores(self, factors: Mapping[str, float]) -> dict[str, float]:
        missing = [key for key in self.REQUIRED if key not in factors]
        if missing:
            raise ValueError(f"missing required factor scores: {', '.join(missing)}")
        scores = {key: float(factors[key]) for key in self.REQUIRED}
        invalid = [key for key, value in scores.items() if not 0 <= value <= 100]
        if invalid:
            raise ValueError(f"factor scores must be within 0-100: {', '.join(invalid)}")
        return scores
