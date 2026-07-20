from .base import ComponentSpec, PercentileFactorCalculator


class VolatilityFactor(PercentileFactorCalculator):
    """A high score means a benign volatility environment, not a high VIX."""

    name = "volatility"
    version = "1.0"
    components = (
        ComponentSpec("vix_level", 0.35, "low", critical=True, max_age_days=7),
        ComponentSpec("vix_change_speed", 0.25, "low", critical=True, max_age_days=7),
        ComponentSpec("vix_term_structure", 0.40, "high", critical=True, max_age_days=7),
    )
