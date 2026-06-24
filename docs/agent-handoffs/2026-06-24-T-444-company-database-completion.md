# Handoff: T-444 Company Database Completion Through T-447

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Research and AI Workflows, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related tasks: T-444, T-445, T-446, T-447

## Objective

Complete the next company database usability layer after T-443: review relationship candidates, audit company database coverage, batch-build company records, and update research report realization from local market data.

## Scope

- In scope: service/API endpoints, focused regression tests, API contracts, todo roadmap entries, handoff/index updates.
- Out of scope: relationship review UI, external crawling, LLM relationship extraction, real broker integration, trading recommendations, full production release evidence.

## Background

T-437 through T-443 made company profiles, events, relationships, workflow feedback and disclosure relationship candidates available. The remaining gap was operational usability: users needed a way to promote or reject candidates, see which company database layers are missing, batch-build many companies, and evaluate whether structured research report target prices were realized.

## Problem Statement

The company database had enough first-class objects to display records, but it still lacked four operating controls: candidate relationship promotion, per-company completeness diagnostics, batch completion, and research report realization review. Without these controls, users could see data but could not efficiently make it more trustworthy or measure whether report views were useful.

## Expected Deliverables

- `POST /api/company-relationships/{relationship_id}/review` supports approve, reject and merge.
- `GET|POST /api/company-database/coverage/audit` reports missing company database sections.
- `POST /api/company-database/batch/build` orchestrates profile, event, relationship and workflow builders in batches.
- `POST /api/research-reports/realization/update` updates target-price forecast/viewpoint realization and analyst reliability scores.
- Focused regression tests cover all four flows.
- API contracts, roadmap and handoff records are updated.

## Current State

- Completed: `POST /api/company-relationships/{relationship_id}/review` supports `approve`, `reject` and `merge`.
- Completed: `GET|POST /api/company-database/coverage/audit` reports per-company section availability, missing sections, counts and coverage score.
- Completed: `POST /api/company-database/batch/build` batches the existing profile, event, relationship and workflow builders and returns `coverage_after`.
- Completed: `POST /api/research-reports/realization/update` updates target-price forecasts/viewpoints from local latest market data and can recompute analyst reliability scores.
- Not started: UI review queue and richer benchmark-relative scoring.
- Blocked: none for this slice.

## Current Findings

- The existing `CompanyRelationship` model can carry review states in `review_status`; relationship status already supports `active`, `inactive` and `unknown`.
- Existing builder functions can be safely composed for batch builds without duplicating data-generation logic.
- Existing `ReportForecast`, `ReportViewpoint` and `AnalystReliabilityScore` models can support a first realization update using local latest close.
- The UI static contract is unaffected by this backend slice.

## Proposed Work Plan

1. Keep T-444 through T-447 as backend/data-contract completion work.
2. Use focused tests to lock each new endpoint before broader CI.
3. Treat UI panels, resumable batch artifacts and richer scoring as follow-up tasks.

## Validation Plan

- Compile changed Python files.
- Run focused tests for coverage audit, batch build, relationship review and report realization.
- Run UI static check because route/data additions may be surfaced by the existing workbench later.
- Run security check and handoff validation.
- Run full unit tests before final closeout if the current environment allows it.

## Files Touched

- `app/api.py`: added routes and router handlers for coverage audit, batch build, relationship review and report realization update.
- `app/services.py`: added service implementations for coverage audit, batch build, candidate relationship review and research report realization updates.
- `tests/test_system.py`: added focused regression coverage for all four new flows.
- `docs/api-contracts.md`: documented new endpoints and boundaries.
- `tasks/todo.md`: added DONE entries for T-444 through T-447.
- `docs/README.md`: updated documentation index to include T-447.
- `docs/agent-handoffs/README.md`: updated handoff related task range.
- `docs/agent-handoffs/2026-06-24-T-444-company-database-completion.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_coverage_audit_reports_missing_sections tests.test_system.SystemServiceTests.test_company_database_batch_build_aggregates_batches_and_coverage tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates tests.test_system.SystemServiceTests.test_research_report_realization_update_recomputes_target_price_and_analyst_score
python3 -m py_compile app/api.py app/services.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
```

Result:

- Passed: four focused regression tests.
- Passed: Python compile for changed code/test files.
- Passed: UI static check.
- Passed: handoff validation.
- Passed: full `python3 -m unittest discover -s tests` with 223 tests.

## Decisions

- Relationship candidates stay conservative until reviewed; `approve` promotes to active, `reject` disables, and `merge` preserves backlinks on the target.
- Coverage score is a local completeness metric, not a source-quality score or investment signal.
- Batch build composes existing builders instead of duplicating profile/event/relationship/workflow logic.
- Research report realization uses latest local close versus target price as the minimum review metric; it remains an opinion-layer reliability check.
- All new flows preserve local-only, paper-only and no-real-trading boundaries.

## Dependencies

- Existing `CompanyRelationship`, `CompanyProfile`, `CompanyEvent`, `ObservationItem`, `AnalysisConclusion`, `SimulationFeedback`, `ResearchReport`, `ReportViewpoint`, `ReportForecast` and `AnalystReliabilityScore` models.
- Existing company target resolution and profile/event/relationship/workflow builder methods.
- Existing local `MarketDataPoint` records for realization and feedback performance updates.

## Blockers

- None for this slice.

## Risks and Open Questions

- Relationship review lacks a UI queue, role-specific review workflow and bulk actions.
- Coverage audit does not yet emit versioned artifacts or market/industry rollups.
- Batch build does not yet have resumable run IDs, retries or persistent run history.
- Report realization needs target-price horizons, rating-direction accuracy, earnings actuals and benchmark-relative returns for higher-quality analyst scoring.

## Handoff Checklist

- [x] Relationship review endpoint added.
- [x] Coverage audit endpoint added.
- [x] Batch build endpoint added.
- [x] Research report realization endpoint added.
- [x] Focused regression tests added and passed.
- [x] API contracts updated.
- [x] `tasks/todo.md` updated with T-444 through T-447.
- [x] Handoff and docs indexes updated.

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_coverage_audit_reports_missing_sections tests.test_system.SystemServiceTests.test_company_database_batch_build_aggregates_batches_and_coverage tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates tests.test_system.SystemServiceTests.test_research_report_realization_update_recomputes_target_price_and_analyst_score
python3 -m py_compile app/api.py app/services.py tests/test_system.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
python3 -m unittest discover -s tests
make local-ci
```

Result:

- Passed: focused regression tests.
- Passed: Python compile checks.
- Passed: UI static check.
- Passed: security check.
- Passed: handoff validation.
- Passed: full unit test suite, 223 tests.
- Passed: `make local-ci`, including compile, 223 tests, UI static check, security check and handoff validation.

## Artifacts

- None produced. All checks were local command outputs; no production-grade artifacts or external evidence were generated.

## Next Recommended Action

1. Add UI panels for coverage audit, relationship candidate review and report realization jobs.
2. Add resumable batch build `run_id` and artifact output for long local database completion runs.
3. Extend analyst reliability scoring with target horizons, rating direction, earnings actuals and benchmark-relative performance.
