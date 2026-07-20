# Handoff: T-599 Dashboard Runtime Module

## Metadata

- Status: active
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-18
- Related tasks: T-498, T-592, T-599
- Scope: Extract the dashboard data-health load/render slice into a real runtime module
- Non-goals: Full dashboard extraction, DOM/API changes, or backend business behavior

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-07-18
- Last agent: Codex `/root/t592_ui_modules`
- Branch/worktree: main / shared dirty worktree at `/home/xionglei/Project/sotck_quant`

## Objective

Continue the T-592 compatibility pattern by moving a coherent dashboard load/render slice into `dashboard.mjs`, while retaining the classic script and global entrypoints required by existing acceptance and local debugging.

## Scope

- In scope: data-health status classification, next-action labeling, source row rendering, dashboard/ingestion summary rendering, API loading, runtime registration, manifest/static gates, and clean browser evidence.
- Out of scope: `renderLatestAnalysis`, full `loadDashboard` orchestration, company/graph/market/admin extraction, API schemas, backend logic, live trading, or broker integration.

## Background

T-592 proved that dynamic module import from the classic main script preserves the legacy global browser contract. `dashboard.mjs` remained a two-line scaffold and the data-health load/render behavior was still inline.

## Problem Statement

The next extraction must remove actual dashboard behavior rather than only update metadata, but it must not turn the highly coupled full dashboard orchestration into a large dependency bundle or hide globally invoked functions.

## Expected Deliverables

- A runtime `dashboard.mjs` with a bounded load/render slice.
- Compatibility wrappers for the five existing global function names.
- Manifest and static checks that prove dashboard is runtime-loaded and logic is not duplicated inline.
- Fresh-SQLite Chromium evidence for desktop/mobile data-health and navigation behavior with zero console errors.

## Current Findings

- `loadDashboard` coordinates latest analysis, personal loop, industry-chain, health, governance, and CEO dashboard APIs; extracting it as one unit would create an oversized injected facade.
- The data-health slice has one API, deterministic status/action rules, and two explicit rendering targets, making it a coherent first dashboard module boundary.
- The runtime marker must merge module names because helper/dashboard imports can resolve in either order.

## Proposed Work Plan

1. Add a dependency-injected dashboard runtime factory.
2. Move five data-health functions and retain thin global wrappers.
3. Register dashboard beside helpers in the manifest and DOM runtime marker.
4. Strengthen static ownership checks and run isolated browser acceptance.

## Validation Plan

- Run UI static, Node syntax, Python compile, focused UI unit, whitespace, and handoff checks.
- Verify dashboard module HTTP status and JavaScript MIME.
- Verify Chromium DOM marker includes both runtime modules and stderr is empty.
- Run the research-workbench matrix serially against a new SQLite database.

## Dependencies

- T-592 module route and dynamic-import compatibility pattern.
- Existing DOM IDs and shared UI helpers injected into `createDashboardRuntime()`.
- Existing `/api/data-health/summary` response contract.

## Blockers

- None for this bounded extraction.

## Current State

- Completed: `dashboard.mjs` lines 4-79 define the runtime factory, five functions, runtime marker merge, and public runtime object.
- Completed: `index.html` lines 8746-8765 retain thin compatibility wrappers only.
- Completed: `index.html` lines 12635-12651 import and initialize the dashboard runtime without changing the classic script.
- Completed: manifest runtime modules are `dashboard` and `helpers`.
- Not started: runtime extraction for the remaining domains `company`, `graph`, `market`, and `admin`.
- Not started: later dashboard slices `renderLatestAnalysis`, `renderPersonalIntelligenceSummary`, `loadIndustryChainSummary`, and the full `loadDashboard` coordinator.
- Blocked: none.

## Files Touched

- `app/static/ui_modules/dashboard.mjs`: changed from empty scaffold to runtime factory; owns `dataHealthStatusClass`, `dataHealthNextActionLabel`, `renderDataHealthRows`, `renderDataHealthSummary`, and `loadDataHealthSummary`.
- `app/static/index.html`: replaces the five implementations with global compatibility wrappers and initializes the module through dynamic import.
- `app/static/ui_modules/helpers.mjs`: merges its runtime marker instead of overwriting other concurrently loaded module names.
- `app/static/ui_modules/manifest.json`: adds `dashboard` to runtime modules and removes it from scaffold modules.
- `scripts/ui_static_check.py`: validates dashboard import, runtime partition, implementation ownership, wrappers, syntax, and non-scaffold state.

## Commands Run

```bash
python3 scripts/ui_static_check.py
node --check app/static/ui_modules/dashboard.mjs
node --check app/static/ui_modules/helpers.mjs
python3 -m py_compile scripts/ui_static_check.py
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
git diff --check -- app/static/index.html app/static/ui_modules scripts/ui_static_check.py
curl -sS -D - http://127.0.0.1:8778/ui_modules/dashboard.mjs -o /dev/null
/usr/bin/google-chrome --headless=new --no-sandbox --disable-gpu --virtual-time-budget=5000 --dump-dom http://127.0.0.1:8778/ui
.venv/bin/python scripts/ui_research_workbench_matrix.py http://127.0.0.1:8778 --output-dir /tmp/ui-research-workbench-t599-clean --timeout 60
python3 scripts/check_handoffs.py
```

Result:

- Passed: UI static contract; runtime modules reported as `dashboard`, `helpers`.
- Passed: Node syntax for both runtime modules, Python compile, focused UI unit, and diff whitespace.
- Passed: dashboard module returned `200 OK` and `Content-Type: text/javascript; charset=utf-8`.
- Passed: headless Chrome emitted `data-ui-runtime-modules="dashboard,helpers"` with empty stderr.
- Passed: isolated Chromium matrix 16/16 across desktop/mobile, including data-health center, with zero console errors.
- Not run: full stateful interaction suite; the clean matrix directly covers this slice and T-592 established that stateful suites require isolated serial setup.
- Not run: Firefox/WebKit; evidence is local Chromium only and not acceptable for non-local release gates.

## Decisions

- Extract the five-function data-health slice instead of the whole `loadDashboard` coordinator to keep the module boundary cohesive.
- Preserve global function declarations as one-line delegates because `REQUIRED_JS_FUNCTIONS` and browser/debug callers depend on them.
- Await `dashboardRuntimeReady` in the async loader so startup is safe regardless of module fetch timing.
- Merge and sort runtime marker names in both modules so import completion order cannot lose evidence.

## Risks and Open Questions

- Dashboard modularization is partial. The large latest-analysis renderer and full dashboard coordinator remain inline.
- Synchronous compatibility wrappers assume dashboard initialization has completed; current production calls reach them through the awaited loader, and clean browser startup passed. Future direct early callers should await `dashboardRuntimeReady` or use the async loader.
- Shared helper injection is explicit but verbose. Do not introduce a global service locator until at least one more module proves a stable shared dependency contract.

## Artifacts

- `/tmp/ui-research-workbench-t599-clean`: generated 2026-07-18 by the Chromium research-workbench matrix against isolated local SQLite; owner Product and UI; no intended sensitive data; `local-only`, not valid for non-local production gates.
- `/tmp/t599-chrome.stderr`: empty headless Chromium stderr from module execution check; local diagnostic only; not versioned and not valid for release gates.

## Acceptance Checklist

- [x] Dashboard module imported and executed
- [x] Five-function load/render logic removed from inline ownership
- [x] Global compatibility entrypoints preserved
- [x] Manifest and residual scaffolds truthful
- [x] Static, syntax, MIME, focused unit, browser, and diff checks passed
- [ ] `tasks/todo.md` updated by PM owner during integrated roadmap reconciliation

## Handoff Checklist

- [x] Exact moved functions and current line references recorded
- [x] Runtime and clean browser evidence recorded
- [x] Residual inline dashboard work and scaffold domains recorded
- [x] Local-only artifact boundary stated

## Next Steps

1. Extract `renderLatestAnalysis` into `dashboard.mjs` with a thin global wrapper and focused fixture-driven render check.
2. Extract `loadIndustryChainSummary` separately before considering the full `loadDashboard` coordinator.
3. Move to `company.mjs` only after the dashboard render slices have explicit dependency contracts.

## Evidence

- `app/static/ui_modules/dashboard.mjs`: authoritative implementation for five data-health functions.
- `app/static/index.html`: wrapper-only ownership and dynamic initialization.
- `app/static/ui_modules/manifest.json`: runtime `[dashboard, helpers]`; scaffold `[company, graph, market, admin]`.
- `/tmp/ui-research-workbench-t599-clean`: 16/16 local Chromium checks passed, zero console errors.

## Next Recommended Action

Have PM integrate T-599 into the roadmap, then extract `renderLatestAnalysis` as the next bounded dashboard runtime slice.
