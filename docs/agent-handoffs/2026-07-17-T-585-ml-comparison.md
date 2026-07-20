# Handoff: T-585 Explainable ML Comparison

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality
- Last updated: 2026-07-17
- Last agent: Codex `/root/t585_ml_compare`
- Branch/worktree: shared current worktree

## Objective

Add explainable Markov-state, Ridge, Logistic, XGBoost, and LightGBM research candidates, then compare them with the rule baseline using deterministic expanding-window out-of-sample gates. Complex candidates must remain unpromoted unless risk-adjusted improvement is stable across folds.

## Scope

- In scope: lazy optional ML adapters, probabilities and explanations, chronological comparison, conservative promotion decision, focused tests.
- Out of scope: rule-model changes, risk-limit bypasses, model tuning on production data, API/UI integration, broker or live execution behavior.

## Background

T-584 provides the deterministic rule baseline, five allocation buckets, next-period signal execution, and expanding-window backtest semantics. T-585 adds research candidates without changing those baseline or downstream risk-control contracts.

## Problem Statement

Complex allocation models can look superior through random splits, future leakage, unstable folds, or hidden dependency failures. The comparison must use chronological fold predictions and default to the rule baseline unless improvement is stable and does not materially worsen drawdown.

## Expected Deliverables

- Explainable Markov-state, Ridge, Logistic, XGBoost, and LightGBM candidate adapters.
- Explicit optional-dependency availability and diagnostic status.
- Deterministic expanding-window comparison with a conservative promotion gate.
- Focused tests covering probabilities, explanations, chronology, leakage, unavailability, and unstable results.

## Current State

- Completed: `LinearAllocationModel` supports Ridge and multinomial Logistic candidates with standardized feature contributions and five-bucket probabilities.
- Completed: `TreeAllocationModel` supports lazily imported XGBoost and LightGBM candidates with deterministic seeds, five-bucket probabilities, and explicitly non-causal global-importance diagnostics.
- Completed: `HiddenMarkovRegimeClassifier` provides a deterministic Gaussian Markov-state approximation with transition probabilities, state probabilities, prototype deviations, and backend diagnostics. It does not hide tiny-sample HMM convergence failure.
- Completed: `WalkForwardModelComparator` fits each candidate only on expanding historical windows and retains `rule_baseline` unless every fold-count, stable-improvement, overall Sharpe, and drawdown gate passes.
- Completed: focused unavailability, leakage, chronological ordering, prediction explanation, probability, and unstable-promotion tests.
- In progress: none.
- Not started: real point-in-time production dataset comparison and model selection; this requires governed historical observations and is deliberately not fabricated in T-585.
- Blocked: none.

## Current Findings

- All candidate families fit and predict in the current `.venv`; outputs retain probabilities, explanations, and paper-only boundaries.
- The comparator never fits on a test row, rejects unsorted or duplicate dates, and makes any fold failure disqualifying.
- An intentionally unstable candidate remains unpromoted while the rule baseline stays selected.
- Fixture success validates software contracts, not investment efficacy.

## Proposed Work Plan

1. Run the fixed comparator against governed point-in-time factor and return history without changing thresholds inside a test window.
2. Store fold metrics, model/config versions, and unavailability diagnostics with the backtest run.
3. Promote a candidate for research use only when persisted evidence passes every configured gate.

## Validation Plan

- Compile all T-585 modules and focused tests.
- Run focused ML tests and complete dynamic-allocation discovery under `.venv`.
- Run security, whitespace, and handoff validation checks.

## Files Touched

- `app/dynamic_allocation/models/regime_ml.py`: candidate contracts, lazy dependency status, linear/tree adapters, and robust Markov-state approximation.
- `app/dynamic_allocation/models/ml_compare.py`: deterministic expanding-window comparison and conservative promotion gate.
- `app/dynamic_allocation/models/__init__.py`: public model exports.
- `tests/dynamic_allocation/test_ml_models.py`: focused candidate, availability, explanation, chronology, leakage, and promotion tests.
- `docs/agent-handoffs/2026-07-17-T-585-ml-comparison.md`: this handoff.

## Commands Run

```bash
.venv/bin/python -m unittest tests.dynamic_allocation.test_ml_models -v
.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v
.venv/bin/python -m py_compile app/dynamic_allocation/models/*.py tests/dynamic_allocation/test_ml_models.py
git diff --check -- app/dynamic_allocation/models tests/dynamic_allocation/test_ml_models.py
python3 scripts/check_handoffs.py
```

Result:

- Passed: focused ML tests, 7/7.
- Passed: dynamic-allocation suite, 36/36.
- Passed: model/test compilation and scoped diff whitespace check.
- Passed: handoff validation (run after this file was added).
- Failed: none.
- Not run: PostgreSQL integration because T-585 changes no storage contract; browser/UI checks because T-585 changes no UI.

## Decisions

- Optional ML packages are discovered without importing them and imported only inside `fit`; missing dependencies produce an explicit unavailable evaluation and can never promote.
- All allocation candidates emit only `10/30/50/70/90%` paper-equity buckets. Downstream Kelly and risk limits remain authoritative and unchanged.
- Ridge probability is an auditable distance distribution around its continuous estimate, with residual scale estimated only from training data. Logistic and tree candidates use classifier probabilities.
- The state model uses a supervised Gaussian Markov approximation with smoothed transition counts. This is deterministic and robust on small fixtures; diagnostics disclose the approximation and whether statsmodels is installed.
- Promotion requires no failed fold, enough successful folds, the configured ratio of fold-level Sharpe improvements, overall Sharpe improvement, and no drawdown deterioration beyond tolerance. The default remains the rule baseline.

## Risks

- Tree feature importance is global and associative, not causal; the prediction diagnostics state this explicitly. SHAP is intentionally not added as another dependency.
- LightGBM on the current Python 3.14 environment emits a harmless scikit-learn feature-name warning for list-based prediction; predictions and tests pass.
- No candidate should be called superior until the comparator runs against governed point-in-time data spanning multiple market regimes. Fixture success proves contracts, not investment efficacy.
- The Markov approximation needs at least two observed states; absent business regimes are explicitly listed in diagnostics rather than synthesized.

## Dependencies

- T-584 supplies baseline allocation and backtest semantics.
- scikit-learn, statsmodels, XGBoost, and LightGBM are optional research dependencies and are lazily discovered and imported.
- The current `.venv` contains all four packages; normal application import does not require them.

## Blockers

- No blocker in T-585 implementation scope.
- Production efficacy comparison remains pending governed point-in-time history; this does not block the candidate and comparison contracts.

## Artifacts

- No generated artifact was committed. Test output is local-only evidence, produced by the commands above on 2026-07-17, owner group Research and AI Workflows, contains no sensitive data, and is not acceptable as non-local production release evidence.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [ ] `tasks/todo.md` status updated if roadmap state changed (parent PM owns roadmap integration)

## Handoff Checklist

- [x] Candidate contracts and lazy imports completed
- [x] Chronological comparison and conservative promotion completed
- [x] Focused and dynamic-allocation tests passed
- [x] Security and handoff checks run
- [x] Paper-only and no-broker boundaries preserved
- [ ] Roadmap status update by parent PM agent

## Evidence

- `.venv/bin/python -m unittest tests.dynamic_allocation.test_ml_models -v`: 7 passed; local-only verification on 2026-07-17; no sensitive data; not non-local release evidence.
- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v`: 36 passed; local-only integration verification on 2026-07-17; no sensitive data; not non-local release evidence.
- `python3 scripts/security_check.py .`: passed across 381 files; local-only verification on 2026-07-17; no sensitive data; not non-local release evidence.
- `python3 scripts/check_handoffs.py`: passed after required headings were added; local-only documentation verification on 2026-07-17.

## Next Steps

1. Platform and Quality reviews the fixed walk-forward thresholds against the first governed historical dataset.
2. Integrate the comparator behind the dynamic-allocation evaluation service without changing risk-cap precedence.
3. Keep `rule_baseline` selected until stored OOS evidence passes every promotion gate.

## Next Recommended Action

The parent PM should review the integrated dynamic-allocation test run, update T-585 roadmap status, and keep the rule baseline selected until a governed point-in-time comparison produces stored stable OOS evidence.
