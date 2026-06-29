# 逻辑链条总览

- Status: active
- Owner group: Product and UI, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-29
- Related tasks: T-494, T-553
- Scope: 公司情报、关系链、最新分析、个人研究闭环、数据健康与后续优化入口。
- Non-goals: 真实券商接入、自动下单、非本机生产发布证据。

## Purpose

把当前已经完成的逻辑链条收敛成一个单页总览，说明系统已经覆盖哪些主线、各主线如何串联、当前还剩哪些属于质量和深度增强的工作。

## Current Main Chains

1. 公司情报主线
   - 公司画像
   - 事件时间线
   - 关系图谱
   - 研报观点
   - 观察任务
   - 分析结论
   - 模拟反馈

2. 多维关系主线
   - 产业链位置
   - 同类公司
   - 上下游公司
   - 股东与持有人
   - 同股东关联公司
   - 动态图谱展开

3. 最新分析主线
   - 本地最新分析产物统一回读
   - 公司情报链路补全
   - 研报观点层与事实层隔离
   - 个人关注标的与市场分析汇总

4. 个人研究闭环
   - 数据健康
   - 公司数据库覆盖率
   - 模拟反馈兑现评分
   - 事件/关系质量归并

## What Is Already Complete

- 公司级数据库主轴已经建立，不需要为了关系链目标重建数据库。
- 公司情报页已经能承载画像、事件、关系、研报、观察、结论和反馈。
- 关系链闭环已经收口到产业链、同类、上下游、股东和同股东关联公司。
- 最新分析接口已经能回读公司情报链路和个人关注池状态。
- 个人研究闭环已经把数据健康、兑现评分和图谱降噪汇总成单一读模型。

## What Still Needs Ongoing Work

- 真实外部数据源的广度和质量继续补强。
- 关系与事件的来源质量评分继续细化。
- 更大样本的本地验收继续扩展。
- 个人研究视图的操作体验继续降噪和收敛。

## Usage

- 根入口：[`README.md`](../README.md)
- 文档索引：[`docs/README.md`](./README.md)
- 关系链证明：[`docs/multidimensional-relationship-closure.md`](./multidimensional-relationship-closure.md)
- 个人研究闭环：[`docs/agent-handoffs/2026-06-28-T-494-personal-research-loop-overview.md`](./agent-handoffs/2026-06-28-T-494-personal-research-loop-overview.md)
- 最新分析链路：`artifacts/latest-analysis/latest-analysis.json`
- 路线总览：`tasks/todo.md`

## Notes

- 这份总览是导航文档，不替代具体实现和验收记录。
- 所有主线仍遵守本地优先、公开/已提供数据优先、研报只进观点层、模拟反馈 paper-only 的边界。
