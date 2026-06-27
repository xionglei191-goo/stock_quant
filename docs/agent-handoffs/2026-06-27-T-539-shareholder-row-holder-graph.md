# Handoff: T-539 股东/持有人行直达同一持有人网络

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-539
- Handoff type: implementation
- Roadmap state: DONE

## Objective

当用户看到某个 13F/持仓股东时，可以从“股东/持有人”这一行本身直接展开“该持有人还持有哪些公司”，不必先找到二跳“股东关联公司”行。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 后端 `/api/graph/query` holder-key 逻辑
  - `relationship_context` schema
  - 真实外部持仓数据接入

## Background

T-532 已让“股东关联公司”行可以按同一 13F/持仓持有人进入动态图谱，但“股东/持有人”普通行仍只是打开公司中心图。用户看到某个股东时，最自然的问题就是“这个股东还持有哪些公司”，因此普通股东行也应携带 holder-key 图谱入口。

## Problem Statement

普通 `ownership.shareholders[]` 行没有 `data-institutional-holder-key` 时，用户必须依赖二跳关联行或图谱推荐入口，链路不够直观。

## Expected Deliverables

- “股东/持有人”行写入 `data-institutional-holder-key` 和 `data-institutional-holder-label`。
- 浏览器验收覆盖普通股东行点击进入同一持有人网络。
- API 合同和任务台账记录该 UI 入口。

## Current Findings

- `relationship_context.ownership.shareholders[]` 已有标准化 `holder_key`。
- `/api/graph/query` 已支持 `institutional_holder_key`。
- 图谱 chip 已能显示 “13F持有人” 和可读 label。

## Proposed Work Plan

1. 更新普通股东/持有人行 action attrs。
2. 新增浏览器验收检查。
3. 更新 API 合同、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t539 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `relationship_context.ownership.shareholders[].holder_key`.
- Existing `/api/graph/query` institutional holder filter.
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

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` -> passed
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py` -> passed
- `python3 scripts/ui_static_check.py` -> passed, `required_functions=162`, `required_ids=379`, `text_snippets=23`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t539 --timeout 60` -> passed, 42/42 checks, evidence `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t539`
- `python3 scripts/check_handoffs.py` -> passed
- `git diff --check` -> passed

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: the change is only in UI row attributes and browser acceptance; no service/module logic was required.
- What focused regression protects the facade behavior: browser acceptance exercises the existing company-intelligence and graph APIs through the UI.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed; API/storage/no-broker boundaries did not.

## Decisions

- Use the same `institutional_holder_key` path as “股东关联公司” rows and recommended 13F graph queries.
- Keep the label as `holder_name || holder_key || holder_id` so graph chips remain readable.

## Risks and Open Questions

- No known open risk for T-539 after the browser acceptance rerun.

## Next Recommended Action

1. Run the planned verification commands.
2. Update this handoff Evidence section.
3. Continue with the next relationship-chain UX or API gap.
