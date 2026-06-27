# Handoff: T-516 Graph Active Filter Chips

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Make active graph query filters visible in the relationship graph UI so users can tell whether the current graph is a full graph, a relationship-type subgraph, a chain-node subgraph, or a same-holder shareholder network.

## Scope

- In scope: static UI graph toolbar, graph state, filter-chip rendering, UI static contract, browser acceptance assertions, roadmap status.
- Out of scope: backend graph-query behavior, storage schema, external graph database sync, source ingestion, broker integration.

## Background

T-515 added `ownership_holder_key` filtering and browser coverage for same-shareholder graph expansion. The remaining usability gap was that a graph opened from a relationship row did not visibly show the active relationship or holder-key scope.

## Problem Statement

The same graph canvas can represent different scopes. Without a visible filter chip, users may confuse a scoped relationship graph with the full company graph, especially when opening "事实股东关联" rows.

## Expected Deliverables

- Add a visible graph filter chip row.
- Persist active query filters in `knowledgeGraphState`.
- Show chips for issuer, security, relationship type, chain, chain node, and ownership holder key.
- Extend static UI contract and browser acceptance.

## Current Findings

- `openRelationshipGraphContext()` already carries pending graph filters into `loadEntity()`.
- `renderKnowledgeGraphExplorer()` is the stable place to refresh graph toolbar state during graph rerenders.
- Browser acceptance can validate both relationship-type and holder-key filter chips.

## Proposed Work Plan

- Completed: add `knowledgeGraphFilterChips` to the relationship graph toolbar.
- Completed: add `activeFilters` plus `setKnowledgeGraphActiveFilters()` and `renderKnowledgeGraphFilterChips()`.
- Completed: persist active filters from `loadEntity()` before graph query rendering.
- Completed: update `scripts/ui_static_check.py` required IDs/functions.
- Completed: extend `scripts/ui_interaction_acceptance.py` holder-key and shareholder graph assertions to verify visible chips.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t516 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The chip labels currently show normalized technical values such as `external company alpha capital`; future UI work can map holder keys to display names.
- Direct graph renders outside `loadEntity()` must call `setKnowledgeGraphActiveFilters()` when they represent a scoped graph.

## Dependencies

- Existing graph query parameters.
- Existing `knowledgeGraphState` and `renderKnowledgeGraphExplorer()`.
- Existing UI static and browser acceptance scripts.

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
- `python3 scripts/ui_static_check.py` passed after adding `knowledgeGraphFilterChips`, `setKnowledgeGraphActiveFilters`, and `renderKnowledgeGraphFilterChips` to the contract.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t516 --timeout 60` passed with 35/35 checks, including chip assertions in `company_ownership_holder_key_graph_click_loads_same_holder_network` and `company_ownership_approved_graph_filter_loads_shareholder_edge`.

## Next Recommended Action

Map technical holder keys to display names in graph chips, for example showing `股东: Alpha Capital` while preserving the raw holder key in trace details.
