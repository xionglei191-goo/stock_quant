# Handoff: T-543 产业方向图谱过滤显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-543
- Handoff type: implementation
- Roadmap state: DONE

## Objective

图谱过滤条面对用户显示“同类 / 上游 / 下游 / 产业链位置”，而不是直接显示 `peer/upstream/downstream/position` 枚举；同时保留 raw 枚举给脚本和审计追溯。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 后端关系查询语义
  - `relationship_context` 数据生成
  - 数据库 schema 或重建

## Background

T-541/T-542 已让产业链关系行和方向级推荐入口把 `industryDirection` 带入图谱过滤条。但 chip 显示值仍是 raw 枚举，例如 `upstream`，不够贴近用户在页面中看到的“上游公司”逻辑线。

## Problem Statement

用户需要在图谱中快速理解当前关系方向。直接显示英文枚举虽然可追溯，但不够直观；完全替换 raw 又会削弱脚本和审计验证。

## Expected Deliverables

- `industryDirection` chip 面向用户显示中文方向。
- `data-filter-raw-value` 和 title 仍保留 raw 枚举。
- 浏览器验收覆盖普通产业链行和推荐入口点击后的中文显示和 raw 追溯。

## Current Findings

- `graphFilterDisplayValue()` 已支持 holder label 的显示值替换。
- `renderKnowledgeGraphFilterChips()` 已把 raw 值写入 `data-filter-raw-value` 和 title。

## Proposed Work Plan

1. 在 `graphFilterDisplayValue()` 中加入 `industryDirection` 显示映射。
2. 更新浏览器验收，断言显示中文且 raw 保留。
3. 更新静态契约、API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t543 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- T-541 `industryDirection` graph chip support.
- T-542 direction-level recommended query support.
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
  - Result: passed, `text_snippets=27`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t543-clean --timeout 60`
  - Result: passed, 45/45 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t543-clean`, local-only evidence.
  - Note: an earlier run against `/tmp/ai_quant_t543_state.db` failed because the first direction-chip assertion checked the whole chip area for absence of `upstream`, while the relationship-type chip legitimately contained `upstream_of`. The final assertion checks only the `industryDirection` chip and passed on a clean DB.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t543 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: all planned checks passed.
- Failed: none known.
- Not run: none planned.

## Decisions

- Keep raw enum values in `data-filter-raw-value` and title.
- Only localize the user-facing chip label.
- Use existing direction vocabulary: `position` -> “产业链位置”, `peer` -> “同类”, `upstream` -> “上游”, `downstream` -> “下游”.

## Risks and Open Questions

- No known blocker. This is a display-only UI improvement.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t543`: local-only browser acceptance evidence after final run.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: no backend business logic changed; this is a UI display mapping.
- What focused regression protects the facade behavior: browser acceptance asserts industry direction chip displays Chinese while retaining raw enum trace values.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI display behavior changed only; API/storage and no-broker boundaries did not change.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
