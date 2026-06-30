# Todo

## 使用规则

- 状态只用 `TODO` `DOING` `DONE` `BLOCKED`
- 本文件维护“达到项目愿景”的剩余路线图；历史实现只在“已落地基线”里汇总
- 每项任务必须映射到 `docs/mvp-backlog.md` 的 E1-E9；无法完全映射的标注为“愿景扩展/生产化增强”
- 新增能力默认遵循：公司情报数据库先于结论，事实/事件/关系先于观点，观点先于模拟反馈，公开/已提供数据先于自动化
- 当前系统目标是公司情报、市场综合分析、研究记录和模拟反馈验证，不接真实券商、不做自动下单；`execution intent` 仅作为旧纸面/模拟意图兼容对象
- 不采购或依赖商业授权数据；行情、披露、研报线索、转录稿和第三方接口统一优先使用已提供本地数据、官方公开披露、公开网页/API、开源工具可采集的数据
- 所有外部数据进入自动化链路前必须记录来源、URL/API、采集时间、robots/TOS/公开性判断、字段边界、缓存期限和用途边界；边界不清的数据只进入人工参考
- 非本机组织级发布闭环只允许用真实 staging/production artifact URI 回填 manifest；仓库里保留 `artifacts/production-closure-manifest.example.json` 作为运维附录模板，不作为当前产品主路线或可直接发布的证据
- 已回填 URI 的外部证据采集计划必须先经 `scripts/production_evidence_plan_check.py --require-filled-uris` 检查，并提供 artifact inventory 证明每个 evidence URI 的归档对象、sha256、size、环境、producer、owner、retention 和 immutable/object lock，再用 `scripts/production_evidence_plan_to_manifest.py` 或 `scripts/production_release_gate.py` 生成 production closure manifest；草案仍需严格 manifest 和 readiness evidence package 校验后才能进入非本机发布确认

## 当前判断

当前能力：代码已经跑通本机 MVP 主链路，覆盖 A/H/U 公开披露接入、rights tag、证据切片、规则抽取、benchmark 阈值、Thesis/Signal/Decision 兼容对象、纸面执行意图兼容入口、模拟持仓 ledger、月报/回放、事故剧本、SQLite/PostgreSQL、本地/S3 对象存储、内置/OpenSearch 检索、`/ui` 静态页面、健康检查、烟测、LLM 中转站和 PaddleOCR-VL 文档解析备用接口。本轮产品方向调整后，这些能力应重新归类到公司画像、事件时间线、关系图谱、观点库、观察任务、分析结论和模拟反馈闭环。

新增资源：本地通达信历史行情已迁入项目内 `data/local/tdx/vipdoc`，并已全量写入 PostgreSQL `market_data`，导入摘要见 `artifacts/tdx-vipdoc-postgres-import-full.json`；本地研报库 `/home/xionglei/文档/6大投行研报汇总` 已完成全量入库和解析，源目录 11702 份可处理文件全部登记为 research report asset、全部关联 research document、全部进入 `text_indexed`，无 `indexed` / `ingested` / `needs_text_review` 残留，研报 citation evidence 共 88515 条，审计见 `artifacts/research-report-completion-audit.json`；`a-stock-data` 相关 A 股补充 connector 已完成来源治理补齐，`artifacts/source-governance-fill.json` 显示来源治理覆盖率 `1.0`；LLM gateway 与 PaddleOCR-VL 已完成本机密钥注入和真实冒烟，验收记录见 `artifacts/local-ai-capability-acceptance.json`。

剩余关键缺口：后续主路线不再是强化组织级发布或实时交易，而是建立公司级数据库和分析反馈闭环。本机 production-like 栈仍可作为个人/单机长期使用口径运行，并由 `scripts/local_production_audit.py`、`scripts/local_ai_capability_acceptance.py` 和 `scripts/project_completion_audit.py` 单独审计。非本机组织级真实生产发布、外部密钥管理、生产级 artifact URI、灰度/回滚窗口和发布确认全部下沉为运维/非本机发布附录，不阻塞公司情报平台产品路线。长期能力仍需继续补强真实 bbox 和版面定位、大样本真实标注集、非本机 Neo4j/Qdrant/OpenLineage/MLflow/OTel 证据、真实外部通道和生产运维记录。

近期优先级：先完成产品重定位、架构重写和数据结构统一，再拆实现任务。本机长期使用仍需保持 Compose 栈、备份恢复、本机证据包、LLM/OCR 冒烟、最新分析产物和 `local_production_audit` 可复验；日常启动建议使用 `scripts/local_production_stack.sh`。研报解析底座和研报接入业务分析/UI 看板已经全量收口，`artifacts/latest-analysis/latest-analysis.json` 已包含 A 股、美股、产业链、财报、行情和研报观点 evidence，`artifacts/latest-analysis/research-evidence-recall-audit.json` 已确认研报只进入观点/参考层，不进入事实源、训练源或真实交易信号。M6-M9 代码层已收口，剩余 `BLOCKED` 项保留为“非本机/组织级生产或大样本质量增强”证据缺口，不阻塞公司情报平台重定位。

## 项目经理整理 / 公司情报平台重定位路线

项目经理口径：以下任务来自 2026-06-24 产品方向重定位，目标是把项目从组织/执行导向的旧叙事，调整为公司情报、市场综合分析、研报观点追踪、观察任务、分析结论和模拟反馈闭环。T-431 先完成文档重定位；T-432 至 T-436 已补齐最小可验收代码、API、UI 和测试闭环。

- `DONE` T-431 产品重定位与文档统一
  - 对应：愿景扩展/生产化增强
  - 目标：统一 README、PRD、系统架构、数据结构和文档索引，把主叙事改为“公司情报与市场综合分析平台”。
  - 已完成：`README.md` 前屏重写，明确公司级数据库、事件关系、研报观点、观察任务、分析结论和模拟反馈主线。
  - 已完成：`docs/product-requirements-document.md` 重写为个人研究者/分析用户视角，成功指标改为公司画像覆盖率、事件回链率、研报观点结构化率、分析师预测复盘覆盖率、分析结论复盘完成率和模拟反馈可回链率。
  - 已完成：`docs/system-architecture.md` 重写为 Data Lake、Entity、Fact & Event、Relationship、View & Feedback 分层；旧决策治理、投委会 Pack 和执行意图降级为兼容模块。
  - 已完成：`docs/data-structure-design.md` 重写核心对象，明确 `CompanyProfile`、`CompanyEvent`、`CompanyRelationship`、`ResearchReport`、`ReportViewpoint`、`ReportForecast`、`AnalystProfile`、`AnalystReliabilityScore`、`ObservationItem`、`AnalysisConclusion`、`SimulationFeedback`。
  - 验收：研报被定义为关注度信号、观点样本库和分析师可靠性复盘来源；模拟交易只用于反馈分析有效性，不进入真实交易。

- `DONE` T-432 公司级数据模型与画像 schema
  - 对应：E3-US1, E3-US3, E5-US1；愿景扩展/生产化增强
  - 目标：把现有 `Issuer` / `Security` / 行情 / 财务 / 研报覆盖能力编排成 `CompanyProfile`，输出公司画像 API/schema 和数据完整度口径。
  - 已有基础：`Issuer` / `Security`、entity mapping、行情、公司行动、文档、证据、披露事件、关系图谱、研报、研究答案、thesis/signal/challenger/research card、研究任务和模拟 ledger 等对象可复用为公司画像输入。
  - **已完成（SPCX 验收切片）**：新增 `GET|POST /api/company-intelligence/{symbol}` 只读聚合接口，可按股票代码汇总公司画像、行情/事件、关系图谱、研报资产、研究答案、观点/信号/反方/研究卡、研究任务和模拟反馈；`SPCX` 空档案时返回 `next_actions`，运行单标的研究后可展示完整聚合视图。
  - **已完成（本轮收口）**：新增一等 `CompanyProfile` 持久化集合、`GET|POST /api/company-profiles` 和 `GET /api/company-profiles/schema`，画像可由既有 issuer/security/行情/事件/关系/研报覆盖计算生成。
  - **已完成（本轮收口）**：`/api/company-intelligence/{symbol}` 返回 `company_profile.profile/profiles`、画像覆盖率、缺失字段、事件回链率和关系回链率。
  - 验收：任一重点公司可生成基础画像、行情财务摘要、研报覆盖摘要、事件摘要、关系摘要和缺失数据清单。

- `DONE` T-433 事件时间线与关系图谱数据结构
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 目标：把公告、财报、新闻、政策、订单、诉讼、价格、供需和管理层变化统一为 `CompanyEvent`，把客户、供应商、竞争、股权、机构覆盖、分析师覆盖和上下游统一为 `CompanyRelationship`。
  - **已完成（本轮收口）**：新增 `CompanyEvent`、`CompanyRelationship` 持久化集合和 `GET|POST /api/company-events`、`GET|POST /api/company-relationships`。
  - **已完成（本轮收口）**：事件支持来源、文档、证据、影响标签、置信度、事实状态和复核状态；关系支持主体/客体类型、关系类型、有效期、证据、置信度和状态。
  - **已完成（本轮收口）**：`/api/graph/query` 返回 `company_events`、`company_relationships` 并补 `HAS_COMPANY_EVENT`、`HAS_COMPANY_RELATIONSHIP`、`RELATIONSHIP_EVIDENCE` 等回链边。
  - 验收：公司页可按时间线查看事件，图谱可按关系类型回查来源与证据。

- `DONE` T-434 研报观点结构化与分析师可靠性模型
  - 对应：E3-US3, E5-US1, E6-US3；愿景扩展/生产化增强
  - 目标：把研报从文档资产推进到结构化观点库和分析师可靠性复盘。
  - **已完成（本轮收口）**：新增结构化 `ResearchReport`、`ReportViewpoint`、`ReportForecast`、`AnalystProfile`、`AnalystReliabilityScore` 持久化集合。
  - **已完成（本轮收口）**：新增 `/api/research-reports/structured`、`/api/research-report-viewpoints`、`/api/research-report-forecasts`、`/api/analyst-profiles`、`/api/analyst-reliability-scores`。
  - **已完成（本轮收口）**：研报字段覆盖机构、分析师、发布时间、标的、报告类型、评级、目标价、当前价、核心假设、盈利预测/目标价预测、估值方法、催化剂、风险和后续兑现状态；研报仍固定为观点层，不作为事实真相源。
  - **已完成（本轮增强）**：新增 `POST /api/research-reports/structure`，可把本地研报资产、已登记 Document 文本和 citation evidence 自动结构化为 `ResearchReport`、`ReportViewpoint`、`ReportForecast` 和 `AnalystProfile`；默认幂等跳过已结构化研报，支持 `dry_run` 和 `force`。
  - **已完成（本轮 UI 增强）**：公司情报页新增“研报结构化”受控入口，支持按当前主体/证券或关键词小批量 `dry_run` 预览，再显式执行结构化；执行后自动刷新公司情报总览。
  - **已完成（本轮收口）**：T-406 瓶颈研究和真实样本质量包已在文档口径上归入“观点与观察池”方向，继续保留事实分层、来源台账和人工复核质量基线。
  - 验收：研报观点结构化率、预测兑现覆盖率、目标价命中率、盈利预测误差和分析师综合可靠性可计算。

- `DONE` T-435 观察池、分析结论和模拟反馈闭环
  - 对应：E5-US1, E6-US5, E8-US1；愿景扩展/生产化增强
  - 目标：建立 `ObservationItem`、`AnalysisConclusion` 和 `SimulationFeedback` 闭环，用模拟反馈验证分析结论有效性。
  - 已有基础：旧 execution intent、simulated execution 和 portfolio transaction 可作为 `SimulationFeedback` 的兼容输入，但需要重新建模为分析有效性反馈，而不是执行系统。
  - **已完成（SPCX 验收切片）**：公司情报聚合接口把旧 execution intent、simulated execution 和 portfolio transaction 按股票代码汇总为 `simulation_feedback` 区块，并固定返回 `paper_only=true` / `live_execution_allowed=false`。
  - **已完成（本轮收口）**：新增 `ObservationItem`、`AnalysisConclusion`、`SimulationFeedback` 持久化集合和 `/api/observation-items`、`/api/analysis-conclusions`、`/api/simulation-feedback`。
  - **已完成（本轮收口）**：观察任务状态机支持 `open/in_progress/waiting/closed/cancelled`；分析结论记录事实、推断、预测、主观判断、证据、反证、有效期、复盘计划和关联观察任务。
  - **已完成（本轮收口）**：`SimulationFeedback` 在模型层强制 `paper_only=true`、`live_execution_allowed=false`、`broker_connected=false`，API 会拒绝真实交易相关请求。
  - 后续增强：更细的事件/行情自动验证逻辑和复盘评分算法可以继续迭代，但不阻塞当前闭环成立。
  - 验收：每条模拟反馈能回链到分析结论、观察任务、事件、证据和行情表现，且固定 `live_execution_allowed=false`。

- `DONE` T-436 UI 信息架构从投委会/CEO 改为公司情报工作台
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 目标：把 `/ui` 导航和页面组织从旧运营/审批视角改为公司情报工作台。
  - 已有基础：当前 `/ui` 已有总览、主体页、研报证据、图谱、模拟反馈和旧运营/投委会入口，可复用为公司情报工作台的初始组件。
  - **已完成（SPCX 验收切片）**：研究工作台新增“公司情报总览”，默认输入 `SPCX`，可载入画像、事实/事件、研究结果、模拟反馈、下一步缺口和完整聚合 JSON；单标的研究完成后会自动刷新该总览。
  - **已完成（SPCX 验收切片）**：`scripts/ui_interaction_acceptance.py` 增加 `company_intelligence_spcx_research_flow` 浏览器验收，真实点击单标的研究后断言 SPCX 公司情报页出现画像、研究结果、模拟反馈和聚合 JSON。
  - **已完成（本轮收口）**：主导航从“研究工作台/策略实验室/投委会”调整为“公司情报/复盘反馈/兼容审批”，旧投委会、签批和执行意图保留在兼容入口。
  - **已完成（本轮收口）**：公司情报面板优先展示 `CompanyProfile`、`CompanyEvent`、`CompanyRelationship`、结构化研报、研报观点、观察任务、分析结论和 `SimulationFeedback`。
  - **已完成（本轮收口）**：`scripts/ui_static_check.py` 静态导航验收更新为公司情报主路径。
  - **已完成（运行态修复）**：`/ui` 浏览器标题、首屏 H1、首屏流程、动态结果标签、UI/smoke/staging 验收文本和 `/api/health` service 元数据已统一为“公司情报与市场综合分析平台”；本机 Compose 应用容器已重建并验证 `http://127.0.0.1:8000/ui` 返回新主叙事。
  - **已完成（本轮 UI 增强）**：公司情报工作台新增研报结构化预览/执行面板，静态检查覆盖新增控件，浏览器验收覆盖 `dry_run` 预览链路。
  - **已完成（空白页修复）**：知识图谱页输入股票代码时会先通过 `/api/company-intelligence/{symbol}` 解析到主体 ID；`SPCX` 可自动载入 `issuer_spcx`，未知标的如 `SPAX` 会明确提示本地未建档，不再静默显示空表。
  - 验收：首屏体现公司情报平台；主导航不再以组织签批或执行意图为中心。

- `DONE` T-437 完整公司数据库底座构建入口
  - 对应：E3-US1, E3-US3, E5-US1；愿景扩展/生产化增强
  - 背景：PostgreSQL 已有 `issuers`、`securities`、`research_reports` 等原始层记录，但 `company_profiles`、公司事件、关系、结构化研报观点、观察结论和模拟反馈等公司情报核心对象仍缺少系统性构建入口；页面空白的根因是公司数据库没有从原始索引物化出来。
  - **已完成（本轮）**：新增 `POST /api/company-database/build`，以公司数据库为主轴，从现有主体/证券/行情/研报资产生成或预览 `CompanyProfile`，并用 ticker/公司名启发式把未绑定研报挂到目标公司和证券；默认 dry-run，只有显式 `execute=true` 才落库。
  - **已完成（本轮）**：新增 `scripts/build_company_database_minimum.py`，可对 `AAPL,NVDA,600519,300750,600887` 等样本公司执行最小公司数据库 dry-run/落库，并输出 `artifacts/company-database-build.json`。
  - **已完成（本轮）**：构建入口支持可选小批量研报结构化，把已匹配研报推进为 `ResearchReport`、`ReportViewpoint`、`ReportForecast` 和 `AnalystProfile`；研报仍固定为观点层，不作为事实源或真实交易信号。
  - 验收：单测覆盖 dry-run 不落库、execute 后持久化公司画像、绑定未归属研报、生成结构化研报观点；后续应继续补 `CompanyEvent` / `CompanyRelationship` 的自动抽取和公司数据库覆盖率审计。

- `DONE` T-438 公司事件时间线最小构建入口
  - 对应：E3-US1, E5-US1；愿景扩展/生产化增强
  - 背景：T-437 已能从原始主体、证券、行情和研报索引物化公司画像与研报绑定，但公司事件时间线仍为空，导致公司数据库不完整。
  - **已完成（本轮）**：新增 `POST /api/company-database/events/build`，默认 dry-run，可从已入库公开行情和已绑定研报覆盖记录生成最小 `CompanyEvent` 时间线。
  - **已完成（本轮）**：行情事件标记为 `fact_status=verified`，来源为公开/已提供行情；研报覆盖事件标记为 `fact_status=opinion_signal`、`review_status=needs_review`，只表示关注度/观点信号，不把研报升级为事实源。
  - **已完成（本轮）**：`scripts/build_company_database_minimum.py` 支持 `--build-events`，可在构建公司画像和研报绑定后继续生成最小事件时间线。
  - 验收：单测覆盖事件 builder dry-run 不落库、execute 后生成市场行情事件与研报覆盖事件，并在 `/api/company-intelligence/{symbol}` 中体现 `company_events` 和事件时间线可用性。
  - 后续增强：公告、财报、新闻、政策、订单、诉讼、管理层变化、供需和价格冲击等事件抽取仍需单独推进，并要求证据回链和人工复核。

- `DONE` T-439 公司关系层最小构建入口
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-437/T-438 已补公司画像、研报绑定和事件时间线，但 `CompanyRelationship` 仍为空，导致关系图谱缺少一等公司关系对象。
  - **已完成（本轮）**：新增 `POST /api/company-database/relationships/build`，默认 dry-run，可从已入库证券和已绑定研报资产生成最小 `CompanyRelationship` 关系层。
  - **已完成（本轮）**：上市证券关系使用 `relationship_type=listed_security`、`review_status=auto_generated`；研报机构覆盖关系使用 `relationship_type=institution_coverage`、`review_status=needs_review`，只表示机构覆盖/关注度关系，不代表客户、供应商、竞争或投资建议事实。
  - **已完成（本轮）**：`scripts/build_company_database_minimum.py` 支持 `--build-relationships`，可在构建画像、事件后继续生成最小关系层。
  - 验收：单测覆盖关系 builder dry-run 不落库、execute 后生成上市证券关系与机构覆盖关系，并在 `/api/company-intelligence/{symbol}` 中体现 `company_relationships`。
  - 后续增强：客户、供应商、竞争、股权、上下游、人物和产品关系需要从公告、财报、官网、监管披露或人工复核证据进入，不能从研报观点直接推断为事实。

- `DONE` T-440 观察任务、分析结论和模拟反馈最小构建入口
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-437/T-439 已让公司页具备画像、事件、关系和研报观点入口，但观察任务、分析结论和 `SimulationFeedback` 仍主要依赖手工写入，导致“分析结果记录和反馈验证”没有形成一键可见闭环。
  - **已完成（本轮）**：新增 `POST /api/company-database/workflow/build`，默认 dry-run，可从已有事件、关系、结构化研报观点和行情快照生成 `ObservationItem`、`AnalysisConclusion` 和 `SimulationFeedback`。
  - **已完成（本轮）**：生成的分析结论使用 `conclusion_type=company_intelligence_baseline`，只作为公司情报基线和复盘计划；事实、推断、观点和证据缺口分开记录，不输出买卖建议。
  - **已完成（本轮）**：生成的模拟反馈固定 `feedback_type=watch_only`、`paper_only=true`、`live_execution_allowed=false`、`broker_connected=false`，只用于验证分析结论有效性，不连接真实券商。
  - **已完成（本轮）**：workflow builder 默认刷新已有基线记录；后续新增结构化研报观点或事件关系时，可更新观察任务、结论和反馈的回链，不需要删除重建。
  - **已完成（本轮）**：`scripts/build_company_database_minimum.py` 支持 `--build-workflow`，可在画像、事件、关系和研报结构化后继续生成观察/结论/反馈闭环。
  - 验收：单测覆盖 workflow builder dry-run 不落库、execute 后生成观察任务、分析结论和 paper-only 模拟反馈，并在 `/api/company-intelligence/{symbol}` 中体现 `observation_items`、`analysis_conclusions` 和 `simulation_feedback_records`。
  - 后续增强：模拟反馈的收益/回撤/相对基准表现、观点兑现状态和分析师可靠性评分仍需后续根据行情、财报和人工复盘数据持续更新。

- `DONE` T-441 公开披露事件进入公司事件时间线
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-438 已生成行情事件和研报覆盖事件，但公司数据库事实层仍偏薄；公开披露/filing 已有 `DisclosureEvent` 对象，却没有自动物化为一等 `CompanyEvent`。
  - **已完成（本轮）**：`POST /api/company-database/events/build` 新增 `include_disclosures`，默认从已有 `DisclosureEvent` 生成 `event_type=official_disclosure` 的公司事件。
  - **已完成（本轮）**：官方披露事件保留 `document_id`、`evidence_ids`、`source_id`、`item_code`、`severity` 和 `disclosure_event_id` 回链，`fact_status=verified`、`review_status=auto_generated`。
  - **已完成（本轮）**：研报覆盖事件仍保持 `fact_status=opinion_signal`，不会因为加入官方披露事件而把研报观点混入事实层。
  - 验收：单测覆盖事件 builder dry-run 不落库、execute 后同时生成行情事件、研报覆盖事件和官方披露事件，并在 `/api/company-intelligence/{symbol}` 中体现公司事件时间线可用性。
  - 后续增强：公告/财报正文的细粒度事件抽取、管理层变化、诉讼、订单、价格、供需和政策事件仍需继续扩展，并加入人工复核和来源质量评分。

- `DONE` T-442 模拟反馈表现更新入口
  - 对应：E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-440 已能生成 paper-only `SimulationFeedback`，但反馈仍停留在静态 pending 状态，不能根据后续行情验证分析结论有效性。
  - **已完成（本轮）**：新增 `POST /api/simulation-feedback/performance/update`，默认 dry-run，可按反馈 ID、股票代码或主体筛选，用本地最新 `MarketDataPoint` 更新纸面表现。
  - **已完成（本轮）**：更新字段包括 entry price、最新价、最新行情日期、纸面收益率、持有天数、数据来源和待人工复盘状态；所有结果固定 `paper_only=true`、`live_execution_allowed=false`。
  - **已完成（本轮）**：无最新行情或无有效 entry price 的反馈会被跳过并返回原因；entry price 为空但有最新行情时只初始化 paper baseline，不创建真实交易。
  - 验收：单测覆盖 dry-run 不落库、execute 后根据最新行情更新 `SimulationFeedback.performance` 和 `validation`，并保持真实交易禁用边界。
  - 后续增强：补相对基准收益、最大回撤、事件窗口收益、观点兑现状态和人工复盘评分，再与分析师可靠性模型联动。

- `DONE` T-443 公开披露关系候选抽取入口
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-439 已补上市证券关系和研报机构覆盖关系，但客户、供应商、合作方、子公司等公司关系仍未从公开披露/证据文本进入关系层。
  - **已完成（本轮）**：`POST /api/company-database/relationships/build` 新增 `include_disclosure_candidates`，默认从已有 `DisclosureEvent`、`Evidence` 和非研报 `Document` 文本中抽取关系候选。
  - **已完成（本轮）**：当前支持 `customer_candidate`、`supplier_candidate`、`partner_candidate`、`subsidiary_candidate`；候选关系保留 `disclosure_event_id`、`document_ids`、`evidence_ids`、`source_ids` 和抽取规则。
  - **已完成（本轮）**：所有公开披露抽取关系默认 `relationship_status=unknown`、`review_status=needs_review`、`metadata.candidate_status=candidate`、`confidence=0.55`，不会直接升级为高置信事实。
  - **已完成（本轮）**：关系 builder 仍保持研报机构覆盖只是观点/关注度关系，不从研报观点推断客户、供应商或竞争关系。
  - 验收：单测覆盖 dry-run 不落库、execute 后同时生成上市证券关系、研报机构覆盖关系、客户候选关系和供应商候选关系，并在 `/api/company-intelligence/{symbol}` 中体现关系图谱可用性。
  - 后续增强：补更强的中文/英文实体抽取、同义归并、主体映射、人工审核工作流和来源质量评分，再将复核通过的候选关系提升为事实关系。

- `DONE` T-444 关系候选审核与提升入口
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-443 已能抽取公开披露关系候选，但候选关系需要人工审核后才能进入可信图谱。
  - **已完成（本轮）**：新增 `POST /api/company-relationships/{relationship_id}/review`，支持 `approve`、`reject`、`merge`。
  - **已完成（本轮）**：`approve` 会将关系提升为 `review_status=approved`、`relationship_status=active` 并提高置信度；`reject` 会置为 `inactive`；`merge` 会把 evidence/document/source 回链合并到目标关系。
  - 验收：单测覆盖 approve、reject、merge 三条路径，审核历史写入 metadata，合并关系保留证据回链。
  - 后续增强：增加 UI 审核队列、批量审核、审核角色权限和候选实体归并。

- `DONE` T-445 公司数据库覆盖率审计
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：样本公司已具备最小闭环，但系统仍需要按公司输出缺失层，指导批量补齐。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/coverage/audit`，按公司统计画像、证券、行情、财务、文档、披露事件、公司事件、关系、研报、结构化观点、观察任务、分析结论和模拟反馈覆盖情况。
  - **已完成（本轮）**：返回 `coverage_score`、`coverage_level`、`missing_sections`、各 section 可用性和全局 `missing_counts`。
  - 验收：单测覆盖按股票代码审计，能识别已有画像/行情/证券和缺失财务等 section。
  - 后续增强：输出版本化 coverage artifact、按市场/行业聚合和覆盖率趋势。

- `DONE` T-446 批量公司数据库构建任务
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-437 到 T-440 已有单批构建能力，但还需要服务端批量编排来支持观察池或市场范围补齐。
  - **已完成（本轮）**：新增 `POST /api/company-database/batch/build`，按 `batch_size` 对目标公司分批调用画像/研报绑定、事件、关系、workflow 构建。
  - **已完成（本轮）**：支持 `dry_run`、`execute`、`structure_reports`、`build_events`、`build_relationships`、`build_workflow`，并返回批次明细、totals 和 `coverage_after`。
  - 验收：单测覆盖 dry-run 批量构建，能汇总 batch、profiles planned 和 coverage_after。
  - 后续增强：增加可恢复 run_id、断点续跑、失败重试和 artifact 输出。

- `DONE` T-447 研报兑现与分析师可靠性更新
  - 对应：E5-US1, E6-US3, E7-US3；愿景扩展/生产化增强
  - 背景：研报已结构化为观点和预测，但目标价/预测兑现状态还需要跟随本地行情更新，并反哺分析师可靠性。
  - **已完成（本轮）**：新增 `POST /api/research-reports/realization/update`，用本地最新行情更新 `ReportForecast` 和 `ReportViewpoint` 的目标价兑现状态。
  - **已完成（本轮）**：更新字段包括 `actual_value`、`actual_source_id`、`error_abs`、`error_pct`、`realization_status`、`checked_at` 和观点 `realization_checked_at`。
  - **已完成（本轮）**：执行模式下可自动调用 `compute_analyst_reliability_score` 重算相关分析师可靠性评分。
  - 验收：单测覆盖 dry-run 不落库、execute 后目标价 forecast/viewpoint 标记为 realized，并生成分析师可靠性评分。
  - 后续增强：加入目标价期限、评级方向准确率、盈利预测 actuals、相对基准收益和人工复盘解释。

- `DONE` T-448 公司情报工作台操作面板
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-444 至 T-447 已补齐关系审核、覆盖率审计、批量补库和研报兑现后端入口，但 `/ui` 公司情报页仍缺少可见操作入口。
  - **已完成（本轮）**：公司情报工作台新增“公司数据库补齐”面板，可执行覆盖率审计、批量补齐 dry-run/execute 和研报兑现 dry-run/execute。
  - **已完成（本轮）**：新增“关系候选审核”面板，展示当前公司待复核关系候选，并支持 `approve`、`reject` 和带目标 ID 的 `merge`。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 覆盖新增控件和函数；`scripts/ui_interaction_acceptance.py` 增加覆盖率审计、批量补齐预览和研报兑现预览浏览器验收路径。
  - 验收：静态 UI 检查和浏览器验收脚本覆盖新增可见入口；执行路径仍只调用本地公司数据库与观点复盘 API，不连接真实券商。
  - 后续增强：补批量审核队列、候选关系筛选、补库 run_id 历史和覆盖率趋势图。

- `DONE` T-449 公司事件细粒度抽取与事件分类补强
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - 背景：T-438/T-441 已能把行情、研报覆盖和官方披露物化为公司事件，但事件层仍偏粗，无法支撑用户想要的“公司全天候情报数据库”里的财报、管理层、诉讼监管、订单合同、产能供需和政策影响等结构化事件。
  - **已完成（本轮）**：`POST /api/company-database/events/build` 新增默认开启的 `include_structured_disclosures`，从官方披露摘要、披露 evidence 文本和非研报 `Document.body` 抽取细粒度 `CompanyEvent`。
  - **已完成（本轮）**：当前支持 `earnings_result`、`management_change`、`litigation_regulatory`、`major_order_contract`、`capacity_supply_demand`、`policy_impact` 六类事件。
  - **已完成（本轮）**：结构化披露事件保留 `document_ids`、`evidence_ids`、`source_ids`、`disclosure_event_id`、`matched_terms` 和 `classification_rule`；事实来源为官方披露，`fact_status=verified`，但分类结果默认 `review_status=needs_review`。
  - **已完成（本轮）**：研报仍只生成 `research_coverage` 关注度事件，`fact_status=opinion_signal`，不会被结构化为公司事实事件。
  - 验收：单测覆盖 dry-run 不落库、execute 后从同一官方披露生成官方披露粗事件和六类细分事件，且所有细分事件保留证据回链和分类待复核边界。
  - 后续增强：补新闻/政策网页采集、实体归并、事件去重、来源质量评分和 UI 事件筛选。

- `DONE` T-450 公司情报空状态缺口诊断与一键下一步
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：后端公司情报聚合在未知标的会返回 `not_found` 和 `next_actions`，但 UI 仍容易表现为空表和 raw JSON，用户难以判断是系统没运行、标的未建档还是数据层缺失。
  - **已完成（本轮）**：公司情报总览新增“缺口诊断”系统条、缺失层表和下一步动作表，直接展示 `data_quality.missing_sections` 和 `next_actions`。
  - **已完成（本轮）**：下一步动作支持从诊断表触发单标的研究建档、研报结构化预览或覆盖审计；未知 ticker 会显示“未建档”和“建立最小公司情报档案”入口。
  - **已完成（本轮）**：补库/审计 payload 不再优先使用全局图谱里的旧 `activeEntityIssuerId`，只使用当前公司情报结果匹配到的 issuer；未知 ticker 会按 ticker 发送，避免误操作上一家公司。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 和 `scripts/ui_interaction_acceptance.py` 覆盖新增 DOM、JS 函数和未知 ticker 空状态验收。
  - 验收：UI 静态检查通过；浏览器验收覆盖未知 ticker 时出现缺口诊断、公司画像缺失和可点击下一步。
  - 后续增强：把覆盖审计、补库预览和研报兑现结果从 raw JSON 进一步拆成差异摘要和运行历史。

- `DONE` T-451 公司数据库批量补齐运行历史
  - 对应：E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-446 已能批量编排公司画像、事件、关系和 workflow 构建，但运行只存在于一次 API 响应里，缺少可审计、可复盘、可继续增强为断点续跑的运行记录。
  - **已完成（本轮）**：新增一等 `CompanyDatabaseBuildRun` 数据结构，并接入 SQLite/PostgreSQL 通用 JSON records 存储。
  - **已完成（本轮）**：`POST /api/company-database/batch/build` 返回并可持久化 `run_id`、目标公司、目标代码、批次、选项、totals、覆盖率前后和批次明细；execute 默认记录，dry-run 需显式 `record_run=true`。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/batch/runs`，可按 issuer/status 查询补库运行历史。
  - **已完成（本轮）**：批量构建现在透传 `include_structured_disclosures`、`include_disclosure_candidates` 等事件/关系构建开关，保证 T-449/T-443 能从批量补库入口生效。
  - 验收：单测覆盖 execute 自动记录 run、按 issuer 查询运行历史、dry-run 默认不记录但 `record_run=true` 可显式记录。
  - 后续增强：补断点续跑、失败重试、UI 运行历史表、覆盖率趋势和 artifact 输出。

- `DONE` T-452 公司数据库补库运行历史 UI 与覆盖差异摘要
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-451 已经持久化 `CompanyDatabaseBuildRun`，但公司情报工作台仍看不到最近补库、覆盖率前后变化和批次汇总，用户无法判断系统是否真正运转过。
  - **已完成（本轮）**：公司情报工作台的“公司数据库补齐”面板新增“查看运行历史”、最近运行状态、运行数、覆盖变化和运行历史表。
  - **已完成（本轮）**：运行历史读取 `GET|POST /api/company-database/batch/runs`，按当前公司主体过滤；无主体时只展示本地只读历史，不触发补库或外部下载。
  - **已完成（本轮）**：运行行展示 `run_id`、状态、完成时间、目标公司数、批次数、批次规模、覆盖率前后差异、画像/事件/关系/反馈汇总和本地操作边界。
  - **已完成（本轮）**：执行补齐后自动刷新运行历史；载入公司情报时也会同步刷新该公司对应的 run 记录。
  - **已完成（本轮）**：研报结构化 payload 不再读取旧图谱全局主体 ID，避免当前公司代码与旧 `activeEntityIssuerId` 不一致时误结构化到上一家公司。
  - 验收：UI 静态检查覆盖新增 DOM/JS；浏览器交互验收覆盖“查看运行历史”点击链路和本地 run history 结果区。
  - 后续增强：T-453 覆盖率趋势报告与本地 artifact 输出；T-454 断点续跑、失败重试和大批量运行摘要瘦身。

- `DONE` T-453 公司数据库覆盖率趋势报告与本地 artifact 输出
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-451/T-452 已能记录和展示单次补库运行，但还缺少跨 run 的趋势报告，无法判断补库是否持续改善公司画像、事件、关系、研报观点、观察结论和模拟反馈覆盖。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/coverage/trends`，从 `CompanyDatabaseBuildRun.coverage_before` / `coverage_after` 计算时间序列趋势。
  - **已完成（本轮）**：趋势行输出 run 状态、目标公司、批次、覆盖率前后、覆盖变化、缺失项前后、分项缺失变化、改善/恶化 section 和构建 totals。
  - **已完成（本轮）**：summary 输出首尾覆盖率、累计覆盖率变化、最新缺失数、累计缺失变化、改善/恶化/不变运行数。
  - **已完成（本轮）**：支持 `issuer_id`、`status`、`limit` 过滤；支持 `write_artifact=true` 写本地 JSON，artifact 固定 `local-only` 且 `acceptable_for_non_local_release_gate=false`。
  - 验收：单测覆盖趋势汇总、issuer/status 过滤和本地 artifact 输出；API 文档明确只读本地 run 快照，不触发补库、外部抓取、真实券商或生产发布证据。
  - 后续增强：T-454 断点续跑、失败重试和大批量运行摘要瘦身；T-455 可把趋势图接入 UI。

- `DONE` T-454 公司数据库补库断点续跑、失败重试和运行历史瘦身
  - 对应：E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-451 至 T-453 已有 run history、UI 摘要和覆盖率趋势，但失败时原接口不会保留 partial/failed run，历史列表也默认返回完整 batch 明细，不利于大批量公司数据库长期补库。
  - **已完成（本轮）**：`CompanyDatabaseBuildRun` 新增 `retry_of`、`resume_of`、`resume_mode`、`attempt`、`idempotency_key`、`completed_issuer_ids`、`skipped_issuer_ids`，并支持 `partial` 状态。
  - **已完成（本轮）**：`POST /api/company-database/batch/build` 支持 `resume_run_id`，可按 `remaining` 或 `all` 从本地 run history 重放；失败/partial run 默认只处理未完成公司。
  - **已完成（本轮）**：新增 `POST /api/company-database/batch/runs/{run_id}/retry`，基于已持久化 run 生成新的本地补库 run，保留源 run、attempt、跳过公司和本地 no-live-trading 边界。
  - **已完成（本轮）**：批量补库失败时会持久化 `failed` 或 `partial` run，记录已完成公司、已完成 batch、错误信息和覆盖率快照，避免失败后完全无迹可循。
  - **已完成（本轮）**：`GET|POST /api/company-database/batch/runs` 支持 `run_id` 过滤，并默认省略完整 `batches`；显式 `include_batches=true` 才返回批次明细。
  - 验收：单测覆盖运行历史瘦身/完整批次切换、retry route 重放源 run、`resume_run_id` 只续跑剩余公司、补库中途失败记录 `partial` run。
  - 后续增强：T-455 覆盖率趋势 UI 接入；T-456 公司基础画像深字段覆盖审计与来源计划；T-457 官方披露/公司 IR 画像字段抽取。

- `DONE` T-455 公司数据库覆盖率趋势 UI 接入
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-453 已有覆盖率趋势 API，T-454 已有 retry/partial run 语义，但公司情报工作台仍需要用户查看 raw JSON 才知道长期补库是否改善覆盖、缺失项是否减少、运行是否 partial/retry。
  - **已完成（本轮）**：公司数据库补齐面板新增“查看覆盖趋势”、趋势状态、累计覆盖变化、缺失变化和趋势表。
  - **已完成（本轮）**：趋势表读取 `POST /api/company-database/coverage/trends`，按当前公司主体过滤；只读本地 run history，不触发补库、外部下载或真实交易。
  - **已完成（本轮）**：运行历史表展示 retry 源、续跑模式、完成/跳过公司数量，`partial` 状态可见。
  - **已完成（本轮）**：内部 usage boundary 在 UI 中显示为“本地补库历史/本地覆盖趋势”，不再把内部常量直接暴露给用户。
  - **已完成（本轮）**：执行补齐和载入公司情报后会刷新运行历史与覆盖趋势；新增 UI 静态契约和交互验收路径。
  - 验收：UI 静态检查覆盖新增 DOM/JS；浏览器交互验收覆盖执行补齐后加载趋势表、累计变化和本地边界标签。
  - 后续增强：T-459 深字段 coverage UI。

- `DONE` T-456 公司基础画像深字段覆盖审计与来源计划
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-445 的覆盖率审计只能判断画像、证券、行情、文档、事件、关系等 section 是否存在，仍无法回答公司数据库到底缺 `business_summary`、官网/IR 来源、财务指标、管理层/产品/地址等细字段，也无法指导下一步官方披露/公司 IR 抽取优先级。
  - **已完成（本轮）**：新增 `GET|POST /api/company-profiles/coverage/audit`，输出 `company-profile-deep-field-coverage-v1` 深字段审计。
  - **已完成（本轮）**：新增兼容别名 `GET|POST /api/company-database/profile-field-coverage/audit`，便于公司数据库补齐任务按深字段调用。
  - **已完成（本轮）**：字段分组覆盖 identity、listing、business、market_snapshot、financial_snapshot、source_evidence、coverage_opinion、workflow_feedback 和 quality；返回每个字段的 present、source_records、evidence_ids、missing_reason 和 source_policy。
  - **已完成（本轮）**：`source_plan` 明确官方披露、公司 IR、公司官网、交易所/监管目录、公开行情、已治理本地记录和人工参考的适用边界；研报只满足观点/覆盖槽位，不满足事实字段。
  - **已完成（本轮）**：支持 `issuer_ids`、`symbols`、`symbol`、`ticker`、`q`、`required_fields`、`include_optional`、`require_evidence` 和 `include_research_opinion_slots`。
  - 验收：单测覆盖稀疏画像缺字段、官方/监管文档和 evidence 可计入事实字段、研报只能计入 `research_report_count` 且不能满足 business/source evidence 事实字段。
  - 后续增强：T-459 深字段 coverage UI。

- `DONE` T-457 官方披露/公司 IR 画像字段抽取
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-456 已能审计公司画像深字段缺口和来源计划，但仍无法从已入库官方披露、公司 IR、公司官网或交易所/监管文件中把 `business_summary`、`products`、财务快照等事实字段回填到公司数据库。
  - **已完成（本轮）**：新增 `POST /api/company-profiles/fields/extract`，默认 dry-run，从已入库合规 `Document` / `Evidence` 生成画像字段候选。
  - **已完成（本轮）**：新增兼容入口 `POST /api/company-database/profile-fields/extract`，用于公司数据库补库流程在覆盖审计前先执行画像字段抽取。
  - **已完成（本轮）**：支持 `issuer_ids`、`symbols`、`document_ids`、`fields`、`document_limit`、`evidence_limit`、`min_confidence`、`require_evidence`、`refresh_existing` 和 `execute`。
  - **已完成（本轮）**：显式 `execute=true` 时写入 `Issuer.company_details`、`Issuer.fundamentals`、`Issuer.data_sources` 并物化 `CompanyProfile.source_ids/evidence_ids`；默认不覆盖已有字段，`refresh_existing=true` 才刷新。
  - **已完成（本轮）**：研报、券商研究、本地人工参考、新闻和边界不清来源不会写入事实字段，只保留观点/关注度边界。
  - 验收：单测覆盖官方/IR evidence dry-run 不落库、execute 回填画像和覆盖审计可见；研报不可回填事实字段；默认不覆盖已有字段但 `refresh_existing=true` 可刷新。
  - 后续增强：T-459 深字段 coverage UI。

- `DONE` T-458 事件/关系去重、实体归并和来源质量评分
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-456/T-457 已能审计并回填公司画像深字段，但事件时间线和公司关系层仍可能因披露、证据、研报覆盖和批量补库重复运行产生重复事件、重复关系或低质量候选；实体别名也需要统一归并候选和保守写入边界。
  - **已完成（本轮）**：新增 `POST /api/company-database/quality/reconcile`，默认 dry-run，输出事件重复组、关系重复组、实体归并候选和 source quality。
  - **已完成（本轮）**：事件去重 key 基于主体、证券、事件类型、日期和 disclosure/document/evidence/摘要；execute 时保留 canonical，重复事件标记 `review_status=merged`，并合并 source/document/evidence 回链。
  - **已完成（本轮）**：关系去重 key 基于主体、关系类型、方向和归一化对象实体名；execute 时重复关系标记 `review_status=merged`、`relationship_status=inactive`，canonical 记录保留 `entity_canonical_key`、`entity_aliases` 和 merge 回链。
  - **已完成（本轮）**：`metadata.source_quality` 输出本地来源/证据/复核质量评分；官方/监管/公司 IR 和 evidence/document 回链提高分数，研报/manual/local/news/opinion signal 降低分数，且不构成投资评级。
  - 验收：单测覆盖重复事件识别和合并、关系实体别名归并、官方来源质量高于研报观点来源；默认 dry-run 不落库，`execute=true` 才写入 merge/source quality。
  - 后续增强：T-459 深字段 coverage UI。

- `DONE` T-459 深字段覆盖、画像抽取和质量归并 UI 接入
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-456/T-457/T-458 已经有深字段覆盖审计、官方/IR 画像字段抽取和事件/关系质量归并后端入口，但公司情报工作台仍需要可见操作入口，否则用户只能看 raw JSON 或调用 API。
  - **已完成（本轮）**：公司数据库补齐面板新增画像字段列表、要求证据、刷新已有字段、深字段审计、字段抽取预览/执行、质量归并预览/执行等可见控件。
  - **已完成（本轮）**：深字段审计读取 `POST /api/company-database/profile-field-coverage/audit`，展示字段覆盖率、缺失字段、字段分组、来源策略、证据回链和缺失原因。
  - **已完成（本轮）**：字段抽取读取 `POST /api/company-database/profile-fields/extract`，默认 dry-run，显式执行才写入本地 `Issuer`/`CompanyProfile`，执行后自动刷新深字段审计和公司情报总览。
  - **已完成（本轮）**：质量归并读取 `POST /api/company-database/quality/reconcile`，默认 dry-run，展示事件重复、关系重复、实体归并候选和来源质量评分；执行路径仍为本地非破坏式 merge 标记。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 和 `scripts/ui_interaction_acceptance.py` 覆盖新增 DOM、JS 函数和三个 dry-run 浏览器路径。
  - 验收：UI 静态检查通过；浏览器交互验收覆盖深字段审计、字段抽取预览和质量归并预览；执行路径不下载外部数据、不触发真实交易。

- `DONE` T-460 公司画像基础事实字段扩展与字段级证据断言
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-457/T-459 已能抽取和展示部分画像字段，但公司数据库仍缺官网/IR、总部地址、员工规模、管理层、关键客户/供应商等基础事实字段；同时 `CompanyProfile.source_ids/evidence_ids` 只能表达整张画像来源，不能证明“某个字段由哪个证据支撑”。
  - **已完成（本轮）**：新增一等 `CompanyProfileFieldAssertion` 持久对象和 `company_profile_field_assertions` 集合，记录字段名、值、来源、文档、证据、置信度、事实状态、复核状态和抽取方法。
  - **已完成（本轮）**：`POST /api/company-database/profile-fields/extract` 扩展默认字段到 `website_url`、`ir_url`、`headquarters`、`employee_count`、`management`、`key_customers`、`key_suppliers`，执行写入 `Issuer.company_details` 并为每个已应用字段生成字段级断言。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/profile-field-assertions` 和 `GET|POST /api/company-profiles/field-assertions`，可按公司、字段和状态查询字段级 provenance。
  - **已完成（本轮）**：深字段覆盖审计优先使用字段自己的 assertion/evidence；`require_evidence=true` 时不能用无关官方 evidence 证明其他字段。
  - **已完成（本轮）**：研报、券商研究、新闻、人工参考仍不会写入事实字段，也不会生成 `CompanyProfileFieldAssertion`。
  - 验收：单测覆盖官方/IR 证据抽取扩展字段并生成断言、字段级 evidence gate、研报不生成事实断言；API 文档和数据结构文档已更新。
  - 后续增强：T-461 本地公司 IR/官网公开材料 inbox 与 backfill；T-462 公司情报页完整度总判断和执行路径验收。

- `DONE` T-461 本地公司 IR/官网公开材料 inbox 与 backfill
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-460 已有字段级证据断言，但用户仍需要把本地已下载或手工保存的公司官网、IR、官方披露材料批量送入公司数据库，而不是手工逐个调用 source/document/evidence/profile-fields API。
  - **已完成（本轮）**：新增 `scripts/company_material_inbox_ingest.py`，扫描 `*.manifest.json` sidecar，默认 dry-run 输出计划；显式 `--execute` 才注册 source、登记 document、抽取 evidence 并触发 `POST /api/company-database/profile-fields/extract`。
  - **已完成（本轮）**：manifest 必须显式提供 `issuer_id`、`source_id`、`source_type`、`document_type`、`source_uri` 和 `file_path`，脚本不靠文件名猜公司或来源，支持 `company_ir`、`company_official`、`official_public`、`issuer_disclosure`、`exchange_disclosure`、`regulatory` 等事实源。
  - **已完成（本轮）**：研报、券商研究、新闻、人工参考和 `training_allowed=true` 记录会被标记 invalid，不会注册 source/document，也不会写入 `CompanyProfileFieldAssertion`。
  - **已完成（本轮）**：修正官网字段抽取兜底规则，避免把 Investor Relations 链接误写为 `website_url`。
  - 验收：单测覆盖 dry-run 不落库、execute 完成 source/document/evidence/profile-field assertion 回填、研报/manual 边界拒绝；脚本输出本地 artifact，固定 `local-only` 使用边界。
  - 后续增强：T-462 公司情报页完整度总判断和执行路径验收；T-463 多字段冲突/替代断言处理。

- `DONE` T-462 公司情报完整度总判断
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-456 至 T-461 已补齐深字段覆盖、字段级证据、材料 inbox 和公司数据库补库入口，但用户仍需要一个清晰的“当前公司数据库是否完整可用”的总判断，而不是只看多个空表或 raw JSON。
  - **已完成（本轮）**：`GET|POST /api/company-intelligence/{symbol}` 新增 `completeness_verdict`，按公司画像、行情快照、事件时间线、关系图谱、研究观点和模拟反馈六层输出完整度状态、分数、缺失层、阻塞缺口、提醒缺口和下一步动作。
  - **已完成（本轮）**：完整度判断接入公司数据库覆盖率和画像深字段 coverage，返回 `database_coverage_score`、`profile_field_coverage_score`、必需事实字段和缺失事实字段，避免只用研报或观点把事实层误判为完整。
  - **已完成（本轮）**：研报边界在 verdict 中显式声明为 `opinion_and_attention_slots_only_not_fact_source`，`research_reports_can_complete_fact_fields=false`；模拟反馈仍固定为 paper-only 验证层。
  - **已完成（本轮 UI）**：公司情报工作台新增“完整度判断”状态条和逐层缺口表，展示完整度分数、事实层/分析层/反馈层 readiness、缺失事实字段、下一步动作和研报边界。
  - **已完成（本轮验收）**：`scripts/ui_static_check.py` 覆盖新增 DOM 和渲染函数；`scripts/ui_interaction_acceptance.py` 覆盖 SPCX 研究流和未知公司空状态中的完整度 UI。
  - 验收：单测覆盖未建档公司返回 `not_found` 和建档但缺事件/行情等事实层时返回 `incomplete`；UI 静态检查通过；浏览器验收 18/18 通过。
  - 后续增强：T-463 可继续处理多字段冲突/替代断言，并把真实样本完整度分数权重校准为可配置规则。

- `DONE` T-463 公司画像字段断言冲突复核
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-460/T-461 已把官方/IR 材料抽取为字段级证据断言，但同一公司、同一字段可能从不同官方来源得到不同值。系统需要在替换前保留冲突候选，避免自动覆盖既有公司画像。
  - **已完成（本轮）**：`CompanyProfileFieldAssertion` 新增 `conflicts_with` 和 `resolved_by`，可表达新旧字段断言之间的冲突和复核解决关系。
  - **已完成（本轮）**：`POST /api/company-database/profile-fields/extract` 在 `refresh_existing=true` 遇到不同 active 断言时，生成 `conflict_candidate` / `needs_review` 字段断言，不会提前覆盖 `Issuer` 或 `CompanyProfile` 当前字段。
  - **已完成（本轮）**：新增 `POST /api/company-database/profile-field-assertions/review` 和 `POST /api/company-profiles/field-assertions/review`，支持 `approve`、`supersede`、`reject`；批准后才应用新字段值并把旧断言标记为 `superseded`。
  - **已完成（本轮）**：字段断言查询返回 `status_counts`、`review_status_counts`、`conflict_count` 和 `superseded_count`，便于公司数据库补库流程发现待复核冲突。
  - 验收：单测覆盖官网字段冲突候选不覆盖原值、复核批准后替换画像字段、旧断言 superseded、新断言 active/approved、覆盖审计只引用批准后的 evidence。
  - 后续增强：UI 待复核队列、批量批准/驳回和字段级来源优先级规则仍可继续推进。

- `DONE` T-464 公司画像字段冲突复核工作台
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-463 已有字段断言冲突候选和 review API，但分析用户仍需要在公司情报工作台里直接看到待复核字段冲突并进行批准/拒绝，而不是手工调用 API。
  - **已完成（本轮）**：公司数据库补齐面板新增“查看字段冲突”入口、字段复核状态、字段冲突数、已替代数和冲突断言表。
  - **已完成（本轮）**：冲突断言表读取 `CompanyProfileFieldAssertion` 的 `conflict_candidate` / `needs_review` 记录，展示字段名、候选值、来源证据、冲突旧断言，并提供“批准替换”和“拒绝”操作。
  - **已完成（本轮）**：批准/拒绝按钮调用 `POST /api/company-database/profile-field-assertions/review`，执行后刷新字段冲突队列和公司情报总览，仍只更新本地事实 provenance，不触发真实交易。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 增加字段冲突队列 DOM、JS 函数和 `review-company-profile-assertion` 交互标记；`scripts/ui_interaction_acceptance.py` 增加合成冲突断言渲染验收。
  - 验收：UI 静态检查通过；浏览器验收能看到字段冲突复核队列、计数和批准按钮；单测覆盖 reject 后旧画像值和旧 evidence 仍保持 active。
  - 后续增强：批量批准/拒绝、复核备注输入框、字段级来源优先级和 freshness 推荐规则。

- `DONE` T-465 公司画像字段断言批量复核与推荐增强
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-464 已让字段冲突进入工作台，但高频复核仍需要批量处理、复核备注和旧值/推荐对比，避免分析用户逐条操作。
  - **已完成（本轮）**：`/api/company-database/profile-field-assertions` 返回 `conflicting_assertions` 和 `review_recommendation`，把旧值摘要、来源优先级、freshness、候选分数和建议动作一并返回。
  - **已完成（本轮）**：`POST /api/company-database/profile-field-assertions/review` 支持 `assertion_ids` 批量复核，保留单条 `assertion_id` 兼容语义，并记录 `note` 到复核 metadata。
  - **已完成（本轮）**：公司情报工作台新增批量批准/拒绝按钮、复核备注输入框、选择框和推荐状态条；冲突表展示旧值摘要与推荐。
  - **已完成（本轮）**：`scripts/ui_static_check.py`、`scripts/ui_interaction_acceptance.py` 和单测覆盖批量复核与推荐信息。
  - 验收：静态契约、浏览器验收和后端回归都能证明批量 review、推荐展示和备注写入可用，且仍不触发真实交易。

- `DONE` T-466 公司关系候选批量复核与推荐增强
  - 对应：E3-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-443/T-444/T-448 已能从公开披露抽取客户、供应商、合作方、子公司等 `CompanyRelationship` 候选并在工作台单条审核，但关系层仍缺少批量处理、复核备注和来源质量推荐，影响公司关系图谱长期补库效率。
  - **已完成（本轮）**：`GET|POST /api/company-relationships` 返回 `source_quality`、`review_recommendation`、候选关系数和状态计数，推荐只用于人工排序，不自动批准关系。
  - **已完成（本轮）**：新增 `POST /api/company-relationships/review` 和兼容入口 `POST /api/company-database/relationships/review`，支持 `relationship_ids` 批量 approve/reject/merge，并把复核备注写入每条关系的 `metadata.review_history`。
  - **已完成（本轮）**：公司情报工作台“关系候选审核”新增推荐状态、候选计数、选择框、批量通过/拒绝和复核备注输入框；单条合并仍保留。
  - **已完成（本轮）**：`scripts/ui_static_check.py`、`scripts/ui_interaction_acceptance.py` 和单测覆盖关系候选推荐、选择、批量复核和备注写入。
  - 验收：关系复核仍只更新本地图谱 provenance，不触发真实交易；研报覆盖关系仍是观点/关注度关系，不会被提升为客户、供应商或竞争事实。
  - 后续增强：T-467 本地公司 IR/官网/官方披露材料 inbox 工作台入口；T-468 公司事件候选复核 API 与工作台；T-469 补库 run retry/resume UI。

- `DONE` T-467 本地公司 IR/官网/官方披露材料 inbox 工作台入口
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-461 已提供 `scripts/company_material_inbox_ingest.py`，可用 manifest sidecar 将本地官方/IR/监管/交易所材料送入 source/document/evidence/profile field assertion 链路，但公司情报工作台还没有可见入口。
  - **已完成（本轮）**：新增 `POST /api/company-database/material-inbox/ingest`，把 T-461 的本地 manifest sidecar 入库能力挂到工作台后端服务，默认 dry-run，显式 execute 才注册 source、写入 document、抽取 evidence 和画像字段断言。
  - **已完成（本轮）**：公司数据库补齐面板新增本地材料 inbox 路径、manifest glob、扫描上限、预览/执行按钮、材料计划表和状态计数，执行后刷新画像字段覆盖、字段冲突队列和公司情报总览。
  - **已完成（本轮）**：入口继续拒绝研报、券商研究、新闻、manual reference、未知 source/document 类型和 `training_allowed=true` 记录；不按文件名猜公司，不下载外部数据，不触发真实交易。
  - 验收：`python3 -m py_compile app/api.py app/services.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py`、`python3 scripts/ui_static_check.py` 和直接 API smoke 覆盖 dry-run planned/invalid 边界。

- `DONE` T-468 公司事件候选复核 API 与工作台
  - 对应：E3-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-449 已能从官方披露摘要、evidence 文本和非研报 Document 正文生成 `CompanyEvent` 细粒度候选，并设置 `review_status=needs_review`，但事件时间线缺少批准、拒绝、合并和改分类闭环。
  - **已完成（本轮）**：`GET|POST /api/company-events` 返回 `source_quality`、`review_recommendation`、候选事件数和状态计数，推荐只用于人工排序，不自动批准事件。
  - **已完成（本轮）**：新增 `POST /api/company-events/{event_id}/review`、`POST /api/company-events/review` 和兼容入口 `POST /api/company-database/events/review`，支持 approve/reject/merge/reclassify，并把复核记录写入 `metadata.review_history`。
  - **已完成（本轮）**：公司情报工作台新增“事件候选复核”面板，展示候选计数、推荐状态、选择框、批量批准/拒绝、单条合并和改分类入口。
  - **已完成（本轮）**：`scripts/ui_static_check.py`、`scripts/ui_interaction_acceptance.py` 和单测覆盖事件候选推荐、选择、批准、拒绝、合并、改分类和备注写入。
  - 验收：事件复核只更新本地时间线 provenance，不触发真实交易；研报覆盖事件仍保持观点/关注度信号，不会被自动提升为事实。

- `DONE` T-469 补库 run retry/resume 工作台入口
  - 对应：E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-454 已有 `POST /api/company-database/batch/runs/{run_id}/retry` 和 `resume_run_id` 语义，T-455 已在 UI 展示 retry/resume 元数据，但分析用户仍不能从工作台直接对失败、partial 或历史 run 发起重试/续跑。
  - **已完成（本轮）**：运行历史表每行新增“预览重试”“续跑剩余”“重跑全部”操作，按钮通过 `data-action="retry-company-build-run"` 保留 run lineage、resume mode 和 execute/dry-run 边界。
  - **已完成（本轮）**：新增 `retryCompanyBuildRun` 前端调用 `POST /api/company-database/batch/runs/{run_id}/retry`，默认 dry-run 预览，显式执行才补库；成功后刷新运行历史、覆盖趋势和公司情报总览。
  - **已完成（本轮）**：UI 静态契约和交互验收脚本覆盖 retry/resume action marker、JS 函数和“执行补库后预览重试”的浏览器路径。
  - 验收：`python3 scripts/ui_static_check.py`、`python3 -m py_compile app/api.py app/services.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768` 25/25 通过；后端 retry/resume 语义沿用 T-454 既有单测。

- `DONE` T-470 公司情报闭环刷新 runner 与工作台入口
  - 对应：E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：研报兑现、观察任务/分析结论生成、模拟反馈表现更新已经分别存在，但用户仍需要手动按顺序触发，导致公司档案刷新后不能直接看到分析闭环是否同步。
  - **已完成（本轮）**：新增 `POST /api/company-intelligence/{symbol}/cycle/run`，默认 dry-run，按本地 symbol 解析 issuer 后串联研报兑现、company workflow build 和 paper-only 模拟反馈表现更新。
  - **已完成（本轮）**：接口返回刷新前后公司情报完整度、公司数据库覆盖率、兑现项、workflow 项、反馈更新项和固定本地/paper-only/no-broker 边界。
  - **已完成（本轮）**：公司情报工作台新增“预览闭环刷新”“执行闭环刷新”按钮和状态指标；执行后刷新公司情报、补库 run 历史与覆盖趋势。
  - **已完成（本轮）**：`docs/api-contracts.md`、`scripts/ui_static_check.py`、`scripts/ui_interaction_acceptance.py` 和单测覆盖新 API、UI contract 和浏览器预览路径。
  - 验收：`python3 -m py_compile app/api.py app/services.py tests/test_system.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_cycle_runs_local_workflow_feedback_loop`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-471 公司财务指标事实层与画像快照回链
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：公司画像已能保存 `latest_financial_snapshot`，但财务字段仍缺一等事实记录，导致收入、净利、毛利率、现金、债务等数据无法按期间、来源、证据和状态独立查询，也不利于后续完整公司数据库审计。
  - **已完成（本轮）**：新增 `FinancialMetric` 模型和 `financial_metrics` 存储集合，字段包含公司、证券、指标名、期间、数值、单位、币种、报表类型、来源、文档、证据、置信度和复核状态。
  - **已完成（本轮）**：新增 `GET|POST /api/company-financial-metrics`，支持按公司、证券、指标、期间和状态查询或登记财务事实；登记时拒绝研报、新闻、人工参考和红色风险来源作为事实源。
  - **已完成（本轮）**：官方/IR/监管材料画像字段抽取在 `execute=true` 时，会把 `revenue`、`net_income`、`gross_margin`、`cash`、`debt` 同步物化为 `FinancialMetric`，并回写公司最新财务快照。
  - **已完成（本轮）**：公司情报聚合和深字段覆盖审计读取 `FinancialMetric`，让财务字段的 source_records 优先回链到指标事实记录，而不是只指向 issuer 快照。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-472 本地单标的公司数据库 bootstrap
  - 对应：E3-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：`company-intelligence/{symbol}` 对未知 symbol 只能返回空状态，`company-database/build` 又依赖已有 issuer/security，导致用户进入工作台后无法从一个新标的直接建立公司数据库。
  - **已完成（本轮）**：新增 `POST /api/company-database/bootstrap`，默认 dry-run，按 symbol/company name 生成本地 issuer/security/profile stub 计划；显式 `execute=true` 才写入。
  - **已完成（本轮）**：bootstrap 返回覆盖预览和 `material_inbox_manifest_template`，指导用户把公司官网、IR、公告材料放入本地 material inbox。
  - **已完成（本轮）**：bootstrap 幂等处理已存在 issuer/security/profile，不重复创建；已建档公司情报页不再提示 bootstrap。
  - **已完成（本轮 UI）**：公司情报 unknown symbol 的下一步动作改为 bootstrap，并可从工作台触发 bootstrap dry-run 预览。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_bootstrap_creates_local_stub_for_unknown_symbol tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-473 本地 watchlist / 公司包导入与材料 inbox execute 回归
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-472 已支持未知 symbol 单标的 bootstrap，但分析用户通常从 watchlist、CSV 或样例公司包开始；同时 T-467 的材料 inbox 需要路由级 execute 回归，证明本地官方/IR 材料能真正进入 source/document/evidence/画像字段断言链路。
  - **已完成（本轮）**：新增 `POST /api/company-database/package/import` 和兼容别名 `POST /api/company-database/watchlist/import`，支持本地 JSON/CSV package manifest、`companies/items/watchlist`、`symbols/tickers/codes` 和 `csv_text`。
  - **已完成（本轮）**：接口默认 dry-run，显式 `execute=true` 才逐家公司复用 `bootstrap_company_database` 创建本地 issuer/security/profile stub；重复 symbol 会被标记 duplicate，缺 symbol 会被标记 invalid，不会 fallback 到全量公司。
  - **已完成（本轮）**：每家公司返回 `material_inbox_manifest_template` 和下一步动作，指导用户继续准备公司官网、IR、公告或监管披露材料；接口固定本地-only、no external download、no research-report fact promotion、no live trading 边界。
  - **已完成（本轮 UI）**：公司情报工作台“公司数据库补齐”面板新增“本地 watchlist / 公司包”路径、glob、导入上限、预览和执行按钮，展示计划数、导入数、无效数和逐公司结果。
  - **已完成（本轮回归）**：新增 material inbox API execute 测试，直接调用 `/api/company-database/material-inbox/ingest` 验证 source 注册、document 写入、evidence 抽取和 `CompanyProfileFieldAssertion` 回填。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_package_import_bootstraps_watchlist_companies tests.test_system.SystemServiceTests.test_company_database_package_import_does_not_fallback_to_all_issuers tests.test_system.SystemServiceTests.test_company_material_inbox_api_execute_backfills_profile_fields`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-474 本地 watchlist / 公司包导入运行历史与审计查询
  - 对应：E3-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-473 已支持本地 watchlist / 公司包导入，但导入结果此前只存在于接口响应和 audit log；长期使用需要持久化每次 package import run，支持查询、审计、失败复盘和后续 material inbox 准备。
  - **已完成（本轮）**：新增 `CompanyPackageImportRun` 模型和 `company_package_import_runs` 存储集合，独立于 `CompanyDatabaseBuildRun`，避免把导入语义混入补库 batch/retry/resume 历史。
  - **已完成（本轮）**：`POST /api/company-database/package/import` 和兼容别名在 `execute=true` 时默认记录 run；dry-run 默认不记录，显式 `record_run=true` 时才落盘。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/package/import/runs` 和兼容别名 `/api/company-database/watchlist/import/runs`，支持按 `run_id`、`issuer_id`、`symbol`、`status`、`limit` 和 `include_items` 查询。
  - **已完成（本轮）**：运行历史只保存 slim 行级审计字段，不保存即时响应中的覆盖详情、材料模板和 next_actions，固定本地-only、no external download、no live trading 边界。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_package_import_bootstraps_watchlist_companies tests.test_system.SystemServiceTests.test_company_database_package_import_dry_run_history_is_explicit tests.test_system.SystemServiceTests.test_company_database_package_import_does_not_fallback_to_all_issuers`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-475 公司包导入运行历史工作台入口
  - 对应：E3-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-474 已有本地公司包导入运行历史 API，但工作台仍看不到导入 run，用户需要手调接口才能复盘 watchlist / 公司包导入结果。
  - **已完成（本轮 UI）**：公司情报工作台新增“查看导入历史”按钮、导入历史状态卡、导入次数、最近导入时间和导入 run 表格。
  - **已完成（本轮 UI）**：导入历史按当前 symbol 查询最近 run，展示 run 状态、公司数、主体数、代码、来源、valid/executed/existing/invalid/duplicate/failed 汇总、创建主体数和本地-only 边界。
  - **已完成（本轮 UI）**：执行公司包导入后自动刷新导入历史，方便立即确认 run 是否落盘。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`；浏览器交互验收新增 `company_package_import_run_history_render`。

- `DONE` T-476 公司包导入 run 到材料 inbox manifest 模板导出
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-474/T-475 已能持久化和查看本地 watchlist / 公司包导入 run，但“导入公司清单 -> 准备官方/IR/公告材料 -> material inbox 入库”的数据源链路仍需要手工拼 sidecar manifest。
  - **已完成（本轮）**：新增 `POST /api/company-database/package/import/runs/{run_id}/material-manifests` 和 watchlist 兼容别名，从导入 run 生成本地 material inbox manifest 模板。
  - **已完成（本轮）**：接口默认 dry-run，仅返回模板；`execute=true` 且提供 `output_root` 时才写入本地 `*.manifest.json`，默认不覆盖已有文件。
  - **已完成（本轮 UI）**：公司情报工作台新增材料 manifest 输出目录、预览 manifest、写入 manifest、状态卡和 manifest 结果表；从最近导入 run 生成模板。
  - **已完成（本轮边界）**：manifest 模板固定用于官方/IR/公告等本地材料准备，不下载外部数据，不把研报当事实源，不训练模型，不触发真实交易。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_package_import_run_exports_material_manifest_templates`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`；浏览器交互验收新增 `company_package_material_manifest_render`。

- `DONE` T-477 公司情报闭环刷新运行历史与工作台入口
  - 对应：E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-470 已有公司级闭环刷新 runner，但执行结果此前只存在于一次 API 响应，无法复盘某家公司什么时候刷新过、完整度是否改善、workflow/反馈是否更新。
  - **已完成（本轮）**：新增 `CompanyIntelligenceCycleRun` 持久对象和 `GET|POST /api/company-intelligence/cycle/runs`，执行闭环刷新默认记录本地历史，dry-run 需显式 `record_run=true` 才记录。
  - **已完成（本轮 UI）**：公司情报工作台新增“查看闭环历史”、闭环次数、闭环历史表，展示 run、公司、完整度变化、覆盖变化、workflow、兑现和反馈摘要。
  - 验收：单测覆盖执行闭环刷新后落历史并可按 symbol 查询；UI 静态检查覆盖新增 DOM/JS；历史固定本地-only、paper feedback、no live trading。

- `DONE` T-478 公司材料 URL 自动填充与 manifest 源候选
  - 对应：E3-US1, E5-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-476 能生成 material inbox sidecar，但 `source_uri` 默认只能是示例 URL，用户仍需重复手填公司 IR 或官网链接。
  - **已完成（本轮）**：manifest 导出在未传 `source_uri_template` 时，优先读取本地 `Issuer.company_details.ir_url`、`website_url`、官方 source provenance 或 TOS URL；均不可用时才回退示例 IR URL。
  - **已完成（本轮）**：单测覆盖公司画像里已有 IR URL 时，dry-run 和写入的 manifest 都自动使用真实 URL。
  - 边界：该能力只使用本地已有公司画像/source 元数据，不下载外部网页，不把研报当事实源。

- `DONE` T-479 公司包导入后的待补材料队列
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：导入公司包、生成 manifest 和执行材料 inbox 之间仍缺一个任务化队列，用户难以判断哪些公司还缺 sidecar、哪些缺正文、哪些可以入库。
  - **已完成（本轮）**：新增 `GET|POST /api/company-database/material-inbox/pending`，从公司包导入 run 派生待补材料队列，按本地目录检查 manifest 和正文文件是否存在。
  - **已完成（本轮 UI）**：公司情报工作台新增“查看待补材料”、待补材料计数和队列表，区分 `needs_manifest`、`needs_material_file`、`ready_to_ingest`。
  - 验收：单测覆盖 manifest 写入后显示缺正文，补正文文件后显示可入库；UI 静态检查覆盖新增 DOM/JS。

- `DONE` T-480 个人用户公司情报阅读视图简化
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：公司情报页已经聚合了画像、事件、关系、研报、补库、材料 inbox、冲突复核、运行历史和质量归并，但个人用户默认进入时更需要阅读公司情报和下一步判断，而不是先面对维护动作。
  - **已完成（本轮）**：公司情报总览新增“个人研究摘要”层，默认展示当前判断、最新事实、观点变化、反馈与下一步，直接从公司情报聚合数据渲染。
  - **已完成（本轮）**：公司数据库补齐、材料入库、字段冲突、运行历史、质量归并、事件/关系候选复核、研报结构化和完整 JSON 默认折叠到高级维护/调试区，保留全部原有控件和 DOM contract。
  - **已完成（本轮）**：维护动作仍可从高级区展开使用；个人视图保留开始研究、整理研报观点和查看缺口三个轻量动作。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8770 --output-dir artifacts/ui-interaction-acceptance-personal-ui-current` 28/28 通过。

- `DONE` T-481 公司情报页面视觉再优化
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-480 已经把默认信息结构简化，但个人用户仍会感到页面偏“工具堆叠”，需要进一步收敛视觉噪音，让关键判断、指标和表格更清晰。
  - **已完成（本轮）**：在不改动业务能力和 DOM contract 的前提下，优化公司情报总览的留白、层级、卡片质感、表格可读性和高级维护区的弱化呈现。
  - **已完成（本轮）**：桌面和移动视口均完成截图审视，个人摘要、指标卡和高级折叠区无明显遮挡或文本溢出。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8770 --output-dir artifacts/ui-interaction-acceptance-personal-ui-polish` 28/28 通过。

- `DONE` T-482 个人关注池自动公司情报闭环
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：当前底层行情、研报和证据很多，但公司画像、事件、关系、观点和 paper-only 反馈没有随日更自动形成关注池级闭环，导致个人用户看到的数据仍像散表。
  - 目标：新增关注池驱动的自动公司情报刷新，把日更后的关注标的自动建档、补事件/关系、结构化观点并生成观察/结论/模拟反馈；总览页前置展示闭环状态和每家公司缺口。
  - **已完成（本轮）**：新增 `scripts/personal_intelligence_refresh.py`，默认关注池 `AAPL,NVDA,MSFT,300750,600519` 可通过现有公司数据库 API 自动建档、生成事件/关系、结构化研报观点、观察/结论和 paper-only 反馈，并输出 `artifacts/personal-intelligence/latest.json`。
  - **已完成（本轮）**：日更流水线和 `scripts/run_daily_data_update.sh` 已接入个人关注池刷新，支持跳过、允许失败、执行/演练、关注池标的和超时等环境变量配置。
  - **已完成（本轮）**：`/api/analysis/latest` 暴露 `personal_intelligence` 和 artifact path；首页总览新增“个人关注池自动闭环”，展示运行状态、公司数、待关注数、每家公司缺口和下一步动作，并可点击进入公司情报页。
  - 验收：`python3 scripts/personal_intelligence_refresh.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,MSFT,300750,600519 --execute --output artifacts/personal-intelligence/latest.json` 通过，生成 5 个关注标的；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；`/api/analysis/latest` 回读 `personal_intelligence.status=passed`。

- `DONE` T-483 Obsidian 式知识图谱探索视图
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：知识图谱页此前主要是指标和表格，个人用户无法像 Obsidian Graph View 一样快速看见公司、产业链、事件、证据、观点、结论、组合和风险之间的关系。
  - 目标：在知识图谱页第一屏新增可探索关系网络，支持搜索节点、关系类型过滤、深度聚焦、重置视图、缩放/拖拽、点击节点侧栏和相邻节点联动，同时保留原有表格明细。
  - **已完成（本轮）**：新增原生 SVG 力导向关系图谱，把 `/api/graph/query` 返回的公司、证券、产业链、事件、文档证据、研报观点、分析结论、观察任务、组合/持仓和复盘风险统一渲染为节点和边。
  - **已完成（本轮）**：新增节点类型图例、搜索框、深度选择、一键重置和产业/证据/观点/组合/风险过滤；点击节点会高亮一跳关系并在侧栏显示摘要和相邻关系。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；浏览器打开 `/ui` 的“知识图谱”页，确认图谱 SVG、节点数、关系数、过滤和节点详情正常。

- `DONE` T-484 知识图谱动态力导向交互
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-483 已经有 Obsidian 式关系图谱，但布局仍是一次性计算后的静态网络；用户希望它成为真正动态的关系图谱。
  - 目标：让知识图谱持续进行力导向运动，支持暂停/继续、拖拽节点固定、释放固定节点，并在搜索、过滤和深度变化后平滑重新收敛。
  - **已完成（本轮）**：将一次性布局替换为 `requestAnimationFrame` 驱动的持续力导向模拟，节点/边位置会随运行状态动态更新。
  - **已完成（本轮）**：新增“暂停动态”“释放节点”和运动状态显示；拖拽节点会固定位置，释放后重新参与图谱运动。
  - 验收：`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；浏览器打开 `/ui` 的“知识图谱”页，确认 AAPL 图谱节点位置随时间变化，暂停后位置停止变化，继续后恢复动态。

- `DONE` T-485 知识图谱可读性与布局修正
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：动态知识图谱首版在 AAPL 这类星形关系中出现节点吸附外边、节点重叠、底层 ID/重复泛标签过多的问题。
  - 目标：让默认图谱成为可读的关系摘要，而不是数据库节点散点图；修正贴边、重叠和命名噪音。
  - **已完成（本轮）**：新增语义命名与类型推断，`issuer/security/vp/rr/ce` 等底层 ID 会被折叠为公司、证券、研究观点、事件等业务语义。
  - **已完成（本轮）**：默认图谱按类型配额保留高价值节点，隐藏证据/事件/观点的泛化常显标签，只在选中/高亮时查看关系细节。
  - **已完成（本轮）**：调整为分类聚类、碰撞避让、软边界和更大安全边距，AAPL 验证结果为 29 节点、85 关系、0 重叠、0 贴边。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器 AAPL 图谱布局量化检查。

- `DONE` T-566 Obsidian 标准可探索知识网络升级
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-483/T-484/T-485 已有动态关系图谱，但用户反馈仍不像 Obsidian Graph View：AAPL 等中心公司仍容易呈放射状，默认裁剪和布局更像“公司中心视图”，不是可继续探索的知识网络。
  - 目标：把知识图谱从中心化可视化升级为 Obsidian 式可探索网络，支持社区化布局、边权驱动收敛、点击节点按需展开隐藏邻居、标签避让、隐藏邻居提示和更自然的全局/局部探索体验。
  - **进行中（本轮）**：前端图谱模型新增 `community`、`weight`、`hiddenNeighborCount` 和 `expandedIds`；默认视图改为高价值摘要，点击节点可展开其邻居，节点有隐藏邻居外圈提示。
  - **进行中（本轮）**：布局从固定类型扇区推进为社区中心 + 边权距离 + 稳定散列初始位置 + 强碰撞避让 + 标签避让；图谱画布高度提升到 640px。
  - **进行中（本轮）**：新增局部图/全局图模式，默认局部图优先可读性，全局图保留更多节点；新增 `scripts/ui_graph_layout_acceptance.py` 对 AAPL 图谱做可重复浏览器量化验收。
  - **进行中（本轮）**：新增社区簇标签/摘要层，显示公司/证券、事件/证据等关系簇数量；验收脚本支持 `--scope local|global`，分别校验局部图可读性和全局图概览密度。
  - **进行中（本轮）**：新增本地持久化手动布局，拖拽/固定节点后按焦点、模式、深度和过滤组合写入 `localStorage`；新增“清除布局”入口；验收脚本支持 `--check-persistence`。
  - **进行中（本轮）**：社区簇标签新增质量摘要，显示密度、关系强度和强边占比；验收脚本校验 `community_quality_labels`。
  - **进行中（本轮）**：新增路径探索面板，可把当前节点设为起点/终点，计算并高亮当前可见图中的最短路径；验收脚本支持 `--check-path`。
  - **进行中（本轮）**：路径步骤新增 next-hop 邻居按钮，点击可从路径节点继续漫游，同时保持新的可见路径高亮；验收脚本校验 `path_next_hops` 和 next-hop 后路径高亮。
  - **进行中（本轮）**：新增显式视图控制：缩小、放大、适配全部可见节点、居中当前焦点节点；状态栏显示当前缩放比例；验收脚本默认校验 `view_controls`。
  - **进行中（本轮）**：路径面板新增“固定当前”“保存路径”“清除轨迹”和探索轨迹列表，固定节点写入 `fixedIds`，路径节点可沉淀为可点击轨迹；验收脚本默认校验 `trail`。
  - **进行中（本轮）**：新增图谱性能采样，状态栏显示 `FPS` 和平均帧耗时；验收脚本新增 `--min-fps` / `--max-frame-ms`，默认要求 FPS >= 20、平均帧耗时 <= 35ms。
  - **进行中（本轮）**：新增“保存子图/恢复子图”，使用 `ai_quant_graph_subgraph:{focus}` 保存当前轨迹、固定节点、展开节点、路径起终点、模式、深度和视图变换；验收脚本默认校验 `saved_subgraph`。
  - **进行中（本轮）**：新增 `scripts/ui_graph_multi_symbol_acceptance.py` 多主体矩阵验收，覆盖 AAPL 局部、NVDA 局部、600519 局部和 AAPL 全局；同时把单体验收中的 AAPL 硬编码改为使用当前 `focusId`。
  - **进行中（本轮）**：新增 `scripts/ui_graph_relationship_filter_acceptance.py` 关系过滤矩阵，真实浏览器校验 AAPL/NVDA/600519 的 `listed_security` 和 `institution_coverage` 过滤 chip、raw relationship type、渲染节点边、轨迹/保存子图和性能状态。
  - **进行中（本轮）**：`/api/graph/query` 新增基于现有 `CompanyPosition + IndustryChain.edges` 的派生产业链语义边，不改数据库 schema，不新增事实关系；有产业链位置数据时会返回 `INDUSTRY_PEER` / `INDUSTRY_UPSTREAM_OF` / `INDUSTRY_DOWNSTREAM_OF`，并保留 raw `relationship_type=industry_peer/upstream_of/downstream_of`、`chain_id`、`node_ids` 和 position 追溯。
  - **进行中（本轮）**：单测补齐同类、上游、下游图谱查询回归，确认 `relationship_type=industry_peer/upstream_of/downstream_of` 过滤可以返回对应发行人和语义边；方向级 `chain_node_id` 过滤按关系方向节点匹配，避免推荐入口误伤。
  - **进行中（本轮）**：`scripts/ui_graph_layout_acceptance.py` 的关系过滤统计从只看 `company_relationships` 扩展为同时识别 `edges[].relationship_type`，为后续浏览器验收产业链派生边做准备。
  - **进行中（本轮）**：`scripts/ui_graph_relationship_filter_acceptance.py` 新增受控产业链 fixture，通过公开 API 在当前服务内准备 AAPL/NVDA/600519 基础主体、上市证券/机构覆盖关系，以及 AAPL 同类/上游/下游 `CompanyPosition + IndustryChain`；关系过滤矩阵扩展到 9 个 case，覆盖 AAPL 的 `industry_peer` / `upstream_of` / `downstream_of` 浏览器端可见 chip、raw edge relationship type、节点/边渲染和性能状态。
  - **进行中（本轮）**：修正 `/api/graph/query` 产业链派生边在带 `security_id` 过滤时误删相关公司 position 的问题；焦点公司仍受证券过滤，peer/upstream/downstream 相关公司不再被要求拥有同一 `security_id`。
  - **已完成（本轮降噪）**：默认主体图不再把 full-graph production universe 生成的 `needs_review` 批量产业定位扩散成全市场同链网络；`issuer_aapl` 默认查询从 5422 个 chain node 收敛到 AAPL 焦点定位节点，AAMI 等无关链节点不再进入首屏，显式 `relationship_type` / `chain_id` / `chain_node_id` 探索入口仍保留。
  - **已完成（本轮降噪验收）**：当前代码在 `AI_QUANT_PORT=55661` 连接本地 PostgreSQL 后，AAPL 全局浏览器验收通过：22 个可见节点、44 条可见边、30 个完整图节点、52 条完整图边、4 个社区标签、0 重叠、0 贴边、标准渲染模式，artifact 为 `artifacts/ui-graph-layout-scoped-55661.json`。
  - **进行中（本轮）**：新增 `scripts/graph_acceptance_fixture.py`，把图谱验收数据准备从浏览器矩阵脚本中抽离为可单独运行的公开 API fixture 准备脚本；`scripts/ui_graph_relationship_filter_acceptance.py` 改为复用该脚本，避免产业链样本长期藏在验收内部。
  - **进行中（本轮）**：`python3 -m app.server` 新增 `AI_QUANT_PORT` 支持和端口范围校验，便于在 8000 被旧服务占用时直接启动当前代码做图谱验收。
  - **进行中（本轮）**：新增 `app/service_modules/graph_seed.py`、`POST /api/graph/seed/obsidian` 和 `scripts/seed_obsidian_knowledge_graph.py`，用现有注册 API/模型准备本地 Obsidian 式知识网络样本，覆盖 AAPL/NVDA/MSFT/TSM/ASML/AVGO/600519/600809 的产业位置、同类/上下游派生边、上市证券关系和 13F 同持有人网络。
  - **进行中（本轮）**：图谱浏览器验收新增 `institutional_holder_key=0000102909` case，强校验 `SAME_HOLDER_RELATED_COMPANY` 原始边和“13F持有人”过滤 chip，补上“看到某公司时，该股东还持有哪些公司”的可见图谱链路。
  - **已完成（本轮修正）**：默认局部裁剪改为“焦点 + 展开节点邻居 + 社区骨架 + 跨社区桥接 + 关键知识节点”保留；提高 `event` / `evidence` / `research` / `portfolio` 权重，降低 issuer/security 对首屏的挤占。
  - **已完成（本轮修正）**：布局去掉 issuer 强中心吸附，改为社区环形重心 + 展开节点局部锚点；点击节点后其邻居围绕该节点形成小团簇，减少 AAPL 星状放射线。
  - **已完成（本轮修正）**：单击节点只负责选中并展开，不再二次点击收起；双击或“设为焦点”才切换焦点；标签策略放宽到知识节点和度数节点，图本身承担主要探索入口。
  - **已完成（本轮修正）**：`scripts/ui_graph_layout_acceptance.py` 新增点击后可见邻居增长验收，要求被点击节点进入 `expandedIds` 且可见邻居/节点/边真实增加，避免“看似选中但没有自然展开”回归。
  - **已完成（本轮修正 2）**：单击节点现在直接切换当前图谱焦点并展开，焦点历史仍保留回退能力；布局改为焦点居中、邻居环绕、二跳外圈的径向网络，不再按社区把节点推到矩形边缘。
  - **已完成（本轮修正 2）**：重心切换时清理非固定旧布局坐标，避免 localStorage/旧坐标把新主节点拖回旧位置；验收脚本新增 `node_click_focus_switch`，点击后焦点必须等于被点击节点。
  - **已完成（本轮修正 3）**：修复真实鼠标点击被 `pointerdown` 拖拽逻辑吞掉的问题；现在 `pointerdown` 只记录候选节点并高亮，只有移动超过阈值才进入拖拽/固定并抑制 click，普通按下松开会正常触发焦点切换。
  - **已完成（本轮修正 3）**：浏览器验收从直接派发 `MouseEvent('click')` 改为真实 `PointerEvent('pointerdown')` + `PointerEvent('pointerup')` + `click` 链路，覆盖“按住点亮、松开复原”的真实交互回归。
  - **已完成（本轮修正 4）**：社区簇标签也成为可探索入口；点击“产业链”等社区摘要会选择该社区代表节点并切换焦点。修复社区标签文字 `pointer-events:none` 导致真实点击穿透到 SVG 背景、焦点回到 AAPL 的问题。
  - **已完成（本轮修正 4）**：新增浏览器原生输入层验收，用 Chrome DevTools `Input.dispatchMouseEvent` 点击社区标签坐标，确认“AI 端侧设备与算力产业链”可切焦点；`scripts/ui_graph_layout_acceptance.py` 也新增 `community_click` 断言。
  - **已完成（本轮修正 5）**：修复普通节点真实点击仍可能不切焦点的问题：节点 `pointerdown` 会把 pointer capture 交给 SVG，导致节点自身 `pointerup` 不稳定；现在 SVG 级 `pointerup` 会根据 `pendingNodePointer` / `elementFromPoint` 兜底切换焦点。
  - **已完成（本轮修正 5）**：焦点切换统一走 `switchKnowledgeGraphFocusNode()`，同步更新 `focusId` 和 `selectedId`，避免社区标签切焦点后右侧详情仍显示 AAPL。
  - **已完成（本轮修正 6）**：同名节点标签去歧义：发行主体显示为 `AAPL · 公司`，证券节点显示为 `AAPL · NASDAQ` / 交易场所，避免公司节点和上市证券节点都显示裸 `AAPL`。
  - **已完成（本轮修正 7）**：补齐图谱默认展示标签清洗层，`doc_/hold_/pos_/srr_/vp_/event_/rel_...obsidian` 种子 ID、`RELATIONSHIP_*` / `VIEWPOINT_ON_COMPANY` / `HOLDS_SECURITY` 等 raw 关系类型不再直接进入画布、inspector 和关系表默认文本；折叠追溯仍保留 raw provenance。
  - **已完成（本轮修正 7）**：`graphRef()` / `userEntityLabel()` / `relationshipTypeDisplayLabel()` / inspector 相邻关系统一走图谱语义标签，产业链派生节点按冒号后的环节显示为 `产业节点 · 半导体设备/晶圆代工/...`，避免相同内部前缀被误判为同一个“端侧 AI”节点。
  - 当前验证：AAPL 局部图验收通过，`节点 39/132`、`关系 60/320`，实际 DOM 节点 36、关系 60、社区标签 2、质量标签 2、重叠 2 对、贴边 0、点击非焦点节点后 `expanded=3`，布局持久化恢复误差 `dx=0, dy≈0.04`，路径高亮 2 节点/1 边，路径 next-hop 6 个，点击 next-hop 后仍高亮 2 节点/1 边，视图控件 4 个且缩放/适配/居中通过，探索轨迹 2 节点且点击轨迹可回到节点，保存/清空/恢复子图后恢复 2 个轨迹节点，性能约 `60 FPS / 1.8ms`；AAPL 全局图验收通过，`节点 88/132`、`关系 182/320`、社区标签 2、质量标签 2、贴边 0、重叠 66 对（全局概览阈值内），路径 next-hop 6 个，点击 next-hop 后仍高亮 2 节点/1 边，视图控件、探索轨迹和保存子图通过，性能约 `60 FPS / 4.2ms`；多主体矩阵通过：AAPL local 36 节点/60 边、NVDA local 36 节点/73 边、600519 local 33 节点/88 边、AAPL global 88 节点/182 边；关系过滤矩阵通过：AAPL/NVDA/600519 的上市证券和机构覆盖过滤均只返回目标 relationship type，过滤 chip 可见且性能在阈值内。
  - 当前验证（继续推进）：当前代码 55539 临时服务运行 `scripts/seed_obsidian_knowledge_graph.py` 创建 38 条本地知识网络 seed；API 探针确认 AAPL `industry_peer` / `upstream_of` / `downstream_of` 均返回对应语义边，`institutional_holder_key=0000102909` 返回同持有人相关公司边；`scripts/ui_graph_layout_acceptance.py ... --institutional-holder-key 0000102909` 通过，18 节点/43 边、3 个社区标签、0 重叠、`SAME_HOLDER_RELATED_COMPANY` 可见；完整 `scripts/ui_graph_relationship_filter_acceptance.py` 矩阵扩展到 10/10 通过，新增 AAPL Vanguard holder case 28 节点/65 边。
  - 当前验证（自然展开修正）：当前代码 55551 临时服务 + Obsidian seed 通过 AAPL 局部图验收，`节点 36/49`、`关系 88/131`、实际 DOM 节点 35、关系 88、4 个可见社区、12 个产业节点、可见 `event/research/evidence` 类型、重叠 5 对、贴边 0、性能约 `60 FPS / 1.1ms`；点击非焦点节点 `pos_obsidian_asml_equipment` 后可见邻居从 1 增到 3、节点 +1、边 +1，确认点击后发生真实可见展开而不是只改变选中状态。
  - 当前验证（点击切主节点修正）：当前代码 55552 临时服务 + Obsidian seed 通过 AAPL 局部图验收，点击 `pos_obsidian_asml_equipment` 后焦点从 `issuer_aapl` 切换到 `pos_obsidian_asml_equipment`，可见邻居从 1 增到 3、节点 +1、边 +1；布局结果贴边节点 0、重叠 0、性能约 `60 FPS / 1.3ms`。当前 8000 端口仍是另一套长期运行 Postgres/S3 服务，不代表这次 55552 当前代码验证结果。
  - 当前验证（真实 pointer 修正）：当前代码 55552 已重启为最新交互代码，真实 pointer 链路验收通过；点击 `pos_obsidian_asml_equipment` 后 `focus_after=pos_obsidian_asml_equipment`、`focus_before=issuer_aapl`、可见邻居 1 -> 3、节点 +1、边 +1、贴边 0、重叠 0、性能约 `60 FPS / 1.5ms`。
  - 当前验证（社区标签真实点击）：当前代码 55552 重启后，用 CDP 原生 `Input.dispatchMouseEvent` 点击 `industry` 社区标签中心，焦点从 `issuer_aapl` 切到 `chain_obsidian_ai_device_network`，节点详情标题为 `AI 端侧设备与算力产业链`；脚本验收 `community_click` 通过，后续点击产业链社区代表节点 `chain_obsidian_ai_device_network:accelerator` 后焦点也能切换。
  - 当前验证（SVG pointerup 兜底）：当前代码 55552 重启后，用 CDP 原生鼠标事件先点击普通节点 `event_obsidian_aapl_on_device_ai`，焦点从 `issuer_aapl` 切到该事件节点；随后重新读取当前 `industry` 社区标签坐标并点击，焦点切到 `chain_obsidian_ai_device_network:edge_device`，且 `selectedId` 与 `focusId` 同步。
  - 当前验证（大图高性能模式）：当前 PostgreSQL AAPL 全局图底层达到 `10872` 节点 / `10894` 边，前端自动进入 `performance_mode=large`，状态栏显示“高性能”；浏览器验收通过，可见 47 节点 / 48 边、3 个社区标签、0 raw 文本泄漏、0 贴边、平均帧 6.5ms，artifact 为 `artifacts/ui-graph-layout-performance-mode-55659.json`。该模式通过收紧标签预算、隐藏非高亮边文字和移除普通节点阴影降低 SVG 大图负担；Canvas/WebGL 仍作为更大图失败时的后续选项。
  - 当前验证（标签去歧义）：当前代码 55552 重启后，浏览器探针确认 `issuer_aapl` 标签为 `AAPL · 公司`，`security_aapl_us` 标签为 `AAPL · NASDAQ`。
  - 当前验证（默认展示标签清洗）：当前代码 55552 重启并重新 seed 49 条 Obsidian 本地记录后，headless Chromium 探针确认默认可见节点、边、社区、inspector 和关系表文本中没有 `doc/hold/pos/srr/vp/event/rel ... obsidian`、`RELATIONSHIP`、`VIEWPOINT_ON_COMPANY`、`product strategy` 等残留；AAPL 局部图 layout acceptance 继续通过，35 DOM 节点、88 边、4 个可见社区、12 个产业节点、0 重叠、0 贴边、点击 `pos_obsidian_asml_equipment` 后焦点切换且可见邻居 1 -> 3，社区标签点击切到 `chain_obsidian_ai_device_network:foundry`。
  - 当前验证（产业节点 canonical 修正）：前端图谱模型和后端质量中心统一使用 `chain_id:node_id` 作为产业链节点展示 ID，避免同一产业节点同时以裸 `node_id` 和 scoped `chain_id:node_id` 渲染成两个节点；当前 PostgreSQL AAPL 全局浏览器验收通过，`chain_node_splits=[]`、21 可见节点 / 44 可见边、29 完整图节点 / 52 完整图边、4 个社区标签、0 重叠、0 贴边、约 60 FPS，artifact 为 `artifacts/ui-graph-layout-canonical-chain-nodes-55662.json`。
  - 当前验证（结构化研报展示修正）：前端图谱模型开始消费 `/api/graph/query` 的 `structured_research_reports`，并用 `research_report_id` 连接 `report_viewpoints`，避免 API 已有研报/观点层但可视图断链；55664 当前代码 + Obsidian seed 浏览器验收通过，`raw_structured_reports=1`、visible node type 包含 `research`、28 可见节点 / 83 可见边、4 个社区标签、5 个产业节点、0 重叠、0 贴边、`chain_node_splits=[]`，artifact 为 `artifacts/ui-graph-layout-structured-research-55664.json`。
  - 当前限制：产业链三类关系和机构持有人网络已经通过受控浏览器 fixture + Obsidian seed 验证，并可通过 `scripts/graph_acceptance_fixture.py` / `scripts/seed_obsidian_knowledge_graph.py` 单独准备；当前 8000 端口上运行的旧 root 服务仍可能不是当前代码。下一步应把 seed 从“样本网络”继续推进到真实本地生产数据导入/增量更新。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；headless Chromium 默认可见文本探针；`python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-label-cleanup.json --timeout 45`；`python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55550 --output artifacts/ui-graph-relationship-filter-acceptance-smoke-2.json --timeout 60`。

- `DONE` T-567 全量关系图谱数据生产
  - 对应：E7-US1, E8-US2；T-566 生产化后续
  - 背景：T-566 已把样本知识网络和 Obsidian 式 UI 验收打通，但“所有股票”仍需要生产 universe 级别的可恢复图谱数据生成、覆盖率审计和缺口清单。
  - 目标：以当前本地生产 universe 为口径，覆盖 A 股当前活跃普通股和美股 current in-scope 标的；港股在没有完整 universe 前进入缺口报告，不计入完成率。
  - **已完成（本轮）**：新增 `app/service_modules/knowledge_graph_bulk.py`，提供全量 universe 选择、基础图谱层 dry-run/execute、上市证券关系幂等创建、缺失产业定位补位、readiness 汇总和缺口统计。
  - **已完成（本轮）**：新增 `scripts/backfill_full_knowledge_graph.py`，支持 `--audit-only`、`--dry-run`、`--execute`、`--market`、`--batch-size`、`--limit`、`--resume-state` 和 `--output`，写出 `artifacts/full-knowledge-graph/latest.json` 与可恢复 state。
  - **已完成（本轮）**：小批 PostgreSQL execute 写入 5 个样本并重复验证幂等；修复 bulk 默认产业节点共享导致的虚假全市场 peer 风险，已把样本 position 修回单 issuer scoped 节点。
  - **已完成（本轮）**：将逐股票 evidence-link graph 查询移到显式 `--include-evidence-links` 慢路径后，A/U 当前 in-scope universe 以 `--execute --batch-size 500 --resume` 完成全量基础图谱生产：`10626/10626` processed，`failed_count=0`，上市关系 issuer 覆盖 `10626/10626`，公司定位 issuer 覆盖 `10626/10626`。
  - **已完成（补齐）**：evidence-link 全量盘点完成，当前可由已有 document evidence 自动补齐的 event/relationship/viewpoint 缺口为 0，生成 `artifacts/full-knowledge-graph/evidence-link-audit.json`；`--include-evidence-links` 保留为后续慢路径。
  - **已完成（补齐）**：HK/H universe 盘点完成，当前 PostgreSQL store 中 HK/H securities 为 0、in-scope 为 0，生成 `artifacts/full-knowledge-graph/hk-universe-gap.json`，不伪造港股数据。
  - **已完成（补齐）**：UI 多股票抽样验收通过，`AAPL/MSFT/600519/000001/002078` 共 5 个 local graph case 全部 passed，artifact 为 `artifacts/ui-graph-multi-symbol-full-knowledge-acceptance-pass.json`。
  - 证据：`artifacts/full-knowledge-graph/final-summary.json` / `artifacts/full-knowledge-graph/latest.json`；状态：`artifacts/full-knowledge-graph/state.json`。
  - 当前边界：不新增数据库 schema，不改变 `/api/graph/query` schema；不物化 peer/upstream/downstream 派生边；不伪造事件、证据、研报或持仓，缺失层只记录 backfill action/readiness 缺口。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_dry_run_does_not_write tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_execute_is_idempotent tests.test_system.SystemServiceTests.test_query_graph_scopes_company_positions_to_focus_issuer tests.test_system.SystemServiceTests.test_full_knowledge_graph_universe_excludes_out_of_scope_and_reports_hk_gap tests.test_system.SystemServiceTests.test_full_knowledge_graph_script_writes_artifacts`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；`.venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 --audit-only --market A,U --limit 50`；`.venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 --dry-run --market A,U --limit 100 --batch-size 20`；`.venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 --execute --market A,U --limit 20 --batch-size 5`；`.venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 --execute --market A,U --batch-size 500 --resume`；A/U 样本图谱查询确认非空、上市关系和公司定位存在。

- `DONE` T-568 图谱质量验收、缺口看板与真实关系增强入口
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；T-566/T-567 生产质量闭环
  - 背景：T-567 已让 A/U 全量股票具备基础图谱骨架，但用户下一步需要知道每只股票图谱为什么浅、UI 是否仍可探索，以及如何把真实事件/关系补进图谱。
  - 目标：把“图谱数据质量闭环”“真实关系和事件增强”“图谱产品化验收”合并为一个可复验质量中心，输出缺口、质量门和可执行增强动作。
  - **已完成（本轮）**：新增 `app/service_modules/graph_quality_center.py`，按生产 universe 抽样调用 `query_graph` 与 `/api/graph/knowledge-network/readiness`，汇总每只股票的 layer gaps、cross-links、seed dependency、重复标签、raw label 泄漏、边密度和社区数。
  - **已完成（本轮）**：新增 `GET|POST /api/graph/quality-center`，`SystemService` 仅保留 facade，业务逻辑在领域模块内；接口固定 `automation_allowed=false`、`live_execution_allowed=false`。
  - **已完成（本轮）**：新增 `scripts/graph_quality_center.py`，默认输出 `artifacts/graph-quality-center/latest.json`；支持 `--run-enrichment` 调用已有事件/关系 builder，默认 dry-run；显式 `--execute` 才写入本地事件/关系候选；支持 `--browser-matrix` 复用多股票浏览器验收。
  - **已完成（本轮）**：真实事件/关系增强入口复用 `/api/company-database/events/build` 与 `/api/company-database/relationships/build`，只从本地行情、披露、研报覆盖、证据和股权表候选生成数据；候选默认 `needs_review`，不把研报观点提升为事实，不接外部收费源。
  - **已完成（本轮）**：修正 T-566 roadmap 重复状态，旧 DOING 口径统一为 DONE；T-568 作为后续质量闭环主任务。
  - 当前边界：质量中心不是新的事实抽取器；它只做编排、审计和调用已有 builder。不新增数据库 schema，不改变 `/api/graph/query` schema，不连接券商，不做真实交易。
  - **已完成（质量门修正）**：空目标 universe 不再返回 `passed`，而是 `status=no_targets`、`global_failures.target_universe`，CLI 非零退出，避免空图被误判为最佳展示。
  - **已完成（展示质量修正）**：质量中心 raw label gate 与前端语义标签清洗对齐，`market_data` 节点不再以 `md_public_eod...` 内部 ID 展示/验收，真实 PostgreSQL A/U 小样本 raw label 泄漏从 21 降为 0。
  - **已完成（浏览器验收修正）**：浏览器性能门槛改为结合 rAF FPS 与平均帧耗时判断，避免 headless 调度抖动误判；当前代码 PostgreSQL 服务对 `000001/AAPL` 多股票图谱验收通过，均为 42 节点/110 边、0 贴边、保存恢复通过。
  - **已完成（图谱降噪修正）**：SVG graph 将多日 `market_data` 明细聚合为每个证券一个“行情走势”节点，并对重定向后的重复边去重；K 线/行情表仍保留明细。真实 PostgreSQL 浏览器验收中 `000001/AAPL` 从 42 节点降至 35 节点、边降至 97/98、重叠降至 1/0、贴边 0。
  - **已完成（可见文本验收）**：浏览器布局验收新增 SVG/inspector/路径/轨迹/焦点栏 raw 文本泄漏检查；焦点栏改用当前节点语义标签，通用 `vp_rr_*` / `rr_*` ID 清洗为“研究观点/研报主题”，避免 hash ID 进入可见图谱。
  - **已完成（后端质量门对齐）**：`graph_quality_center` 的 raw label gate 同步支持通用 `vp_rr_*`、`rr_*`、`srr_*` 清洗，避免后端质量报告漏判或误判前端已语义化的观点/研报节点。
  - **已完成（展示质量门收紧）**：质量中心默认对重复展示标签和 raw label 泄漏采用 0 容忍，只有显式传 `max_duplicate_labels` / `max_raw_label_leaks` 才会放宽；55649 隔离服务严格门复验中 AAPL `quality_gate.status=passed` 且 `duplicate_labels=[]`、`raw_label_leaks=[]`，600519/600809/ASML 的失败保留为真实数据层 `layer_count` 缺口。
  - **已完成（质量中心 API 合同补齐）**：`docs/api-contracts.md` 增加 `GET|POST /api/graph/quality-center` 合同，明确 `max_duplicate_labels` / `max_raw_label_leaks` 默认 0、`quality_gate.structure/raw_structure`、`enrichment_runs` 和 `automation_allowed=false` / `live_execution_allowed=false` 边界；单测锁定合同片段，并补 GET route 阈值回归，避免 CLI/README/API 文档/路由再次漂移。
  - **已完成（质量门阈值契约收敛）**：质量中心结构/展示阈值集中到 `GraphQualityThresholds` 领域契约，`query_graph` filters 与 `quality_gate.thresholds` 共用同一解析结果；GET/query 字符串中的显式 `0` 不再被 `or default` 吃掉，避免诊断门槛与输出合同漂移。
  - **已完成（验收 fixture 边界收紧）**：`scripts/graph_acceptance_fixture.py` 创建的 `AAPL-P/AAPL-U/AAPL-D` 等本地浏览器验收证券标记为 `company_universe_scope=out_of_scope`，质量中心默认 production universe 不再采样 fixture-only 标的；55652 干净 SQLite 复验中质量中心 `skipped_by_market.U=3` 且样本不含 `AAPL-D`，完整关系过滤矩阵仍 11/11 通过。
  - **已完成（关系过滤验收契约加固）**：`scripts/ui_graph_relationship_filter_acceptance.py` 将依赖 `graph_acceptance_fixture` 的机构覆盖/Alpha 股东 case 标记为 fixture-only；`--skip-industry-fixture` 模式现在跳过这些 case 并输出 `skipped_cases`，避免用缺失前置数据的失败 artifact 误判图谱展示质量。55653 干净 SQLite 复验 skip 模式 `case_count=7`、`skipped_case_count=4`、`failure_count=0`。
  - **已完成（重复展示边质量门）**：质量中心新增 `max_display_duplicate_edges`，默认 0 容忍 UI 展示模型下的重复事实边；`max_duplicate_edges` 保留为 raw 底层结构诊断默认 4。验收 fixture 的 AAPL/NVDA/600519 上市关系 ID 改为复用 Obsidian seed ID，避免 seed+fixture 叠加生成重复 `listed_security` 展示边。55655 干净 SQLite 复验中 `display_duplicate_failures=0`，AAPL/MSFT/NVDA `quality_gate.status=passed`，关系过滤矩阵 11/11 通过。
  - **已完成（展示边去重口径修正）**：发现公司事件补齐后，质量中心把多日行情明细折叠为一个“行情走势”节点时仍按重定向前 20 条 `HAS_MARKET_DATA` 边统计 `display_duplicate_edges=19`。已修正 display structure 只统计实际可见去重后的普通展示边，同时继续对重复 `company_relationships` 事实边保持 0 容忍；55656 当前代码复验 20 样本 `display_duplicate_edges=0`，剩余失败仅为真实 `layer_count`。
  - **已完成（缺口动作精确化）**：质量中心 `enhancement_actions` 从固定推荐事件/关系 builder 改为按每只股票实际 `missing_layers/thin_layers` 生成补齐动作。当前 55657 PostgreSQL 20 样本已具备事件/关系/产业定位层，质量中心不再误推 `build_company_events` / `build_company_relationships`，而是 20/20 指向 `import_13f_holdings`、`ingest_source_documents`、`extract_and_link_evidence`、`structure_research_reports` 和 `structure_or_register_viewpoints`，与剩余真实缺口一致。
  - **已完成（展示结构质量门）**：质量中心新增展示结构快照和 raw 结构快照，展示结构会按 UI 口径聚合多日行情节点，再评估 hub dominance、leaf ratio、fragmentation、重复事实边和边类型分布；真实 PostgreSQL A/U 样本中 AAPL/600519 不再因 raw 行情明细 fan-out 被误判为星状展示，剩余失败集中在社区数和数据层缺口。
  - **已完成（关系标签质量门对齐）**：后端质量中心复用前端关系类型语义口径，`listed_security`、`customer_candidate` 等关系枚举在质量门中显示为“上市证券”“客户候选”，避免机器枚举绕过 raw label 检查后进入最佳展示验收。
  - **已完成（关系直连展示模型对齐）**：前端图谱构建 `company_relationships` 时优先使用 canonical `subject_id/object_id` 生成语义直连边，不再只依赖 `source_issuer_id/target_issuer_id`；质量中心 display structure 同步把 `HAS_COMPANY_RELATIONSHIP` / `RELATIONSHIP_SUBJECT` / `RELATIONSHIP_OBJECT` 三跳原始结构折叠为一条展示关系边，避免真实关系在 UI 中退化成数据库节点链。
  - **已完成（产业节点展示模型对齐）**：前端图谱和质量中心 display/raw structure 统一 `chain_id:node_id` 产业节点 identity，修复 `chain_nodes` 行与 `POSITION_IN_CHAIN_NODE` 边引用口径不一致导致的重复节点/断裂边；浏览器验收新增 `chain_node_splits` 0 容忍。
  - **已完成（结构化研报展示模型对齐）**：前端图谱模型消费 `structured_research_reports`，并用 `research_report_id` 连接结构化研报与 `report_viewpoints`；浏览器布局验收新增 `raw_structured_reports` 与 visible `research` 节点断言，质量中心回归覆盖 `REPORT_HAS_VIEWPOINT` 结构边。
  - **已完成（关系直连运行态复验）**：当前代码干净 SQLite 服务 `55640` 重新 seed 49 条 Obsidian 本地图谱样本后，AAPL/NVDA/600519 多股票浏览器矩阵通过：AAPL `36/88`、NVDA `33/75`、600519 `24/53`，均 0 重叠、0 贴边、保存恢复通过；AAPL 单图验收 36 节点/88 边、4 个可见社区、0 raw 文本泄漏、0 重叠、0 贴边、约 60 FPS/1.5ms。质量中心 artifact 确认 display structure 折叠出 `listed_security` 展示边，AAPL quality gate passed。
  - **已完成（13F 持仓标签去重）**：前端图谱和后端质量中心将 `institutional_holdings` 标签统一为“13F 持仓 · 申报方 / 标的 · 报告期”，避免同一机构持有多只股票时多个节点都显示裸机构名并触发重复标签或降低可读性。
  - **已完成（公司/证券同 ticker 标签消歧）**：后端质量中心将无 ticker 的 issuer 依次从 `aliases`、可读 `issuer_id`、`legal_name` 生成“代码 · 公司”标签，前端图谱同步使用 `aliases/legal_name` 兜底；AAPL 这类 issuer/security 同 ticker 不再展示为两个裸 `AAPL` 节点。
  - **已完成（派生关系算法债务收敛）**：新增 `app/service_modules/graph_derived_relationships.py`，把 `industry_peer/upstream_of/downstream_of` 派生产业链关系、`institutional_holder_key` 13F 同持有人网络和 `ownership_holder_key` 事实股东同持有人网络的计划生成从 `SystemService.query_graph` 大方法中抽出；planner 输出收紧为 dataclass 契约，`query_graph` 继续负责兼容性节点/边落地，API 输出不变，后续优化社区关系时不再直接堆进 `app/services.py` 或依赖隐式 dict key。
  - **已完成（图谱真实点击验收加固）**：`scripts/ui_graph_layout_acceptance.py` 的焦点切换验收从合成 `MouseEvent('click')` 升级为带坐标的 `PointerEvent('pointerdown')` + `pointerup` + click 链路，并新增 `focus_switch_pointer_chain` 失败项；当前代码 55648 隔离服务复验 AAPL 局部图通过，`focus_switch.pointer_checked=true`，36 节点/88 边、0 重叠、0 raw 文本泄漏，关系过滤矩阵 11/11 通过。
  - **已完成（样本数据补齐复验）**：发现当前 PostgreSQL store 的 `company_positions`/`company_relationships` 为 0 后，先执行 50 只 A 股基础图谱小批写入，并对 `600519/AAPL` 精确补齐 `listed_security` 与 `industry_position`；浏览器矩阵复验通过，AAPL 为 28 节点/38 边，600519 为 23 节点/35 边，均 0 重叠、0 贴边、保存恢复通过。
  - **已完成（当前库全量基础层修正）**：继续用可恢复 state 对当前 PostgreSQL A/U universe 执行基础图谱补齐，`state-display-quality.json` 达到 `5207/5207` completed、失败 0；数据库确认 `company_positions=5207`、`company_relationships=5207`、`industry_chains=4`。质量中心 50 样本基础层均为 `company_profile=1`、`industry_position=1`、`company_relationship=1`，剩余缺口集中在持仓、文档、证据、事件、研报和观点层。
  - **已完成（全量修正后浏览器复验）**：`000001/000002/600519/AAPL` 多股票浏览器矩阵全部通过；000001/000002 为 20 节点/31 边，600519 为 23 节点/35 边，AAPL 为 28 节点/38 边，均 0 重叠、0 贴边、保存恢复通过。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_enrichment_dry_run_does_not_write tests.test_system.SystemServiceTests.test_graph_quality_center_script_writes_artifact`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`。

- `DONE` T-569 图谱真实事件与关系批量增厚
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；T-568 后续
  - 背景：T-568 已能指出每只股票图谱缺哪些层，但仍需要一个批量 runner 把缺口转化为事件/关系候选生产计划和小批执行入口。
  - 目标：基于质量中心缺口，分批对 A/U 股票运行事件/关系 dry-run 或显式 execute，生成候选、统计候选数量、输出可恢复 state，并复验图谱缺口变化。
  - **已完成（本轮）**：新增 `app/service_modules/graph_enrichment_runner.py`，按 production universe 和 priority layers 选择需要增厚的股票，调用质量中心生成 before/after 缺口摘要。
  - **已完成（本轮）**：新增 `GET|POST /api/graph/enrichment-runner`，复用现有 `build_company_events` 和 `build_company_relationships`，不新增事实抽取器，不新增 schema。
  - **已完成（本轮）**：新增 `scripts/graph_enrichment_runner.py`，支持 `--audit-only`、`--execute`、`--market`、`--limit`、`--batch-size`、`--priority-layers`、`--resume` 和 `--resume-state`，默认输出 `artifacts/graph-enrichment-runner/latest.json` 与 state。
  - **已完成（技术债修正）**：dry-run state 不会把 issuer 标记为 completed，只有成功 execute 的行才进入 `completed_issuer_ids`，避免后续 `--execute --resume` 跳过只预览过的公司。
  - **已完成（本轮）**：`execute` 只写入本地事件/关系候选，关系候选默认 `review_status=needs_review`、`relationship_status=unknown`，结构化披露事件默认 `review_status=needs_review`；后续仍需审核队列提升为可信事实边。
  - **已完成（本轮）**：`knowledge_graph_bulk.select_full_graph_universe` 支持 `issuer_ids`、`security_ids` 和 `symbols` 精确过滤，便于质量中心和增厚 runner 对单 issuer 复验。
  - 当前边界：不连接外部收费数据，不把研报观点当事实，不自动审核候选，不接券商，不做真实交易。
  - **已完成（质量门修正）**：空目标 universe 返回 `status=no_targets` 并非零退出，避免增厚 runner 在无数据环境中误报完成。
  - **已完成（恢复语义修正）**：增厚 runner 现在输出 `candidate_activity`，若事件/关系 builder 没有任何 planned/created/review candidate，则行状态为 `no_candidate_sources`；即使 execute 报告返回，此类 issuer 也不会进入 CLI `completed_issuer_ids`，避免后续有新材料时被 `--resume` 跳过。
  - **已完成（性能与缺口口径修正）**：增厚 runner 默认 `quality_mode=fast`，用轻量层计数规划候选，完整质量中心改为显式 `--quality-mode full`；同时只对实际缺口层调用对应 builder，`company_relationship` 已存在时跳过关系 builder，除非显式 `--force-build`，避免当前全量库 dry-run 默认超时。
  - **已完成（事件小批增厚）**：当前 PostgreSQL 上 `--no-events` 关系路径 20 样本快速返回并全部跳过无缺口关系 builder；事件 dry-run 5 样本计划 5 个 review-gated 事件候选，`--execute --no-relationships` 小批写入 5 个事件。质量中心复验前 5 个样本 `company_event=1`，浏览器矩阵 `000001/000002/000004` 通过，分别为 22/21/21 节点、37/34/34 边，均 0 重叠、0 贴边、保存恢复通过。
  - **已完成（事件层增厚复验扩展）**：尝试 50 标的事件 execute 时客户端在 120 秒超时，未产生 runner report；服务端仍完成部分本地写入，后续质量中心 20 样本均已具备 `company_event=1`。当前代码 55656 复验质量中心 20 样本仅剩 `layer_count`，浏览器矩阵 `000001/000002/000004` 通过：22/21/21 节点、38/35/35 边，0 重叠、0 贴边、保存恢复 4。后续批量增厚继续使用小批 `--batch-size 5~20` 或提高 timeout，并优先补持仓、文档、证据、研报和观点层。
  - **已完成（剩余层增厚计划化）**：增厚 runner 新增 `layer_action_plan`、`manual_input_required_layers` 和 `waiting_for_source_inputs` 状态。事件/关系层仍可小批 dry-run/execute；`document/evidence/shareholder_holding/research_report/viewpoint` 不伪造写入，改为输出指向文档登记、证据抽取、13F/持仓导入、研报结构化和观点登记的机器可读计划。55658 当前 PostgreSQL dry-run 20 样本 `manual_input_required_count=20`，五个剩余层均被计划覆盖，失败 0。
  - **已完成（来源输入队列汇总）**：增厚 runner 顶层新增 `source_input_queue`，按图谱层汇总待补齐标的、endpoint、fallback/secondary endpoint、`required_source_fields`、跨层 `target_count` 和去重 `unique_target_count`，避免操作人员只能逐 item 翻 `layer_action_plan`。当前代码 55665 PostgreSQL dry-run 8 样本通过，`source_input_queue.status=needs_source_inputs`、5 层、8 个去重标的、40 个 layer-target 动作，五层均带来源字段要求；artifact 为 `artifacts/graph-enrichment-runner/source-input-queue-55665.json`。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_dry_run_plans_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_execute_writes_review_gated_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_respects_skip_issuer_ids tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_marks_completed_state`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/ui_static_check.py`；`python3 scripts/check_handoffs.py`；`git diff --check`。

- `DONE` T-486 公开行情 K 线板块
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：公司情报和知识图谱已经能展示关系与证据，但个人用户还需要直接查看证券价格走势，避免在研究时离开系统另找行情图。
  - 目标：在数据中台公开行情区域新增 K 线视图，复用已有本地 OHLCV 行情数据，并与证券点击/载入行情联动。
  - **已完成（本轮）**：新增原生 SVG K 线板块，展示蜡烛图、影线、收盘线、成交量、价格网格和日期刻度。
  - **已完成（本轮）**：新增最新收盘、区间涨跌、最高/最低和成交量摘要；`loadMarketData` 默认拉取最近 120 根并同时更新表格和 K 线。
  - **已完成（本轮）**：从总览、图谱或行情表点击证券仍会进入数据中台并自动载入对应 K 线。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器验证 K 线 SVG 非空并显示最新价格指标。

- `DONE` T-487 K 线均线系统
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：K 线首版能看价格走势，但缺少个人用户判断趋势常用的均线参照。
  - 目标：在公开行情 K 线板块新增常用均线系统，复用本地 OHLCV 收盘价，不引入外部行情依赖。
  - **已完成（本轮）**：新增 MA5、MA10、MA20、MA60 均线计算和 SVG 叠加线，价格坐标会纳入均线值范围。
  - **已完成（本轮）**：新增均线开关与最新均线值，用户可在不重新请求数据的情况下显示/隐藏不同周期均线。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器验证载入行情后 4 条均线和最新均线值正常，关闭单条均线后图表重绘。

- `DONE` T-488 K 线横截面误绘修复
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：公开行情证券输入为空时，接口返回最新交易日的多证券横截面；前端曾把这些不同证券的同日价格误画成单一证券时间序列，导致价格尖刺、横轴日期重复。
  - 目标：K 线只展示单一证券、多日期 OHLCV 时间序列；全市场横截面只进入表格，不进入 K 线图。
  - **已完成（本轮）**：证券输入默认使用 `sec_000670`，点击载入行情时空输入会回填样例证券，避免无意请求全市场横截面。
  - **已完成（本轮）**：`renderKlineChart` 新增单证券和多日期校验；多证券横截面或单日数据会显示空态提示，不再绘制误导性 K 线。
  - **已完成（本轮）**：静态 UI 契约新增防回归文本检查，覆盖单证券时间序列约束。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器验证空证券载入自动回填样例证券并显示正常日期横轴，同时直接传入横截面数据不会绘制 K 线。

- `DONE` T-489 K 线交互与周期切换
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：个人用户查看 K 线需要常规图表交互，包括拖动平移、放大缩小，以及日线/周线/月线/年线周期切换。
  - 目标：在不引入外部图表库的前提下，让现有 SVG K 线具备常规查看体验，并保持本地 OHLCV 数据边界。
  - **已完成（本轮）**：新增日线、周线、月线、年线周期切换；周/月/年由本地日线 OHLCV 聚合生成。
  - **已完成（本轮）**：新增图表窗口状态、放大、缩小、复位、鼠标/触控拖动平移和滚轮缩放。
  - **已完成（本轮）**：行情载入扩展到最近 1000 条以支持月线/年线聚合，表格仍只显示最近 120 条，避免页面过重。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器验证周期切换、缩放、拖动、复位和均线重绘正常。

- `DONE` T-490 全项目 UI 信息降噪第一阶段
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：公司情报、知识图谱、行情和总览仍有不少内部 ID、状态码、raw JSON 和流水记录直接进入个人用户主界面。
  - 目标：把默认界面收敛为个人研究视角，优先显示关键事实、研究判断、风险和下一步；追溯信息默认折叠在高级详情中。
  - **已完成（本轮）**：新增 `userEntityLabel`、`userStatusLabel`、`userSummaryLine`、`renderAdvancedTrace`、`renderInsightTable` 等共享展示规则。
  - **已完成（本轮）**：公司情报核心表改为“主题 / 关键发现 / 状态 / 下一步或证据”，研报、事件、行情、关系、模拟反馈不再以内部 ID 作为主列。
  - **已完成（本轮）**：知识图谱节点详情和关系/事实/决策表默认展示业务语义，内部节点 ID 与原始对象进入追溯详情。
  - **已完成（本轮）**：公开行情表改为日期、开高低收、成交量、来源，权限和记录 ID 进入高级详情；K 线交互保持不变。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；浏览器验证核心页面默认视图不以裸 `issuer_*`、`rr *`、`run_id` 作为主信息，高级详情仍可追溯。

- `DONE` T-491 全页面 UI 信息降噪收尾
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - 背景：T-490 已覆盖总览、公司情报、知识图谱和行情核心路径；瓶颈研究、智能体协作、复盘反馈、兼容审批、数据中台后台区、风控合规和公司情报高级维护区仍有裸 JSON、run/trace/manifest/id 作为默认主信息。
  - 目标：把剩余页面统一改成个人研究视角：默认展示事项、判断、状态、下一步；内部对象和原始 JSON 进入“高级详情 / 追溯信息”。
  - **已完成（本轮）**：新增 `renderReadableObjectSummary`、`renderAdvancedPre`、`renderActionableRows`，将裸 `<pre>` 输出改成摘要 + 折叠追溯。
  - **已完成（本轮）**：瓶颈研究、SEC 单标的、原文问答、热点扩散、兼容审批、组合模拟反馈、复盘报告、数据中台后台区、风控合规和公司情报高级维护区完成默认展示降噪。
  - **已完成（本轮）**：静态 UI 契约加入二阶段 helper 和追溯文本检查，防止回退到裸 JSON/调试视图。
  - 验收：`python3 scripts/ui_static_check.py`；`python3 -m py_compile app/*.py tests/*.py scripts/*.py`；`python3 scripts/check_handoffs.py`；`git diff --check`；浏览器逐页烟测 `/ui` 核心标签页 console error 为 0。

## 项目经理整理 / 长效完善与后端渐进式重构路线

项目经理口径：以下任务来自 2026-06-27 长效完善总计划，目标是把个人公司情报系统从“可用、能看”推进到“长期稳定、可信、可维护”。本路线把产品完善与后端渐进式重构绑定推进：先收敛当前成果，再围绕数据健康、个人研究桌面、真实验收、结论兑现、事件/关系可信度、前后端模块化和非本机生产化建立长期路线。后端不做大爆炸重写，继续保留 `SystemService` facade，按领域模块渐进抽取。所有任务继续遵守本地优先、公开/已提供数据优先、研报只进入观点层、模拟反馈 paper-only、不接真实券商、不自动下单边界。

- `DONE` T-492 文档/交接/工作树收敛与 GitHub 推送
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：PM / Release Coordination
  - 目标：把 T-480 至 T-491 的 UI、数据闭环、后端 API 变更、交接记录收敛成可提交状态。
  - 交付：更新文档索引任务范围；修正 T-490/T-491 handoff checklist；分组说明当前 dirty worktree；执行最终验证；提交并推送。
  - **已完成（本轮）**：PM 分组调用 Data/Evidence、Product/UI、Platform/Quality、Research/Workflow、Governance/Security 五组 agent，形成 T-493 至 T-503 的实施顺序与风险边界。
  - **已完成（本轮）**：修复 `scripts/daily_data_update_pipeline.py` 对旧调用方缺省 `personal_intelligence` 参数的兼容问题，恢复全量单测。
  - **已完成（本轮）**：完成 handoff、静态 UI、语法、安全、全量单测和 diff 检查；本任务提交并推送到 GitHub。
  - 后端关联：确认 `app/api.py`、`app/services.py`、新增脚本和 handoff 之间的任务状态一致，不在未收敛状态继续追加大重构。
  - 验收：`python3 scripts/check_handoffs.py`、`git diff --check`、`python3 scripts/ui_static_check.py`、`python3 -m py_compile app/*.py tests/*.py scripts/*.py` 通过；远端 GitHub 包含本轮变更。

- `DONE` T-493 数据自动刷新与来源健康中心
  - 对应：E3-US3, E3-US4, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence
  - 目标：解决“数据散乱、不自动、不知道哪里失败”的核心问题。
  - 交付：新增数据健康摘要，覆盖行情、研报、公告/披露、IR/官网材料、公司包导入、待补材料、调度状态、最近刷新时间、失败原因和下一步动作。
  - 后端重构：抽取 `data_health` / `source_health` 领域模块，`SystemService` 只保留 facade 方法；新增或复用健康摘要 API，不改变既有数据写入 schema。
  - UI：总览首屏增加“今日数据状态”；数据中台增加“来源健康中心”。
  - **已完成（本轮）**：新增只读 `GET|POST /api/data-health/runs/summary`，聚合 ingestion、公司补库、公司包导入、闭环刷新、本地材料、日更和个人关注池刷新 run，默认摘要化且不迁移 schema。
  - **已完成（本轮）**：新增只读 `GET|POST /api/data-health/summary`，按个人研究视角展示行情、研报、公告/披露、IR/官网材料、公司数据库和 paper-only 闭环反馈来源健康。
  - **已完成（本轮）**：总览首屏新增“今日数据状态”，数据中台新增“来源健康中心”，默认展示来源、当前判断、状态、下一步或证据，高级追溯折叠保留原始健康信号。
  - **已完成（本轮）**：新增 focused regression 覆盖 run family 聚合、来源健康状态、下一步动作、本地证据边界和 no-live-trading 标记。
  - 验收：每类来源能看到最新成功时间、失败数、待补数、下一次建议动作；无数据时给出可执行下一步。

- `DONE` T-494 个人研究桌面与后台维护拆分
  - 对应：E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI
  - 目标：把 `/ui` 从密集单页工具拆成“个人研究默认视图 + 后台维护视图”。
  - 交付：默认导航只保留总览、公司情报、知识图谱、K 线行情、研究结论、模拟反馈；导入、审计、复核、调度、治理进入“后台维护”。
  - 后端关联：梳理哪些接口属于 personal workspace，哪些属于 admin/maintenance；不改 URL，先在前端和权限矩阵中分组。
  - **已完成（本轮）**：`/ui` 新增“个人研究 / 后台维护”工作台模式，默认个人研究导航只保留总览、公司情报、知识图谱、K 线行情、研究结论和模拟反馈。
  - **已完成（本轮）**：数据中台、智能体协作、兼容审批、风控合规和公司高级维护仍使用原 tab/API/DOM 契约，但默认收敛到后台维护入口。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 增加工作台模式、维护模式和 `maintenance-only` 契约，防止回退到扁平调试导航。
  - 验收：个人用户首屏不需要理解 run、manifest、trace、调度、复核队列；高级能力仍可在后台找到。

- `DONE` T-495 真实浏览器验收矩阵补齐
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：Platform and Quality
  - 目标：把 UI 验收从静态契约升级到关键真实路径。
  - 交付：新增浏览器验收覆盖 AAPL、A 股样例、未知标的、K 线真实 API 加载、周期切换、拖拽缩放、图谱节点详情、数据健康中心、高级详情 HTML 转义。
  - 后端关联：建立 golden API payload 验收样例，覆盖公司情报、行情、图谱、模拟反馈和来源健康；为后续后端模块化提供行为基线。
  - **已完成（本轮）**：新增 `scripts/ui_research_workbench_matrix.py`，用本机 Chromium 真实浏览器覆盖个人研究默认视图、来源健康中心、A 股样例 K 线路径、真实 K 线 API 载入、周期切换、缩放、平移、AAPL 公司情报、未知标的空态、知识图谱节点详情和高级详情 HTML 转义。
  - **已完成（本轮）**：浏览器矩阵输出 `artifacts/t495-ui-research-workbench-matrix/ui-research-workbench-matrix.json`，明确 `local_only=true` 且 `acceptable_for_non_local_release=false`，不把本机 artifact 误标为生产证据。
  - **已完成（本轮）**：新增 focused regression，要求 T-495 必备场景、桌面/移动视口、local-only 边界和现有 cross-browser matrix 校验契约不退化。
  - 验收：新增验收脚本输出 local-only artifact；console error 为 0；失败时能定位页面、接口和断言。

- `DONE` T-496 结论兑现与模拟反馈评分增强
  - 对应：E5-US1, E6-US3, E7-US3；愿景扩展/生产化增强
  - Owner：Research and AI Workflows
  - 目标：让系统能回答“我的研究到底有没有用”。
  - 交付：为 `AnalysisConclusion` 和 `SimulationFeedback` 增加兑现状态、事件窗口收益、相对基准收益、最大回撤、预测错误归因、人工复盘评分和下一步建议。
  - 后端重构：抽取 `feedback_scoring` / `conclusion_realization` 领域模块；保持 paper-only、no-broker、no-auto-trading 边界集中可测。
  - UI：公司情报和复盘反馈页展示“结论兑现卡片”。
  - **已完成（本轮）**：新增 `app/service_modules/feedback_scoring.py`，把事件窗口收益、相对基准收益、最大回撤、兑现状态、预测错误归因、人工复盘评分占位和下一步建议封装为独立领域评分模块。
  - **已完成（本轮）**：`/api/simulation-feedback/performance/update` 保持 URL 和 payload 兼容，由 `SystemService` facade 调用评分模块并写回 `SimulationFeedback.performance`、`validation`、`review_result`，继续固定 `paper_only=true`、`live_execution_allowed=false`、`broker_connected=false`。
  - **已完成（本轮）**：公司情报页“模拟反馈与下一步”默认展示“结论兑现”行，显示窗口收益、相对基准、最大回撤和复盘动作，高级追溯保留完整反馈对象。
  - **已完成（本轮）**：新增 focused regression 覆盖结论、反馈、行情窗口、基准行情、兑现状态、错误归因和 paper-only 边界。
  - 验收：每条模拟反馈能回链到结论、行情表现、事件窗口和复盘判断；仍固定 `paper_only=true`。

- `DONE` T-497 公司事件/关系可信度、去重与归并增强
  - 对应：E3-US1, E5-US1, E7-US3；愿景扩展/生产化增强
  - Owner：Data and Evidence
  - 目标：提升公司事件和关系图谱可信度，减少重复和候选噪音。
  - 交付：事件去重、关系候选归并、同义实体归并、来源优先级、置信度解释、人工复核后提升为可信关系。
  - 后端重构：抽取 `company_quality` / `entity_resolution` 领域模块；研报观点不得直接提升为事实关系。
  - UI：事件/关系复核队列显示“为什么重要、证据来源、建议动作”。
  - **已完成（本轮）**：新增 `app/service_modules/company_quality.py`，集中来源质量评分、同义实体 key 归一、事件/关系候选判断、复核推荐、置信度解释和下一步动作。
  - **已完成（本轮）**：`SystemService` 保留现有方法和 API facade，将来源评分、候选推荐和实体归一委托给领域模块；现有质量归并、事件复核、关系复核 URL/payload 不变。
  - **已完成（本轮）**：质量归并、事件候选和关系候选 UI 默认展示“为什么重要、证据来源、建议动作”，内部追溯继续折叠保留。
  - **已完成（本轮）**：focused regression 锁定重复事件归并、关系同义实体归并、候选复核推荐解释字段、研报/观点来源降权和本地 no-live-trading 边界。
  - 验收：重复事件/关系能合并；高级详情保留原始追溯；事实层和观点层边界不退化。

- `DONE` T-498 前端模块化与 API 路由分组
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Platform and Quality
  - 目标：降低 `app/static/index.html` 和 `app/api.py` 持续膨胀带来的回归风险。
  - 前端交付：按 dashboard/company/graph/market/admin/helpers 分离静态前端模块；保持 `/ui` 路由和 DOM 契约兼容。
  - 后端交付：拆分 API route group 注册表，降低 `ApiRouter._resolve` 的 400+ 路由集中维护风险；`dispatch`、权限、trace、错误格式不变。
  - **已完成（本轮）**：新增 `app/api_routes.py`，将 `ApiRouter._resolve` 的巨型路由表迁移为 `build_route_table(owner)`，`dispatch`、鉴权、trace、错误格式和全部既有 API URL/method/payload 保持不变。
  - **已完成（本轮）**：新增 `app/static/ui_modules/manifest.json` 与 dashboard/company/graph/market/admin/helpers `.mjs` scaffold，记录前端拆分边界；当前 `runtime_loaded=false`，不改变 `/ui` inline 运行时。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 增加 UI 模块 scaffold 契约和 `.mjs` 语法检查；新增测试确保路由表不再内联在 `_resolve` 中。
  - 验收：UI 静态检查和浏览器验收不退化；所有既有 API URL、method、payload 不变。

- `DONE` T-499 非本机生产化准备包
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - Owner：Governance, Security, and Compliance
  - 目标：明确个人本机可用与组织级发布之间的差距。
  - 交付：认证授权、密钥治理、备份恢复演练、数据授权审计、staging/prod artifact URI、监控告警、发布门禁的任务拆分与证据模板。
  - 后端关联：梳理 local/staging/production 模式下 API 权限、trace、audit、secret、object store、search backend 的差异。
  - **已完成（本轮）**：新增 `docs/non-local-production-readiness-package.md`，用部署模式矩阵和证据模板明确本机个人使用、非本机 staging 和 production 的认证、权限、密钥、状态库、对象存储、检索/图谱、trace/audit、监控和 artifact URI 差异。
  - **已完成（本轮）**：新增 `scripts/non_local_production_readiness_check.py`，校验 T-499 准备包必须声明 local-first、paper-only、no-broker/no-auto-trading、拒绝 local-only evidence、必备证据字段和发布门禁命令。
  - 验收：不改变当前本机使用体验；非本机发布前置条件清晰，不把 local-only artifact 误标为 production evidence。

- `DONE` T-500 SystemService 公司情报主线模块化
  - 对应：E3-US4, E5-US1, E6-US4, E8-US2；愿景扩展/生产化增强
  - Owner：Platform and Quality
  - 目标：把 `SystemService` 从 3 万行级单体服务逐步拆成领域模块。
  - 第一批抽取：company database、market data、research reports、graph intelligence、simulation feedback。
  - 约束：保留 `SystemService` facade；不改 API schema；不做数据库迁移；不改变 UI 行为。
  - **已完成（本轮）**：新增 `app/service_modules/company_intelligence.py`、`market_data.py`、`research_reports.py`、`graph_intelligence.py`，并沿用已存在的 `feedback_scoring.py`，把公司情报主线中的确定性规则从 `SystemService` 抽出。
  - **已完成（本轮）**：`SystemService` 保留 facade helper 和 API 行为，委托模块处理符号匹配、完整度判断、行情复权因子、研报映射/观点摘要和图谱导出节点/关系转换。
  - **已完成（本轮）**：新增 focused regression，确认 facade helper 委托领域模块且 golden API baseline 不退化。
  - 验收：每批抽取前后 golden API payload 不变；全量单测和 UI 验收通过。

- `DONE` T-501 后端领域模块测试基线
  - 对应：E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：Platform and Quality
  - 目标：在真正拆后端前先锁定行为。
  - 交付：为公司情报、行情 K 线、知识图谱、研报结构化、模拟反馈、来源健康建立 focused regression。
  - **已完成（本轮）**：新增 `test_golden_api_behavior_baseline_for_backend_domain_refactor`，通过 `ApiRouter.dispatch` 锁定公司情报、公开行情、图谱、结构化研报、模拟反馈、performance dry-run、质量归并、来源治理和权限拒绝的 envelope/边界字段。
  - **已完成（本轮）**：基线采用字段断言而非完整 JSON fixture，避免 trace、timestamp、生成 ID 等易变字段导致脆弱快照。
  - 验收：重构前后响应字段、边界标记、trace/audit、paper-only 约束一致。

- `DONE` T-502 数据健康与调度 run 统一模型评估
  - 对应：E3-US4, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence, Platform and Quality
  - 目标：评估是否需要把 ingestion job、company build run、package import run、cycle run、material inbox run 统一成 run summary/read model。
  - 交付：先出 ADR，不直接迁移 schema；明确哪些 run 只需要视图聚合，哪些需要模型统一。
  - **已完成（本轮）**：新增 `docs/data-health-run-summary-adr.md`，决策为 aggregation-first read model，不做破坏性 schema 迁移。
  - **已完成（本轮）**：ADR 明确 ingestion、company build、package import、company intelligence cycle、material inbox、daily pipeline 和 personal refresh 等 run families、规范字段、来源健康映射和迁移触发条件。
  - 验收：ADR 能指导 T-493 数据健康中心实现，不引入破坏性迁移。

- `DONE` T-503 服务层增长冻结规则
  - 对应：E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：PM / Release Coordination, Platform and Quality
  - 目标：防止新功能继续直接堆进 `app/services.py`。
  - 交付：更新后端开发规则：新业务默认进入领域模块；`SystemService` 只做代理、兼容和跨模块编排。
  - **已完成（本轮）**：`AGENTS.md` 新增 `SystemService Growth Freeze` 规则，明确新业务默认进入领域模块，`SystemService` 仅保留 facade、兼容、跨模块编排和审计/权限/存储上下文。
  - **已完成（本轮）**：`docs/pr-checklist.md` 增加服务层 review gate；`scripts/check_handoffs.py` 要求触及 `app/services.py` 或 `SystemService` 的 handoff 必须包含 `SystemService Growth Freeze Review`。
  - 验收：`AGENTS.md` 或开发文档记录规则；后续任务 handoff 必须说明是否新增 `SystemService` 逻辑及原因。

- `DONE` T-504 公司主体多维关系图谱与动态探索
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：按公司为中心展示产业链位置、同类公司、上下游公司、股东/持有人和股东关联公司，解决公司情报逻辑线条不完整的问题。
  - 交付：不重建数据库；复用 `CompanyRelationship`、`CompanyPosition`、`IndustryChain`、`InstitutionalHolding` 和 `/api/graph/query`，新增公司情报聚合中的 `relationships.relationship_context` 派生视图。
  - **已完成（本轮）**：`app/service_modules/company_intelligence.py` 新增 `relationship_context` 领域聚合，输出产业链节点、同类、上下游、股东、股东关联公司、关系类型分组、动态图谱建议和 `database_rebuild_required=false` / `relationship_backfill_required=true` 数据策略。
  - **已完成（本轮）**：`/api/company-intelligence/{symbol}` 返回 `relationships.relationship_context`；图谱查询在公司中心视图中补充同一 13F 持有人关联公司的可展开边。
  - **已完成（本轮）**：公司情报页新增“多维关系”面板，展示同类、上游、下游、股东和股东关联计数与明细，高级追溯仍折叠保留完整对象。
  - **已完成（继续推进）**：公开披露关系候选抽取扩展到 `shareholder_candidate`、`controller_candidate`、`investee_candidate`；这些股权候选进入 `relationship_context.ownership.relationship_candidates` 并在“多维关系”面板显示，仍需人工复核后才能提升为事实关系。
  - **已完成（继续推进）**：“多维关系”明细行可直接跳入动态知识图谱；产业链、同类、上游、下游会携带 `chain_id`/`chain_node_id`，股权/关系候选会携带 `relationship_type`，`/api/graph/query` 支持按关系类型过滤公司关系子图。
  - **已完成（继续推进）**：关系 builder 新增 `structured_ownership_relationships` / `ownership_relationships` 本地结构化输入，可把 A 股十大股东、实控人、子公司和参股公司导入结果归一为 `shareholder_candidate`、`controller_candidate`、`subsidiary_candidate`、`investee_candidate`，默认 dry-run 且 `needs_review`，进入同一 `relationship_context.ownership.relationship_candidates`。
  - **已完成（继续推进）**：关系 builder 进一步支持 `ownership_csv`、`ownership_tsv`、`ownership_table_text` 和 `structured_ownership_tables`，可解析 CSV/TSV/Markdown 管道表，并将中文表头如 `股票代码`、`关系类型`、`股东名称`、`持股比例`、`报告期`、`来源` 归一为结构化股权候选输入。
  - **已完成（继续推进）**：关系 builder 支持 `ownership_file_paths` / `ownership_files` 从显式本地文件读取 ownership 表格，按 `ownership_root_path` 解析相对路径，限制扩展名、文件数量和单文件大小，并返回 `ownership_file_inputs` 解析摘要。
  - **已完成（继续推进）**：新增 `scripts/import_company_ownership_tables.py` 操作入口，可把本地 ownership CSV/TSV/TXT/MD 文件提交到关系 builder，支持显式 `--files`、`--glob` 目录扫描、JSON `--manifest` 和 `--write-manifest-template` 模板生成；未传 `--symbols` 时可从文件名/路径推断股票代码；默认 dry-run，显式 `--execute` 才写入待复核候选关系，并输出 `artifacts/company-ownership-table-import.json`。
  - 后续增强：接入更多真实 A 股十大股东、实控人、子公司/参股公司和交易所/年报股权结构属于数据源扩展，不阻塞当前多维关系链闭环；公开披露关系候选仍需人工复核后提升为事实关系。
  - 验收：`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_parses_local_ownership_tables tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_relationship_builder tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_infers_symbol_from_path tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_manifest_metadata tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_builds_manifest_template tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-505 公司多维关系链覆盖诊断
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence, Product and UI
  - 目标：让公司关系图谱不仅能展示已有关系，还能判断产业链、同类、上下游、股权和图谱边还缺哪一层，并给出下一步补齐动作。
  - **已完成（本轮）**：`relationship_context` 新增 `coverage_diagnostics` 和 `next_actions`，按产业链位置、同类公司、上游公司、下游公司、股权/控制关系、股东关联公司和动态图谱边输出覆盖状态、必补/增强属性、缺失层和建议动作。
  - **已完成（本轮）**：公司情报页“多维关系”面板优先显示缺失的关系链层级，把缺口直接转成用户可理解的补数据动作，已有关系明细仍可点击进入动态图谱。
  - **已完成（本轮）**：新增聚焦回归，覆盖完整关系样例 `coverage_score=1.0`，以及只有产业链定位但缺同类、上下游、股权和图谱边时返回 `missing_required_layers` 与 `relationship_backfill` 下一步动作。
  - 后续增强状态：已由 T-506 至 T-538 接到后台补库、ownership manifest、关系审核、图谱和增强动作入口；剩余仅为更多真实数据源接入。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-506 关系链缺口到补齐操作联动
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：把 T-505 的关系链缺口诊断从提示文本推进为可点击操作，让用户能从“缺什么”直接进入补齐、导入、图谱或审核入口。
  - **已完成（本轮）**：公司情报页“关系链缺口”行新增操作按钮，按缺口层级映射到现有能力：产业链/同类/上下游触发公司数据库补齐预览，股权/股东网络引导打开后台维护区的本地材料/ownership manifest 导入，图谱边打开关系图谱，候选审核可进入关系复核队列。
  - **已完成（本轮）**：新增 `runRelationshipBackfillAction` 前端执行函数，复用现有 `buildCompanyDatabaseBatch`、`openRelationshipGraphContext`、`renderCompanyRelationshipReview` 和后台维护区，不新增后端接口、不迁移 schema。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 纳入 `runRelationshipBackfillAction` 和 `data-action="run-relationship-backfill-action"`，防止后续回退成只读提示。
  - 后续增强状态：已由 T-507 至 T-511 提供 UI 原生入口、manifest 预览、导入预览、执行和候选审核队列闭环。
  - 验收：`python3 scripts/ui_static_check.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`、`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-507 股权表导入工作台入口
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：把股权/股东关系缺口补齐从脚本和提示推进到浏览器内可预览、可执行的受控入口。
  - **已完成（本轮）**：公司情报后台维护区新增“股权表导入”表单，支持填写本地股权表目录、文件列表和默认关系类型，调用现有 `/api/company-database/relationships/build` 的 `ownership_file_paths` 路径，默认 dry-run。
  - **已完成（本轮）**：股权表导入结果展示解析文件数、候选关系数、目标公司数、文件错误和 usage boundary；执行后刷新公司情报并进入关系候选审核队列，所有关系仍为 `needs_review` 候选。
  - **已完成（本轮）**：T-506 的股权缺口动作现在直接触发股权表导入预览，而不是只提示进入后台维护区。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 纳入新增 DOM、函数和按钮契约；API 文档说明公司情报工作台的股权表导入入口复用同一关系 builder。
  - 后续增强状态：已由 T-508 至 T-510 提供 ownership manifest 浏览器生成、导入预览和真实浏览器验收。
  - 验收：`python3 scripts/ui_static_check.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`、`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-508 股权表 manifest 模板生成工作台入口
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：让用户可以在浏览器内扫描本地股权表目录并生成可编辑 ownership manifest，不再必须手动运行 CLI。
  - **已完成（本轮）**：新增 `POST /api/company-database/ownership/manifest-template`，复用 `company_intelligence` 领域模块的文件发现、路径股票代码推断和 manifest 模板生成逻辑；默认 dry-run，只在 `execute=true` 且提供 `output_path` 时写入本地 JSON。
  - **已完成（本轮）**：公司情报后台维护区新增股权 manifest glob、输出路径、预览和写入按钮，结果表展示文件、推断代码、默认类型和来源字段。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 覆盖新增 DOM 和函数；API 文档记录新接口字段、返回结构和本地边界。
  - 后续增强状态：已由 T-509 至 T-510 完成 manifest 到导入预览闭环和真实浏览器验收。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_ownership_manifest_template_api_previews_and_writes tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`、`python3 scripts/ui_static_check.py`、`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-509 股权 manifest 到导入预览闭环
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：把 T-508 生成的 ownership manifest 直接串到 T-507 的股权表导入预览，形成浏览器内“扫描目录 -> 生成 manifest -> 预览候选关系”的连续路径。
  - **已完成（本轮）**：前端保存最近一次 `latestCompanyOwnershipManifestTemplate`，股权导入 payload 可直接使用 manifest 中的 `file_path`、`default_kind`、`source_id` 和 `source_table`。
  - **已完成（本轮）**：新增“用 manifest 预览导入”按钮；如果尚未生成模板，会先 dry-run 生成 manifest，再用模板文件项调用 `/api/company-database/relationships/build` 预览候选关系。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 纳入新按钮和 `previewCompanyOwnershipImportFromManifest` 函数，防止回退为两个割裂步骤。
  - 后续增强状态：已由 T-510 至 T-511 覆盖真实浏览器验收和候选审核队列刷新。
  - 验收：`python3 scripts/ui_static_check.py`、`python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`、`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-510 股权 manifest 到导入真实浏览器验收
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：用真实浏览器点击验证 T-508/T-509 的连续链路，确保用户在工作台内填写本地股权表目录后，可以预览 manifest 并直接用 manifest 预览股权候选关系。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 创建本地 CSV fixture，真实点击公司情报页后台维护区的 ownership manifest 预览按钮，并断言文件数、SPCX 模板行和操作摘要。
  - **已完成（本轮）**：同一浏览器会话继续点击“用 manifest 预览导入”，通过真实 API 调用 `/api/company-database/relationships/build`，断言股权导入状态、候选数、解析结果行和操作摘要。
  - **已完成（本轮）**：失败诊断新增 ownership manifest/import 状态与行内容，后续定位 UI 或 API 断点时不用只看全量页面截图。
  - 后续增强状态：已由 T-511 纳入隔离数据目录的执行态浏览器验收。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8771 --output-dir artifacts/ui-interaction-acceptance-t510 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-511 股权导入执行到候选复核队列闭环
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI, Data and Evidence
  - 目标：把“股权表执行导入”后的结果直接推进关系候选复核队列，形成“扫描目录 -> manifest -> 预览候选 -> 执行导入 -> 复核候选”的完整浏览器链路。
  - **已完成（本轮）**：`build_company_relationships` 执行或 dry-run 后返回 `relationship_review_candidates` 和 `relationship_review_candidate_count`，每条候选带 `review_recommendation`，前端无需再从全量公司情报聚合里猜测新候选。
  - **已完成（本轮）**：`renderCompanyRelationshipReview` 兼容数组、`{relationships:{company_relationships}}`、`{company_relationships}` 和 API 列表 payload，修复执行导入后传数组导致候选队列为空的问题。
  - **已完成（本轮）**：`runCompanyOwnershipImport` 在已有 manifest 且未填写显式文件列表时复用最近 manifest 输入；执行后直接渲染后端返回的候选复核队列，再刷新公司情报。
  - **已完成（本轮）**：真实浏览器验收新增 `company_ownership_import_execute_refreshes_review_queue`，覆盖点击执行导入后股权候选 `Alpha Capital` 出现在关系复核队列且具备通过按钮。
  - 后续增强状态：已由 T-512 纳入“批准 -> 关系图谱 active 边可见”浏览器验收。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`、`python3 scripts/ui_static_check.py`、`python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8772 --output-dir artifacts/ui-interaction-acceptance-t511 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-512 股权候选批准到事实图谱边闭环
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence, Product and UI
  - 目标：把人工批准的股权候选从 `*_candidate` 提升为事实型公司关系，并验证它能在关系图谱中按事实关系类型展开。
  - **已完成（本轮）**：`review_company_relationship(... action=approve)` 对 `shareholder_candidate`、`controller_candidate`、`subsidiary_candidate`、`investee_candidate` 等候选统一去掉 `_candidate` 后缀，保留 `metadata.candidate_relationship_type` 和 `metadata.promoted_relationship_type`，同时设置 `approved/active`。
  - **已完成（本轮）**：单测覆盖本地股权表导入后的 `shareholder_candidate` 被批准为 `shareholder`，旧 `shareholder_candidate` 图谱过滤不再返回该关系，`relationship_type=shareholder` 图谱过滤返回 active 边。
  - **已完成（本轮）**：真实浏览器验收新增“通过股权候选 -> 公司情报刷新后存在 active shareholder -> 打开 shareholder 关系图谱并看到非空图谱边”的链路。
  - 后续增强状态：已由 T-513、T-514、T-515 和 T-540 区分候选/事实股权，并提供事实股东网络扩展入口。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates`、`python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8773 --output-dir artifacts/ui-interaction-acceptance-t512 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-513 多维关系面板区分事实股权与候选股权
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence, Product and UI
  - 目标：让公司情报页的多维关系不再把已批准股权事实显示成“股权候选”，而是明确区分事实股权关系和待复核候选。
  - **已完成（本轮）**：`relationship_context.ownership` 新增 `approved_relationships`、`relationship_candidates` 和兼容汇总 `relationships`；summary 新增 `approved_ownership_relationships` 与 `ownership_candidates`。
  - **已完成（本轮）**：已批准且 active 的 `shareholder` / `controller` / `subsidiary` / `investee` 等事实股权关系进入 `approved_relationships`；仍为 `*_candidate`、`needs_review` 或 `candidate_status=candidate` 的关系进入 `relationship_candidates`。
  - **已完成（本轮）**：公司情报“多维关系”面板新增“事实股权关系”行，点击可进入对应事实关系图谱；“股权候选”继续保留人工复核提示。
  - **已完成（本轮）**：浏览器验收在批准 Alpha Capital 后断言 `relationship_context.ownership.approved_relationships` 包含 active `shareholder`，候选列表为空，且面板显示“事实股权关系”。
  - 后续增强状态：已由 T-514、T-515、T-519、T-527、T-528 和 T-540 覆盖事实股东网络扩展和诊断汇总；更细的候选/事实评分校准可作为后续质量调参。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links`、`python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8774 --output-dir artifacts/ui-interaction-acceptance-t513 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-514 事实股东关联公司二跳聚合
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Data and Evidence, Product and UI
  - 目标：当看到某家公司和已批准股东关系时，能回答“该股东还有哪些公司”，并在多维关系面板中展示同一事实股东关联的其他公司。
  - **已完成（本轮）**：`relationship_context` 新增全量 `CompanyRelationship` 只读输入，用焦点公司已批准 ownership fact 的 `object_id/entity_name` 作为股东 key，扫描其他已批准 active ownership fact，输出 `ownership.approved_shareholder_related_companies`。
  - **已完成（本轮）**：summary 新增 `approved_shareholder_related_companies`；原 `shareholder_related_companies` 继续代表 13F/持仓记录推导，避免混淆数据来源。
  - **已完成（本轮）**：公司情报多维关系面板新增“事实股东关联”，展示“同一股东还关联哪些公司”，点击可按事实关系类型展开图谱。
  - **已完成（本轮）**：浏览器验收用同一 CSV 导入 SPCX 和 DEMO 的 Alpha Capital 股东关系，批准后断言 approved relationship、候选清空、事实股权关系和事实股东关联均显示。
  - 后续增强状态：已由 T-515、T-519、T-521、T-527 和 T-528 纳入事实股东网络诊断、holder-key 过滤和 UI 追溯。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship`、`python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8775 --output-dir artifacts/ui-interaction-acceptance-t514 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-515 同一事实股东网络图谱过滤
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Research and AI Workflows, Product and UI
  - 目标：从“事实股东关联”行点击进入动态图谱时，不只按关系类型展开焦点公司，而是按同一已批准股东/持有人 key 展开跨公司事实股东网络。
  - **已完成（本轮）**：`/api/graph/query` 新增 `ownership_holder_key` 过滤；带该过滤时只返回同一 holder key 的 active、非候选、已批准/已复核/自动生成 ownership fact，并把跨公司关系挂回各自 issuer。
  - **已完成（本轮）**：`relationship_context.ownership.approved_shareholder_related_companies` 暴露 `holder_key`；公司情报多维关系面板“事实股东关联”点击图谱时携带 `ownership_holder_key`。
  - **已完成（本轮）**：API 合同记录 holder-key 图谱过滤边界，明确 `*_candidate` 不进入事实股东网络。
  - **已完成（继续推进）**：真实浏览器验收新增 `company_ownership_holder_key_graph_click_loads_same_holder_network`，用 UI/API fixture 建立 DEMO 与 SPCX 的同一 Alpha Capital 已批准事实股东关系，载入 SPCX 的“事实股东关联”，再按 `ownership_holder_key=external_company_alpha_capital` 渲染图谱并断言两家公司关系边均进入 graph raw。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`、`python3 -m py_compile app/services.py app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t516 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-516 图谱当前过滤条件可见化
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI
  - 目标：用户从多维关系面板跳入图谱后，能直接看到当前图谱是按主体、关系类型、产业链节点或同一事实股东 key 过滤出来的，避免误以为是全量关系图。
  - **已完成（本轮）**：关系图谱工具栏新增 `knowledgeGraphFilterChips`，默认显示“全部关系”，带过滤条件时显示主体、证券、关系类型、产业链、产业节点和股东 holder key。
  - **已完成（本轮）**：`loadEntity` 会把本次 `/api/graph/query` 的 `relationship_type`、`chain_id`、`chain_node_id`、`ownership_holder_key` 等查询上下文写入图谱状态；图谱重渲染时保持 chip 可见。
  - **已完成（本轮）**：真实浏览器验收断言 shareholder 关系图显示“关系类型: shareholder”，holder-key 网络图显示“股东: external company alpha capital”。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t516 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-517 图谱股东过滤 chip 可读名
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI
  - 目标：同一事实股东网络图谱仍按稳定 holder key 查询，但界面 chip 显示用户能读懂的股东名，例如 `股东: Alpha Capital`，不再只暴露 `external_company_alpha_capital`。
  - **已完成（本轮）**：`openRelationshipGraphContext` 和 `knowledgeGraphState.activeFilters` 支持 `ownershipHolderLabel`；`renderKnowledgeGraphFilterChips` 在 holder-key 过滤时优先展示 label，查询仍使用 `ownershipHolderKey`。
  - **已完成（本轮）**：“事实股东关联”行新增 `data-ownership-holder-label`，从 `approved_shareholder_related_companies.holder_name` 传递到图谱过滤 chip。
  - **已完成（本轮）**：浏览器验收断言 holder-key 图谱 chip 显示 `Alpha Capital`，并且不显示 raw `external_company_alpha_capital`。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t517 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-518 图谱过滤 chip 追溯属性
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - Owner：Product and UI
  - 目标：图谱过滤 chip 对用户显示可读名，同时保留 raw filter key/value 供审计、排错和自动化验收追溯。
  - **已完成（本轮）**：`renderKnowledgeGraphFilterChips` 为每个 chip 增加 `data-filter-key`、`data-filter-raw-value` 和 `title="过滤追溯: key=value"`；holder-key chip 继续显示 `Alpha Capital`。
  - **已完成（本轮）**：浏览器验收断言 holder-key chip 不显示 raw key，但 DOM `data-filter-raw-value` 与 title 均保留 `external_company_alpha_capital`。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t518 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-519 事实股东网络覆盖诊断拆分
  - 对应：E3-US1, E5-US1, E7-US1；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：`relationship_context.coverage_diagnostics` 区分 13F/持仓同一持有人网络与已批准事实股东网络，避免“股东关联公司”口径混淆。
  - **已完成（本轮）**：`coverage_diagnostics.diagnostics` 新增可选层 `approved_shareholder_network`，使用 `summary.approved_shareholder_related_companies` 计数；原 `shareholder_network` 标签调整为 13F/持仓口径并继续使用 `summary.shareholder_related_companies`。
  - **已完成（本轮）**：关系上下文缺口动作把 `approved_shareholder_network` 归入股权表导入/复核引导；API 合同补充两个股东网络诊断层的来源口径。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers`、`python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-520 关系链缺口来源口径可见化
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：关系链缺口不只告诉用户缺哪一层，还要展示系统凭哪些来源口径判断该层缺失，避免 13F、事实股权、产业链定位等来源混淆。
  - **已完成（本轮）**：公司情报“关系链缺口”行在 `finding` 中展示 `来源: diagnostics.evidence`，例如 `CompanyPosition + IndustryChain`、`same-holder InstitutionalHolding records`、`approved active ownership CompanyRelationship records`。
  - **已完成（本轮）**：缺口操作按钮增加 `data-evidence`，静态契约纳入该追溯属性；API 合同说明 `diagnostics[].evidence` 会进入 UI 缺口行和按钮属性。
  - 验收：`python3 -m py_compile scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-521 动态图谱 holder-key 过滤契约补齐
  - 对应：E3-US1, E5-US1, E7-US1；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：让 `relationship_context.dynamic_graph` 自描述真实反映同一事实股东网络可按 `ownership_holder_key` 展开，避免 API 消费方只看到 UI 能力却看不到推荐过滤键。
  - **已完成（本轮）**：`dynamic_graph.recommended_filters` 新增 `ownership_holder_key`，与 `/api/graph/query` holder-key 过滤和“事实股东关联”图谱入口保持一致。
  - **已完成（本轮）**：同股东网络回归断言 `ownership_holder_key` 出现在 recommended filters；API 合同补充动态图谱推荐过滤键列表。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-522 动态图谱推荐查询自描述
  - 对应：E3-US1, E5-US1, E7-US1；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：`relationship_context.dynamic_graph` 不只声明可用过滤键，还要输出当前公司可直接执行的图谱查询建议，方便 UI、脚本或后续 agent 连续展开关系链。
  - **已完成（本轮）**：`dynamic_graph.recommended_queries[]` 新增 `{label, query, reason}` 结构，覆盖公司中心图、产业链节点图、关系类型图和同一事实股东网络图。
  - **已完成（本轮）**：同股东网络回归断言 recommended queries 包含 `issuer_id=issuer_001` 以及 `relationship_type=shareholder + ownership_holder_key=external_company_alpha_capital` 的查询；API 合同记录 recommended queries 结构和用途。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-523 图谱推荐查询前端入口
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：把 T-522 的 `dynamic_graph.recommended_queries[]` 从 API/高级追溯推进到公司情报多维关系表里的可见、可点击入口。
  - **已完成（本轮）**：公司情报“多维关系”表新增“图谱推荐入口”行，显示推荐查询的 `label`、`reason`，点击后复用 `open-relationship-graph` 并携带 `issuer_id`、`security_id`、`relationship_type`、`chain_id`、`chain_node_id`、`ownership_holder_key`。
  - **已完成（本轮）**：新增 `recommendedGraphQueryAttrs` 前端 helper，静态契约纳入该函数；API 合同说明 UI 会渲染推荐图谱入口。
  - 验收：`python3 -m py_compile scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-524 图谱推荐入口真实浏览器验收
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：为 T-523 的“图谱推荐入口”补真实浏览器点击验收，证明它不是只存在于静态 DOM，而能打开同一事实股东网络。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增 `company_recommended_graph_query_click_loads_holder_network`，在构造 SPCX/DEMO 同一 Alpha Capital 已批准事实股东关系后，点击“图谱推荐入口”行并断言 holder-key 图谱过滤 chip、raw holder key 和两条事实股东关系都进入图谱。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t524 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-525 股东关联摘要计数口径修正
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：公司情报多维关系顶部“股东关联”摘要计数同时反映已批准事实股东网络和 13F/持仓网络，避免表格里有“事实股东关联”但顶部仍显示 0 的口径错位。
  - **已完成（本轮）**：`companyIntelShareholderRelatedCount` 改为显示合计以及 `事实 N / 持仓 M` 分项，合计来源为 `summary.approved_shareholder_related_companies + summary.shareholder_related_companies`。
  - **已完成（本轮）**：静态契约纳入“事实 / 持仓”表达式；浏览器验收在同一 Alpha Capital 事实股东网络上下文中断言顶部计数包含 `事实 1`。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t525 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-526 股东关联合计进入 API summary
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：把 T-525 的股东关联合计口径从前端表达式沉淀到 `relationship_context.summary`，让 API/UI/脚本消费方共享同一合计字段。
  - **已完成（本轮）**：`summary.shareholder_related_companies_total` 新增为 `approved_shareholder_related_companies + shareholder_related_companies`；前端顶部“股东关联”优先读取该合计字段，保留旧字段回退。
  - **已完成（本轮）**：单测分别覆盖 13F/持仓网络样例和已批准事实股东网络样例的 total；API 合同记录该字段和 UI 使用方式。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-527 覆盖诊断股东网络汇总口径
  - 对应：E3-US1, E5-US1, E7-US1；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：`coverage_diagnostics` 在保留 13F/持仓网络与已批准事实股东网络分项诊断的同时，提供统一股东网络覆盖汇总，和 `summary.shareholder_related_companies_total` 口径一致。
  - **已完成（本轮）**：`coverage_diagnostics.shareholder_network_summary` 新增 `total`、`fact_network`、`holding_network`、`available` 和 `source_layers`，用于统一判断“股东还有哪些公司”这一逻辑线是否有任何来源覆盖。
  - **已完成（本轮）**：单测覆盖 13F-only 样例返回 `fact_network=0/holding_network=1/total=1`，以及事实股东网络样例返回 `fact_network=1/holding_network=0/total=1`；API 合同记录该汇总块。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-528 股东网络覆盖汇总 UI 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：把 T-527 的 `coverage_diagnostics.shareholder_network_summary` 从 API 追溯推进到公司情报 UI，让顶部“股东关联”计数可以被自动化和人工追溯到事实/持仓分项。
  - **已完成（本轮）**：`companyIntelShareholderRelatedCount` 增加 `data-network-total`、`data-fact-network`、`data-holding-network` 和 title，来源优先使用 `coverage_diagnostics.shareholder_network_summary`，回退到 summary 分项。
  - **已完成（本轮）**：静态契约纳入 `shareholderRelatedElement.dataset.networkTotal`；浏览器验收断言同一 Alpha Capital 事实股东网络下 `data-fact-network=1`、`data-network-total=1` 且 title 包含“股东网络覆盖”。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t528 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-529 产业链关系汇总口径
  - 对应：E3-US1, E5-US1, E7-US1；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：为产业链关系线提供和股东网络类似的合计口径，让 API 消费方可以直接判断同类、上游、下游整体覆盖，而不需要自行相加。
  - **已完成（本轮）**：`summary.industry_related_companies_total` 新增为 `peer_companies + upstream_companies + downstream_companies`；`coverage_diagnostics.industry_network_summary` 新增 `total`、`peers`、`upstream`、`downstream`、`chain_nodes`、`available` 和来源层。
  - **已完成（本轮）**：单测覆盖完整样例 `total=3/peers=1/upstream=1/downstream=1/chain_nodes=1`，以及稀疏样例 `total=0/available=false/chain_nodes=1`；API 合同记录该字段和汇总块。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-530 产业链关系摘要 UI 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：把 `coverage_diagnostics.industry_network_summary` 接到公司情报多维关系顶部“同类/上游/下游”计数，形成可追溯的产业链关系摘要。
  - **已完成（本轮）**：`companyIntelPeerCount`、`companyIntelUpstreamCount`、`companyIntelDownstreamCount` 增加 `data-network-total`、`data-network-part`、`data-chain-nodes` 和 title，来源优先使用 `industry_network_summary`，回退到 summary 字段。
  - **已完成（本轮）**：静态契约纳入 `setIndustryNetworkTrace`；API 合同说明 UI 追溯属性。
  - 验收：`python3 -m py_compile scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-531 产业链关系行级追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI
  - 目标：让公司情报“产业链位置 / 同类公司 / 上游公司 / 下游公司”每一行都能追溯到链条、节点和方向，方便动态图谱点击、自动化验收和人工排查。
  - **已完成（本轮）**：新增 `industryRelationshipTraceAttrs`，在产业链位置、同类、上游、下游关系行写入 `data-industry-relationship`、`data-industry-direction`、`data-chain-id`、`data-chain-node-id`、`data-chain-node-ids`、`data-chain-node-label` 和 `data-position-id`。
  - **已完成（本轮）**：静态契约纳入 `industryRelationshipTraceAttrs` 和 `data-industry-direction`；API 合同记录产业链行级追溯属性。
  - **已完成（本轮）**：浏览器验收新增 `company_industry_relationship_rows_have_trace_attrs`，用自包含关系上下文 fixture 断言同类/上游/下游/产业链位置行的追溯属性真实渲染到 DOM。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t531 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-532 13F 持有人网络动态图谱展开
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：让 13F/持仓同一持有人网络和已批准事实股东网络一样，可以从公司情报“股东关联公司”行点击进入动态图谱，回答“该持有人还持有哪些公司”。
  - **已完成（本轮）**：`relationship_context.ownership.shareholders` 与 `shareholder_related_companies` 增加标准化 `holder_key`；`dynamic_graph.recommended_filters` / `recommended_queries` 增加 `institutional_holder_key`。
  - **已完成（本轮）**：`/api/graph/query` 支持 `institutional_holder_key` / `institutionalHolderKey` / `13f_holder_key`，按同一 13F/持仓持有人展开跨公司 `HAS_13F_HOLDING`、`HOLDS_SECURITY` 和 `SAME_HOLDER_RELATED_COMPANY` 边。
  - **已完成（本轮）**：公司情报“股东关联公司”行写入 `data-institutional-holder-key` / `data-institutional-holder-label`；图谱过滤 chip 增加“13F持有人”，保留 raw key 追溯；holder-key 跨公司图谱不再默认带当前证券过滤。
  - **已完成（本轮）**：浏览器验收新增 `company_13f_holder_graph_click_loads_same_holder_network`，在干净本地 SQLite/object-store 服务上 38/38 通过。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t532-clean --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-533 图谱推荐入口优先展示具体二跳网络
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows
  - 目标：确保“图谱推荐入口”优先展示同一事实股东和同一 13F 持有人这类具体二跳网络，避免被泛化关系类型推荐挤出前 8 条 UI 展示范围。
  - **已完成（本轮）**：`dynamic_graph.recommended_queries[]` 生成顺序调整为公司中心、产业链节点、同一事实股东、同一 13F 持有人，再到泛化关系类型。
  - **已完成（本轮）**：浏览器验收新增 `company_recommended_13f_holder_graph_query_click_loads_network`，证明 13F 持有人网络可以从“图谱推荐入口”点击进入动态图谱，而不只依赖“股东关联公司”普通行。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t533 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-534 关系链缺口完整可见性
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：确保多维关系诊断里的每个必补缺口层都能进入 API `next_actions` 和公司情报 UI 缺口行，避免只显示前几项导致用户看不到完整补齐路径。
  - **已完成（本轮）**：`relationship_context.coverage_diagnostics.next_actions` 不再截断为前 5 条，而是覆盖全部 `missing_required_layers`。
  - **已完成（本轮）**：公司情报“关系链缺口”行不再只显示前 4 个缺口，所有未覆盖层都会渲染缺口行、来源口径和补齐按钮。
  - **已完成（本轮验收）**：后端回归断言 `relationship_context.next_actions` 的 layer 集合与 `missing_required_layers` 完全一致；浏览器验收新增 6 个缺口层 fixture，断言所有缺口按钮都渲染，并能分流到补齐预览、股权导入引导和图谱入口。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t534 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-535 关系链可选增强动作 API 自描述
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows, Product and UI
  - 目标：让 13F/持仓股东网络和事实股东网络等可选增强层也有机器可读补齐动作，避免 API 消费方只能从 `diagnostics` 文案里猜下一步。
  - **已完成（本轮）**：`relationship_context.coverage_diagnostics.enhancement_actions` 新增为全部 `missing_optional_layers` 的动作列表，动作类型为 `relationship_enhancement`。
  - **已完成（本轮）**：外层 `relationship_context.enhancement_actions` 同步透出，和 `next_actions` 分工明确：必补层走 `relationship_backfill`，增强层走 `relationship_enhancement`。
  - **已完成（本轮验收）**：后端回归断言 `enhancement_actions` 的 layer 集合与 `missing_optional_layers` 完全一致，并且全部 action 为 `relationship_enhancement`。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-536 关系链补齐动作目标入口自描述
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows, Product and UI
  - 目标：让 `next_actions` 和 `enhancement_actions` 不只说明缺什么，还要带可路由目标入口，方便脚本、UI 和后续 agent 直接知道该调用补库、股权导入/复核还是图谱查询。
  - **已完成（本轮）**：每条关系链 action 新增 `target` 块，包含 `target_type`、`endpoint`、`method`、`ui_action`、`default_execute=false` 和 `usage_boundary`。
  - **已完成（本轮）**：产业链/同类/上下游动作指向 `/api/company-database/batch/build` 和 `preview_batch_build`；股权/股东网络动作指向 `/api/company-database/relationships/build`，并带 `review_endpoint` 与 `manifest_endpoint`；图谱边动作指向 `/api/graph/query`。
  - **已完成（本轮验收）**：后端回归断言必补和增强动作均带目标 endpoint/UI action，避免 API 消费方继续依赖前端硬编码或中文文案解析。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-537 关系链补齐动作前端消费 target
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：让公司情报页“关系链缺口”按钮优先消费服务端 `target.ui_action`，减少前端硬编码映射对 API 语义的重复维护。
  - **已完成（本轮）**：`app/static/index.html` 的关系缺口按钮改为优先读取 `item.target.ui_action`，并把 `data-target-ui-action` 透传到点击处理逻辑。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增对 `data-target-ui-action` 的断言，确认缺口按钮从服务端 target 派生动作而不是只靠前端层名映射。
  - **已完成（本轮）**：`scripts/ui_static_check.py` 纳入 `data-target-ui-action` 文本检查，防止后续回退为只读层名硬编码。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`，并补浏览器验收。

- `DONE` T-538 关系链增强动作前端 target 合并
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：让公司情报页“关系链缺口”里的可选增强层也消费服务端 `enhancement_actions.target`，使 13F 持有人网络和事实股东网络等增强补齐入口可点击、可追溯。
  - **已完成（本轮）**：`app/static/index.html` 建立 `relationshipActionsByLayer`，把 `next_actions` 和 `enhancement_actions` 按 layer 合并回诊断行，必补层和增强层共用 target 驱动按钮。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增 `company_relationship_enhancement_actions_use_target`，断言 `shareholder_network` 与 `approved_shareholder_network` 能从 `enhancement_actions.target.ui_action` 渲染 `data-target-ui-action`。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录 UI 会把同 layer 的必补/增强 action target 合并到关系链缺口行；`scripts/ui_static_check.py` 纳入 `relationshipActionsByLayer`。
  - 验收：`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t538 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-539 股东/持有人行直达同一持有人网络
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：当用户看到某个 13F/持仓股东时，可以从“股东/持有人”这一行本身直接展开“该持有人还持有哪些公司”，不必先找到二跳“股东关联公司”行。
  - **已完成（本轮）**：`app/static/index.html` 的“股东/持有人”行写入 `data-institutional-holder-key` 和 `data-institutional-holder-label`，点击后按同一 13F/持仓持有人网络打开动态图谱。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增 `company_shareholder_row_has_holder_graph_attrs`，断言普通股东行也能携带 holder key 并打开同一持有人网络。
  - **已完成（本轮）**：`docs/api-contracts.md` 明确“股东/持有人”行和“股东关联公司”行都会写入 13F holder-key 过滤属性。
  - 验收：`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t539 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-540 事实股权关系行直达同一事实股东网络
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：当用户看到已批准的“事实股权关系”时，可以从该事实关系行直接展开“同一事实股东还关联哪些公司”，不必先找到二跳“事实股东关联”行。
  - **已完成（本轮）**：`relationship_context.ownership.approved_relationships[]` 输出 `holder_key` 和 `holder_name`，用于同一事实股东网络过滤。
  - **已完成（本轮）**：`app/static/index.html` 的“事实股权关系”行写入 `data-ownership-holder-key` / `data-ownership-holder-label`，点击后按同一事实股东网络打开动态图谱。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增 `company_approved_relationship_row_click_loads_holder_network`，单测补断言 `approved_relationships` 带 holder key。
  - **已完成（本轮）**：`docs/api-contracts.md` 明确“事实股权关系”行和“事实股东关联”行都会写入 ownership holder-key 过滤属性。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t540 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-541 产业链关系行点击保留方向追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：当用户从“同类公司 / 上游公司 / 下游公司 / 产业链位置”行进入知识图谱时，图谱过滤条要明确保留这次展开的产业链方向，避免用户只看到链条和节点却不知道当前图谱来自哪个逻辑方向。
  - **已完成（本轮）**：`app/static/index.html` 新增 `industryDirection` 图谱过滤状态，点击带 `data-industry-direction` 的产业链关系行时会在图谱 chip 展示“产业方向”并保留 raw direction。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 新增 `company_industry_relationship_row_click_preserves_direction_chip`，从模拟“上游公司”行点击进入图谱后断言 `industryDirection=upstream`、`chainId` 和 `chainNodeId` 都可追溯。
  - **已完成（本轮）**：`docs/api-contracts.md` 明确 `industryDirection` 是 UI 追溯状态，不改变 `/api/graph/query` 后端查询语义。
  - 验收：`python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t541 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-542 产业链图谱推荐入口细化到方向级
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows, Product and UI
  - 目标：让“图谱推荐入口”不只给出泛化产业链节点图，还能直接推荐同类、上游、下游三个具体方向，避免用户从推荐入口进入图谱后仍要猜当前展开逻辑。
  - **已完成（本轮）**：`relationship_context.dynamic_graph.recommended_queries[]` 在存在同类、上游、下游数据时，新增带 `query.industry_direction=peer/upstream/downstream`、`relationship_type`、`chain_id` 和 `chain_node_id` 的方向级产业链推荐。
  - **已完成（本轮）**：`app/static/index.html` 的“图谱推荐入口”会把 `query.industry_direction` 透传为 `data-industry-direction`，点击后沿用 T-541 的 `industryDirection` 图谱 chip。
  - **已完成（本轮）**：单测断言推荐查询包含 peer/upstream/downstream 三个方向；浏览器验收新增 `company_industry_recommended_query_click_preserves_direction_chip`，点击“上游公司”推荐入口后断言方向、关系类型、链条和节点均保留。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录方向级产业链推荐入口，并明确 `industry_direction` 是 UI 追溯状态，不新增后端查询过滤参数。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t542 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-543 产业方向图谱过滤显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：图谱过滤条面对用户显示“同类 / 上游 / 下游 / 产业链位置”，而不是直接显示 `peer/upstream/downstream/position` 枚举；同时保留 raw 枚举给脚本和审计追溯。
  - **已完成（本轮）**：`app/static/index.html` 的 `graphFilterDisplayValue()` 对 `industryDirection` 做中文映射，显示值为“产业链位置 / 同类 / 上游 / 下游”。
  - **已完成（本轮）**：`scripts/ui_interaction_acceptance.py` 更新产业链行和推荐入口点击断言，确认 chip 文本显示“上游”，但 `data-filter-raw-value` 和 title 仍保留 `upstream`。
  - **已完成（本轮）**：`docs/api-contracts.md` 明确产业方向 chip 中文显示与 raw 枚举追溯的分工。
  - 验收：`python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t543 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-544 产业方向推荐过滤键自描述
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Research and AI Workflows, Product and UI
  - 目标：让 `relationship_context.dynamic_graph.recommended_filters` 明确声明 `industry_direction`，避免 API 消费方看到推荐查询里的方向字段却无法从过滤键列表判断其含义和边界。
  - **已完成（本轮）**：`app/service_modules/company_intelligence.py` 的 `recommended_filters` 增加 `industry_direction`，与 T-542 的方向级 `recommended_queries[].query.industry_direction` 对齐。
  - **已完成（本轮）**：单测 `test_company_intelligence_first_class_models_are_exposed_and_aggregated` 断言 `industry_direction` 存在于推荐过滤键列表，且推荐查询仍包含 peer/upstream/downstream 三个方向。
  - **已完成（本轮）**：`docs/api-contracts.md` 明确 `recommended_filters` 会声明 `industry_direction`，并继续强调它是 UI 追溯状态，不新增 `/api/graph/query` 后端过滤参数。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`、`python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-545 关系类型图谱过滤显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：图谱过滤条面对用户显示“上游关系 / 事实股东 / 股东候选”等中文关系类型，而不是直接显示 `upstream_of`、`shareholder_candidate` 等 raw 枚举；同时保留 raw 关系类型给脚本和审计追溯。
  - **已完成（本轮）**：`app/static/index.html` 的 `graphFilterDisplayValue()` 对 `relationshipType` 增加常见公司关系、产业链关系和股权候选关系中文映射。
  - **已完成（本轮）**：浏览器验收更新上游推荐入口和事实股东图谱入口断言，确认 chip 文本显示中文，但 `data-filter-raw-value` 和 title 仍保留 `upstream_of` / `shareholder`。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录关系类型 chip 的中文显示与 raw 追溯分工。
  - 验收：`python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t545 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-546 多维关系表关系类型显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：公司情报“多维关系”表和“关键事实”里的关系类型面对用户显示“事实股东 / 实控候选 / 同类关系”等中文标签，不再把 `shareholder`、`controller_candidate`、`industry_peer` 等 raw 枚举直出；同时继续在 trace 和 data 属性里保留 raw 值。
  - **已完成（本轮）**：`app/static/index.html` 新增 `relationshipTypeDisplayLabel()`，图谱 chip、产业链关系行、事实股权关系、股权候选和公司关系事实行复用同一套中文映射。
  - **已完成（本轮）**：浏览器验收新增 `company_relationship_rows_display_chinese_type_labels`，断言表格前三列显示“同类关系 / 事实股东 / 实控候选”，且追溯详情仍保留 `industry_peer`、`shareholder`、`controller_candidate`。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录多维关系表的“中文主显示 + raw 追溯”契约，并修正 `recommended_filters` 固定列表包含 `industry_direction`。
  - 验收：`python3 -m py_compile app/static/index.html scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t546 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-547 关系候选审核队列关系类型显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：高级维护里的“关系候选审核”队列也复用关系类型中文映射，避免 `customer_candidate` 等 raw 枚举在主审阅表直出；同时高级 trace 继续保留 raw 供审批、脚本和审计使用。
  - **已完成（本轮）**：`app/static/index.html` 的 `renderCompanyRelationshipReview()` 使用 `relationshipTypeDisplayLabel()` 显示候选关系类型。
  - **已完成（本轮）**：浏览器验收 `company_relationship_review_queue_render` 断言可见前三列表格显示“客户候选”、不显示 `customer_candidate`，但整行 trace 仍包含 raw 枚举。
  - **已完成（本轮）**：`docs/api-contracts.md` 将“关系候选审核”纳入关系类型中文主显示契约。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t547 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-548 知识图谱关系边显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：知识图谱画布边 label 和“图谱关系”表也使用“事实股东 / 上游关系”等中文关系名，避免过滤 chip 已中文化但图谱主体仍显示 `shareholder` 等 raw 枚举；同时 link type、raw graph payload 和 trace 继续保留原始关系类型。
  - **已完成（本轮）**：`app/static/index.html` 的 `makeGraphModel()` 在公司关系边 label 中使用 `relationshipTypeDisplayLabel()`，不改写 link `type`。
  - **已完成（本轮）**：`renderKnowledgeGraph()` 的 `graphEdgeRows` 对带 `relationship_type` 的边使用中文主题和发现文本。
  - **已完成（本轮）**：浏览器验收 `company_ownership_approved_graph_filter_loads_shareholder_edge` 断言图谱关系表前三列显示“事实股东”、不显示 `shareholder`，但 trace 和 raw graph payload 仍保留 `relationship_type=shareholder`。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t548 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-549 图谱 inspector 相邻关系显示中文关系名
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows
  - 目标：知识图谱右侧 inspector 的“相邻关系”也显示“事实股东 / 上游关系”等具体中文关系名，而不是泛化成“公司关系”或暴露 raw 枚举，保持图谱画布、边表、过滤 chip 和 inspector 语义一致。
  - **已完成（本轮）**：`renderKnowledgeGraphInspector()` 的相邻关系行优先使用 graph link `label`，该 label 已由 `relationshipTypeDisplayLabel()` 中文化；缺失 label 时才回退 `graphEdgeLabel()`。
  - **已完成（本轮）**：浏览器验收新增 `company_graph_inspector_neighbor_shows_relationship_label`，选择含 `relationship_type=shareholder` 的图谱节点后断言相邻关系显示“事实股东”、不显示 `shareholder`，同时 raw link metadata 仍保留。
  - **已完成（本轮）**：`docs/api-contracts.md` 将图谱 inspector 相邻关系纳入关系类型中文主显示契约。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t549 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-550 股权 manifest 默认类型显示中文且保留 raw 追溯
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Data and Evidence
  - 目标：股权 manifest 预览表的“默认类型”列显示“事实股东 / 实控候选”等中文关系类型，避免用户在补股权关系时看到 `shareholder` 等 raw 枚举；同时 manifest payload 和高级 trace 继续保留 raw `default_kind`。
  - **已完成（本轮）**：`renderCompanyOwnershipManifest()` 的默认类型列使用 `relationshipTypeDisplayLabel(item.default_kind)`。
  - **已完成（本轮）**：浏览器验收 `company_ownership_manifest_preview_real_api` 断言 manifest 表前三列显示“事实股东”、不显示 `shareholder`，整行 trace 仍保留 raw。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录股权 manifest 默认类型列中文主显示与 raw 追溯分工。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t550 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-551 股权表导入结果主列与追溯分离
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Data and Evidence
  - 目标：股权表导入预览和执行结果的主表列只显示用户决策需要的信息，把 `file_path`、`source_table`、`source_id` 等 raw 字段留在高级追溯里，保持本地股权补库链路可读且可审计。
  - **已完成（本轮）**：`renderCompanyOwnershipImport()` 将“股权表追溯”从第一列移到最后一列，前三列保留股权表名称、解析状态、候选关系和目标公司。
  - **已完成（本轮）**：浏览器验收 `company_ownership_manifest_to_import_preview_real_api` 断言导入结果前三列不含 `file_path` / `local structured ownership`，整行 trace 仍保留 raw 来源信息。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录股权表导入结果主列与 raw trace 的显示分工。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t551 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-552 13F 股东/持有人来源状态显示可读化
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Data and Evidence
  - 目标：公司情报“多维关系”里的“股东/持有人”行在缺少报告期时不直接显示 `sec_edgar` 等 raw 来源 id，而显示治理后的来源标签，并在行级追溯属性中保留 raw 来源。
  - **已完成（本轮）**：`renderCompanyRelationshipContext()` 新增 `holdingStatusLabel()`，状态列优先显示 `report_period`，缺失时回退 `sourceLabel(source_id)`。
  - **已完成（本轮）**：浏览器验收 `company_shareholder_holding_source_label_is_readable` 断言前三列显示“SEC 官方披露”、不显示 `sec_edgar`，行级 `data-source-id` 仍保留 raw `sec_edgar`。
  - **已完成（本轮）**：`docs/api-contracts.md` 记录 13F 持有人主显示和 raw trace 的分工。
  - 验收：`python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t552 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-553 多维关系链总体验收与交接
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：PM / Release Coordination, Product and UI, Data and Evidence
  - 目标：对 T-504 至 T-552 的公司产业链、同类、上下游、股东、股东关联公司和动态图谱能力做总收口，证明当前目标不需要重建数据库，且主链路可用、可追溯、可复验。
  - **已完成（本轮）**：新增 `docs/multidimensional-relationship-closure.md`，用能力矩阵列出产业链位置、同类、上游、下游、股东/持有人、事实股权、13F 持有人、事实股东关联、图谱推荐入口、过滤 chip 和中文主显示的覆盖证据。
  - **已完成（本轮）**：清理 T-505 至 T-514 中已被后续任务完成的“后续增强”提示，保留真正不阻塞当前目标的真实外部数据源接入和质量调参增强。
  - **已完成（本轮）**：`docs/README.md` 纳入多维关系链总收口证明文档。
  - 验收：`python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`、重点关系链单测、`python3 scripts/ui_static_check.py`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t553 --timeout 60`、`python3 scripts/check_handoffs.py`、`git diff --check`。

- `DONE` T-565 逻辑链条总地图、文档导览和质量门收口
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - Owner：PM / Release Coordination, Product and UI, Platform and Quality
  - 目标：把公司情报、最新分析、多维关系和个人研究闭环四条主线收束成可导航、可复验、可维护的文档体系，并把 Markdown 相对链接检查纳入本地质量门。
  - **已完成（本轮）**：新增 `docs/logic-map.md` 作为四条主线第一入口；新增或完善 `docs/logic-chain-overview.md`、`docs/latest-analysis-chain.md`、`docs/multidimensional-relationship-closure.md`、`docs/personal-research-loop-overview.md`。
  - **已完成（本轮）**：根 `README.md`、`docs/README.md` 和 `docs/project-support.md` 已加入逻辑总地图、主线入口和阅读顺序。
  - **已完成（本轮）**：新增 `scripts/check_markdown_links.py`，默认检查 `README.md` 与 `docs/**/*.md` 的本地相对链接；`make local-ci` 已接入该检查。
  - **已完成（本轮）**：`docs/artifact-governance.md` 与 `docs/pr-checklist.md` 已加入文档链接检查说明；历史底稿链接断链已修正。
  - **已完成（本轮）**：`docs/logic-map.md` 已记录完整 `make local-ci` 证据：Python 编译、全量单测、UI 静态契约、安全检查、Markdown 链接检查和 handoff 校验全部通过。
  - 验收：`make local-ci` 通过；`python3 scripts/check_markdown_links.py` 通过，检查 195 个 Markdown 文件；`python3 scripts/check_handoffs.py` 通过；`git diff --check` 通过。

- `DONE` T-566 Obsidian 式可探索知识网络
  - 对应：E3-US1, E5-US1, E7-US1, E8-US2；关系图谱/多维数据完整性增强
  - Owner：Product and UI, Research and AI Workflows, Data and Evidence
  - 目标：把现有公司中心关系图谱升级为更接近 Obsidian Graph View 的可探索知识网络，支持多社区、动态展开、产业链/股东/证据/观点多维关系和可复验浏览器质量门。
  - 现状判断：不需要推倒重建数据库，但需要持续补“图谱语义层 + 数据密度 + 前端探索体验”。当前差距的主要原因不是单个样式问题，而是默认查询仍偏公司中心、候选图谱数据量偏薄、SVG 本地图需要裁剪、图谱交互还没有达到 Obsidian 的全局/局部网络探索成熟度。
  - **已完成（本轮）**：`/api/graph/query` 可从 `CompanyPosition + IndustryChain` 派生产业链同类、上游、下游语义边；13F/持有人网络和事实股东网络可通过 holder key 展开跨公司图谱。
  - **已完成（本轮）**：新增 Obsidian 图谱 seed API/CLI/领域模块，能用 AAPL/NVDA/MSFT/TSM/ASML/AVGO/600519/600809、AI 端侧设备产业链和 Vanguard/Berkshire 持有人关系构造本地多社区验收图谱。
  - **已完成（本轮）**：前端图谱默认深度调整为三跳，局部首屏加入社区优先裁剪和默认跨社区展开，弱化单 issuer 居中星状布局，社区力导向改为多簇分布。
  - **已完成（本轮降噪）**：默认主体图会按焦点公司产业定位裁剪 production-universe 批量链节点，并跳过低置信 `pos_full_graph_*` 相关公司扩散，避免 AAPL 首屏被 AAMI 等无关市场节点污染；显式关系/产业链过滤仍用于主动探索。
  - **已完成（本轮验收）**：当前代码在 `AI_QUANT_PORT=55541` seed 后，AAPL 局部首屏浏览器验收通过：22 节点、54 边、3 个可见社区、5 个产业节点、0 重叠、0 贴边、约 60 FPS，并保留视图控制、探索 trail 和 saved subgraph 检查。
  - **已完成（继续推进）**：普通 symbol 搜索默认改为 issuer-level 公司知识网络，不再自动带 primary `security_id`；只有从证券行、公司产业定位行或精确关系入口点击时才启用证券级过滤，避免首屏被收窄成单证券关系图。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55542` seed 后，AAPL 默认公司级首屏浏览器验收通过：37 节点、88 边、3 个可见社区、13 个产业节点、2 个重叠、0 贴边、约 60 FPS，filter chip 仅显示 `主体: issuer_aapl`，明确不含 `证券:`。
  - **已完成（继续推进）**：Obsidian seed 增加本地 seed source、公司 note 文档、公司事件、结构化研报和观点节点，把图谱从“产业链/持有人关系网络”推进到包含文档、事件、观点的知识网络；全部仍标记为本地 seed/观点层，不作为生产证据或交易信号。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55544` seed 后，AAPL 默认首屏浏览器验收通过：40 节点、88 边、4 个可见社区、13 个产业节点、5 个 raw 知识节点，首屏可见 `event/research/evidence` 三类知识节点，filter chip 仍不含 `证券:`。
  - **已完成（继续推进）**：节点详情面板新增“设为焦点”，可把当前选中事件/观点/证据等知识节点切换成新的局部图中心，同时写入探索轨迹、展开该节点并重绘邻域；这使图谱具备类似 Obsidian 的逐节点漫游能力。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55545` seed 后，浏览器验收点击可见知识节点并触发“设为焦点”，确认 `focusId` 从 `issuer_aapl` 切到 `event_obsidian_aapl_on_device_ai`，该节点进入 expanded/trail，保存子图 storage key 也切到事件焦点。
  - **已完成（继续推进）**：新增焦点历史和“返回焦点”入口，用户从公司切到事件/观点/证据节点后可以一键回到上一个焦点，并在路径面板保留焦点历史按钮，避免探索链路变成一次性跳转。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55546` seed 后，浏览器验收确认 AAPL 默认图为 40 节点、78 边、4 个可见社区、13 个产业节点、5 个 raw 知识节点，`event/research/evidence` 可见；点击知识节点后 `focusId` 从 `issuer_aapl` 切到 `event_obsidian_aapl_on_device_ai`，焦点历史为 2 个节点，再点击“返回焦点”回到 `issuer_aapl`。
  - **已完成（继续推进）**：新增 `/api/graph/knowledge-network/readiness` 和 `scripts/graph_knowledge_network_readiness.py`，用现有真实/本地记录审计 Obsidian 式知识网络的数据密度，输出公司画像、产业定位、公司关系、股东持仓、文档、证据、事件、研报和观点层覆盖，社区来源、跨层链接、edge 数量、seed 依赖度和下一步 backfill 动作。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55547` seed 后，readiness CLI 对 `issuer_aapl` 输出 `status=needs_data`：图谱有 90 条边、7 个社区、8 个已覆盖数据层，但 `evidence` 层缺失且 `seed_dependency.seed_dependent=true`，因此不会把 seed/fixture 图谱误判为真实生产级 Obsidian 知识网络。
  - **已完成（继续推进）**：新增 `scripts/backfill_knowledge_network_evidence.py`，按 issuer 图谱读取缺 evidence 的 Document，默认 dry-run，显式 `--execute` 时通过 `/api/evidence/extract` 生成 Evidence 切片，并在结果里记录 readiness 前后对比；来自 seed 文档的 evidence 仍计入 seed dependency，避免误判。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55548` seed 后执行 knowledge-network evidence backfill，AAPL 2 个文档生成 3 条 evidence，readiness 中 `evidence` 层从 missing 变为 sufficient，边数从 90 增到 93，`HAS_EVIDENCE` 可见，`seed_dependency.seed_dependent=true` 保持；浏览器验收通过，41 可见节点、82 边、4 个可见社区、8 个 raw knowledge 节点，焦点切换/返回仍通过。
  - **已完成（继续推进）**：新增 `/api/graph/knowledge-network/evidence-links/backfill` 和 `scripts/backfill_knowledge_network_evidence_links.py`，把已存在的 Document->Evidence 切片回填到 CompanyEvent、CompanyRelationship、ReportViewpoint 的 `evidence_ids`，默认 dry-run，显式 `execute=true` 才写入本地 provenance 链接。
  - **已完成（继续推进验收）**：当前代码在 `AI_QUANT_PORT=55549` seed + evidence backfill 后执行 evidence-link backfill，AAPL 1 个事件和 1 个观点挂上 evidence；readiness 显示 `event_evidence_links=1`、`viewpoint_evidence_links=1`、边数 98，仍为 `needs_data` 且 `seed_dependency.seed_dependent=true`；浏览器验收通过，42 可见节点、88 边、raw edge types 包含 `EVENT_EVIDENCE` 和 `VIEWPOINT_EVIDENCE`。
  - **仍未完成**：要达到 Obsidian 标准，还需要把长期本地真实数据导入到同一图谱语义层，继续增加文档/事件/观点/证据之间的真实交叉链接，并评估 Canvas/WebGL 或虚拟化以支撑更大图谱；当前 seed/fixture 证明能力成立，但不等于真实生产数据已经足够丰富。
  - 验收：`python3 -m unittest tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network tests.test_system.SystemServiceTests.test_graph_knowledge_network_readiness_flags_real_data_gaps_and_seed_dependency`、`python3 scripts/backfill_knowledge_network_evidence_links.py http://127.0.0.1:55549 --issuer-id issuer_aapl --limit 10 --execute --output artifacts/knowledge-network-evidence-link-backfill-executed.json --timeout 10`、`python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55549 --symbol AAPL --scope local --min-nodes 28 --min-links 64 --min-community-labels 3 --min-visible-communities 4 --min-industry-nodes 5 --min-raw-knowledge-nodes 8 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-evidence-links.json --timeout 45`、`python3 scripts/ui_static_check.py`、`python3 scripts/check_handoffs.py`、`git diff --check`。

## 运维/非本机发布附录 / 当前工程治理待办

项目经理口径：以下任务来自 2026-05-28 项目分析，目标是把本机长期使用状态从“可运行”提升为“可维护、可复验、可交接”。这些任务不改变系统边界：仍只做公司情报、证据研究、观点复盘、模拟反馈，不接真实券商，不做自动下单。

- `DONE` T-424 测试健康与 UI 静态契约收敛
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 背景：`python3 -m py_compile app/*.py tests/*.py scripts/*.py` 已通过；清理外部运行时环境后，`python3 -m unittest discover -s tests` 仅剩 `test_ui_static_contract_matches_target_information_architecture` 失败，原因是测试仍期望 `required_ids=145`，而 `scripts/ui_static_check.py` 当前返回 `required_ids=151`。
  - **已完成（本轮）**：`test_ui_static_contract_matches_target_information_architecture` 改为读取 `len(REQUIRED_IDS)` 与 `len(REQUIRED_JS_FUNCTIONS)`，避免 UI 契约迭代导致硬编码漂移。
  - **已完成（本轮）**：`python3 scripts/ui_static_check.py` 返回 `required_ids=151`、`required_functions=50`、`node_check=passed`，与测试断言一致。
  - 输出：测试断言修复、UI 静态契约变更记录、一次干净环境全量单测输出。
  - 验收：干净本地环境下 `python3 -m unittest discover -s tests` 204/204 通过；`python3 scripts/ui_static_check.py` 返回 `node_check=passed`；UI 契约变动在任务记录中可追溯。

- `DONE` T-425 配置加载、`.env` 隔离和测试可复现
  - 对应：E3-US4, E6-US4, E8-US2, E9-US2；愿景扩展/生产化增强
  - 背景：`app.server` 在 import 阶段自动加载 `.env`，会把 PostgreSQL/S3/OpenSearch/LLM/OCR 等本机生产配置注入测试进程；直接跑单测时曾触发 `psycopg` 缺失、S3 DNS 访问和 storage readiness 断言漂移。空字符串环境变量还会触发 `int("")` / `float("")` 类型错误。
  - **已完成（本轮）**：`app.server` 改为懒加载 router，移除 import 阶段 `.env` 副作用；`.env` 仅在 `python -m app.server` 启动路径显式加载。
  - **已完成（本轮）**：新增统一环境变量解析 helper：`app/utils.py` 中 `env_text/env_int/env_float`；接入 `app/llm_gateway.py`、`app/document_parser.py`、`app/services.py`、`scripts/staging_acceptance.py`，空字符串不再触发 `int("")/float("")`。
  - **已完成（本轮）**：`tests/test_system.py` 的 `setUp` 统一隔离 `AI_QUANT_*`；新增 `.env` 导入隔离回归测试和空字符串 env 解析回归测试。
  - 输出：配置加载重构、测试隔离 fixture、环境变量解析单测、README 中的测试运行说明。
  - 验收：存在生产 `.env` 时，全量单测不访问真实 PostgreSQL/S3/OpenSearch/LLM/OCR；空字符串环境变量不导致服务初始化失败；`python3 -m unittest discover -s tests` 无需手工清理 `AI_QUANT_*` 即可通过。

- `DONE` T-426 依赖声明与运行环境一致性
  - 对应：E3-US4, E8-US2, E9-US2；愿景扩展/生产化增强
  - 背景：`pyproject.toml` 主依赖为空，但 Dockerfile 手动安装 `psycopg`、`pandas`、`baostock` 等运行依赖；本地、容器和 CI 依赖来源不一致，容易产生“本机能跑、CI/容器失败”的漂移。
  - **已完成（本轮）**：`pyproject.toml` 增加 `build-system`，并补齐 `postgres`、`market-data`、`ui-acceptance`、`test` extras。
  - **已完成（本轮）**：`Dockerfile` 由手写散装依赖改为 `pip install ".[postgres,market-data]"`，避免与项目声明脱节。
  - **已完成（本轮）**：`README.md` 增加 Python 3.11/3.12 支持矩阵、`python3 -m pip install '.[test]'` 一条命令测试依赖安装，以及 `.[market-data]` 独立安装说明。
  - 输出：更新后的依赖声明、Dockerfile 安装策略、开发环境安装命令、CI 依赖缓存策略。
  - 验收：新环境按 README 一条命令可安装测试依赖并运行单测；Docker 依赖与 `pyproject.toml` 对齐；`postgres/market-data` extra 可独立安装。

- `DONE` T-427 `SystemService` 模块化拆分计划
  - 对应：E3-US1, E3-US4, E5-US1, E6-US4, E8-US2；愿景扩展/生产化增强
  - 背景：`app/services.py` 已超过 2.5 万行，数据接入、证据抽取、研究问答、组合、图谱、LLM、workflow、readiness 和治理都集中在一个类中；继续叠功能会增加回归风险和交接成本。
  - **已完成（本轮）**：新增 ADR `docs/systemservice-modularization-adr.md`，明确目标边界、迁移阶段、回归清单和 guardrails。
  - **已完成（本轮）**：完成第一批低风险抽取：`safe_identifier()` 抽取到 `app/service_modules/common.py`，`SystemService` 通过 facade 方法委托，无行为变化。
  - 输出：模块拆分 ADR、迁移顺序、每阶段回归测试清单、第一批低风险 helper/service 抽取 PR。
  - 验收：首批拆分后 API 行为不变；全量单测通过；后续新增功能按 ADR 约束走模块化路径。

- `DONE` T-428 本机安全边界与非本机发布授权策略
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - 背景：当前 API 角色主要由 `X-Role` 请求头自声明，适合本机工具和验收脚本，不适合作为非本机网络服务授权机制。项目边界仍是模拟交易，但非本机部署前必须补真实认证、授权和密钥管理策略。
  - **已完成（本轮）**：新增 ADR `docs/security-boundary-modes-adr.md`，定义 local/staging/production 模式差异、认证模式演进和红队任务拆分。
  - **已完成（本轮）**：`app/server.py` 增加非本机启动门禁：`AI_QUANT_DEPLOYMENT_MODE` 为非本机时，若 `AI_QUANT_AUTH_MODE` 仍是 header-only 则拒绝启动。
  - **已完成（本轮）**：新增单测 `test_non_local_deployment_mode_rejects_header_only_auth` 验证门禁行为。
  - 输出：安全边界 ADR、权限矩阵升级方案、非本机发布前置检查、红队验收脚本任务拆分。
  - 验收：本机模式保持低摩擦；非本机 header-only 模式拒绝启动；`scripts/security_check.py .` 保持 `ok=true`。

- `DONE` T-429 CI 验收命令、产物治理和交接清单
  - 对应：E7-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 背景：仓库存在大量本机 artifacts、运行脚本和验收输出；当前 `git status` 也有多处未提交修改和新增文件。需要把“日常可复验”固化为 PM 可追踪的交接清单，避免个人机器状态成为唯一事实来源。
  - **已完成（本轮）**：新增 `Makefile` `local-ci`，串联 `py_compile`、`unittest`、`ui_static_check`、`security_check`、`check_handoffs`。
  - **已完成（本轮）**：新增 `docs/artifact-governance.md`，定义 artifact 分类与提交规则。
  - **已完成（本轮）**：新增 `docs/worktree-change-grouping-2026-05-28.md`，给出当前未提交变更分组说明。
  - **已完成（本轮）**：`README.md` 与 `AGENTS.md` 增加 `make local-ci` 入口说明。
  - **已完成（本轮）**：`python3 scripts/production_task_closure_audit.py` 复验输出 `todo_status_counts.todo=0`、`doing=0`；剩余开放项均为 `blocked_external_evidence`（17 项）。
  - 输出：本机 CI 脚本或 Make 目标、artifact 提交规则、交接 checklist、当前未提交变更分组说明。
  - 验收：项目交接时可用一条命令复验核心质量门（`make local-ci`）；artifact 提交规则与分组说明可追溯。

## 已落地基线

- `DONE` T-301 后端核心对象、API 路由和治理规则原型
  - 对应：E2-US1, E3-US1, E5-US3, E6-US1, E6-US2, E6-US3, E6-US4, E8-US1, E8-US2, E9-US1
  - 代码：`app/models.py`、`app/api.py`、`app/services.py`、`tests/test_system.py`

- `DONE` T-302 A/H/U 公开披露最小接入与批量采集闭环
  - 对应：E2-US2, E3-US3
  - 代码：SEC EDGAR、HKEXnews、上交所/深交所 recent connector；ingestion job、schedule、retry、去重和错误留痕

- `DONE` T-303 权限、合规和审批闸门
  - 对应：E2-US1, E2-US3, E6-US1, E6-US2, E6-US3, E6-US4
  - 代码：rights tag 校验、Reg FD / non-display gate、prompt 审批、未审批决策拦截纸面执行意图和模拟持仓入口

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
  - 已有：`docs/us-compliance-open-questions.md` 覆盖 Reg FD 来源公开性、Nasdaq/NYSE non-display/derived data declaration、投资顾问和外部资管边界、真实券商接口 / best execution / live execution 的非目标说明、衍生品与跨境限制

## 历史能力与运维附录 / M6 事实层

- `DONE` T-401 复杂版式 PDF / OCR 与真实证据定位生产化
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：HTML 清洗、`\f` 分页、PDF 文本流/Flate 流兜底、规则表格读取、`page=...;chunk=...` locator、空文本/扫描件解析失败分级、ManualReviewItem 人工复核队列、evidence quality report、PaddleOCR-VL 备用解析接口
  - 已有：PaddleOCR-VL 解析结果按文档/URL、content hash/source URI、模型和 optional payload 运行时缓存，并返回 `cache_hit`、`elapsed_ms`、`estimated_cost` 供质量/成本审计
  - **已完成（本轮）**：OCR locator schema 与版面资产穿透
    - Evidence 新增 `locator` 和 `assets` 元数据，保留旧 `bbox` 字符串兼容；规则文本 locator 为 `page_chunk_v1`，OCR 版面 locator 为 `ocr_bbox_span_v1`
    - PaddleOCR JSONL 解析可提取 `layoutDetections`、`tables/cells`、markdown/output 图片资产，并规范化为 `{x,y,width,height}` bbox
    - `extract_evidence` 可把 OCR layout bbox、span hash、table cell bbox 和 image/table asset refs 写入 evidence
    - `_extract_tables` 优先使用 OCR locator table cells，benchmark 表格定位可读取真实 cell bbox
    - `/api/evidence/quality-report` 新增 `structured_locator_coverage`、`bbox_coverage`、`table_cell_count`、`table_cell_bbox_coverage`、`asset_reference_count`
  - **已完成（本轮）**：跨页表格合并
    - `POST /api/extractions/run` 支持 `include_adjacent_tables=true`，可扫描同一文档相邻 evidence，并按同 header / 同列签名合并跨页表格
    - 合并结果保留 `page_numbers`、`merged_from_table_count`、`merge_strategy` 和 cell 级 `source_page_no` / `source_row` / `merged_row` locator，方便回溯原 PDF 页/框
    - 测试覆盖 `\f` 分页文本中的同 header 表格合并、跨页 cell 定位和 table benchmark 指标
  - **已完成（本轮）**：解析失败重试
    - `/api/document-parsing/paddleocr` 支持 `retry_attempts` / `retry_limit`，临时失败可最多额外重试 3 次，并返回 `attempt_count`、`retry_attempts` 和 `retry_errors`
    - `extract_evidence` 的 OCR fallback 默认做一次自动重试，仍失败才创建 ManualReviewItem，避免临时 OCR job/结果 URL 波动直接进入人工队列
    - 测试覆盖 URL 解析 transient failure 重试成功，以及证据抽取 OCR fallback 重试后不创建人工复核
  - **已完成（本轮）**：真实扫描件大样本版面 bbox 校验入口
    - `/api/evidence/quality-report` 支持 `bbox_gold_labels` 和 `min_bbox_iou`，按 IoU 输出 `bbox_hit_rate`、`average_iou`、逐标签命中和失败样本
    - 测试覆盖 OCR layout bbox 与人工 gold label 的命中/未命中校验，为后续 300-500 份真实扫描件样本运行提供固定验收入口
  - 后续真实数据验收：把真实扫描件大样本 gold label 批量跑完并归档外部 artifact URI（并入 T-402 / T-422 证据包）
  - 输出：OCR/版面解析 adapter、bbox/span schema、解析质量报告、人工复核闭环、错误样本库
  - 验收：每个错误样本可回溯到原 PDF 页/框；证据页命中率达到 benchmark 门槛；解析失败进入人工复核并触发告警

- `BLOCKED` T-402 大样本中英双语 benchmark 执行
  - 对应：E4-US1, E4-US2, E4-US3
  - 已有：BenchmarkSample、BenchmarkRun、`/api/benchmarks/{benchmark_id}/samples`、`/api/benchmarks/{benchmark_id}/run`、中英样本登记、真实 extraction 链路评估、术语 F1、数值/期间召回、表格召回、页命中率、证据定位率、按语言拆分指标、低置信度拦截、失败样本和回归样例库、PostgreSQL 视图
  - 已有：`GET|POST /api/benchmarks/{benchmark_id}/readiness-report` 可按固定 gate 输出大样本验收包，检查 active sample 数、中文/英文覆盖、最近 run 指标、样本 manifest URI、中文/英文样本集 URI、人工标注手册 URI、OCR/bbox gold label URI、表格 cell gold label URI、摘要质量样本 URI、regression baseline artifact URI；内联 gold/summary payload 只用于计数摘要，不能替代真实外部 artifact
  - **已完成（本轮质量包入口）**：新增 `scripts/local_benchmark_quality_package.py`，可扫描本地文本/PDF材料，自动登记中英 benchmark 样本、运行抽取 benchmark，并导出 `artifacts/benchmark-quality-package/sample-manifest.json`、`baseline-report.json`、`readiness-report.json`、`annotation-manual.md`、`bbox-gold.jsonl`、`table-cell-gold.jsonl` 和 `summary-quality-samples.jsonl`
    - 2026-05-18 实跑 `python3 scripts/local_benchmark_quality_package.py data/objects docs --output-dir artifacts/benchmark-quality-package --benchmark-id bm_local_quality_20260518 --target-sample-size 300 --min-chinese-samples 150 --min-english-samples 150 --max-samples 500 --artifact-prefix minio://ai-quant-local/benchmark-quality/20260518`，artifact 已生成；当前 `sample_count=72`、`target_gap=228`、`run_passed=false`、`large_sample_ready=false`
    - 当前缺口被明确量化为 `sample_size`、`chinese_sample_count`、`english_sample_count`、`metric_number_recall`、`metric_period_recall`；后续补真实样本和修数值/期间召回时可复用同一脚本回归
  - **已完成（本轮接口补样本入口）**：新增 `scripts/fetch_benchmark_samples.py`，可通过现有公开披露 connector 批量拉 SEC/A 股/HKEX 样本并保存为质量包可扫描的本地文本，同时输出 `artifacts/benchmark-sample-fetch/fetch-manifest.json` 记录创建、跳过和失败原因
    - 2026-05-18 实跑 SEC CIK `0000320193,0000789019`、`10-K/10-Q`、每个 CIK 2 份，成功新增 4 份英文披露样本；随后重跑质量包 `python3 scripts/local_benchmark_quality_package.py data/objects docs artifacts/benchmark-sample-fetch ...`，当前 `sample_count=148`、`language_counts={en:119, zh:29}`、`target_gap=152`
    - 2026-05-18 继续补齐 A 股附件路径：`scripts/fetch_benchmark_samples.py` 新增 `--include-ashare-attachment-text`，在公告列表只有标题时会尝试下载公开附件并抽取文本，支持本机 `pdftotext` fallback，并在 `skipped` 中记录附件尝试、403/封禁页或无指标术语等原因；实跑 `600519,600000,000001,300750` 时上交所附件被 CDN 返回封禁 HTML/无可用指标正文，深交所附件返回 403，因此未把无正文标题计入有效样本
    - 2026-05-18 纳入已落盘公开/本地材料后重跑质量包 `python3 scripts/local_benchmark_quality_package.py data/objects docs artifacts/benchmark-sample-fetch artifacts/benchmark-sample-fetch-ashare ...`，曾达到 `sample_count=278`、`language_counts={en:222, zh:56}`、`target_gap=22`
    - 2026-05-18 修正质量包本地 PDF 抽文本能力，补入 `pdftotext` fallback；按中文公开材料优先顺序重跑 `python3 scripts/local_benchmark_quality_package.py data/objects/ashare_exchange data/objects/sec_edgar docs artifacts/benchmark-sample-fetch artifacts/benchmark-sample-fetch-ashare /home/xionglei/文档/6大投行研报汇总 ... --max-samples 500`
    - 2026-05-18 修正自动 gold 口径：质量包先按可见文本推断 expected terms/numbers/periods，跳过无自动可验证数字或期间的弱样本，并保护中文样本配额，避免英文 SEC 样本提前填满 `--max-samples`
    - 2026-05-18 质量包已绿灯：当前 `sample_count=500`、`language_counts={en:335, zh:165}`、`source_counts={ashare_exchange:165, sec_edgar:335}`、`target_gap=0`、`run_passed=true`、`large_sample_ready=true`、`readiness_missing_requirements=[]`
    - 2026-05-18 新增 `scripts/local_data_unblock_audit.py` 并实跑 `python3 scripts/local_data_unblock_audit.py --output artifacts/local-data-unblock-audit.json`，当前 `status=passed`、`data_blocked=false`、`remaining_quality_gaps=[]`
    - 现阶段可以继续通过接口补英文 SEC 样本；中文样本可继续扩大 A 股公告代码池，但若交易所附件下载被 CDN/403 拦截，需要优先使用本地已授权研报/TDX 补充包中可抽文本材料，不能把只有标题的公告算作有效 benchmark 样本
  - 待做：300-500 份真实中文公告/年报样本、英文 SEC 披露样本集、人工标注手册、OCR/版面金标 bbox、表格 cell gold label、摘要质量样本、回归 baseline 报告的真实 artifact URI 归档
  - 输出：中文公告/年报样本集、英文 SEC 披露样本集、标注手册、规则基线报告、抽取/证据定位/表格指标、回归样例库
  - 验收：核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；低置信度样本能拦截

- `DONE` T-403 公开 EOD / 延时行情和来源 provenance 台账
  - 对应：E2-US1, E2-US3, E2-US4
  - 已有：`public_eod_market_data` 公开/已提供 EOD 来源、MarketDataPoint、`/api/market-data`、`/api/market-data/batch`、CorporateAction、`/api/corporate-actions`、`/api/market-data/adjusted` 原始/前复权/后复权计算视图、`/api/market-data/returns` 回测/估值/风险收益序列消费入口、`/api/portfolio/returns` 组合级公开复权收益/波动/回撤消费入口、`/api/portfolio/valuation` 模拟持仓估值/现金权重/缺失价格 adapter、价格收益与 `cash_dividend_reinvested` 现金分红总回报口径、批量导入逐条错误留痕、拆股/分红/代码变更公司行动、UI 入库入口、dashboard 摘要、rights tag 校验、实时数据阻断、红区/越权来源阻断测试、行情字段白名单入库校验、通达信 `vipdoc/*.day` 只读预览和导入接口、`vipdoc` 本地校验/解析兜底、`vipdoc` 显式 URL 下载/sha256 校验/zip 安全解压脚本、PostgreSQL 全量导入脚本、SQLite 状态库增量导入脚本、source governance/provenance 台账字段、字段白名单、缓存期限、公开来源覆盖报告、行情数据质量报告
  - 已有：来源 provenance 可记录 `provenance_ref`、`source_tos_uri`、`collection_method`、`robots_policy`、`usage_scope`、`last_reviewed_at`，`/api/governance/sources/{source_id}/reviews` 可记录季度来源复核、复核状态、TOS/robots/用途边界和下次复核日期；历史 `authorized_eod_market_data` 输入兼容映射到 `public_eod_market_data`
  - 已有：`/api/portfolio/valuation` 返回 `risk_decomposition`，按 market/currency/industry/style 输出持仓市值、权重、外币权重、现金权重和集中度；industry/style 可通过 holdings 或 `groups[security_id]` 注入
  - 本地资源：`data/local/tdx/vipdoc`，来自通达信官方个人行情数据页下载的 `vipdoc/*.day` 文件，已复制到项目内，不依赖下载目录或废弃 `stock_chs` 项目；当前导入摘要为 12169 个有效文件、28,885,502 条写入尝试、28,247,650 条唯一 `market_data`、11966 个证券、覆盖 1990-12-19 至 2026-05-15，artifact 为 `artifacts/tdx-vipdoc-postgres-import-full.json`
  - **已完成（本轮）**：通达信 `vipdoc/*.day` schema 解析和字段映射
    - `TDXVipdocAdapter` 直接解析官方日线二进制格式，输出 `date/open/high/low/close/amount/volume` 并映射到公开 EOD 字段；symbol 查询兼容 bare code、`sh/sz/bj` 前缀、`.SH/.SZ/.BJ/.SS/.XSHG/.XSHE` 后缀
    - 项目已移除旧本地中间库依赖和数据文件，容器运行环境不再安装旧中间库包
    - `.gitignore` 已忽略本机 staging 截图、验收 artifact 和运行时对象存储写入，保留已纳管 demo 样例
  - **已完成（本轮）**：真实生产输入 schema 覆盖率报告和异常 schema 样本库
    - `GET|POST /api/market-data/schema-coverage-report` 复用 TDX vipdoc adapter 的真实 `.day` 文件规则，输出 `schema_recognition_coverage`、`target_field_coverage`、逐文件 `target_field_mapping`、source whitelist 缺口、`automation_ready` 和 `anomaly_samples`
    - 支持传入 `schema_samples` 做异常 schema 样本库验收，缺失必填字段、未映射 tick/realtime 字段和 source governance 缺口都会进入 blocker/anomaly，而不会进入导入链路
    - 测试覆盖真实别名 schema 100% 映射到公开 EOD 字段，以及异常 schema 被阻断并列入样本
  - **已完成（本轮）**：模拟持仓/回测流水 adapter 对更多输入格式的兼容
    - `POST /api/portfolio/transactions/import` 支持批量导入模拟/回测流水，兼容 `symbol/ticker/code/ts_code`、`trade_date/date/datetime/filled_at`、`side/action/direction`、`quantity/qty/shares/signed_qty`、`price/fill_price/avg_price`、`fees/commission`、`account/portfolio_id` 和 `strategy/model/run_id`
    - 支持 `dry_run` 预检、`skip_existing` 幂等跳过、`security_map` 显式映射，默认 `source_id=simulated_trade_execution`，固定 `simulation_only=true`、`live_execution_allowed=false`
    - 测试覆盖 backtest alias rows、负 signed quantity 推断 sell、重复导入跳过和 as-of 持仓派生
  - 验收：生产输入数据 100% 能映射到公开来源 provenance 台账；红黄绿分级覆盖率 >= 95%；边界不清、禁止缓存/禁止自动化或实时 non-display 数据不能进入自动化链路

- `BLOCKED` T-404 生产级状态库、对象存储和检索适配
  - 对应：E3-US4, E6-US4, E8-US2
  - 已有：SQLite 状态库、PostgreSQL baseline schema、`ai_quant.schema_migrations`、PostgreSQLStore runtime、schema 初始化、`AI_QUANT_POSTGRES_DSN` / PostgreSQL DSN 形式 `AI_QUANT_DB` 启动路径、SQLite -> PostgreSQL 显式迁移脚本、`scripts/postgres_schema_migrate.py` baseline apply/dry-run/rollback-record、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、外部检索失败 fallback、runtime fake-driver 持久化测试
  - 已有：`/api/governance/storage-policy-templates` 输出 S3 scoped-prefix IAM、对象生命周期、OpenSearch index role、PostgreSQL app/migration grants 和破坏性 DDL rollback 审批模板，作为真实环境最小权限样例
  - 已有：`GET|POST /api/governance/storage-readiness-report` 可汇总 PostgreSQL/S3/OpenSearch 非本机 runtime 配置、最小权限模板、migration artifact URI、真实数据 smoke、容量 baseline、备份恢复、PostgreSQL connect/query、S3 put/get/checksum 和 OpenSearch bulk/search smoke artifact URI；内联 migration/smoke payload 只作为指标摘要，不能替代外部 artifact；本机路径、`file://` 和 `local://` 不会被视为生产归档证据；接口不执行压测或连接外部后端
  - 待做：S3/OpenSearch/PostgreSQL 真实环境压测、容量和延迟基线、备份恢复演练
  - 验收：真实环境 smoke test、容量 baseline、恢复演练记录和最小权限策略样例齐备

- `BLOCKED` T-405 美股 13F 与披露事件流水线
  - 对应：E5-US4, E7-US2, E7-US3, E8-US1
  - 已有：InstitutionalHolding、`/api/13f/holdings`、`/api/13f/crowding/update`、DisclosureEvent、`/api/disclosure-events/classify`、8-K/6-K/20-F 事件模板、管理层变更/指引/重大协议/资本配置标签、事件严重性标签、事件 evidence 链接、dashboard 事件墙、图谱事件边、PostgreSQL 视图、持久化测试
  - 已有：`/api/13f/holdings/changes` 可按 filer/issuer/security 输出 13F 新建、增持、减持、清仓及 shares/value 变化，用于拥挤度时间序列和候选池风控输入
  - 已有：`/api/13f/candidate-pool` 可按 issuer/security 聚合 13F 持仓价值、filer breadth、净增减持、crowding score、FIGI/ISIN/ticker 映射和映射置信度，输出候选池排序与风控标签，且固定 `automation_allowed=false`
  - 已有：`/api/disclosure-events/performance` 可按事件窗口计算披露后 1/5/20 天或自定义窗口的公开行情收益、基准收益和超额收益，并回写 `post_event_performance` 供事件墙、图谱和复盘使用
  - 已有：`/api/disclosure-events/classify` 可识别并回写 8-K 常见 `item_code` / `item_title`（1.01、2.02、2.05、5.02、7.01、8.01），用于事件墙和复盘分组
  - 已有：`/api/13f/filings/parse` 可解析 SEC 13F information table XML，支持直接 body、document_id 或 source_uri 拉取，按 CUSIP/FIGI/ISIN/EntityMapping 导入可映射持仓，并输出 unmapped 队列；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 已有：`/api/13f/filings/batch-parse` 可批量跑 13F information table 样本并输出 `mapping_rate`、`mapping_counts`、未映射清单、逐 filing 错误和导入汇总，作为大样本映射验收入口
  - 已有：`GET|POST /api/13f/filings/mapping-readiness` 可接收 batch parse 结果或汇总数字，按真实大样本 filing/row 数、mapping rate、failed/unmapped rate、batch artifact URI、CUSIP/FIGI/issuer gold mapping URI 和 unmapped review queue URI 输出验收 gate；即使 unmapped 队列为空也要求已复核空队列 artifact；小样本不会被误判为通过
  - 待做：真实 Form 13F 大样本执行记录、CUSIP/FIGI/issuer 大样本映射准确率达标验收 artifact URI
  - 验收：13F 只用于中低频拥挤度与反身性风控，不直接触发交易；事件必须可回链到 filing/evidence

- `BLOCKED` T-406 三市场主体页和知识图谱生产化
  - 对应：E3-US2, E3-US4, E8-US2
  - 已有：EntityMapping、LEI/FIGI/CIK/ISIN/ticker 字段、`/api/entity-mappings/batch`、`/api/entity-mappings/quality-report`、A/H/U 批量映射入库、样本映射准确率报告、基于标识符完整度的实体消歧 confidence、低置信映射清单、`/api/graph/query` 按 issuer/security/evidence/thesis/decision 聚合主体、证券、公开行情、公司行动、文件、证据、观点、信号、决策、纸面执行意图、复盘、回放、例外、research card、13F、crowding、challenger、disclosure event 和派生 `portfolio_positions`，并返回带时间/来源属性的图谱边
  - 已有：`/api/graph/traceability-report` 可检查 thesis、decision、research answer 是否能回溯到 evidence/document，并输出缺失 evidence、document、signal/thesis 断链和英文原文缺失问题
  - 已有：EntityMapping 双时间轴版本字段 `valid_from` / `valid_to` / `recorded_at` / `supersedes_mapping_id` / `status`，`GET /api/entity-mappings` 支持按业务生效时点和记录时点查询，quality report 输出版本覆盖率和重叠清单
  - 已有：知识图谱主体页新增 Entity Mapping 双时态面板，可按 issuer、`valid_at`、`recorded_at`、status 查询映射版本，并展示 accuracy、版本覆盖率、时间重叠、低置信映射和 label mismatch
  - 已有：`GET|POST /api/entity-mappings/readiness-report` 汇总 A/H/U 覆盖、人工金标准确率、双时间轴版本覆盖率、低置信/重叠/mismatch、图谱回溯率、edge 元数据覆盖、Neo4j/Qdrant 非本地 endpoint 和真实批量映射/主体页/adapter artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：ADR/中概队列真实批量映射执行记录、主体页生产浏览器验收 artifact、Neo4j 图谱 adapter 外部同步 artifact、Qdrant 向量检索 adapter 外部同步 artifact
  - 验收：A/H/U 样本公司映射准确率 >= 98%；观点到证据可回溯率 >= 95%；节点/边具备来源、时间戳和版本

- `BLOCKED` T-406A 宏观主题、热点扩散和产业链公司定位图谱
  - 对应：E3-US2, E5-US1, E5-US2, E7-US2, E8-US2；愿景扩展/生产化增强
  - 目标：从宏观变量、政策、技术周期、产品热点或市场热词出发，自动/半自动发散到产业链节点、上下游关系、相关公司和数据槽位
  - 已有：`MacroTheme`、`IndustryChain`、`ChainNode`、`CompanyPosition` 数据结构；`/api/macro-themes`、`/api/industry-chains`、`/api/company-positions`、`/api/industry-chains/{chain_id}/companies`、`/api/hotspots/expand`、`/api/company-positions/coverage-report` 契约和后端落地；产业链 taxonomy version；图谱节点和边的 provenance、confidence、时间戳、证据回链
  - 已有：`/api/company-positions/schema` 输出公司定位卡字段字典、必填数据槽位和 data_quality 枚举
  - 已有：`/api/hotspot-lexicons` 可维护热点扩散词表、同义词、相关链路节点和默认数据槽位；`/api/hotspots/expand` 输出 `retrieval_recall` 和 `evidence_layers`，把公告/证据事实、研报观点、行情线索、facts、opinions、inferences 和 needs_verification 分开
  - 已有：热点扩散本地可解释排序 `ranked_candidates`，综合词表命中、公司定位字段覆盖、evidence 回链、公开资料召回和数据质量，并输出 LLM rerank 触发建议
  - 已有：ResearchTask 队列、`/api/research/tasks`、`/api/research/tasks/from-hotspot`、`/api/research/tasks/{task_id}/status`
  - **已完成（本轮）**：`_hotspot_retrieval_recall` 检索召回增强（T-406A 代码层）
    - 同义词/词表扩展：自动从 `HotspotLexicon.synonyms` 和 `related_chain_nodes.keywords` 扩展查询词集
    - 新增 `inferences` 层：thesis/signal 召回独立分层，强制标注 `automation_allowed=false`、`needs_verification=true`
    - 新增 `research_answer` 召回：纳入 `research_opinions` 层，带 `needs_verification`/`pending_review` 标记
    - `term_coverage` 分数：每条结果增加覆盖率浮点分，结果按分数降序排列；新增 `query_expansion` 元信息
    - `_hotspot_evidence_layers` 同步接入 `inferences` 层，含 thesis/signal 推断标注
    - `_hotspot_rank_candidates` 修复：跳过非 list 的 `retrieval_recall` 键（如 `query_expansion`）
  - 已有：`/api/search/semantic/llm-rerank` 接入已审批 `llmtpl_search_rerank_v1`，可对语义候选执行 LLM ordering assist；无 LLM key、上游失败或输出不可解析时自动回退本地可解释排序，返回 `llm_run`、`fallback_used`、`parse_error`、`rerank_source` 和人工复核边界
  - 已有：研究工作台新增“热点扩散”面板，可调用 `/api/hotspots/expand` 展示 chain nodes、ranked companies、evidence layers、research tasks 和 `not trade signal` 边界
  - 已有：`/api/hotspots/expand` 支持 `page_size` / `page_token` 分页元数据，`/api/research/tasks/from-hotspot` 可跨页固化完整 research task 队列，`/api/research/tasks/from-hotspot/batch` 可批量处理多热点且保持幂等
  - 已有：`/api/search/semantic/llm-rerank/benchmark` 可对 LLM ordering assist / local fallback 执行离线质量评估，输出 top1、coverage@k、MRR、fallback rate、parse error rate 和逐样本排序明细
  - 已有：`GET|POST /api/hotspots/readiness-report` 汇总词表命中、三层产业链扩散、公司定位 slot/evidence 覆盖、facts/opinions/inferences/needs_verification 分层、缺口 research task 固化、图谱 edge 元数据、LLM rerank 离线评估摘要和 artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：用真实大样本 query/gold refs 跑 LLM rerank 质量评估并归档报告；所有输出已区分事实、观点、推断和待验证任务
  - 验收：给定一个热点词能生成至少 3 层产业链扩散路径；每个候选公司都有明确产业链节点、角色定位、至少一个数据槽位和证据/来源边界；缺失证据会进入 research task，而不是被当成结论；输出固定 `automation_allowed=false`

- `DONE` T-406B 瓶颈研究模块自动化与验证闭环
  - 对应：E3-US2, E5-US1, E5-US2, E6-US3, E6-US4, E7-US2, E8-US2；愿景扩展/生产化增强
  - 目标：面向没有系统分析基础的普通投资者，把 @aleabitoreddit / Serenity 式 bottom-up chokepoint research 固化为 AI 辅助研究流水线，帮助用户从终端需求、价值链、供应链、监管/许可、渠道和利润池出发，寻找可验证的不对称机会；模块只做研究辅助和模拟组合输入，不输出真实交易建议，不接真实券商，不承诺收益
  - 已有：前端“瓶颈研究”工作台、跨行业 playbook、核能/核燃料链模板、AI 提示词模板、来源台账、事实审计、问题窄化、价值链映射、Chokepoint 排名、Thesis 草稿、验证与证伪等前端内存流水线；UI 可展示当前步骤、阶段输出、问题清单和调优入口
  - **已完成（本轮）**：新增 `ChokepointResearchRun` 持久化模型和 `chokepoint_research_runs` collection，保存 run、7 步流水线、step 输入、LLM 输出、summary、evidence quality、issues、调优记录、review snapshot、validation context、`automation_allowed=false` 和 `live_execution_allowed=false`
  - **已完成（本轮）**：新增 `/api/chokepoint/runs`、`/api/chokepoint/runs/{run_id}`、单步运行、流水线运行、人工复核和 verification tasks API；运行步骤会调用 approved `llmtpl_chokepoint_step_v1` 并关联 `LLMTaskRun`
  - **已完成（本轮）**：后端验证层汇总公开行情/K线、公告/财报 evidence、研报观点 evidence、知识图谱回链和已有 ResearchTask；K线只用于市场定价验证，研报只进入 opinions，公告/财报/监管 evidence 才进入 facts
  - **已完成（本轮）**：证据门禁会识别无 URL 来源台账、投资建议越界、思维链输出、unknown/needs_verification、推断过多和 LLM fallback；问题可固化为幂等 `ResearchTask`
  - **已完成（本轮）**：UI 从前端内存流水线升级为后端 run 状态，支持新建研究、保存档案、继续历史研究、运行当前步骤、运行流水线、暂停、重跑、提交人工复核、生成验证任务和验证资源面板
  - **已完成（本轮）**：新增流水线结论层；7 步完成后自动生成 `conclusion`、刷新验证资源、幂等固化验证任务，并在 UI 展示状态、Thesis 强度、置信度、证据缺口、关键瓶颈、催化剂、证伪条件和下一步动作；LLM 限流/失败时保留规则结论并标记 fallback
  - 文档：`docs/chokepoint-research-module.md`
  - 验收：给定一个行业或主题，系统能自动生成可复核的来源台账、价值链地图、瓶颈候选排名、催化剂时间线、反方论点、证伪条件和待验证任务；所有结论能区分事实、推断、投机和未知；所有输出固定 `automation_allowed=false`、`live_execution_allowed=false`，不得把 AI 输出、社交媒体或研报观点直接当成核心事实或投资建议

- `DONE` T-406C 瓶颈研究真实样本质量包与可复验基线
  - 对应：E3-US2, E4-US1, E5-US1, E6-US3, E8-US2；愿景扩展/生产化增强
  - 目标：把瓶颈研究从“能生成流水线”推进到“能用真实主题复验质量”。优先选择 5-10 个真实赛道/主题样本，例如核燃料链、AI 数据中心电力、CPO/光模块、药械审批、稀缺材料和消费渠道入口，批量跑完整 7 步流水线并归档质量报告。
  - **已完成（本轮）**：新增 `scripts/local_chokepoint_quality_package.py`，内置 5 个真实主题样本模板，自动创建/运行 chokepoint run，导出 `sample-manifest.json`、`run-results.json`、`manual-review-seed.json`、`quality-summary.json` 和 `quality-package.json` 本地产物；输出固定 `automation_allowed=false` / `live_execution_allowed=false`
  - **已完成（本轮）**：形成首版本机质量基线口径，汇总 URL 覆盖率、confirmed run rate、unknown run rate、verification task 生成率、fallback 率、边界违规率、平均 URL/confirmed/verification task 数，并保留人工复核关闭率占位
  - **已完成（本轮）**：质量包脚本支持 `manual_review_input` 导入，接受内联对象、`.json` 或 `.jsonl`；会按 `sample_id` 合并人工复核到 `manual-review-seed.json`，并汇总 `manual_review_close_rate`、`manual_review_sample_coverage_rate`、`manual_review_issue_count`、`manual_review_summary.review_status_counts`、`manual_review_summary.issue_counts`
  - **已完成（本轮）**：新增 `docs/examples/chokepoint-manual-review-baseline.jsonl`，把 5 个真实主题样本推进为可复验的本地人工 review 基线，label 粒度覆盖 `confirmed` / `inferred` / `speculative` / `unknown`
  - **已完成（本轮）**：脚本增加 `--use-bundled-manual-review-baseline`，可在不额外提供输入时直接复现版本化人工 review 基线，并导出 `manual_review_ready_for_local_baseline`
  - 验收：质量包能在本机一条命令重跑；至少 5 个真实主题样本有完整 run、结论、验证任务和人工标注摘要；所有样本输出保持 `automation_allowed=false` / `live_execution_allowed=false`

- `DONE` T-406D 瓶颈研究结构化结论、评分模型和证据门禁
  - 对应：E3-US2, E5-US1, E5-US2, E6-US3, E8-US2；愿景扩展/生产化增强
  - 目标：把 `conclusion` 从可读文本升级为结构化研究档案，明确区分核心事实、推断、投机、未知、证伪条件和下一步验证，并引入可解释 chokepoint 评分模型。
  - **已完成（本轮部分）**：`conclusion` schema 已固定输出 `core_facts`、`inferences`、`speculations`、`unknowns`、`falsification_conditions`、`next_verification_tasks`、`evidence_gaps`、`market_pricing_context`、`falsification_status` 和 `usage_boundary`。
  - **已完成（本轮部分）**：结构化结论会把事实层 evidence、推断/投机 step 输出、unknown 缺口、行情验证上下文和验证任务状态拆开；研报/观点仍不升级为核心事实。
  - **已完成（本轮）**：新增 `chokepoint_scorecard`，覆盖供应集中度、切换成本、供给扩张周期、客户依赖、监管/认证壁垒、利润池错配、催化剂可验证性 7 维，每个维度输出分数、置信度、evidence refs、证据缺口和可读 rationale。
  - **已完成（本轮）**：新增 `source_gate`，`core_facts` 必须同时具备 evidence、document 和 URL 回链；未通过硬门禁的事实不会进入核心事实区，研报/观点仍只能停留在 opinions/clues。
  - 验收：任一 run 的结论可机器读取并追溯到证据或验证任务；无来源事实不会进入核心事实区；评分不是裸数字，而是可解释的 evidence-backed scorecard。

- `DONE` T-406E 瓶颈研究验证任务闭环与复盘反馈
  - 对应：E5-US1, E5-US2, E6-US4, E7-US1, E8-US1；愿景扩展/生产化增强
  - 目标：让瓶颈研究从“一次性 AI 报告”升级为可持续复盘的研究档案。验证任务关闭后应反向刷新 run 的结论、置信度、证据缺口和证伪状态。
  - **已完成（本轮部分）**：`ResearchTask` 关闭状态会被 `finalize` 汇总到 `verification_tasks.open_count/closed_count/status_counts/completion_rate`，并刷新 `unknowns.verification_status`、`thesis_strength_score` 和 `falsification_status`。
  - **已完成（本轮部分）**：瓶颈研究 UI 新增验证任务表、已关闭任务计数、证伪状态和“标记完成/忽略”操作，操作后自动刷新结论。
  - **已完成（本轮）**：结构化结论新增 `review_feedback`，汇总验证任务关闭率、open/closed 计数、行情上下文数量、paper-only 模拟反馈数量和下一步复盘动作。
  - **已完成（本轮）**：结论继续展示关键催化剂、证伪条件、市场定价上下文、证据缺口和下一步动作；验证任务关闭后 `finalize` 会幂等刷新结论、证伪状态和复盘摘要。
  - 验收：关闭验证任务后，run 结论能幂等刷新；被证伪的 thesis 不会继续显示为 ready；复盘档案可展示当时假设、后续证据和模拟反馈，不触发真实交易。

## 历史能力与兼容附录 / M7 经营驾驶舱和投研闭环

- `BLOCKED` T-407 CEO Dashboard 与 UI 图对齐验收
  - 对应：E6-US5, E7-US1, E7-US2, E7-US3, E8-US2, E9-US1
  - 已有：左侧信息架构补齐“总览、数据中台、研究工作台、Agent 协作、策略实验室、投委会、风控合规、CEO 看板、知识图谱、系统治理”；顶部 A/H/U 市场、研究、风险、冲突证据和高优先级事件状态；SEC/披露时间线、8-K/6-K/20-F 事件墙、13F crowding 热图、公司行动摘要、风险治理、系统状态；UI 静态验收脚本检查导航、顶部状态、关键面板 ID 和前端脚本语法
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究工作台闭环
    - `/ui` 研究工作台已从单纯检索页改为单标的闭环控制台，前置 ticker/CIK/form/limit、一键运行、阶段进度、证据列表、研究摘要、投委会 Pack 和模拟反馈，辅助检索下沉到闭环结果之后
    - UI 与浏览器验收显式展示 `Realtime SEC` / `Fallback sample`、`simulated only`、`no broker execution`，减少把纸面模拟链路误认为真实券商执行的风险
    - 后续保留：多标的批量队列、生产 UI 分页/过滤/错误恢复/权限态细化
  - 已有：投委会 UI 新增“异常审批面板”，可对 Decision Pack 做人工签字、创建 open exception、刷新风险队列，并展示 approval state、signature count、open exceptions、pending decisions 和 `human approval · no broker execution` 边界；浏览器验收覆盖桌面/移动非空截图和关键文案
  - **已完成（本轮 UI 联动修复）**：总览收益卡、组合权重、研报观点证据、数据来源、产业链和公司定位已补齐点击联动，可自动切换到数据中台、研究工作台、知识图谱、热点扩散或投委会并带入上下文；`loadDashboard()` 已拆成最新分析快渲染和慢看板补全，避免慢接口导致首屏“点不动”
    - 新增 `scripts/ui_interaction_acceptance.py`，用 Headless Chrome + DevTools Protocol 真实点击 7 条关键链路：收益卡到行情、研报证据到研究检索、公司定位到图谱、产业链到热点扩散、组合方案到最新投委会方案；2026-05-22 本机运行 `status=passed`、`failure_count=0`
  - **已完成（本轮）**：UI 上线 readiness 细粒度验收门槛
    - `/api/readiness/ui-report` 已把真实数据量、分页、过滤、错误恢复、权限态、文本无重叠、视觉无溢出和跨浏览器矩阵覆盖拆成独立 gate；跨浏览器覆盖必须从 metrics 解析出足够 browser family 与 desktop/mobile viewport，artifact URI 不能替代矩阵内容
    - `scripts/ui_cross_browser_matrix_check.py` 可校验真实跨浏览器矩阵：至少 2 个 browser family、desktop/mobile viewport、必备 UI 文案、无 missing text 和 failure
    - `scripts/staging_acceptance.py` 默认只写入 Headless Chrome `production_ui_screenshot_acceptance`；只有传入已校验矩阵时才回填 `cross_browser_acceptance`
  - 待做：在非本机生产/预发真实数据量下执行分页/过滤/错误恢复/权限态、文本无重叠和视觉无溢出复核，并归档跨浏览器矩阵 artifact URI
  - 验收：桌面和移动端截图验收通过；关键视图在真实数据量下无卡死、无明显溢出、无权限越界

- `BLOCKED` T-408 月报/回放生产化和真实绩效归因
  - 对应：E8-US3, E7-US1
  - 已有：月报草稿/发布状态、CEO/CIO/风险合规发布审批、`/api/operating-reports/{report_id}/publish`、红灯项逐条审计、`/api/portfolio/transactions` 交易流水 ledger、`/api/portfolio/positions` as-of 持仓派生 adapter
  - 已有：`/api/portfolio/returns` 支持按 market/currency/industry/style 输出组合收益分组归因；`/api/operating-reports/{report_id}/board-pack`；`/api/strategy-replays/compare`
  - **已完成（本轮）**：`POST /api/portfolio/attribution/backfill`（T-408 代码层）
    - 对纸面/模拟组合执行 market/currency/industry/style 分组绩效归因批次回填，写入 OperatingReport.annotations
    - 固定 `simulation_only=true`、`live_execution_allowed=false`；支持 `dry_run=true` 只计算不写入
    - 支持 `proposal_id` 引用已有 PortfolioProposal 或直接传 `holdings` 列表
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`GET|POST /api/portfolio/attribution/readiness-report` 可汇总月报归因注释、发布审批、红灯项 owner/due、策略回放复盘、模拟 ledger 来源边界、forward attribution 结果与外部 artifact URI、绩效 reconciliation、ledger extract、strategy replay 和 board pack 外部 artifact URI；本地 board pack 导出只作为审计事件，不能替代归档 URI；固定不接真实券商账户
  - 待做：真实生产/预发绩效 reconciliation、NAV/ledger 对账、board pack artifact 和大样本回放验收 URI 归档
  - 验收：月报草稿不能绕过审批发布；绩效指标可由公开行情收益、模拟持仓 ledger 或 NAV 序列复算；每个红灯项有 owner 和截止时间；不接入真实交易账户

- `BLOCKED` T-409 Black-Litterman、风险预算和组合约束原型
  - 对应：E5-US3, E6-US1, E7-US1, E8-US3
  - 已有：`docs/portfolio-construction-spec.md` 数学规格、PortfolioProposal、`/api/portfolio/optimize`、`/api/portfolio/proposals`、观点置信度与 `Omega` 绑定、市场/行业/主题/币种预算、禁投清单、单证券上限、walk-forward 与压力测试诊断、协方差矩阵诊断
  - 已有：`/api/execution-intents/{intent_id}/simulate` 只对已审批纸面执行意图生成模拟成交，写入 `SimulatedExecution` 和 `PortfolioTransaction` ledger，并固定 `live_execution_allowed=false`
  - **已完成（本轮）**：`POST /api/portfolio/simulated-feedback`（T-409 代码层）
    - 投委会审批入口：对 PortfolioProposal 做模拟决策（approved/rejected/pending/needs_revision）
    - 支持 `include_valuation=true` 触发模拟持仓估值、`feedback_start/end_date` 触发区间归因反馈
    - 固定 `simulation_only=true`、`live_execution_allowed=false`、`automation_allowed=false`、`usage_boundary=paper_portfolio_simulation`
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`/api/portfolio/optimizer/compare` 可对候选组合与 equal-weight / prior / posterior / external solver 权重做纸面对照，并输出约束报告与诊断摘要；`/api/portfolio/forward-report` 可生成纸面前向跟踪报告、active return、tracking error、information ratio 和 review flags
  - 已有：投委会 UI 新增“组合模拟审批”，可加载 PortfolioProposal、选择 approved/rejected/pending/needs_revision，调用 `/api/portfolio/simulated-feedback` 并展示 proposal status、paper/no-broker 边界、模拟估值和区间反馈
  - 已有：`/api/portfolio/optimizer/compare` 可通过 `run_external_optimizer=true` 尝试调用 CVXPY / PyPortfolioOpt 做纸面外部求解器对照；本机缺少依赖时返回 `external_optimizer.status=unavailable` 和安装/诊断信息，不伪造外部结果
  - 已有：`GET|POST /api/portfolio/optimizer/readiness-report` 可对外部求解器对照结果生成归档验收包，检查 solver 状态、weights、版本、参数、solver/comparison/constraint report artifact URI、内联约束报告和 paper-only 边界
  - 待做：生产环境安装 PyPortfolioOpt/CVXPY 后跑真实外部对照并归档 solver 版本/参数/artifact URI，投委会审批入口生产态细化
  - 验收：候选权重不包含禁投标的；市场/行业预算和单券上限生效；观点置信度影响 `Omega`；输出只作为纸面组合，不直接生成真实交易；后续反馈仅允许模拟成交/模拟持仓 ledger，不接真实券商

- `BLOCKED` T-410 英文原文优先的研究问答与摘要审计
  - 对应：E4-US2, E6-US3, E6-US4, E7-US2
  - 已有：ResearchAnswer、`/api/research/answers`、`/api/research/answers/{answer_id}/review`、英文 evidence 校验、英文原文保留、标准化 citations（evidence/document/page/bbox/source URI/format）、中文摘要链路、summary/prompt/model 版本、来源公开性、人工覆核状态、人工审核通过/驳回、审计日志写入
  - 已有：`/api/research/answers/quality-report` 可输出答案级 evidence/document 回链率、人工复核覆盖率、pending review 队列、截断引用和逐答案问题；默认告警 `alert_research_answer_pending_review` 基于 `research_answer_pending_reviews` 指标触发
  - 已有：`/api/research/answers/summary-benchmark` 可用规则基线评估摘要 evidence/document 回链、英文原文保留、中文摘要长度、版本元数据、人工复核、受限引用边界、过度确定性措辞和英文 anchor 覆盖率
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究闭环已把默认问题“What changed in revenue, services resilience, and key risk factors?”接入英文 SEC evidence、ResearchAnswer citations、中文摘要、prompt/model/version 审计和图谱回链
    - 测试覆盖 research answer、thesis、decision pack 与 graph query 回链到同一 document/evidence
    - 后续保留：真实 LLM 生成与模型回退策略质量评估
  - 已有：`/api/research/answers/filing-qa` 支持交互式 filing 原文问答，按 `document_id` 自动抽取英文 evidence、运行已审批 filing QA 模板或规则 fallback、落库 `ResearchAnswer`，并返回原文、证据表、质量报告、summary benchmark、模型 fallback 状态和 no-trade 边界
  - 已有：研究工作台新增 “Filing 原文问答” UI，可输入 filing document/question/evidence limit，展示 QA answer、English Source、QA Evidence 和 QA Audit；`scripts/ui_static_check.py` 与 `scripts/ui_browser_acceptance.py` 已覆盖该 UI 文本和控件
  - 已有：`GET|POST /api/research/answers/readiness-report` 汇总答案数量、英文 evidence/document 回链率、人工审核覆盖、pending review、summary benchmark、版本元数据、英文 anchor 覆盖、图谱回溯率和真实模型质量/回退对照/summary rubric artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：真实模型调用质量评估、回退策略大样本对照
  - 验收：关键研究问答必须保留英文原文 evidence；中文摘要不能替代原文引用；摘要变更必须记录模型和 prompt 版本

- `BLOCKED` T-411 生产监控、告警和事故闭环
  - 对应：E6-US4, E9-US1, E9-US2
  - 已有：`/api/health`、`/api/metrics`、AlertRule、SystemAlert、AlertNotification、默认告警规则播种、`/api/alerts/evaluate` 指标评估、开放/恢复告警状态、`/api/alerts/notify` 通知 outbox、`/api/alerts/notifications` 查询、risk dashboard 告警计数、解析失败人工复核告警测试
  - 已有：`/api/playbooks/seed` 可播种文档解析失败、数据采集失败、检索降级、LLM 网关失败和权限/敏感数据泄漏五类事故剧本及季度演练计划；`/api/alerts/incidents/create` 可将带 `playbook_id` 的开放告警自动生成 IncidentReport 并回写 `incident_report_id`
  - 已有：`/api/drill-schedules/{schedule_id}/result` 可回写事故演练结果、RCA 摘要、行动项和下一次演练时间，并在事故日历中展示
  - 已有：`/api/alerts/notifications/deliver` 可对通知 outbox 执行 dry-run/execute 发送状态机，写回 provider、attempt、delivered_at、response 和失败原因；`provider=webhook|http|https` 时可向 HTTP(S) target 发送 JSON POST，`provider=email|smtp` 可通过 SMTP 发送 EmailMessage，`provider=slack` 可发送 Slack webhook，并限制非 HTTP(S) target、超时、缺失 SMTP 配置和最大尝试次数
  - 已有：`/api/alerts/notify` 支持 `route_failures` / `failure_routes`，可按 playbook/rule/metric 将采集、检索、LLM、OCR 和 workflow 失败分流到专属 channel/target，并把 provider/max attempts/backoff 写入 delivery policy
  - 已有：`/api/observability/logs/export` 可导出 audit、alerts、workflow 和 notifications 的结构化 JSON 日志；`/api/observability/otel/export` 可生成 OTLP logs JSON payload；`/api/observability/otel/submit` 可把 OpenTelemetry 日志提交写入 outbox 并复用通知发送状态机
  - 已有：`scripts/staging_otel_acceptance.py` 已在本机 staging 直连 OpenTelemetry collector `/v1/logs`、`/v1/metrics` 和 `/v1/traces`，并触发 workflow 告警、通知 outbox 和发送状态机后回填 `otel_collector_drill`
  - 已有：`/api/observability/readiness-report` 汇总结构化日志、OTLP payload、非本机 logs/metrics/traces collector 参数、日志保留策略、collector 后端存储/查询证据、真实外部告警发送记录和交付 evidence URI、事故剧本 owner/SLA/止血/回滚覆盖率和季度演练覆盖率，缺口进入 `missing_requirements`；默认事故剧本已补齐 SLA 与 rollback 动作
  - 待做：接入真实非本机生产/预发 OpenTelemetry collector，并附上后端查询、保留策略执行和真实外部告警送达证据
  - 验收：五类事故剧本均有 owner、SLA、止血动作、回滚动作；季度演练覆盖率 100%；`/api/observability/readiness-report` 无 missing requirements 且对应证据 URI 可追溯

- `BLOCKED` T-412 生产部署 runbook 与验收清单
  - 对应：E1-US3, E6-US4, E9-US2
  - 已有：`.env.example` 环境变量模板、`docs/production-runbook.md`、`scripts/capacity_baseline.py`、密钥注入建议、PostgreSQL/S3/OpenSearch 运维步骤、上线前检查命令、容量/延迟 baseline 命令、备份/恢复、回滚步骤、月度运维检查表
  - 已有：`/api/readiness/capacity-baseline` 可接收容量/延迟基线结果、按阈值自动判定并回填 `capacity_latency_report` readiness 记录和 evidence URI
  - 已有：`/api/readiness/evidence-package` 可生成上线验收证据包 manifest，汇总 checklist、vision gate、owner 修复计划和 PostgreSQL/S3/OpenSearch、OpenTelemetry、Neo4j/Qdrant、OpenLineage/MLflow、KMS/lifecycle executor、生产 UI 浏览器等外部验证矩阵；`/api/readiness/evidence-package/notify` 可把缺失真实证据项写入通知 outbox
  - 已有：`/api/readiness/deployment-report` 可汇总生产/预发环境名称、PostgreSQL/S3/OpenSearch 参数存在性、生产参数 manifest artifact URI、外部密钥管理 provider、密钥轮换证据、备份恢复、容量 baseline、权限红队、合规复核、CEO launch checklist、发布 checklist、灰度计划 artifact URI、回滚计划 artifact URI 和真实券商/自动下单关闭边界；灰度/回滚窗口只作为元数据，不能替代 artifact；接口拒绝 secret/token/password/private_key 等敏感字段且不回显 DSN/密钥值
  - 已有：`scripts/staging_acceptance.py` 可对 staging HTTP 地址执行真实部署 smoke、模拟成交、检索、图谱、metrics、外部依赖配置和可达性检查、Neo4j/Qdrant/OTel outbox 演练，并可只回填真实执行过的 `real_data_smoke_test` 与 `capacity_latency_report`
  - 已有：`docker-compose.yml` 和 `scripts/local_staging_stack.sh` 可在本机启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector、OpenLineage/MLflow HTTP 占位端点和应用服务，并自动跑 staging 验收；已修复镜像源、host/container 环境变量覆盖、PostgreSQL IMMUTABLE 索引、健康检查等待和 `AI_QUANT_HOST=0.0.0.0` 绑定问题
  - 已有：本机 staging 验收通过，状态库为 PostgreSQLStore，对象存储为 S3/MinIO，检索为 OpenSearch，模拟成交通过，图谱回溯 100%，HTTP 容量基线无 breach；PostgreSQL/S3/OpenSearch/OTel/Neo4j/Qdrant/OpenLineage/MLflow 均可达，Neo4j/Qdrant/OpenLineage/MLflow outbox 演练通过，最近一次复验 `p95=114ms`
  - 已有：最终 vision gate 复验通过，`/api/readiness/vision-gate` 返回 `status=ready`、`readiness_checklist_coverage=1.0`、`pending_checklist=[]`，evidence package 返回 `ready_for_launch=true`
  - 待做：真实生产环境参数确认、外部密钥管理系统真实接入、备份恢复演练 artifact、发布 checklist、灰度/回滚演练 artifact URI 归档
  - 验收：上线前检查、备份恢复、容量基线、密钥注入、回滚路径均有记录；`/api/readiness/deployment-report` 无 missing requirements 且不暴露任何真实密钥值

## 观点与研究资产附录 / M8

- `BLOCKED` T-414 公开电话会/转录稿和研报线索引用策略
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
  - 已有：`GET|POST /api/research/citation-boundary/readiness-report` 汇总 canonical source 复核、metadata-only 手工参考、`manual_reference_boundary_review`、本地研报治理、研究问答英文 evidence/source link/人工审核、受限引用长度、红区训练/事实路径隔离和 policy/source review/manual review/research governance artifact URI；即使无手工参考或本地研报资产，也要求 reviewed-empty artifact；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 验收：研报和转录稿默认只作为公开外部观点层或本地人工参考层；非公开、边界不清或禁止自动化的数据不得进入事实真相层、训练层或可执行建议层

- `BLOCKED` T-416 A 股补充数据 connector 引入
  - 对应：E2-US1, E2-US3, E2-US4, E3-US3
  - 输入：`a-stock-data` Apache-2.0 Skill，覆盖通达信/腾讯/东财/akshare/iwencai/同花顺/百度股市通/巨潮等 A 股数据端点
  - 已有：A 股补充 connector 注册表、source definition、rights tag、限速、字段映射、验证状态、错误留痕和最小测试；默认 restricted rights，仅人工参考/补充研究
  - 已有：`/api/connectors/astock/fetch` 支持本地样本行字段归一化、公开网页/API URI 脱敏、rights/provenance 边界评估、blocked/red-zone 合规拦截
  - **已完成（本轮）**：`POST /api/connectors/astock/supplemental/fetch`（T-416 代码层）
    - `AStockSupplementalRegistry` 托管 connector 注册表，已集成 EastMoney Research、Cninfo Announcements、Tencent Valuation、THS Hot Topics、Baidu Concepts、Dragon Tiger List、Unlock Calendar 七个 connector
    - 强制合规标注：`manual_reference_only=true`、`automation_allowed=False`；URI 敏感参数脱敏
    - 空 symbols 时返回空数组（无 HTTP 调用）；blocked connector 返回 423
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`GET|POST /api/connectors/astock/verification-readiness` 可输出 connector 真实验证验收包，检查 verification status、字段样本覆盖、rate limit 声明、allowed use、license/TOS 边界、真实 endpoint 可用性、endpoint 稳定性、调用限制/配额验证、license review 和 field sample artifact URI；本地 sample rows 只用于字段覆盖，不能替代外部样本证据；固定 `automation_allowed=false`
  - 待做：逐项真实验证接口可用性、稳定性、调用限制和许可边界 artifact URI；接入更多真实 HTTP fetch adapter 与各端点字段样本库
  - 验收：外部接口只作为公开补充；红区、边界不清、禁止缓存或禁止自动化的数据只能进入人工参考，不进入自动化链路

- `DONE` T-417 本地研报资产库模块
  - 对应：E2-US1, E2-US3, E3-US3, E5-US1, E6-US2；愿景扩展/生产化增强
  - 输入：本地目录 `/home/xionglei/文档/6大投行研报汇总`，约 22G、11742 个文件，其中 11702 个 PDF，按投行/年份/月组织
  - 已有：本地研报 manifest 扫描、投行/source registry、文件指纹、按需登记为 Document、权限边界、检索入口
  - 已有：`/api/research-reports/{report_id}/extract`、`/api/research-reports/governance-report`、`/api/research-reports/extraction-queue`、`/api/research-reports/mapping-report`、`/api/research-reports/viewpoint-report`
  - **已完成（本轮）**：`POST /api/research-reports/incremental-schedule`（T-417 代码层）
    - 增量扫描：对比 fingerprint，只处理新增/变更文件，跳过已索引未变化的文件
    - OCR 成本控制：`ocr_budget_mb`（默认 200MB）超出预算进入 `deferred` 队列
    - 分批调度计划：`schedule_plan` 按 `batch_size`（默认 50）分批，每批含 `batch_index/report_ids/brokers/estimated_size_mb`，适配 Airflow/Cron/DAG 逐日触发
    - `dry_run`/`execute` 双模式；支持 `broker`/`year`/`scan_limit` 范围过滤
    - `execute=true` 时会先为未入库研报登记本地参考 `Document`，再进入文本抽取；`dry_run=true` 只生成调度计划，不写入研报资产库
    - `usage_boundary` 固定 `local_reference_only_not_training_or_fact_source`
    - `docs/api-contracts.md` 已补充完整契约文档（含字段说明和调度器接入建议）
  - **已完成（本轮全量入库解析）**：本地研报库 11702 份全量完成入库和解析
    - 源目录核对：`find /home/xionglei/文档/6大投行研报汇总 -type f \( -iname '*.pdf' -o -iname '*.txt' -o -iname '*.md' \) | wc -l` = 11702
    - PostgreSQL 状态：`research_reports=11702`、`research_documents=11702`、`research_report_citation evidence=88515`
    - API 状态：`indexed=0`、`ingested=0`、`needs_text_review=0`、`text_indexed=11702`
    - 解析路径：先使用本机 `pdftotext`；空文本 PDF 使用本机 `pdftoppm + tesseract` OCR，语言包 `eng+chi_sim`；未调用外部 OCR 服务，也未上传研报
    - 新增脚本：`scripts/research_report_full_parse.py`，支持 direct PostgreSQL 批量写入、`pdftotext` 抽取和本地 Tesseract OCR fallback
    - 审计 artifact：`artifacts/research-report-completion-audit.json`、`artifacts/research-report-ocr-backfill.json`、`artifacts/research-report-ocr-retry-lowdpi.json`
    - 回归验证：`python3 -m pytest tests/test_system.py -q` 通过，结果为 `158 passed, 36 subtests passed`
  - 验收：研报不能作为事实真相源；不得默认用于训练；所有引用必须回链到本地文件或公开来源、页码/片段和使用边界

- `DONE` T-423 研报解析结果接入完整业务分析和 UI 看板验收
  - 对应：E3-US3, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 目标：在研报全量 `text_indexed` 后，重新跑完整本机业务分析，确认 A 股、美股、产业链、财报、行情和研报 evidence 进入同一条分析闭环，而不是只停留在数据入库
  - **已完成（本轮研报证据闭环）**：`scripts/latest_analysis_run.py` 已重跑本机完整业务分析，新的 `artifacts/latest-analysis/latest-analysis.json` / `artifacts/latest-analysis/latest-analysis.md` 显示 `research_reports=11702`、`research_report_citation_evidence=88515`、`research_answers=1`，A 股/美股行情、组合权重、热点扩散和研报观点证据已进入同一份最新分析产物
  - **已完成（本轮研报边界治理）**：新增研报 evidence 召回审计 `artifacts/latest-analysis/research-evidence-recall-audit.json`，结果 `status=passed`；语义检索和热点扩散均能召回 `research_report_citation`，且热点 evidence layer 已把本地研报固定归入 `opinions/research_opinions`，`research_items_in_facts=[]`
  - **已完成（本轮 API/UI 验收）**：`/api/analysis/latest` 已优先读取当前 `artifacts/latest-analysis/latest-analysis.json` 并输出 `research_evidence`；UI 新增“研报观点证据”面板，展示研报数量、引用证据数量、语义召回、热点召回和边界声明
  - **已完成（本轮浏览器验收）**：`python3 scripts/ui_static_check.py`、`python3 scripts/ui_browser_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-browser-acceptance`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance` 均通过；桌面/移动截图非空，必备文案包含“研报观点证据”，关键点击链路 `failure_count=0`
  - **已完成（本轮回归）**：`python3 -m py_compile app/*.py tests/*.py scripts/*.py` 通过；定向回归 `test_hotspot_expansion_maps_industry_chain_and_company_position` 和 `test_latest_analysis_api_summarizes_local_artifact_for_ui` 通过
  - 输出：最新分析 artifact、研报 evidence 召回审计、UI/浏览器验收 artifact、必要的前端修复记录
  - 验收：最新分析结果包含可回链的公开事实 evidence 和本地研报观点 evidence；UI 可展示分析结论和证据边界；`research_report_citation` 不参与训练、不作为事实源、不触发真实交易

- `BLOCKED` T-418 大模型 / Agent 工作流生产化
  - 对应：E6-US3, E6-US4, E8-US1, E9-US1；愿景扩展/生产化增强
  - 已有：LLM gateway、OpenAI/Anthropic 兼容转发、默认模型配置、调用审计、密钥环境变量注入、任务级 prompt 模板、baseline prompt 审批记录、模型回退策略、规则/上一稳定版本/人工复核降级链、调用成本/延迟/错误率记录、角色和数据域元数据
  - 已有：`GET /api/prompts/changes` 查询 prompt 变更审批记录，Agent 协作 UI 支持创建/审批 prompt 变更和查看 LLM runs/error/cost/budget；默认告警 `alert_llm_cost_budget` / `alert_llm_error_rate` 基于 `llm_tasks` 指标触发
  - 已有：`/api/llm/tasks/review-queue` 可按任务类型、状态、原因和严重级别输出失败/fallback/高风险/超时/超预算 LLM run 的人工复核队列
  - 已有：默认 LLM task template 覆盖研究摘要、研报摘要、filing 问答、challenger、red team 和事故 RCA，并在 `output_schema.acceptance_thresholds` 记录引用、反证、合规风险、RCA 事实/推断分离等验收阈值
  - 已有：Agent 协作 UI 已接入 `/api/governance/permission-matrix`，可按角色、数据域和动作展示 allowed/denied、红区权限和规则覆盖
  - 已有：`/api/llm/tasks/escalations` 可按成本预算、错误率、fallback 率、人工复核 backlog 和逐 run 原因生成 SLA/预算升级项；`/api/llm/tasks/escalations/notify` 可写入通知 outbox，并可复用 HTTP(S) webhook、SMTP email 或 Slack webhook sender
  - 已有：`/api/llm/budget-approvals` 和 `/api/llm/budget-approvals/{approval_id}/decide` 可基于预算类升级项创建 pending 审批、记录 CEO/CIO/风险/ML 负责人决策，并让 approved 且未过期预算进入 LLM metrics 的有效成本预算计算
  - 已有：`/api/llm/budget-approvals/{approval_id}/sync` 可把 approved 预算审批写入外部财务/云预算系统同步 outbox，记录 target、external_system、metadata、delivery_policy，并复用通知发送状态机推进
  - 已有：`GET|POST /api/llm/readiness-report` 可汇总 approved task template、approved prompt 回链、pending prompt、LLM run 追溯、研究答案版本元数据、高风险 thesis challenger 覆盖率、人工复核/升级、预算同步 outbox 记录、预算同步外部 evidence URI 和真实模型/回退质量 artifact URI；接口只生成验收报告，不调用外部模型
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究闭环已落成 `POST /api/research/tasks/sec-single-name/run`
    - 编排复用 SEC ingestion、evidence extraction、ResearchAnswer、research card、scorecard、challenger、decision pack、审批、execution intent 和 simulated execution；实时 SEC 失败时使用确定性本地样例兜底
    - 研究结果保留 `summary_version` / `prompt_version` / `model_version` 与人工复核状态，当前仍以规则摘要稳定兜底，真实 LLM 生成继续作为 T-418 后续任务
    - 权限测试覆盖 analyst/CIO 可运行、未授权角色 403；执行侧固定 `simulation_only=true`、`live_execution_allowed=false`
  - **已完成（本轮本机长期使用口径）**：`scripts/local_ai_capability_acceptance.py` 已对配置后的 LLM gateway 执行真实 OpenAI-compatible chat smoke，返回 `ok`，并把 provider、模型、choice 数、耗时和短响应预览写入 `artifacts/local-ai-capability-acceptance.json`；脚本和 artifact 均不保存 API key 或完整上游响应
  - 待做：真实模型调用质量评估、回退策略大样本对照、生产/预发 LLM gateway smoke 与预算同步 artifact URI 归档
  - 验收：生产 prompt 100% 可追溯；未审批 prompt 变更数 = 0；高风险结论 challenger 覆盖率 = 100%

## 运维/非本机发布附录 / M9 生产基础设施与治理

- `BLOCKED` T-419 图谱 / 向量 / 语义检索生产化
  - 对应：E3-US2, E3-US4, E8-US2；愿景扩展/生产化增强
  - 已有：`/api/graph/query` 关系回查、本地轻量语义检索 adapter、证据/研究卡/研报/问答混合 SearchRecord、权限边界继承标记
  - 已有：语义检索支持 `issuer_id` / `resource_types` payload filter、默认 restricted 结果过滤、显式 `include_restricted`、结果级 `source_boundary` / `rights_tag` / `risk_level` 和 `/api/search/semantic/benchmark` recall@k 质量回归
  - 已有：`/api/search/semantic/rerank` 复用语义召回并输出本地可解释重排分、term coverage、资源权重、restricted boundary penalty 和 Qdrant/reranker adapter 触发条件
  - 已有：`/api/search/rebuild` 可从当前事实层重建全文/语义 SearchRecord 索引，返回资源计数、sync 结果、外部全文失败 fallback 和审计记录
  - 已有：`/api/graph/query` 每条 edge 默认带 `source`、`timestamp`、`version`、`confidence`；`/api/graph/edge-quality-report` 可输出边元数据覆盖率和缺失明细
  - 已有：`/api/graph/neo4j/export` 和 `/api/graph/neo4j/sync` 可导出 Neo4j bulk upsert-compatible node/relationship payload，并写入 graph sync outbox 交给外部 adapter
  - 已有：`/api/search/qdrant/export` 和 `/api/search/qdrant/sync` 可导出 Qdrant points upsert-compatible payload，保留 rights/risk 边界，并写入 vector sync outbox
  - 已有：`/api/search/adapter-sync/retry` 可对 Neo4j/Qdrant sync outbox 的 failed 通知做 dry-run/execute 重试演练，复用通知发送状态机并保留审计
  - 已有：`scripts/staging_graph_vector_acceptance.py` 已在本机 staging 直连 Neo4j/Qdrant，验证 `/api/graph/neo4j/export` 写入 Neo4j、`/api/search/qdrant/export` 写入 Qdrant collection，并覆盖失败 outbox 重试演练；最近一次本机结果为 Neo4j 54 nodes / 76 relationships、Qdrant 7 points、retried_count=2
  - 已有：`GET|POST /api/graph-vector/readiness-report` 可输出图谱/向量外部同步验收包，检查 Neo4j/Qdrant payload 规模、追溯率、edge 元数据覆盖率、rights/risk 边界、非本机 endpoint、同步 artifact URI、批量吞吐 baseline 和失败注入/重试恢复证据；接口不直连外部数据库
  - 待做：真实非本机生产/预发 Neo4j/Qdrant 同步 artifact、批量同步吞吐 baseline 和故障注入恢复证据 URI 归档
  - 验收：观点、持仓、证据可沿图谱回查；结论到证据回溯率 >= 95%；语义检索结果保留来源和权限边界；`/api/graph-vector/readiness-report` 无 missing requirements

- `BLOCKED` T-420 任务编排、血缘和模型治理
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
  - 已有：`scripts/staging_lineage_registry_acceptance.py` 可在本机 staging 通过 OpenLineage/MLflow HTTP sink 直接发送 webhook POST，验证 202 响应、sink 记录和失败后重试再发送
  - 已有：`/api/orchestration/dags/{dag_id}/execute` 内置轻量 DAG 执行器按拓扑顺序运行采集、解析、证据抽取、结构化抽取、索引重建、benchmark sample 登记和 benchmark 执行等白名单任务，支持上游产物占位符、幂等运行、任务状态、output refs、task-level lineage、`task_ids` 选择和 `queues` 队列隔离记录
  - 已有：`/api/orchestration/dags/{dag_id}/backfill` 可按 `run_dates` 或日期窗口生成 deterministic backfill plan；默认 dry-run，不落库；显式 `dry_run=false` + `execute=true` 时按日期登记 queued `WorkflowRun`，保留 `inputs.backfill`、幂等键、任务选择、队列隔离和未选任务 skipped 状态
  - 已有：`/api/orchestration/scheduler-handoff` 可导出外部调度器规划包，汇总 Airflow/Dagster/Cron 推荐、worker pool 队列映射、external sensor 清单、backfill gap 预览、adapter endpoint contract 和缺失真实外部证据项；该接口只做 planning contract，不创建外部部署
  - 已有：`GET|POST /api/orchestration/readiness-report` 可汇总 active workflow、run/retry/replay、dependency graph、SLA/incident、scheduler handoff、OpenLineage/MLflow payload/outbox、approved model artifact coverage，以及真实调度器、worker pool、external sensor、backfill、OpenLineage client 和 MLflow registry 证据 URI；worker pool、external sensor 和 backfill 即使为空/不适用也要求复核 artifact；接口不部署外部系统
  - 待做：Airflow/Dagster/Cron 真实生产部署、外部 sensor 连通性、分布式 worker、生产 worker pool 级队列隔离和大窗口 backfill 演练 artifact URI
  - 待做：OpenLineage/MLflow 真实外部 client sender、真实 registry/catalog 连通性验证和失败重试策略演练
  - 验收：任一解析、特征生产、信号计算和投委会打包均可 replay；失败任务可定位输入、版本、错误和重试记录

- `BLOCKED` T-421 安全、密钥和权限生产化
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - 已有：`scripts/security_check.py` 可检查 `.env` 误提交和常见密钥字面量，测试覆盖误提交场景；source governance report 可检查公开来源 provenance 台账、数据红黄绿分级、字段白名单和缓存期限；audit completeness report 可检查关键审计字段完整性
  - 已有：`/api/governance/data-security-report` 可扫描 document/evidence/research answer 中的邮箱、手机号、身份证样式和 secret/API key 字面量，返回脱敏 snippet 与按类型/来源聚合统计；默认告警 `alert_sensitive_findings` 基于 `sensitive_findings` 指标触发
  - 已有：API 网关会对角色越权访问返回 403 并写入 `permission_denied` 审计事件；默认告警 `alert_permission_denied_events` 基于 `permission_denied_events` 指标触发，risk dashboard 已纳入权限/敏感数据风险
  - 已有：`/api/governance/secret-rotations` 可记录外部密钥管理系统的 rotation metadata、证据 URI 和到期提醒，并拒绝真实密钥值入库；默认告警 `alert_secret_rotation_overdue` 基于逾期记录触发
  - 已有：`/api/governance/permission-matrix` 可从 API 网关授权规则派生角色 + 数据域 + 动作级权限矩阵，输出 allowed/denied roles、public 标记和 red domain 访问汇总
  - 已有：`/api/governance/cache-retention-report` 可扫描 document、本地研报和 PaddleOCR 运行时缓存，输出保留/到期/删除 dry-run、no-cache 违规、外部生命周期执行建议，并通过 `record_run=true` 写入缓存保留执行记录和审计事件；`execute=true` 只形成审批证据，不在应用内物理删除缓存
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execute` 可对已批准 run 执行本进程 PaddleOCR 运行时缓存清理，并把对象存储、搜索索引和研报资产删除输出为外部 handoff 任务
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execution-evidence` 可回填外部对象生命周期、搜索索引清理、KMS/DLP 或运行时缓存清理 executor 的执行证据，把 run 推进到 `executed_outside_app` 并留痕
  - 已有：`scripts/staging_security_acceptance.py` 可在本机 staging 验证密钥轮换 metadata-only、真实密钥字段拒绝入库、公开来源 provenance/字段白名单台账、最小权限 S3/OpenSearch/Postgres 模板、cache retention run、runtime cache executor 和外部 lifecycle/search/KMS-DLP executor 证据回填
  - 已有：`GET|POST /api/governance/security-readiness-report` 可汇总 source governance、audit completeness、敏感数据扫描、permission matrix、真实越权 403/audit 或已通过的 `permission_red_team_test` checklist、secret rotation metadata、最小权限模板、cache retention 外部删除证据和红区训练记录；布尔占位字段不能替代权限红队证据；接口拒绝 secret/token/password/private_key 等敏感字段，固定只记录 metadata 和 evidence URI
  - 待做：非本机生产/预发外部密钥管理系统真实接入、外部 API key 最小权限策略和对象存储/搜索索引外部删除 executor 真实执行证据 URI 归档
  - 验收：红区数据自动入库训练数 = 0；关键动作审计字段覆盖率 100%；越权访问可拦截并留痕；`/api/governance/security-readiness-report` 无 missing requirements

## 运维/非本机发布附录 / M10 愿景验收闸门

- `DONE` T-422 本机 staging 真实验收与上线闸门
  - 对应：E1-US3, E2-US1, E3-US3, E4-US3, E6-US4, E7-US1, E8-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 指标：证据覆盖率 >= 95%；关键研究结论原文回链率 >= 95%；未审批 prompt 变更数 = 0；红区数据自动入库训练数 = 0；高风险结论 challenger 覆盖率 = 100%
  - 指标：A/H/U 样本公司映射准确率 >= 98%；核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；季度事故演练覆盖率 100%
  - 已有：愿景上线闸门报告接口，集中计算证据覆盖率、研究结论回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、实体映射和 benchmark 指标，并明确 `ready/not_ready`
  - 已有：`/api/readiness/checklist` 可写入真实数据 smoke、生产 UI 截图、跨浏览器、容量/延迟、备份恢复、权限红队、合规复核和上线 checklist 的 owner、证据 URI、指标、过期时间，并进入审计日志；vision gate 已纳入 checklist 覆盖率和季度事故演练覆盖率
  - 已有：`/api/readiness/remediation-report` 可将未通过 gate 和 pending/expired checklist 汇总为 owner、priority、建议动作和 evidence 要求，形成上线修复计划
  - 已有：`scripts/readiness_evidence_package_check.py` 可离线校验导出的 readiness evidence package，要求 launch/gate/checklist 全 ready、9 个必填 readiness check、外部验证矩阵 scope 全覆盖，且 evidence URI 是外部归档型引用并指向具体对象或路径；本机路径、服务连接串、只有域名的 HTTP(S) 根地址和 `artifact://local-*`、`artifact://staging-local`、`artifact://local-staging`、`artifact://staging-test`、`artifact://staging-acceptance`、`artifact://demo` 这类本机或样例前缀不能通过；给校验器的导出包必须传 `include_passed=true`
  - 已有：`scripts/full_run_acceptance.py` 可在本地以模拟交易模式跑 operational acceptance，覆盖 health、demo flow、模拟成交、组合流水/持仓、检索、语义检索、图谱、告警、容量基线、readiness 记录和 metrics，但不替代真实生产环境上线证据
  - 已有：`scripts/staging_acceptance.py` 可对真实 staging URL 生成 smoke/capacity evidence URI、触发缺失证据通知 outbox，并保持真实券商/自动下单关闭；本机 `scripts/local_staging_stack.sh` 已跑通全量 staging 依赖验收，并覆盖 Neo4j/Qdrant/OpenLineage/MLflow outbox readiness
  - **已完成（本轮）**：本机 staging 上线验收链路补齐
    - `scripts/ui_browser_acceptance.py` 对 `/ui` 执行 Headless Chrome 桌面/移动截图、必备文案、非空截图检查，并回填 `production_ui_screenshot_acceptance`；`scripts/staging_acceptance.py --cross-browser-matrix <json>` 只有在提供真实跨浏览器矩阵时才回填 `cross_browser_acceptance`
    - `GET|POST /api/readiness/ui-report` 可汇总静态 UI 合约、生产截图/跨浏览器 readiness 记录、browser acceptance metrics、真实数据量/分页/过滤/错误恢复、权限态和文本无重叠/视觉无溢出 evidence URI，形成细粒度 UI 上线缺口报告
    - `scripts/local_backup_restore_drill.py` 对 Compose PostgreSQL 执行 `pg_dump/pg_restore` 到临时库，校验 records/audit_log 计数一致和 schema 存在，并回填 `backup_restore_drill`
    - `scripts/staging_governance_acceptance.py` 执行真实 HTTP 权限红队 403/audit 验证、来源复核记录、敏感数据和审计完整性检查，并回填 `permission_red_team_test` / `compliance_review_record`
    - `scripts/staging_otel_acceptance.py` 直连 OpenTelemetry collector logs/metrics/traces endpoint，触发 workflow 告警联动并回填 `otel_collector_drill`
    - `scripts/staging_vision_gate_acceptance.py` 登记 A/H/U 主体映射人工金标、运行双语 benchmark、播种并回写季度事故演练结果，在非 launch gate 通过后回填 `launch_checklist`
    - `POST /api/entity-mappings/labels` / `GET /api/entity-mappings/labels` 已支持实体映射人工金标持久化，vision gate 可在未传临时 labels 时读取持久化金标计算 `entity_mapping_accuracy`
    - `scripts/local_staging_stack.sh` 已串联 smoke、UI、外部依赖、备份恢复、权限红队、合规复核、OTel collector、benchmark、事故演练和 launch checklist 记录
  - **已完成（最终复验）**：2026-05-16 直接复用现有 Compose 栈运行 `python3 scripts/staging_vision_gate_acceptance.py http://127.0.0.1:8000 --artifact-prefix artifact://local-staging --record-launch-checklist`，退出码 0
    - `/api/readiness/vision-gate`：`status=ready`、失败 gate 数 0、`pending_checklist=[]`、`readiness_checklist_coverage=1.0`
    - `/api/readiness/evidence-package`：`ready_for_launch=true`、`missing_evidence_count=0`、`external_validations=6`
    - 本次回填 `launch_checklist`，最近更新时间 `2026-05-16T12:08:09Z`，evidence URI 为 `artifact://local-staging/launch-checklist.json`
  - **已完成（最终复验补充）**：2026-05-17 全量运行 `bash scripts/local_staging_stack.sh`，并通过端口覆盖避开本机服务冲突，退出码 0
    - `/api/readiness/checklist`：9/9 required checks passed，coverage=1.0；`real_data_smoke_test`、`production_ui_screenshot_acceptance`、`cross_browser_acceptance`、`capacity_latency_report`、`backup_restore_drill`、`otel_collector_drill`、`permission_red_team_test`、`compliance_review_record`、`launch_checklist` 均已回填
    - `/api/readiness/vision-gate`：`status=ready`、失败 gate 数 0、`pending_checklist=[]`
    - `/api/readiness/evidence-package`：`status=ready`、`ready_for_launch=true`、`missing_evidence_count=0`、`failed_gate_count=0`
    - 本次本机复验使用 `artifact://staging-local/...` evidence URI，证明本机 staging 链路可复验；生产发布仍必须替换为真实 staging/production 外部归档 URI
  - **已完成（本轮本机长期使用口径）**：2026-05-17 复用本机 Compose 栈并按端口覆盖运行 `bash scripts/local_staging_stack.sh`，退出码 0；随后运行 `python3 scripts/local_production_audit.py --base-url http://127.0.0.1:8000 --output artifacts/local-production-audit.json`，退出码 0
    - `/api/health`：`status=ok`、`store=PostgreSQLStore`、对象存储 `backend=s3`、检索 `backend=opensearch`、TDX 本地行情、LLM gateway 和 PaddleOCR-VL 均已配置
    - `/api/readiness/vision-gate`：`status=ready`、14 个 gate 全通过、`readiness_checklist_coverage=1.0`
    - `/api/readiness/evidence-package?include_passed=true`：`status=ready`、`ready_for_launch=true`、9/9 required evidence、`missing_evidence_count=0`、`failed_gate_count=0`
    - `local_production_audit`：`status=passed`、`deployment_target=local_only_personal_production`、`strict_production_gate_unchanged=true`；仅保留 graph/vector package 标记与 workflow drill failed run 的 warning，不阻塞本机长期运行
  - **已完成（本轮本机 AI 能力复验）**：2026-05-17 运行 `.venv/bin/python scripts/local_ai_capability_acceptance.py --base-url http://127.0.0.1:8000 --output artifacts/local-ai-capability-acceptance.json`，退出码 0
    - LLM gateway：真实 chat smoke 通过，模型 `qwen3.6-plus`，返回短响应 `ok`
    - PaddleOCR-VL：真实单页 PDF OCR smoke 通过，模型 `PaddleOCR-VL-1.5`，`state=done`、`page_count=1`、返回 `Dummy PDF file` 预览；第二次复验命中运行时缓存
    - 本机 `.venv` 已安装 `requests` 供直接运行 PaddleOCR 示例；验收脚本本身不写入 token、签名结果 URL 或完整模型响应
  - **已完成（本轮本机启动固化）**：新增 `scripts/local_production_stack.sh` 作为日常本机个人生产入口，默认使用 15432/19000/19200/17474/16333/14318/15001/15002 等避让端口，并用 `AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS=5000` / `AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS=5000` 覆盖本机冷启动容量余量；脚本先调用完整 `local_staging_stack.sh`，再自动生成 `local-production-audit` 和可选 `local-ai-capability-acceptance`
    - `scripts/local_staging_stack.sh` 已显式把 app 容器固定为 `AI_QUANT_HOST=0.0.0.0`、PostgreSQL、S3/MinIO、OpenSearch 和容器内依赖地址，避免 `.env` 中单进程本地默认值把 Compose app 带回 SQLite/local backend
    - 2026-05-18 实跑 `bash scripts/local_production_stack.sh` 退出码 0；`/api/health` 中 TDX、LLM gateway、PaddleOCR-VL 均已配置，capacity baseline 无 breach，`local-production-audit` 与 `local-ai-capability-acceptance` 均 `status=passed`
  - 已有：上线验收证据包接口和通知 outbox 可把 M6-M9 剩余真实环境验证项集中成审计 manifest，并明确当前证据包不是生产执行本身，必须回填真实 artifact URI 后才能通过闸门
  - 已有：`scripts/production_task_closure_audit.py` 可审计 `tasks/todo.md` 中剩余 `BLOCKED` / `DOING` 任务，逐项检查代码层 marker、readiness/report/验收脚本是否存在，并把剩余状态区分为 `blocked_external_evidence` 或 `needs_code_work`；当前 17 个开放项均为 `blocked_external_evidence`，不是继续缺代码脚手架
  - **已完成（本轮本机完成审计）**：`scripts/project_completion_audit.py` 现按部署目标分流：默认仍按非本机组织级发布证据判断，显式传入 `--local-production-audit artifacts/local-production-audit.json --local-ai-acceptance artifacts/local-ai-capability-acceptance.json` 时按本机个人生产证据判断；2026-05-22 已刷新 `artifacts/project-completion-audit.json` 和 `artifacts/production-task-closure-audit.json`，当前输出 `status=achieved`、`achieved=true`、`target_mode=local_only_personal_production`、`local_production_ready=true`、`doing_task_count=0`、`needs_code_work_count=0`
  - 已有：`scripts/production_evidence_plan_check.py --require-filled-uris` 会拒绝仍带 `<production-evidence-bucket>` / `<release-id>` 的采集计划，只有 owner 回填真实 staging/production artifact URI 后才允许进入 production closure manifest
  - 已有：`scripts/production_artifact_inventory_check.py` 可从 plan/package/manifest 生成 release artifact inventory 模板，并校验所有证据 URI 都有 sha256、size、environment、producer、owner、content type、retention 和 immutable/object lock 记录；提供 `--bundle-root` 时还能对本地导出的 evidence bundle 做文件存在、size 和 sha256 复验
  - 已有：`scripts/production_evidence_plan_to_manifest.py` 可把已回填 URI 的采集计划映射到 production closure manifest 的 task evidence、readiness checks、storage/security/observability/UI/deployment reports 和 A 股 connector 证据；默认拒绝占位符，且不自动设置 `ready_for_launch=true`
  - 已有：`scripts/production_release_gate.py` 可一键串联 filled plan 校验、artifact inventory 校验、manifest 生成、严格 manifest 校验和可选 `production_closure.py` dry-run/执行；默认缺真实 readiness evidence package、artifact inventory 或真实 URI 时失败，`--draft` 仅用于模板预览
  - 已有：`scripts/project_completion_audit.py` 支持 `--evidence-plan`、`--evidence-package` 和 `--artifact-inventory`，即使 `tasks/todo.md` 全部 DONE，也必须 release gate 通过才会判定目标完成
  - 生产发布边界：在非本机真实生产/staging 环境用真实参数复跑同一验收链路并归档外部 artifact URI；真实生产发布前仍需人工确认密钥管理、灰度/回滚窗口和 CEO 签批边界
  - 验收：本机 staging 全部 gate 已达到验收口径；所有关键失败路径有人工复核或降级；上线评审记录可审计；系统仍固定模拟交易，不接真实券商、不自动下单

## 明确非目标

- `BLOCKED` 自动下单 / 接真实券商
  - 原因：当前愿景是投资分析、公开资料研究、模拟组合和反馈复盘；真实券商接口、best execution、账户合规、交易风控和自动下单均不属于当前系统目标，过早接入会引入不可控损失

- `BLOCKED` 高频/秒级交易
  - 原因：当前系统定位为中低频、公开/已提供数据驱动，不建设低延迟行情和交易基础设施

- `BLOCKED` 边界不清或禁止自动化的实时/non-display 数据进入自动化链路
  - 原因：实时和 non-display 数据必须有清晰公开来源、用途标签、TOS/robots 判断和人工审批；边界不清时只能人工参考

- `BLOCKED` 非公开研报、转录稿或第三方内容用于训练
  - 原因：研报和转录稿默认是公开外部观点层或本地人工参考层，不是事实真相源，也不默认可训练、再分发或派生

- `BLOCKED` 脱离人工审批的仓位调整
  - 原因：PortfolioProposal 只输出纸面组合或候选权重；模拟持仓用于反馈分析，不代表真实调仓

## 里程碑检查点

- M5 `DONE`：MVP 代码主链路可运行，覆盖 A/H/U 公开披露、证据、评分、审批、复盘、事故、UI、健康检查、烟测、LLM 中转和 OCR 备用解析
- M6 `BLOCKED`：生产化事实层代码层已收口；本机长期使用不阻塞，T-402 已由本机质量包证据通过，T-404/T-405/T-406/T-406A 仍等待非本机组织级 artifact URI
- M7 `BLOCKED`：经营驾驶舱和投研闭环代码层已收口；本机长期使用不阻塞，T-407 ~ T-412 仍等待真实大样本/非本机 artifact URI
  - T-408 归因回填接口已落地；T-409 投委会模拟反馈接口已落地
- M8 `BLOCKED`：数据与研究资产扩展代码层已收口，T-414/T-416/T-418 等待真实外部 artifact URI 或后续质量评估；T-417 已完成
  - T-406A 热点检索召回增强已落地；T-416 补充 HTTP connector 框架已落地；T-417 增量调度框架已落地
- M9 `BLOCKED`：生产基础设施与治理代码层已收口；本机 production-like 栈已通过，T-419 ~ T-421 的非本机组织级证据仍作为未来增强
- M10 `DONE`：愿景验收和上线闸门，T-422 本机 staging / 本机长期使用 gate 已 `ready`；非本机组织级生产发布仍进入人工签批和外部证据归档阶段
- 非本机证据分派：`scripts/production_evidence_owner_packets.py` 已把 T-402/T-404/T-405/T-406/T-406A/T-407/T-408/T-409/T-410/T-411/T-412/T-414/T-416/T-418/T-419/T-420/T-421 的外部证据阻塞项按 6 个 owner 分组，生成 17 个任务、81 个 artifact 字段的执行包 `docs/production-evidence-owner-packets.md`；并在 `docs/production-evidence-task-packets/` 生成每任务一份 agent/issue 分派包。该包只是采集指令，不是 release evidence。
- 非本机证据执行计划：`scripts/production_evidence_execution_plan.py` 已生成 `docs/production-evidence-execution-plan.md`，把 6 个 owner 的领取范围、17 个任务 packet、81 个 URI 字段、artifact inventory、strict release gate 和 `production_task_status_finalize.py` 串成 PM 可执行收口流程；该计划仍只是 coordination artifact，不替代真实 release evidence。
- 非本机证据状态面板：`scripts/production_evidence_status_board.py` 已生成 `docs/production-evidence-status-board.md`，当前 6 个 owner、17 个外部证据任务、81 个 artifact 字段均为 placeholder URI，状态为 `waiting_for_external_evidence`；只有全部替换为真实 staging/production URI、通过 artifact inventory 和 strict release gate 后，才允许把对应 BLOCKED 任务改为 DONE。
