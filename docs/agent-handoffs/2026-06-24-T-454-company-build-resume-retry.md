# Handoff: T-454 Company Build Resume And Retry

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence, Product and UI
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-454

## Objective

Add local retry/resume semantics to company database batch builds so long-running补库 work can be recovered from persisted run history and reviewed without returning oversized batch payloads by default.

## Scope

- In scope: `CompanyDatabaseBuildRun` metadata, batch-build failure recording, retry/resume API, run-history slim responses, tests, API/data-structure docs, roadmap and handoff.
- Out of scope: external crawling, new paid/token data sources, background job engine, UI trend chart, real broker integration, real trading.

## Background

T-451 persisted company database build runs, T-452 exposed recent run history in the workbench, and T-453 added coverage trend reporting. The next roadmap gap was that failed long-running补库 work could still disappear as a 500 response without a recoverable run record, and large run-history responses returned full nested batch payloads by default.

## Problem Statement

The company intelligence platform needs an operationally usable company database, but a failed batch run should not force the user to guess which companies were completed or manually reconstruct the next attempt. Run history also needs to remain readable when the target set grows beyond a few companies.

## Expected Deliverables

- Add retry/resume metadata to `CompanyDatabaseBuildRun`.
- Persist failed or partial batch runs.
- Add a local retry/resume API over existing run history.
- Support `resume_run_id` on the existing batch-build endpoint.
- Slim run-history responses by default.
- Cover the behavior with focused regression tests and docs.

## Current Findings

- Existing runs already store target issuers, options, totals, coverage snapshots and batch details.
- The generic JSON record store can load new dataclass fields with defaults, so the model can be extended compatibly.
- Current batch execution is synchronous; this task should not invent a background job engine.
- UI run-history rows only need summary fields, not full nested `batches`.

## Proposed Work Plan

1. Extend `CompanyDatabaseBuildRun` with retry/resume fields and `partial` status.
2. Refactor batch build to record failed/partial runs on exceptions.
3. Add retry/resume replay from source runs.
4. Slim run-history serialization unless `include_batches=true`.
5. Update tests, docs and handoff.

## Validation Plan

- Compile Python modules and scripts.
- Run focused company database retry/resume tests.
- Run full clean-env unit tests.
- Run UI static check, security check, handoff validation and diff whitespace check.

## Current State

- Completed: `CompanyDatabaseBuildRun` now records `retry_of`, `resume_of`, `resume_mode`, `attempt`, `idempotency_key`, `completed_issuer_ids` and `skipped_issuer_ids`.
- Completed: run status accepts `partial` in addition to `dry_run`, `executed` and `failed`.
- Completed: `POST /api/company-database/batch/build` supports `resume_run_id`; failed/partial source runs default to `remaining` mode.
- Completed: `POST /api/company-database/batch/runs/{run_id}/retry` replays a persisted local run and writes a new run by default.
- Completed: batch-build failures persist a `failed` or `partial` run with completed issuers, batches, error and coverage snapshots before the API returns failure.
- Completed: run-history listing supports `run_id` filtering and defaults to slim rows with `batches=[]`; callers can request full batch details using `include_batches=true`.
- Blocked: none.

## Files Touched

- `app/models.py`: extended `CompanyDatabaseBuildRun` retry/resume fields and `partial` status.
- `app/api.py`: added retry route and handler.
- `app/services.py`: added retry/resume replay, failed/partial run recording, idempotency key generation and slim run-history serialization.
- `tests/test_system.py`: added tests for slim/full run history, retry route replay, `resume_run_id` remaining-mode replay and partial failure recording.
- `docs/api-contracts.md`: documented retry/resume request fields, retry endpoint and slim history responses.
- `docs/data-structure-design.md`: documented retry/resume fields and `partial` semantics.
- `docs/README.md`: updated doc index task range.
- `docs/agent-handoffs/README.md`: added T-454.
- `tasks/todo.md`: added T-454 as done with follow-ups.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py && python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_batch_retry_replays_source_run tests.test_system.SystemServiceTests.test_company_database_batch_resume_run_id_retries_remaining_issuers tests.test_system.SystemServiceTests.test_company_database_batch_records_partial_run_on_failure tests.test_system.SystemServiceTests.test_company_database_coverage_trends_filters_by_issuer_and_status
```

Result:

- Passed: Python compile.
- Passed: focused company database retry/resume/history tests, 5 tests.
- Passed: full clean-env unit test discovery, 231 tests.
- Passed: UI static check.
- Passed: security check.
- Passed: diff whitespace check.
- Passed: handoff validation.
- Failed: none.

## Decisions

- Retry/resume uses persisted local run history, not a new async job engine.
- `resume_run_id` is supported on the existing batch-build endpoint for compatibility, while a dedicated retry route is also available for explicit user flows.
- Failed runs are persisted before the API reports failure so the user can inspect and retry them.
- Run history defaults to slim batch rows to keep large company-universe runs usable in the UI and API.
- The feature remains local research operations only; it does not add real trading, broker connectivity or automatic external crawling.

## Dependencies

- T-451 `CompanyDatabaseBuildRun` persistence and `/api/company-database/batch/runs`.
- T-452 UI run-history summary, which relies on slim run rows remaining summary-compatible.
- T-453 coverage trends, which consume run status, coverage snapshots and totals.

## Blockers

- None.

## Risks and Open Questions

- There is still no background scheduler or durable worker heartbeat; this is a local synchronous retry/resume layer.
- Partial progress is tracked at company/batch granularity, not at sub-step granularity inside profile/event/relationship/workflow builders.
- UI can later expose retry buttons and coverage-trend charting as T-455/T-456 follow-ups.

## Artifacts

- None committed. Any run-history records are local JSON/SQLite/PostgreSQL records, not production release evidence.

## Handoff Checklist

- [x] Model fields added.
- [x] API route added.
- [x] Resume via existing batch-build endpoint added.
- [x] Failed/partial run persistence added.
- [x] Slim run-history response added.
- [x] Tests added.
- [x] Docs and todo updated.
- [x] Final handoff validation rerun after this structure update.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py && python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_batch_retry_replays_source_run tests.test_system.SystemServiceTests.test_company_database_batch_resume_run_id_retries_remaining_issuers tests.test_system.SystemServiceTests.test_company_database_batch_records_partial_run_on_failure tests.test_system.SystemServiceTests.test_company_database_coverage_trends_filters_by_issuer_and_status
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: compile, focused tests, full 231-test suite, UI static check, security check, handoff validation and diff whitespace check.

## Next Steps

1. T-455: expose coverage trend rows in the company intelligence UI.
2. T-456: audit deep company-profile field coverage and source plan.
3. T-457: extract richer company profile facts from already-ingested official disclosures and company IR documents.

## Next Recommended Action

Implement T-455 so the UI can display the T-453 coverage trend rows and T-454 retry/resume status without requiring raw JSON inspection.
