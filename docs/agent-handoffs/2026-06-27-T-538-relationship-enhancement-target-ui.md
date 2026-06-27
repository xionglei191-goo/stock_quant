# Handoff: T-538 关系链增强动作前端 target 合并

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-538
- Handoff type: implementation
- Roadmap state: DONE

## Objective

让公司情报页“关系链缺口”里的可选增强层也消费服务端 `enhancement_actions.target`，使 13F 持有人网络和事实股东网络等增强补齐入口可点击、可追溯。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 后端 relationship schema 变更
  - 数据库重建
  - 新增真实外部数据源

## Background

T-535/T-536 已经让 API 输出 `enhancement_actions` 和每条 action 的 `target` 元数据，T-537 已让必补缺口按钮优先消费 `target.ui_action`。但 UI 的诊断行仍主要来自 `coverage_diagnostics.diagnostics`，可选增强层没有明确合并同 layer 的 `enhancement_actions.target`。

## Problem Statement

如果增强层只显示 diagnostics 文案，用户仍看不到机器可读的补齐入口，13F 持有人网络和事实股东网络这类“非必补但很有价值”的链路就没有形成 UI 闭环。

## Expected Deliverables

- 关系缺口 UI 按 layer 合并 `next_actions` 和 `enhancement_actions`。
- 增强层按钮透出 `data-target-ui-action`。
- 浏览器验收覆盖 `shareholder_network` 和 `approved_shareholder_network`。
- API 合同和任务台账记录这条 UI 消费规则。

## Current Findings

- `relationship_context.enhancement_actions` 和 `coverage_diagnostics.enhancement_actions` 都已存在。
- UI 原先只从 diagnostics 行渲染缺口，增强层不能稳定拿到 action target。
- 现已新增 `relationshipActionsByLayer`，统一合并必补和增强 action。

## Proposed Work Plan

1. 在 `renderCompanyRelationshipContext` 中按 layer 建立 action 索引。
2. 将 action 的 reason/target 合并回 diagnostics 行。
3. 补浏览器验收、静态契约、API 合同和任务记录。

## Validation Plan

- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t538 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- 本地 UI 服务可访问 `http://127.0.0.1:8000`。
- T-535/T-536 的 `enhancement_actions.target` API 已存在。

## Blockers

- 当前无阻塞。

## Handoff Checklist

- [x] 任务范围和目标明确
- [x] 代码改动已完成
- [x] `tasks/todo.md` 已更新
- [x] 文档/API 合同已更新
- [x] 浏览器验收重跑
- [x] handoff 检查通过

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` -> passed
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py` -> passed
- `python3 scripts/ui_static_check.py` -> passed, `required_functions=162`, `required_ids=379`, `text_snippets=23`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t538 --timeout 60` -> passed, 41/41 checks, evidence `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t538`
- `python3 scripts/check_handoffs.py` -> passed
- `git diff --check` -> passed

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: this change only updates UI consumption of existing relationship action metadata and acceptance/static checks.
- What focused regression protects the facade behavior: existing company relationship context unit tests still cover API action metadata; UI acceptance covers the enhanced target consumer path.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed; API/storage and no-broker boundaries did not.

## Decisions

- Keep one relationship gap row per diagnostics layer and merge target metadata into that row, rather than adding a separate enhancement-actions table.
- Keep layer fallback behavior in `relationshipGapActionHtml`, but use action target as the preferred source.

## Risks and Open Questions

- No known open risk for T-538 after the browser acceptance rerun.

## Next Recommended Action

1. Rerun browser acceptance on an isolated local service.
2. If it passes, update Evidence and checklist.
3. Continue the next relationship-chain gap from the roadmap rather than broad refactoring.
