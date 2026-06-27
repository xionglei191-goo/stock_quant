# Handoff: T-528 Shareholder Network UI Trace

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Expose `coverage_diagnostics.shareholder_network_summary` through the company intelligence `股东关联` summary metric as structured UI trace attributes.

## Scope

- In scope: company intelligence relationship summary rendering, static UI contract, browser acceptance assertion, API contract note, roadmap entry, handoff.
- Out of scope: backend diagnostics changes, storage schema, graph query behavior, layout redesign.

## Background

T-527 added `coverage_diagnostics.shareholder_network_summary` with total, fact-network, and holding-network counts. The UI top metric displayed visible split text, but the diagnostic summary was not available as structured DOM trace.

## Problem Statement

The relationship chain should be inspectable from the UI. Analysts and browser acceptance need to confirm that the visible `股东关联` count follows the diagnostics summary, not just an ad hoc frontend expression.

## Expected Deliverables

- Add `data-network-total`, `data-fact-network`, and `data-holding-network` to `companyIntelShareholderRelatedCount`.
- Add a title summarizing shareholder network coverage.
- Prefer `coverage_diagnostics.shareholder_network_summary` and retain summary field fallbacks.
- Add static and browser acceptance coverage.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `renderCompanyRelationshipContext()` already receives `coverage_diagnostics`.
- Existing browser acceptance creates a fact shareholder network where `fact_network=1`.
- The top metric element is a stable DOM target for structured trace attributes.

## Proposed Work Plan

- Completed: add dataset fields and title to `companyIntelShareholderRelatedCount`.
- Completed: protect the code path with `scripts/ui_static_check.py`.
- Completed: extend browser acceptance to assert `dataset.factNetwork`, `dataset.networkTotal`, and title.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t528 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The title is a compact trace, not a full explanatory UI. Longer provenance explanations remain in advanced trace and API payloads.
- Browser acceptance requires Chrome/Chromium and a clean local app server.

## Dependencies

- T-527 `coverage_diagnostics.shareholder_network_summary`.
- Existing same-holder browser acceptance fixture.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py` passed.
- `python3 scripts/ui_static_check.py` passed with `interaction_markers=18`, `required_functions=162`, `required_ids=379`, and `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t528 --timeout 60` passed with 36/36 checks; evidence URI `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t528`.
- `python3 scripts/check_handoffs.py` passed before browser run; rerun after final evidence update.
- `git diff --check` passed before browser run; rerun after final evidence update.
- Browser server was launched with explicit local SQLite/object-store overrides because `.env` contains PostgreSQL settings and this environment lacks `psycopg`.

## Next Recommended Action

Consider adding a visible source legend if users need the distinction between `事实` and `持仓` explained without hovering or inspecting DOM attributes.
