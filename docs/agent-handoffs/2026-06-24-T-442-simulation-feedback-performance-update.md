# Handoff: T-442 Simulation Feedback Performance Update

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-442

## Objective

Make paper-only simulation feedback useful for validating analysis conclusions by updating feedback performance from local market data.

## Scope

- In scope: simulation feedback performance update API, local latest-market calculation, focused regression test, API/todo/handoff documentation.
- Out of scope: broker integration, real orders, portfolio accounting, benchmark-relative performance, drawdown windows, analyst reliability recomputation.

## Background

T-440 created `SimulationFeedback` records as watch-only feedback attached to company baseline conclusions. Those records were visible in the company intelligence workbench, but their performance fields stayed pending. The user wants simulation feedback to validate whether analysis conclusions worked, so the feedback layer needs a local market-data update path.

## Problem Statement

Static paper feedback does not close the analysis loop. The system needs a safe, local-only way to update performance without implying real trading or broker execution.

## Expected Deliverables

- `POST /api/simulation-feedback/performance/update` defaults to dry-run.
- The endpoint filters by feedback ID, symbol or issuer.
- The endpoint uses latest local `MarketDataPoint` and entry price to compute paper return.
- The endpoint updates `performance`, `validation` and `review_result` only when `execute=true`.
- The endpoint always returns `paper_only=true` and `live_execution_allowed=false`.
- Focused tests cover dry-run and execute.

## Current Findings

- Added API route and service method.
- Added latest-market helper for feedback performance.
- Added focused regression test.
- Updated API contracts, todo and docs index.

## Proposed Work Plan

1. Treat this as the first paper-feedback measurement slice.
2. Add benchmark-relative returns and drawdown windows later.
3. Add event-window validation and viewpoint realization updates after richer event data is available.

## Validation Plan

- Compile changed API, service, script and test files.
- Run focused feedback performance regression.
- Run adjacent company builder regressions.
- Run handoff validation.

## Decisions

- The update uses latest local close versus stored `entry_price`.
- If entry price is missing but latest price exists, the endpoint initializes a paper baseline instead of creating a trade.
- Human review remains required via `review_result.status=pending_review`.
- No broker or live execution fields can be enabled by this endpoint.

## Risks and Open Questions

- Latest close versus entry price is a minimal metric; it does not yet capture maximum drawdown or benchmark-relative behavior.
- A same-day baseline can produce near-zero holding period; later review windows should be explicit.
- Feedback quality depends on market-data freshness.

## Dependencies

- Existing `SimulationFeedback`, `AnalysisConclusion` and `MarketDataPoint` models.
- Existing company target resolution and local market-data store.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Performance update API added.
- [x] Paper-only boundary preserved.
- [x] Focused tests passed.
- [x] API contracts, todo and docs index updated.
- [x] Handoff validation passed.

## Evidence

Files changed:

- `app/api.py`: added `/api/simulation-feedback/performance/update`.
- `app/services.py`: added `update_simulation_feedback_performance` and latest market helper.
- `tests/test_system.py`: added feedback performance regression.
- `docs/api-contracts.md`: documented endpoint.
- `tasks/todo.md`: added T-442 completion entry.
- `docs/README.md`: updated task range through T-442.
- `docs/agent-handoffs/README.md`: added T-442 to related tasks.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_simulation_feedback_performance_update_uses_latest_market_data
python3 -m unittest tests.test_system.SystemServiceTests.test_simulation_feedback_performance_update_uses_latest_market_data tests.test_system.SystemServiceTests.test_company_workflow_builder_creates_observation_conclusion_and_paper_feedback tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports
docker compose restart ai-quant-org
curl -sS --max-time 60 -X POST 'http://127.0.0.1:8000/api/simulation-feedback/performance/update' -H 'Content-Type: application/json' -H 'X-Role: analyst' -H 'X-Actor: company_database_builder' -d '{"symbols":["AAPL","NVDA","600519"],"limit":20,"execute":true}'
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile.
- Passed: focused feedback performance test.
- Passed: focused feedback, workflow, relationship, event and company database builder test group.
- Passed: local sample performance update for AAPL, NVDA and 600519; three feedback records updated and zero skipped.
- Passed: handoff validation.
- Not run: full `make local-ci`; this is a focused feedback slice and the worktree already contains broad unrelated changes.

Artifacts:

- None required.

## Next Recommended Action

Add benchmark-relative feedback metrics, viewpoint realization checks and analyst reliability score updates so the platform can evaluate which analysis sources and analysts have better historical reliability.
