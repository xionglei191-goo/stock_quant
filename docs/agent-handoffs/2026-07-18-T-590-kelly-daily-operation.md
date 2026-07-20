# Handoff: T-590 Auditable Kelly Inputs and Daily Paper Operation

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex `/root`
- Branch/worktree: shared current worktree
- Artifact classification: local-only

## Objective

Replace the current missing-Kelly-input warning with a conservative, source-linked estimator when sufficient public SPY history exists, then produce a repeatable daily paper-operation report and append-only snapshot evidence.

## Scope

- In scope: dynamic-allocation risk estimator, configuration, application decision lineage, daily local runner, focused tests, local runtime evidence, docs, and roadmap state.
- Out of scope: broker connectivity, order execution, investment advice, paid data, historical-vintage claims, and fabricated financial benefit.

## Background

T-589 connected all 38 public-data series but left Kelly unavailable because no expected-return or volatility contract supplied current inputs. The dashboard therefore showed a conservative fallback warning even though governed SPY return history was present.

## Problem Statement

Silently inserting arbitrary Kelly defaults would violate explainability, while leaving the cap permanently unavailable wastes the existing audited history. Daily operation also lacked one command joining refresh, decision persistence, immutable paper evidence, and an operator-facing report.

## Expected Deliverables

- A source-linked, conservative Kelly input estimator with explicit fallback behavior.
- API and Dashboard disclosure of the estimate and binding cap.
- An execute-gated daily runner, hash-chain ledger, and local-only operational report.
- Focused and full repository verification plus a real current run.

## Acceptance

- Explicit `expected_return` and `volatility` remain authoritative and must be supplied together.
- Automatic estimates use at least 24 non-overlapping quarter-end SPY three-month return observations, disclose method/sample/caps/confidence, and degrade safely when unavailable.
- Current paper decision persists the estimate lineage and applies `min(requested, Kelly, risk, maximum)`.
- One explicit daily command refreshes governed public data, persists the decision, appends a hash-chained local paper snapshot, and writes a local-only operational report.
- Focused tests, runtime replay, handoff validation, and final `make local-ci` pass.

## Current State

- Completed: estimator, YAML policy, application/API/Dashboard integration, daily runner, real idempotent execution, responsive acceptance, documentation, roadmap, and all gates.
- In progress: none.
- Not started: none in scope.
- Blocked: none.

## Current Findings

- The current 10-year window contains 40 non-overlapping quarterly samples.
- Geometric annual return of 15.25% is capped at 12%; annualized volatility is 16.96%; 35% confidence and Quarter Kelly produce a 36.52% equity cap.
- The real strict daily run has 38/38 fresh series, 8/8 ready factors, 11,902 duplicate observations, zero insert conflicts, and a valid one-record hash chain.

## Proposed Work Plan

1. Expose the estimator and method/sample lineage in the current decision.
2. Add the read-only/execute-gated daily runner and real evidence.
3. Validate API, Streamlit desktop/mobile rendering, security, docs, handoffs, and full tests.

## Validation Plan

- Focused estimator/application/pipeline/daily-run/dashboard tests.
- Identical real daily command executed twice to prove SQLite and JSONL idempotence.
- API current payload inspection and desktop/mobile Streamlit acceptance.
- Final `make local-ci PYTHON=.venv/bin/python`, handoff validation, and diff checks.

## Dependencies

- Existing governed FRED, Cboe, FINRA, and Yahoo public-data pipeline.
- `data/local/dynamic_allocation.sqlite` and the existing `return_3m` series.
- Local Streamlit/API runtime; no external broker or paid source.

## Blockers

- None for local paper operation.
- Financial efficacy remains time-dependent evidence, not a code blocker.

## Handoff Checklist

- [x] Conservative estimator and explicit-input precedence implemented
- [x] Focused tests pass
- [x] Real daily execution and idempotent replay pass
- [x] API and desktop/mobile dashboard acceptance pass
- [x] Full repository quality gate passes
- [x] Roadmap and final evidence reconciled

## Files Touched

- `app/dynamic_allocation/risk/estimator.py`: non-overlapping quarterly historical estimator and audit contract.
- `app/dynamic_allocation/application.py`: explicit/estimated input selection, lineage, risk snapshot, and API payload.
- `app/dynamic_allocation/dashboard/presentation.py`, `app/dynamic_allocation/dashboard/app.py`: stable Kelly input view model and compact sample disclosure.
- `config/dynamic_allocation.yaml`: versioned estimator lookback, sample threshold, cap/floor, and confidence.
- `scripts/dynamic_allocation_daily_run.py`: read-only preview and explicit strict execute path.
- `tests/dynamic_allocation/`: estimator, precedence, daily operation, pipeline, and Dashboard regressions.
- `README.md`, `docs/api-contracts.md`, `tasks/todo.md`: operator command, contract, limitations, and roadmap evidence.

## Commands Run

```bash
.venv/bin/python -m unittest tests.dynamic_allocation.test_daily_run tests.dynamic_allocation.test_kelly_estimator tests.dynamic_allocation.test_application tests.dynamic_allocation.test_public_data_pipeline -v
.venv/bin/python scripts/dynamic_allocation_daily_run.py --as-of 2026-07-18T00:15:00+08:00 --market-start 2000-01-01 --execute --ledger data/local/dynamic-allocation-paper.jsonl --output artifacts/dynamic-allocation/daily-run-latest.json
.venv/bin/python scripts/dynamic_allocation_dashboard_acceptance.py http://127.0.0.1:8502 --output-dir /tmp/t590-dashboard-acceptance --timeout 45
make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: focused suites; identical real daily command twice; API current payload; desktop 1440x1000 and mobile 390x844; 423 repository tests and every local gate.
- Failed: none at closure. One initial TDX CLI persistence audit and one test-double mismatch were fixed and covered before the final pass.
- Not run: non-local staging/production gates, because all artifacts and operation are explicitly local-only.

## Evidence

- `artifacts/dynamic-allocation/daily-run-latest.json`: generated by the T-590 daily command; local-only, no secrets, not valid for non-local release.
- `data/local/dynamic-allocation-paper.jsonl`: one validated hash-chain record after two identical runs; ignored local-only state.
- `data/local/dynamic_allocation.sqlite`: 11,902 observations across 38 series and two persisted decisions; ignored local-only state.
- `/tmp/t590-dashboard-acceptance/`: desktop/mobile local screenshots; 2 Plotly charts, 19 tables, zero exceptions, and zero horizontal overflow in both viewports.
- `make local-ci PYTHON=.venv/bin/python`: 423 tests passed; UI static, security (381 files, zero findings), 224-file Markdown, 167-file handoff, and canonical metadata gates passed.

## Decisions

- Use non-overlapping March/June/September/December observations from `return_3m`; this avoids treating overlapping monthly windows as independent samples.
- Use a 10-year lookback, 24-sample minimum, 12% expected-return cap, 8% volatility floor, 35% confidence shrink, and Quarter Kelly.
- Never mix one caller-supplied input with one estimated input; incomplete explicit input remains unavailable and visible.
- Treat current-vintage source history as suitable for current paper sizing only, not as historical walk-forward evidence.

## Risks and Open Questions

- The estimate uses SPY as a conservative proxy for the SPY/QQQ equity sleeve and is not a return forecast guarantee.
- A daily runner proves operational repeatability immediately; investment efficacy still requires the stated 6-12 month paper observation window.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain placement: all behavior is under `app/dynamic_allocation/` and a thin operator script.
- Focused regression: estimator, application, public pipeline, paper snapshot, and daily-run tests.
- Contract/boundary changes: API decision payload gains `kelly_input`; no storage schema, broker, live execution, or paper-only boundary changes.

## Next Steps

1. Implement and test the daily runner.
2. Execute it against the governed local public-data state and verify the JSONL chain.
3. Run all repository gates and mark the handoff DONE only after evidence is recorded.

## Next Recommended Action

Run the documented daily command after US market close and accumulate at least 6-12 months of paper evidence before evaluating risk-adjusted return or drawdown benefit.
