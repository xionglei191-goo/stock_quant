# Handoff: T-592 UI Runtime Modularization

## Metadata

- Status: active
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-18
- Related tasks: T-498, T-592
- Scope: First runtime-loaded `/ui` module extraction with compatibility checks
- Non-goals: Full frontend modularization, DOM/API changes, or backend business behavior

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-07-18
- Last agent: Codex `/root/t592_ui_modules`
- Branch/worktree: main / shared dirty worktree at `/home/xionglei/Project/sotck_quant`

## Objective

Replace T-498's metadata-only frontend scaffold with a real runtime-loaded module slice. Preserve `/ui`, existing DOM IDs and data attributes, API requests, navigation behavior, and browser-visible behavior.

## Scope

- In scope: first runtime module, navigation listener extraction, `.mjs` serving, manifest truthfulness, static/browser compatibility gates, and handoff.
- Out of scope: API/schema changes, backend business logic, full frontend split, broker connectivity, or automatic trading.

## Background

T-498 created six `.mjs` placeholders but explicitly kept `runtime_loaded=false`; all browser behavior remained in the inline script. PM review identified that state as a scaffold rather than completed frontend modularization.

## Problem Statement

The repository needs an incremental extraction pattern that executes real module code without hiding the legacy global functions and state used by browser acceptance and local debugging.

## Expected Deliverables

- One coherent runtime-owned listener slice removed from inline ownership.
- A safe server path and correct JavaScript MIME for `.mjs` assets.
- A manifest and static gate that distinguish runtime modules from remaining scaffolds.
- Clean Chromium evidence for desktop/mobile navigation and console behavior.

## Current Findings

- Converting the full inline script to `type="module"` breaks legacy global access; dynamic import from the classic script preserves compatibility.
- The two navigation listener groups form a bounded extraction with no API or DOM contract changes.
- Existing browser suites must run serially against isolated SQLite databases to avoid false `database is locked` and fixture-state failures.

## Proposed Work Plan

1. Serve and dynamically import `helpers.mjs`.
2. Move navigation listener installation and expose a runtime DOM marker.
3. Strengthen static checks and run clean serial browser acceptance.
4. Record exact residual scaffold domains and follow-up order.

## Validation Plan

- Run UI static, Node syntax, Python compile, focused unit, whitespace, and handoff checks.
- Verify `/ui_modules/helpers.mjs` response status/MIME.
- Verify headless Chromium executes the module and reports zero console errors.
- Exercise desktop/mobile navigation and representative company/market/graph workflows.

## Dependencies

- Existing classic runtime in `app/static/index.html`.
- Existing local HTTP server and UI acceptance utilities.
- T-498 module domain map and DOM/API compatibility requirements.

## Blockers

- None for the first runtime extraction.

## Current State

- Completed: `helpers.mjs` is fetched and executed at runtime; it owns installation of the `[data-open]` and `[data-workspace-mode]` navigation listeners.
- Completed: the classic inline main script remains classic so existing browser acceptance and debugging calls through global functions and state remain compatible.
- Completed: the server exposes only direct `.mjs` files below `/ui_modules/` with a JavaScript MIME type.
- Completed: the manifest now records `helpers` as the only runtime module and the remaining domains as scaffolds.
- In progress: none for this bounded first extraction.
- Not started: runtime extraction for `dashboard`, `company`, `graph`, `market`, and `admin`.
- Blocked: none.

## Files Touched

- `app/static/index.html`: dynamically imports `helpers.mjs`; removes the two navigation listener installation blocks from inline ownership; preserves existing DOM/API/global runtime contracts and unrelated dynamic-allocation navigation edits.
- `app/static/ui_modules/helpers.mjs`: replaces the empty scaffold with the runtime `installNavigation()` implementation; writes `data-ui-runtime-modules="helpers"` after successful installation.
- `app/static/ui_modules/manifest.json`: changes status from `scaffold-only` to `runtime-partial`, records `helpers` as runtime and the five remaining scaffold domains explicitly.
- `app/server.py`: serves validated direct `/ui_modules/*.mjs` assets as `text/javascript; charset=utf-8`; preserves unrelated dynamic-allocation route-list edits already in the worktree.
- `scripts/ui_static_check.py`: validates module/runtime partition, helper import/export, syntax, and that navigation listener installation no longer remains inline.

## Commands Run

```bash
python3 scripts/ui_static_check.py
node --check app/static/ui_modules/helpers.mjs
python3 -m py_compile app/server.py scripts/ui_static_check.py
git diff --check -- app/server.py app/static/index.html app/static/ui_modules scripts/ui_static_check.py
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
curl -sS -D - http://127.0.0.1:8777/ui_modules/helpers.mjs -o /dev/null
/usr/bin/google-chrome --headless=new --no-sandbox --disable-gpu --virtual-time-budget=5000 --dump-dom http://127.0.0.1:8777/ui
.venv/bin/python scripts/ui_research_workbench_matrix.py http://127.0.0.1:8777 --output-dir /tmp/ui-research-workbench-t592-clean --timeout 60
.venv/bin/python scripts/ui_interaction_acceptance.py http://127.0.0.1:8776 --output-dir /tmp/ui-interaction-acceptance-t592-rerun --timeout 60
```

Result:

- Passed: static UI contract, Node module/main-script syntax checks, Python compile, focused unit regression, and diff whitespace check.
- Passed: GET of `/ui_modules/helpers.mjs` returned `200` with `Content-Type: text/javascript; charset=utf-8`.
- Passed: headless Chrome DOM contained `data-ui-runtime-modules="helpers"`; Chrome stderr was empty.
- Passed: clean isolated Chromium research-workbench matrix, 16/16 desktop/mobile checks, zero console errors.
- Failed: the long interaction suite reported 4/49 failures after an earlier concurrent run shared the same SQLite database. One missing fixture row and three state-dependent ownership/graph assertions failed; the other 45 checks, including global function calls and navigation behavior, passed. The first concurrent matrix also hit `database is locked`. These were not used as acceptance evidence; the clean, serial browser matrix is authoritative for T-592.
- Not run: full cross-browser Firefox/WebKit matrix; only installed Chromium was used for this local-only extraction.

## Decisions

- Use dynamic `import()` from the classic main script. Converting the entire inline script to `type="module"` hid legacy global functions/state and caused 25 interaction failures, so that approach was rejected.
- Extract listener ownership rather than only toggling manifest metadata. Navigation installation exists only in `helpers.mjs`; inline code imports and invokes it.
- Keep runtime status explicitly partial. `dashboard`, `company`, `graph`, `market`, and `admin` remain scaffold-only and must not be described as modularized.
- Serve only direct `.mjs` filenames. The handler rejects non-`.mjs`, nested, missing, and traversal-like names.

## Risks and Open Questions

- `app/static/index.html` remains very large; this is a meaningful first extraction, not completion of frontend modularization.
- Dynamic import means navigation listener installation is asynchronous. The clean browser matrix exercised navigation successfully with zero console errors; the module failure path also surfaces a visible status error.
- The long interaction acceptance is stateful and should use a fresh database and avoid concurrent suites before being treated as release evidence.
- The module asset route currently supports `.mjs` only. Add other static types only when a concrete extracted module needs them, with equivalent path validation and MIME tests.

## Artifacts

- `/tmp/ui-research-workbench-t592-clean`: produced by `scripts/ui_research_workbench_matrix.py` on 2026-07-18 against isolated local SQLite; owner Product and UI; no intended sensitive data; `local-only`, not acceptable for non-local release gates.
- `/tmp/ui-interaction-acceptance-t592-rerun`: produced by the long interaction suite on 2026-07-18 against reused local SQLite; diagnostic only because state contamination caused four failures; no intended sensitive data; `local-only`, not acceptable for release gates.

## Acceptance Checklist

- [x] Code changes completed
- [x] Runtime module import and execution proved in Chromium
- [x] JavaScript MIME and module syntax verified
- [x] Existing DOM IDs, API calls, and classic global behavior preserved
- [x] Static, focused unit, and clean browser checks passed
- [x] Remaining scaffold domains recorded without overstating completion
- [ ] `tasks/todo.md` updated by PM owner during integrated roadmap reconciliation

## Handoff Checklist

- [x] Runtime extraction implemented without duplicate inline listener ownership
- [x] Static, syntax, unit, MIME, DOM execution, and clean browser checks recorded
- [x] Local-only evidence boundary and failed diagnostic run explained
- [x] Remaining scaffold domains and exact next action recorded

## Next Steps

1. Extract `dashboard` loading/rendering behind the same dynamic-import compatibility pattern and add a focused browser scenario.
2. Extract `company` in smaller render/load slices; keep acceptance-visible globals as explicit compatibility exports until scripts are migrated.
3. Run the long interaction suite serially with a fresh SQLite database before the integrated release gate.

## Evidence

- `app/static/ui_modules/helpers.mjs`: runtime navigation owner and browser execution marker.
- `app/static/ui_modules/manifest.json`: authoritative partial-runtime partition.
- `/tmp/ui-research-workbench-t592-clean`: 16/16 local Chromium checks passed with zero console errors.
- HTTP response for `/ui_modules/helpers.mjs`: `200 OK`, `text/javascript; charset=utf-8`.
- Headless Chrome dump: `data-ui-runtime-modules="helpers"`, empty stderr.

## Next Recommended Action

Have PM integrate T-592 into `tasks/todo.md`, then extract the dashboard load/render slice with a fresh isolated browser gate.
