# Handoff: T-541 产业链关系行点击保留方向追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-541
- Handoff type: implementation
- Roadmap state: DONE

## Objective

用户从“同类公司 / 上游公司 / 下游公司 / 产业链位置”行进入知识图谱时，图谱过滤条要明确保留这次展开的产业链方向，避免只看到链条和节点而不知道当前图谱来自哪条逻辑线。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 改变 `/api/graph/query` 后端查询语义
  - 新增数据库字段或重建数据库
  - 改变产业链推导算法

## Background

产业链关系行已经写入 `data-industry-direction`、`data-chain-id`、`data-chain-node-id` 等追溯属性。但点击进入图谱后，过滤 chip 只显示主体、关系类型、产业链和产业节点，用户看不到当前入口是同类、上游、下游还是产业链位置。

## Problem Statement

用户原始诉求强调“属于哪个板块、同类公司、上下游公司”要能在关系图谱中动态展示。已有图谱能按链条/节点展开，但方向状态没有留在图谱过滤条上，削弱了上下游逻辑线的可解释性。

## Expected Deliverables

- 图谱过滤状态支持 `industryDirection`。
- 点击产业链关系行时从 `data-industry-direction` 传入图谱上下文。
- 图谱 chip 展示“产业方向”并保留 raw direction 追溯值。
- 浏览器验收覆盖从上游行点击进入图谱后的方向 chip。

## Proposed Work Plan

1. Extend graph active filter display with `industryDirection`.
2. Pass `data-industry-direction` from industry relationship rows into `openRelationshipGraphContext()`.
3. Add static and browser acceptance coverage.
4. Update docs, roadmap, and handoff.

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t541 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `data-industry-direction` attributes on company relationship context rows.
- Existing `/api/graph/query` `chain_id` / `chain_node_id` filters.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Current Findings

- `renderCompanyRelationshipContext()` 已给产业链位置、同类、上游和下游行写入 `data-industry-direction`。
- `openRelationshipGraphContext()` 之前没有接收或保留该字段。
- `/api/graph/query` 已支持 `chain_id` / `chain_node_id`，本任务只增强 UI 追溯状态，不新增后端过滤字段。

## Files Touched

- `app/static/index.html`: 增加 `industryDirection` 过滤 label、active filter chip、pending filter 传递和点击事件参数。
- `scripts/ui_interaction_acceptance.py`: 新增 `company_industry_relationship_row_click_preserves_direction_chip` 浏览器验收。
- `scripts/ui_static_check.py`: 增加 `industryDirection` 和“产业方向”静态文本检查。
- `docs/api-contracts.md`: 记录产业链方向 chip 的 UI 合同和后端查询非目标。
- `tasks/todo.md`: 记录 T-541 完成状态和验收口径。

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance rerun
- [x] Handoff validation rerun

## Commands Run

```bash
python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t541 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: all planned checks passed.
- Failed: none known.
- Not run: none planned.

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=25`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t541 --timeout 60`
  - Result: passed, 44/44 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t541`, local-only evidence.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Decisions

- Keep `industryDirection` as UI trace state rather than an API query parameter, because the backend already scopes the graph by `chain_id` / `chain_node_id` and direction is a row-entry provenance label.
- Use the existing raw direction values: `position`, `peer`, `upstream`, `downstream`.

## Risks and Open Questions

- The chip communicates the entry direction, not an additional backend filter. This is intentional and documented.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t541`: local-only browser acceptance evidence after final run.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: no backend business logic changed; the task only adds UI filter trace state and validation.
- What focused regression protects the facade behavior: browser acceptance clicks an upstream industry relationship row and asserts the graph chip preserves `industryDirection=upstream` with chain and node filters.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed by adding an active graph chip; API/storage and paper-only/no-broker boundaries did not change.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
