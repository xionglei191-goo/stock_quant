# Handoff: T-584 Rule Regime and Walk-Forward Backtest

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality
- Last updated: 2026-07-17
- Last agent: Codex sub-agent `/root/t584_t586_rules_risk`
- Branch/worktree: current shared worktree; dirty before task and concurrently edited

## Objective

Implement an explainable five-state rule classifier, continuous factor scoring into the 10/30/50/70/90 equity buckets, portfolio/rebalance policies, and a paper-only no-lookahead walk-forward backtest with required metrics and benchmarks.

## Scope

- In scope: pure mapping/sequence model interfaces, state hysteresis, five allocation buckets, SPY/QQQ/SGOV split, no-trade buffer, maximum rebalance step, next-observation signal execution, four benchmarks, stress-year slicing, proxy disclosure, and focused tests.
- Out of scope: PIT repositories and data ingestion, factor calculation, model training, HMM/ML, APIs, UI/dashboard, persistence, real historical evidence, broker integration, and automatic execution.

## Background

T-581 defines a rules-first dynamic allocation domain. Factor scores are normalized to 0-100 with higher values supporting equity risk, and the first-phase universe is SPY, QQQ and SGOV with a fixed 70:30 split inside equity exposure.

## Problem Statement

The first portfolio model needs to remain deterministic and inspectable while preventing state churn and future-data leakage. Historical ETF coverage also cannot be represented as authentic before inception, so benchmark inputs need an explicit cash-proxy disclosure path.

## Expected Deliverables

- Deterministic `risk_on`, `late_cycle`, `risk_off`, `crisis`, and `recovery` results with matched-rule explanations.
- Weighted factor score, score bucket, regime cap, and final target as separate inspectable fields.
- Monthly/event-compatible rebalance controls with no-trade buffer and maximum step.
- Backtest metrics: CAGR, annual return, maximum drawdown, Sharpe, Sortino, Calmar, win rate, and turnover.
- SPY buy-and-hold, 60/40 SPY/SGOV, QQQ buy-and-hold, and lagged SPY 200MA benchmarks.
- 2000/2008/2020/2022 slice output and explicit pre-inception proxy warnings.

## Current Findings

- The classifier gives crisis rules priority so a severe risk break can bypass the minimum residence period.
- Non-crisis transitions honor both minimum residence and a configurable composite-score transition margin.
- A signal stored on observation `t` is first applied to observation `t+1`; the same-row return remains under the previously applied allocation.
- The 200MA benchmark similarly uses the prior observation's close/MA decision.
- Real PIT market/factor histories are not part of this unit; the engine is ready to consume them through mapping rows after T-582/T-583 integration.

## Proposed Work Plan

1. Connect ready `FactorResult` scores to the classifier/scorer without changing these pure interfaces.
2. Feed PIT-aligned market returns and the governed Treasury proxy into the engine.
3. Persist backtest summaries and points only through the later application/API integration task.

## Validation Plan

- Compile every new model, portfolio and backtest module.
- Run focused deterministic regime, bucket, rebalance, leakage, metric, benchmark, stress-slice and proxy tests.
- Run the complete dynamic-allocation test directory and record dependency/environment failures separately.
- Run whitespace/error checks on the scoped changes and validate all handoff documents.

## Risks

- Stress-year support is structurally tested with synthetic observations; no claim is made that a real 2000/2008/2020/2022 backtest artifact exists yet.
- The 60/40 benchmark trusts the caller to supply either authentic SGOV returns or a row explicitly labeled with the governed cash proxy.
- The default engine is dependency-light and does not model intraday fills; its contract is observation-level next-period paper execution.

## Dependencies

- T-582 PIT data and governed proxy rows.
- T-583 complete, ready factor scores.
- T-586 risk output can cap the bucket target before the rebalance policy is applied.

## Blockers

- No blocker for the delivered pure model/backtest code.
- Full `tests/dynamic_allocation` currently has two T-582 repository-test errors because `PyYAML` is not installed in the active interpreter; the T-584 tests do not depend on YAML and pass.

## Handoff Checklist

- [x] Code changes completed
- [x] Focused tests and compile checks passed
- [x] No-lookahead behavior directly asserted
- [x] Paper-only/no-broker boundary included in backtest results
- [x] Known integration dependency recorded
- [ ] PM roadmap status update in `tasks/todo.md` (intentionally reserved for parent PM agent)

## Evidence

Commands run:

```bash
python3 -m unittest tests.dynamic_allocation.test_regime_rules tests.dynamic_allocation.test_walk_forward
python3 -m py_compile app/dynamic_allocation/models/*.py app/dynamic_allocation/portfolio/*.py app/dynamic_allocation/risk/*.py app/dynamic_allocation/backtest/*.py tests/dynamic_allocation/*.py
python3 -m unittest discover -s tests/dynamic_allocation
git diff --check -- app/dynamic_allocation/models app/dynamic_allocation/portfolio app/dynamic_allocation/risk app/dynamic_allocation/backtest tests/dynamic_allocation/test_regime_rules.py tests/dynamic_allocation/test_risk_limits.py tests/dynamic_allocation/test_walk_forward.py
```

Results:

- Passed: 9 focused T-584 tests; scoped compile; scoped `git diff --check`.
- Failed: full dynamic-allocation discovery ran 29 tests with 2 errors in concurrent T-582 repository tests because the interpreter lacks `yaml`; 27 tests passed and no T-584 test failed.
- Not run: full repository unit/UI/security suites, because the parent PM agent owns the combined T-581 through T-588 integration gate.
- `app/dynamic_allocation/models/`: deterministic regime and allocation score producer; local source code, no sensitive data, not release evidence.
- `app/dynamic_allocation/portfolio/`: allocation and rebalance policies; local source code, no sensitive data, not release evidence.
- `app/dynamic_allocation/backtest/`: engine, metrics, benchmarks and walk-forward orchestration; local source code, no sensitive data, not release evidence.

## Next Recommended Action

1. Have the parent PM agent install/synchronize declared dependencies, then rerun full dynamic-allocation discovery.
2. Integrate T-582/T-583 outputs and produce a local-only PIT historical backtest artifact with proxy inventory.
3. Run the repository-wide integration and security gates before updating T-584 roadmap status.
