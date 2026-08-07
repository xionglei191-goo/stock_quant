# 需求文档：项目可用性改进（每日一键研究主线）

- Status: active
- Owner group: 产品与 UI
- Reviewer groups: 研究与 AI 工作流、平台与质量、治理安全与合规、项目经理 / 发布协调
- Last updated: 2026-07-28
- Related tasks: `tasks/todo.md` 近期优先级（五家公司官方事实缺口、产品使用口径、公司情报分析闭环）；T-605 最新分析热读、T-607 产品使用指标来源分层、T-608 五家公司证据闭环、T-619 研报导入收口
- Scope: 每日主线编排（CLI + UI 单入口）、首屏当日清单、UI 主线收敛、LLM 任务模板与运行记录激活、完整度/覆盖度/新鲜度口径统一、本机证据产物、边界与规范约束
- Non-goals: 不扩大公司覆盖面到全部 10,627 家主体；不接入券商、不做实盘或自动下单；不产出非本机组织级发布证据；不把单页 UI 重写为前端框架；不删除既有脚本、API 路由或数据行

## Introduction

本机 Compose 栈与数据底座已具备生产化形态，但缺少"打开就能用"的每日研究路径：入口分散在 127 个脚本、461 条 `(method, path)` 路由映射（334 条唯一 API 路径）与上百条 README 命令中，已配置密钥的 LLM 与文档解析能力零运行，读数口径在不同响应之间互相矛盾。

本需求把项目可用性收敛为一条主线：一次触发完成 扫市扰动 → 当日候选池 → 自动尽调（调用已配置 LLM 产出可回链证据的观点）→ 今日待研究清单 → 加入关注池；UI 首屏只回答"今天看什么"；同时修正完整度与新鲜度口径矛盾，并把每次运行固化为本机可复现证据。项目既有的 paper-only、不接券商、不自动下单边界保持不变。

## 事实基线（本机实测，作为需求依据）

- 运行态：Compose 9 服务 Up 且核心服务 healthy；`/api/health` 返回 200，store=PostgreSQLStore，对象存储 s3(MinIO)，检索 OpenSearch。
- 凭据齐备：`llm_gateway.configured=true`（qwen3.6-plus）、`document_parser.configured=true`（PaddleOCR-VL-1.5）、`tdx_vipdoc.configured=true`。
- 数据多、分析少（`/api/analysis/latest` 计数）：`market_data=28,382,788`、`issuers=10,627`、`securities=10,627`、`research_reports=9,568`、`research_report_citation_evidence=73,118`、`documents=9,602`、`evidence=75,519`；而 `llm_task_templates=0`、`llm_task_runs=0`、`research_answers=1`、`extraction_results=0`、`disclosure_events=0`、`corporate_actions=0`、`ingestion_jobs=0`、`ingestion_schedules=0`、`manual_reviews=0`。
- 深度内容集中在 5-9 家主体（AAPL、NVDA、MSFT、300750、600519、600000 等）。
- 口径矛盾：`/api/company-intelligence/600519` 同一响应中 `status=complete`、`label=完整`、`score=0.988`、`is_complete=true`，但 `profile_field_coverage_score=0.4167`、`database_coverage_score=0.8462`、`missing_fact_fields` 27 项、`next_actions=[]`；同批公司在 `daily_insight.companies` 中为 `completeness_status=partial`、`missing_layers=[financial_snapshot, disclosure_events]`。
- 时间戳错位：`market_freshness` 中 A 市场 EOD 到 2026-07-24、U 市场到 2026-07-27，而公司活动条目 `latest_market.as_of_date=2026-05-25`。
- 规模与约束：`app/services.py` 31,956 行（受 AGENTS.md §8.1 增长冻结约束）；`app/service_modules/` 已有 33 个模块 8,787 行；`app/api_routes.py` 路由表 461 条 `(method, path)` / 334 条唯一路径（`grep -cE '^\s+\("(GET|POST|PUT|DELETE|PATCH)"' app/api_routes.py`、`grep -oE '\^/api/[^"]*\$' app/api_routes.py | sort -u | wc -l`）；`app/static/index.html` 12,650 行；`app/static/ui_modules/` 已有 T-599 运行期模块化产物（`manifest.json` 标注 `status=runtime-partial`，`dashboard.mjs` 与 `helpers.mjs` 为运行期加载模块，`company/graph/market/admin` 为 scaffold），并由 `scripts/ui_static_check.py` 与 `node scripts/ui_dashboard_module_check.mjs` 双向约束。
- 路由数量为易漂移基线，所有可达性护栏一律用"变更前路由快照 ⊆ 变更后路由表"的子集断言表达，不硬编码数量。
- 可复用落点：UI 导航已有"个人研究 / 后台维护"双模式与 6 个个人侧入口；首屏已有 quick-start 卡片与 `data-action="seed-demo"`；`scripts/daily_market_insight.py` 已产出 daily insight；`/api/llm/task-templates/seed`、`/api/llm/tasks/run`、`/api/personal-research/loop-overview`、`/api/company-database/watchlist/import` 已存在；扫市实测可产出 24 家异动（首位 000670 +10.07%）。

## Glossary

- **每日主线编排器（Daily_Mainline_Orchestrator）**：按固定顺序驱动扫市、候选池、自动尽调、清单生成四个阶段的编排组件，同时被 CLI 入口与 UI 触发入口调用。
- **扫市扰动扫描器（Market_Disturbance_Scanner）**：基于本机行情与热点词表计算当日异动与热点主体的组件。
- **候选池构建器（Candidate_Pool_Builder）**：将扫市结果转换为带排序与入选理由的当日候选集合的组件。
- **自动尽调器（Auto_Diligence_Runner）**：对候选调用已配置 LLM gateway 生成研究观点并回链证据的组件。
- **今日待研究清单（Daily_Research_Queue）**：当日经排序与证据校验后可供人工研究的条目集合。
- **关注池服务（Watchlist_Service）**：维护用户长期跟踪主体集合的组件。
- **首屏总览视图（Overview_View）**：`/ui` 个人研究模式默认打开的总览页面。
- **UI 导航控制器（UI_Navigation）**：控制"个人研究 / 后台维护"模式与入口可见性的前端逻辑。
- **LLM 任务模板库（LLM_Task_Template_Registry）**：`llm_task_templates` 的内置模板集合与写入逻辑。
- **LLM 任务运行记录（LLM_Task_Run_Log）**：`llm_task_runs` 表及其 lineage 字段（`template_id` / `provider` / `model` / `prompt_version` / `latency_ms` / `estimated_*_tokens` / `estimated_cost` / `status` / `fallback_used`）。
- **研究结论存储（Research_Answer_Store）**：`research_answers` 及其与候选、证据的关联关系。
- **完整度口径服务（Completeness_Reporter）**：计算并输出公司完整度状态、覆盖度分值、缺失字段与下一步动作的组件。
- **公司情报视图（Company_Intel_View）**：`/ui` 公司情报页面及其行情新鲜度展示区域。
- **证据产物写出器（Artifact_Writer）**：把编排运行结果写入 `artifacts/` 并附带分类元数据的组件。
- **平台质量门（Local_Quality_Gate）**：`make local-ci` 及追加的 UI、handoff 校验脚本组合。
- **交付 handoff（Delivery_Handoff）**：`docs/agent-handoffs/` 下本任务的移交记录。

## Requirements

### Requirement 1：每日一键主线编排（CLI + UI 单入口）

**User Story:** 作为个人研究者，我希望一次触发就跑完"扫市 → 候选池 → 自动尽调 → 今日待研究清单"，这样我每天不需要在 127 个脚本和 334 条 API 路径之间挑选起点。

#### Acceptance Criteria

1. THE 每日主线编排器 SHALL 提供一个 CLI 入口与一个 UI 触发入口，且两个入口调用同一编排实现。
2. WHEN 用户通过任一入口触发每日主线编排，THE 每日主线编排器 SHALL 按 扫市扰动扫描 → 候选池构建 → 自动尽调 → 今日待研究清单生成 的固定顺序执行四个阶段。
3. WHEN 一个阶段结束，THE 每日主线编排器 SHALL 输出该阶段的 `stage`、`status`（取值 `passed`、`partial`、`failed`、`skipped`）、`started_at`、`finished_at` 与 `record_count`。
4. WHEN 扫市扰动扫描完成，THE 候选池构建器 SHALL 为每个候选输出 `rank`、`selection_reason`、触发指标名、触发指标值与数据 `as_of_date`。
5. WHEN 候选池构建完成，THE 自动尽调器 SHALL 通过已配置的 LLM gateway 为候选生成研究观点，并在每条观点上记录 `llm_task_run_id` 与所用模板标识。
6. THE 自动尽调器 SHALL 为每条生成观点关联至少一条已存在的证据标识（`evidence_id` 或研报引用证据标识）。
7. IF 一条生成观点缺少可关联证据，THEN THE 自动尽调器 SHALL 把该观点标记为 `unsupported` 并置于清单的待补证据分区。
8. WHERE 观点来源为本地研报，THE 自动尽调器 SHALL 把该来源标记为观点层（`viewpoint`），并把事实字段的写入来源限定为官方披露或行情数据。
9. IF 任一阶段失败，THEN THE 每日主线编排器 SHALL 输出该阶段的失败原因码、已完成阶段的结果与建议下一步动作，并把整体 `status` 置为 `partial` 或 `failed`。
10. IF 今日待研究清单条目数为 0，THEN THE 每日主线编排器 SHALL 返回 `status=empty` 与至少一条可执行下一步动作（含命令或 API 路径）。
11. WHEN 用户对清单条目执行"加入关注池"，THE 关注池服务 SHALL 记录 `security_id`、加入时间、来源 `run_id` 与入选理由。
12. WHERE 配置项 `daily_brief_timeout_seconds` 已设置，WHEN 累计运行时间超过该上限（默认 600 秒），THE 每日主线编排器 SHALL 停止后续阶段、返回 `status=partial` 并保留已完成阶段的结果。
13. WHEN 同一日期再次触发编排，THE 每日主线编排器 SHALL 生成新的 `run_id` 并保留上一次运行的清单记录。

### Requirement 2：首屏"今天看什么"

**User Story:** 作为个人研究者，我希望打开 `/ui` 首屏就看到今天该研究什么以及一个可点的按钮，这样我不需要先读文档再决定操作。

#### Acceptance Criteria

1. WHEN 用户打开个人研究模式的总览视图，THE 首屏总览视图 SHALL 在默认呈现区域展示当日待研究清单。
2. THE 首屏总览视图 SHALL 在当日清单区域提供一个触发每日主线编排的按钮。
3. WHEN 首屏读取当日清单，THE 首屏总览视图 SHALL 使用已物化的最新分析读取路径，并保持 p95 响应时间低于 2 秒（沿用 T-605 口径）。
4. WHEN 清单条目被呈现，THE 首屏总览视图 SHALL 对每条条目显示排名、入选理由、证据入口与"加入关注池"操作。
5. IF 当日清单不存在，THEN THE 首屏总览视图 SHALL 呈现空态卡片，并给出触发按钮与对应 CLI 命令文本。
6. WHILE 每日主线编排正在运行，THE 首屏总览视图 SHALL 显示当前阶段名称与已完成阶段数。
7. IF 编排整体状态为 `partial` 或 `failed`，THEN THE 首屏总览视图 SHALL 显示失败阶段名称与失败原因码。
8. THE 首屏总览视图 SHALL 在当日清单区域标注数据 `as_of_date` 与运行生成时间。

### Requirement 3：UI 主线收敛与可达性保持

**User Story:** 作为个人研究者，我希望个人研究模式只保留主线入口、治理类功能下沉到后台维护，这样界面不再让人不知从哪开始，同时既有能力仍可访问。

#### Acceptance Criteria

1. THE UI 导航控制器 SHALL 在个人研究模式下仅呈现主线入口：总览、公司情报、知识图谱、K 线行情、研究结论、模拟反馈与动态配置外链。
2. THE UI 导航控制器 SHALL 在后台维护模式下呈现治理、签批、发布门禁与投委会兼容入口。
3. WHEN UI 导航完成收敛，THE 应用服务 SHALL 使变更前路由快照中的每一条 `(method, path)` 都仍存在于变更后路由表中（子集断言，不硬编码路由数量），且这些路由的响应包装结构不变。
4. THE 收敛改动 SHALL 只调整 UI 呈现层，并保留既有脚本文件、API 路由与已存储数据行。
5. WHEN 用户通过直接 URL 或深链访问已下沉到后台维护的视图，THE UI 导航控制器 SHALL 打开该视图。
6. WHEN UI 呈现契约变更，THE 平台质量门 SHALL 通过 `scripts/ui_static_check.py` 与 `scripts/ui_interaction_acceptance.py`。

### Requirement 4：AI 层激活（模板、运行记录与人工复核）

**User Story:** 作为个人研究者，我希望已配置的 LLM 能力真正参与每日流程并留下可追溯记录，这样密钥与模型配置不再是零运行的摆设。

#### Acceptance Criteria

1. THE LLM 任务模板库 SHALL 提供覆盖候选尽调、证据摘要与风险质询三类任务的内置模板集。
2. WHEN 触发每日主线编排且 `llm_task_templates` 计数为 0，THE LLM 任务模板库 SHALL 幂等写入内置模板集。
3. WHEN 自动尽调器成功调用 LLM gateway，THE LLM 任务运行记录 SHALL 新增一条 `llm_task_runs` 记录，包含模板标识（`template_id`）、模型名（`model`）、prompt 版本（`prompt_version`）、耗时（`latency_ms`）与 token 用量（`estimated_input_tokens` / `estimated_output_tokens`）。`LLMTaskRun` 无独立 `model_version` 字段，"模型版本" lineage 由 `model` + `prompt_version` 组合承载。
4. WHEN 自动尽调产出观点，THE 研究结论存储 SHALL 新增对应 `research_answers` 记录，并关联候选标识与证据标识。
5. IF LLM gateway 调用失败或超时，THEN THE 自动尽调器 SHALL 记录失败原因码、跳过该候选的观点生成并保留该候选池条目。
6. THE 自动尽调器 SHALL 为每条生成观点提供人工复核入口，复核状态取值为 `pending`、`accepted` 或 `rejected`。
7. THE LLM 任务模板库 SHALL 在模板记录中保存 prompt 版本标识，并把凭据与完整上游响应排除在本轮新增的持久化字段（模板记录、清单条目、关注池条目）与写出的 artifact 之外。既有 `LLMTaskRun.output` 持久化上游响应属于既有行为，本需求不改其语义。
8. WHEN 一次编排结束，THE LLM 任务运行记录 SHALL 使该次运行中 `status == "succeeded"` 的 `llm_task_runs` 记录数与网关成功调用次数一致。既有 `run_llm_task` 在 fallback 时同样写入 `LLMTaskRun`（`status` 取 `fallback` / `needs_review` / `failed`），因此成功计数不得按记录总数统计。

### Requirement 5：读数口径一致性修正

**User Story:** 作为个人研究者，我希望完整度、覆盖度与行情新鲜度只有一套口径，这样"完整"不会和 27 项缺失字段同时出现。

#### Acceptance Criteria

1. THE 完整度口径服务 SHALL 仅在 `missing_fact_fields` 为空且各分层覆盖度均达到既定阈值时，把公司完整度状态报告为 `complete`。
2. WHEN `missing_fact_fields` 非空，THE 完整度口径服务 SHALL 把公司完整度状态报告为 `partial` 并列出缺失分层。
3. THE 完整度口径服务 SHALL 使同一公司在公司情报响应与当日清单中的完整度状态取值一致。
4. WHEN 公司完整度状态不是 `complete`，THE 完整度口径服务 SHALL 返回至少一条 `next_actions` 条目，包含目标字段、来源类型与执行命令或 API 路径。
5. THE 完整度口径服务 SHALL 为每个覆盖度分值声明分母定义，包含统计字段总数与已填字段数。
6. WHEN 公司情报视图呈现最新行情日期，THE 公司情报视图 SHALL 使用与 `market_freshness` 相同的市场 EOD 取数口径。
7. IF 公司最新行情日期早于对应市场 EOD 日期，THEN THE 公司情报视图 SHALL 标注滞后天数与滞后原因码。
8. WHEN 每日主线编排生成清单，THE 每日主线编排器 SHALL 对每个候选引用完整度口径服务的状态值，而非另行计算完整度。

### Requirement 6：可复现的本机证据产物

**User Story:** 作为项目经理，我希望每次一键运行都留下可复现证据，这样后续 agent 与复盘能确认当天跑了什么、跑出了什么。

#### Acceptance Criteria

1. WHEN 每日主线编排结束，THE 证据产物写出器 SHALL 在 `artifacts/` 下写出一个包含 `run_id` 与各阶段结果的 artifact 文件。
2. THE 证据产物写出器 SHALL 在 artifact 元数据中记录 producer 命令、生成时间戳（UTC ISO 8601）、环境标识、owner group 与是否含敏感数据。
3. THE 证据产物写出器 SHALL 把 artifact 分类固定为 `local-only`，并把"可用于非本机发布门禁"标记固定为 `false`。
4. WHEN 同一日期重复运行编排，THE 证据产物写出器 SHALL 使用包含 `run_id` 的独立文件名，并保留上一次运行的 artifact 文件。
5. THE 证据产物写出器 SHALL 把凭据、签名 URL 与完整模型响应排除在 artifact 内容之外。
6. THE 交付 handoff SHALL 引用该 artifact 路径及其分类、producer 与环境说明。

### Requirement 7：边界与工程规范约束

**User Story:** 作为治理与合规评审方，我希望可用性改进不越过 paper-only 边界，也不把新逻辑堆进已 31,956 行的 facade，这样后续维护成本可控。

#### Acceptance Criteria

1. THE 每日主线编排器 SHALL 在运行输出中声明 `live_execution_allowed=false`。
2. THE 每日主线编排器 SHALL 把所有持仓与交易相关输出标记为 paper-only 模拟结果。
3. THE 每日主线编排器 SHALL 仅调用项目内已注册的本机服务端点与本地或公开数据源。
4. THE 新增业务逻辑 SHALL 位于 `app/service_modules/` 下的领域模块中。
5. WHERE 需要保持既有 API 兼容，THE `SystemService` SHALL 仅新增 facade 方法或跨模块编排方法。
6. WHEN 变更触及 `app/services.py` 或 `SystemService`，THE 交付 handoff SHALL 包含 `SystemService Growth Freeze Review` 章节。
7. THE 交付 SHALL 通过 `make local-ci`（`py_compile`、`unittest discover -s tests`、`scripts/ui_static_check.py`、`scripts/security_check.py .`、`scripts/check_markdown_links.py`、`scripts/check_handoffs.py`、`scripts/check_doc_metadata.py`）。
8. WHEN `docs/agent-handoffs/` 发生变更，THE 交付 SHALL 单独通过 `python3 scripts/check_handoffs.py`。
9. THE 交付 SHALL 保持既有测试用例断言不变，并使测试总数不少于变更前基线。
10. WHEN API、环境变量、artifact 或 UI 契约发生变更，THE 交付 SHALL 同步更新 `docs/` 下对应文档与 `tasks/todo.md` 状态。

## Assumptions

- 每日主线在现有深度覆盖公司（5-9 家）与扫市异动结果范围内跑通即视为达标，不要求覆盖 10,627 家主体。
- LLM gateway 与 PaddleOCR 凭据在本机 `.env` 中保持可用；需求不包含密钥轮换或外部密钥管理。
- 扫市扰动的指标定义沿用现有实现（涨跌幅等本机行情派生指标），本轮不引入新的付费数据源。
- 首屏 p95 < 2 秒沿用 T-605 已建立的最新分析物化热读路径，不要求新增缓存层。

## Open Questions

当前无未决问题。以下条目已全部决策：设计可自决项记录于 `design.md` §8，需用户批准项已于 2026-07-28 获批。

- 已决策：候选池默认总上限 20 条，单市场配额 10 条；入选阈值沿用现有异动规则（涨跌幅 7%、量额倍率 3、振幅 8%）。理由：与 `scripts/daily_market_insight.py` 现有口径一致，单市场配额避免 A 股行数优势占满清单。
- 已决策（2026-07-30 实跑修订）：自动尽调默认覆盖前 4 个候选（`AI_QUANT_DAILY_MAINLINE_DILIGENCE_LIMIT`），优先已建档且有可绑定证据的候选；20 个候选仍全部进入清单，超出预算的候选记 `diligence_budget_exhausted`。理由：真实 20 候选、600 秒运行中，旧默认值 8 把单次模型预算压到约 36-46 秒并全部超时；默认值 4 可为每次调用保留约 75 秒，同时不缩减研究清单。
- 已决策："今日待研究清单"持久化为独立存储实体（`daily_mainline_runs` / `daily_mainline_queue_items` / `daily_watchlist_entries` 三个 collection），**不复用** `observation_items` 与 `research/tasks`。理由：验收标准 1.13 要求同日多次运行各自保留清单、1.11 要求关注池条目回链 `run_id`，复用 `observation_items` 会丢失 run 维度并污染既有观察项语义；三个 collection 沿用 `records` 表按 collection 分区的既有模式，无需迁移脚本。副作用（`/api/analysis/latest` 计数与备份脚本的 collection 枚举）作为落成验证项跟踪。
- 已决策：后台维护模式沿用现有单一角色选择器，不引入独立角色默认值。理由：本轮需求未要求角色语义变更，避免越出 UI 呈现层范围。

已获用户批准的决策（原"仍待用户确认"项）：

- 已批准（批准日期 2026-07-28）：完整度状态取值域收敛（`usable_with_gaps` / `incomplete` → `partial`）。该变更会改变 `/api/company-intelligence/{symbol}` 的既有 `status` 字符串，属**破坏性取值域变更**；用户已批准实施，不再作为实施前置阻塞项。依赖面适配（`app/static/index.html` 的 `statusLabel()` 与完整度展示、`app/static/ui_modules/*.mjs`、引用完整度状态的 `scripts/`、`tests/` 既有断言、`docs/` 记录取值的段落）由 `tasks.md` 任务 7.3 承担，并须在交付 handoff 中记为响应取值域契约变更。
