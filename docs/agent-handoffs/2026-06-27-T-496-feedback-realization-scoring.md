# Handoff: T-496 Feedback Realization Scoring

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-496

## Objective

Make the system answer whether a paper-only research conclusion worked. The implementation links `AnalysisConclusion`, `SimulationFeedback`, local market windows, benchmark comparison, drawdown, error attribution, and human review next actions without changing public API URLs or connecting to brokers.

## Scope

- In scope: feedback realization scoring module, existing simulation feedback performance update facade, company intelligence UI summary, focused regression, task status, and handoff.
- Out of scope: broker integration, live execution, automated orders, database schema migration, external benchmark data ingestion, production investment advice.

## Background

Before T-496, simulation feedback could store latest-close performance but did not expose conclusion realization status, event window return, relative benchmark return, drawdown, prediction error attribution, or human review scoring as a coherent product surface. T-503 also requires new service logic to move toward domain modules instead of growing `app/services.py`.

## Problem Statement

Personal users need to see whether a research conclusion was validated, missed, or still mixed. The UI should show this as a readable "结论兑现" item, while raw feedback objects and trace fields remain available through advanced details.

## Expected Deliverables

- Domain scoring module for paper-only feedback realization.
- Existing `/api/simulation-feedback/performance/update` enriched with realization fields while keeping URL and payload compatibility.
- `SimulationFeedback.performance`, `validation`, and `review_result` populated with:
  - `realization_status`
  - `event_window_return`
  - `relative_benchmark_return`
  - `max_drawdown`
  - `prediction_error_attribution`
  - `manual_review_score`
  - `next_action`
- Company intelligence UI displays conclusion realization by default.
- Focused tests cover conclusion linkage, market window, benchmark comparison, review result, and paper-only boundaries.

## Current Findings

- `AnalysisConclusion` and `SimulationFeedback` already had flexible `performance`, `validation`, and `review_result` dict fields, so no schema migration was needed.
- `SystemService.update_simulation_feedback_performance` was the correct compatibility facade because existing workflows and UI already call it.
- Market data can be queried from direct stores or in-memory stores; the facade now gathers the point window and passes it to the domain scoring module.

## Proposed Work Plan

1. Add `app/service_modules/feedback_scoring.py` with pure scoring logic.
2. Keep `SystemService` responsible for filtering rows, loading market windows, persistence, auditing, and commit.
3. Enrich the existing performance update response and stored feedback objects.
4. Add UI formatting for "结论兑现" in company intelligence actions and personal summary.
5. Add focused regression and run the standard checks.

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_simulation_feedback_performance_update_uses_latest_market_data tests.test_system.SystemServiceTests.test_simulation_feedback_realization_scoring_links_conclusion_market_window_and_review`
- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/security_check.py .`

## Risks

- Realization thresholds are intentionally simple: 3% positive/negative bands. They are suitable for a local product baseline, not an investment recommendation.
- A feedback row without benchmark data still receives an event-window score, but relative benchmark fields remain null and attribution records a benchmark gap.
- Human review score is a preserved optional field, not an automated judgment.

## Dependencies

- Existing analysis conclusion and simulation feedback models.
- Existing public/local market data points.
- T-494 company intelligence UI structure.
- T-503 direction to keep new service logic in domain modules where practical.

## Blockers

- None for local T-496 completion.

## Handoff Checklist

- [x] Feedback scoring domain module added.
- [x] Existing performance update facade preserved.
- [x] Paper-only/no-broker/no-auto-trading boundary retained.
- [x] Company intelligence UI shows conclusion realization by default.
- [x] Focused regression added and passed.
- [x] `tasks/todo.md` marked T-496 DONE.

## Evidence

- `app/service_modules/feedback_scoring.py`: pure realization scoring logic.
- `app/services.py`: facade loads market windows, delegates scoring, persists performance/review fields.
- `app/static/index.html`: `feedbackRealizationSummary()` and "结论兑现" action rows.
- `tests/test_system.py`: `test_simulation_feedback_realization_scoring_links_conclusion_market_window_and_review`.
- Focused regression result: two simulation feedback tests passed.
- `python3 scripts/ui_research_workbench_matrix.py http://127.0.0.1:8013 --output-dir artifacts/t496-ui-research-workbench-matrix --timeout 60`: passed 16 desktop/mobile browser checks; failure count 0; console error count 0; artifact is local-only and not acceptable for non-local release gates.

## Next Recommended Action

Proceed to T-497 event and relationship credibility, deduplication, and merge enhancement. Reuse the same pattern: keep `SystemService` as facade and move domain quality logic into a dedicated module.
