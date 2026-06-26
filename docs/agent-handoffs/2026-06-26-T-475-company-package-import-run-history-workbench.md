# Handoff: T-475 Company Package Import Run History Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-475

## Objective

Expose T-474 package import run history in the company intelligence workbench so analysts can review local watchlist / company package import runs without manually calling the API.

## Scope

- In scope: company intelligence workbench button, status cards, run history table, JS payload/render/load functions, UI static contract, browser acceptance render check, roadmap and handoff.
- Out of scope: backend schema changes, package import retry/resume, upload widget, external package download, real trading.

## Background

T-474 added `GET|POST /api/company-database/package/import/runs`, but the workbench still only showed the immediate package import response. For a useful company database intake workflow, import history needs to be visible alongside package import, material inbox, coverage audit and batch build history.

## Problem Statement

After executing a local watchlist / company package import, the user could not see the persisted import run from the UI. This made it hard to verify that the run was recorded, inspect invalid/duplicate counts later, or hand off the next material inbox step.

## Expected Deliverables

- A workbench button to load package import run history.
- Status cards for latest import state, run count and latest import time.
- A run history table with run ID, target summary, source path/glob, totals and boundary.
- JS functions for payload construction, rendering and API loading.
- Automatic history refresh after execute import.
- UI static and browser render acceptance coverage.

## Current Findings

- The package import UI already has root path, glob, limit, preview/execute buttons and result rows.
- Existing build-run history UI provides a good pattern for status cards plus table rendering.
- T-474 run history API supports symbol filtering, so the workbench can scope history to the current company symbol by default.

## Proposed Work Plan

1. Add workbench controls and table IDs near existing package import UI.
2. Implement `companyPackageImportRunsPayload`, `renderCompanyPackageImportRuns` and `loadCompanyPackageImportRuns`.
3. Refresh package import run history after execute import.
4. Update static UI contract and browser interaction acceptance.
5. Update roadmap, docs index and handoff.
6. Run compile, UI static, handoff and diff checks; run browser acceptance if a current-code service is available.

## Validation Plan

- Compile app, tests and scripts.
- Run `python3 scripts/ui_static_check.py`.
- Run `python3 scripts/check_handoffs.py`.
- Run `git diff --check`.
- Run `scripts/ui_interaction_acceptance.py` against a current-code local service when feasible.

## Current State

- Completed: workbench has `loadCompanyPackageImportRuns` button.
- Completed: workbench shows package run history status, count and latest timestamp.
- Completed: package import run table renders run status, targets, source, totals, created issuer count and local-only boundary.
- Completed: execute package import refreshes run history automatically.
- Completed: UI static contract and browser render check include package import run history.
- Blocked: None.

## Risks

- The UI currently filters history by current symbol only; broader package-level browsing may need a future filter control.
- Browser acceptance depends on a current-code local service; stale services can produce false failures unrelated to this UI render path.
- Local `root_path` may reveal machine-specific paths and remains local-only operational metadata.

## Dependencies

- T-474 `CompanyPackageImportRun` API.
- Existing company intelligence workbench table and status helper functions.
- Existing UI static and browser interaction acceptance scripts.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: added package import run history controls, cards, table and JS load/render functions.
- `scripts/ui_static_check.py`: added required IDs and JS functions.
- `scripts/ui_interaction_acceptance.py`: added `company_package_import_run_history_render`.
- `docs/README.md`: updated task range to T-475.
- `tasks/todo.md`: added `DONE` T-475.
- `docs/agent-handoffs/2026-06-26-T-475-company-package-import-run-history-workbench.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t475
```

Result:

- Passed: Python compile on app, tests and scripts.
- Passed: UI static contract.
- Passed: handoff validation.
- Passed: whitespace diff check.
- Passed: browser interaction acceptance against current-code local service on `127.0.0.1:8768`, 27/27 checks including `company_package_import_run_history_render`.
- Failed: none known.
- Not run: none for this task.

## Evidence

- UI static contract should prove all new IDs and JS functions are present.
- Browser render check should prove the table and status cards render a representative package import run history payload.
- Handoff validation should prove this file has the required handoff sections.
- `artifacts/ui-interaction-acceptance-t475` contains local-only browser acceptance output from a current-code service.

## Decisions

- Reused current company symbol as the default history filter to keep the workflow company-centric.
- Defaulted history API calls to `include_items=false`; row-level items stay available in API but are not needed for the compact workbench table.
- Rendered local path/glob as source metadata but preserved local-only boundary labeling.

## Artifacts

- `artifacts/ui-interaction-acceptance-t475`: local-only browser acceptance output; not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Code changes completed.
- [x] UI static contract updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [x] Verification commands completed.

## Next Steps

1. Add explicit history filters only if analysts need cross-symbol package browsing.
2. Consider a failed-row re-import helper after actual import run usage produces repeat failure patterns.
3. Keep local path metadata out of non-local release evidence.

## Next Recommended Action

Run verification commands, fix any UI contract drift, then commit and push T-475 when checks pass.
