# Handoff: T-537 关系链补齐动作前端消费 target

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-537
- Handoff type: implementation
- Roadmap state: DONE

## Objective

让公司情报页“关系链缺口”按钮优先消费服务端 `target.ui_action`，减少前端硬编码映射对 API 语义的重复维护。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `tasks/todo.md`
  - `docs/agent-handoffs/2026-06-27-T-537-relationship-target-ui-consumption.md`
- Out of scope:
  - `app/service_modules/company_intelligence.py` 的关系生成逻辑
  - 关系数据库重建
  - 其他图谱入口的重构

## Background

T-536 已经把关系链必补/增强动作做成可路由的 `target` 元数据，但公司情报页“关系链缺口”按钮仍主要依赖层名硬编码决定 UI 动作。当前工作是把前端消费端真正切到 `target.ui_action`，让服务端自描述成为首选来源。

## Problem Statement

如果前端仍只靠层名映射，新增或调整关系动作时就必须同步改 UI 逻辑，容易和 API 自描述漂移。需要让按钮先读 `item.target.ui_action`，再保留层名兜底。

## Expected Deliverables

- 公司情报页关系缺口按钮透传 `data-target-ui-action`。
- 点击处理优先使用 `target.ui_action`。
- 静态检查与浏览器验收覆盖这条消费链路。
- `tasks/todo.md` 记录该前端消费改动。

## Current Findings

- 前端原本有 `backfillActionForLayer` 硬编码映射。
- 服务端 `relationship_context.next_actions` / `enhancement_actions` 已带 `target.ui_action`。
- `scripts/ui_static_check.py` 需要检查 `data-target-ui-action` 的文本契约，而不是把它放进函数名列表。

## Proposed Work Plan

1. 改造 `app/static/index.html`，让关系缺口按钮优先消费 `item.target.ui_action`。
2. 更新 `scripts/ui_interaction_acceptance.py` 和 `scripts/ui_static_check.py`。
3. 补 `tasks/todo.md`、运行验证、写 handoff。

## Validation Plan

- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- 浏览器验收：`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t537 --timeout 60`

## Dependencies

- 本地 UI 服务可访问 `http://127.0.0.1:8000`。
- T-536 的后端 target 元数据已存在。

## Blockers

- 当前无阻塞。

## Handoff Checklist

- [x] 任务范围和目标明确
- [x] 代码改动已完成
- [x] `tasks/todo.md` 已更新
- [x] 初步验证已运行
- [x] handoff 格式补齐
- [x] 浏览器验收重跑

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` -> passed
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py` -> passed
- `python3 scripts/ui_static_check.py` -> passed, `required_functions=162`, `required_ids=379`
- `python3 scripts/check_handoffs.py` -> passed after handoff format fix
- `git diff --check` -> passed
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t537 --timeout 60` -> passed, 40/40 checks, evidence `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t537`

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: this change only updates the browser UI consumer and acceptance/static checks; no new service behavior was introduced.
- What focused regression protects the facade behavior: existing company relationship context unit tests still pass, and UI acceptance should verify the click routing after the browser rerun.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed; API/storage boundaries did not.

## Decisions

- Keep the layer-name fallback in UI, but make `target.ui_action` the primary path.
- Treat the target consumption change as a separate roadmap item from API self-description.

## Risks and Open Questions

- No known open risk for T-537 after the browser acceptance rerun.

## Next Recommended Action

1. Rerun browser acceptance for the relationship gap buttons.
2. Keep future relationship actions target-driven by default.
3. Avoid reintroducing layer-name-only mapping in the company relationship panel.
