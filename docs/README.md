# 项目文档索引

## 主文档

- [../README.md](../README.md): 公司情报与市场综合分析平台入口、运行方式和当前能力说明
- [product-requirements-document.md](./product-requirements-document.md): 公司情报平台 PRD，定义产品定位、目标用户、主流程、研报边界和成功指标
- [system-architecture.md](./system-architecture.md): 公司情报平台目标架构，主线为数据、实体、事件、关系、观点和反馈
- [data-structure-design.md](./data-structure-design.md): 公司画像、事件、关系、研报观点、观察任务、分析结论和模拟反馈数据结构
- [../tasks/todo.md](../tasks/todo.md): 执行待办清单；T-431 至 T-442 记录公司情报平台重定位、公司数据库构建、最小反馈闭环、事实事件层和模拟反馈表现更新

## 研报、观点和数据边界

- [chokepoint-research-module.md](./chokepoint-research-module.md): 瓶颈研究模块方向文档，后续归入观点与观察池能力
- [transcript-research-citation-policy.md](./transcript-research-citation-policy.md): 电话会、转录稿、卖方研报引用和训练边界策略
- [us-compliance-open-questions.md](./us-compliance-open-questions.md): Reg FD、Non-Display、投顾、券商、衍生品和跨境合规开放问题
- [risk-register.md](./risk-register.md): 风险与依赖登记册

## 交付、协作和质量

- [agent-handoffs/README.md](./agent-handoffs/README.md): 多 agent 交接记录目录与使用规则
- [agent-handoffs/TEMPLATE.md](./agent-handoffs/TEMPLATE.md): 标准交接记录模板
- [pr-checklist.md](./pr-checklist.md): PR 与合并检查清单（含多 agent 交接必查项）
- [../AGENTS.md](../AGENTS.md): 多 agent / 开发小组协作、交接记录和文档标准
- [development-ready-checklist.md](./development-ready-checklist.md): 开发就绪清单
- [mvp-backlog.md](./mvp-backlog.md): MVP backlog
- [workstreams-by-role.md](./workstreams-by-role.md): 按角色拆分的执行包

## 架构和运维附录

- [api-contracts.md](./api-contracts.md): 接口契约；包含公司画像、事件、关系、研报观点、观察结论和模拟反馈 API
- [postgresql-schema.sql](./postgresql-schema.sql): PostgreSQL 状态库基线 schema
- [postgresql-migrations.md](./postgresql-migrations.md): PostgreSQL schema 迁移、dry-run、迁移记录和回滚策略
- [systemservice-modularization-adr.md](./systemservice-modularization-adr.md): `SystemService` 模块化拆分 ADR 与迁移顺序
- [security-boundary-modes-adr.md](./security-boundary-modes-adr.md): 本机/非本机访问控制边界与认证模式 ADR
- [artifact-governance.md](./artifact-governance.md): 产物提交规则与本机 CI 质量门
- [production-runbook.md](./production-runbook.md): 备份、恢复、部署和非本机发布运维附录
- [portfolio-construction-spec.md](./portfolio-construction-spec.md): 纸面组合和风险诊断规格；后续归入模拟反馈附录
- [feast-kafka-decision-memo.md](./feast-kafka-decision-memo.md): Feast / Kafka 暂缓上线、触发阈值、迁移草案和 PoC 成本
- [../artifacts/project-completion-audit.json](../artifacts/project-completion-audit.json): 本机目标完成审计输出

## 历史研究底稿

- [deep-research-report.md](./deep-research-report.md): 历史战略研究底稿，保留作背景，不再作为当前产品主叙事
- [deep-research-report-加美股.md](./deep-research-report-%E5%8A%A0%E7%BE%8E%E8%82%A1.md): 历史美股扩展研究
- [deep-research-report -next.md](./deep-research-report%20-next.md): 历史下一步研究清单
- [project-audit.md](./project-audit.md): 资料完整性审查
- [project-support.md](./project-support.md): 项目支持文档
- [development-task-book.md](./development-task-book.md): 开发任务书
- [worktree-change-grouping-2026-05-28.md](./worktree-change-grouping-2026-05-28.md): 2026-05-28 未提交变更分组说明
