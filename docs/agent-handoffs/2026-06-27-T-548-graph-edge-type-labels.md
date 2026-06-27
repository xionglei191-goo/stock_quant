# Handoff: T-548 知识图谱关系边显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-548
- Handoff type: implementation
- Roadmap state: DONE

## Objective

知识图谱画布边 label 和“图谱关系”表也使用“事实股东 / 上游关系”等中文关系名，避免过滤 chip 已中文化但图谱主体仍显示 `shareholder` 等 raw 枚举；同时 link type、raw graph payload 和 trace 继续保留原始关系类型。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - `/api/graph/query` response schema
  - Graph filtering semantics
  - Database schema or relationship enum changes

## Background

T-545 到 T-547 已让图谱过滤 chip、多维关系表、关键事实和关系候选审核队列使用中文关系类型。但知识图谱的公司关系边仍用 raw `relationship_type` 生成边 label，导致用户进入图谱后仍可能看到 `shareholder`。

## Problem Statement

图谱过滤条和图谱主体的关系名称必须一致。可见 label 应该中文化，但 raw `relationship_type` 仍需要保留给过滤、trace、脚本断言和审计。

## Expected Deliverables

- Graph canvas link label uses Chinese relationship type where available.
- `graphEdgeRows` visible topic/finding uses Chinese relationship type.
- Raw `relationship_type` remains in trace and `knowledgeGraphState.raw`.
- Browser acceptance covers visible Chinese labels plus raw preservation.

## Current Findings

- `makeGraphModel()` previously called `addLink(..., item.relationship_type, statusLabel(item.relationship_type), item)`.
- `renderKnowledgeGraph()` used `graphEdgeLabel(item.type)` for every edge row, which returns “公司关系” for generic company edge types but not the specific relationship name.
- Existing browser acceptance expected `#graphEdgeRows` to include raw `shareholder`.

## Proposed Work Plan

1. Use `relationshipTypeDisplayLabel()` for company relationship edge labels in `makeGraphModel()`.
2. Use `relationshipTypeDisplayLabel(item.relationship_type)` for `graphEdgeRows` when the edge carries a relationship type.
3. Update browser acceptance to require “事实股东” in visible columns while preserving raw `shareholder` in trace/raw graph data.
4. Update static contract, API contract, task ledger, and handoff.

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `relationshipTypeDisplayLabel()`.
- Existing graph rendering and browser acceptance fixtures.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance planned
- [x] Handoff validation planned

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=35`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- First `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60`
  - Result: failed, 45/46 checks passed.
  - Cause: the updated graph edge assertion triggered `openRelationshipGraphContext()` without awaiting its async `loadEntity()` path.
- Second `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60`
  - Result: failed, 45/46 checks passed.
  - Cause: the assertion inspected the first graph edge row, but the shareholder edge is not guaranteed to be the first rendered edge.
- Final `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60`
  - Result: passed, 46/46 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t548`, local-only evidence.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: corrected py_compile, UI static check, final browser acceptance.
- Failed: first two browser acceptance runs failed due to acceptance timing/row selection issues; both were fixed.
- Not run: full unit suite, because this was a focused UI display-label change and browser/static checks cover the touched path.

## Decisions

- Do not rewrite graph edge `type`; only the visible label changes.
- Use the same shared relationship display helper across graph chips, tables, review queues, and graph edges.
- Keep raw `relationship_type` available in trace and raw graph payload.
- Browser assertions should await `openRelationshipGraphContext()` and locate the relationship edge row by row content rather than assuming first-row ordering.

## Risks and Open Questions

- Unknown future relationship types still fall back to raw display until added to `relationshipTypeDisplayLabel()`.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t548`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`, not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_ownership_approved_graph_filter_loads_shareholder_edge`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible labels changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

Continue scanning maintenance preview tables and graph inspector surfaces for raw enum leakage outside trace JSON.

## Next Steps

1. Continue relationship-chain UI readability audit.
2. Check graph inspector and maintenance preview tables for raw enum leakage.
3. Keep graph payload raw values intact while localizing visible labels.
