# 项目支持文档

## 项目名称

AI Native 虚拟量化基金组织

## 项目背景

现有 `deep-research-report.md`、`deep-research-report-加美股.md` 和 `deep-research-report -next.md` 已经给出战略定位、三市场扩展、治理边界、阶段路线图和下一步研究清单，但缺少统一的项目执行口径，因此本文件用于把研究结论固化为项目边界、角色、验收和管理基线。

## 项目目标

构建一个以公开披露信息、公开/已提供数据和审计留痕为基础的研究增强型投研与组合管理系统，支持 A/H/U 三市场、中低频、人工审批的工作模式。

## 数据来源策略

优先级从高到低如下：

1. 官方公开披露与交易所/监管站点。
2. 本地已提供或已入湖数据，如通达信 K 线库和本地研报资产库。
3. 免费可获取的公开接口与公开网页数据。
4. 仅作为候选补充源的第三方免费数据接口，例如 `a-stock-data` 生态。

约束：

- `a-stock-data` 作为当前生产闭环内的免费补充接口集合，优先登记和使用已批准的 connector，不再扩展新收费源。
- TDX `vipdata` / `vipdoc` 作为本地 K 线主数据来源，优先级高于第三方补充接口，且作为历史/补充数据，不要求每天全量重新下载。当前本机副本来自通达信官方个人行情数据页 `https://www.tdx.com.cn/article/vipdata.html`，已复制到项目内 `data/local/tdx/vipdoc`，避免依赖 `/home/xionglei/下载` 下的临时下载文件；项目不再使用旧本地中间库作为数据源或存储路线。
- 本地研报目录 `/home/xionglei/文档/6大投行研报汇总` 作为本地参考观点层，配合东方财富研报发现、巨潮公告补充和其他免费公开接口形成研报层闭环。
- 任何新来源都必须补齐 provenance、rights tag、使用边界和验证记录。

## `daily_stock_analysis` 免费接口借鉴

已分析 `https://github.com/ZhuLinsen/daily_stock_analysis` 的数据层。该项目采用 provider fallback 体系，主要数据源包括 `efinance`、`akshare`、`pytdx`、`baostock`、`yfinance`、Tushare、Longbridge、TickFlow、Finnhub 和 AlphaVantage。

纳入本项目免费补充候选的接口：

- `efinance` / 东方财富：历史 K 线、实时行情、公司基础信息、所属板块。登记为 `efinance_eastmoney_history`、`efinance_eastmoney_base_info`、`efinance_eastmoney_board`。
- `akshare` / 东方财富、腾讯、新浪封装：A 股/ETF/港股/美股历史行情、实时快照、筹码分布、板块排行、人气榜、涨停池。登记为 `akshare_em_history`、`akshare_em_spot`、`akshare_chip_distribution`、`akshare_hot_rank`、`akshare_limit_up_pool`。
- `baostock`：A 股日线、股票基础表。登记为 `baostock_eod_history`、`baostock_stock_basic`。
- `yfinance` / Yahoo Finance 与 Stooq 兜底：继续只用于美股 EOD/延时行情和外汇兜底，当前 source 为 `yahoo_chart_us_eod`，不提升为生产实时行情授权。
- `pytdx`：只作为通达信公开/本地行情补充候选；本项目主线仍以已复制的 TDX `vipdoc` 本地日线包为准。

暂不纳入自动补充链路的接口：

- Tushare、Longbridge、TickFlow、Finnhub、AlphaVantage：需要 token、注册或商业/准商业额度，当前不符合“不新增外部收费数据源”的约束，只可在用户明确提供授权并完成 source governance 后再登记。
- 新闻搜索和舆情类 Anspire、SerpAPI、Tavily、Bocha、Brave、MiniMax、Stock Sentiment API：需要 key 或第三方服务授权，不能作为本轮免费数据闭环基础。

## 公开基础信息回填状态

本轮已增加并执行 `scripts/backfill_company_fundamentals_public.py`，用于把公开来源中的行业、板块、估值快照和公司详情写入现有 `issuers`、`securities` 和 `company_positions`。A 股使用东方财富公开延迟接口，优先走 `push2delay.eastmoney.com`；美股使用 Nasdaq screener，SEC ticker/exchange 目录可用时补 CIK/交易所，不可用时降级为 Nasdaq 基础信息，不阻塞行业和估值回填。

执行产物：

- `artifacts/company-fundamentals-public-backfill-a.json`
- `artifacts/company-fundamentals-public-backfill-u.json`
- `artifacts/public-company-universe-scope.json`

当前数据库覆盖率：

- A 股自动生产公司宇宙：`5519` 只，`company_positions` 行业缺口为 `0`。
- A 股证券目录仍保留历史、基金、债券、指数、退市和异常代码；其中 `589` 条为 `out_of_scope/review_required`，不进入自动产业链分析。
- 美股证券目录：`5412` 只；其中 `5075` 个 issuer 已补 sector/industry，`5275` 个 issuer 已补估值/公司详情，`5298` 个 issuer 已补 SEC CIK。

字段范围：

- `Issuer`：`sector`、`industry`、`region`、`company_details`、`fundamentals`、`valuation_metrics`、`data_sources`。
- `Security`：`security_type`、`sector`、`industry`、`board`、`listing_date`、`company_universe_scope`、`company_universe_reason`。
- `CompanyPosition`：`revenue_exposure.industry/sector/region/concepts/source_uri`、`valuation_metrics`、`data_quality`。

边界说明：当前补齐的是公开目录、行业/板块、估值快照、上市年份/地区/概念等生产基础画像；完整财报三表、逐季财务指标、主营构成、高管、员工数、注册地址和官网仍需要后续专门 connector 或公告/年报抽取链路补齐。以上数据仅用于本地投研、模拟组合和审计，不连接真实券商，不做自动下单。

## 公开财务摘要回填状态

本轮已增加并执行：

- `scripts/backfill_company_financials_public.py`：A 股使用东方财富公开财务摘要 `RPT_LICO_FN_CPD`，默认按代码保留最新报告期，写入 `Issuer.fundamentals.financial_summary` 和 `CompanyPosition.profit_exposure.financial_summary`。
- `scripts/backfill_us_cik_sec.py`：使用 SEC `company_tickers_exchange.json` 补齐美股 CIK。
- `scripts/backfill_us_financials_sec_companyfacts.py`：使用 SEC `companyfacts` XBRL JSON 补美股财务摘要，支持 `--missing-only`、`--limit`、`--offset`、`--min-market-cap` 和受限并发；当前全量 US issuer 已完成“有摘要或有明确不可得原因”的状态闭环，后续仅在新增证券或刷新财报时补跑。
- `scripts/run_us_companyfacts_batches.py`：顺序执行多个 companyfacts 批次，每批生成独立 artifact 和 manifest，便于断点续跑或后续增量刷新。
- `scripts/company_basic_info_production_audit.py`：统一审计行业、板块、财务、估值、公司详情和 CIK 覆盖率，输出本机生产基础信息门禁。

执行产物：

- `artifacts/company-financials-public-backfill-a-extended.json`
- `artifacts/us-cik-sec-backfill.json`
- `artifacts/us-financials-sec-companyfacts-top50.json`
- `artifacts/us-financials-sec-companyfacts-batch-100.json`
- `artifacts/us-financials-sec-companyfacts-batch-100-ifrs.json`
- `artifacts/us-companyfacts-batches-core/manifest.json`
- `artifacts/us-financials-sec-companyfacts-batch-unavailable-mark.json`
- `artifacts/company-basic-info-production-audit.json`

当前财务覆盖率：

- A 股自动生产公司宇宙：`5523/5523` 条 `company_positions` 已有财务摘要。
- CN issuer：`5616/11986` 已有财务摘要；未覆盖部分主要是 out-of-scope 历史/非公司证券或不进入自动生产宇宙的目录项。
- US issuer：`4945/5412` 已有 SEC companyfacts 财务摘要；`467/5412` 已明确标记为 SEC companyfacts 不可得或缺 CIK；严格未知缺口为 `0`。
- 本机生产基础信息门禁：`artifacts/company-basic-info-production-audit.json` 当前 `ready_for_local_production_basic_info=true`。

美股财务边界：SEC companyfacts 对美国发行人效果较好；脚本已支持 `us-gaap` 与常见 `ifrs-full` 指标。ADR、外国发行人、优先股/多类别证券、特殊基金或缺 CIK 标的若缺少支持指标，会记录 `no_supported_companyfacts`、`HTTP 404` 或 `missing_sec_cik`，并写入 `fundamentals.financial_unavailable=true`；后续 `--missing-only` 批次会跳过这些永久不可覆盖项，不能伪造为已覆盖。远端大 JSON 偶发 `IncompleteRead`，脚本已加入重试；当前全量 US issuer 已达到“有摘要或有明确不可得原因”的审计闭环。

## 本机业务与完成审计状态

最新本机长期运行口径已通过以下审计：

- `artifacts/source-governance-fill.json`：13 个 A 股免费补充 connector 已补 provenance、TOS/robots、用途边界和 2026Q2 复核记录；来源治理覆盖率 `1.0`。
- `artifacts/local-business-acceptance.json`：行情、研报扫描、组合估值/优化、13F/crowding、热点图谱、编排、readiness package 全链路验收 `status=passed`、`failed_count=0`。
- `artifacts/latest-analysis/latest-analysis.json`：A 股 `600000/000001/300750/600519` 与美股 `AAPL/MSFT/NVDA/TSLA/SPY` 最新分析 `status=passed`，包含 `11702` 份本地研报和 `88515` 条受限研报引用证据的观点层召回，仅用于本地投研和模拟组合。
- `artifacts/local-production-audit.json`：本机生产审计 `status=passed`、`ready_for_launch=true`，保留 graph/vector outbox 与历史 workflow drill warning，不阻塞本机长期使用。
- `artifacts/project-completion-audit.json`：部署目标为 `local_only_personal_production` 时 `status=achieved`；剩余 `BLOCKED` 任务均为非本机组织级发布 artifact URI、inventory、签批证据，不是本机代码或数据闭环阻塞。

## 逻辑链条阅读顺序

如果需要按产品主线快速理解当前系统，优先按下面顺序阅读：

1. [`README.md`](../README.md) - 产品入口与本机运行边界。
2. [`docs/logic-map.md`](./logic-map.md) - 四条主线的逻辑总地图。
3. [`docs/logic-chain-overview.md`](./logic-chain-overview.md) - 当前逻辑链条总览地图。
4. [`docs/latest-analysis-chain.md`](./latest-analysis-chain.md) - 最新分析链路总览地图。
5. [`docs/multidimensional-relationship-closure.md`](./multidimensional-relationship-closure.md) - 多维关系链总收口证明。
6. [`docs/personal-research-loop-overview.md`](./personal-research-loop-overview.md) - 个人研究闭环总览。
7. [`artifacts/latest-analysis/latest-analysis.json`](../artifacts/latest-analysis/latest-analysis.json) - 最新分析产物与证据层回读。

本机新增研报的推荐流程：

1. 用户把新研报文件放入宿主机研报目录 `/home/xionglei/文档/6大投行研报汇总/inbox`，可按 `券商/年份/月/文件.pdf` 分层；容器内对应路径为 `/data/local/research_reports/inbox`。
2. 运行 `python3 scripts/research_report_inbox_ingest.py --base-url http://127.0.0.1:8000` 生成 dry-run 增量计划。
3. 确认预算和候选文件后运行 `python3 scripts/research_report_inbox_ingest.py --base-url http://127.0.0.1:8000 --execute` 登记并执行首批解析。
4. 无可抽文本的 PDF/扫描件会进入 `research_report_text_extraction_required` 人工复核队列；可抽文本的 TXT/MD 会生成受限 citation evidence。

该流程只处理本机目录，不自动登录、订阅、抓取或下载外部研报；研报仍保持 `local_research_reference` 边界，不训练、不再分发、不升级为自动事实真相层。

接入边界：

- 上述新增 connector 默认 `manual_reference` / `supplemental_research`，不直接进入自动交易、训练或事实真相层。
- 每个 connector 必须通过 `/api/connectors/astock/verify` 和 `/api/connectors/astock/verification-readiness`，并提供真实 endpoint、稳定性、限速、TOS/robots、字段样本 artifact 后，才允许进入生产补充链路。
- 东方财富、腾讯、新浪等网页接口存在反爬和字段变动风险，必须使用限速、缓存、失败降级和季度复核。

## 全量公司与证券目录口径

当前全量范围拆成两层，避免把 TDX 日线包中的基金、转债、指数、板块序列或历史退市代码误当成公司：

- 证券目录层：保留从 TDX 日线包和公开目录获取到的 A 股证券代码，以及 Nasdaq Trader 官方目录获取到的美股证券代码，用于行情、回测、质量检查和后续补齐。
- 公司产业链层：只把已解析为普通股且已取得公司/发行人名称的 A 股和美股公司纳入 `company_positions`，用于产业链定位、图谱和研究分析。
- 对 A 股，TDX 本地目录作为候选全集；腾讯免费行情名称接口用于补齐发行人中文名；仍无法命中的历史/退市/非公司代码保留在 `securities` 中，但标记为 `company_universe_scope=out_of_scope`。
- 对美股，Nasdaq Trader 官方 symbol directory 作为公司目录主来源，过滤 ETF、基金、权证、rights、units、票据和优先股等非公司类证券。

本机当前全量执行产物：

- `artifacts/full-ahu-universe.json`：A 股 + 美股初始全集导入摘要。
- `artifacts/ashare-name-backfill-tencent.json` 与 `artifacts/ashare-name-backfill-tencent-bj.json`：A 股名称补齐记录。
- `artifacts/ashare-company-universe-classification.json`：A 股公司范围分类结果。
- `artifacts/ashare-company-position-sync.json`：公司定位卡与最新 issuer/security 名称同步结果。

## 研报层闭环

研报层当前以本地研报资产库为主，免费公开 connector 只做发现、交叉验证和人工参考补充；不自动登录、订阅、抓取或下载边界不清的外部研报。

当前已落地的研报相关能力：

- 东方财富研报发现接口，已作为 `eastmoney_research` 补充 connector 注册。
- 巨潮公告接口可作为研报/公告交叉验证来源。
- 同花顺热点、百度概念、龙虎榜、解禁日历等免费 A 股补充 connector 已登记为 `ths_hot_topics`、`baidu_concepts`、`dragon_tiger_list`、`unlock_calendar`。
- 本地研报目录 `/home/xionglei/文档/6大投行研报汇总` 已完成全量扫描、抽取、引用和治理接入。
- 研报抽取、治理、观点、映射、边界复核和新增 inbox 流程已在 `docs/api-contracts.md` 中定义。
- `artifacts/latest-analysis/research-evidence-recall-audit.json` 已验证语义检索和热点扩散可召回 `research_report_citation`，且研报 evidence 固定在观点/参考层。

后续只做质量和运维增强：

- 周期性复验免费 connector 的可用性、限速、TOS/robots 和字段样本。
- 继续用本机 inbox 接收用户提供的新研报，再执行 dry-run 和人工确认后的解析。
- 对外部研报 PDF 自动下载、一致预期或分析师评级等能力，只有在来源公开、许可清晰、用途边界可审计时才作为 `manual_reference` / `supplemental_research` 扩展；不作为当前本机闭环阻塞项。

这些接口都应保持 `manual_reference` / `supplemental_research` 边界，不直接进入事实真相层或训练层。

## 成功标准

- 研究结论可回溯到原始证据。
- 任何调仓建议都可追溯到责任人、版本和审批记录。
- 长线与短线使用不同评分卡和不同 KPI。
- 三市场主体、披露、事件与证券可以统一映射。
- 中英双语披露支持原文定位和摘要审计。
- 系统默认研究增强，不做自动下单。

## 范围

### 包含

- A/H/U 三市场公开披露、结构化财务和公开/已提供 EOD/延时数据接入。
- 公司研究卡、行业研究卡、Thesis Card、证据链和主体知识图谱。
- 长短线双评分卡、13F 拥挤度、事件驱动与反方机制。
- CEO Dashboard、投委会流程、风险审计、提示词审批与留痕。
- 中文公告/年报 benchmark、中英双语抽取基线和事故剧本。
- 免费公开补充接口候选的登记、验证和权限标签管理。

### 不包含

- 完全自动下单。
- 高频/秒级交易。
- 非公开或边界不清研报抓取和复用。
- 边界不清或禁止自动化的实时 non-display 数据使用。
- 未经核验版权的电话会转录和第三方会议纪要。
- 脱离人工审批的仓位变更。

## 项目假设

- 第一阶段优先接入官方披露与公开来源，不处理灰色来源数据。
- MVP 团队规模按 4-7 人估算。
- 研究增强和决策治理优先于组合自动化。
- A/H/U 三市场采用统一治理、分市场执行的方式推进。
- 模型、向量库和工作流框架允许后续替换，但数据与审计对象保持稳定。

## 角色与责任

| 角色 | 责任 |
|---|---|
| CEO | 终审、例外审批、战略边界 |
| CIO | 研究框架、投委会组织、策略协调 |
| PM | 组合建议、再平衡、执行意图 |
| 风险/合规 | 权限、限额、版权、审计 |
| 平台负责人 | 数据、系统、流程与稳定性 |
| 分析师 | 研究卡、证据链、反证材料 |
| 海外研究负责人 | 美股、ADR、中概与双语披露研究 |
| NLP/ML 负责人 | benchmark、抽取模型、反方自动化 |

## RACI

| 工作项 | CEO | CIO | PM | 风险/合规 | 平台负责人 | 分析师 | 海外研究负责人 | NLP/ML 负责人 |
|---|---|---|---|---|---|---|---|---|
| 项目边界审批 | A | R | C | C | C | I | C | I |
| 三市场公开来源治理与准入 | I | C | I | A/R | C | I | C | I |
| 证据链 schema 与知识图谱 | I | C | C | C | A/R | R | C | C |
| 研究卡模板与双语抽取标准 | I | A | C | C | C | R | R | R |
| 双评分卡与 13F 拥挤度口径 | I | A | R | C | I | C | C | I |
| benchmark 与抽取评测 | I | C | I | I | C | C | C | A/R |
| 投委会流程与签字链 | A | R | C | R | C | I | I | I |
| 审计日志与 prompt 审批 | I | C | I | C | A/R | I | I | C |
| 例外事项审批 | A | C | I | R | C | I | I | I |
| 复盘机制与 challenger | I | A | R | C | C | C | C | R |

说明：

- `A` 负责最终拍板。
- `R` 负责直接执行或交付。
- `C` 参与评审或提供输入。
- `I` 保持知情。

## 交付物

- 资料完整性审查文档
- 项目支持文档
- 风险与依赖登记册
- 开发任务书
- PRD
- 需求范围和验收口径
- 风险与依赖清单

## 里程碑基线

| 里程碑 | 目标 | 入口条件 | 出口条件 |
|---|---|---|---|
| M1 | 文档与治理基线 | 研究报告完成 | 范围、角色、验收、任务书齐备 |
| M2 | 公开来源与证据链跑通 | 公开来源 provenance 清单明确 | 三市场研究结论可回链到原始证据 |
| M3 | 研究与评分跑通 | benchmark、研究卡、评分卡可用 | 决策包支持签字、反方和审计 |
| M4 | 复盘与知识图谱闭环 | 决策流程可追踪 | 决策结果可归因、图谱可回查 |

## 验收口径

- 文档齐全且相互引用一致。
- 任务分解可直接进入研发排期。
- 每个关键任务都有负责人、输出物和验收条件。
- 关键边界写清楚，避免自动交易化和黑箱化。
- PRD 能覆盖三市场范围、数据边界、能力清单、阶段目标和验收标准。
- 生产闭环分两层验收：代码层和本机 staging 复验可用 `scripts/local_staging_stack.sh` 完成；非本机真实生产发布仍必须用真实 staging/production artifact URI 回填 evidence collection plan，并提供覆盖所有 evidence URI 的 artifact inventory，再由 `scripts/production_evidence_plan_to_manifest.py` 或 `scripts/production_release_gate.py` 生成并校验 production closure manifest，并通过 readiness evidence package 与 strict manifest 离线校验。

## 关键依赖

- 公开来源 provenance 与 TOS/robots 复核流程。
- 交易所公告、年报、XBRL、SEC EDGAR 等原始资料接入能力。
- 审计日志和权限控制的技术实现。
- CIO、风险和平台三方共同参与的审批机制。
- 双语抽取 benchmark 和三市场主数据映射。

## 沟通与例会机制

- 周例会：同步里程碑、阻塞项和风险变化。
- 投委会评审会：评审研究包、反方意见和风险结论。
- 双周复盘会：检查任务偏差、需求变更和验收状态。
- 月度经营回顾会：统一检查收益、研究质量和治理健康。

## 变更规则

- 任何范围变更都必须同步更新支持文档和任务书。
- 任何权限、合规或数据源变更都必须保留审批记录。
- 任何新增自动执行能力都必须重新评审合规边界。
