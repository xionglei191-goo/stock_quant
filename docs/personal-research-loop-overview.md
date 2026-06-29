# 个人研究闭环总览

- Status: active
- Owner group: Product and UI, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-29
- Related tasks: T-493, T-494, T-496, T-497
- Scope: data health, company coverage, realization scoring, and graph noise reduction overview.
- Non-goals: 真实交易、券商连接、schema 迁移、外部生产证据。

## Purpose

把个人研究闭环从实现交接提升为正式文档，说明数据健康、公司覆盖、结论兑现评分和图谱降噪如何组成一个本地每日研究状态总览。

## Current Chain

1. 数据健康中心汇总行情、研报、公告、公司材料和运行状态。
2. 公司数据库覆盖率审计说明哪些层已补齐、哪些层仍缺失。
3. 模拟反馈兑现评分把分析结论和纸面反馈连起来。
4. 事件/关系质量归并把噪声、重复和候选态控制住。
5. `GET|POST /api/personal-research/loop-overview` 把以上四主题汇总成单一读模型。

## What Is Already Complete

- 个人研究闭环已有只读 API 和领域读模型。
- 首页个人关注池面板已展示研究闭环状态。
- 聚焦单测和 UI 静态契约已经覆盖新增入口。
- 读模型保持 paper-only/no-broker 边界。

## What Still Needs Ongoing Work

- 继续改善首页默认展示和动作建议。
- 在必要时补真实浏览器验收。
- 根据数据量优化聚合缓存和默认 limit。

## Usage

- 根入口：[`README.md`](../README.md)
- 文档索引：[`docs/README.md`](./README.md)
- 逻辑总地图：[`docs/logic-map.md`](./logic-map.md)
- 逻辑链条总览：[`docs/logic-chain-overview.md`](./logic-chain-overview.md)
- 最新分析链路：[`docs/latest-analysis-chain.md`](./latest-analysis-chain.md)
- 交接证据：[`docs/agent-handoffs/2026-06-28-T-494-personal-research-loop-overview.md`](./agent-handoffs/2026-06-28-T-494-personal-research-loop-overview.md)

## Notes

- 这份总览只负责导航和边界说明，不替代 API、UI 或测试实现。
- 所有主线仍遵守本地优先、公开/已提供数据优先、研报只进观点层、模拟反馈 paper-only 的边界。
