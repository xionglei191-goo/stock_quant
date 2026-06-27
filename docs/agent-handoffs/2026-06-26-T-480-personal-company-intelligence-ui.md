# Handoff: T-480 Personal Company Intelligence UI

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-480

## Objective

Simplify the company intelligence workbench for a personal user who wants to read all-weather company intelligence and market analysis first, while keeping advanced maintenance tools available.

## Scope

- In scope: `app/static/index.html`, UI static contract, browser acceptance, roadmap and handoff.
- Out of scope: backend API changes, data model changes, route changes, deleting existing maintenance tools.

## Background

The company intelligence page had grown into a dense operations console: company profile, events, relationships, reports, batch builds, material inbox, assertion conflicts, run histories and JSON debug output were all visible at once. For a personal research user, the first screen should prioritize company interpretation, facts, viewpoints, feedback and next action.

## Problem Statement

The UI exposed too many engineering controls by default. Users had to visually parse maintenance actions before seeing what the company intelligence system concluded or what they should do next.

## Expected Deliverables

- A default personal research summary area.
- Advanced maintenance sections folded by default.
- Existing DOM IDs and interaction paths preserved for current scripts.
- UI static and browser interaction acceptance kept passing.

## Current Findings

- Existing `renderCompanyIntelligence` already has all data required for a personal summary.
- Existing tests and interaction scripts depend on DOM IDs, so the change should hide/reframe controls rather than rename or remove them.
- Browser acceptance can validate that folded maintenance controls remain functionally reachable.

## Proposed Work Plan

1. Add a compact personal research summary with current judgment, latest fact, viewpoint change and feedback/next step.
2. Fold database maintenance, material inbox, conflict review, run history, event/relationship review, report structure and raw JSON into advanced `details` sections.
3. Preserve all existing IDs/functions.
4. Update UI static contract.
5. Run UI static and browser interaction acceptance.

## Validation Plan

- Run `python3 scripts/ui_static_check.py`.
- Start a current-code temporary service.
- Run `python3 scripts/ui_interaction_acceptance.py <base-url> --output-dir artifacts/ui-interaction-acceptance-personal-ui-current`.

## Current State

- Completed: personal research summary cards added.
- Completed: advanced maintenance areas are folded by default.
- Completed: all prior controls and IDs remain present.
- Completed: static and browser acceptance pass.
- Blocked: None.

## Dependencies

- Existing company intelligence aggregation payload.
- Existing UI interaction acceptance script.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: added personal summary UI/rendering and advanced folded sections.
- `scripts/ui_static_check.py`: added personal summary and folded-section IDs/functions.
- `tasks/todo.md`: added DONE T-480.
- `docs/agent-handoffs/2026-06-26-T-480-personal-company-intelligence-ui.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= python3 -c 'from app.server import serve; serve(port=8770)'
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8770 --output-dir artifacts/ui-interaction-acceptance-personal-ui-current
```

Result:

- Passed: UI static check.
- Passed: browser interaction acceptance, 28/28 checks.
- Failed: initial browser run against stale `8000` service and first current-code run had one manifest display assertion; both issues were resolved or superseded by final current-code acceptance.

## Evidence

- UI static result: `status_labels=9`, `required_ids=300`, `required_functions=109`, `node_check=passed`.
- Browser acceptance result: `status=passed`, `failure_count=0`, `check_count=28`, output under `artifacts/ui-interaction-acceptance-personal-ui-current`.

## Decisions

- Kept maintenance capabilities in the same page but folded, instead of moving routes or deleting controls.
- Preserved existing IDs and functions to avoid breaking scripts and acceptance coverage.
- Used the current company intelligence payload for summary cards; no new backend endpoint was needed.

## Risks and Open Questions

- The page is simpler by default, but the app is still a dense single-page tool. A future route split could further improve personal use.
- Advanced sections remain accessible but still contain many controls; future work can group them into separate tabs.

## Artifacts

- `artifacts/ui-interaction-acceptance-personal-ui-current`: local-only browser acceptance evidence, not acceptable for non-local production release gates.

## Handoff Checklist

- [x] UI change completed.
- [x] UI static contract updated.
- [x] Browser acceptance passed.
- [x] `tasks/todo.md` updated.
- [x] Handoff created.

## Next Steps

1. Optionally split advanced maintenance into a separate tab if the page still feels dense after hands-on use.
2. Commit and push T-480 when ready.

## Next Recommended Action

Commit and push T-480 after final diff review.
