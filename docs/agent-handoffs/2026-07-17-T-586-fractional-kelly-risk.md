# Handoff: T-586 Fractional Kelly and Risk Caps

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: Codex sub-agent `/root/t584_t586_rules_risk`
- Branch/worktree: current shared worktree; dirty before task and concurrently edited

## Objective

Implement quarter/half Kelly sizing and transparent permanent-loss, asset, correlation, data-quality and maximum-allocation caps. The final result must explain the binding minimum and remain strictly paper-only.

## Scope

- In scope: binomial and continuous fractional Kelly, confidence shrinkage, sample/input stability gates, permanent-loss budget conversion, named component caps, final minimum-cap decision, warnings, and focused tests.
- Out of scope: return forecasting, probability estimation, model training, source data, persistence, APIs, UI, paper ledger orchestration, broker connectivity, and live execution.

## Background

Kelly sizing is highly sensitive to estimation error. T-581 therefore permits only quarter or half Kelly, requires an unavailable state for insufficient inputs, and places Kelly behind independent risk and maximum-allocation controls.

## Problem Statement

A single `expected_return + probability + volatility` tuple does not define one defensible Kelly equation. The implementation needs explicit binomial and continuous modes, must avoid counting probability twice, and cannot silently convert weak evidence into an aggressive cap.

## Expected Deliverables

- Quarter and half fractions only; full Kelly rejected at construction.
- Binomial mode using win probability and average gain/loss odds.
- Continuous mode using confidence-shrunk `mu / sigma^2`.
- Conservative unavailable results for missing, undersampled, invalid or near-zero-volatility inputs.
- A documented permanent-loss budget cap and the final minimum of requested, Kelly, risk and maximum allocation.
- Named binding limit, component values, warning list and fixed paper-only boundary fields.

## Current Findings

- Raw Kelly estimates remain visible for diagnostics; the fractional recommendation is clipped to a long-only, unlevered 0-100% range.
- Probability is used in binomial Kelly, while continuous mode uses optional confidence only to shrink expected return once.
- An unavailable Kelly result is not fabricated as a numeric cap. Independent risk and maximum caps decide the allocation and the warning remains visible.
- Permanent-loss budget conversion is `loss_budget / equity_stress_loss`, capped at 100%; the stress loss must be a documented positive scenario magnitude.

## Proposed Work Plan

1. Supply expected-return distributions from a separately validated estimator; do not derive them inside the risk module.
2. Configure risk component caps and scenario provenance in the application layer.
3. Expose every cap and warning in the decision snapshot and dashboard.

## Validation Plan

- Test constructor rejection for full Kelly.
- Test quarter/half results in binomial mode and confidence shrinkage in continuous mode.
- Test missing samples and zero volatility return unavailable results.
- Test permanent-loss conversion and named binding cap selection.
- Compile scoped modules and validate handoff structure.

## Risks

- Kelly remains unstable when upstream estimates are unstable; callers must preserve sample size, model version and scenario provenance.
- Direct component caps are policy inputs, not inferred facts. Governance review must validate their configuration before relying on paper recommendations.
- An unavailable Kelly warning does not itself force zero allocation; the independent data-quality/permanent-loss caps are responsible for conservative fallback.

## Dependencies

- T-584 supplies the requested rules-based target.
- Later application integration must supply validated estimates, policy configuration and auditable decision persistence.

## Blockers

- No blocker for the pure risk implementation.
- The active interpreter lacks `PyYAML`, which blocks two concurrent T-582 tests during full dynamic-allocation discovery but does not affect the five T-586 tests.

## Handoff Checklist

- [x] Code changes completed
- [x] Full Kelly explicitly rejected
- [x] Insufficient/unstable input fallback covered
- [x] Permanent-loss and minimum-cap explanations covered
- [x] Paper-only/no-broker boundary fixed in risk decisions
- [ ] PM roadmap status update in `tasks/todo.md` (intentionally reserved for parent PM agent)

## Evidence

Commands run:

```bash
python3 -m unittest tests.dynamic_allocation.test_risk_limits
python3 -m py_compile app/dynamic_allocation/risk/*.py tests/dynamic_allocation/test_risk_limits.py
python3 -m unittest discover -s tests/dynamic_allocation
git diff --check -- app/dynamic_allocation/risk tests/dynamic_allocation/test_risk_limits.py
```

Results:

- Passed: 5 focused T-586 tests; scoped compile; scoped `git diff --check`.
- Failed: full dynamic-allocation discovery ran 29 tests with 2 errors in concurrent T-582 repository tests because the interpreter lacks `yaml`; no T-586 test failed.
- Not run: full repository unit/UI/security suites, because the parent PM agent owns the combined T-581 through T-588 integration gate.
- `app/dynamic_allocation/risk/`: Kelly and risk policy source, local source code, no sensitive data, not release evidence.
- No generated market/model artifact: implementation used deterministic fixtures only; no sensitive data and not acceptable for non-local release evidence.

## Next Recommended Action

1. Wire the T-584 requested target and configured risk caps into the auditable decision snapshot.
2. Add governance-reviewed config ranges and provenance for permanent-loss and correlation scenarios.
3. Rerun combined dynamic-allocation and repository-wide gates after dependency synchronization.
