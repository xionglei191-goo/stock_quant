# Handoff: T-453 Company Coverage Trends

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-453

## Objective

Add a local coverage trend report over persisted company database build runs so analysts can review whether repeated补库 operations improve company profile, event, relationship, research viewpoint, observation, conclusion and simulation feedback coverage.

## Scope

- In scope: API route, service trend calculation, optional local JSON artifact output, unit tests, API/data-structure docs, roadmap and handoff updates.
- Out of scope: UI trend chart, resumable batch execution, failed-run retry, new external crawling, real broker integration and production release evidence.

## Background

T-451 records `CompanyDatabaseBuildRun` with before/after coverage snapshots. T-452 exposes recent runs in the workbench. The missing backend piece is a trend report that turns those snapshots into deltas and optional local evidence for personal research operations.

## Problem Statement

Single run history answers "what just ran" but not "is the company database getting better over time." Without trend rows, the user cannot review whether补库 is reducing missing sections or improving coverage across repeated local runs.

## Expected Deliverables

- Add `GET|POST /api/company-database/coverage/trends`.
- Filter trends by `issuer_id`, `status` and `limit`.
- Derive per-run coverage and missing-section deltas from persisted run snapshots.
- Add optional `write_artifact=true` local JSON output with strict local-only boundary.
- Add regression tests and docs.

## Current Findings

- Existing `CompanyDatabaseBuildRun.coverage_before` and `coverage_after` already contain `average_coverage_score`, `missing_counts` and company-level rows.
- No new data source or crawler is required.
- Dry-run records may represent planned coverage rather than actual persisted improvement, so the status stays visible in every trend row.
- Large run details can be heavy; trend rows intentionally summarize totals and deltas instead of returning full `batches`.

## Proposed Work Plan

1. Add route and service method beside run-history APIs.
2. Add helpers to compute coverage score, missing counts and deltas.
3. Add optional local artifact writing.
4. Add tests for trend summary, filters and artifact output.
5. Update API/data-structure docs and roadmap.

## Validation Plan

- Compile changed Python modules and scripts.
- Run focused `SystemServiceTests` for T-451/T-453 company database run history and trends.
- Run full unit tests if feasible.
- Run handoff validation because new handoff was added.

## Agent Coordination

- Explorer agent `019ef98c-fcff-7761-ba87-39087c0bae6b` reviewed the in-progress T-453 slice and confirmed the route/method shape, local-only artifact boundary and tests/docs needed to complete it.

## Current State

- Completed: `/api/company-database/coverage/trends` route added.
- Completed: `SystemService.company_database_coverage_trends` implemented.
- Completed: trend rows include before/after coverage, coverage delta, missing-count delta and per-section missing deltas.
- Completed: summary includes first/latest score, cumulative delta and improved/worsened/unchanged run counts.
- Completed: optional local JSON artifact output implemented with `classification=local-only` and `acceptable_for_non_local_release_gate=false`.
- Completed: tests and docs added.
- Blocked: none.

## Files Touched

- `app/api.py`: added coverage trends route and handler.
- `app/services.py`: added trend report and helper methods.
- `tests/test_system.py`: added trend summary, filter and artifact tests.
- `docs/api-contracts.md`: documented endpoint contract and local-only artifact boundary.
- `docs/data-structure-design.md`: documented derived trend row shape.
- `tasks/todo.md`: added T-453.
- `docs/README.md`: updated task range and data-structure summary.
- `docs/agent-handoffs/README.md`: added T-453.
- `docs/agent-handoffs/2026-06-24-T-453-company-coverage-trends.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_coverage_trends_report_and_artifact tests.test_system.SystemServiceTests.test_company_database_coverage_trends_filters_by_issuer_and_status
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile for app/tests/scripts.
- Passed: focused company database run-history/trend tests, 3 tests.
- Passed: full unit test discovery, 228 tests.
- Passed: security check, no findings.
- Passed: handoff validation.
- Passed: diff whitespace check.
- Failed: none.

## Decisions

- Trend reports are derived from persisted local run snapshots only; they do not rebuild the company database.
- Artifact output is opt-in and local-only.
- Dry-run, executed and failed statuses remain visible so users can separate planned coverage from actual persisted changes.
- The endpoint returns summarized rows rather than full batch payloads to avoid large responses for market-wide runs.

## Dependencies

- T-451 `CompanyDatabaseBuildRun` model and run-history persistence.
- T-445 coverage audit payload shape.
- Existing local store and route authorization for company database APIs.

## Blockers

- None.

## Risks and Open Questions

- Trend rows depend on the quality of coverage snapshots captured by each run.
- Dry-run records can be useful for planning but should not be interpreted as actual database improvement.
- UI charting is still a follow-up task.

## Artifacts

- Optional caller-provided local JSON path from `write_artifact=true`; tests use `TemporaryDirectory` to avoid committed artifact churn.

## Handoff Checklist

- [x] API route added.
- [x] Service trend report implemented.
- [x] Local-only artifact boundary implemented.
- [x] Tests added.
- [x] Docs and todo updated.
- [x] Final validation passed.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_build_records_run_history tests.test_system.SystemServiceTests.test_company_database_coverage_trends_report_and_artifact tests.test_system.SystemServiceTests.test_company_database_coverage_trends_filters_by_issuer_and_status
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: compile, focused tests, full 228-test suite, security check, handoff validation and diff whitespace check.

## Next Steps

1. Add T-454 resumable run and retry semantics for failed or partial batch runs.
2. Add T-455 UI coverage trend chart after the backend trend report is stable.
3. Add payload-size controls for large historical runs if needed.

## Next Recommended Action

Implement T-454 failed/partial run retry semantics with explicit idempotency and no-live-trading boundaries.
