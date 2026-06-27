# Handoff: T-544 产业方向推荐过滤键自描述

## Status

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-544
- Handoff type: implementation
- Roadmap state: DONE

## Objective

让 `relationship_context.dynamic_graph.recommended_filters` 明确声明 `industry_direction`，避免 API 消费方看到推荐查询里的方向字段却无法从过滤键列表判断其含义和边界。

## Scope

- In scope:
  - `app/service_modules/company_intelligence.py`
  - `tests/test_system.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 新增 `/api/graph/query` 后端过滤参数
  - 改变 UI 点击行为
  - 数据库 schema 或数据重建

## Background

T-542 已让 `recommended_queries[].query.industry_direction` 表达方向级产业链推荐，T-543 已让 UI chip 显示中文并保留 raw 枚举。但 `recommended_filters` 仍未声明 `industry_direction`，API 自描述不完整。

## Problem Statement

推荐查询输出了一个字段，但过滤键列表没有同步声明。后续脚本、前端或 agent 只能从单条 query 推断该字段，无法通过推荐过滤键清单判断它是受支持的 UI 追溯字段。

## Expected Deliverables

- `dynamic_graph.recommended_filters` 包含 `industry_direction`。
- 单测覆盖该过滤键存在。
- API 合同记录它仍是 UI 追溯状态，不作为 `/api/graph/query` 新过滤参数。

## Current Findings

- `relationship_context()` 已生成方向级 recommended queries。
- UI 已消费 `query.industry_direction` 并渲染 `industryDirection` chip。
- 只缺 API 自描述列表同步。

## Proposed Work Plan

1. 在 `recommended_filters` 中加入 `industry_direction`。
2. 更新聚焦单测。
3. 更新 API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- T-542 direction-level recommended query support.
- T-543 graph chip display support.

## Blockers

- Current: none.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance not required for display-neutral API self-description change
- [x] Handoff validation rerun

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`
  - Result: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=28`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: all planned checks passed.
- Failed: none known.
- Not run: none planned.

## Decisions

- `industry_direction` is included in recommended filter self-description, but not sent to `/api/graph/query`.
- The backend query remains scoped by existing `relationship_type`, `chain_id`, and `chain_node_id`.

## Risks and Open Questions

- No known blocker. This is an API self-description alignment change.

## Artifacts

- No new browser artifact required. Existing T-543 clean browser evidence covers the UI consumption path.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: the relationship context response is assembled in `app/service_modules/company_intelligence.py`; no `SystemService` change is needed.
- What focused regression protects the facade behavior: `test_company_intelligence_first_class_models_are_exposed_and_aggregated` asserts `industry_direction` appears in `recommended_filters`.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API response self-description changed; storage, UI behavior, and no-broker boundaries did not change.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
