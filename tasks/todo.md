# Todo

## 使用规则

- 状态只用 `TODO` `DOING` `DONE` `BLOCKED`
- 只保留当前阶段真正要推进的事项；历史设计项只在“已落地基线”里汇总
- 每项任务必须能映射到 `docs/mvp-backlog.md`
- 新增能力默认遵循：研究先于交易、公开/授权数据先于自动化、人工审批先于执行意图

## 当前判断

代码已经跑通 MVP 主链路：A/H/U 公开披露接入、rights tag、证据切片、规则抽取、benchmark 阈值、Thesis/Signal/Decision/Execution Intent、月报/回放、事故剧本、SQLite、本地/S3 对象存储、内置/OpenSearch 检索、`/ui` 静态页面、健康检查和烟测。

下一阶段重点不是继续堆 demo，而是把文档和 UI 图里的生产化缺口补齐：真实供应商行情、复杂 PDF/OCR 和真实 bbox、大样本双语 benchmark、图谱/向量检索生产 adapter、13F/美股事件流水线深化、UI 生产验收、监控告警和运维 runbook。

## 已落地基线

- `DONE` T-301 后端核心对象、API 路由和治理规则原型
  - 对应：E2-US1, E3-US1, E5-US3, E6-US1, E6-US2, E6-US3, E6-US4, E8-US1, E8-US2, E9-US1
  - 代码：`app/models.py`、`app/api.py`、`app/services.py`、`tests/test_system.py`

- `DONE` T-302 A/H/U 公开披露最小接入与批量采集闭环
  - 对应：E2-US2, E3-US3
  - 代码：SEC EDGAR、HKEXnews、上交所/深交所 recent connector；ingestion job、schedule、retry、去重和错误留痕

- `DONE` T-303 权限、合规和审批闸门
  - 对应：E2-US1, E2-US3, E6-US1, E6-US2, E6-US3, E6-US4
  - 代码：rights tag 校验、Reg FD / non-display gate、prompt 审批、未审批决策拦截 execution intent

- `DONE` T-304 证据链、结构化抽取和 benchmark 原型
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 代码：HTML 清洗、分页文本 locator、PDF Flate/text stream 兜底、术语/数值/期间/规则表格抽取、benchmark 阈值校验

- `DONE` T-305 研究卡、评分、challenger、13F crowding 占位和投委会闭环
  - 对应：E5-US1, E5-US2, E5-US3, E5-US4, E6-US1, E8-US1
  - 代码：template、research card、scorecard、crowding snapshot、challenger、decision pack、签字链

- `DONE` T-306 复盘、月报、事故和最小经营看板
  - 对应：E6-US5, E7-US1, E8-US3, E9-US1, E9-US2
  - 代码：OperatingReport、StrategyReplay、Exception、IncidentPlaybook、DrillSchedule、dashboard、incident calendar

- `DONE` T-307 MVP 存储、检索、部署和 UI 初版
  - 对应：E3-US4, E7-US1, E7-US2, E7-US3, E8-US2
  - 代码：SQLiteStore、PostgreSQL baseline schema、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、`/ui`、`/api/health`、`/api/metrics`、Docker、smoke test

## P0 当前冲刺

- `DOING` T-401 复杂版式 PDF / OCR 与真实证据定位生产化
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：HTML 清洗、`\f` 分页、PDF 文本流/Flate 流兜底、规则表格读取、`page=...;chunk=...` locator、空文本/扫描件解析失败分级、ManualReviewItem 人工复核队列、evidence quality report
  - 待做：OCR fallback、扫描件版面识别、真实 `bbox`/span 坐标、跨页表格合并、定位准确率报告与标注样本对比

- `DOING` T-402 大样本中英双语 benchmark 执行
  - 对应：E4-US1, E4-US2, E4-US3
  - 已有：BenchmarkSample、BenchmarkRun、`/api/benchmarks/{benchmark_id}/samples`、`/api/benchmarks/{benchmark_id}/run`、中英样本登记、真实 extraction 链路评估、术语 F1、数值/期间召回、表格召回、页命中率、证据定位率、按语言拆分指标、低置信度拦截、失败样本和回归样例库、PostgreSQL 视图
  - 待做：300-500 份真实中文公告/年报样本、英文 SEC 披露样本集、人工标注手册、OCR/版面金标 bbox、表格 cell gold label、大样本 baseline 报告
  - 输出：中文公告/年报样本集、英文 SEC 披露样本集、标注手册、规则基线报告、抽取/证据定位/表格指标、回归样例库
  - 验收：核心术语 F1、页命中率、关键数值口径、表格 cell accuracy 达到文档阈值；低置信度样本能拦截

- `DOING` T-403 授权 EOD / 延时行情和供应商权限台账
  - 对应：E2-US1, E2-US3, E2-US4
  - 已有：`authorized_eod_market_data` 默认来源、MarketDataPoint、`/api/market-data`、`/api/market-data/batch`、CorporateAction、`/api/corporate-actions`、批量导入逐条错误留痕、拆股/分红/代码变更公司行动、UI 入库入口、dashboard 摘要、rights tag 校验、实时数据阻断、红区/越权来源阻断测试
  - 待做：真实供应商 connector、字段级供应商白名单、公司行动自动复权计算、真实回测/估值消费链路
  - 说明：MVP 不接未经许可的实时 non-display 数据；行情只服务研究、估值、回测和风控

- `DOING` T-404 生产级状态库、对象存储和检索适配
  - 对应：E3-US4, E6-US4, E8-US2
  - 已有：SQLite 状态库、PostgreSQL baseline schema、`ai_quant.schema_migrations`、PostgreSQLStore runtime、schema 初始化、`AI_QUANT_POSTGRES_DSN` / PostgreSQL DSN 形式 `AI_QUANT_DB` 启动路径、SQLite -> PostgreSQL 显式迁移脚本、`scripts/postgres_schema_migrate.py` baseline apply/dry-run/rollback-record、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、外部检索失败 fallback、runtime fake-driver 持久化测试
  - 待做：S3/OpenSearch/PostgreSQL 真实环境压测、权限策略样例、容量和延迟基线、破坏性 DDL rollback 审批模板

- `DOING` T-405 美股 13F 与披露事件流水线
  - 对应：E5-US4, E7-US2, E7-US3, E8-US1
  - 已有：InstitutionalHolding、`/api/13f/holdings`、`/api/13f/crowding/update`、DisclosureEvent、`/api/disclosure-events/classify`、8-K/6-K/20-F 事件模板、管理层变更/指引/重大协议/资本配置标签、事件严重性标签、事件 evidence 链接、dashboard 事件墙、图谱事件边、PostgreSQL 视图、持久化测试
  - 待做：Form 13F 数据集真实下载/解析、CUSIP/FIGI/issuer 映射、候选池排序和风控展示、更多 8-K item 编码、事件后验表现回写
  - 约束：13F 只用于中低频拥挤度与反身性风控，不直接触发交易

- `DOING` T-406 三市场主体页和知识图谱生产化
  - 对应：E3-US2, E3-US4, E8-US2
  - 已有：EntityMapping、LEI/FIGI/CIK/ISIN/ticker 字段、`/api/entity-mappings/batch`、`/api/entity-mappings/quality-report`、A/H/U 批量映射入库、样本映射准确率报告、`/api/graph/query` 按 issuer/security/evidence/thesis/decision 聚合主体、证券、授权行情、公司行动、文件、证据、观点、信号、决策、execution intent、复盘、回放、例外、research card、13F、crowding、challenger、disclosure event 和派生 `portfolio_positions`，并返回带时间/来源属性的图谱边
  - 待做：ADR/中概队列真实批量映射、图谱 adapter、向量检索 adapter、双时间轴版本字段、主体页 UI 细化、观点到证据回溯率报告
  - 验收：样本公司映射准确率、观点到证据回溯率、节点/边来源和时间戳完整性

## P1 下一批

- `DOING` T-407 CEO Dashboard 与 UI 图对齐验收
  - 对应：E6-US5, E7-US1, E7-US2, E7-US3, E8-US2, E9-US1
  - 已有：左侧信息架构补齐“总览、数据中台、研究工作台、Agent 协作、策略实验室、投委会、风控合规、CEO 看板、知识图谱、系统治理”；顶部 A/H/U 市场、研究、风险、冲突证据和高优先级事件状态；SEC/披露时间线、8-K/6-K/20-F 事件墙、13F crowding 热图、公司行动摘要、风险治理、系统状态；UI 静态验收脚本检查导航、顶部状态、关键面板 ID 和前端脚本语法
  - 待做：异常审批面板的生产态细化；桌面和移动端截图验收、跨浏览器检查、真实数据量分页/过滤、错误恢复、权限态、文本无重叠/无溢出
  - 验收：桌面和移动端截图验收、跨浏览器检查、真实数据量分页/过滤、错误恢复、权限态、文本无重叠/无溢出

- `DOING` T-408 月报/回放生产化和真实绩效归因
  - 对应：E8-US3, E7-US1
  - 已有：月报草稿/发布状态、CEO/CIO/风险合规发布审批、`/api/operating-reports/{report_id}/publish`、`/api/operating-reports/{report_id}/red-flags/{red_flag_id}/resolve`、红灯项逐条 ID/状态/处理结论审计、`portfolio_returns`/`portfolio_values` 与 benchmark 输入、TWR/总收益/最大回撤/换手/信息比率、归因指标透传、版本化 strategy replay 与 `/api/strategy-replays` 筛选、发布审计事件
  - 待做：真实持仓流水和成交流水 adapter、分行业/风格/货币归因、月报 PDF/Board pack 导出、回放批次对比 UI
  - 验收：月报草稿不能绕过审批发布；绩效指标可由真实收益或 NAV 序列复算；回放可按 decision/version/outcome/time 筛选；发布和红灯项处理均有审计留痕

- `DOING` T-409 Black-Litterman、风险预算和组合约束原型
  - 对应：E5-US3, E6-US1, E7-US1, E8-US3
  - 已有：`docs/portfolio-construction-spec.md` 数学规格与参数字典、PortfolioProposal、`/api/portfolio/optimize`、`/api/portfolio/proposals`、观点置信度与 `Omega` 绑定、市场/行业/主题/币种预算、禁投清单、单证券上限、候选权重、风险贡献、换手、walk-forward 与压力测试诊断、图谱关联、PostgreSQL 视图
  - 待做：完整协方差矩阵/收缩估计、约束影子价格、PyPortfolioOpt/CVXPY 对照、真实组合回测报告、投委会 UI 审批入口
  - 验收：候选权重不包含禁投标的；市场/行业预算和单券上限生效；观点置信度影响 `Omega`；输出只作为纸面组合，不直接生成 execution intent
  - 约束：只输出纸面组合或候选权重；进入 execution intent 仍必须经过投委会审批

- `DOING` T-410 英文原文优先的研究问答与摘要审计
  - 对应：E4-US2, E6-US3, E6-US4, E7-US2
  - 已有：ResearchAnswer、`/api/research/answers`、`/api/research/answers/{answer_id}/review`、英文 evidence 校验、英文原文保留、中文摘要链路、summary/prompt/model 版本、来源公开性、人工覆核状态、人工审核通过/驳回、审计日志写入
  - 待做：交互式 filing 原文问答 UI、摘要质量 benchmark、真实模型调用与回退策略、引用格式细化

- `DOING` T-411 生产监控、告警和事故闭环
  - 对应：E6-US4, E9-US1, E9-US2
  - 已有：`/api/health`、`/api/metrics`、AlertRule、SystemAlert、AlertNotification、默认告警规则播种、`/api/alerts/evaluate` 指标评估、开放/恢复告警状态、`/api/alerts/notify` 通知 outbox、`/api/alerts/notifications` 查询、risk dashboard 告警计数、解析失败人工复核告警测试
  - 待做：OpenTelemetry 接入、结构化日志输出、真实外部告警通道发送器、采集/检索失败专用告警、事故自动建单、RCA 与演练结果回写

- `DOING` T-412 生产部署 runbook 与验收清单
  - 对应：E1-US3, E6-US4, E9-US2
  - 已有：`.env.example` 环境变量模板、`docs/production-runbook.md`、`scripts/capacity_baseline.py`、密钥注入建议、PostgreSQL/S3/OpenSearch 运维步骤、上线前检查命令、容量/延迟 baseline 命令、备份/恢复、回滚步骤、月度运维检查表
  - 待做：真实生产环境参数确认、密钥管理系统接入、备份恢复演练记录、真实 PostgreSQL/S3/OpenSearch 容量和延迟基线

## P2 研究预研

- `DONE` T-413 Feast / Kafka 阶段性决策 memo
  - 对应：E3-US4, E6-US4, E8-US3
  - 已有：`docs/feast-kafka-decision-memo.md` 记录暂缓上线理由、Feast/Kafka 触发阈值、outbox/feature registry 迁移草案、PoC 人力周期和退出标准
  - 输出：不上线理由、触发阈值、迁移草案、PoC 成本评估
  - 触发条件：共享特征数、训练/回测/生产口径偏差事故、多事件并发、跨 Agent 解耦和次分钟级联动达到文档阈值后再实施

- `DOING` T-414 授权电话会/转录稿和研报引用策略
  - 对应：E2-US1, E2-US3, E6-US2
  - 已有：`docs/transcript-research-citation-policy.md`、默认来源 `company_public_webcast` / `authorized_transcript_vendor` / `authorized_research_vendor`、rights tag 边界、公开 webcast 入库路径、供应商 transcript/research 默认禁止训练/再分发/派生、越权 transcript 拦截测试
  - 待做：真实供应商合同逐条核验、缓存保留期字段、供应商对象 URI 脱敏策略、红区私会/路演纪要人工参考流程 UI、季度来源复核记录
  - 输出：公开 webcast 与授权 transcript 白名单、缓存权限、引用与训练边界、来源审查字段、红区数据人工参考流程

- `DONE` T-415 美股合规专题补充
  - 对应：E2-US1, E6-US2, E6-US4
  - 已有：`docs/us-compliance-open-questions.md` 覆盖 Reg FD 来源公开性、Nasdaq/NYSE non-display/derived data declaration、投资顾问和外部资管、券商接口和 best execution、衍生品与跨境限制、上线前 live execution 必备清单
  - 输出：Reg FD 细则、Nasdaq/NYSE non-display declaration 核验、投资顾问/券商接口/衍生品/跨境限制的开放问题清单

## 里程碑检查点

- M5 `DONE`：MVP 代码主链路可运行，覆盖 A/H/U 公开披露、证据、评分、审批、复盘、事故、UI、健康检查和烟测
- M6 `DOING`：生产化事实层，完成 T-401 ~ T-406
- M7 `TODO`：经营驾驶舱和投研闭环生产化，完成 T-407 ~ T-412
- M8 `TODO`：复杂基础设施和合规扩展预研，完成 T-413 ~ T-415
