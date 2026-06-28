# Handoff: T-494 Personal Research Loop Overview

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-28
- Last agent: TRAE
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-494

## Objective

把数据健康、个人研究桌面、结论兑现评分和关系图谱降噪收敛为一个本地个人研究闭环总览，便于首页和后续脚本一次读取日常研究状态。

## Scope

- In scope: 个人研究闭环只读 API、领域读模型、首页总览展示、UI 静态契约、聚合接口回归测试、handoff。
- Out of scope: 存储 schema 迁移、真实交易、券商连接、外部生产证据回填、全量 UI 重设计、自动写入评分或质量归并结果。

## Background

T-493 已提供数据健康中心，T-496 已有模拟反馈兑现评分，T-497 已有事件/关系质量归并，T-494 需要把这些能力变成个人研究桌面上的日常闭环状态，而不是让用户分别打开多个维护入口。

## Problem Statement

系统已有大量独立能力，但用户无法在首页快速判断今天最该处理的是数据缺口、公司覆盖、结论兑现评分还是关系图谱噪声。缺少一个统一读模型会让产品继续表现为功能堆叠。

## Expected Deliverables

- `GET|POST /api/personal-research/loop-overview` 返回四主题闭环总览。
- 首页个人关注池面板展示研究闭环状态、数据待处理、兑现待评分和图谱待降噪。
- 聚合接口复用现有 dry-run 能力，不打开 UI 就写库。
- 聚焦单测和 UI 静态契约覆盖新增入口。

## Current Findings

- `data_health_summary`、`company_database_coverage_audit`、`update_simulation_feedback_performance` 和 `reconcile_company_database_quality` 已经具备本轮聚合所需数据。
- `app/service_modules/company_quality.py` 与 `app/service_modules/feedback_scoring.py` 已承载核心算法，本轮无需复制算法。
- 首页已有个人关注池面板，适合承载轻量总览而不是新增导航页。

## Proposed Work Plan

1. 新增领域读模型模块聚合四主题状态。
2. 在 `SystemService` 增加 facade 复用已有接口。
3. 注册个人研究闭环 API 路由和授权前缀。
4. 在首页个人关注池面板展示闭环总览。
5. 补充单测、UI 静态契约和 handoff。

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_personal_research_loop_overview_unifies_daily_research_status`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `git diff --check`

## Risks

- 首页加载会多调用一次聚合接口；当前接口内部会做 dry-run 质量与反馈预览，后续大数据量本机环境可考虑增加缓存或 limit 默认收紧。
- UI 目前是状态总览，尚未做真实浏览器点击验收和更细的操作按钮联动。

## Dependencies

- T-493 数据健康中心。
- T-496 模拟反馈兑现评分。
- T-497 公司事件/关系质量归并。
- 现有个人研究桌面首页结构和 UI 静态检查脚本。

## Blockers

- 无。

## Handoff Checklist

- [x] 后端读模型和 API 已完成。
- [x] 首页总览展示已完成。
- [x] 聚焦测试已新增并通过。
- [x] UI 静态契约已更新并通过。
- [x] SystemService Growth Freeze Review 已记录。

## Evidence

- `app/service_modules/personal_research_loop.py`: 四主题聚合读模型，固定 paper-only/no-broker 边界。
- `app/services.py`: `personal_research_loop_overview` facade 复用数据健康、覆盖审计、模拟反馈评分和质量归并 dry-run。
- `app/api.py`: `/api/personal-research` 授权前缀和 handler。
- `app/api_routes.py`: `GET|POST /api/personal-research/loop-overview`。
- `app/static/index.html`: 首页个人关注池面板新增研究闭环状态展示。
- `tests/test_system.py`: `test_personal_research_loop_overview_unifies_daily_research_status`。

## Current State

- Completed: 新增个人研究闭环领域读模型、API facade、路由、首页总览卡片、静态 UI 检查 ID 和后端回归测试。
- In progress: 无。
- Not started: 真实浏览器点击验收、按用户偏好进一步调整首页视觉层级。
- Blocked: 无。

## Files Touched

- `app/service_modules/personal_research_loop.py`: 新增四主题聚合读模型。
- `app/services.py`: 新增 `personal_research_loop_overview` facade。
- `app/api.py`: 新增 API handler 与授权前缀。
- `app/api_routes.py`: 新增个人研究闭环路由。
- `app/static/index.html`: 新增首页研究闭环总览展示。
- `scripts/ui_static_check.py`: 新增 UI 元素静态检查。
- `tests/test_system.py`: 新增聚合接口回归测试。
- `docs/agent-handoffs/2026-06-28-T-494-personal-research-loop-overview.md`: 本交接记录。

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_personal_research_loop_overview_unifies_daily_research_status
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
git diff --check
```

Result:

- Passed: 聚焦单测、UI 静态检查、Python 编译、`git diff --check`。
- Failed: 首次 `python3 scripts/check_handoffs.py` 因 handoff 章节格式不符合当前校验器失败；已改为标准章节并待复验。
- Not run: 全量 `python3 -m unittest discover -s tests` 和完整 `make local-ci` 尚未运行。

## Decisions

- 采用读模型聚合而不是新增 schema，原因是 T-493/T-502 已明确数据健康先做聚合视图、不迁移 schema。
- 兑现评分与图谱降噪只用 dry-run 预览，不在首页自动写库，避免日常打开 UI 产生副作用。
- 首页接入使用现有个人关注池面板，避免继续增加导航复杂度。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否，核心状态归并在 `app/service_modules/personal_research_loop.py`。
- Domain module usage: 已新增领域读模型模块；`SystemService` 仅作为 facade 调用既有 API 能力并传入 payload。
- Regression: `test_personal_research_loop_overview_unifies_daily_research_status` 覆盖 API、四主题 section、模拟反馈边界和图谱重复关系提示。
- Contract/boundary changes: 新增只读 API；无存储 schema 变更；UI 行为新增首页展示；paper-only/no-broker 边界未改变。

## Risks and Open Questions

- 首页加载会多调用一次聚合接口，后续可按本机数据量考虑缓存或更小默认 limit。
- UI 暂未补真实浏览器验收，当前只通过静态契约。

## Artifacts

- 无新增外部 artifact。

## Next Recommended Action

运行全量 `python3 -m unittest discover -s tests` 或 `make local-ci`，并在需要时补真实浏览器验收。
