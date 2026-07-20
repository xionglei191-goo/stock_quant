from .base import ComponentSpec, PercentileFactorCalculator


class MacroFactor(PercentileFactorCalculator):
    name = "macro"
    version = "1.0"
    minimum_coverage = 0.70
    components = (
        ComponentSpec("unemployment_rate", 0.10, "low", critical=True, max_age_days=60),
        ComponentSpec("initial_claims", 0.10, "low", max_age_days=21),
        ComponentSpec("payroll_growth", 0.15, "high", critical=True, max_age_days=60),
        ComponentSpec("cpi", 0.10, "target", max_age_days=60, target=2.0),
        ComponentSpec("core_cpi", 0.10, "target", max_age_days=60, target=2.0),
        ComponentSpec("pce", 0.15, "target", critical=True, max_age_days=60, target=2.0),
        ComponentSpec("pmi", 0.15, "high", max_age_days=60),
        ComponentSpec("ism", 0.15, "high", critical=True, max_age_days=60),
    )
