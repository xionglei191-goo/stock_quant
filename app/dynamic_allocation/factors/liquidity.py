from .base import ComponentSpec, PercentileFactorCalculator


class LiquidityFactor(PercentileFactorCalculator):
    name = "liquidity"
    version = "1.0"
    components = (
        ComponentSpec("fed_balance_sheet", 0.25, "high", critical=True, max_age_days=21),
        ComponentSpec("treasury_general_account", 0.15, "low", max_age_days=21),
        ComponentSpec("reverse_repo", 0.15, "low", max_age_days=14),
        ComponentSpec("dollar_index", 0.20, "low", max_age_days=7),
        ComponentSpec("financial_conditions", 0.25, "low", critical=True, max_age_days=21),
    )
