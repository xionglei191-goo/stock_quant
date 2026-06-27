# Handoff: T-549 图谱 inspector 相邻关系显示中文关系名

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-549
- Handoff type: implementation
- Roadmap state: DONE

## Objective

知识图谱右侧 inspector 的“相邻关系”也显示“事实股东 / 上游关系”等具体中文关系名，而不是泛化成“公司关系”或暴露 raw 枚举，保持图谱画布、边表、过滤 chip 和 inspector 语义一致。

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

T-548 已让图谱画布边 label 和“图谱关系”表显示中文关系名。但 inspector 的相邻关系仍通过 `graphEdgeLabel(link.type, link.label)` 渲染；对于公司关系，`graphEdgeLabel()` 会优先按 type 泛化为“公司关系”，没有展示具体的“事实股东”。

## Problem Statement

用户点选图谱节点后，右侧相邻关系必须与画布和边表使用同一业务语义。否则过滤 chip 和边表显示“事实股东”，inspector 却只显示“公司关系”，关系链路解释不完整。

## Expected Deliverables

- Graph inspector neighbor rows prefer the graph link label.
- For company relationship links, inspector neighbor rows show Chinese relationship names.
- Raw `relationship_type` remains in link metadata/raw graph payload.
- Browser acceptance covers inspector display.

## Current Findings

- `makeGraphModel()` now stores localized relationship names in `link.label`.
- `renderKnowledgeGraphInspector()` still calls `graphEdgeLabel(link.type, link.label)`, which masks specific company relationship labels.

## Proposed Work Plan

1. Update inspector neighbor row rendering to prefer `link.label`.
2. Add browser acceptance that selects a node connected by a shareholder edge and verifies “事实股东” is shown.
3. Update static contract, API contract, task ledger, and handoff.

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `relationshipTypeDisplayLabel()`.
- Existing graph link label behavior from T-548.
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
  - Result: passed, `text_snippets=36`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- First `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`
  - Result: failed, 46/47 checks passed.
  - Cause: the acceptance tried to use a real graph layout edge that was not guaranteed to remain in the visible inspector neighbor set.
- Second `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`
  - Result: failed, 46/47 checks passed.
  - Cause: the self-contained fixture still used the previous graph focus, so the fixture edge was filtered out.
- Third `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`
  - Result: failed, 46/47 checks passed.
  - Cause: `addLink()` overwrote the already localized `link.label` by calling `graphEdgeLabel(type, label)`; `HAS_COMPANY_RELATIONSHIP` became the generic “公司关系”.
- Final `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`
  - Result: passed, 47/47 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t549`, local-only evidence.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: corrected py_compile, UI static check, final browser acceptance.
- Failed: first three browser acceptance runs failed while tightening the inspector regression; causes and fixes are recorded above.
- Not run: full unit suite, because this was a focused UI display-label change and browser/static checks cover the touched path.

## Decisions

- Prefer `link.label` in inspector neighbor rows because graph links already carry the user-facing semantic label.
- Keep `graphEdgeLabel()` as fallback for generic/non-company edges.
- Preserve explicit labels in `addLink()` instead of re-normalizing them through `graphEdgeLabel()`.
- Preserve raw `relationship_type` in metadata and raw graph payload.

## Risks and Open Questions

- Generic company edges without specific `relationship_type` still display the broad “公司关系” label.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t549`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`, not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_graph_inspector_neighbor_shows_relationship_label`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible labels changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

Continue scanning ownership manifest and maintenance preview tables for raw enum leakage outside trace JSON.

## Next Steps

1. Continue relationship-chain UI readability audit.
2. Check ownership manifest default-kind columns for raw `shareholder` display.
3. Keep graph payload raw values intact while localizing visible labels.
