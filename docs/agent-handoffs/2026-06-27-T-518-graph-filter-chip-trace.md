# Handoff: T-518 Graph Filter Chip Trace

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Governance Security and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Keep graph filter chips readable while retaining raw filter key/value traceability for audit and diagnostics.

## Scope

- In scope: graph filter chip DOM attributes, chip title trace text, browser acceptance assertion, roadmap and handoff.
- Out of scope: backend graph query behavior, storage schema, canonical holder identity mapping, data governance policy changes.

## Background

T-517 changed same-holder graph chips from raw holder keys to readable holder names. That improves usability but removes the raw key from visible text. Operators still need a way to inspect the exact filter key/value used for graph queries.

## Problem Statement

The UI should show `股东: Alpha Capital` but preserve `ownershipHolderKey=external_company_alpha_capital` in a structured, inspectable way.

## Expected Deliverables

- Add structured raw trace attributes to each graph filter chip.
- Preserve readable holder labels in chip text.
- Extend browser acceptance to verify raw holder key trace is retained without leaking into visible chip text.

## Current Findings

- `renderKnowledgeGraphFilterChips()` is the single rendering point for graph filter chips.
- `knowledgeGraphState.activeFilters` already keeps raw filter values.
- The browser acceptance can inspect DOM dataset and title without adding new visible controls.

## Proposed Work Plan

- Completed: add `data-filter-key` and `data-filter-raw-value` to graph filter chip badges.
- Completed: add a `title` string with `过滤追溯: key=value`.
- Completed: update holder-key browser acceptance to assert readable chip text and raw-key trace attributes.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t518 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The trace is exposed in local DOM attributes, which is acceptable for this local-first app but should not include secrets. Current graph filters are local IDs, relationship types, and holder keys.
- This does not add a visible trace popover; it only provides title/dataset trace.

## Dependencies

- T-516 graph active filter chips.
- T-517 holder label display.
- Existing `escapeHtml()` UI helper.

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
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t518 --timeout 60` passed with 35/35 checks. The holder-key graph check asserts readable text, hidden raw key, and raw-key trace via `data-filter-raw-value` plus title.

## Next Recommended Action

Consider adding a small trace popover or copy action for graph chips if analysts need to copy scoped query parameters during manual review.
