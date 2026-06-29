# 最新分析链路总览

- Status: active
- Owner group: Research and AI Workflows, Data and Evidence
- Last updated: 2026-06-29
- Related tasks: T-482, T-494, T-553
- Scope: latest analysis artifact, company intelligence chain backfill, research evidence recall, and personal intelligence readback.
- Non-goals: 真实券商接入、自动下单、外部生产证据。

## Purpose

把 `artifacts/latest-analysis/latest-analysis.json` 对应的最新分析链路收拢成一页入口，说明它如何把公司情报、研报观点、市场数据、个人关注池和证据回链合成一份可回读的本机分析产物。

## Current Chain

1. 运行 `scripts/latest_analysis_run.py` 生成最新分析产物。
2. 产物回读公司情报链路，补足公司画像、关系、事件和观点层信息。
3. `/api/analysis/latest` 暴露同一份产物，供 UI 与本地脚本读取。
4. `research-evidence-recall-audit.json` 验证研报证据只停留在观点/参考层。
5. 个人关注池与 company intelligence cycle 复用同一条本地分析回读路径。

## What Is Already Complete

- 最新分析产物已覆盖 A 股、美股、产业链、财报、行情和研报观点证据。
- `/api/analysis/latest` 可以回读 `personal_intelligence` 和 `latest-analysis` 相关字段。
- 研报 evidence 已固定在观点/参考层，不进入事实源、训练源或真实交易信号。
- UI 中已有最新分析与研报观点证据展示入口。

## What Still Needs Ongoing Work

- 继续扩展最新分析的本地样本覆盖和证据召回质量。
- 按需细化分析分段、摘要和个人关注池动作建议。
- 把更多链路中的关系/事件/观点回链继续并入同一产物。

## Usage

- 根入口：[`README.md`](../README.md)
- 文档索引：[`docs/README.md`](./README.md)
- 项目支持文档：[`docs/project-support.md`](./project-support.md)
- 产物：[`artifacts/latest-analysis/latest-analysis.json`](../artifacts/latest-analysis/latest-analysis.json)
- 召回审计：[`artifacts/latest-analysis/research-evidence-recall-audit.json`](../artifacts/latest-analysis/research-evidence-recall-audit.json)

## Notes

- 这份总览不替代最新分析产物本身，只提供链路入口和边界说明。
- 所有内容仍遵守本地优先、公开/已提供数据优先、研报只进观点层、模拟反馈 paper-only 的边界。
