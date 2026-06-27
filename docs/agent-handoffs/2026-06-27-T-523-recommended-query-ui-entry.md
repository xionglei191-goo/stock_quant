# Handoff: T-523 Recommended Query UI Entry

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Render `relationship_context.dynamic_graph.recommended_queries` as visible, clickable graph entry rows in the company intelligence relationship table.

## Scope

- In scope: company intelligence relationship context rendering, UI static contract, API contract note, roadmap entry, handoff.
- Out of scope: graph query API behavior, backend recommended query generation, storage schema, browser acceptance expansion.

## Background

T-522 added `dynamic_graph.recommended_queries[]` with concrete graph query suggestions. Before this task, those suggestions were only available through the API payload or advanced trace, so users did not have a visible entry point.

## Problem Statement

The relationship chain should be directly explorable from the UI. If recommended graph queries are not rendered, the analyst still has to infer graph actions from separate rows instead of following the API-provided exploration path.

## Expected Deliverables

- Add a UI helper that maps recommended query payloads to `open-relationship-graph` data attributes.
- Render the first few recommended queries as `图谱推荐入口` rows.
- Preserve existing relationship context rows and click handler behavior.
- Update static checks, API contracts, roadmap, and handoff.

## Current Findings

- `renderCompanyRelationshipContext()` is the single place rendering the company intelligence relationship table.
- `open-relationship-graph` already accepts issuer, security, relationship type, chain, chain node, and holder-key dataset attributes.
- `renderInsightTable()` already supports row-level `actionAttrs`, so no new table component is required.

## Proposed Work Plan

- Completed: add `recommendedGraphQueryAttrs()` inside `renderCompanyRelationshipContext()`.
- Completed: render `context.dynamic_graph.recommended_queries` as `图谱推荐入口` rows.
- Completed: add `recommendedGraphQueryAttrs` to `scripts/ui_static_check.py`.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- This renders the first eight recommended queries to keep the relationship table compact while preserving holder-key entries that appear after base relationship-type suggestions.
- Browser acceptance is not expanded in this task; static UI contract protects the helper and existing click handler already covers the data-action path.

## Dependencies

- T-522 `dynamic_graph.recommended_queries[]`.
- Existing `openRelationshipGraphContext()` and click delegation for `data-action="open-relationship-graph"`.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m py_compile scripts/ui_static_check.py` passed.
- `python3 scripts/ui_static_check.py` passed with `required_functions=162`, `required_ids=379`, and `node_check=passed`.
- `python3 scripts/check_handoffs.py` passed, checking 97 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Add browser acceptance for clicking a `图谱推荐入口` holder-key row if this path becomes a primary user workflow.
