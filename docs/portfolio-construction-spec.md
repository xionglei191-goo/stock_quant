# Black-Litterman Portfolio Prototype

## Scope

The portfolio engine produces paper-only candidate weights for research and committee review. It does not create `ExecutionIntent` records and it must remain downstream of evidence-backed research views and upstream of human approval.

## Inputs

| Field | Meaning |
|---|---|
| `securities[]` | Universe with `security_id`, `market_weight`, `volatility`, `market`, `industry`, optional `theme` |
| `views[]` | Absolute-return research views with `security_id`, `expected_return`, `confidence`, optional `evidence_ids` |
| `risk_aversion` | Delta parameter for equilibrium prior return |
| `tau` | Prior uncertainty scale |
| `constraints.max_weight` | Per-security long-only cap |
| `constraints.restricted_securities` | Securities forced to zero weight |
| `constraints.market_budget` | Maximum market exposure by A/H/U bucket |
| `constraints.industry_budget` | Maximum industry exposure |
| `constraints.theme_budget` | Maximum theme exposure |
| `constraints.currency_budget` | Maximum currency exposure |
| `constraints.current_weights` | Current paper or live weights used for turnover diagnostics |
| `risk_budget` | Market/industry budget aliases used by risk review |
| `stress_scenarios[]` | Named per-security return shocks |
| `return_history` | Per-security period return series for walk-forward diagnostics |

## Math

The prototype uses a diagonal Black-Litterman approximation so the first implementation stays inspectable:

```text
Pi_i = delta * sigma_i^2 * w_mkt_i
prior_variance_i = tau * sigma_i^2
omega_i = max(prior_variance_i * (1 - confidence_i) / confidence_i, 1e-6)
mu_bl_i = (Pi_i / prior_variance_i + Q_i / omega_i) / (1 / prior_variance_i + 1 / omega_i)
score_i = max(mu_bl_i, 0) / sigma_i^2
```

Higher confidence lowers `omega`, so a view with stronger evidence has more pull on posterior return. Candidate weights are normalized from positive risk-adjusted scores, then restricted securities, per-security caps, market budgets, and industry budgets are applied. Any unallocated residual is reported as `cash_weight`.

## Diagnostics

Each `PortfolioProposal` stores prior returns, posterior returns, candidate weights, view-level omega diagnostics, market, industry, theme, and currency exposures, approximate risk contribution, turnover, stress results, and walk-forward total return / max drawdown.

## Governance

The proposal status defaults to `candidate`, and `constraints.paper_only` is forced to `true`. Moving from a proposal to any execution workflow still requires a separate DecisionPack and approval-signature path.
