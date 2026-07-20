from .base import ComponentSpec, PercentileFactorCalculator


class ValuationFactor(PercentileFactorCalculator):
    name = "valuation"
    version = "1.0"
    components = (
        ComponentSpec("forward_pe", 0.20, "low", critical=True, max_age_days=120),
        ComponentSpec("cape", 0.20, "low", max_age_days=400),
        ComponentSpec("earnings_yield", 0.20, "high", critical=True, max_age_days=120),
        ComponentSpec("free_cash_flow_yield", 0.20, "high", max_age_days=120),
        ComponentSpec("equity_risk_premium", 0.20, "high", critical=True, max_age_days=45),
    )
