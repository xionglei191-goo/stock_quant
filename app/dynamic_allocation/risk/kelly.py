"""Conservative fractional-Kelly sizing for research allocations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class KellyFraction(str, Enum):
    QUARTER = "quarter"
    HALF = "half"

    @property
    def multiplier(self) -> float:
        return 0.25 if self is KellyFraction.QUARTER else 0.50


@dataclass(frozen=True)
class KellyResult:
    available: bool
    mode: str
    fraction: KellyFraction
    raw_kelly: float | None
    recommended_position: float | None
    explanation: str
    warnings: tuple[str, ...] = ()


class FractionalKellySizer:
    def __init__(self, fraction: KellyFraction | str) -> None:
        try:
            self.fraction = KellyFraction(fraction)
        except ValueError as exc:
            raise ValueError("only quarter or half Kelly is supported; full Kelly is prohibited") from exc

    def binomial(
        self,
        *,
        p_win: float | None,
        avg_gain: float | None,
        avg_loss: float | None,
        sample_size: int | None = None,
        minimum_samples: int = 24,
    ) -> KellyResult:
        if sample_size is not None and sample_size < minimum_samples:
            return self._unavailable("binomial", f"sample_size {sample_size} is below minimum {minimum_samples}")
        if p_win is None or avg_gain is None or avg_loss is None:
            return self._unavailable("binomial", "p_win, avg_gain and avg_loss are all required")
        p, gain, loss = float(p_win), float(avg_gain), abs(float(avg_loss))
        if not 0 < p < 1 or gain <= 0 or loss <= 0:
            return self._unavailable("binomial", "probability must be in (0,1), gains and losses must be positive")
        odds = gain / loss
        raw = p - (1 - p) / odds
        return self._available("binomial", raw, f"p={p:.3f}, gain/loss odds={odds:.3f}")

    def continuous(
        self,
        *,
        expected_return: float | None,
        volatility: float | None,
        confidence: float | None = None,
        sample_size: int | None = None,
        minimum_samples: int = 24,
    ) -> KellyResult:
        if sample_size is not None and sample_size < minimum_samples:
            return self._unavailable("continuous", f"sample_size {sample_size} is below minimum {minimum_samples}")
        if expected_return is None or volatility is None:
            return self._unavailable("continuous", "expected_return and volatility are required")
        mu, sigma = float(expected_return), float(volatility)
        if not math.isfinite(mu) or not math.isfinite(sigma) or sigma <= 1e-6:
            return self._unavailable("continuous", "volatility is zero, near zero, or non-finite")
        shrink = 1.0 if confidence is None else float(confidence)
        if not 0 <= shrink <= 1:
            return self._unavailable("continuous", "confidence must be within 0-1")
        raw = (mu * shrink) / (sigma * sigma)
        return self._available("continuous", raw, f"mu={mu:.4f}, sigma={sigma:.4f}, confidence_shrink={shrink:.3f}")

    def _available(self, mode: str, raw: float, details: str) -> KellyResult:
        # Preserve the diagnostic raw estimate, then prevent the final fractional
        # recommendation from introducing short exposure or leverage.
        fractional = raw * self.fraction.multiplier
        recommended = min(max(fractional, 0.0), 1.0)
        warning = () if recommended == fractional else ("fractional Kelly was clipped to the long-only 0-100% range",)
        return KellyResult(
            True, mode, self.fraction, round(raw, 10), round(recommended, 10),
            f"{details}; raw={raw:.4f}; {self.fraction.value} Kelly={recommended:.4f}", warning,
        )

    def _unavailable(self, mode: str, reason: str) -> KellyResult:
        return KellyResult(False, mode, self.fraction, None, None, f"Kelly unavailable: {reason}", (reason,))
