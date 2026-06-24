# Handoff: T-451 Company Database Build Run History

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-451

## Objective

Persist company database batch build runs so补库 operations can be audited, queried and later extended into resumable runs, retries and coverage trends.

## Scope

- In scope: data model, store collection registration, batch build service response, run-history query API, tests, API/data-structure docs, roadmap and handoff updates.
- Out of scope: scheduler integration, resumable execution implementation, UI run-history table, external artifact export, real broker integration and live trading.

## Background

T-446 added batch company database build orchestration, but results only lived in the one API response. The company intelligence platform needs durable local operations history so analysts can know which companies were processed, what was planned or executed, what coverage changed and which options were used.

## Problem Statement

Without a run record, long-running补库 work cannot be audited after the response disappears. It is also hard to build later features such as retry, resume, coverage trends and UI operation summaries.

## Expected Deliverables

- Add a first-class `CompanyDatabaseBuildRun` model.
- Persist run records through the existing SQLite/PostgreSQL JSON records store.
- Record batch build execution by default and dry-run only when explicitly requested.
- Add a run-history query endpoint.
- Add regression tests and update docs.

## Current State

- Completed: `CompanyDatabaseBuildRun` model added.
- Completed: `company_database_build_runs` registered in the store.
- Completed: `POST /api/company-database/batch/build` returns `run_id`, `run_recorded`, `coverage_before`, `coverage_after` and optional `run`.
- Completed: execute mode records runs by default; dry-run requires `record_run=true`.
- Completed: `GET|POST /api/company-database/batch/runs` lists run history by issuer/status.
- Completed: batch build now passes structured disclosure and disclosure candidate flags into event/relationship builders.
- Completed: full validation.
- Blocked: none.

## Current Findings

- Existing JSON records storage is sufficient for this object; a typed PostgreSQL table can wait until query volume requires it.
- Existing batch build already had all necessary totals and batch details.
- Run history is operations metadata only and remains separate from trading or production release evidence.

## Proposed Work Plan

1. Add the model and store registration.
2. Capture run snapshots inside the existing batch build flow.
3. Add a narrow list endpoint and focused tests.
4. Leave resume/retry/UI history to follow-up tasks.

## Validation Plan

- Compile changed Python files.
- Run focused batch build run-history tests.
- Run handoff validation.
- Run full `make local-ci` before closeout if feasible.

## Files Touched

- `app/models.py`: added `CompanyDatabaseBuildRun`.
- `app/store.py`: added collection, aliases, datetime hydration and in-memory field.
- `app/services.py`: records batch build runs and lists run history.
- `app/api.py`: added `/api/company-database/batch/runs`.
- `tests/test_system.py`: added run-history regression tests.
- `docs/api-contracts.md`: documented run-history request/response and endpoint.
- `docs/data-structure-design.md`: documented `CompanyDatabaseBuildRun`.
- `tasks/todo.md`: added T-451.
- `docs/README.md`: updated task range and data-structure summary.
- `docs/agent-handoffs/README.md`: added T-451.
- `docs/agent-handoffs/2026-06-24-T-451-company-database-build-run-history.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/models.py app/store.py app/services.py app/api.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_aggregates_batches_and_coverage tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_batch_build_dry_run_history_is_explicit
python3 scripts/check_handoffs.py
make local-ci
```

Result:

- Passed: Python compile for changed backend modules.
- Passed: focused run-history tests.
- Passed: handoff validation.
- Passed: full `make local-ci`, including compile, 226 tests, UI static check, security check and handoff validation.

## Decisions

- Execute-mode batch builds record runs by default; dry-run history is opt-in via `record_run=true` to avoid noisy preview history.
- Run records include full batch details for now; future UI can summarize without needing to rerun operations.
- The usage boundary explicitly states local research operations history and no live trading.

## Dependencies

- Existing company database batch build flow.
- Existing store JSON records persistence.
- Existing company database coverage audit for before/after snapshots.

## Blockers

- None for this slice.

## Risks and Open Questions

- Full batch details can become large for market-wide runs; future work should add artifact output and summarized persisted rows.
- Resume/retry semantics are not implemented yet.
- UI does not yet show run history.

## Artifacts

- None produced.

## Handoff Checklist

- [x] Model added.
- [x] Store collection added.
- [x] Service records runs.
- [x] Query endpoint added.
- [x] Focused tests added.
- [x] Docs and todo updated.
- [x] Full local validation completed.

## Evidence

Commands run:

```bash
python3 -m py_compile app/models.py app/store.py app/services.py app/api.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_aggregates_batches_and_coverage tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_batch_build_dry_run_history_is_explicit
python3 scripts/check_handoffs.py
make local-ci
```

Result:

- Passed: backend compile and focused tests.
- Passed: handoff validation.
- Passed: full local CI with 226 unit tests.

## Next Steps

1. Add a compact UI run-history table.
2. Add resume/retry semantics for failed or partial batch runs.
3. Add optional artifact output for large market-wide build runs.

## Next Recommended Action

After validation, add a compact UI run-history table and operation summaries for coverage audit, batch build and report realization.
