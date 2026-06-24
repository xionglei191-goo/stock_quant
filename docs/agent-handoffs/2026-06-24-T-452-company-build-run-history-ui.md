# Handoff: T-452 Company Build Run History UI

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-452

## Objective

Expose persisted company database batch build runs in the company intelligence workbench so users can see whether补库 actually ran, which companies were processed, and how coverage changed before and after the run.

## Scope

- In scope: static UI, UI static contract, UI interaction acceptance, roadmap docs, handoff record.
- Out of scope: backend API shape changes, resumable batch execution, failed-run retry, external source crawling, production release evidence and real broker integration.

## Background

T-451 added `CompanyDatabaseBuildRun` and `/api/company-database/batch/runs`, but the workbench still required users to inspect raw JSON from the latest operation. The next safe slice is a UI-only read path over the existing local run-history API.

## Problem Statement

Users could execute company database补库 and receive a `run_id`, but the workbench did not expose persisted run history. After the response disappeared, it was hard to tell which company was processed, whether coverage improved, or which local operation boundary applied.

## Expected Deliverables

- Add a compact run-history area to the company intelligence workbench.
- Query existing local run-history API without changing backend contracts.
- Show coverage before/after deltas and summarized totals.
- Refresh run history after batch execution and company intelligence load.
- Extend UI static and browser interaction acceptance.

## Current Findings

- Existing `/api/company-database/batch/runs` already supports `issuer_id`, `status` and `limit`.
- Existing run records include coverage snapshots and totals sufficient for a compact UI.
- No new data source, crawler or model call is required for this slice.
- Follow-up coverage trend artifacts should be backend/report work, not part of this UI-only slice.

## Proposed Work Plan

1. Add UI controls and table in the company database panel.
2. Add render/load helpers that use the current company issuer only when it matches the active ticker.
3. Refresh history after execute-mode batch builds.
4. Update UI acceptance and docs.

## Validation Plan

- Compile Python scripts to catch acceptance-script syntax errors.
- Run UI static contract check for added IDs/functions.
- Run browser interaction acceptance for the new history load path.
- Run handoff validation because this task adds a handoff.

## Agent Coordination

- Explorer agent `019ef97f-c098-73f1-b6dc-92f71a82e1ee` inspected the UI/API slice and confirmed no backend changes were required.
- Explorer agent `019ef980-0512-78d0-a38c-ba25a60adf09` ranked follow-up gaps and recommended T-452 before coverage-trend artifacts or resume/retry.

## Current State

- Completed: company database panel now has a "查看运行历史" action, recent run status, run count, coverage delta and run-history table.
- Completed: UI queries `/api/company-database/batch/runs` with the current company issuer when available.
- Completed: executing a batch build refreshes run history; loading company intelligence also refreshes matching run history.
- Completed: rows summarize `run_id`, status, time, target count, batch count, coverage before/after delta, totals and local operation boundary.
- Completed: research-report structure payload no longer uses stale graph-level `activeEntityIssuerId`.
- Blocked: none.

## Files Touched

- `app/static/index.html`: added run-history UI, render/load helpers and batch-build refresh hooks.
- `scripts/ui_static_check.py`: added required IDs and functions for the run-history UI.
- `scripts/ui_interaction_acceptance.py`: added browser acceptance for loading run history.
- `tasks/todo.md`: added T-452.
- `docs/README.md`: updated company-intelligence task range.
- `docs/agent-handoffs/README.md`: added T-452 to related tasks.
- `docs/agent-handoffs/2026-06-24-T-452-company-build-run-history-ui.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= python3 -c "from app.server import get_router, serve; get_router(); serve(port=8765)"
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8765
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile for app/tests/scripts.
- Passed: UI static contract check.
- Passed: handoff validation after adding required template sections.
- Passed: UI interaction acceptance on temporary current-code service `http://127.0.0.1:8765`, 14 checks, `failure_count=0`.
- Failed: first handoff validation failed because the initial handoff missed required template sections; fixed in this file.
- Failed: first default `python3 scripts/ui_interaction_acceptance.py` against `http://127.0.0.1:8000` failed because the already-running 8000 service was stale and returned 404 for `/api/company-database/batch/runs`; current-code validation used the temporary 8765 service and passed.

## Decisions

- Reused the existing run-history endpoint; no backend contract change was needed.
- Used `currentCompanyIntelIssuerId()` rather than `activeEntityIssuerId` to avoid operating on stale graph context after the user changes ticker.
- Displayed summarized totals and coverage deltas in the table; full run details stay in the operation JSON only when the user explicitly loads history.
- Kept run history as local research operations metadata, not production evidence or a trading record.

## Risks and Open Questions

- Large market-wide runs can produce large `batches`; the table intentionally avoids rendering full batch details.
- Coverage trend charts and artifact output are still follow-up work.
- Resume/retry semantics remain unimplemented.

## Dependencies

- Existing `CompanyDatabaseBuildRun` model and store collection from T-451.
- Existing `/api/company-database/batch/runs` endpoint.
- Existing company intelligence workbench state helpers.

## Blockers

- None.

## Artifacts

- None produced.

## Handoff Checklist

- [x] UI controls added.
- [x] Run-history load/render helpers added.
- [x] Batch execute refresh hook added.
- [x] UI static contract updated.
- [x] Browser interaction acceptance updated.
- [x] Roadmap and docs index updated.
- [x] Final validation passed on current-code service.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= python3 -c "from app.server import get_router, serve; get_router(); serve(port=8765)"
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8765
python3 scripts/check_handoffs.py
```

Result:

- Passed: compile, UI static check, handoff validation, and 8765 current-code UI interaction acceptance.
- Failed: default 8000 UI interaction acceptance was stale-service failure, not current-code failure.
- Failed: first handoff validation caught missing template sections; fixed.

## Next Steps

1. Add T-453 coverage trend report and optional local artifact output from persisted run snapshots.
2. Add T-454 resume/retry semantics for partial or failed batch runs.
3. Consider a compact run detail drawer only after large-run payload size is bounded.

## Next Recommended Action

Implement T-453 as a backend coverage trend report and local artifact export based on persisted `CompanyDatabaseBuildRun.coverage_before` / `coverage_after` snapshots.
