# Handoff: T-600 Latest Analysis Runtime Slice

## Metadata

- Status: active
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-18
- Related tasks: T-498, T-592, T-599, T-600
- Scope: Move the latest-analysis renderer into the runtime dashboard module
- Non-goals: Full dashboard orchestration, other UI domains, API changes, or backend behavior

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-07-18
- Last agent: Codex `/root/t592_ui_modules`
- Branch/worktree: main / shared dirty worktree at `/home/xionglei/Project/sotck_quant`

## Objective

Extract `renderLatestAnalysis` and its cohesive presentation dependencies into the already-loaded `dashboard.mjs`, while preserving the global browser/debug entrypoint and all current DOM and API behavior.

## Scope

- In scope: the complete latest-analysis renderer, explicit presentation-helper injection, thin compatibility wrapper, module ownership checks, deterministic fixture check, and clean browser evidence.
- Out of scope: `loadDashboard`, personal-loop/industry-chain loaders, company/graph/market/admin domains, service/API changes, broker integration, or automatic trading.

## Background

T-599 moved dashboard data-health loading and rendering into `dashboard.mjs`. The 164-line `renderLatestAnalysis` implementation remained one of the largest cohesive dashboard presentation blocks in `index.html`.

## Problem Statement

The renderer owns a single payload-to-DOM transformation but uses many shared formatting helpers. It needed to move without introducing a global service locator, copying helpers, or converting the classic main script to module scope.

## Expected Deliverables

- The full renderer exists only in `dashboard.mjs`.
- The classic script retains a thin global `renderLatestAnalysis(data)` delegate.
- Dependencies are explicitly injected into the dashboard runtime factory.
- Static ownership and fixture-driven output checks protect the extraction.
- Fresh-SQLite desktop/mobile Chromium passes with zero console errors.

## Current Findings

- The renderer requires DOM lookup plus presentation helpers only; it does not call APIs or mutate shared application state outside target elements.
- `renderPersonalIntelligenceSummary` remains inline but is passed as an explicit callback, preserving a coherent boundary.
- Interaction contract markers such as `open-research` and `open-ingestion` now live in runtime module source, so the static interaction scan must include both HTML and runtime modules.

## Proposed Work Plan

1. Mechanically move the entire renderer into the dashboard runtime factory.
2. Inject its existing presentation helpers and expose it from the runtime object.
3. Replace inline ownership with a one-line delegate.
4. Add a deterministic module fixture and extend static ownership coverage.
5. Run isolated browser, MIME, marker, syntax, unit, diff, and handoff checks.

## Validation Plan

- Execute the module fixture check and static UI contract.
- Run Node syntax, Python compile, focused UI unit, and diff whitespace checks.
- Verify dashboard module HTTP response and runtime DOM marker.
- Run the 16-scenario Chromium matrix against a new SQLite database.

## Dependencies

- T-599 `createDashboardRuntime()` and T-592 dynamic-import/server path.
- Existing shared presentation functions injected from the classic script.
- Existing latest-analysis payload and DOM ID contracts.

## Blockers

- None for this renderer extraction.

## Current State

- Completed: `dashboard.mjs` lines 78-241 own the complete 164-line `renderLatestAnalysis` implementation.
- Completed: `index.html` lines 8873-8875 retain the three-line global delegate, removing 161 inline implementation lines.
- Completed: dashboard runtime initialization around line 12474 explicitly injects all required presentation dependencies.
- Completed: the deterministic fixture asserts nine output/contract dimensions.
- Not started: `renderPersonalIntelligenceSummary`, `renderPersonalResearchLoopOverview`, `loadIndustryChainSummary`, and full `loadDashboard` orchestration remain inline.
- Not started: runtime extraction for `company`, `graph`, `market`, and `admin`.
- Blocked: none.

## Files Touched

- `app/static/ui_modules/dashboard.mjs`: owns `renderLatestAnalysis` and accepts its explicit presentation dependencies.
- `app/static/index.html`: replaces the 164-line implementation with a three-line compatibility wrapper and injects dependencies during runtime creation.
- `scripts/ui_static_check.py`: includes runtime module sources when checking interaction markers and enforces renderer implementation/wrapper ownership.
- `scripts/ui_dashboard_module_check.mjs`: adds a backend-independent fixture with nine assertions over headline, returns, weights, research, sources, market dates, acceptance, personal-summary delegation, and runtime marker.

## Commands Run

```bash
node scripts/ui_dashboard_module_check.mjs
node --check app/static/ui_modules/dashboard.mjs
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
git diff --check -- app/static/index.html app/static/ui_modules/dashboard.mjs scripts/ui_static_check.py scripts/ui_dashboard_module_check.mjs
curl -sS -D - http://127.0.0.1:8779/ui_modules/dashboard.mjs -o /dev/null
/usr/bin/google-chrome --headless=new --no-sandbox --disable-gpu --virtual-time-budget=5000 --dump-dom http://127.0.0.1:8779/ui
.venv/bin/python scripts/ui_research_workbench_matrix.py http://127.0.0.1:8779 --output-dir /tmp/ui-research-workbench-t600-clean --timeout 60
python3 scripts/check_handoffs.py
```

Result:

- Passed: fixture check, 9/9 assertions.
- Passed: UI static contract, Node syntax, Python compile, focused UI unit, and diff whitespace.
- Passed: dashboard module returned `200 OK` and `Content-Type: text/javascript; charset=utf-8`.
- Passed: headless Chrome emitted `data-ui-runtime-modules="dashboard,helpers"`; stderr was empty.
- Passed: isolated Chromium matrix 16/16 across desktop/mobile with zero console errors.
- Not run: full stateful interaction suite; the fixture and clean matrix directly exercise the moved renderer and its click markers.
- Not run: Firefox/WebKit; evidence is local Chromium only and not valid for non-local release gates.

## Decisions

- Move the renderer as one cohesive payload-to-DOM unit; do not split individual cards into premature micro-modules.
- Inject 13 existing presentation dependencies and the personal-summary callback explicitly; do not add a global service locator.
- Keep `renderPersonalIntelligenceSummary` outside this task because it is a separate payload/render boundary.
- Expand interaction-marker scanning to runtime sources while keeping DOM ID and global-function checks anchored to HTML.

## Risks and Open Questions

- The runtime factory dependency list is now longer. A later dashboard composition object may reduce ceremony, but only after another extraction proves a stable grouping.
- The full dashboard coordinator remains inline and still combines unrelated APIs; it should not be moved until industry and personal-loop slices are isolated.
- The fixture uses a DOM stub and complements rather than replaces real browser acceptance.

## Artifacts

- `/tmp/ui-research-workbench-t600-clean`: generated 2026-07-18 by Chromium against isolated local SQLite; Product and UI owner; no intended sensitive data; `local-only`, not acceptable for non-local release gates.
- `/tmp/t600-chrome.stderr`: empty local module execution diagnostic; not versioned and not acceptable for release gates.

## Acceptance Checklist

- [x] Renderer implementation absent inline and owned by dashboard module
- [x] Thin global compatibility wrapper preserved
- [x] Explicit dependency injection used
- [x] Fixture-driven renderer assertions passed
- [x] Clean desktop/mobile Chromium passed with zero console errors
- [x] Static, syntax, MIME, focused unit, diff, and handoff gates passed
- [ ] `tasks/todo.md` updated by PM owner during integrated roadmap reconciliation

## Handoff Checklist

- [x] Exact implementation and wrapper lines recorded
- [x] Line delta and residual dashboard ownership recorded
- [x] Local-only evidence boundary stated
- [x] Exact next extraction identified

## Next Steps

1. Extract `renderPersonalIntelligenceSummary` and its small load callback boundary.
2. Extract `loadIndustryChainSummary` as a separate API/render slice.
3. Reassess `loadDashboard` only after those dependencies no longer own large inline render blocks.

## Evidence

- `app/static/ui_modules/dashboard.mjs`: sole implementation owner for latest-analysis rendering.
- `app/static/index.html`: three-line global delegate and explicit runtime dependency wiring.
- `scripts/ui_dashboard_module_check.mjs`: deterministic 9-assertion renderer fixture.
- `/tmp/ui-research-workbench-t600-clean`: 16/16 local Chromium checks, zero console errors.

## Next Recommended Action

Have PM integrate T-600, then move `renderPersonalIntelligenceSummary` before attempting the dashboard coordinator.
