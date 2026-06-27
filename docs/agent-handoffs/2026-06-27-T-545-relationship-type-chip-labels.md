# Handoff: T-545 关系类型图谱过滤显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-545
- Handoff type: implementation
- Roadmap state: DONE

## Objective

图谱过滤条面对用户显示“上游关系 / 事实股东 / 股东候选”等中文关系类型，而不是直接显示 `upstream_of`、`shareholder_candidate` 等 raw 枚举；同时保留 raw 关系类型给脚本和审计追溯。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - `/api/graph/query` 查询语义
  - 后端 relationship type 枚举
  - 数据库 schema 或数据重建

## Background

T-543 已让 `industryDirection` chip 中文化并保留 raw 追溯。但 `relationshipType` chip 仍直接显示 raw 枚举，例如 `upstream_of` 和 `shareholder`，对用户理解不够直接。

## Problem Statement

用户在图谱过滤条里需要看到业务语义，而不是内部枚举。完全替换 raw 会影响测试和审计，因此需要显示值中文化、raw 值继续保留。

## Expected Deliverables

- `relationshipType` chip 显示常见关系类型中文。
- `data-filter-raw-value` 和 title 保留原始关系类型。
- 浏览器验收覆盖产业链推荐入口和事实股东关系入口。

## Current Findings

- `graphFilterDisplayValue()` 已用于 holder label 和 industry direction 显示值替换。
- `renderKnowledgeGraphFilterChips()` 已把 raw 值写入 `data-filter-raw-value` 和 title。

## Proposed Work Plan

1. 在 `graphFilterDisplayValue()` 中加入 `relationshipType` 显示映射。
2. 更新浏览器验收，断言中文显示和 raw 追溯同时存在。
3. 更新静态契约、API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t545 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing graph filter chip rendering.
- Existing relationship graph click paths.
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

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=31`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t545 --timeout 60`
  - Result: passed, 45/45 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t545`, local-only evidence.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t545 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: all planned checks passed.
- Failed: none known.
- Not run: none planned.

## Decisions

- Keep raw relationship types in `data-filter-raw-value` and title.
- Only localize the user-facing chip label.
- Cover common company, industry, and ownership relationship types; unknown types still display raw.

## Risks and Open Questions

- Unknown relationship types remain raw until a mapping is added. This is acceptable because raw trace remains correct.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t545`: local-only browser acceptance evidence after final run.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: no backend business logic changed; this is a UI display mapping.
- What focused regression protects the facade behavior: browser acceptance asserts relationship type chip displays Chinese while retaining raw enum trace values.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI display behavior changed only; API/storage and no-broker boundaries did not change.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
