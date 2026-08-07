# Handoff: T-620 每日一键研究主线可用性改进

## Metadata

- Status: DONE
- Owner group: 产品与 UI
- Reviewer groups: 研究与 AI 工作流、平台与质量、治理安全与合规、项目经理 / 发布协调
- Last updated: 2026-07-29
- Last agent: Codex
- Branch/worktree: `main`，共享工作树
- Artifact classification: local-only
- Related tasks: T-620、T-621、T-622、T-623、T-624；依赖 T-605 最新分析热读、T-607 指标来源分层、T-608 五家公司证据闭环、T-619 研报导入收口

## Objective

落地 `.kiro/specs/project-usability-improvement` 的每日一键研究主线（扫市 → 候选池 → 自动尽调 → 今日待研究清单），并完成 HTTP/CLI 双入口、首屏与导航收敛、完整度与行情新鲜度统一、审计产物和本机验收。

## Scope

- In scope: `app/service_modules/` 每日主线领域模块与 `market_data.py` / `completeness_policy.py` 口径统一、`app/models.py` 与 `app/store.py` 接线、`SystemService` facade、`/api/daily-mainline/*` 路由、CLI/Makefile、首屏与导航、属性/集成/UI 测试、延迟探针、契约、路线图与本 handoff。
- Out of scope: 不扩大公司覆盖面、不接券商、不自动下单、不产出非本机发布证据、不重写单页 UI 为前端框架、不删除既有脚本 / API 路由 / 数据行、不新增第三方依赖（不引入 `hypothesis`）、不改既有 `run_llm_task` 持久化语义、不改 `scripts/staging_acceptance.py`（范围收窄已于 2026-07-28 获批）。

## Background

本机 Compose 栈、数据底座与凭据均已就绪（`llm_gateway.configured=true`、`document_parser.configured=true`、`tdx_vipdoc.configured=true`），但入口分散在 127 个脚本、461 条 `(method, path)` 路由与上百条 README 命令中；`llm_task_templates` / `llm_task_runs` / `extraction_results` 全为 0；`/api/company-intelligence/{symbol}` 同一响应里 `status=complete` 与 27 项 `missing_fact_fields` 并存；每次运行无固化证据。spec 的 requirements.md / design.md 已转 active，4 项待确认事项已于 2026-07-28 全部获用户批准。

任务 1.1 存在的理由：需求 7.9 要求"测试总数不少于变更前基线"，需求 3.3 要求"变更前路由快照 ⊆ 变更后路由表"。这两条护栏都必须先有**变更前**的实测取数，否则后续 16 个任务组无法证明"没删东西"。

## Problem Statement

变更前缺少可复现基线与路由快照，产品入口又分散在脚本、API 和后台页面。交付现已用可提交的路由 fixture、统一 facade、首屏主清单和 `local-only` 运行证据解决这些问题。

## Expected Deliverables

- 可运行的每日主线领域、存储、facade、API、CLI 与首屏。
- 21 条属性不变量、双入口、路由子集、UI 静态/模块/浏览器与完整本地门禁证据。
- 完整度与行情新鲜度同源契约，以及固定 `paper_only=true`、`live_execution_allowed=false` 的脱敏 `local-only` artifact。
- 当前路线图、Kiro 清单与可供下一位维护者复现的 handoff。

## Current State

- Completed: 五个每日主线领域模块、完整度策略与行情新鲜度同源实现。
- Completed: dataclass、SQLite/PostgreSQL store、配置、`SystemService` facade、7 个 method-route pair / 5 个路径、CLI 与 Makefile 接线。
- Completed: 首页“今天看什么”、主清单/待补证据/失败阶段、维护态深链和 watchlist 操作。
- Completed: 21 条属性测试、双入口与路由 fixture 回归、779 个全量测试、静态/模块/桌面/移动浏览器验收。
- Completed: README、API/产物/用户手册/分析链、路线图、Kiro 清单和本 handoff 同步。
- Completed: 修复自动尽调把 600 秒总预算当成逐调用预算、导致最终清单阶段被跳过的问题；120 秒生产样本回归在 112.7626 秒内完成并持久化 4 条清单。
- In progress: 无。
- Not started: 无。
- Blocked: 无本任务阻塞。

## Current Findings

### 变更前实测基线（采集于 git 短修订版 `e70e1e9`，分支 `main`，Python 3.14.3）

完整 40 位修订号不写入本文档：`scripts/security_check.py` 的 `paddleocr_token_literal` 规则会把 40 位十六进制串判为疑似令牌，写入会造成门禁假失败。需要完整值时执行 `git rev-parse e70e1e9`。

| 基线项 | 实测值 | 采集命令 |
| --- | --- | --- |
| `unittest` 用例总数 | 551 | `python3 -c "import unittest;s=unittest.defaultTestLoader.discover('tests');print(s.countTestCases())"` |
| 路由表 `(method, path)` 条数 | 461 | `grep -cE '^\s+\("(GET\|POST\|PUT\|DELETE\|PATCH)"' app/api_routes.py` |
| 唯一 API 路径数 | 334 | `grep -oE '\^/api/[^"]*\$' app/api_routes.py \| sort -u \| wc -l` |
| 运行期路由表：行数 / 唯一 pair / 唯一路径 | 461 / 461 / 334 | `python3 -c "import sys;sys.path.insert(0,'.');from unittest.mock import MagicMock;from app.api_routes import build_route_table;t=build_route_table(MagicMock());print(len(t), len({(m,p) for m,p,_ in t}), len({p for _,p,_ in t}))"` |
| 方法分布 | GET 168 / POST 293（无 PUT / DELETE / PATCH） | 同上（按 method 计数） |
| `app/services.py` 行数 | 31,956 | `wc -l app/services.py` |
| `app/api_routes.py` 行数 | 473 | `wc -l app/api_routes.py` |
| `app/static/index.html` 行数 | 12,650 | `wc -l app/static/index.html` |
| `app/service_modules/` 模块数 / 总行数 | 36 / 10,093 | `ls app/service_modules/*.py \| grep -v __init__ \| wc -l`、`cat app/service_modules/*.py \| wc -l` |
| `scripts/` 脚本数 | 127（122 `.py` + 4 `.sh` + 1 `.mjs`） | `ls scripts \| sed -E 's/.*\.//' \| sort \| uniq -c` |

核对结论：spec 记录的 551 / 461 / 334 / 31,956 与本机实测**完全一致**，无需回改 spec。`app/service_modules/` 的 spec 记录值（33 模块 / 8,787 行）已漂移到 36 / 10,093；该数值不是任何护栏的输入项，本轮按实测记录，不回改 spec。

基线时点说明：551 于本任务开始时（并行 wave 0 任务落文件之前）采集。采集后，并行执行的 wave 0 任务已落 `app/service_modules/daily_mainline.py`、`daily_mainline_scan.py`、`daily_mainline_artifact.py`、`completeness_policy.py` 与对应 4 个测试文件，`discover('tests')` 复算为 586；`python3 -m unittest tests.test_daily_mainline tests.test_daily_mainline_scan tests.test_daily_mainline_artifact tests.test_completeness_policy` 得 35 个用例，`586 - 35 = 551` 与基线自洽。护栏仍以 551 为下限。

### 变更前路由快照（任务 13.2 的断言依据）

- 快照数据：`artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv`，461 行 `METHOD\t^/api/...$`，334 个唯一路径模式，18,508 字节。
- 快照 manifest：`artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.json`，含分类元数据、计数、两个摘要哈希与全部生成 / 校验命令。
- 摘要哈希（两项都可复算）：
  - `snapshot_tsv_sha256 = 9d1d7c14dbe6e4da039579ca84856fd07f92c4d43751c688b447192aa99f8a19`
  - `routes_canonical_json_sha256 = 8b849a65baff54224ca1d24b3555d8fdd81a8a57651c0fecaf8a15eb0b2fa887`（对 `[{"method","path_pattern"}, ...]` 排序后 `sort_keys=True, separators=(',',':')` 序列化取 sha256）
- 双路提取交叉校验一致：源码正则提取（可对任意 git 修订版执行）与运行期 `build_route_table(MagicMock())` 提取给出同一组 461 条 pair 和同一个 `routes_canonical_json_sha256`。
- 快照未进提交：`.gitignore:45` 的 `artifacts/*` 覆盖该目录；快照可由 `git show e70e1e9:app/api_routes.py` 用 git + coreutils 完整重建，因此本文档只记录生成命令与摘要哈希，不复制 461 行清单。

### 响应取值域契约变更：完整度 `status`（任务 7.3，批准日期 2026-07-28）

`/api/company-intelligence/{symbol}` 的 `completeness_verdict` 取值域收敛为 `complete` / `partial` / `not_found`，属**破坏性取值域变更**，已于 2026-07-28 获用户批准；服务端改造在任务 7.2，依赖面适配在任务 7.3。

| 键 | 收敛前 | 收敛后 |
| --- | --- | --- |
| `status` | `complete` / `usable_with_gaps` / `incomplete` / `not_found` | `complete` / `partial` / `not_found` |
| `label` | `完整` / `可复盘` / `可分析` / `事实层可用` / `可用但有缺口` / `需要补库` / `未建档` | `完整` / `部分完整` / `未建档` |
| `is_complete` | `status == "complete"`（只看分层可用性与加权分） | 追加"`missing_fact_fields` 为空 ∧ 三项覆盖度均 ≥ 0.9" |
| `missing_layers` | 6 个分节名 + 2 个 backlink 名 | 追加 `profile_field_coverage` / `database_coverage` / `relationship_coverage` / `profile_fact_fields` |
| 新增键（加法，向后兼容） | — | `relationship_coverage_score`、`section_gap_layers`（旧 `missing_layers` 等价物）、`status_source`、verdict 内 `next_actions` |

`level` / `score` / `sections` / `blocking_gaps` / `warning_gaps` / `ready_for_*` / `recommended_next_action` 语义未变。

依赖面逐条处理结果（任务 7.3）：

- `app/static/index.html` `statusLabel()`：新增 `COMPLETENESS_STATUS_LABELS` + `completenessStatusLabel()`，与 `completeness_policy.STATUS_LABELS` 同源，并把 `usable_with_gaps` / `incomplete` 归并为 `部分完整`。通用 `partial: "部分补齐"` 保留不动（跨域取值：批量构建、作业状态、覆盖档位），只在完整度场景改走新解析器，避免跨域回归。
- `app/static/index.html` `companyIntelVerdictTone()`：判红改为 `not_found` 或 `blocking_gaps.length > 0`。理由：旧口径 `incomplete` 的定义正是"profile 可用但存在 blocking gap"，按 `blocking_gaps` 判红与收敛前红色语义等价；若只按 `status` 判，`partial` 会把事实层阻塞公司降级为黄色告警。
- `app/static/index.html` 新增 `companyIntelVerdictView()`：完整度判断区块（原 9674 起）与个人视图摘要（原 11428 起）共用同一取值域解析器；对 `status=complete` 且 `missing_fact_fields` 非空的历史产物在 UI 侧同样降级为 `部分完整`，保证界面不再出现"完整"与数十项缺失字段并列。
- `app/static/index.html` 完整度判断表：新增"覆盖度分层"行，读 `missing_layers` 去掉 `section_gap_layers` 与 `profile_fact_fields` 后的余项，并带三项覆盖度分值，解释"分节全绿但仍是部分完整"。
- `app/static/index.html` 原始 JSON 面板（原 11739）：保持透传 `data.completeness_verdict`，不做改写，审计追溯仍看后端原值。
- `app/static/index.html` 8888（`renderPersonalIntelligenceSummary`）与 5595（`renderKnowledgeGraphReadiness`）：读的是 `/api/personal-intelligence` 的 `coverage_level` 与图谱就绪度 `missing_layers`，与公司完整度不同源，核对后确认展示不串，未改动。
- `app/static/ui_modules/dashboard.mjs`：`statusLabel` 以依赖注入传入，随 `index.html` 自动对齐；公司情报行渲染的 `item.status` 是响应级 `available` / `not_found`，非完整度取值，无需改动（`node scripts/ui_dashboard_module_check.mjs` 复跑通过）。
- `app/api.py`（`/api/analysis/latest` 逐公司兜底）与 `scripts/latest_analysis_run.py`（物化快照）：仍读 `is_complete`，键名与统计方式不变，只补注释说明口径收紧。实测数值变化见下。
- `tests/test_system.py:862`：任务 7.2 已改为 `"partial"`，本任务核对通过，未再改动。
- `tests/test_completeness_policy.py`：新增 `UiCompletenessValueDomainTests`（4 条），把"UI 完整度 label 必须等于 `completeness_policy.STATUS_LABELS`"、"旧取值归并为 `部分完整`"、"判红按 `blocking_gaps`"、"`完整` 不与缺失字段并列"固化为回归；未修改任何既有断言。
- `docs/api-contracts.md`：`/api/company-intelligence/{symbol}` 返回字段补 `completeness_verdict` 取值域段落；latest-analysis 段补 `ready_count` / `needs_attention_count` 口径收紧说明。

`ready_count` 实测变化（口径切换前后同一批输入复算，探针按 `resolve_status` 重跑最新物化产物 `artifacts/daily-update-local/runs/2026-07-28-183121/latest-analysis-2026-07-28/latest-analysis.json` 中 9 家公司的记录输入）：

- `ready_count` 5 → 0，`needs_attention_count` 4 → 9（`company_count=9` 不变）。
- 逐公司：`300750` / `600519` / `AAPL` / `MSFT` / `NVDA` 由 `complete`→`partial`（各带 28–29 项 `missing_fact_fields`，`relationship_coverage_score` 均为 0.3333）；`000001` 由 `usable_with_gaps`→`partial`；`600000` / `SPY` / `TSLA` 由 `incomplete`→`partial`（仍有 `events` blocking gap，UI 判红不变）。
- 结论：`/api/analysis/latest` 的 `company_intelligence.status` 会从 `ready` 变为 `watch`（`ready_count=0` 且有公司行），这是口径收紧的预期结果，不是数据丢失；恢复 `ready` 需要补齐事实字段与三项覆盖度。

### 行情新鲜度同源（任务 8.1 / 8.2，需求 5.6 / 5.7，设计 §4.9）

变更前问题：公司侧最新行情日期与市场 EOD 日期两条取数通路各自硬编码 source，且 `scripts/daily_market_insight.py` 的公司活动条目按 `source_id = ANY([source_a, source_u])` 跨市场混取，导致实测出现"公司条目 `latest_market.as_of_date=2026-05-25` 与市场 EOD `2026-07-24` 并列且无任何解释"。

统一后的唯一入口在 `app/service_modules/market_data.py`（任务 8.1 落地，任务 8.2 接线）：

| 函数 | 作用 | 调用方 |
| --- | --- | --- |
| `market_eod_key(market, *, data_type="eod", source_id="")` | 解析 `(market, source_id, data_type)`；未登记市场（含 `H`、空串）回落 A 市场公开 EOD 源；`source_id` 非空即显式覆盖 | `scripts/daily_market_insight._market_eod_target(s)`、`SystemService._market_eod_key` |
| `freshness_lag(...)` | 精确日历差 `lag_days` + `reason_code` + `is_lagging` | `market_freshness_annotation` |
| `freshness_reason_label(reason_code)` | 原因码 → 中文文案（脚本 Markdown、UI 共用一套措辞） | `market_freshness_annotation`、脚本 `_freshness_note` |
| `market_freshness_annotation(...)` | 三元键 + 两个并列日期 + 滞后标注的组合出口 | `SystemService._market_freshness_annotation`、脚本 `_fetch_latest_market_context` |

原因码判定优先级（`_freshness_reason_code`）：`security_suspended_or_delisted`（`Security.status` 非空且非 `active`）> `source_partial_coverage`（市场批次覆盖率 < 0.9）> `security_not_in_latest_eod_batch`（默认）。`lag_days <= 0` 时 `reason_code` / `reason_label` 为空串、`is_lagging=False`；任一日期缺失或不可解析时返回 `lag_days=0` 且不标注滞后（属"行情待补"，由调用方单独呈现）。

响应字段变化一律**加法**，既有键名与语义不变：

| 出口 | 新增键 |
| --- | --- |
| `GET /api/company-intelligence/{symbol}` → `facts_and_events` | `latest_market_freshness`（`market` / `source_id` / `data_type` / `company_as_of_date` / `market_eod_date` / `lag_days` / `reason_code` / `reason_label` / `is_lagging`） |
| `POST /api/market-data/backfill-coverage` → `markets[*]` | `data_type`、`lagging_count`、`lagging_samples[]`（每条含 `security_id` / `ticker` / `latest_as_of_date` + 上述标注键） |
| `GET /api/analysis/latest` → `company_intelligence.companies[*]` | `market_freshness`（物化快照与逐公司兜底两条路径同时透传） |
| `daily-insight` 产物 → `research_and_events.company_recent_activity[*].latest_market` | `market_eod_date`、`lag_days`、`reason_code`、`reason_label`、`is_lagging`；Markdown 追加"滞后市场 EOD {日期} 共 N 天（原因）" |

`lagging_samples` 与既有 `stale_samples` 是两个口径，互不替代：`stale` 比的是"请求 `as_of_date` − 该证券最新日期 > `stale_after_days`"，`lagging` 比的是"该证券最新日期 < 同键市场 EOD 日期"（阈值为 0，即只要落后一批就标注）。

行为修正（非纯加法）的两处，均为把跨源混取收敛回同键取数：

- `scripts/daily_market_insight.py` 公司活动条目：SQL 由 `source_id = ANY([source_a, source_u])` 改为按市场分组、每组一个 `source_id` + `market` 过滤。变更前同一 A 股标的若在美股源下存在更新的行，会被当成它的"最新行情"；变更后不会。回归：`test_cross_market_source_rows_no_longer_win`。
- `SystemService.market_data_backfill_coverage_report`：`data_type` 由 `filters.get("data_type", "eod")` 改为经 `market_eod_key` 解析（空串也回落 `eod`），`source_id` 解析路径不变（`ashare_source_id` / `us_source_id` / `source_id` 覆盖 + `SOURCE_ID_ALIASES` 归一）。回归：`ServiceMarketEodKeyTests` 3 条。

`/api/analysis/latest` 顶层 `latest_market_date`（`app/api.py:851` 变更前行号）取自 `scripts/latest_analysis_run.py` 物化的 asset 列表。该脚本是纯 stdlib HTTP 客户端（无 `app` 包导入、可对远端 base_url 运行），本任务未给它加 `sys.path` 引导去 import 领域模块，而是用 `LatestAnalysisAssetSourceParityTests` 把它的两个硬编码 source（`public_eod_market_data` / `yahoo_chart_us_eod`）与 `MARKET_EOD_SOURCES` 锁成同值。改动该取值需同时改 `MARKET_EOD_SOURCES`，否则该回归失败。

### 护栏口径（后续任务必须遵守）

- 路由可达性一律用**子集断言**：变更前快照中的每一条 `(method, path)` 都必须仍存在于变更后 `build_route_table` 结果中；**不得**断言路由总数等于 461 或 334，也不得把这两个数字写进测试。
- 测试总数护栏：变更后 `countTestCases()` 必须 ≥ 551，且既有断言语义不得被改写。
- 本任务全部产物固定 `classification=local-only`、`production_release_gate_eligible=false`，不可作为非本机发布门禁输入。

## Proposed Work Plan

1. 已先落 `app/service_modules/` 纯函数层并用 21 条属性不变量锁定阶段、候选、证据、状态与幂等行为。
2. 已统一 `completeness_policy` 与 `market_data` 新鲜度口径，并适配完整度 `status` 取值域。
3. 已完成 dataclass / store / 配置、`SystemService` facade、API、CLI 与首屏接线。
4. 已用可提交 fixture 验证变更前路由是变更后路由子集，并完成全量门禁、浏览器与本机延迟采样。
5. 已同步契约、T-620 至 T-624、Kiro 清单与本 handoff。

## Validation Plan

- `.venv/bin/python -m unittest tests.test_daily_mainline_properties -v`：21 条属性测试通过，每条至少 100 次迭代。
- `make PYTHON=.venv/bin/python local-ci`：779 个测试及全部本地质量门通过。
- `node scripts/ui_dashboard_module_check.mjs`、`scripts/ui_static_check.py`：主线模块与静态契约通过。
- `scripts/ui_browser_acceptance.py`：桌面 1440×1000、移动 390×844 均非空且必需文案齐全。
- `scripts/ui_interaction_acceptance.py`：本任务新增的 5 个维护态深链与主线失败阶段/原因断言全部通过；全套 55 项中另有 2 个既有股权/图谱断言失败，详见 Risks。
- `scripts/latency_audit.py`：`daily_mainline_queue` 单次本机样本 260.23 ms，低于 5000 ms 阈值。

## Dependencies

- 本机 Compose 栈（PostgreSQL / MinIO / OpenSearch）与已注入的 LLM gateway、PaddleOCR-VL 凭据，仅后续任务的本机采样与冒烟需要；任务 1.1 未触达任何服务。
- git 修订版 `e70e1e9` 保持可达，否则路由快照的重建命令需换成快照文件本身。
- T-605 最新分析物化热读路径（首屏清单读路径复用）。

## Blockers

- 无本任务阻塞。spec 评审阶段的 4 项待确认事项已于 2026-07-28 全部获批。

## Files Touched

- `docs/agent-handoffs/2026-07-28-T-620-daily-mainline-usability.md`：本文件，新建；记录变更前基线、路由快照依据与护栏口径。
- `artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv`：新建（`local-only`，被 `.gitignore` 覆盖）；变更前 461 条 `(method, path)` 快照数据。
- `artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.json`：新建（`local-only`，被 `.gitignore` 覆盖）；快照 manifest 与摘要哈希。
- 生产代码（任务 1.1）：未改动任何 `app/`、`scripts/`、`tests/` 文件。
- `app/static/index.html`（任务 7.3，+60 −7 行）：新增 `COMPLETENESS_STATUS_LABELS` / `completenessStatusLabel()` / `companyIntelVerdictView()`；`companyIntelVerdictTone()` 改按 `blocking_gaps` 判红；完整度判断区块与个人视图摘要改走同一解析器；完整度表新增"覆盖度分层"行；`statusLabel()` 只加取值域注释，通用文案未改。
- `app/api.py`（任务 7.3，+7 行注释）：`/api/analysis/latest` 逐公司兜底路径的 `is_complete` 计数处标注口径收紧，代码逻辑未改。
- `scripts/latest_analysis_run.py`（任务 7.3，+8 行注释）：物化快照路径同上。
- `tests/test_completeness_policy.py`（任务 7.3，+42 行）：新增 `UiCompletenessValueDomainTests` 4 条 UI/后端取值域对齐回归；文件本体由任务 7.1 创建，既有断言未改。
- `docs/api-contracts.md`（任务 7.3，+7 −4 行）：补 `completeness_verdict` 取值域段落与 `ready_count` 口径说明，头部 `Last updated` 改 2026-07-28、`Related tasks` 追加 T-622。
- `app/service_modules/market_data.py`（任务 8.1，+210 −1 行）：新增 `MARKET_EOD_SOURCES` / `DEFAULT_EOD_SOURCE_ID` / `DEFAULT_EOD_DATA_TYPE` / `FRESHNESS_REASON_CODES` / `FRESHNESS_REASON_LABELS` / `ACTIVE_SECURITY_STATUSES` / `SOURCE_COVERAGE_THRESHOLD` 与 `market_eod_key` / `freshness_lag` / `freshness_reason_label` / `market_freshness_annotation`；既有除权调整函数未改。
- `app/services.py`（任务 8.2，+114 −6 行）：`_market_data_source_for_market` 改为 `_market_eod_key(...)["source_id"]` 的薄壳（签名与返回类型不变），新增 `_market_data_source_override` / `_market_eod_key` / `_market_eod_latest_date` / `_company_latest_market_freshness` / `_market_freshness_annotation` 五个私有委派方法；`market_data_backfill_coverage_report` 与 `company_intelligence` 改由同键取数并透传标注。判定逻辑全部在 `app/service_modules/market_data.py`，`SystemService` 内无新增业务判定。
- `scripts/daily_market_insight.py`（任务 8.2，+146 −14 行）：新增 `ROOT` `sys.path` 引导与 `market_eod_key` / `market_freshness_annotation` 导入；新增 `_market_eod_target` / `_market_eod_targets` / `_freshness_note`；`_fetch_latest_market_context` 拆为按市场分组取数（`_fetch_latest_market_rows`）+ 滞后标注；`market_targets` 改由 `_market_eod_targets` 提供；`_market_snapshot` / `_research_readout` / `_activity_summary` / `build_markdown` 输出滞后标注。
- `app/api.py`（任务 8.2，+5 行）：`/api/analysis/latest` 逐公司兜底路径透传 `market_freshness`（读 `facts_and_events.latest_market_freshness`），既有键未改。
- `scripts/latest_analysis_run.py`（任务 8.2，+4 行）：物化快照路径同上透传 `market_freshness`。
- `tests/test_market_eod_freshness.py`（任务 8.1，新建 288 行）：领域模块单元测试 26 条（键解析、精确日历差、原因码优先级、文案、组合出口、与既有调用点的常量一致性）。
- `tests/test_market_eod_freshness_wiring.py`（任务 8.2，新建 359 行）：接线测试 19 条。脚本侧用最小 psycopg cursor 替身断言"实际发出的取数键 == `market_eod_key`"；服务侧用真实 `SystemService` + `ApiRouter`（无 mock 数据）断言公司情报、覆盖报告、`/api/analysis/latest` 两条路径的标注一致。
- `docs/api-contracts.md`（任务 8.2，+3 −1 行）：补 backfill-coverage 的 `data_type` / `lagging_*`、`facts_and_events.latest_market_freshness` 与 latest-analysis `market_freshness` 透传段落。

### Final delivery additions

- `app/service_modules/daily_mainline.py`、`daily_mainline_scan.py`、`daily_mainline_diligence.py`、`daily_mainline_artifact.py`：阶段、候选、尽调、脱敏产物领域逻辑；最终补充基于实时剩余预算的尽调单次超时分配，并为非 LLM 工作和清单持久化预留预算。
- `app/models.py`、`app/store.py`：三类每日主线记录及 SQLite/PostgreSQL collection/query 接线。
- `app/services.py`：五个兼容 facade、跨模块编排、存储、审计与 latest-analysis 计数加键；`run_daily_mainline` 只计算总 deadline 并向尽调阶段注入实时剩余预算回调。
- `app/api_routes.py`、`app/api.py`：`/api/daily-mainline/*` 五个路径、七个 method-route pair 及权限/handler。
- `scripts/daily_mainline_run.py`、`Makefile`、`.env.example`：CLI、`make daily-mainline` 与集中配置。
- `app/static/index.html`、`app/static/ui_modules/dashboard.mjs`、`app/static/ui_modules/helpers.mjs`：首屏“今天看什么”、清单状态、失败阶段、watchlist 和维护态深链。
- `scripts/ui_static_check.py`、`scripts/ui_dashboard_module_check.mjs`、`scripts/ui_interaction_acceptance.py`、`scripts/daily_data_update_pipeline.py`：静态、模块、点击与延迟探针验收。
- `tests/test_daily_mainline.py`、`tests/test_daily_mainline_properties.py`、`tests/data/t620-route-snapshot.tsv`：集成、21 条属性和路由子集回归；新增带每候选 12 秒非 LLM 开销的总预算回归，证明最终清单阶段仍执行。
- `README.md`、`docs/api-contracts.md`、`docs/artifact-governance.md`、`docs/user-manual.md`、`docs/latest-analysis-chain.md`、`tasks/todo.md`、`.kiro/specs/project-usability-improvement/tasks.md`：使用、契约、证据、路线图与完成状态。

## Commands Run

```bash
python3 -c "import unittest;s=unittest.defaultTestLoader.discover('tests');print(s.countTestCases())"
python3 -m unittest tests.test_daily_mainline tests.test_daily_mainline_scan tests.test_daily_mainline_artifact tests.test_completeness_policy
grep -cE '^\s+\("(GET|POST|PUT|DELETE|PATCH)"' app/api_routes.py
grep -oE '\^/api/[^"]*\$' app/api_routes.py | sort -u | wc -l
wc -l app/services.py app/api_routes.py app/static/index.html
python3 -c "import sys;sys.path.insert(0,'.');from unittest.mock import MagicMock;from app.api_routes import build_route_table;t=build_route_table(MagicMock());print(len(t), len({(m,p) for m,p,_ in t}), len({p for _,p,_ in t}))"
git show e70e1e9:app/api_routes.py \
  | grep -oE '\("(GET|POST|PUT|DELETE|PATCH)", r"\^[^"]*\$"' \
  | sed -E 's/^\("([A-Z]+)", r"(.*)"$/\1\t\2/' \
  | sort -u > artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv
sha256sum artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv
LC_ALL=C python3 -c "import hashlib,json,sys;rows=[l.rstrip('\n').split('\t') for l in open(sys.argv[1],encoding='utf-8')];routes=[{'method':m,'path_pattern':p} for m,p in sorted(rows)];print(hashlib.sha256(json.dumps(routes,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest())" artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv
git check-ignore -v artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.json artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv
# 用 scripts/security_check.py 的既有 SECRET_PATTERNS 预扫本文件与 manifest（临时探针脚本，已删除）
python3 scripts/check_handoffs.py
python3 scripts/check_doc_metadata.py
python3 scripts/check_markdown_links.py
```

Result:

- Passed: `countTestCases()` = 551（任务开始时点），与 spec 记录一致；并行 wave 0 落文件后复算 586，减去新增 4 个测试文件的 35 个用例正好回到 551。
- Passed: 路由 grep 计数 461 条 `(method, path)` / 334 条唯一路径，与运行期 `build_route_table` 提取的 461 / 461 / 334 一致（GET 168、POST 293）。
- Passed: `wc -l` 得 `app/services.py` 31,956、`app/api_routes.py` 473、`app/static/index.html` 12,650。
- Passed: 快照 TSV 461 行、334 个唯一路径，`sha256=9d1d7c14dbe6e4da039579ca84856fd07f92c4d43751c688b447192aa99f8a19`；由 TSV 复算的 `routes_canonical_json_sha256=8b849a65baff54224ca1d24b3555d8fdd81a8a57651c0fecaf8a15eb0b2fa887`，与运行期提取结果相同。
- Passed: `git check-ignore` 确认两个快照文件命中 `.gitignore:45` 的 `artifacts/*`，不会进入提交。
- Passed（修正后）：secret 规则预扫初次命中 `paddleocr_token_literal`（原因是文中写了 40 位完整 git 修订号），已改为短修订号 `e70e1e9` 后复扫无命中；sha256（64 位）不触发该规则。
- Passed: `python3 scripts/check_handoffs.py` —— handoff validation passed，检查 `docs/agent-handoffs/` 下 203 个 markdown 文件（含本文件）。
- Passed: `python3 scripts/check_doc_metadata.py` —— canonical document metadata validation passed，检查 5 个规范文档。
- Not run: `make local-ci` 全量（含 `unittest discover`、`ui_static_check`、`security_check`、`check_markdown_links`）留到任务 16.4；本轮未改生产代码，只做基线与文档，按任务约束仅跑两个校验脚本。

### 任务 7.3（取值域依赖面适配）

```bash
.venv/bin/python -m py_compile app/api.py scripts/latest_analysis_run.py tests/test_completeness_policy.py
node --check app/static/ui_modules/dashboard.mjs
sed -n '3519,12697p' app/static/index.html > /tmp/t73_index_script.js && node --check /tmp/t73_index_script.js
.venv/bin/python -m unittest tests.test_completeness_policy
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -c "import unittest;s=unittest.defaultTestLoader.discover('tests');print(s.countTestCases())"
.venv/bin/python scripts/ui_static_check.py
.venv/bin/python scripts/security_check.py .
.venv/bin/python scripts/check_markdown_links.py
.venv/bin/python scripts/check_handoffs.py
node scripts/ui_dashboard_module_check.mjs
```

Result（任务 7.3）：

- Passed: `py_compile`、`node --check`（dashboard 模块与 index.html 内联脚本）。
- Passed: `tests.test_completeness_policy` 23 个用例（含新增 4 条 UI 取值域对齐回归）。
- Passed: `unittest discover -s tests` 全量与 `countTestCases()` 复算（数值见任务 7.3 执行记录，≥ 基线 551）。
- Passed: `ui_static_check.py`、`security_check.py .`、`check_markdown_links.py`、`check_handoffs.py`、`ui_dashboard_module_check.mjs`。
- 说明: `ready_count` 变化用临时探针按 `completeness_policy.resolve_status` 复算最新物化产物的 9 家公司记录输入（探针为 `/tmp` 临时文件，已删除，命令与结论见"响应取值域契约变更"段）。

### 任务 8.2（行情新鲜度取数接线）

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
.venv/bin/python -m unittest tests.test_market_eod_freshness tests.test_market_eod_freshness_wiring
.venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/security_check.py .
```

Result（任务 8.2）：

- Passed: `py_compile`（`app/` / `tests/` / `scripts/` 全量）。
- Passed: `tests.test_market_eod_freshness`（26 条）+ `tests.test_market_eod_freshness_wiring`（19 条）。
- Passed: `.venv/bin/python -m unittest discover -s tests` —— 726 个用例全通过（≥ 基线 551）。
- Passed: `scripts/security_check.py .` —— `ok=true`、`findings=[]`、`checked_files=559`。
- 环境漂移（与本任务无关，不隐藏）：系统 `python3`（非 `.venv`）跑 `unittest discover -s tests` 得 3 failures / 14 errors，全部落在 `tests/dynamic_allocation/*`，根因是该解释器缺 `PyYAML` / `xgboost` / `lightgbm`（首个失败 `tests.dynamic_allocation.test_repositories` → `ModuleNotFoundError: No module named 'yaml'` → `RuntimeError: dynamic allocation YAML config requires PyYAML`）。用仓库 `.venv/bin/python`（Python 3.14.3，依赖完整）同一命令 726 用例全绿。后续任务与任务 16.4 的全门禁请统一用 `.venv/bin/python`。

### Final verification (2026-07-29)

```bash
.venv/bin/python -m unittest tests.test_daily_mainline_properties -v
.venv/bin/python -m unittest tests.test_daily_mainline tests.test_market_eod_freshness tests.test_market_eod_freshness_wiring
node scripts/ui_dashboard_module_check.mjs
.venv/bin/python scripts/ui_static_check.py
make PYTHON=.venv/bin/python local-ci
.venv/bin/python scripts/ui_browser_acceptance.py http://127.0.0.1:55538 --output-dir artifacts/t620-ui-browser-acceptance --timeout 30
.venv/bin/python scripts/ui_interaction_acceptance.py http://127.0.0.1:55538 --output-dir artifacts/t620-ui-interaction-acceptance --timeout 30
.venv/bin/python scripts/latency_audit.py --base-url http://127.0.0.1:55538 --output artifacts/t620-daily-mainline-acceptance/latency-audit.json --max-ms 5000 --timeout 30
```

Result:

- Passed: 21/21 property tests；每条属性至少 100 次固定种子迭代。
- Passed: daily-mainline 与行情新鲜度聚焦回归 205 项。
- Passed: 运行期路由表 468 个唯一 method-route pair / 339 个唯一路径；变更前 461 个 pair fixture 全部仍存在。
- Passed: dashboard 模块 13 项、静态 UI、模块语法检查。
- Passed: `make local-ci`，779 个测试；`py_compile`、UI static、安全扫描（559 个文件、0 findings）、Markdown、handoff 与规范文档元数据全绿。
- Passed: 浏览器 DOM 与桌面/移动截图，0 failure；截图 1440×1000 与 390×844，均非空且无首屏文字遮挡。
- Passed: 本任务新增交互断言 6/6（5 个维护态深链 + 主线失败阶段/原因）。全脚本另有 2 个既有公司股权/图谱断言失败，53/55 通过；未隐藏，见 Risks。
- Passed: 延迟审计 5/5；`daily_mainline_queue` 260.23 ms，阈值 5000 ms。
- Passed: 独立临时 SQLite 实例执行真实 `POST /api/daily-mainline/run`，在无当日行情时生成 `scan_market_disturbance / market_data_unavailable` 的失败阶段和脱敏 `local-only` artifact；`paper_only=true`、`live_execution_allowed=false`。

### Local service switch (2026-07-29)

```bash
docker compose restart ai-quant-org
docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS -H 'X-Role: analyst' 'http://127.0.0.1:8000/api/daily-mainline/queue?limit=5'
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/metrics
.venv/bin/python scripts/ui_browser_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/t624-live-switch-browser --timeout 30
docker compose logs --since=2m ai-quant-org
systemctl --user status ai-quant-daily-update.timer --no-pager --full
```

Result:

- Passed: 仅 `ai-quant-org` 重启；PostgreSQL、MinIO、OpenSearch 与其他 Compose 服务未重启。
- Passed: 应用容器 `healthy`；`/api/health` 返回 `PostgreSQLStore`、S3、OpenSearch、LLM configured；`/api/metrics` 返回 HTTP 200。
- Passed: `/api/daily-mainline/queue` 从切换前 HTTP 404 变为成功响应；当前为空清单，且固定 `paper_only=true`、`live_execution_allowed=false`。
- Passed: 生产样本栈桌面/移动截图与 DOM 验收 0 failure；重启后两分钟日志无新 `Traceback` / `Exception` / `ERROR`。
- Passed: 用户级 `ai-quant-daily-update.timer` 为 `active` / `enabled`；系统级同名 unit 不存在是预期作用域差异。

### Runtime timeout regression and final switch verification (2026-07-29)

```bash
make PYTHON=.venv/bin/python local-ci
docker compose restart ai-quant-org
curl -fsS -H 'X-Role: analyst' -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":120,"candidate_limit":4,"market_quota":2,"diligence_limit":2}' \
  http://127.0.0.1:8000/api/daily-mainline/run
curl -fsS -H 'X-Role: analyst' \
  'http://127.0.0.1:8000/api/daily-mainline/queue?run_id=dmrun_1f3cb197583e'
docker compose logs --since=5m ai-quant-org
systemctl --user is-active ai-quant-daily-update.timer
```

Result:

- Root cause: 编排器只在阶段边界检查总预算；自动尽调对最多 8 个候选串行调用 LLM，每次仍可使用 120 秒 gateway timeout，且未计入每候选约 8–12 秒的公司上下文读取、lineage、审计和持久化开销。`dmrun_290c25d79736` 用时约 896 秒、`dmrun_cb10610bf9ae` 用时约 677 秒，均在自动尽调后把 `build_daily_queue` 标为 `timeout_budget_exceeded`。
- First attempt not accepted: 仅按剩余预算平均分配 LLM timeout 后，`dmrun_7c2cbf851b9b` 在 120 秒配置下仍用时 129.5532 秒，`queue_count=0`，证明还必须显式预留非 LLM 开销。
- Passed: 最终分配器为最终清单预留总预算的 10%（最多 30 秒），并在每个候选的公平份额内另留 12 秒非 LLM 开销；每次调用前都按实时剩余预算和剩余候选重新计算 timeout。
- Passed: 相同 120 秒、4 个候选、2 个自动尽调的生产样本 `dmrun_1f3cb197583e` 用时 112.7626 秒；`build_daily_queue=passed`、`queue_count=4`、`researchable_count=4`，没有 `timeout_budget_exceeded`。
- Expected partial state: 两个短预算 LLM 调用返回 `llm_timeout`，因此 run 状态为 `partial`；候选及原因码均被保留，最终清单不再被丢弃。
- Passed: 最新清单 GET 返回 HTTP 200，约 48.54 ms；PostgreSQL 持久化 4 条 queue item，应用日志无新 `Traceback` / `Exception` / `ERROR`，容器 healthy，用户级每日更新 timer 为 `active`。
- Passed: 最终 `make PYTHON=.venv/bin/python local-ci` 共 779 个测试全绿，包含 `py_compile`、UI static、安全扫描（559 个文件、0 findings）、Markdown、handoff 和文档元数据门禁。

## Evidence

- `artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.tsv`：producer 为上方 `git show e70e1e9:app/api_routes.py | grep | sed | sort -u` 管道；用途是任务 13.2 的"变更前 ⊆ 变更后"子集断言依据；环境为本机开发工作站（acp-client），生成时间 2026-07-28T05:12:31Z（UTC）；owner group 产品与 UI；无敏感数据（只含 API 路径正则）；分类 `local-only`，`production_release_gate_eligible=false`，不可作为非本机发布门禁证据。
- `artifacts/t620-baseline/route-snapshot-2026-07-28-pre-t620.json`：producer 为本任务写出的 manifest（`schema_id=route-snapshot-baseline-v1`）；用途是快照的分类元数据、计数、两个摘要哈希与复算命令；环境与新鲜度同上；无敏感数据；分类 `local-only`，`production_release_gate_eligible=false`。
- `artifacts/t620-daily-mainline-acceptance/daily-mainline-2026-07-28-dmrun_4eef856c1f04.json`：producer 为独立临时 SQLite 实例上的 `POST /api/daily-mainline/run`；生成于 2026-07-29，本机开发环境，owner 产品与 UI；无密钥或完整模型响应；记录无行情时 `market_data_unavailable` 阶段失败；`local-only`，不可用于非本机发布门。
- `artifacts/t620-daily-mainline-acceptance/latency-audit.json`：producer 为 `scripts/latency_audit.py`；生成于 2026-07-29，本机独立实例，owner 平台与质量；无敏感数据；5 个探针全通过，主线清单样本 260.23 ms；`local-only`，不是生产 p95 证据。
- `artifacts/t620-ui-browser-acceptance/`：producer 为 `scripts/ui_browser_acceptance.py`；生成于 2026-07-29，本机 Chrome；包含桌面/移动截图，无账户凭据或业务私密数据；`local-only`，0 failure。
- `artifacts/t620-ui-interaction-acceptance/`：producer 为 `scripts/ui_interaction_acceptance.py`；生成于 2026-07-29，本机 Chrome + 临时 SQLite；本任务新增断言全通过，全套 53/55；只含验收夹具与结果，`local-only`。
- `artifacts/t624-live-switch-browser/`：producer 为切换后的 `scripts/ui_browser_acceptance.py`；生成于 2026-07-29，本机 Compose production-like 栈与 Chrome；桌面/移动截图均非空，0 failure；无密钥，`local-only`，不可用于非本机发布门。
- `artifacts/daily-mainline/daily-mainline-2026-07-28-dmrun_290c25d79736.json` 与 `daily-mainline-2026-07-28-dmrun_cb10610bf9ae.json`：producer 为本机 Compose 栈上的每日主线 API；记录修复前自动尽调耗尽总预算、最终清单被跳过的原始故障；无完整模型响应，`local-only`，不可用于非本机发布门。
- `artifacts/daily-mainline/daily-mainline-2026-07-28-dmrun_7c2cbf851b9b.json`：producer 为第一次预算修复后的 120 秒生产样本；记录 129.5532 秒且清单仍被跳过的未通过证据，明确该版本未作为验收结果；无完整模型响应，`local-only`。
- `artifacts/daily-mainline/daily-mainline-2026-07-28-dmrun_1f3cb197583e.json`：producer 为最终预算分配实现后的同条件 API 回归；生成于 2026-07-29，本机 Compose production-like 环境，owner 产品与 UI；`build_daily_queue=passed`、4 条 item、`paper_only=true`、`live_execution_allowed=false`；无完整模型响应，`local-only`，不可用于非本机发布门。
- 上述产物均不含密钥、签名 URL 或完整模型响应。

## Decisions

- 快照落成方式：数据落 TSV（461 行、18 KB）、元数据落 JSON manifest，都放 `artifacts/t620-baseline/`。理由：`artifacts/*` 已被 `.gitignore` 覆盖，天然满足 `local-only` 且不产生提交噪声；快照可从 git 修订版 `e70e1e9` 完整重建，所以本文档只记生成命令与摘要哈希，不把 461 行清单复制进 `docs/`。
- 双路提取交叉校验：同时用源码正则与运行期 `build_route_table(MagicMock())` 提取并比对摘要哈希。理由：单一提取方式可能漏掉换行或动态注册的条目，两路一致才能把快照当作护栏依据。`MagicMock` 只用于让 handler 属性解析成功，不参与任何断言逻辑。
- 护栏一律子集断言：`pre ⊆ post`，不硬编码 461 / 334。理由：路由数量是易漂移基线，硬编码会在任何追加路由时假失败，也会掩盖删除行为（子集断言才真正拦住删除）。
- 基线以本机实测为准：spec 的 551 / 461 / 334 / 31,956 已复核一致；`app/service_modules/` 的 33 / 8,787 已漂移为 36 / 10,093，按实测记录且不回改 spec（非护栏输入项）。
- 本轮不动生产代码，也不预先创建任务 13.2 的测试 fixture：fixture 形态由任务 13.2 自行决定，本任务只提供数据与哈希。
- 任务 8.2：滞后标注一律**加字段**，不改既有 `latest_market_snapshot` / `stale_samples` / `latest_market_date` 的取值与语义。理由：这三个键已被 UI、脚本与既有测试消费，改语义属破坏性变更且需求 5.7 只要求"标注滞后天数与原因码"，加法即可满足。
- 任务 8.2：`market_eod_key` 的显式覆盖（`source_id` 非空即优先）保留了 `--source-a` / `--source-u` 与 `ashare_source_id` / `us_source_id` / `source_id` 三条既有覆盖通路。理由：这些参数是本机换源（如 `tdx_vipdoc_eod`）的现役入口，收敛取数键不应顺带收掉换源能力。覆盖值的别名归一仍留在调用方（`SystemService._canonical_source_id`），领域模块不引入对 `SOURCE_ID_ALIASES` 的依赖。
- 任务 8.2：脚本侧公司行情取数改为"按市场分组、每组一次查询"，而不是保留单条 SQL 再在 Python 侧过滤。理由：单条 SQL 的 `DISTINCT ON (security_id) ... ORDER BY as_of_date DESC` 会在数据库侧就把跨源的错误行选定，Python 侧无法还原；分组查询让每次查询的键与 `market_freshness` 完全一致，也让"实际发出的键"可被测试直接断言。
- 总预算语义：`timeout_seconds` 是四个阶段共享的 wall-clock 预算，不是每个 LLM 调用的独立 timeout。单次尽调 timeout 按实时剩余预算重算，并显式预留每候选非 LLM 工作与最终清单持久化时间；理由是清单是主线的用户可见终态，单个 AI 调用超时不得导致候选和清单整体丢失。

## Risks and Open Questions

- 全套 `scripts/ui_interaction_acceptance.py` 在独立临时库上有 2 个与每日主线无关的既有失败：`company_ownership_approved_same_holder_network_context` 未生成预期事实股东关联摘要，`company_graph_inspector_neighbor_shows_relationship_label` 的邻居标签断言未满足。每日主线新增的 6 个断言全部通过；这两个问题不在 T-620 至 T-624 范围内，应另立公司关系图谱任务处理。
- `ApiRouter.dispatch` 仍使用进程内全局 dispatch lock；同步每日主线运行期间，其他业务 API 请求会排队，而独立 health endpoint 仍可用。本轮修复保证主线在预算内收口，没有改变全局并发模型；若需要运行中实时查询进度，应另立异步 job/细粒度锁任务。
- 在较短总预算下，单个候选仍可能出现 `llm_timeout`，run 因此为 `partial`。这是预期降级：候选、触发原因、既有证据和最终清单全部保留，可按 `next_actions` 延长预算重跑。
- 变更前快照产物被 `.gitignore` 覆盖；任务 13.2 已把同一清单固化为可提交的 `tests/data/t620-route-snapshot.tsv`，当前回归验证其为变更后路由表子集。
- 完整度 `status` 取值域收敛（`usable_with_gaps` / `incomplete` → `partial`）是破坏性响应取值域变更（已于 2026-07-28 获批）。依赖面适配已由任务 7.3 完成并记入本文件"响应取值域契约变更"段。遗留风险：`artifacts/daily-update-local/runs/*` 下 2026-07-28 之前的物化产物仍带收敛前取值，`/api/analysis/latest` 读旧产物时会回放旧 `status` / `label`；UI 侧已把旧取值归并显示为 `部分完整`，但产物文件本身不回填，需要收敛后取值时重跑 `scripts/latest_analysis_run.py`。
- `ready_count` 口径收紧后本机 9 家深度覆盖公司全部落入 `needs_attention`（5 → 0），`/api/analysis/latest` 的 `company_intelligence.status` 会显示 `watch`。若产品侧希望首屏仍有"就绪"计数，需要另立补数任务（补齐事实字段与三项覆盖度），不得回调阈值绕过判定。
- 关注池摘要（`scripts/personal_intelligence_refresh.py:77` → `index.html` `renderPersonalIntelligenceSummary`）的 `completeness_status` 取的是 `coverage_level`（`complete` / `partial` / `sparse` 的评分档位），不是 `completeness_verdict.status`，界面上显示为通用文案"部分补齐"。任务 7.3 已核对两者不串，但同一屏出现"部分补齐"与"部分完整"两种措辞仍有认知成本；是否把关注池摘要也切到统一口径属产品侧取舍，需求 5.3 只约束公司情报响应与当日清单（后者由任务 11.1 直接引用 `completeness_policy` 返回值）。
- 新增 3 个 store collection 对 `/api/analysis/latest` 的 `counts` 只允许**加法**补键，不得改为按 `COLLECTIONS` 全量派生（任务 9.4 落成验证）。
- 任务 8.2 遗留：`facts_and_events.latest_market_snapshot`（既有键，取"全部行里最新一条"）与新增 `latest_market_freshness.company_as_of_date`（只取 `market_eod_key` 同键下最新一条）在公司同时拥有非同键行情行（例如 `data_type=delayed` 或其他源）时会给出不同日期。两者语义都正确且各自自述来源，但同屏并列仍有认知成本；UI 任务（15.x）呈现"最新行情日期"时应取 `latest_market_freshness.company_as_of_date`，并把 `market_eod_date` / `lag_days` / `reason_label` 一起显示。回归见 `test_annotation_ignores_rows_outside_the_eod_key`。
- 任务 8.2 遗留：公司情报在直连查询模式下每只证券只取最近 `min(limit, 20)` 行（`app/services.py:26742`）。若某证券最近 20 行全部来自非同键源，`latest_market_freshness.company_as_of_date` 会为空串并按"行情待补"处理（`lag_days=0`、不标注滞后），而不是报一个很大的滞后天数。这是有意的降级口径（见 `freshness_lag` docstring），但会掩盖"该证券在同键源下确实很久没数据"的情况；需要精确判定时应走 backfill-coverage 报告的 `lagging_samples`。
- 任务 8.2 遗留：`scripts/latest_analysis_run.py` 的两个 EOD source 仍是硬编码字面量，只由 `LatestAnalysisAssetSourceParityTests` 锁成与 `MARKET_EOD_SOURCES` 同值，未改为 import 领域模块（理由见"行情新鲜度同源"段末：该脚本是可对远端 base_url 运行的纯 stdlib HTTP 客户端）。若未来允许该脚本导入 `app` 包，应把这两处一并切到 `market_eod_key`。
- 任务 8.2 遗留：`reason_code` 的 `source_partial_coverage` 目前只有 backfill-coverage 报告会传入覆盖率信号；公司情报视图不传，因此该路径上市场级批次缺口会被归到 `security_not_in_latest_eod_batch`。要在公司视图区分两者，需要先有一处按市场缓存批次覆盖率的读模型，属后续任务。
- 测试总数 551 是本机 `defaultTestLoader.discover('tests')` 的取数，若后续出现环境漂移导致 discover 结果变化，须在本文件记录实际值与根因，不得直接下调护栏。
- `app/service_modules/` 已达 10,093 行；本轮再加 5 个模块，后续若需要拆分或建子包，属跨组（平台与质量）讨论项。
- 门禁陷阱（后续任务同样适用）：`scripts/security_check.py` 的 `paddleocr_token_literal` 规则（`\b[A-Fa-f0-9]{40}\b`）会把 40 位十六进制串（例如完整 git 修订号）判为疑似令牌。文档与被提交文件里一律用短修订号，需要完整值时用 `git rev-parse <short>` 现场解析。

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated（T-620 至 T-624 为 `DONE`）

## SystemService Growth Freeze Review

- New `SystemService` business logic added: 否。新增 `run_daily_mainline`、两个读模型和两个条目操作方法只负责跨模块编排、store、权限/审计和兼容 facade；本次 timeout 修复也只在 facade 计算 deadline、注入实时剩余预算回调。阶段、预算分配、候选、尽调、artifact、完整度与行情新鲜度判定均在 `app/service_modules/`。
- Domain placement: 每日主线业务规则与 `queue_stage_reserve_seconds` / `diligence_call_timeout_seconds` 位于 `daily_mainline*.py`，完整度位于 `completeness_policy.py`，行情键与滞后判定位于 `market_data.py`。`SystemService` 内保留 IO/委派方法和跨域编排，符合增长冻结例外。
- Focused regression: `tests/test_daily_mainline.py::DailyMainlineDomainTests.test_diligence_timeout_allocator_reserves_queue_budget` 保护纯预算分配，`DailyMainlineServiceTests.test_run_reserves_total_budget_for_queue_stage` 用可控时钟覆盖每候选非 LLM 开销并保护最终清单；`tests/test_daily_mainline_properties.py` 保护 21 条不变量；完整 `make local-ci` 779 项通过。
- Contract/boundary changes: 新增 5 个 API 路径、3 个 records collection、首屏 UI 与 latest-analysis 三个计数键；行情新鲜度字段均为加法。完整度 `status` 收敛为 `complete|partial|not_found` 是已批准的取值域变更。本次修复明确既有 `timeout_seconds` 的总预算语义，不改 API schema、存储 schema 或 UI 字段；`paper_only=true`、`live_execution_allowed=false`、不接券商、不自动下单边界未变。

## Next Steps

1. 日常使用从 `/ui` 首页“今天看什么”、`make daily-mainline` 或 `POST /api/daily-mainline/run` 进入；运行产物按 `run_id` 保留为 `local-only`。
2. 若处理验收残留，另立公司关系图谱任务修复上方 2 个既有交互断言，不修改每日主线契约。
3. 后续门禁统一使用 `.venv/bin/python`，避免系统 Python 缺少动态配置依赖造成环境漂移。

## Next Recommended Action

无每日主线剩余实现项。下一个独立改进应处理公司关系图谱的 2 个浏览器验收断言，或继续路线图中的五家公司官方事实缺口。
