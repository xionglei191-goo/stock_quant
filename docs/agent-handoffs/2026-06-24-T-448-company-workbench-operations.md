# Handoff: T-448 Company Workbench Operations

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-448

## Objective

Expose the T-444 through T-447 company database operations in the company intelligence workbench so users can see and run coverage audit, batch build preview, report realization review and relationship candidate review from `/ui`.

## Scope

- In scope: static UI controls, JavaScript API calls, company workbench rendering, UI static contract, browser interaction acceptance script, todo and handoff updates.
- Out of scope: new backend APIs, real broker integration, external crawling, relationship review permissions, charts, persistent batch run history.

## Background

The backend had gained relationship candidate review, coverage audit, batch build and research report realization update endpoints. The user previously reported that running the platform still looked empty, so these operations need visible workbench entry points rather than API-only behavior.

## Problem Statement

Backend-only company database operations do not help the user operate the platform day to day. The workbench needs compact controls that make the database completion loop visible while preserving dry-run defaults and paper-only boundaries.

## Expected Deliverables

- Add a company database operations panel to the company intelligence tab.
- Add coverage audit, batch build preview/execute and report realization preview/update controls.
- Add a relationship candidate review table with approve, reject and merge actions.
- Update UI static checks for new controls/functions.
- Add browser acceptance checks for the non-destructive preview paths.

## Current State

- Completed: company database operations panel is visible in `/ui`.
- Completed: coverage audit and batch build preview/execute call the existing backend endpoints.
- Completed: report realization preview/update calls the existing backend endpoint.
- Completed: relationship candidate table renders candidate relationships and supports approve/reject/merge.
- Completed: static UI and browser acceptance scripts know about the new controls.
- Blocked: none for this slice.

## Current Findings

- Existing UI style is a dense operational dashboard; the new controls reuse panels, rows, tables and system-strip counters.
- Relationship candidate review needs a target relationship ID for merge, so the UI uses one compact merge-target input.
- Browser acceptance should stay non-destructive by default, so it exercises dry-run/preview paths.

## Proposed Work Plan

1. Keep controls compact and located in the existing company intelligence tab.
2. Default browser acceptance to audit/preview checks.
3. Leave richer queues, filtering and charts to follow-up tasks after users validate the workflow.

## Validation Plan

- Run `python3 scripts/ui_static_check.py`.
- Compile changed UI acceptance script.
- Run full `make local-ci` before final closeout if feasible.
- Run browser interaction acceptance when a local server/browser path is available.

## Files Touched

- `app/static/index.html`: added company database operations panel, relationship review panel and supporting JavaScript.
- `scripts/ui_static_check.py`: added new control IDs and JavaScript functions.
- `scripts/ui_interaction_acceptance.py`: added preview-path browser checks for coverage audit, batch build and report realization; made existing hotspot and portfolio checks robust against current local data state.
- `tasks/todo.md`: added T-448 completion entry.
- `docs/README.md`: updated task range through T-448.
- `docs/agent-handoffs/README.md`: added T-448.
- `docs/agent-handoffs/2026-06-24-T-448-company-workbench-operations.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
docker compose restart ai-quant-org
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --timeout 60
make local-ci
```

Result:

- Passed: UI static check after adding controls.
- Passed: `scripts/ui_static_check.py` compile.
- Passed: `scripts/ui_interaction_acceptance.py` with 12/12 browser checks, including the three new company database operation preview paths.
- Passed: `make local-ci`, including compile, 223 tests, UI static check, security check and handoff validation.

## Decisions

- The batch build panel exposes both preview and execute; browser acceptance only checks preview.
- Report realization exposes preview and execute; the API remains opinion-layer only.
- Candidate relationship merge uses a single target ID field rather than building a full queue UI in this slice.
- No visual redesign was introduced; the page stays data-dense and workbench-oriented.

## Dependencies

- T-444 relationship review API.
- T-445 coverage audit API.
- T-446 batch build API.
- T-447 research report realization API.
- Existing static UI helpers: `api`, `rows`, `statusLabel`, `compactId`, `userPretty`.

## Blockers

- None for this slice.

## Risks and Open Questions

- Relationship review still lacks filtering, bulk actions and reviewer role enforcement in the UI.
- Batch build execute can be slow on large targets; future work should add run history and resumability.
- Report realization still uses latest close versus target price; richer horizon-aware scoring is pending.

## Handoff Checklist

- [x] Company database operations panel added.
- [x] Relationship candidate review panel added.
- [x] New UI functions wired to backend APIs.
- [x] Static UI contract updated.
- [x] Browser acceptance preview paths added.
- [x] Todo and handoff indexes updated.

## Evidence

Commands run:

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
docker compose restart ai-quant-org
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --timeout 60
make local-ci
```

Result:

- Passed: UI static contract and Node syntax check.
- Passed: Python compile for UI static check script.
- Passed: Python compile for UI interaction script.
- Passed: browser interaction acceptance, 12 checks and 0 failures.
- Passed: full `make local-ci`.

## Artifacts

- None produced.

## Next Recommended Action

Add richer filtering and batch actions for relationship candidate review after the user validates the new workbench controls.
