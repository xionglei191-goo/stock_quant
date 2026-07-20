from .base import ComponentSpec, PercentileFactorCalculator


class TrendFactor(PercentileFactorCalculator):
    name = "trend"
    version = "1.0"
    components = (
        ComponentSpec("price_to_ma_50", 0.10, "high", max_age_days=7),
        ComponentSpec("price_to_ma_100", 0.10, "high", max_age_days=7),
        ComponentSpec("price_to_ma_200", 0.20, "high", critical=True, max_age_days=7),
        ComponentSpec("return_3m", 0.10, "high", max_age_days=7),
        ComponentSpec("return_6m", 0.15, "high", max_age_days=7),
        ComponentSpec("return_12m", 0.20, "high", critical=True, max_age_days=7),
        ComponentSpec("distance_from_high", 0.15, "high", max_age_days=7),
    )
