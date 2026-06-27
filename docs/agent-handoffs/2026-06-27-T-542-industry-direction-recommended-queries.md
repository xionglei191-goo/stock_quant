# Handoff: T-542 产业链图谱推荐入口细化到方向级

## Status

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-542
- Handoff type: implementation
- Roadmap state: DONE

## Objective

让“图谱推荐入口”不只给出泛化产业链节点图，还能直接推荐同类、上游、下游三个具体方向，用户从推荐入口进入图谱时能看到当前展开逻辑。

## Scope

- In scope:
  - `app/service_modules/company_intelligence.py`
  - `app/static/index.html`
  - `tests/test_system.py`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 新增 `/api/graph/query` 后端过滤参数
  - 改变产业链节点推导算法
  - 数据库重建或 schema 迁移

## Background

T-541 已让普通产业链关系行点击进入图谱后保留 `industryDirection` chip。但“图谱推荐入口”仍主要提供公司中心、产业链节点和泛化关系类型入口，产业链方向没有被作为推荐查询的一等入口。

## Problem Statement

用户从推荐入口进入图谱时，仍可能只看到链条和节点，而不知道本次推荐是同类、上游还是下游。对于“我看到某家公司，要知道属于哪个板块、同类公司、上下游公司”这个目标，推荐入口还不够直接。

## Expected Deliverables

- `dynamic_graph.recommended_queries[]` 输出方向级产业链推荐。
- 推荐查询包含 `industry_direction=peer/upstream/downstream`、`relationship_type`、`chain_id` 和 `chain_node_id`。
- UI 将 `query.industry_direction` 透传到 `data-industry-direction`。
- 浏览器验收覆盖从方向级推荐入口点击后保留方向 chip。

## Current Findings

- `relationship_context()` 已能汇总 `peer_rows`、`upstream_rows` 和 `downstream_rows`。
- 普通产业链关系行已写入 `data-industry-direction`。
- 图谱 chip 已支持 `industryDirection`，但推荐入口此前没有设置该属性。

## Proposed Work Plan

1. 在 `relationship_context()` 中为 peer/upstream/downstream 生成方向级推荐查询。
2. 更新推荐入口 DOM 属性，透传 `industry_direction`。
3. 补后端单测、浏览器验收、静态契约和 API 合同。

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t542 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing relationship context peer/upstream/downstream rows.
- T-541 `industryDirection` graph chip support.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance rerun
- [x] Handoff validation rerun

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`
  - Result: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=26`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t542 --timeout 60`
  - Result: passed, 45/45 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t542`, local-only evidence.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t542 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: all planned checks passed.
- Failed: none known.
- Not run: none planned.

## Decisions

- Use `industry_direction` inside recommended query payload as UI trace metadata, not as a new backend filter parameter.
- Keep actual graph query scoping on existing `relationship_type`, `chain_id`, and `chain_node_id`.
- Generate at most one recommendation per direction by using the first row in each direction bucket; this keeps the top UI recommendations focused and avoids crowding out shareholder network recommendations.

## Risks and Open Questions

- Direction-level recommendations are visible only when the relationship context has matching peer/upstream/downstream rows.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t542`: local-only browser acceptance evidence after final run.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: relationship recommendation generation already lives in `app/service_modules/company_intelligence.py`; no `SystemService` change is needed.
- What focused regression protects the facade behavior: `test_company_intelligence_first_class_models_are_exposed_and_aggregated` asserts peer/upstream/downstream recommended query directions, and browser acceptance asserts the UI click path preserves direction chips.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: response/UI shape changed by adding `query.industry_direction` to recommended queries; storage and no-broker boundaries did not change.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
