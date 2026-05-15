# Todo

## 使用规则

- 状态只用 `TODO` `DOING` `DONE` `BLOCKED`
- 本文件维护“达到项目愿景”的剩余路线图；历史实现只在“已落地基线”里汇总
- 每项任务必须映射到 `docs/mvp-backlog.md` 的 E1-E9；无法完全映射的标注为“愿景扩展/生产化增强”
- 新增能力默认遵循：研究先于交易、公开/授权数据先于自动化、人工审批先于执行意图
- 研报、转录稿、第三方接口和行情数据必须先确认授权边界，再进入自动化链路

## 当前判断

当前能力：代码已经跑通 MVP 主链路，覆盖 A/H/U 公开披露接入、rights tag、证据切片、规则抽取、benchmark 阈值、Thesis/Signal/Decision/Execution Intent、月报/回放、事故剧本、SQLite/PostgreSQL、本地/S3 对象存储、内置/OpenSearch 检索、`/ui` 静态页面、健康检查、烟测、LLM 中转站和 PaddleOCR-VL 文档解析备用接口。

新增资源：本地通达信历史行情已迁入 `data/local/tdx/market_data.duckdb`；本地研报目录 `/home/xionglei/文档/6大投行研报汇总` 可作为后续独立研报资产库；`a-stock-data` 可作为 A 股补充接口候选；LLM gateway 与 PaddleOCR-VL 已具备可配置的外部能力入口。

剩余关键缺口：距离完整愿景仍差真实数据管线、授权台账、研报合规资产库、大样本双语 benchmark、真实 bbox 和版面定位、图谱/向量/语义检索生产 adapter、生产 UI、外部监控告警、任务编排、血缘、模型治理、密钥管理和最终上线验收闸门。

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
  - 待做：扫描件版面识别、真实 `bbox`/span 坐标、跨页表格合并、表格 cell 定位、图片/表格资产引用、解析结果缓存、解析失败重试、OCR 成本/耗时记录
  - 输出：OCR/版面解析 adapter、bbox/span schema、解析质量报告、人工复核闭环、错误样本库
  - 验收：每个错误样本可回溯到原 PDF 页/框；证据页命中率达到 benchmark 门槛；解析失败进入人工复核并触发告警

- `DOING` T-402 大样本中英双语 benchmark 执行
  - 对应：E4-US1, E4-US2, E4-US3
  - 已有：BenchmarkSample、BenchmarkRun、`/api/benchmarks/{benchmark_id}/samples`、`/api/benchmarks/{benchmark_id}/run`、中英样本登记、真实 extraction 链路评估、术语 F1、数值/期间召回、表格召回、页命中率、证据定位率、按语言拆分指标、低置信度拦截、失败样本和回归样例库、PostgreSQL 视图
  - 待做：300-500 份真实中文公告/年报样本、英文 SEC 披露样本集、人工标注手册、OCR/版面金标 bbox、表格 cell gold label、摘要质量样本、回归 baseline 报告
  - 输出：中文公告/年报样本集、英文 SEC 披露样本集、标注手册、规则基线报告、抽取/证据定位/表格指标、回归样例库
  - 验收：核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；低置信度样本能拦截

- `DOING` T-403 授权 EOD / 延时行情和供应商权限台账
  - 对应：E2-US1, E2-US3, E2-US4
  - 已有：`authorized_eod_market_data` 默认来源、MarketDataPoint、`/api/market-data`、`/api/market-data/batch`、CorporateAction、`/api/corporate-actions`、批量导入逐条错误留痕、拆股/分红/代码变更公司行动、UI 入库入口、dashboard 摘要、rights tag 校验、实时数据阻断、红区/越权来源阻断测试、通达信 DuckDB 只读预览和导入接口
  - 本地资源：`data/local/tdx/market_data.duckdb`，来自废弃项目 `stock_chs`，约 2703 万行、10849 个 symbol、覆盖 1990-12-19 至 2026-04-08；该目录已被 Git 忽略
  - 待做：通达信 symbol/market/date 字段映射完善、增量导入脚本、供应商字段白名单、行情数据质量报告
  - 待做：通达信官网 `vipdoc` 下载/校验/解析兜底、公司行动自动复权、前复权/后复权口径声明、真实回测/估值/风险消费链路、授权台账和缓存保留期字段
  - 验收：生产输入数据 100% 能映射到授权台账；红黄绿分级覆盖率 >= 95%；未授权实时 non-display 数据不能进入自动化链路

- `DOING` T-404 生产级状态库、对象存储和检索适配
  - 对应：E3-US4, E6-US4, E8-US2
  - 已有：SQLite 状态库、PostgreSQL baseline schema、`ai_quant.schema_migrations`、PostgreSQLStore runtime、schema 初始化、`AI_QUANT_POSTGRES_DSN` / PostgreSQL DSN 形式 `AI_QUANT_DB` 启动路径、SQLite -> PostgreSQL 显式迁移脚本、`scripts/postgres_schema_migrate.py` baseline apply/dry-run/rollback-record、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、外部检索失败 fallback、runtime fake-driver 持久化测试
  - 待做：S3/OpenSearch/PostgreSQL 真实环境压测、权限策略样例、容量和延迟基线、备份恢复演练、破坏性 DDL rollback 审批模板、对象生命周期策略
  - 验收：真实环境 smoke test、容量 baseline、恢复演练记录和最小权限策略样例齐备

- `DOING` T-405 美股 13F 与披露事件流水线
  - 对应：E5-US4, E7-US2, E7-US3, E8-US1
  - 已有：InstitutionalHolding、`/api/13f/holdings`、`/api/13f/crowding/update`、DisclosureEvent、`/api/disclosure-events/classify`、8-K/6-K/20-F 事件模板、管理层变更/指引/重大协议/资本配置标签、事件严重性标签、事件 evidence 链接、dashboard 事件墙、图谱事件边、PostgreSQL 视图、持久化测试
  - 待做：Form 13F 数据集真实下载/解析、CUSIP/FIGI/issuer 映射、持仓变化和拥挤度时间序列、候选池排序和风控展示、更多 8-K item 编码、事件后验表现回写
  - 验收：13F 只用于中低频拥挤度与反身性风控，不直接触发交易；事件必须可回链到 filing/evidence

- `DOING` T-406 三市场主体页和知识图谱生产化
  - 对应：E3-US2, E3-US4, E8-US2
  - 已有：EntityMapping、LEI/FIGI/CIK/ISIN/ticker 字段、`/api/entity-mappings/batch`、`/api/entity-mappings/quality-report`、A/H/U 批量映射入库、样本映射准确率报告、`/api/graph/query` 按 issuer/security/evidence/thesis/decision 聚合主体、证券、授权行情、公司行动、文件、证据、观点、信号、决策、execution intent、复盘、回放、例外、research card、13F、crowding、challenger、disclosure event 和派生 `portfolio_positions`，并返回带时间/来源属性的图谱边
  - 待做：ADR/中概队列真实批量映射、双时间轴版本字段、主体页 UI 细化、图谱 adapter、向量检索 adapter、观点到证据回溯率报告
  - 验收：A/H/U 样本公司映射准确率 >= 98%；观点到证据可回溯率 >= 95%；节点/边具备来源、时间戳和版本

## P1 下一批 / M7 经营驾驶舱和投研闭环

- `DOING` T-407 CEO Dashboard 与 UI 图对齐验收
  - 对应：E6-US5, E7-US1, E7-US2, E7-US3, E8-US2, E9-US1
  - 已有：左侧信息架构补齐“总览、数据中台、研究工作台、Agent 协作、策略实验室、投委会、风控合规、CEO 看板、知识图谱、系统治理”；顶部 A/H/U 市场、研究、风险、冲突证据和高优先级事件状态；SEC/披露时间线、8-K/6-K/20-F 事件墙、13F crowding 热图、公司行动摘要、风险治理、系统状态；UI 静态验收脚本检查导航、顶部状态、关键面板 ID 和前端脚本语法
  - 待做：异常审批面板生产态细化、桌面/移动端截图验收、跨浏览器检查、真实数据量分页/过滤、错误恢复、权限态、文本无重叠/无溢出
  - 验收：桌面和移动端截图验收通过；关键视图在真实数据量下无卡死、无明显溢出、无权限越界

- `DOING` T-408 月报/回放生产化和真实绩效归因
  - 对应：E8-US3, E7-US1
  - 已有：月报草稿/发布状态、CEO/CIO/风险合规发布审批、`/api/operating-reports/{report_id}/publish`、`/api/operating-reports/{report_id}/red-flags/{red_flag_id}/resolve`、红灯项逐条 ID/状态/处理结论审计、`portfolio_returns`/`portfolio_values` 与 benchmark 输入、TWR/总收益/最大回撤/换手/信息比率、归因指标透传、版本化 strategy replay 与 `/api/strategy-replays` 筛选、发布审计事件
  - 待做：真实持仓流水和成交流水 adapter、分行业/风格/货币归因、月报 PDF/Board pack 导出、回放批次对比 UI、红灯项 owner/due_date 字段和提醒
  - 验收：月报草稿不能绕过审批发布；绩效指标可由真实收益或 NAV 序列复算；每个红灯项有 owner 和截止时间

- `DOING` T-409 Black-Litterman、风险预算和组合约束原型
  - 对应：E5-US3, E6-US1, E7-US1, E8-US3
  - 已有：`docs/portfolio-construction-spec.md` 数学规格与参数字典、PortfolioProposal、`/api/portfolio/optimize`、`/api/portfolio/proposals`、观点置信度与 `Omega` 绑定、市场/行业/主题/币种预算、禁投清单、单证券上限、候选权重、风险贡献、换手、walk-forward 与压力测试诊断、图谱关联、PostgreSQL 视图
  - 待做：完整协方差矩阵/收缩估计、约束影子价格、PyPortfolioOpt/CVXPY 对照、真实组合回测报告、投委会 UI 审批入口、观点来源必须来自 benchmark 通过的证据链
  - 验收：候选权重不包含禁投标的；市场/行业预算和单券上限生效；观点置信度影响 `Omega`；输出只作为纸面组合，不直接生成 execution intent

- `DOING` T-410 英文原文优先的研究问答与摘要审计
  - 对应：E4-US2, E6-US3, E6-US4, E7-US2
  - 已有：ResearchAnswer、`/api/research/answers`、`/api/research/answers/{answer_id}/review`、英文 evidence 校验、英文原文保留、中文摘要链路、summary/prompt/model 版本、来源公开性、人工覆核状态、人工审核通过/驳回、审计日志写入
  - 待做：交互式 filing 原文问答 UI、摘要质量 benchmark、真实模型调用与回退策略、引用格式细化、答案级证据覆盖率、人工复核队列
  - 验收：关键研究问答必须保留英文原文 evidence；中文摘要不能替代原文引用；摘要变更必须记录模型和 prompt 版本

- `DOING` T-411 生产监控、告警和事故闭环
  - 对应：E6-US4, E9-US1, E9-US2
  - 已有：`/api/health`、`/api/metrics`、AlertRule、SystemAlert、AlertNotification、默认告警规则播种、`/api/alerts/evaluate` 指标评估、开放/恢复告警状态、`/api/alerts/notify` 通知 outbox、`/api/alerts/notifications` 查询、risk dashboard 告警计数、解析失败人工复核告警测试
  - 待做：OpenTelemetry 接入、结构化日志输出、真实外部告警通道发送器、采集/检索/LLM/OCR 失败专用告警、事故自动建单、RCA 与演练结果回写
  - 验收：五类事故剧本均有 owner、SLA、止血动作、回滚动作；季度演练覆盖率 100%

- `DOING` T-412 生产部署 runbook 与验收清单
  - 对应：E1-US3, E6-US4, E9-US2
  - 已有：`.env.example` 环境变量模板、`docs/production-runbook.md`、`scripts/capacity_baseline.py`、密钥注入建议、PostgreSQL/S3/OpenSearch 运维步骤、上线前检查命令、容量/延迟 baseline 命令、备份/恢复、回滚步骤、月度运维检查表
  - 待做：真实生产环境参数确认、密钥管理系统接入、备份恢复演练记录、真实 PostgreSQL/S3/OpenSearch 容量和延迟基线、发布 checklist、灰度/回滚演练
  - 验收：上线前检查、备份恢复、容量基线、密钥注入、回滚路径均有记录

## P2 数据与研究资产扩展 / M8

- `DOING` T-414 授权电话会/转录稿和研报引用策略
  - 对应：E2-US1, E2-US3, E6-US2
  - 已有：`docs/transcript-research-citation-policy.md`、默认来源 `company_public_webcast` / `authorized_transcript_vendor` / `authorized_research_vendor`、rights tag 边界、公开 webcast 入库路径、供应商 transcript/research 默认禁止训练/再分发/派生、越权 transcript 拦截测试
  - 待做：供应商白名单、合同条款字段、缓存保留期、引用片段限制、供应商对象 URI 脱敏、红区私会/路演纪要人工参考流程 UI、季度来源复核记录
  - 验收：研报和转录稿默认只作为授权外部观点层；未经授权不得进入事实真相层、训练层或可执行建议层

- `DOING` T-416 A 股补充数据 connector 引入
  - 对应：E2-US1, E2-US3, E2-US4, E3-US3
  - 输入：`a-stock-data` Apache-2.0 Skill，覆盖通达信/腾讯/东财/akshare/iwencai/同花顺/百度股市通/巨潮等 A 股数据端点
  - 已有：A 股补充 connector 注册表、source definition、rights tag、限速、字段映射、验证状态、错误留痕和最小测试；默认 restricted rights，仅人工参考/补充研究
  - 待做：逐项真实验证接口可用性、稳定性、调用限制和许可边界；接入具体 fetch adapter 和字段归一化样本
  - 优先级：东财研报发现、巨潮公告补充、腾讯估值快照、同花顺热点题材、百度概念/资金流、龙虎榜、解禁日历；需要 key 的 iwencai 放到可选配置
  - 验收：外部接口只作为补充，不替代授权/本地核心数据；红区或边界不清的数据只能进入人工参考，不进入自动化链路

- `DOING` T-417 本地研报资产库模块
  - 对应：E2-US1, E2-US3, E3-US3, E5-US1, E6-US2；愿景扩展/生产化增强
  - 输入：本地目录 `/home/xionglei/文档/6大投行研报汇总`，约 22G、11742 个文件，其中 11702 个 PDF，按投行/年份/月组织
  - 已有：本地研报 manifest 扫描、投行/source registry、文件指纹、按需登记为 Document、权限边界、检索入口
  - 待做：OCR/文本抽取队列、引用片段索引、缓存保留期、人工复核入口
  - 待做：研报观点与公司/行业/事件映射、同一主题多来源观点对比、研报偏见告警、单一来源占比控制、过期研报提示
  - 验收：研报不能作为事实真相源；不得默认用于训练；所有引用必须回链到授权来源、页码/片段和使用边界

- `DOING` T-418 大模型 / Agent 工作流生产化
  - 对应：E6-US3, E6-US4, E8-US1, E9-US1；愿景扩展/生产化增强
  - 已有：LLM gateway、OpenAI/Anthropic 兼容转发、默认模型配置、调用审计、密钥环境变量注入、任务级 prompt 模板、baseline prompt 审批记录、模型回退策略、规则/上一稳定版本/人工复核降级链、调用成本/延迟/错误率记录、角色和数据域元数据
  - 待做：摘要质量 benchmark、prompt 变更 UI 审批、任务结果人工复核队列、Agent 角色权限矩阵落到 UI、模型供应商 SLA 和成本预算告警
  - 待做：研究摘要、研报摘要、filing 问答、challenger、red team、事故 RCA 的独立模板和验收阈值
  - 验收：生产 prompt 100% 可追溯；未审批 prompt 变更数 = 0；高风险结论 challenger 覆盖率 = 100%

## P2/P3 生产基础设施与治理 / M9

- `DOING` T-419 图谱 / 向量 / 语义检索生产化
  - 对应：E3-US2, E3-US4, E8-US2；愿景扩展/生产化增强
  - 已有：`/api/graph/query` 关系回查、本地轻量语义检索 adapter、证据/研究卡/研报/问答混合 SearchRecord、权限边界继承标记
  - 待做：Neo4j 或替代 property graph adapter、Qdrant 或替代向量检索 adapter、embedding/reranker 管线、payload filter、权限过滤、检索质量 benchmark
  - 待做：图谱边来源、时间版本、实体消歧置信度、观点到证据回链率、检索失败 fallback 和重建脚本
  - 验收：观点、持仓、证据可沿图谱回查；结论到证据回溯率 >= 95%；语义检索结果保留来源和权限边界

- `DOING` T-420 任务编排、血缘和模型治理
  - 对应：E3-US4, E6-US4, E8-US3, E9-US2；愿景扩展/生产化增强
  - 已有：轻量 DAG / workflow definition、任务运行记录、幂等键、任务级审计、数据血缘事件、模型版本记录、模型/prompt/输入输出引用关联
  - 待做：Airflow/Dagster/Cron 生产选择、采集/解析/抽取/索引/benchmark 任务 DAG 执行器、失败重放、调度日历、回放输入冻结
  - 待做：OpenLineage adapter、MLflow adapter、任务依赖可视化、失败任务自动建单、调度 SLA 告警
  - 验收：任一解析、特征生产、信号计算和投委会打包均可 replay；失败任务可定位输入、版本、错误和重试记录

- `DOING` T-421 安全、密钥和权限生产化
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - 已有：`scripts/security_check.py` 可检查 `.env` 误提交和常见密钥字面量，测试覆盖误提交场景
  - 待做：密钥管理系统接入、密钥轮换记录、角色 + 数据域 + 动作级权限、供应商授权台账、数据红黄绿分级、审计字段完整性检查
  - 待做：PII/合同敏感字段扫描、权限越界告警、外部 API key 最小权限、供应商缓存保留期和删除策略
  - 验收：红区数据自动入库训练数 = 0；关键动作审计字段覆盖率 100%；越权访问可拦截并留痕

## 愿景验收闸门 / M10

- `DOING` T-422 真实验收与上线闸门
  - 对应：E1-US3, E2-US1, E3-US3, E4-US3, E6-US4, E7-US1, E8-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 指标：证据覆盖率 >= 95%；关键研究结论原文回链率 >= 95%；未审批 prompt 变更数 = 0；红区数据自动入库训练数 = 0；高风险结论 challenger 覆盖率 = 100%
  - 指标：A/H/U 样本公司映射准确率 >= 98%；核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；季度事故演练覆盖率 100%
  - 已有：愿景上线闸门报告接口，集中计算证据覆盖率、研究结论回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、实体映射和 benchmark 指标，并明确 `ready/not_ready`
  - 待做：真实数据 smoke test、生产 UI 截图验收、跨浏览器验收、容量和延迟报告、备份恢复演练、权限红队测试、合规复核记录、上线 checklist
  - 验收：全部 M6-M9 任务达到验收口径；所有关键失败路径有人工复核或降级；上线评审记录可审计

## 明确非目标

- `BLOCKED` 自动下单
  - 原因：当前愿景是研究增强和人工审批执行；自动下单需要券商接口、best execution、账户合规、交易风控和更高监管边界

- `BLOCKED` 高频/秒级交易
  - 原因：当前系统定位为中低频、公开/授权数据驱动，不建设低延迟行情和交易基础设施

- `BLOCKED` 未授权实时 non-display 数据进入自动化链路
  - 原因：未授权实时和 non-display 数据不能绕过授权台账、用途标签和合规审批

- `BLOCKED` 未授权研报、转录稿或第三方内容用于训练
  - 原因：研报和转录稿默认是授权外部观点层，不是事实真相源，也不默认可训练、再分发或派生

- `BLOCKED` 脱离人工审批的仓位调整
  - 原因：PortfolioProposal 只输出纸面组合或候选权重；进入 execution intent 仍必须经过投委会和合规审批

## 里程碑检查点

- M5 `DONE`：MVP 代码主链路可运行，覆盖 A/H/U 公开披露、证据、评分、审批、复盘、事故、UI、健康检查、烟测、LLM 中转和 OCR 备用解析
- M6 `DOING`：生产化事实层，完成 T-401 ~ T-406
- M7 `TODO`：经营驾驶舱和投研闭环生产化，完成 T-407 ~ T-412
- M8 `TODO`：数据与研究资产扩展，完成 T-414、T-416、T-417、T-418
- M9 `TODO`：生产基础设施与治理，完成 T-419 ~ T-421
- M10 `TODO`：愿景验收和上线闸门，完成 T-422
