# Handoff: T-546 多维关系表关系类型显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-546
- Handoff type: implementation
- Roadmap state: DONE

## Objective

公司情报“多维关系”和“关键事实”里的关系类型面对用户显示“事实股东 / 实控候选 / 同类关系”等中文标签，不再把 `shareholder`、`controller_candidate`、`industry_peer` 等 raw 枚举直出；同时继续在 trace 和 data 属性里保留 raw 值。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 后端 relationship type 枚举
  - `/api/graph/query` 查询语义
  - 数据库 schema 或数据重建

## Background

T-545 已让图谱过滤 chip 的关系类型显示中文并保留 raw 追溯。但“多维关系”表和“关键事实”里的关系类型仍可能直接显示 raw 枚举，导致用户在公司详情中看到内部字段值。

## Problem Statement

主表应该优先表达业务含义，raw 枚举应留给脚本、图谱过滤和审计追溯。如果直接删除 raw，会破坏动态图谱入口和验收可追溯性；如果继续直出 raw，则用户理解成本过高。

## Expected Deliverables

- 关系类型显示映射可复用。
- 多维关系表显示中文关系类型。
- 关键事实里的公司关系显示中文关系类型。
- trace 和 data 属性继续保留 raw 枚举。
- 浏览器验收覆盖中文主显示和 raw 追溯同时存在。

## Current Findings

- `graphFilterDisplayValue()` 已经承担图谱 chip 显示值转换。
- `renderCompanyRelationshipContext()` 的产业链、事实股权和候选关系行仍有 raw 枚举进入主表状态或发现文本。
- `renderCompanyIntelligence()` 的 `relationships.company_relationships` 行仍以 raw `relationship_type` 作为 subject/status。

## Proposed Work Plan

1. 抽出 `relationshipTypeDisplayLabel()` 统一管理关系类型中文映射。
2. 在图谱 chip、多维关系行和公司关系事实行复用该 helper。
3. 新增浏览器验收，断言可见表格前三列显示中文，trace 仍保留 raw。
4. 更新静态契约、API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t546 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `renderInsightTable()` row structure.
- Existing graph action `data-*` attributes.
- Existing local UI service for browser acceptance.

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

- `python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: failed as an invalid command because `app/static/index.html` is not Python; failed with `SyntaxError: invalid decimal literal`.
- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=33`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t546 --timeout 60`
  - Result: passed, 46/46 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t546`, local-only evidence.
- `git diff --check`
  - Result: passed.

## Commands Run

```bash
python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
rm -f /tmp/ai_quant_t546_state.db && rm -rf /tmp/ai_quant_t546_objects && AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_t546_state.db AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t546_objects AI_QUANT_SEARCH_BACKEND=local python3 -m app.server
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t546 --timeout 60
git diff --check
```

Result:

- Passed: corrected py_compile, UI static check, browser acceptance, and diff whitespace check passed.
- Failed: one invalid py_compile command failed because HTML was passed to Python.
- Not run: full unit suite, because this was a focused UI display-label change and browser/static checks cover the touched path.

## Decisions

- Use a shared `relationshipTypeDisplayLabel()` helper rather than embedding separate maps per row.
- Preserve raw relationship type values in trace JSON and `data-*` attributes.
- Keep unknown relationship types falling back to their raw value until a mapping is added.

## Risks and Open Questions

- Future new relationship types need to be added to `relationshipTypeDisplayLabel()` to avoid raw enum fallback in visible UI.
- The worktree contains broader relationship-chain changes from earlier tasks; this handoff only describes T-546.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t546`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`, not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_relationship_rows_display_chinese_type_labels`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible labels changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

Continue scanning company intelligence visible rows for other raw enum leakage outside relationship type fields, especially review queues and maintenance previews.

## Next Steps

1. Check relationship review queue rows for raw enum leakage.
2. Add mappings for any new `CompanyRelationship.relationship_type` values introduced later.
3. Keep browser acceptance focused on visible user-facing cells plus raw trace preservation.
