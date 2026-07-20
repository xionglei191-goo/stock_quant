from .base import ComponentSpec, PercentileFactorCalculator


class CreditFactor(PercentileFactorCalculator):
    name = "credit"
    version = "1.0"
    components = (
        ComponentSpec("high_yield_spread", 0.40, "low", critical=True, max_age_days=14),
        ComponentSpec("investment_grade_spread", 0.30, "low", max_age_days=14),
        ComponentSpec("hyg_return", 0.30, "high", critical=True, max_age_days=7),
    )
