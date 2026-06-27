# Handoff: T-547 关系候选审核队列关系类型显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-547
- Handoff type: implementation
- Roadmap state: DONE

## Objective

高级维护里的“关系候选审核”队列也复用关系类型中文映射，避免 `customer_candidate` 等 raw 枚举在主审阅表直出；同时高级 trace 继续保留 raw 供审批、脚本和审计使用。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 关系候选审批 API
  - 关系候选晋升规则
  - 数据库 schema 或数据重建

## Background

T-546 已让“多维关系”和“关键事实”主表使用中文关系类型。但“高级维护：关系候选审核”仍通过 `statusLabel(item.relationship_type)` 显示候选类型，`customer_candidate` 会在可见审阅表中变成半英文标签。

## Problem Statement

审核队列是人工复核入口，主表需要直接呈现业务语义；raw 枚举仍需要保留给审批动作、脚本断言和 trace 审计。

## Expected Deliverables

- 关系候选审核队列显示中文关系类型。
- 审核队列 trace 保留 raw `relationship_type`。
- 浏览器验收覆盖中文可见值和 raw 追溯同时存在。
- API 契约和任务台账更新。

## Current Findings

- `relationshipTypeDisplayLabel()` 已包含 `customer_candidate` -> “客户候选”。
- `renderCompanyRelationshipReview()` 的第一列仍直接调用 `statusLabel(item.relationship_type || "关系候选")`。
- 现有 `company_relationship_review_queue_render` 验收只检查候选渲染、选择和审批按钮，没有检查 raw 枚举是否泄漏。

## Proposed Work Plan

1. 在 `renderCompanyRelationshipReview()` 里使用 `relationshipTypeDisplayLabel()`。
2. 扩展浏览器验收，断言可见前三列显示“客户候选”且不显示 `customer_candidate`。
3. 保留整行 trace 中 raw `customer_candidate` 的断言。
4. 更新静态契约、API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t547 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `relationshipTypeDisplayLabel()` from T-546.
- Existing relationship review queue rendering and browser acceptance fixture.
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
  - Result: passed, `text_snippets=34`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- First `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t547 --timeout 60`
  - Result: failed, 44/46 checks passed.
  - Related failure: `company_relationship_review_queue_render` showed raw `customer_candidate` in the first three columns because the advanced trace was still embedded in the first column.
  - Follow-up fix: moved `renderAdvancedTrace("关系候选追溯", item)` from the first column to the operation column.
- Final `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t547 --timeout 60`
  - Result: passed, 46/46 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t547`, local-only evidence.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t547 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: corrected py_compile, UI static check, final browser acceptance.
- Failed: first browser acceptance run failed before trace placement was corrected.
- Not run: full unit suite, because this was a focused UI display-label change and browser/static checks cover the touched path.

## Decisions

- Reuse `relationshipTypeDisplayLabel()` instead of adding a separate review-queue mapping.
- Preserve raw relationship type in advanced trace JSON.
- Put advanced trace in the operation column so the review decision columns stay business-readable.
- Keep approval API behavior unchanged.

## Risks and Open Questions

- Unknown future relationship types still fall back to raw display until added to `relationshipTypeDisplayLabel()`.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t547`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`, not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_relationship_review_queue_render`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible labels changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

Continue scanning maintenance previews for raw enum leakage outside relationship type fields.

## Next Steps

1. Continue relationship-chain UI readability audit.
2. Check maintenance preview tables for raw enum leakage.
3. Keep raw enum values in trace/data attributes when visible labels are localized.
