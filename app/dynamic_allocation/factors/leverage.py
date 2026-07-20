from .base import ComponentSpec, PercentileFactorCalculator


class LeverageFactor(PercentileFactorCalculator):
    name = "leverage"
    version = "1.0"
    components = (
        ComponentSpec("margin_debt_level", 0.20, "low", max_age_days=120),
        ComponentSpec("margin_debt_to_market_cap", 0.30, "low", critical=True, max_age_days=120),
        ComponentSpec("margin_debt_growth", 0.25, "low", max_age_days=120),
        ComponentSpec("deleveraging_speed", 0.25, "low", critical=True, max_age_days=120),
    )
