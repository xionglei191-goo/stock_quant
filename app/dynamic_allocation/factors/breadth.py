from .base import ComponentSpec, PercentileFactorCalculator


class BreadthFactor(PercentileFactorCalculator):
    name = "breadth"
    version = "1.0"
    components = (
        ComponentSpec("stocks_above_200ma", 0.40, "high", critical=True, max_age_days=7),
        ComponentSpec("new_highs_lows", 0.30, "high", max_age_days=7),
        ComponentSpec("advance_decline", 0.30, "high", critical=True, max_age_days=7),
    )
