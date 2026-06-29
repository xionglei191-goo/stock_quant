# 逻辑总地图

- Status: active
- Owner group: Product and UI, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-29
- Related tasks: T-494, T-553, T-555
- Scope: 逻辑链条总览、最新分析链路、多维关系链收口、个人研究闭环的总入口。
- Non-goals: 业务逻辑改动、存储 schema 迁移、真实交易、外部生产证据。

## Purpose

把当前已经分开成文的四条主线收束成一张总地图，作为后续继续分析、整理和优化时的第一入口。

## Main Routes

1. 公司情报与逻辑链条总览
   - [`docs/logic-chain-overview.md`](./logic-chain-overview.md)
   - 适合先看全局、再下钻到各条主线。

2. 最新分析链路
   - [`docs/latest-analysis-chain.md`](./latest-analysis-chain.md)
   - 适合先看最新分析产物、证据召回和个人关注池回读。

3. 多维关系链收口
   - [`docs/multidimensional-relationship-closure.md`](./multidimensional-relationship-closure.md)
   - 适合先看产业链、同类、上下游、股东和动态图谱探索。

4. 个人研究闭环
   - [`docs/personal-research-loop-overview.md`](./personal-research-loop-overview.md)
   - 适合先看数据健康、兑现评分和图谱降噪。

## Current Completion

- 公司情报链路已经成文并形成主入口。
- 多维关系链已经完成总收口证明。
- 最新分析链路已经形成独立总览和产物回读入口。
- 个人研究闭环已经形成单独总览。

## Verification

- `make local-ci`
  - Result: passed on 2026-06-29.
  - Covered: Python compile, full unit discovery, UI static contract, security scan, Markdown link validation, and handoff validation.
- `python3 scripts/check_markdown_links.py`
  - Result: passed as part of `make local-ci`, checked 195 Markdown files.

## Navigation

- 根入口：[`README.md`](../README.md)
- 文档索引：[`docs/README.md`](./README.md)
- 项目支持文档：[`docs/project-support.md`](./project-support.md)
- 逻辑链条总览：[`docs/logic-chain-overview.md`](./logic-chain-overview.md)
- 最新分析链路：[`docs/latest-analysis-chain.md`](./latest-analysis-chain.md)
- 多维关系链收口：[`docs/multidimensional-relationship-closure.md`](./multidimensional-relationship-closure.md)
- 个人研究闭环：[`docs/personal-research-loop-overview.md`](./personal-research-loop-overview.md)

## Notes

- 这份总地图只负责导航和分层，不替代任何主线文档。
- 所有主线仍保持本地优先、公开/已提供数据优先、研报只进观点层、模拟反馈 paper-only 的边界。
