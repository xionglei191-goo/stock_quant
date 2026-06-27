# Handoff: T-517 Graph Holder Chip Label

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Make same-holder graph filter chips readable by showing the shareholder display name while keeping the stable holder key for graph queries.

## Scope

- In scope: static UI graph filter state, same-holder relationship row data attributes, browser acceptance assertion.
- Out of scope: backend graph query behavior, holder identity canonicalization, storage schema, database migration.

## Background

T-516 made active graph filters visible, but same-shareholder graph chips displayed the raw holder key such as `external_company_alpha_capital`. The underlying key is useful for deterministic queries but not ideal as user-facing text.

## Problem Statement

Users should see `股东: Alpha Capital` when opening an approved same-shareholder network. The system should still query by `ownership_holder_key` to avoid ambiguous name matching.

## Expected Deliverables

- Add optional `ownershipHolderLabel` to graph filter state.
- Pass `holder_name` from `approved_shareholder_related_companies` rows into graph actions.
- Render holder label in chips while preserving holder key for query state.
- Extend browser acceptance to assert the readable label.

## Current Findings

- `relationship_context.ownership.approved_shareholder_related_companies` already includes both `holder_key` and `holder_name`.
- `openRelationshipGraphContext()` can safely carry label-only context in `pendingFilters` because `loadEntity()` only serializes query parameters from the key fields.
- Direct acceptance graph renders can set `ownershipHolderLabel` through `setKnowledgeGraphActiveFilters()`.

## Proposed Work Plan

- Completed: add `graphFilterDisplayValue()` so chip rendering can display a label for holder-key filters.
- Completed: carry `ownershipHolderLabel` through `openRelationshipGraphContext()` and `loadEntity()` active filter state.
- Completed: add `data-ownership-holder-label` to "事实股东关联" graph action rows.
- Completed: update browser acceptance holder-key assertion to require `Alpha Capital` and reject raw key display in the chip.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t517 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- If a future graph entrypoint sets `ownershipHolderKey` without `ownershipHolderLabel`, the chip will fall back to the raw key. That is acceptable and keeps the scope visible.
- Holder display names are not canonicalized here; this only improves chip readability using already available context rows.

## Dependencies

- T-514 `approved_shareholder_related_companies.holder_name`.
- T-515 `ownership_holder_key` graph query filtering.
- T-516 graph active filter chips.

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
- `python3 scripts/ui_static_check.py` passed.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t517 --timeout 60` passed with 35/35 checks. The holder-key graph check asserts the chip shows `Alpha Capital` and does not show raw `external_company_alpha_capital`.

## Next Recommended Action

Add a compact trace affordance to graph chips so the readable holder name can reveal the raw `ownership_holder_key` on demand.
