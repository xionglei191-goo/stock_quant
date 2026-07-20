"""Transparent caps applied after model scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .kelly import KellyResult


@dataclass(frozen=True)
class RiskDecision:
    requested_allocation: float
    kelly_cap: float | None
    risk_cap: float
    maximum_allocation: float
    final_allocation: float
    binding_limit: str
    component_caps: dict[str, float]
    warnings: tuple[str, ...]
    explanation: str
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


class RiskLimitPolicy:
    """Calculate permanent-loss, asset, correlation and quality caps."""

    def __init__(self, *, maximum_allocation: float = 0.90) -> None:
        if not 0 <= maximum_allocation <= 1:
            raise ValueError("maximum_allocation must be within 0-1")
        self.maximum_allocation = maximum_allocation

    def decide(
        self,
        requested_allocation: float,
        *,
        kelly: KellyResult | None,
        permanent_loss_cap: float = 1.0,
        asset_cap: float = 1.0,
        correlation_cap: float = 1.0,
        data_quality_cap: float = 1.0,
        extra_caps: Mapping[str, float] | None = None,
    ) -> RiskDecision:
        requested = self._cap("requested_allocation", requested_allocation)
        components = {
            "permanent_loss": self._cap("permanent_loss_cap", permanent_loss_cap),
            "asset": self._cap("asset_cap", asset_cap),
            "correlation": self._cap("correlation_cap", correlation_cap),
            "data_quality": self._cap("data_quality_cap", data_quality_cap),
        }
        for name, value in (extra_caps or {}).items():
            components[str(name)] = self._cap(str(name), value)
        risk_name, risk_cap = min(components.items(), key=lambda item: item[1])
        candidates = {
            "requested_allocation": requested,
            "risk_cap": risk_cap,
            "maximum_allocation": self.maximum_allocation,
        }
        warnings: list[str] = []
        kelly_cap: float | None = None
        if kelly is not None and kelly.available and kelly.recommended_position is not None:
            kelly_cap = self._cap("kelly_cap", kelly.recommended_position)
            candidates["kelly_cap"] = kelly_cap
            warnings.extend(kelly.warnings)
        else:
            warnings.append("Kelly unavailable; final allocation uses the conservative risk and maximum caps")
            if kelly is not None:
                warnings.extend(kelly.warnings)
        binding, final = min(candidates.items(), key=lambda item: item[1])
        if binding == "risk_cap":
            binding = f"risk_cap:{risk_name}"
        explanation = (
            f"final={final:.1%} is min(requested={requested:.1%}, "
            f"Kelly={'unavailable' if kelly_cap is None else f'{kelly_cap:.1%}'}, "
            f"risk={risk_cap:.1%} [{risk_name}], max={self.maximum_allocation:.1%})"
        )
        return RiskDecision(
            requested, kelly_cap, risk_cap, self.maximum_allocation, final, binding,
            components, tuple(dict.fromkeys(warnings)), explanation,
        )

    @staticmethod
    def permanent_loss_cap(*, loss_budget: float, equity_stress_loss: float) -> float:
        """Translate a portfolio loss budget into a maximum equity allocation.

        For example, a 15% permanent-loss budget and a 30% equity stress loss
        imply a 50% equity cap. The stress loss is supplied as a positive
        magnitude and must come from a documented scenario.
        """
        budget = float(loss_budget)
        stress = float(equity_stress_loss)
        if not 0 <= budget <= 1:
            raise ValueError("loss_budget must be within 0-1")
        if not 0 < stress <= 1:
            raise ValueError("equity_stress_loss must be within (0,1]")
        return min(budget / stress, 1.0)

    @staticmethod
    def _cap(name: str, value: float) -> float:
        parsed = float(value)
        if not 0 <= parsed <= 1:
            raise ValueError(f"{name} must be within 0-1")
        return parsed
