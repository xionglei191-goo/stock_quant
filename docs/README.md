# 项目文档索引

## 主文档

- [../README.md](../README.md): 公司情报与市场综合分析平台入口、运行方式和当前能力说明
- [product-requirements-document.md](./product-requirements-document.md): 公司情报平台 PRD，定义产品定位、目标用户、主流程、研报边界和成功指标
- [system-architecture.md](./system-architecture.md): 公司情报平台目标架构，主线为数据、实体、事件、关系、观点和反馈
- [data-structure-design.md](./data-structure-design.md): 公司画像、画像字段抽取、画像字段级证据断言、字段断言冲突复核、本地公司材料 inbox、画像深字段覆盖审计、事件/关系质量归并、研报观点、观察任务、分析结论、模拟反馈、补库运行历史、公司包导入运行历史、retry/resume、覆盖率趋势和工作台操作数据结构
- [../tasks/todo.md](../tasks/todo.md): 执行待办清单；T-431 至 T-491 记录公司情报平台重定位、公司数据库构建、事实事件层、关系候选抽取与审核、覆盖率审计、批量补库、模拟反馈表现更新、研报兑现复盘、工作台操作面板、细粒度披露事件抽取、空状态缺口诊断、补库运行历史、运行历史 UI、覆盖率趋势报告、补库断点续跑/失败重试、覆盖趋势 UI 接入、画像深字段覆盖审计、官方/IR 画像字段抽取、事件/关系质量归并、深字段/抽取/质量归并 UI 接入、画像字段级证据断言、本地公司材料 inbox、完整度总判断、字段断言冲突复核、字段冲突复核工作台、字段断言批量复核推荐增强、关系/事件复核工作台、闭环刷新、财务指标事实层、本地单标的 bootstrap、本地 watchlist / 公司包导入、公司包导入运行历史、导入历史工作台入口、材料 manifest 模板导出、闭环刷新历史、材料 URL 自动填充、待补材料队列、个人阅读视图、关注池自动闭环、知识图谱、K 线行情和全页面 UI 信息降噪；T-492 至 T-503 记录长效完善、数据健康、个人研究桌面、真实验收、结论兑现、事件/关系可信度、前后端模块化、非本机生产化准备和 `SystemService` 渐进式重构路线

## 研报、观点和数据边界

- [chokepoint-research-module.md](./chokepoint-research-module.md): 瓶颈研究模块方向文档，包含 T-406C 本地质量包和版本化人工 review 基线
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

- [api-contracts.md](./api-contracts.md): 接口契约；包含公司画像、画像字段抽取、字段断言冲突/批量复核、本地公司材料 inbox 脚本、公司包导入运行历史、材料 manifest 模板导出、画像深字段覆盖审计、事件/关系质量归并、研报观点、观察结论和模拟反馈 API
- [multidimensional-relationship-closure.md](./multidimensional-relationship-closure.md): 多维关系链总收口证明，覆盖产业链、同类、上下游、股东、股东关联公司和动态图谱探索能力
- [postgresql-schema.sql](./postgresql-schema.sql): PostgreSQL 状态库基线 schema
- [postgresql-migrations.md](./postgresql-migrations.md): PostgreSQL schema 迁移、dry-run、迁移记录和回滚策略
- [systemservice-modularization-adr.md](./systemservice-modularization-adr.md): `SystemService` 模块化拆分 ADR 与迁移顺序
- [data-health-run-summary-adr.md](./data-health-run-summary-adr.md): 数据健康与调度 run 统一摘要 read model ADR，指导 T-493/T-502 先聚合视图、不迁移 schema
- [security-boundary-modes-adr.md](./security-boundary-modes-adr.md): 本机/非本机访问控制边界与认证模式 ADR
- [non-local-production-readiness-package.md](./non-local-production-readiness-package.md): 非本机组织级发布准备包，包含认证、密钥、备份、来源授权、监控、证据 URI 和发布门禁模板
- [production-evidence-owner-packets.md](./production-evidence-owner-packets.md): 非本机外部证据 owner 分派包，按角色列出 T-402 至 T-421 的真实 artifact URI、readiness endpoint 和发布门禁要求
- [production-evidence-execution-plan.md](./production-evidence-execution-plan.md): 非本机外部证据 PM 执行计划，串联 owner 领取、URI 回填、artifact inventory、strict release gate 和任务状态最终化
- [production-evidence-status-board.md](./production-evidence-status-board.md): 非本机外部证据 PM 状态面板，按 owner 跟踪 URI 填充、占位符和 release gate 就绪状态
- [production-evidence-task-packets/](./production-evidence-task-packets/): 每个外部证据阻塞任务一份 agent/issue 分派包，用于逐项领取、上传真实外部证据并回填 URI
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
