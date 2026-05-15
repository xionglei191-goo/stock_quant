# Todo

## 使用规则

- 状态只用 `TODO` `DOING` `DONE` `BLOCKED`
- 本文件维护“达到项目愿景”的剩余路线图；历史实现只在“已落地基线”里汇总
- 每项任务必须映射到 `docs/mvp-backlog.md` 的 E1-E9；无法完全映射的标注为“愿景扩展/生产化增强”
- 新增能力默认遵循：研究先于交易、公开/已提供数据先于自动化、人工审批先于执行意图
- 不采购或依赖商业授权数据；行情、披露、研报线索、转录稿和第三方接口统一优先使用已提供本地数据、官方公开披露、公开网页/API、开源工具可采集的数据
- 所有外部数据进入自动化链路前必须记录来源、URL/API、采集时间、robots/TOS/公开性判断、字段边界、缓存期限和用途边界；边界不清的数据只进入人工参考

## 当前判断

当前能力：代码已经跑通 MVP 主链路，覆盖 A/H/U 公开披露接入、rights tag、证据切片、规则抽取、benchmark 阈值、Thesis/Signal/Decision/Execution Intent、模拟成交、月报/回放、事故剧本、SQLite/PostgreSQL、本地/S3 对象存储、内置/OpenSearch 检索、`/ui` 静态页面、健康检查、烟测、LLM 中转站和 PaddleOCR-VL 文档解析备用接口。

新增资源：本地通达信历史行情已迁入 `data/local/tdx/market_data.duckdb`；本地研报目录 `/home/xionglei/文档/6大投行研报汇总` 可作为后续独立研报资产库；`a-stock-data` 可作为 A 股补充接口候选；LLM gateway 与 PaddleOCR-VL 已具备可配置的外部能力入口。

剩余关键缺口：距离完整愿景仍差真实公开数据管线、公开来源 provenance 台账、研报/转录稿公开性与引用边界、大样本双语 benchmark、真实 bbox 和版面定位、图谱/向量/语义检索生产 adapter、生产 UI、外部监控告警、任务编排、血缘、模型治理、密钥管理和最终上线验收闸门。

近期优先级：先完成 M6 生产化事实层，再完成 M7 经营驾驶舱和投研闭环；M8 聚焦数据/研报/LLM 工作流扩展；M9 补齐生产基础设施和治理；M10 用量化指标判断是否达到项目愿景。

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

- `DONE` T-308 大模型中转站基础能力
  - 对应：E6-US3, E6-US4, E8-US1；愿景扩展/生产化增强
  - 已有：OpenAI `/v1/chat/completions` 和 Anthropic `/v1/messages` 兼容转发、默认模型配置、环境变量注入、调用审计、无密钥入库
  - 后续：并入 T-418 做任务级 prompt、成本、延迟、回退和人工复核闭环

- `DONE` T-309 PaddleOCR-VL 文档解析备用接口
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：`/api/document-parsing/paddleocr`、URL/已入湖文档解析、证据抽取空文本自动兜底、markdown 分页、图片 URL 元数据、环境变量注入、无 token 入库
  - 后续：并入 T-401 做真实 bbox、版面金标、跨页表格和质量报告

- `DONE` T-413 Feast / Kafka 阶段性决策 memo
  - 对应：E3-US4, E6-US4, E8-US3；愿景扩展/生产化增强
  - 已有：`docs/feast-kafka-decision-memo.md` 记录暂缓上线理由、Feast/Kafka 触发阈值、outbox/feature registry 迁移草案、PoC 人力周期和退出标准
  - 触发条件：共享特征数、训练/回测/生产口径偏差事故、多事件并发、跨 Agent 解耦和次分钟级联动达到文档阈值后再实施

- `DONE` T-415 美股合规专题补充
  - 对应：E2-US1, E6-US2, E6-US4
  - 已有：`docs/us-compliance-open-questions.md` 覆盖 Reg FD 来源公开性、Nasdaq/NYSE non-display/derived data declaration、投资顾问和外部资管、券商接口和 best execution、衍生品与跨境限制、上线前 live execution 必备清单

## P0 当前冲刺 / M6 生产化事实层

- `DOING` T-401 复杂版式 PDF / OCR 与真实证据定位生产化
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：HTML 清洗、`\f` 分页、PDF 文本流/Flate 流兜底、规则表格读取、`page=...;chunk=...` locator、空文本/扫描件解析失败分级、ManualReviewItem 人工复核队列、evidence quality report、PaddleOCR-VL 备用解析接口
  - 已有：PaddleOCR-VL 解析结果按文档/URL、content hash/source URI、模型和 optional payload 运行时缓存，并返回 `cache_hit`、`elapsed_ms`、`estimated_cost` 供质量/成本审计
  - 待做：扫描件版面识别、真实 `bbox`/span 坐标、跨页表格合并、表格 cell 定位、图片/表格资产引用、解析失败重试
  - 输出：OCR/版面解析 adapter、bbox/span schema、解析质量报告、人工复核闭环、错误样本库
  - 验收：每个错误样本可回溯到原 PDF 页/框；证据页命中率达到 benchmark 门槛；解析失败进入人工复核并触发告警

- `DOING` T-402 大样本中英双语 benchmark 执行
  - 对应：E4-US1, E4-US2, E4-US3
  - 已有：BenchmarkSample、BenchmarkRun、`/api/benchmarks/{benchmark_id}/samples`、`/api/benchmarks/{benchmark_id}/run`、中英样本登记、真实 extraction 链路评估、术语 F1、数值/期间召回、表格召回、页命中率、证据定位率、按语言拆分指标、低置信度拦截、失败样本和回归样例库、PostgreSQL 视图
  - 待做：300-500 份真实中文公告/年报样本、英文 SEC 披露样本集、人工标注手册、OCR/版面金标 bbox、表格 cell gold label、摘要质量样本、回归 baseline 报告
  - 输出：中文公告/年报样本集、英文 SEC 披露样本集、标注手册、规则基线报告、抽取/证据定位/表格指标、回归样例库
  - 验收：核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；低置信度样本能拦截

- `DOING` T-403 公开 EOD / 延时行情和来源 provenance 台账
  - 对应：E2-US1, E2-US3, E2-US4
  - 已有：`public_eod_market_data` 公开/已提供 EOD 来源、MarketDataPoint、`/api/market-data`、`/api/market-data/batch`、CorporateAction、`/api/corporate-actions`、`/api/market-data/adjusted` 原始/前复权/后复权计算视图、`/api/market-data/returns` 回测/估值/风险收益序列消费入口、`/api/portfolio/returns` 组合级公开复权收益/波动/回撤消费入口、`/api/portfolio/valuation` 真实持仓估值/现金权重/缺失价格 adapter、价格收益与 `cash_dividend_reinvested` 现金分红总回报口径、批量导入逐条错误留痕、拆股/分红/代码变更公司行动、UI 入库入口、dashboard 摘要、rights tag 校验、实时数据阻断、红区/越权来源阻断测试、行情字段白名单入库校验、通达信 DuckDB 只读预览和导入接口、通达信 `vipdoc/*.day` 本地校验/解析兜底、`vipdoc` 显式 URL 下载/sha256 校验/zip 安全解压脚本、SQLite 状态库增量导入脚本、source governance/provenance 台账字段、字段白名单、缓存期限、公开来源覆盖报告、行情数据质量报告
  - 已有：来源 provenance 可记录 `provenance_ref`、`source_tos_uri`、`collection_method`、`robots_policy`、`usage_scope`、`last_reviewed_at`，`/api/governance/sources/{source_id}/reviews` 可记录季度来源复核、复核状态、TOS/robots/用途边界和下次复核日期；历史 `authorized_eod_market_data` 输入兼容映射到 `public_eod_market_data`
  - 已有：`/api/portfolio/valuation` 返回 `risk_decomposition`，按 market/currency/industry/style 输出持仓市值、权重、外币权重、现金权重和集中度；industry/style 可通过 holdings 或 `groups[security_id]` 注入
  - 本地资源：`data/local/tdx/market_data.duckdb`，来自废弃项目 `stock_chs`，约 2703 万行、10849 个 symbol、覆盖 1990-12-19 至 2026-04-08；该目录已被 Git 忽略
  - 待做：通达信 symbol/market/date 字段映射覆盖更多真实 schema
  - 待做：真实成交流水 adapter
  - 验收：生产输入数据 100% 能映射到公开来源 provenance 台账；红黄绿分级覆盖率 >= 95%；边界不清、禁止缓存/禁止自动化或实时 non-display 数据不能进入自动化链路

- `DOING` T-404 生产级状态库、对象存储和检索适配
  - 对应：E3-US4, E6-US4, E8-US2
  - 已有：SQLite 状态库、PostgreSQL baseline schema、`ai_quant.schema_migrations`、PostgreSQLStore runtime、schema 初始化、`AI_QUANT_POSTGRES_DSN` / PostgreSQL DSN 形式 `AI_QUANT_DB` 启动路径、SQLite -> PostgreSQL 显式迁移脚本、`scripts/postgres_schema_migrate.py` baseline apply/dry-run/rollback-record、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、外部检索失败 fallback、runtime fake-driver 持久化测试
  - 已有：`/api/governance/storage-policy-templates` 输出 S3 scoped-prefix IAM、对象生命周期、OpenSearch index role、PostgreSQL app/migration grants 和破坏性 DDL rollback 审批模板，作为真实环境最小权限样例
  - 待做：S3/OpenSearch/PostgreSQL 真实环境压测、容量和延迟基线、备份恢复演练
  - 验收：真实环境 smoke test、容量 baseline、恢复演练记录和最小权限策略样例齐备

- `DOING` T-405 美股 13F 与披露事件流水线
  - 对应：E5-US4, E7-US2, E7-US3, E8-US1
  - 已有：InstitutionalHolding、`/api/13f/holdings`、`/api/13f/crowding/update`、DisclosureEvent、`/api/disclosure-events/classify`、8-K/6-K/20-F 事件模板、管理层变更/指引/重大协议/资本配置标签、事件严重性标签、事件 evidence 链接、dashboard 事件墙、图谱事件边、PostgreSQL 视图、持久化测试
  - 已有：`/api/13f/holdings/changes` 可按 filer/issuer/security 输出 13F 新建、增持、减持、清仓及 shares/value 变化，用于拥挤度时间序列和候选池风控输入
  - 已有：`/api/13f/candidate-pool` 可按 issuer/security 聚合 13F 持仓价值、filer breadth、净增减持、crowding score、FIGI/ISIN/ticker 映射和映射置信度，输出候选池排序与风控标签，且固定 `automation_allowed=false`
  - 已有：`/api/disclosure-events/performance` 可按事件窗口计算披露后 1/5/20 天或自定义窗口的公开行情收益、基准收益和超额收益，并回写 `post_event_performance` 供事件墙、图谱和复盘使用
  - 已有：`/api/disclosure-events/classify` 可识别并回写 8-K 常见 `item_code` / `item_title`（1.01、2.02、2.05、5.02、7.01、8.01），用于事件墙和复盘分组
  - 待做：Form 13F 数据集真实下载/解析、CUSIP/FIGI/issuer 大样本映射
  - 验收：13F 只用于中低频拥挤度与反身性风控，不直接触发交易；事件必须可回链到 filing/evidence

- `DOING` T-406 三市场主体页和知识图谱生产化
  - 对应：E3-US2, E3-US4, E8-US2
  - 已有：EntityMapping、LEI/FIGI/CIK/ISIN/ticker 字段、`/api/entity-mappings/batch`、`/api/entity-mappings/quality-report`、A/H/U 批量映射入库、样本映射准确率报告、基于标识符完整度的实体消歧 confidence、低置信映射清单、`/api/graph/query` 按 issuer/security/evidence/thesis/decision 聚合主体、证券、公开行情、公司行动、文件、证据、观点、信号、决策、execution intent、复盘、回放、例外、research card、13F、crowding、challenger、disclosure event 和派生 `portfolio_positions`，并返回带时间/来源属性的图谱边
  - 已有：`/api/graph/traceability-report` 可检查 thesis、decision、research answer 是否能回溯到 evidence/document，并输出缺失 evidence、document、signal/thesis 断链和英文原文缺失问题
  - 待做：ADR/中概队列真实批量映射、双时间轴版本字段、主体页 UI 细化、图谱 adapter、向量检索 adapter
  - 验收：A/H/U 样本公司映射准确率 >= 98%；观点到证据可回溯率 >= 95%；节点/边具备来源、时间戳和版本

## P1 下一批 / M7 经营驾驶舱和投研闭环

- `DOING` T-407 CEO Dashboard 与 UI 图对齐验收
  - 对应：E6-US5, E7-US1, E7-US2, E7-US3, E8-US2, E9-US1
  - 已有：左侧信息架构补齐“总览、数据中台、研究工作台、Agent 协作、策略实验室、投委会、风控合规、CEO 看板、知识图谱、系统治理”；顶部 A/H/U 市场、研究、风险、冲突证据和高优先级事件状态；SEC/披露时间线、8-K/6-K/20-F 事件墙、13F crowding 热图、公司行动摘要、风险治理、系统状态；UI 静态验收脚本检查导航、顶部状态、关键面板 ID 和前端脚本语法
  - 待做：异常审批面板生产态细化、桌面/移动端截图验收、跨浏览器检查、真实数据量分页/过滤、错误恢复、权限态、文本无重叠/无溢出
  - 验收：桌面和移动端截图验收通过；关键视图在真实数据量下无卡死、无明显溢出、无权限越界

- `DOING` T-408 月报/回放生产化和真实绩效归因
  - 对应：E8-US3, E7-US1
  - 已有：月报草稿/发布状态、CEO/CIO/风险合规发布审批、`/api/operating-reports/{report_id}/publish`、`/api/operating-reports/{report_id}/red-flags/{red_flag_id}/resolve`、红灯项逐条 ID/状态/处理结论审计、红灯项 owner/owner_role/due_date 标准化、`/api/operating-reports/red-flag-reminders` 逾期提醒、`portfolio_returns`/`portfolio_values` 与 benchmark 输入、TWR/总收益/最大回撤/换手/信息比率、归因指标透传、版本化 strategy replay 与 `/api/strategy-replays` 筛选、发布审计事件、`/api/portfolio/transactions` 交易流水 ledger、`/api/portfolio/positions` as-of 持仓派生 adapter
  - 已有：`/api/portfolio/returns` 支持按 market/currency/industry/style 输出组合收益分组归因，industry/style 可通过 `groups[security_id]` 注入，供月报绩效归因复算
  - 已有：`/api/operating-reports/{report_id}/board-pack` 可将已发布月报导出为对象存储中的 markdown 或 PDF Board pack 制品，返回 URI/sha256/size/content_type 并写审计日志
  - 已有：`/api/strategy-replays/compare` 和策略实验室 UI 可按 decision/version/replay 批量对比回放结果、variance、版本分布和下一步动作桶
  - 待做：真实绩效归因批次回填到投后复盘
  - 验收：月报草稿不能绕过审批发布；绩效指标可由真实收益或 NAV 序列复算；每个红灯项有 owner 和截止时间

- `DOING` T-409 Black-Litterman、风险预算和组合约束原型
  - 对应：E5-US3, E6-US1, E7-US1, E8-US3
  - 已有：`docs/portfolio-construction-spec.md` 数学规格与参数字典、PortfolioProposal、`/api/portfolio/optimize`、`/api/portfolio/proposals`、观点置信度与 `Omega` 绑定、市场/行业/主题/币种预算、禁投清单、单证券上限、候选权重、风险贡献、换手、约束影子价格、walk-forward 与压力测试诊断、图谱关联、PostgreSQL 视图
  - 已有：`/api/portfolio/optimize` 支持 `require_benchmark_passed_evidence=true`，要求 view 的 `evidence_ids` 已有通过的结构化抽取/benchmark 结果，否则触发合规闸门，避免未通过证据链进入组合候选权重
  - 已有：`/api/portfolio/optimize` 可基于 `return_history` 输出样本协方差、相关矩阵和对角 shrinkage 协方差诊断
  - 已有：`/api/execution-intents/{intent_id}/simulate` 只对已审批 execution intent 生成模拟成交，写入 `SimulatedExecution` 和 `PortfolioTransaction` ledger，并固定 `live_execution_allowed=false`
  - 待做：PyPortfolioOpt/CVXPY 对照、真实组合回测报告、投委会 UI 审批入口
  - 验收：候选权重不包含禁投标的；市场/行业预算和单券上限生效；观点置信度影响 `Omega`；输出只作为纸面组合，不直接生成 execution intent；交易执行仅允许模拟成交，不接真实券商

- `DOING` T-410 英文原文优先的研究问答与摘要审计
  - 对应：E4-US2, E6-US3, E6-US4, E7-US2
  - 已有：ResearchAnswer、`/api/research/answers`、`/api/research/answers/{answer_id}/review`、英文 evidence 校验、英文原文保留、标准化 citations（evidence/document/page/bbox/source URI/format）、中文摘要链路、summary/prompt/model 版本、来源公开性、人工覆核状态、人工审核通过/驳回、审计日志写入
  - 已有：`/api/research/answers/quality-report` 可输出答案级 evidence/document 回链率、人工复核覆盖率、pending review 队列、截断引用和逐答案问题；默认告警 `alert_research_answer_pending_review` 基于 `research_answer_pending_reviews` 指标触发
  - 已有：`/api/research/answers/summary-benchmark` 可用规则基线评估摘要 evidence/document 回链、英文原文保留、中文摘要长度、版本元数据、人工复核、受限引用边界、过度确定性措辞和英文 anchor 覆盖率
  - 待做：交互式 filing 原文问答 UI、真实模型调用与回退策略
  - 验收：关键研究问答必须保留英文原文 evidence；中文摘要不能替代原文引用；摘要变更必须记录模型和 prompt 版本

- `DOING` T-411 生产监控、告警和事故闭环
  - 对应：E6-US4, E9-US1, E9-US2
  - 已有：`/api/health`、`/api/metrics`、AlertRule、SystemAlert、AlertNotification、默认告警规则播种、`/api/alerts/evaluate` 指标评估、开放/恢复告警状态、`/api/alerts/notify` 通知 outbox、`/api/alerts/notifications` 查询、risk dashboard 告警计数、解析失败人工复核告警测试
  - 已有：`/api/playbooks/seed` 可播种文档解析失败、数据采集失败、检索降级、LLM 网关失败和权限/敏感数据泄漏五类事故剧本及季度演练计划；`/api/alerts/incidents/create` 可将带 `playbook_id` 的开放告警自动生成 IncidentReport 并回写 `incident_report_id`
  - 已有：`/api/drill-schedules/{schedule_id}/result` 可回写事故演练结果、RCA 摘要、行动项和下一次演练时间，并在事故日历中展示
  - 已有：`/api/alerts/notifications/deliver` 可对通知 outbox 执行 dry-run/execute 发送状态机，写回 provider、attempt、delivered_at、response 和失败原因；`provider=webhook|http|https` 时可向 HTTP(S) target 发送 JSON POST，`provider=email|smtp` 可通过 SMTP 发送 EmailMessage，`provider=slack` 可发送 Slack webhook，并限制非 HTTP(S) target、超时、缺失 SMTP 配置和最大尝试次数
  - 已有：`/api/alerts/notify` 支持 `route_failures` / `failure_routes`，可按 playbook/rule/metric 将采集、检索、LLM、OCR 和 workflow 失败分流到专属 channel/target，并把 provider/max attempts/backoff 写入 delivery policy
  - 已有：`/api/observability/logs/export` 可导出 audit、alerts、workflow 和 notifications 的结构化 JSON 日志；`/api/observability/otel/export` 可生成 OTLP logs JSON payload；`/api/observability/otel/submit` 可把 OpenTelemetry 日志提交写入 outbox 并复用通知发送状态机
  - 待做：真实 OpenTelemetry collector 连通性、metrics/traces 端到端采集、日志保留策略和告警联动演练
  - 验收：五类事故剧本均有 owner、SLA、止血动作、回滚动作；季度演练覆盖率 100%

- `DOING` T-412 生产部署 runbook 与验收清单
  - 对应：E1-US3, E6-US4, E9-US2
  - 已有：`.env.example` 环境变量模板、`docs/production-runbook.md`、`scripts/capacity_baseline.py`、密钥注入建议、PostgreSQL/S3/OpenSearch 运维步骤、上线前检查命令、容量/延迟 baseline 命令、备份/恢复、回滚步骤、月度运维检查表
  - 已有：`/api/readiness/capacity-baseline` 可接收容量/延迟基线结果、按阈值自动判定并回填 `capacity_latency_report` readiness 记录和 evidence URI
  - 已有：`/api/readiness/evidence-package` 可生成上线验收证据包 manifest，汇总 checklist、vision gate、owner 修复计划和 PostgreSQL/S3/OpenSearch、OpenTelemetry、Neo4j/Qdrant、OpenLineage/MLflow、KMS/lifecycle executor、生产 UI 浏览器等外部验证矩阵；`/api/readiness/evidence-package/notify` 可把缺失真实证据项写入通知 outbox
  - 已有：`scripts/staging_acceptance.py` 可对 staging HTTP 地址执行真实部署 smoke、模拟成交、检索、图谱、metrics、外部依赖配置和可达性检查、Neo4j/Qdrant/OTel outbox 演练，并可只回填真实执行过的 `real_data_smoke_test` 与 `capacity_latency_report`
  - 已有：`docker-compose.yml` 和 `scripts/local_staging_stack.sh` 可在本机启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector、OpenLineage/MLflow HTTP 占位端点和应用服务，并自动跑 staging 验收；已修复镜像源、host/container 环境变量覆盖、PostgreSQL IMMUTABLE 索引、健康检查等待和 `AI_QUANT_HOST=0.0.0.0` 绑定问题
  - 已有：本机 staging 验收通过，状态库为 PostgreSQLStore，对象存储为 S3/MinIO，检索为 OpenSearch，模拟成交通过，图谱回溯 100%，HTTP 容量基线无 breach；PostgreSQL/S3/OpenSearch/OTel/Neo4j/Qdrant/OpenLineage/MLflow 均可达，Neo4j/Qdrant/OpenLineage/MLflow outbox 演练通过，最近一次复验 `p95=114ms`
  - 待做：真实生产环境参数确认、密钥管理系统接入、备份恢复演练记录、发布 checklist、灰度/回滚演练
  - 验收：上线前检查、备份恢复、容量基线、密钥注入、回滚路径均有记录

## P2 数据与研究资产扩展 / M8

- `DOING` T-414 公开电话会/转录稿和研报线索引用策略
  - 对应：E2-US1, E2-US3, E6-US2
  - 已有：`docs/transcript-research-citation-policy.md`、默认来源 `company_public_webcast` / `manual_reference_transcripts` / `local_research_reports`、rights tag 边界、公开 webcast 入库路径、非公开 transcript/research 默认禁止训练/再分发/派生、越权 transcript 拦截测试、来源引用/缓存期限/公开性/source TOS 治理字段
  - 已有：历史 `authorized_*` 来源输入已兼容映射到 `public_*` / `local_reference_*` / `manual_reference_*` canonical source，避免新数据继续落到商业授权命名
  - 已有：公开网页/API `source_uri` 入湖前会移除 fragment，并脱敏 `token`、`api_key`、`access_token`、`signature`、`secret` 等敏感查询参数
  - 已有：研究问答对非公开或本地参考来源按 `citation_char_limit` 截断英文引用片段，并记录 `citation_truncated`
  - 已有：source governance report 基于 provenance 缺口、risk level 和用途边界计算 `automation_ready`，作为公开来源自动化白名单
  - 已有：红区私会/路演/expert note 只能通过 `/api/research/manual-references` 登记 metadata-only 人工参考记录；接口拒绝正文并自动创建 `manual_reference_boundary_review`，UI 已提供人工参考边界复核入口
  - 已有：`/api/governance/source-review-reminders` 支持从未复核、逾期、即将到期来源提醒，按 `review_owner` / `review_owner_role` 汇总 owner 看板，并透传 TOS/robots/用途边界阻断原因
  - 已有：系统治理 UI 已展示来源复核提醒、owner 看板和来源复核通知 outbox；默认告警 `alert_source_review_overdue` 会基于 `source_review_overdue` 指标触发并可通过 `/api/alerts/notify` 写入通知 outbox
  - 已有：通知 outbox 可通过 `/api/alerts/notifications/deliver` dry-run/execute 落发送状态、重试次数、外部 webhook response 和失败原因，来源复核通知可复用该发送闭环
  - 已有：`/api/governance/source-review-escalations` 可按逾期天数、红/黄区来源、缺失复核、TOS/robots/publicness/usage blocker 生成 SLA 升级项；`/api/governance/source-review-escalations/notify` 可写入通知 outbox 并复用 HTTP(S) webhook、SMTP email 或 Slack webhook sender
  - 验收：研报和转录稿默认只作为公开外部观点层或本地人工参考层；非公开、边界不清或禁止自动化的数据不得进入事实真相层、训练层或可执行建议层

- `DOING` T-416 A 股补充数据 connector 引入
  - 对应：E2-US1, E2-US3, E2-US4, E3-US3
  - 输入：`a-stock-data` Apache-2.0 Skill，覆盖通达信/腾讯/东财/akshare/iwencai/同花顺/百度股市通/巨潮等 A 股数据端点
  - 已有：A 股补充 connector 注册表、source definition、rights tag、限速、字段映射、验证状态、错误留痕和最小测试；默认 restricted rights，仅人工参考/补充研究
  - 已有：`/api/connectors/astock/fetch` 支持本地样本行字段归一化、公开网页/API URI 脱敏、rights/provenance 边界评估、blocked/red-zone 合规拦截和 automation blockers 输出
  - 待做：逐项真实验证接口可用性、稳定性、调用限制和许可边界；接入真实 HTTP fetch adapter 与各端点字段样本库
  - 优先级：东财研报发现、巨潮公告补充、腾讯估值快照、同花顺热点题材、百度概念/资金流、龙虎榜、解禁日历；需要 key 的 iwencai 放到可选配置
  - 验收：外部接口只作为公开补充，不替代本地通达信和官方披露核心数据；红区、边界不清、禁止缓存或禁止自动化的数据只能进入人工参考，不进入自动化链路

- `DOING` T-417 本地研报资产库模块
  - 对应：E2-US1, E2-US3, E3-US3, E5-US1, E6-US2；愿景扩展/生产化增强
  - 输入：本地目录 `/home/xionglei/文档/6大投行研报汇总`，约 22G、11742 个文件，其中 11702 个 PDF，按投行/年份/月组织
  - 已有：本地研报 manifest 扫描、投行/source registry、文件指纹、按需登记为 Document、权限边界、检索入口
  - 已有：`/api/research-reports/{report_id}/extract` 支持本地 `.txt`/显式文本抽取、`citation_char_limit` 引用片段索引、restricted evidence 回链和无文本/扫描件 `research_report_text_extraction_required` 人工复核入口
  - 已有：`/api/research-reports/governance-report` 可按 issuer/security/broker 输出过期研报提示、broker/source 集中度、单一来源占比 breach、Document 回链缺口和本地参考用途边界
  - 已有：`/api/research-reports/extraction-queue` 可 dry-run 或 execute 批量文本抽取/OCR 队列，输出 ready_text、ocr_required、needs_ingest、already_indexed、manual_review 计数，并附 raw text/citation index 缓存保留期策略
  - 已有：`/api/research-reports/mapping-report` 可按 issuer/security/industry/event 输出研报到公司、证券、行业和披露事件的映射，并明确 `automation_allowed=false` 与本地参考边界
  - 已有：`/api/research-reports/viewpoint-report` 可按主题汇总多 broker 观点、情绪分布、单一来源占比，并输出研报偏见告警，仍固定为本地参考层
  - 待做：大目录增量处理
  - 待做：真实大目录增量调度与批量 OCR 成本控制
  - 验收：研报不能作为事实真相源；不得默认用于训练；所有引用必须回链到本地文件或公开来源、页码/片段和使用边界

- `DOING` T-418 大模型 / Agent 工作流生产化
  - 对应：E6-US3, E6-US4, E8-US1, E9-US1；愿景扩展/生产化增强
  - 已有：LLM gateway、OpenAI/Anthropic 兼容转发、默认模型配置、调用审计、密钥环境变量注入、任务级 prompt 模板、baseline prompt 审批记录、模型回退策略、规则/上一稳定版本/人工复核降级链、调用成本/延迟/错误率记录、角色和数据域元数据
  - 已有：`GET /api/prompts/changes` 查询 prompt 变更审批记录，Agent 协作 UI 支持创建/审批 prompt 变更和查看 LLM runs/error/cost/budget；默认告警 `alert_llm_cost_budget` / `alert_llm_error_rate` 基于 `llm_tasks` 指标触发
  - 已有：`/api/llm/tasks/review-queue` 可按任务类型、状态、原因和严重级别输出失败/fallback/高风险/超时/超预算 LLM run 的人工复核队列
  - 已有：默认 LLM task template 覆盖研究摘要、研报摘要、filing 问答、challenger、red team 和事故 RCA，并在 `output_schema.acceptance_thresholds` 记录引用、反证、合规风险、RCA 事实/推断分离等验收阈值
  - 已有：Agent 协作 UI 已接入 `/api/governance/permission-matrix`，可按角色、数据域和动作展示 allowed/denied、红区权限和规则覆盖
  - 已有：`/api/llm/tasks/escalations` 可按成本预算、错误率、fallback 率、人工复核 backlog 和逐 run 原因生成 SLA/预算升级项；`/api/llm/tasks/escalations/notify` 可写入通知 outbox，并可复用 HTTP(S) webhook、SMTP email 或 Slack webhook sender
  - 已有：`/api/llm/budget-approvals` 和 `/api/llm/budget-approvals/{approval_id}/decide` 可基于预算类升级项创建 pending 审批、记录 CEO/CIO/风险/ML 负责人决策，并让 approved 且未过期预算进入 LLM metrics 的有效成本预算计算
  - 已有：`/api/llm/budget-approvals/{approval_id}/sync` 可把 approved 预算审批写入外部财务/云预算系统同步 outbox，记录 target、external_system、metadata、delivery_policy，并复用通知发送状态机推进
  - 验收：生产 prompt 100% 可追溯；未审批 prompt 变更数 = 0；高风险结论 challenger 覆盖率 = 100%

## P2/P3 生产基础设施与治理 / M9

- `DOING` T-419 图谱 / 向量 / 语义检索生产化
  - 对应：E3-US2, E3-US4, E8-US2；愿景扩展/生产化增强
  - 已有：`/api/graph/query` 关系回查、本地轻量语义检索 adapter、证据/研究卡/研报/问答混合 SearchRecord、权限边界继承标记
  - 已有：语义检索支持 `issuer_id` / `resource_types` payload filter、默认 restricted 结果过滤、显式 `include_restricted`、结果级 `source_boundary` / `rights_tag` / `risk_level` 和 `/api/search/semantic/benchmark` recall@k 质量回归
  - 已有：`/api/search/semantic/rerank` 复用语义召回并输出本地可解释重排分、term coverage、资源权重、restricted boundary penalty 和 Qdrant/reranker adapter 触发条件
  - 已有：`/api/search/rebuild` 可从当前事实层重建全文/语义 SearchRecord 索引，返回资源计数、sync 结果、外部全文失败 fallback 和审计记录
  - 已有：`/api/graph/query` 每条 edge 默认带 `source`、`timestamp`、`version`、`confidence`；`/api/graph/edge-quality-report` 可输出边元数据覆盖率和缺失明细
  - 已有：`/api/graph/neo4j/export` 和 `/api/graph/neo4j/sync` 可导出 Neo4j bulk upsert-compatible node/relationship payload，并写入 graph sync outbox 交给外部 adapter
  - 已有：`/api/search/qdrant/export` 和 `/api/search/qdrant/sync` 可导出 Qdrant points upsert-compatible payload，保留 rights/risk 边界，并写入 vector sync outbox
  - 已有：`/api/search/adapter-sync/retry` 可对 Neo4j/Qdrant sync outbox 的 failed 通知做 dry-run/execute 重试演练，复用通知发送状态机并保留审计
  - 待做：真实 Neo4j/Qdrant 连通性验证、批量同步吞吐与失败重试演练
  - 验收：观点、持仓、证据可沿图谱回查；结论到证据回溯率 >= 95%；语义检索结果保留来源和权限边界

- `DOING` T-420 任务编排、血缘和模型治理
  - 对应：E3-US4, E6-US4, E8-US3, E9-US2；愿景扩展/生产化增强
  - 已有：轻量 DAG / workflow definition、任务运行记录、幂等键、任务级审计、数据血缘事件、模型版本记录、模型/prompt/输入输出引用关联
  - 已有：`/api/orchestration/runs/{run_id}/retry` 支持失败/待复核 run 基于冻结输入重放，保留 `retry_of` / `retry_error`，任务状态可定位到具体 failed task；默认告警 `alert_workflow_failed_runs` 基于 `workflow_failed_runs` 指标触发
  - 已有：`/api/orchestration/sla-report` 可基于任务级 `sla_minutes` 输出 failed、needs_review 和 runtime SLA breach；`workflow_sla_breaches` 默认告警可触发调度 SLA 风险
  - 已有：`/api/orchestration/incidents/create` 可将未建单的 workflow SLA/失败 run 自动创建 `IncidentReport`，并用 `ir_workflow_{run_id}` 防重复
  - 已有：`/api/orchestration/schedule-calendar` 可按 workflow `cadence` 和历史 run 预览未来运行窗口、last/next run、owner、任务数和 Airflow/Dagster 触发阈值建议
  - 已有：`/api/orchestration/dependency-graph` 可按 DAG 输出任务节点、依赖边、拓扑顺序、未解析依赖、ready/blocked task、latest run 状态和 lineage 摘要，用于任务依赖可视化和失败排障
  - 已有：`/api/orchestration/openlineage/export` 可把 workflow run、lineage event、模型版本和 prompt 版本导出为 OpenLineage-compatible dry-run payload，保留 run/job/dataset/facet 和外部提交边界
  - 已有：`/api/model-versions/mlflow/export` 可把模型版本导出为 MLflow Model Registry-compatible dry-run payload，包含 registered model、model version、stage/alias、tags、metrics/params 和 lineage 回链
  - 已有：`/api/orchestration/openlineage/submit` 和 `/api/model-versions/mlflow/register` 可将外部 lineage/catalog/registry payload 写入可靠 outbox，并复用通知发送状态机或通用 HTTP(S) webhook sender 记录 pending/sent/failed、provider、attempt、response 和错误
  - 已有：`/api/orchestration/dags/{dag_id}/execute` 内置轻量 DAG 执行器按拓扑顺序运行采集、解析、证据抽取、结构化抽取、索引重建、benchmark sample 登记和 benchmark 执行等白名单任务，支持上游产物占位符、幂等运行、任务状态、output refs 和 task-level lineage 记录
  - 待做：Airflow/Dagster/Cron 生产选择、外部 sensor、分布式 worker、任务级 retry/backfill 和执行队列隔离
  - 待做：OpenLineage/MLflow 真实外部 client sender、真实 registry/catalog 连通性验证和失败重试策略演练
  - 验收：任一解析、特征生产、信号计算和投委会打包均可 replay；失败任务可定位输入、版本、错误和重试记录

- `DOING` T-421 安全、密钥和权限生产化
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - 已有：`scripts/security_check.py` 可检查 `.env` 误提交和常见密钥字面量，测试覆盖误提交场景；source governance report 可检查公开来源 provenance 台账、数据红黄绿分级、字段白名单和缓存期限；audit completeness report 可检查关键审计字段完整性
  - 已有：`/api/governance/data-security-report` 可扫描 document/evidence/research answer 中的邮箱、手机号、身份证样式和 secret/API key 字面量，返回脱敏 snippet 与按类型/来源聚合统计；默认告警 `alert_sensitive_findings` 基于 `sensitive_findings` 指标触发
  - 已有：API 网关会对角色越权访问返回 403 并写入 `permission_denied` 审计事件；默认告警 `alert_permission_denied_events` 基于 `permission_denied_events` 指标触发，risk dashboard 已纳入权限/敏感数据风险
  - 已有：`/api/governance/secret-rotations` 可记录外部密钥管理系统的 rotation metadata、证据 URI 和到期提醒，并拒绝真实密钥值入库；默认告警 `alert_secret_rotation_overdue` 基于逾期记录触发
  - 已有：`/api/governance/permission-matrix` 可从 API 网关授权规则派生角色 + 数据域 + 动作级权限矩阵，输出 allowed/denied roles、public 标记和 red domain 访问汇总
  - 已有：`/api/governance/cache-retention-report` 可扫描 document、本地研报和 PaddleOCR 运行时缓存，输出保留/到期/删除 dry-run、no-cache 违规、外部生命周期执行建议，并通过 `record_run=true` 写入缓存保留执行记录和审计事件；`execute=true` 只形成审批证据，不在应用内物理删除缓存
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execute` 可对已批准 run 执行本进程 PaddleOCR 运行时缓存清理，并把对象存储、搜索索引和研报资产删除输出为外部 handoff 任务
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execution-evidence` 可回填外部对象生命周期、搜索索引清理、KMS/DLP 或运行时缓存清理 executor 的执行证据，把 run 推进到 `executed_outside_app` 并留痕
  - 待做：密钥管理系统接入、公开来源 provenance 台账录入
  - 待做：外部密钥管理系统接入、外部 API key 最小权限、对象存储/搜索索引外部删除 executor 实作
  - 验收：红区数据自动入库训练数 = 0；关键动作审计字段覆盖率 100%；越权访问可拦截并留痕

## 愿景验收闸门 / M10

- `DOING` T-422 真实验收与上线闸门
  - 对应：E1-US3, E2-US1, E3-US3, E4-US3, E6-US4, E7-US1, E8-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 指标：证据覆盖率 >= 95%；关键研究结论原文回链率 >= 95%；未审批 prompt 变更数 = 0；红区数据自动入库训练数 = 0；高风险结论 challenger 覆盖率 = 100%
  - 指标：A/H/U 样本公司映射准确率 >= 98%；核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；季度事故演练覆盖率 100%
  - 已有：愿景上线闸门报告接口，集中计算证据覆盖率、研究结论回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、实体映射和 benchmark 指标，并明确 `ready/not_ready`
  - 已有：`/api/readiness/checklist` 可写入真实数据 smoke、生产 UI 截图、跨浏览器、容量/延迟、备份恢复、权限红队、合规复核和上线 checklist 的 owner、证据 URI、指标、过期时间，并进入审计日志；vision gate 已纳入 checklist 覆盖率和季度事故演练覆盖率
  - 已有：`/api/readiness/remediation-report` 可将未通过 gate 和 pending/expired checklist 汇总为 owner、priority、建议动作和 evidence 要求，形成上线修复计划
  - 已有：`scripts/full_run_acceptance.py` 可在本地以模拟交易模式跑 operational acceptance，覆盖 health、demo flow、模拟成交、组合流水/持仓、检索、语义检索、图谱、告警、容量基线、readiness 记录和 metrics，但不替代真实生产环境上线证据
  - 已有：`scripts/staging_acceptance.py` 可对真实 staging URL 生成 smoke/capacity evidence URI、触发缺失证据通知 outbox，并保持真实券商/自动下单关闭；本机 `scripts/local_staging_stack.sh` 已跑通全量 staging 依赖验收，并覆盖 Neo4j/Qdrant/OpenLineage/MLflow outbox readiness
  - 已有：上线验收证据包接口和通知 outbox 可把 M6-M9 剩余真实环境验证项集中成审计 manifest，并明确当前证据包不是生产执行本身，必须回填真实 artifact URI 后才能通过闸门
  - 待做：真实环境中执行 smoke test、UI 截图验收、跨浏览器验收、容量和延迟报告、备份恢复演练、权限红队测试、合规复核记录并回填证据 URI
  - 验收：全部 M6-M9 任务达到验收口径；所有关键失败路径有人工复核或降级；上线评审记录可审计

## 明确非目标

- `BLOCKED` 自动下单
  - 原因：当前愿景是研究增强和人工审批执行；自动下单需要券商接口、best execution、账户合规、交易风控和更高监管边界

- `BLOCKED` 高频/秒级交易
  - 原因：当前系统定位为中低频、公开/已提供数据驱动，不建设低延迟行情和交易基础设施

- `BLOCKED` 边界不清或禁止自动化的实时/non-display 数据进入自动化链路
  - 原因：实时和 non-display 数据必须有清晰公开来源、用途标签、TOS/robots 判断和人工审批；边界不清时只能人工参考

- `BLOCKED` 非公开研报、转录稿或第三方内容用于训练
  - 原因：研报和转录稿默认是公开外部观点层或本地人工参考层，不是事实真相源，也不默认可训练、再分发或派生

- `BLOCKED` 脱离人工审批的仓位调整
  - 原因：PortfolioProposal 只输出纸面组合或候选权重；进入 execution intent 仍必须经过投委会和合规审批

## 里程碑检查点

- M5 `DONE`：MVP 代码主链路可运行，覆盖 A/H/U 公开披露、证据、评分、审批、复盘、事故、UI、健康检查、烟测、LLM 中转和 OCR 备用解析
- M6 `DOING`：生产化事实层，完成 T-401 ~ T-406
- M7 `TODO`：经营驾驶舱和投研闭环生产化，完成 T-407 ~ T-412
- M8 `TODO`：数据与研究资产扩展，完成 T-414、T-416、T-417、T-418
- M9 `TODO`：生产基础设施与治理，完成 T-419 ~ T-421
- M10 `TODO`：愿景验收和上线闸门，完成 T-422
