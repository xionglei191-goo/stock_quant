# 实施计划：项目可用性改进（每日一键研究主线）

- Status: active
- Implementation state: completed
- Owner group: 产品与 UI
- Reviewer groups: 研究与 AI 工作流、平台与质量、治理安全与合规、项目经理 / 发布协调
- Last updated: 2026-07-30
- Related tasks: T-620 至 T-624（均已完成）；运行时后续 T-626 与完整 UI 验收 T-627（均已完成）；依赖 T-605 最新分析热读、T-607 指标来源分层、T-608 五家公司证据闭环、T-619 研报导入收口
- Scope: `app/service_modules/` 新增 5 个领域模块与 `market_data.py` 扩展、`app/models.py` 与 `app/store.py` 接线、`SystemService` 5 个 facade 方法、`/api/daily-mainline/*` 5 条路由、`scripts/daily_mainline_run.py`、`app/static/index.html` 与 `app/static/ui_modules/`（`dashboard.mjs` / `helpers.mjs`）首屏与导航、`tests/test_daily_mainline_properties.py` 与 `tests/test_daily_mainline.py`、UI 校验脚本、本机延迟采样脚本 `scripts/daily_data_update_pipeline.py`（`_latency_audit` 探针）、`docs/` 契约与 handoff
- Non-goals: 不扩大公司覆盖面、不接券商、不自动下单、不产出非本机发布证据、不重写单页 UI 为前端框架、不删除既有脚本/API 路由/数据行、不新增第三方依赖（不引入 `hypothesis`）、不改既有 `run_llm_task` 的持久化语义、不改 `scripts/staging_acceptance.py`（已批准的范围收窄，见任务 16.5）
- Related documents: `.kiro/specs/project-usability-improvement/requirements.md`、`.kiro/specs/project-usability-improvement/design.md`

## Overview

实现顺序按“判定逻辑先脱离 IO”组织：先落地 `app/service_modules/` 下的纯函数领域模块并用属性测试锁定不变量，再接 dataclass 与 store，然后是 `SystemService` facade（只做编排、鉴权与审计接线）、API 路由、CLI、UI，最后统一过门禁与交接。读数口径统一（`completeness_policy` 与 `market_data` 新鲜度）作为独立任务组，因为它改既有响应取值域，需要单独核对依赖面。

属性测试统一落在 `tests/test_daily_mainline_properties.py`：stdlib `unittest` + `random.Random(固定种子)` 生成器，每条属性 ≥100 次迭代，`subTest` 携带种子与场景摘要作为反例输出，测试方法 docstring 使用 `Feature: project-usability-improvement, Property N: ...` 标签。LLM 一律使用注入的假网关，不产生真实外部请求。

design.md 第 9 节三条风险各绑定一个落成验证任务：任务 7.3（完整度 `status` 取值域收敛的 UI 与依赖脚本核对）、任务 9.4（新增 3 个 collection 对 `/api/analysis/latest` 计数与备份脚本硬编码枚举的影响）、任务 4.1（内置模板 seed 即 `approved` 并记录 prompt 版本，不走 `allow_unapproved` 绕过审批门）。

已核对的既有落点（实现时直接复用，不新建通路）：

- `SystemService.run_llm_task`（`app/services.py:536`）在 `template.status != "approved"` 且未传 `allow_unapproved` 时抛 `ComplianceGateError`；无论调用成功还是走 fallback 都会写入一条 `LLMTaskRun`，因此“成功调用次数”只能按 `status == "succeeded"` 统计。
- `LLMTaskRun` lineage 字段为 `template_id` / `provider` / `model` / `prompt_version` / `latency_ms` / `estimated_input_tokens` / `estimated_output_tokens` / `estimated_cost`，没有独立 `model_version` 字段；需求 4.3 的“模型版本”映射到 `model` + `prompt_version` 组合。
- 内置模板 seed 的既有 facade 是 `SystemService.seed_default_llm_task_templates`（`app/services.py:316`），既有路由 `POST /api/llm/task-templates/seed`。
- `LLMTaskTemplate` 已有 `status` / `prompt_version` / `allowed_roles` / `risk_level` 字段（`app/models.py:1008`）。
- 扫市指标与阈值实现在 `scripts/daily_market_insight.py:326-337`（`one_day_return` 0.07、`amount_ratio` 3.0、`volume_ratio` 3.0、`intraday_range` 0.08）。
- `market_freshness` 的 `(market, source_id, data_type)` targets 构造在 `scripts/daily_market_insight.py:1259-1268`，经 `app/api.py:882` 输出；公司侧最新行情走 `SystemService._latest_market_data_point` 与 `latest_market_date`（`app/services.py:6801-6828`、`app/api.py:851`），A 市场源常量为 `PUBLIC_EOD_MARKET_DATA_SOURCE_ID`（`app/services.py:150`）。
- `completeness_verdict` 在 `app/service_modules/company_intelligence.py:121`，现有 `incomplete`（:188）与 `usable_with_gaps`（:194）取值将归并为 `partial`。
- `COLLECTIONS` 在 `app/store.py:105`；`_validate_choice` 已在 `app/models.py` 广泛使用；`env_int` 在 `app/utils.py:43`。
- p95 阈值型延迟探针在 `scripts/daily_data_update_pipeline.py` 的 `_latency_audit`（`market_data_latest` / `dashboard_ceo` / `latest_analysis_api` / `graph_query`）——本轮延迟采样入口只改这一处。`scripts/staging_acceptance.py` 的客户端虽会按请求自动累计延迟，但按已批准的范围收窄（2026-07-28）不在本轮改动面内。

## 用户批准记录（2026-07-28）

评审阶段的 4 项待确认事项已全部获用户批准，本计划无待确认前置：

1. 完整度状态取值域收敛（`usable_with_gaps` / `incomplete` → `partial`）已批准，属破坏性取值域变更；任务 7.2 / 7.3 可直接执行，依赖面适配由任务 7.3 承担。
2. 首屏清单延迟采样入口范围收窄已批准：只改 `scripts/daily_data_update_pipeline.py` 的 `_latency_audit`，不改 `scripts/staging_acceptance.py`（任务 16.5）。
3. 在 `tasks/todo.md` 新建 T-620 至 T-624 五个路线图条目已获 PM 批准，owner 为产品与 UI，评审组按各文档头部 Reviewer groups（任务 16.2）。
4. `/api/analysis/latest` 的 `counts` 以加法方式补 3 个键、不改为按 `COLLECTIONS` 全量派生已确认（任务 9.4）。

## Tasks

- [x] 1. 基线记录与交接骨架
  - [x] 1.1 记录变更前基线并创建 handoff 骨架
    - 创建 `docs/agent-handoffs/2026-07-28-T-620-daily-mainline-usability.md`，按 AGENTS.md §6 模板填 Status / Objective / Files Touched 骨架
    - 写入实测基线：`unittest` 用例总数 551（`python3 -c "import unittest;s=unittest.defaultTestLoader.discover('tests');print(s.countTestCases())"`）、`app/api_routes.py` 路由表 461 条 `(method, path)` 与 334 条唯一路径（`grep -cE '^\s+\("(GET|POST|PUT|DELETE|PATCH)"' app/api_routes.py`、`grep -oE '\^/api/[^"]*\$' app/api_routes.py | sort -u | wc -l`）、`app/services.py` 31,956 行
    - requirements.md 与 design.md 已回改为实测口径（461 / 334）；路由护栏一律用“变更前快照 ⊆ 变更后路由表”的子集断言，不硬编码数量
    - 标注 artifact 分类口径：本任务产物固定 `local-only`、`production_release_gate_eligible=false`
    - 不含密钥、签名 URL 或完整模型响应
    - _Requirements: 7.6, 7.9_
    - _Design: §7.3_

- [x] 2. 阶段状态机领域模块 `app/service_modules/daily_mainline.py`
  - [x] 2.1 实现 `STAGES`、`STAGE_STATUSES`、`StageResult` 与 `run_stages`
    - 固定顺序 `scan_market_disturbance → build_candidate_pool → run_auto_diligence → build_daily_queue`
    - 阶段间只经 `StageResult.payload` 传递；失败或耗时越界后剩余阶段一律 `skipped`，已完成阶段结果不清空
    - `clock` / `now_iso` 以参数注入，保证测试可控且不读系统时间
    - _Requirements: 1.2, 1.3, 1.12, 7.4_
    - _Design: §4.1_
  - [x] 2.2 实现 `derive_run_status`、`build_progress`、`build_next_actions`
    - `derive_run_status`：存在 failed 阶段 → `failed`；存在 skipped/partial → `partial`；全 passed 且清单为空 → `empty`；否则 `passed`
    - `build_progress` 返回 `current_stage`（首个未完成阶段）/ `completed_count` / `total_count`
    - `build_next_actions` 对非 `passed` 状态返回 ≥1 条，每条含 `action`、`reason_code` 与 `command` 或 `endpoint`
    - 原因码取值对齐 design 第 5 节错误处理表
    - _Requirements: 1.9, 1.10, 2.6, 2.7_
    - _Design: §4.1, §5_
  - [x] 2.3 属性测试 Property 1
    - **Property 1: 阶段序列、阶段记录与进度投影一致**
    - **Validates: Requirements 1.2, 1.3, 2.6**
    - 生成器覆盖零候选、单候选、失败注入位置、耗时序列；断言阶段序列为 `STAGES` 前缀、字段完备、`finished_at ≥ started_at`、`record_count ≥ 0`、进度投影一致
  - [x] 2.4 属性测试 Property 6
    - **Property 6: 状态与可执行下一步一致**
    - **Validates: Requirements 1.9, 1.10, 2.7**
  - [x] 2.5 属性测试 Property 7
    - **Property 7: 超时截断保留已完成结果**
    - **Validates: Requirements 1.12**

- [x] 3. 扫市与候选池领域模块 `app/service_modules/daily_mainline_scan.py`
  - [x] 3.1 实现 `TRIGGER_RULES` 与 `build_candidate_pool`
    - 指标与阈值沿用 `scripts/daily_market_insight.py:326-337`：`one_day_return` 0.07、`amount_ratio` 3.0、`volume_ratio` 3.0、`intraday_range` 0.08；不引入新数据源
    - 输出每条含 `rank`、`selection_reason`、`trigger_metric`、`trigger_value`、`as_of_date`、`security_id`、`issuer_id`、`ticker`、`market`
    - 稳定排序键 `(|one_day_return|, amount_ratio, volume_ratio, security_id)`；应用 `candidate_limit` 与单市场 `market_quota`；`rank` 从 1 连续编号
    - _Requirements: 1.4, 7.4_
    - _Design: §4.2, §8_
  - [x] 3.2 属性测试 Property 2
    - **Property 2: 候选池条目契约与排名连续性**
    - **Validates: Requirements 1.4**

- [x] 4. 自动尽调领域模块 `app/service_modules/daily_mainline_diligence.py`
  - [x] 4.1 实现 `BUILTIN_TEMPLATES` 与 `seed_specs`（风险 3 落成验证）
    - 三类模板：`candidate_diligence`、`evidence_summary`、`risk_challenge`
    - 每条模板 `status="approved"`、`prompt_version="daily-mainline-v1"`，使编排不需要向 `run_llm_task`（`app/services.py:536`）传 `allow_unapproved` 绕过审批门；在 handoff 记录该决策与 prompt 版本
    - `seed_specs` 只返回缺失模板的注册 payload，已存在返回空列表（幂等）；写入复用既有 `SystemService.seed_default_llm_task_templates`（`app/services.py:316`）与既有路由 `POST /api/llm/task-templates/seed`，不新建 seed 通路
    - 模板持久化字段排除凭据与完整上游响应
    - _Requirements: 4.1, 4.2, 4.7_
    - _Design: §4.3, §9（风险 3）_
  - [x] 4.2 实现 `build_viewpoint` 与来源分层
    - 证据绑定取已存在的 `evidence` / `research_report_citation_evidence` 标识
    - 无可绑定证据 → `diligence_status="unsupported"`、`partition="pending_evidence"`，不进主清单分区
    - 来源含研报 → `source_layer="viewpoint"` 且 `fact_field_writes == []`；`FACT_FIELD_SOURCE_TYPES` 限定 `official_disclosure` / `market_data`
    - 观点携带 `llm_task_run_id`、`template_id`、`prompt_version`、`model`；观点文本只保留摘要，不复制 `LLMTaskRun.output` 的完整上游响应
    - _Requirements: 1.5, 1.6, 1.7, 1.8_
    - _Design: §4.3_
  - [x] 4.3 属性测试 Property 3
    - **Property 3: 观点证据绑定或进入待补分区**
    - **Validates: Requirements 1.6, 1.7**
  - [x] 4.4 属性测试 Property 4
    - **Property 4: 研报只进观点层，不进事实字段**
    - **Validates: Requirements 1.8**
  - [x] 4.5 属性测试 Property 11
    - **Property 11: 内置模板幂等写入**
    - **Validates: Requirements 4.2**
  - [x] 4.6 单元测试：内置模板集合契约（`tests/test_daily_mainline.py`）
    - 断言 `BUILTIN_TEMPLATES` 的 `task_type` 集合恰为三类、`status` 均为 `approved`、`prompt_version` 非空
    - _Requirements: 4.1, 4.7_

- [x] 5. 证据产物领域模块 `app/service_modules/daily_mainline_artifact.py`
  - [x] 5.1 实现 `artifact_payload`、`redact` 与文件名规则
    - payload 含 `schema_id="daily-mainline-run-artifact-v1"`、`run_id`、UTC ISO 8601 `generated_at`、`producer_command`、`environment`、`owner_group`、`classification="local-only"`、`contains_sensitive_data=false`、`production_release_gate_eligible=false`、`stages`、`items`、`paper_only`、`live_execution_allowed`
    - `redact` 递归剔除 `SENSITIVE_KEY_PATTERNS`（`api_key`、`authorization`、`token`、`secret`、`signature`、`x-amz-`、`raw_response`）命中键并截断超长文本；观点只保留摘要
    - 文件名 `artifacts/daily-mainline/daily-mainline-{run_date}-{run_id}.json`，同日多次运行互不覆盖
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
    - _Design: §4.10_
  - [x] 5.2 属性测试 Property 20
    - **Property 20: 证据产物契约**
    - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 6. Checkpoint - 领域纯函数层
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 口径统一 A：完整度判定 `app/service_modules/completeness_policy.py`
  - [x] 7.1 实现 `resolve_status`、`coverage_denominator`、`next_actions`
    - `LAYER_COVERAGE_THRESHOLDS`：`profile_field_coverage_score` / `database_coverage_score` / `relationship_coverage_score` 均 0.9
    - `status="complete"` 当且仅当 profile 可用 ∧ 无 blocking/warning gaps ∧ `missing_fact_fields` 为空 ∧ 所有阈值项达标；其余非 `not_found` 一律 `partial` 并给出 `missing_layers`
    - `coverage_denominator` 输出 `total_fields` / `filled_fields` / `score`（total=0 → 0.0）
    - `next_actions` 对非 `complete` 返回 ≥1 条，每条含 `target_field`、`source_type` 与 `command` 或 `endpoint`
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 7.4_
    - _Design: §4.8_
  - [x] 7.2 `company_intelligence.completeness_verdict` 委派统一口径
    - 取值域收敛已获用户批准（2026-07-28），无待确认前置，可直接执行
    - 改 `app/service_modules/company_intelligence.py:121` 的 `completeness_verdict`：`status` / `is_complete` / `missing_layers` / `next_actions` 全部由 `resolve_status` 与 `next_actions` 产出
    - 取值归并 `incomplete`（:188）与 `usable_with_gaps`（:194）→ `partial`；`label` 对应 `complete → 完整`、`partial → 部分完整`、`not_found → 未建档`
    - 保留 `level` / `score` / `sections` 等既有字段与语义不变
    - _Requirements: 5.1, 5.2, 5.3_
    - _Design: §4.8_
  - [x] 7.3 风险 1 落成验证：完整度 `status` 取值域收敛的依赖面适配
    - 破坏性取值域变更已获用户批准（2026-07-28），本任务承担全部依赖面适配，无需再次确认即可执行
    - 检索并逐一核对依赖完整度 `status` / `is_complete` / `label` 字符串的位置：`app/static/index.html`（`statusLabel()` 与完整度展示，当前 140 处引用）、`app/static/ui_modules/*.mjs`（`statusLabel` 以依赖注入方式传入 `dashboard.mjs`）、`scripts/` 下引用公司完整度的脚本、`tests/` 既有断言、`docs/` 中记录取值的段落
    - 对命中位置做取值适配（不改既有断言语义，只对齐新取值域），确认 UI 不再出现 `完整` 与 27 项缺失字段并列；在 handoff 记为响应取值域契约变更并注明批准日期
    - _Requirements: 5.3, 7.10_
    - _Design: §9（风险 1）_
  - [x] 7.4 属性测试 Property 15
    - **Property 15: 完整度判定等价规则**
    - **Validates: Requirements 5.1, 5.2**
  - [x] 7.5 属性测试 Property 17
    - **Property 17: 非完整状态必有可执行下一步**
    - **Validates: Requirements 5.4**
  - [x] 7.6 属性测试 Property 18
    - **Property 18: 覆盖度分母自述与算术一致**
    - **Validates: Requirements 5.5**

- [x] 8. 口径统一 B：行情新鲜度同源 `app/service_modules/market_data.py` 扩展
  - [x] 8.1 实现 `MARKET_EOD_SOURCES`、`market_eod_key`、`freshness_lag`
    - `MARKET_EOD_SOURCES` 取 `A → public_eod_market_data`（复用 `app/services.py:150` 的 `PUBLIC_EOD_MARKET_DATA_SOURCE_ID`）、`U → yahoo_chart_us_eod`
    - `market_eod_key` 返回 `{"market", "source_id", "data_type"}`，与 `scripts/daily_market_insight.py:1259-1268` 现有 `market_targets` 结构一致
    - `freshness_lag` 返回 `lag_days`（精确日历差）、`reason_code`、`is_lagging`；`lag_days > 0` 时原因码取 `security_not_in_latest_eod_batch` / `security_suspended_or_delisted` / `source_partial_coverage`，等于 0 时为空串
    - _Requirements: 5.6, 5.7, 7.4_
    - _Design: §4.9_
  - [x] 8.2 公司最新行情取数改走 `market_eod_key` 并输出滞后标注
    - `scripts/daily_market_insight.py` 的 `market_targets` 与公司侧 `latest_market_date` 路径（`app/services.py:6801-6828` 经 `_latest_market_data_point`，输出于 `app/api.py:851`、`app/api.py:882`）统一改由 `market_eod_key` 提供 `(market, source_id, data_type)`
    - 公司最新行情日期早于市场 EOD 时输出 `lag_days` 与 `reason_code`，修正 `2026-05-25` 与市场 EOD `2026-07-24` 并列且无解释的问题
    - _Requirements: 5.6, 5.7_
    - _Design: §4.9_
  - [x] 8.3 属性测试 Property 19
    - **Property 19: 行情新鲜度同源与滞后标注**
    - **Validates: Requirements 5.6, 5.7**

- [x] 9. 数据模型、存储与配置接线
  - [x] 9.1 在 `app/models.py` 新增三个 dataclass
    - `DailyMainlineRun`、`DailyMainlineQueueItem`、`DailyWatchlistEntry`，字段与默认值按 design §3.1
    - `__post_init__` 用既有 `_validate_choice` 校验 `status` / `partition` / `review_status` 枚举
    - _Requirements: 1.3, 1.11, 4.6, 7.4_
    - _Design: §3.1_
  - [x] 9.2 在 `app/store.py` 的 `COLLECTIONS`（:105）追加三条 collection
    - `daily_mainline_runs` / `daily_mainline_queue_items` / `daily_watchlist_entries`，沿用 `records` 表按 collection 分区的既有模式，不新增迁移脚本
    - _Requirements: 1.13, 7.4_
    - _Design: §3.2_
  - [x] 9.3 配置项读取与示例同步
    - 在 `app/service_modules/daily_mainline.py` 增加纯函数 `resolve_config(env)` 集中解析配置，facade 只消费其返回值（避免配置解析散落进 `app/services.py`）
    - 用既有 `app/utils.env_int`（:43）读取 `AI_QUANT_DAILY_BRIEF_TIMEOUT_SECONDS`(600)、`AI_QUANT_DAILY_MAINLINE_CANDIDATE_LIMIT`(20)、`AI_QUANT_DAILY_MAINLINE_MARKET_QUOTA`(10)、`AI_QUANT_DAILY_MAINLINE_DILIGENCE_LIMIT`(4，2026-07-30 实跑修订)，以及 `AI_QUANT_DAILY_MAINLINE_ARTIFACT_DIR`(`artifacts/daily-mainline`)
    - 全部有默认值，缺省不改变既有行为；同步 `.env.example`
    - _Requirements: 1.4, 1.12, 4.5, 6.1, 7.10_
    - _Design: §3.3_
  - [x] 9.4 风险 2 落成验证：新增 collection 的下游影响
    - 已实测：`scripts/migrate_sqlite_to_postgres.py` 已按 `app.store.COLLECTIONS` 派生（:19、:52、:125、:270、:317），新增 collection 自动覆盖，无需改动
    - 已实测：`/api/analysis/latest` 的 `counts` 是显式硬编码字典（`app/services.py:30215` 起），新增 collection 不会自动出现。处理方式限定为**加法**，且该口径已获用户确认（2026-07-28）：显式补 `daily_mainline_runs` / `daily_mainline_queue_items` / `daily_watchlist_entries` 三个键；**不得**把整个 `counts` 改为按 `COLLECTIONS` 派生（会把全部 collection 灌入既有仪表盘契约，属越界变更）
    - 在 `tests/test_daily_mainline.py` 补一条回归：三个新 collection 可按 `COLLECTIONS` 读写，且 `counts` 中三个新键存在、既有键一个不少
    - _Requirements: 7.4, 7.10_
    - _Design: §9（风险 2）_
  - [x] 9.5 单元测试：dataclass 枚举校验与 store 往返（`tests/test_daily_mainline.py`）
    - 枚举外取值抛错；三个 collection 写入后可按主键读回且字段保真
    - _Requirements: 1.11, 1.13, 4.6_

- [x] 10. facade 编排 `SystemService.run_daily_mainline`（`app/services.py`）
  - [x] 10.1 实现 `run_daily_mainline`
    - 编排链：读行情 → `build_candidate_pool` → 内置模板 seed → 既有 `self.run_llm_task` → `completeness_policy` 取完整度 → 写 `DailyMainlineRun` / `DailyMainlineQueueItem` → 写 artifact → 审计
    - 判定逻辑全部委派领域模块，facade 内不新增业务判定（AGENTS.md §8.1）；候选完整度只引用 `completeness_policy` 返回值，不本地重算
    - LLM 成功次数按 `LLMTaskRun.status == "succeeded"` 统计（`run_llm_task` 在 fallback 时同样写记录）；观点 lineage 取 `template_id` / `model` / `prompt_version` / `latency_ms` / `estimated_*_tokens`
    - 输出 `live_execution_allowed=false`、`paper_only=true`，持仓与交易相关节点带 paper-only 标记；只调用项目内已注册的本机服务与本地数据源
    - 单候选级 LLM 失败 / 超时 / 预算耗尽记 `llm_call_failed` / `llm_timeout` / `diligence_budget_exhausted` 并保留候选，不升级为阶段失败
    - 同日重复触发生成新 `run_id`，保留历史清单与 artifact
    - _Requirements: 1.1, 1.5, 1.9, 1.10, 1.12, 1.13, 4.3, 4.4, 4.5, 4.8, 5.8, 7.1, 7.2, 7.3, 7.5_
    - _Design: §4.4, §5_
  - [x] 10.2 属性测试 Property 5
    - **Property 5: LLM lineage 与成功调用计数一致**
    - **Validates: Requirements 1.5, 4.3, 4.8**
    - 成功调用口径按 `status == "succeeded"`；模型版本断言取 `model` + `prompt_version` 组合
  - [x] 10.3 属性测试 Property 13
    - **Property 13: LLM 失败保留候选并记录原因**
    - **Validates: Requirements 4.5**
  - [x] 10.4 属性测试 Property 14
    - **Property 14: 凭据与完整上游响应不落盘**
    - **Validates: Requirements 4.7, 6.5**
    - 断言范围为本任务新增持久化字段（模板、清单条目、`daily_watchlist_entries`）与写出的 artifact；既有 `LLMTaskRun.output` 语义不改，该边界写入 handoff
  - [x] 10.5 属性测试 Property 21
    - **Property 21: 边界声明不变量**
    - **Validates: Requirements 7.1, 7.2**
  - [x] 10.6 属性测试 Property 8
    - **Property 8: 同日多次运行互不覆盖**
    - **Validates: Requirements 1.13, 6.4**
  - [x] 10.7 属性测试 Property 16
    - **Property 16: 跨响应完整度状态一致**
    - **Validates: Requirements 5.3, 5.8**

- [x] 11. facade 读模型与条目操作（`app/services.py`）
  - [x] 11.1 实现 `daily_mainline_queue_payload` 与 `daily_mainline_runs_payload`
    - 固定读模型 `schema_id="daily-mainline-queue-v1"`，含 `as_of_date`、`generated_at`、`progress`、`stages`、`items`、`pending_evidence_items`、`next_actions`、`paper_only`、`live_execution_allowed`、`usage_boundary`
    - 每个条目含 `rank`、`selection_reason`、`trigger_metric`、`trigger_value`、`completeness_status`、`evidence_ref`、`watchlist_action`（含 `endpoint` 与 `method`）、`review_status`、`partition`
    - 读路径沿用 T-605 已物化的最新分析热读方式，不新增缓存层
    - _Requirements: 2.1, 2.4, 2.8, 7.5_
    - _Design: §4.5_
  - [x] 11.2 实现 `add_daily_queue_item_to_watchlist`
    - 复用既有 `SystemService.import_company_watchlist`（`app/services.py:24595`）完成公司入库；`daily_watchlist_entries` 记录 `security_id`、加入时间、来源 `run_id`、`item_id` 与入选理由
    - _Requirements: 1.11, 7.5_
    - _Design: §3.2, §4.4_
  - [x] 11.3 实现 `review_daily_mainline_viewpoint`
    - 复核状态默认 `pending`，接受 `pending` / `accepted` / `rejected`，枚举外取值拒绝并写审计；复核结果回写对应 `research_answers` 关联
    - _Requirements: 4.6, 7.5_
    - _Design: §4.4_
  - [x] 11.4 属性测试 Property 10
    - **Property 10: 清单读模型呈现契约**
    - **Validates: Requirements 2.4, 2.8**
  - [x] 11.5 属性测试 Property 9
    - **Property 9: 加入关注池往返保真**
    - **Validates: Requirements 1.11**
  - [x] 11.6 属性测试 Property 12
    - **Property 12: 研究结论与复核状态往返**
    - **Validates: Requirements 4.4, 4.6**

- [x] 12. Checkpoint - facade 与存储层
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. API 路由（`app/api_routes.py` + `app/api.py`）
  - [x] 13.1 新增 5 条路由与对应 handler
    - `POST /api/daily-mainline/run`、`GET|POST /api/daily-mainline/queue`、`GET|POST /api/daily-mainline/runs`、`POST /api/daily-mainline/queue/{item_id}/watchlist`、`POST /api/daily-mainline/viewpoints/{item_id}/review`
    - handler 只做入参解析与 facade 调用，沿用 `build_route_table` 既有正则与响应包装、鉴权与审计接线；只追加路由，既有条目一条不改
    - _Requirements: 1.1, 1.11, 2.1, 3.3, 3.4, 4.6_
    - _Design: §4.5_
  - [x] 13.2 黄金路由清单回归（`tests/test_system.py`）
    - 以任务 1.1 记录的变更前路由快照做子集断言（变更前全部 `(method, path)` ⊆ 变更后路由表），不硬编码路由总数；并断言既有响应包装结构不变
    - _Requirements: 3.3, 3.4_

- [x] 14. CLI 入口（`scripts/daily_mainline_run.py` + `Makefile`）
  - [x] 14.1 实现 CLI 与 `make daily-mainline`
    - 参数 `--as-of-date`、`--timeout-seconds`、`--diligence-limit`、`--artifact-dir`、`--actor`
    - 调用同一 `SystemService.run_daily_mainline`，`json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)` 输出；`status ∈ {passed, empty}` 退出码 0，否则 1
    - CLI 不含任何判定逻辑
    - _Requirements: 1.1, 1.10_
    - _Design: §4.6_
  - [x] 14.2 单元测试：双入口同一实现（`tests/test_daily_mainline.py`）
    - 对 facade 打桩计数，断言 CLI 与 HTTP handler 命中同一方法；断言 CLI 退出码映射；断言编排只经注入接口访问外部（配合 `scripts/security_check.py .`）
    - _Requirements: 1.1, 7.3_

- [x] 15. UI 首屏与导航收敛（`app/static/index.html` + 校验脚本）
  - [x] 15.1 新增首屏“今天看什么”区块
    - `#dailyMainlinePanel` 置于既有 quick-start 之前，含 `system-strip`（数据日期、生成时间、运行状态、阶段进度）、`data-action="run-daily-mainline"` 按钮、清单表格、`#dailyMainlineEmpty` 空态卡片与 `python3 scripts/daily_mainline_run.py --as-of-date YYYY-MM-DD` 命令文本
    - 保持既有单页结构与无障碍属性（`aria-label`、表头语义）
    - _Requirements: 2.1, 2.2, 2.5_
    - _Design: §4.7_
  - [x] 15.2 清单渲染与运行态呈现（落点 `app/static/ui_modules/dashboard.mjs` + `index.html` 薄封装）
    - 渲染函数写入 `ui_modules/dashboard.mjs` 的 `createDashboardRuntime`（沿用既有依赖注入签名），`index.html` 只保留 `return dashboardRuntime.<fn>(...)` 形式的薄封装，与 T-599 既有拆分方向一致
    - 每条显示排名、标的、入选理由、完整度、证据入口、`加入关注池` 操作；顶部标注 `as_of_date` 与 `generated_at`
    - 运行中显示当前阶段名与已完成阶段数；`partial` / `failed` 显示失败阶段名与 `reason_code`；待补证据分区独立呈现
    - 改动 `.mjs` 后单独执行 `node scripts/ui_dashboard_module_check.mjs`（该检查不在 `make local-ci` 内）
    - _Requirements: 1.11, 2.4, 2.6, 2.7, 2.8_
    - _Design: §4.7_
  - [x] 15.3 导航分组收敛与维护态深链（落点 `index.html` 标记 + `ui_modules/helpers.mjs` 接线）
    - `personal` 组保留总览、公司情报、知识图谱、K 线行情、研究结论、模拟反馈与动态配置外链；治理、签批、发布门禁、投委会入口留在 `maintenance` 组（`data-workspace-target` 按钮标记在 `index.html:1667-1682`）
    - 深链先 `setWorkspaceMode` 再 `openTab` 的行为改动落在 `ui_modules/helpers.mjs` 的 `installNavigation`（`helpers.mjs:57,71` 已注入 `setWorkspaceMode`）；`scripts/ui_static_check.py` 断言导航选择器不得回到 `index.html`，不要把接线搬回单页
    - 只改呈现层，不删脚本、路由与数据行
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
    - _Design: §4.7_
  - [x] 15.4 扩展 `scripts/ui_static_check.py` 断言
    - 断言清单区块、触发按钮、空态命令文本、`as_of_date` 与生成时间占位、导航分组属性存在
    - 若在 `dashboard.mjs` 新增渲染函数，同步把函数名加入既有 `dashboard_functions` / `dashboard_wrappers` 抽取断言，保持模块化门禁有效
    - _Requirements: 2.1, 2.2, 2.5, 3.6_
    - _Design: §7.2_
  - [x] 15.5 扩展 `scripts/ui_interaction_acceptance.py` 用例
    - 枚举全部维护态 tab id 逐一验证深链可打开；验证失败态渲染阶段名与 `reason_code`
    - _Requirements: 2.7, 3.5, 3.6_

- [x] 16. 门禁与收尾
  - [x] 16.1 `docs/` 契约同步
    - `docs/api-contracts.md` 补 5 条路由与清单读模型 `daily-mainline-queue-v1`；`docs/artifact-governance.md` 补 `daily-mainline-run-artifact-v1` 分类与保留口径；`docs/user-manual.md` 与 `README.md` 补 CLI / `make daily-mainline` 入口与首屏使用路径；`docs/latest-analysis-chain.md` 补清单读路径；记录完整度 `status` 取值域收敛与 5 个新增 `AI_QUANT_DAILY_MAINLINE_*` / `AI_QUANT_DAILY_BRIEF_TIMEOUT_SECONDS` 环境变量
    - 文档头部按 AGENTS.md §7 补 Status / Owner group / Last updated / Related tasks；不含密钥、签名 URL 或完整模型响应
    - _Requirements: 7.10_
    - _Design: §7.3, §9_
  - [x] 16.2 `tasks/todo.md` 新增任务项（T-620 起，已获 PM 批准）
    - 新建 T-620 至 T-624 五个路线图条目已获 PM 批准（2026-07-28）：owner 统一为产品与 UI，评审组按各 spec 文档头部 Reviewer groups（研究与 AI 工作流、平台与质量、治理安全与合规、项目经理 / 发布协调）
    - T-620 每日主线编排与双入口；T-621 AI 层激活（模板、运行记录、复核）；T-622 读数口径统一（完整度与行情新鲜度）；T-623 首屏与导航收敛；T-624 本机证据产物与门禁收尾
    - 每项按既有条目格式写 `对应`（`docs/mvp-backlog.md` 的 E1-E9 映射与 owner/评审组）、`目标`、`非目标`、`验收`（命令）与 `Handoff` 路径；状态按实际进展维护
    - _Requirements: 7.10_
  - [x] 16.3 补全 handoff 记录
    - 补齐 Files Touched、Commands Run、Decisions、Risks and Open Questions、Artifacts、Next Steps
    - 必含 `SystemService Growth Freeze Review`，需覆盖本轮全部 `app/services.py` 改动面，而非只覆盖新增 facade：
      - 新增 5 个 facade 方法（任务 10.1、11.1-11.3）均为跨模块编排与既有存储/审计接线，业务判定落在 `app/service_modules/`
      - 任务 8.2 把 `_latest_market_data_point` / `latest_market_date` 的取数键改为委派 `market_data.market_eod_key`，属逻辑外移（`app/services.py` 判定减少）
      - 任务 9.4 在 `/api/analysis/latest` 的 `counts` 字典加 3 个键，属 store 计数接线，非业务逻辑
      - facade 回归为黄金路由子集断言与双入口打桩测试；声明 API 响应取值域变更（完整度 `status`）与 paper-only / no-broker 边界未变
    - Artifacts 段声明 `artifacts/daily-mainline/daily-mainline-{run_date}-{run_id}.json` 的 producer 命令、生成时间、环境、owner group、无敏感数据、`local-only` 且不可用于非本机发布门禁
    - 记录变更前后 `unittest` 用例总数（基线 551）与路由快照对比结果
    - _Requirements: 6.6, 7.6, 7.9_
    - _Design: §7.3_
  - [x] 16.4 全门禁执行与基线对比
    - `make local-ci`（`py_compile`、`unittest discover -s tests`、`ui_static_check`、`security_check .`、`check_markdown_links`、`check_handoffs`、`check_doc_metadata`）
    - `docs/agent-handoffs/` 变更后单独执行 `python3 scripts/check_handoffs.py`
    - `app/static/ui_modules/*.mjs` 变更后单独执行 `node scripts/ui_dashboard_module_check.mjs`（不在 `make local-ci` 内）
    - 复算 `unittest` 用例总数并断言不少于基线 551、既有断言未被修改语义；路由子集断言通过
    - 失败项记录首个失败用例、根因与是否与本任务相关，不隐藏环境漂移导致的失败
    - _Requirements: 3.6, 7.3, 7.7, 7.8, 7.9_
    - _Design: §7.3_
  - [x] 16.5 首屏清单延迟采样入口（范围已收窄并获批准）
    - 只在 `scripts/daily_data_update_pipeline.py` 的 `_latency_audit` 探针列表追加 `daily_mainline_queue`（`GET /api/daily-mainline/queue`，沿用既有 `threshold_ms` 口径）
    - **不改** `scripts/staging_acceptance.py`（用户已批准的范围收窄，2026-07-28）。理由：该脚本 owner 为治理/平台组，且贴近"不产出非本机发布证据"的项目边界，本轮产品与 UI 侧改动不介入
    - 仅完成采样入口代码改动；本机 Compose 上的实际采样执行与 p95 结果由运行者写入 `local-only` artifact 并记入 handoff
    - _Requirements: 2.3_
    - _Design: §7.3_

- [x] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务，可为更快 MVP 跳过；顶层任务不带 `*`
- 21 条 Correctness Properties 全部分配到具体任务，属性测试统一落在 `tests/test_daily_mainline_properties.py`（stdlib `unittest` + 固定种子、每条 ≥100 次迭代、`subTest` 输出反例、docstring 用 `Feature: project-usability-improvement, Property N: ...`）
- 属性到任务映射：P1/P6/P7 → 2.3-2.5；P2 → 3.2；P3/P4/P11 → 4.3-4.5；P20 → 5.2；P15/P17/P18 → 7.4-7.6；P19 → 8.3；P5/P13/P14/P21/P8/P16 → 10.2-10.7；P10/P9/P12 → 11.4-11.6
- 示例与单元测试落在 `tests/test_daily_mainline.py`，黄金路由子集断言落在 `tests/test_system.py`
- design.md 第 9 节三条风险的落成验证：任务 4.1（模板审批门与 prompt 版本）、任务 7.3（完整度取值域的 UI 与依赖脚本核对）、任务 9.4（新增 collection 的计数与备份枚举）
- 评审阶段 4 项待确认事项已于 2026-07-28 全部批准（见“用户批准记录”），无待确认前置；`requirements.md` 与 `design.md` 状态已转为 active，本文件保持 draft 直至实现完成
- 口径统一为独立任务组（任务 7、任务 8），因为它改既有响应取值域，需要单独核对依赖面
- 路由基线实测为 461 条 `(method, path)` / 334 条唯一路径（requirements.md 事实基线与 design.md §4.5 已同步为该口径）；护栏统一用子集断言，不硬编码数量
- `app/static/ui_modules/` 并非空目录：T-599 运行期模块化已落地 `dashboard.mjs` / `helpers.mjs`（运行期加载）与 `company/graph/market/admin`（scaffold），`manifest.json` 标注 `status=runtime-partial`；UI 任务落点按 design §4.7 分工，附加门禁 `node scripts/ui_dashboard_module_check.mjs` 不在 `make local-ci` 内，需单独执行
- 边界不变：paper-only、不接券商、不自动下单、artifact 固定 `local-only`、新增业务逻辑落 `app/service_modules/`
- 不新增第三方依赖；不删除既有脚本、API 路由与数据行；不改既有 `run_llm_task` 持久化语义

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "5.1", "7.1", "8.1", "9.1"] },
    { "id": 1, "tasks": ["2.2", "4.1", "7.2", "9.2"] },
    { "id": 2, "tasks": ["3.2", "4.2", "8.2"] },
    { "id": 3, "tasks": ["2.3", "9.3", "9.5"] },
    { "id": 4, "tasks": ["2.4", "4.6"] },
    { "id": 5, "tasks": ["2.5", "9.4"] },
    { "id": 6, "tasks": ["4.3", "7.3"] },
    { "id": 7, "tasks": ["4.4", "10.1"] },
    { "id": 8, "tasks": ["4.5", "11.1"] },
    { "id": 9, "tasks": ["5.2", "11.2"] },
    { "id": 10, "tasks": ["7.4", "11.3"] },
    { "id": 11, "tasks": ["7.5", "13.1"] },
    { "id": 12, "tasks": ["7.6", "14.1"] },
    { "id": 13, "tasks": ["8.3", "13.2"] },
    { "id": 14, "tasks": ["10.2", "14.2", "15.1"] },
    { "id": 15, "tasks": ["10.3", "15.2"] },
    { "id": 16, "tasks": ["10.4", "15.3"] },
    { "id": 17, "tasks": ["10.5", "15.4"] },
    { "id": 18, "tasks": ["10.6", "15.5"] },
    { "id": 19, "tasks": ["10.7", "16.5"] },
    { "id": 20, "tasks": ["11.4", "16.1"] },
    { "id": 21, "tasks": ["11.5", "16.2"] },
    { "id": 22, "tasks": ["11.6", "16.3"] },
    { "id": 23, "tasks": ["16.4"] }
  ]
}
```
