# Handoff: T-524 Recommended Query Browser Acceptance

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Add browser-level acceptance for clicking a relationship context `图谱推荐入口` row and loading the same fact shareholder network graph.

## Scope

- In scope: `scripts/ui_interaction_acceptance.py`, roadmap entry, handoff.
- Out of scope: application logic changes, graph query API changes, storage schema, UI layout redesign.

## Background

T-523 rendered `dynamic_graph.recommended_queries[]` as visible rows in the company intelligence relationship table. Static checks proved the helper and DOM contract existed, but no browser acceptance clicked the new row.

## Problem Statement

For a user-visible relationship chain, static DOM presence is not enough. The recommended graph entry should be verified through the same click path a user takes, including holder-key filter chips and graph data loading.

## Expected Deliverables

- Extend browser acceptance to locate the holder-key `图谱推荐入口` row.
- Click the row and assert the graph tab opens with the same fact shareholder network filter.
- Confirm both approved Alpha Capital holder relationships enter graph raw data.
- Update roadmap and handoff.

## Current Findings

- Existing browser acceptance already creates approved Alpha Capital relationships for DEMO and SPCX.
- The new `图谱推荐入口` row uses `data-action="open-relationship-graph"` and `data-ownership-holder-key`.
- Existing holder-key graph assertions can be reused after clicking the recommended row.

## Proposed Work Plan

- Completed: add `company_recommended_graph_query_click_loads_holder_network`.
- Completed: assert the row text includes `图谱推荐入口` and carries `data-ownership-holder-key="external_company_alpha_capital"`.
- Completed: assert graph filter chips and raw graph relationships after click.
- Completed: update `tasks/todo.md`.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t524 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The browser check depends on the local app server and Chrome/Chromium availability.
- The check is intentionally focused on the holder-key recommended query; other recommended query types remain covered by static rendering and existing graph click behavior.

## Dependencies

- T-523 recommended query UI rows.
- Existing browser acceptance fixture that registers approved Alpha Capital same-holder relationships.
- Existing `openRelationshipGraphContext()` click handler.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py` passed.
- `python3 scripts/ui_static_check.py` passed.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t524 --timeout 60` passed with 36/36 checks; evidence URI `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t524`.
- `python3 scripts/check_handoffs.py` passed before browser run; rerun after final evidence update.
- `git diff --check` passed before browser run; rerun after final evidence update.
- Browser server was launched with explicit local SQLite/object-store overrides because `.env` contains PostgreSQL settings and this environment lacks `psycopg`.

## Next Recommended Action

Consider adding a compact UI grouping for recommended graph entries if the relationship table grows too dense after more query types are added.
