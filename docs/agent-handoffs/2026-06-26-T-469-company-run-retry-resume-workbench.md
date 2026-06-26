# Handoff: T-469 Company Run Retry Resume Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality, Data and Evidence, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-469

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Make existing company database build run retry/resume semantics usable from the company intelligence workbench, so failed, partial or historical build runs can be previewed, resumed or replayed without manual API calls.

## Background

T-454 implemented retry/resume backend semantics for `CompanyDatabaseBuildRun`, and T-455 exposed run history/trends in the workbench. The UI showed retry lineage and resume metadata but did not let users trigger the existing retry endpoint from the run history table.

## Problem Statement

Long-running company database backfills must be recoverable from the workbench. Without visible retry/resume actions, users still need to inspect raw JSON or call APIs manually, which makes the company database feel incomplete even though backend recovery already exists.

## Expected Deliverables

- Run history action buttons for retry preview, remaining resume and full replay.
- Frontend API call to `POST /api/company-database/batch/runs/{run_id}/retry`.
- UI refresh of run history, coverage trends and company intelligence after retry/resume.
- Static and interaction acceptance contracts for the new action.
- Roadmap and handoff updates.

## Scope

- In scope: `app/static/index.html`, UI static check, UI interaction acceptance, roadmap and handoff.
- Out of scope: new backend retry semantics, external source downloads, production orchestration, real broker integrations and live trading.

## Current Findings

- `app/api.py` already registers `POST /api/company-database/batch/runs/{run_id}/retry`.
- `app/services.py` already supports `resume_mode=remaining|all`, `attempt`, source run lineage, `retry_issuer_ids` and `skipped_issuer_ids`.
- `tests/test_system.py` already covers retry replay, remaining resume and partial run recording.
- The missing gap was UI action wiring and acceptance coverage.

## Proposed Work Plan

1. Add retry/resume action buttons to `renderCompanyBuildRunHistory`.
2. Add `retryCompanyBuildRun` frontend helper that calls the existing retry endpoint.
3. Wire `data-action="retry-company-build-run"` into the shared click handler.
4. Update UI static and interaction acceptance scripts.
5. Update roadmap and handoff, then run focused checks.

## Validation Plan

- Compile touched Python/UI acceptance scripts.
- Run `scripts/ui_static_check.py`.
- Run `git diff --check`.
- Run handoff validation.
- Rely on existing backend unit tests for retry/resume semantics unless backend code changes.

## Current State

- Completed: run history rows now expose `预览重试`, `续跑剩余` and `重跑全部`.
- Completed: `retryCompanyBuildRun` calls the existing retry endpoint with explicit `resume_mode`, `execute`, `dry_run` and `record_run=true`.
- Completed: successful retry/resume refreshes run history and coverage trends; execute also refreshes company intelligence.
- Completed: static UI checks include the new function and action marker.
- Completed: interaction acceptance includes a browser path that executes a company database build, then clicks retry preview.

## Dependencies

- T-454 backend retry/resume semantics.
- T-455 run history and coverage trend UI.
- Existing company intelligence workbench API helper and shared `data-action` click handler.

## Blockers

- None for this task.

## Files Touched

- `app/static/index.html`: added run action buttons, retry helper and click-handler action.
- `scripts/ui_static_check.py`: added required JS function and action marker.
- `scripts/ui_interaction_acceptance.py`: added retry preview browser acceptance path.
- `tasks/todo.md`: added DONE T-469 roadmap entry.
- `docs/agent-handoffs/2026-06-26-T-469-company-run-retry-resume-workbench.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/api.py app/services.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
git diff --check
python3 scripts/check_handoffs.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768
```

Result:

- Passed: Python compile on touched Python/UI scripts.
- Passed: UI static check, `required_ids=266`, `required_functions=94`, `interaction_markers=14`.
- Passed: `git diff --check`.
- Passed: handoff validation, 43 markdown files checked.
- Passed: UI interaction acceptance, 25 checks, 0 failures, `artifact://ui-interaction-acceptance/ui-interaction-acceptance`.

## Evidence

- Existing backend tests cover retry replay, remaining resume and partial run persistence.
- Updated UI static contract proves the retry action marker and function are present.
- Updated interaction acceptance proves the workbench exposes retry preview after a recorded build run.

## Decisions

- Do not duplicate backend retry logic; UI calls the existing retry endpoint.
- `预览重试` uses dry-run and records a new run by default for auditability.
- `续跑剩余` uses `resume_mode=remaining`; `重跑全部` uses `resume_mode=all`.
- The action remains local-only and paper/simulated-only; it does not fetch external data or trigger live trading.

## Risks and Open Questions

- Interaction acceptance currently validates retry preview, not execute resume on a synthetic partial run.
- Future UI polish could hide `续跑剩余` for completed runs or add confirmation prompts for execute actions.

## Artifacts

- None. This task does not generate persistent runtime artifacts.

## Handoff Checklist

- [x] UI action buttons added.
- [x] Retry helper added.
- [x] Static and interaction contracts updated.
- [x] Roadmap updated.
- [x] Final verification commands run after this handoff is created.
- [x] Full UI interaction acceptance passed.

## Next Steps

1. T-470 implements the next all-weather company intelligence gap: a cycle runner that updates report realization, workflow rebuild and paper-only feedback after new data arrives.
2. Continue with run-history polish for partial runs or add confirmation prompts for execute actions.

## Next Recommended Action

Add cycle execution history if repeated company refreshes need date-over-date comparison.
