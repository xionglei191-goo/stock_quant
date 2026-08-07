# 设计文档：项目可用性改进（每日一键研究主线）

- Status: active
- Owner group: 产品与 UI
- Reviewer groups: 研究与 AI 工作流、平台与质量、治理安全与合规、项目经理 / 发布协调
- Last updated: 2026-07-28
- Related tasks: T-605 最新分析热读、T-607 产品使用指标来源分层、T-608 五家公司证据闭环、T-619 研报导入收口
- Scope: `app/service_modules/` 新增每日主线领域模块、`SystemService` facade 方法、新增 `/api/daily-mainline/*` 路由、CLI 入口 `scripts/daily_mainline_run.py`、`app/static/index.html` 与 `app/static/ui_modules/`（`dashboard.mjs` / `helpers.mjs`）首屏与导航收敛、完整度与行情新鲜度口径统一、本机 artifact 写出
- Non-goals: 不扩大公司覆盖面、不接券商、不自动下单、不产出非本机发布证据、不重写单页 UI 为前端框架、不删除既有脚本与 API 路由
- Related requirements: `.kiro/specs/project-usability-improvement/requirements.md`

## 1. 设计目标与约束

需求把可用性问题归结为四类：入口分散、AI 层零运行、读数口径矛盾、运行无证据。设计对应四条主线：

1. 一个编排实现 + 两个薄入口（CLI / HTTP），阶段化执行并输出结构化阶段记录。
2. 自动尽调走已有 `SystemService.run_llm_task`，复用 `llm_task_templates` / `llm_task_runs` / `research_answers`，不新建 LLM 通路。
3. 完整度判定与行情新鲜度取数下沉为单一口径模块，公司情报响应与当日清单共用同一函数结果。
4. 每次运行写出一份 `local-only` artifact，文件名带 `run_id`，内容脱敏。

工程约束（AGENTS.md §8.1）：新增业务逻辑一律落在 `app/service_modules/`；`SystemService` 只增加 facade 与跨模块编排方法；不新增外部依赖（当前 `pyproject.toml` 运行期依赖仅 `PyYAML`，测试无 `hypothesis`）。

## 2. 架构

```text
入口层
  scripts/daily_mainline_run.py ──┐
  POST /api/daily-mainline/run ───┤ 都调用同一 facade
                                  ▼
facade 层（app/services.py，仅编排与鉴权/审计接线）
  SystemService.run_daily_mainline(payload, actor)
  SystemService.daily_mainline_queue_payload(filters)
  SystemService.add_daily_queue_item_to_watchlist(payload, actor)
  SystemService.review_daily_mainline_viewpoint(payload, actor)
                                  ▼
领域层（app/service_modules/）
  daily_mainline.py            阶段状态机 / 状态派生 / 进度投影 / next_actions
  daily_mainline_scan.py       扫市扰动指标 → 候选池（纯函数）
  daily_mainline_diligence.py  模板选择 / prompt 变量 / 观点组装 / 证据绑定 / 来源分层
  daily_mainline_artifact.py   artifact payload 构造 + 脱敏
  completeness_policy.py       完整度阈值与状态判定（唯一口径）
  market_data.py（扩展）        市场 EOD 取数键 + 滞后天数与原因码
                                  ▼
基础设施层（既有，不改契约）
  store（records / typed bars）  llm_gateway  object_store  audit_log
```

阶段化执行是编排的唯一控制流：

```text
scan_market_disturbance → build_candidate_pool → run_auto_diligence → build_daily_queue
```

阶段之间只通过 `StageResult.payload` 传递数据，任一阶段失败或超时都不改变后续阶段的位置，只把它们置为 `skipped`。这样阶段序列对任意数据状态都是常量，满足需求 1.2。

### 2.1 组件职责与需求映射

| 组件 | 落点 | 覆盖需求 |
| --- | --- | --- |
| 每日主线编排器 | `app/service_modules/daily_mainline.py` + `SystemService.run_daily_mainline` | 1.1-1.3, 1.9, 1.10, 1.12, 1.13, 7.1-7.3 |
| 扫市扰动扫描器 / 候选池构建器 | `app/service_modules/daily_mainline_scan.py` | 1.4 |
| 自动尽调器 | `app/service_modules/daily_mainline_diligence.py` | 1.5-1.8, 4.3-4.6 |
| LLM 任务模板库 | `daily_mainline_diligence.BUILTIN_TEMPLATES` + 既有 `SystemService.seed_default_llm_task_templates`（`app/services.py:316`） | 4.1, 4.2, 4.7 |
| 今日待研究清单 / 首屏总览 | `daily_mainline.build_queue_payload` + `app/static/index.html` dashboard 区块 | 2.1-2.8 |
| 关注池服务 | `SystemService.add_daily_queue_item_to_watchlist`（复用 `import_company_watchlist`） | 1.11 |
| UI 导航控制器 | `app/static/index.html` nav 分组与 `setWorkspaceMode` | 3.1-3.6 |
| 完整度口径服务 | `app/service_modules/completeness_policy.py`，由 `company_intelligence.completeness_verdict` 委派 | 5.1-5.5, 5.8 |
| 公司情报视图新鲜度 | `app/service_modules/market_data.py` 扩展 | 5.6, 5.7 |
| 证据产物写出器 | `app/service_modules/daily_mainline_artifact.py` | 6.1-6.5 |
| 平台质量门 / 交付 handoff | `make local-ci`、`docs/agent-handoffs/` | 3.6, 6.6, 7.4-7.10 |

## 3. 数据模型

### 3.1 新增 dataclass（`app/models.py`）

```python
@dataclass(slots=True)
class DailyMainlineRun:
    run_id: str
    run_date: str                                   # 数据 as_of_date（本地日历日）
    status: str = "passed"                          # passed | partial | failed | empty
    stages: list[dict[str, Any]] = field(default_factory=list)
    candidate_count: int = 0
    queue_count: int = 0
    unsupported_count: int = 0
    llm_run_ids: list[str] = field(default_factory=list)
    failure_reason_codes: list[str] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    timeout_seconds: int = 600
    elapsed_seconds: float = 0.0
    artifact_path: str = ""
    live_execution_allowed: bool = False
    paper_only: bool = True
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.status, {"passed", "partial", "failed", "empty"}, "status")


@dataclass(slots=True)
class DailyMainlineQueueItem:
    item_id: str
    run_id: str
    security_id: str
    issuer_id: str = ""
    ticker: str = ""
    market: str = ""
    rank: int = 0
    selection_reason: str = ""
    trigger_metric: str = ""                        # one_day_return | amount_ratio | volume_ratio | intraday_range
    trigger_value: float = 0.0
    as_of_date: str = ""
    completeness_status: str = "unknown"            # 来自 completeness_policy，禁止本地重算
    missing_layers: list[str] = field(default_factory=list)
    partition: str = "researchable"                 # researchable | pending_evidence
    viewpoint: dict[str, Any] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    research_answer_id: str = ""
    llm_task_run_id: str = ""
    template_id: str = ""
    review_status: str = "pending"                  # pending | accepted | rejected
    diligence_status: str = "generated"             # generated | unsupported | skipped | failed
    diligence_reason_code: str = ""
    created_at: Any = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_choice(self.partition, {"researchable", "pending_evidence"}, "partition")
        _validate_choice(self.review_status, {"pending", "accepted", "rejected"}, "review_status")


@dataclass(slots=True)
class DailyWatchlistEntry:
    entry_id: str
    security_id: str
    run_id: str = ""
    item_id: str = ""
    selection_reason: str = ""
    joined_at: Any = field(default_factory=utcnow)
    actor: str = "system"
```

### 3.2 存储接线（`app/store.py`）

按既有 `COLLECTIONS` 模式追加三条，无需迁移脚本（`records` 表按 collection 分区存放 payload）：

```python
("daily_mainline_runs", "run_id", DailyMainlineRun),
("daily_mainline_queue_items", "item_id", DailyMainlineQueueItem),
("daily_watchlist_entries", "entry_id", DailyWatchlistEntry),
```

设计决策（对应 requirements.md Open Questions 中已标记为"已决策"的清单存储项）：不复用 `observation_items`（`app/store.py:176`）承载清单。需求 1.13 要求同日多次运行各自保留清单、1.11 要求关注池条目回链 `run_id`，复用 `observation_items` 会丢失 run 维度并污染既有观察项语义。关注池的“公司进入本地库”仍走既有 `import_company_watchlist`，`daily_watchlist_entries` 只记录加入事件的来源与理由。

### 3.3 配置项（`AI_QUANT_*`，全部有默认值，缺省不改变既有行为）

| 环境变量 | 默认 | 用途 | 需求 |
| --- | --- | --- | --- |
| `AI_QUANT_DAILY_BRIEF_TIMEOUT_SECONDS` | 600 | 编排总预算，越界后续阶段 `skipped` | 1.12 |
| `AI_QUANT_DAILY_MAINLINE_CANDIDATE_LIMIT` | 20 | 候选池总条目上限 | 1.4 |
| `AI_QUANT_DAILY_MAINLINE_MARKET_QUOTA` | 10 | 单市场候选配额，避免单市场占满 | 1.4 |
| `AI_QUANT_DAILY_MAINLINE_DILIGENCE_LIMIT` | 4 | 单次运行最多尽调候选数（LLM 预算）；20 候选、600 秒实跑下为每次模型调用保留约 75 秒 | 4.5 |
| `AI_QUANT_DAILY_MAINLINE_ARTIFACT_DIR` | `artifacts/daily-mainline` | artifact 输出目录 | 6.1 |

## 4. 组件与接口

### 4.1 阶段状态机（`daily_mainline.py`）

```python
STAGES = ("scan_market_disturbance", "build_candidate_pool", "run_auto_diligence", "build_daily_queue")
STAGE_STATUSES = ("passed", "partial", "failed", "skipped")


@dataclass(slots=True)
class StageResult:
    stage: str
    status: str
    started_at: str
    finished_at: str
    record_count: int = 0
    reason_code: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    next_actions: list[dict[str, Any]] = field(default_factory=list)


def run_stages(
    *,
    stage_runners: Mapping[str, Callable[[Mapping[str, Any]], StageResult]],
    timeout_seconds: int,
    clock: Callable[[], float],
    now_iso: Callable[[], str],
) -> list[StageResult]:
    """按 STAGES 固定顺序执行；越界或失败后剩余阶段一律 skipped。"""


def derive_run_status(stages: Sequence[StageResult], *, queue_count: int) -> str:
    """failed 阶段 → failed；skipped/partial → partial；全 passed 且清单为空 → empty；否则 passed。"""


def build_progress(stages: Sequence[StageResult]) -> dict[str, Any]:
    """返回 {"current_stage", "completed_count", "total_count"}，供首屏运行中展示。"""


def build_next_actions(stages: Sequence[StageResult], *, status: str) -> list[dict[str, Any]]:
    """非 passed 状态必须返回 ≥1 条，每条含 action / reason_code / command 或 endpoint。"""
```

`derive_run_status` 与 `build_next_actions` 是纯函数，状态与下一步动作的一致性因此可以脱离 IO 单独验证（需求 1.9、1.10、2.7）。

### 4.2 扫市与候选池（`daily_mainline_scan.py`）

沿用 `scripts/daily_market_insight.py` 既有指标定义（`one_day_return`、`amount_ratio`、`volume_ratio`、`intraday_range`），不引入新数据源：

```python
TRIGGER_RULES = (
    ("one_day_return", 0.07, "涨跌幅异常"),
    ("amount_ratio", 3.0, "成交额显著放大"),
    ("volume_ratio", 3.0, "成交量显著放大"),
    ("intraday_range", 0.08, "日内振幅较高"),
)


def build_candidate_pool(
    rows: Iterable[Mapping[str, Any]],
    *,
    candidate_limit: int,
    market_quota: int,
) -> list[dict[str, Any]]:
    """输出按触发强度降序、rank 从 1 连续编号的候选，每条含：
    rank / selection_reason / trigger_metric / trigger_value / as_of_date /
    security_id / issuer_id / ticker / market。
    并列时以 (|one_day_return|, amount_ratio, volume_ratio, security_id) 稳定排序。
    """
```

排序键包含 `security_id` 兜底，保证同输入同输出，`rank` 唯一且连续（需求 1.4）。

### 4.3 自动尽调（`daily_mainline_diligence.py`）

```python
BUILTIN_TEMPLATES = (
    {"template_id": "tpl_daily_candidate_diligence", "task_type": "candidate_diligence",
     "prompt_name": "daily_candidate_diligence", "prompt_version": "daily-mainline-v1", ...},
    {"template_id": "tpl_daily_evidence_summary", "task_type": "evidence_summary", ...},
    {"template_id": "tpl_daily_risk_challenge", "task_type": "risk_challenge", ...},
)


def seed_specs(existing_template_ids: Iterable[str]) -> list[dict[str, Any]]:
    """只返回缺失模板的注册 payload，已存在则返回空列表（幂等）。"""


def build_viewpoint(
    *,
    candidate: Mapping[str, Any],
    llm_output_text: str,
    evidence_candidates: Sequence[Mapping[str, Any]],
    llm_task_run_id: str,
    template_id: str,
    prompt_version: str,
    model: str,
) -> dict[str, Any]:
    """组装观点：
    - evidence_ids 取自已存在的 evidence / research_report_citation_evidence 标识；
    - 无可绑定证据 → diligence_status="unsupported"、partition="pending_evidence"；
    - 来源含研报 → source_layer="viewpoint"，fact_field_writes 恒为空列表。
    """


FACT_FIELD_SOURCE_TYPES = ("official_disclosure", "market_data")
```

事实字段与观点层的分隔用两个显式字段承载：`source_layer` 与 `fact_field_writes`。研报派生的观点 `source_layer="viewpoint"` 且 `fact_field_writes == []`，因此不存在“研报补事实字段”的路径（需求 1.8）。

LLM 调用不新写通路，`SystemService.run_daily_mainline` 内部调用既有 `self.run_llm_task({...})`（`app/services.py:536`），因此 `llm_task_runs` 的 lineage 字段（`template_id` / `provider` / `model` / `prompt_version` / `latency_ms` / `estimated_*_tokens` / `estimated_cost`）与既有语义完全一致（需求 4.3、4.8）。

两条实测约束必须在实现与断言中体现：

- `run_llm_task` 无论上游成功还是走 `_llm_task_fallback`（`app/services.py:1179`）都写入一条 `LLMTaskRun`，`status` 取值为 `succeeded` / `fallback` / `needs_review` / `failed`。因此"成功调用次数"一律按 `status == "succeeded"` 统计，不得按记录总数统计。
- `LLMTaskRun` 没有 `model_version` 字段（`app/models.py:1031`），需求 4.3 的"模型版本"映射为 `model` + `prompt_version` 组合。

观点落库复用 `ResearchAnswer`（`app/models.py:1152`，已有 `prompt_version` / `model_version` / `human_review_status` 字段）：`ResearchAnswer.prompt_version ← LLMTaskRun.prompt_version`、`ResearchAnswer.model_version ← LLMTaskRun.model`、复核状态复用既有 `human_review_status`（默认 `pending`）（需求 4.4、4.6）。

### 4.4 facade（`app/services.py`，仅编排）

```python
def run_daily_mainline(self, payload: Mapping[str, Any] | None = None, *, actor: str = "system") -> dict[str, Any]:
    """跨模块编排：读行情 → 候选池 → seed 模板 → run_llm_task → 完整度口径 →
    写 DailyMainlineRun / DailyMainlineQueueItem → 写 artifact → 审计。
    不含判定逻辑，判定全部委派给 daily_mainline / daily_mainline_scan /
    daily_mainline_diligence / completeness_policy。"""

def daily_mainline_queue_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
def daily_mainline_runs_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
def add_daily_queue_item_to_watchlist(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]: ...
def review_daily_mainline_viewpoint(self, payload: Mapping[str, Any], *, actor: str = "system") -> dict[str, Any]: ...
```

`SystemService Growth Freeze` 定位：以上 5 个方法属于“跨模块编排”与“既有存储/审计接线”，不含业务判定；handoff 需按 AGENTS.md §8.1 记录该结论与对应回归。

### 4.5 API（只追加 5 条，既有路由一条不改）

| 方法 | 路径 | facade | 说明 |
| --- | --- | --- | --- |
| POST | `/api/daily-mainline/run` | `run_daily_mainline` | UI 触发入口；`as_of_date`、`timeout_seconds`、`diligence_limit` 可选 |
| GET/POST | `/api/daily-mainline/queue` | `daily_mainline_queue_payload` | 首屏当日清单读模型 |
| GET/POST | `/api/daily-mainline/runs` | `daily_mainline_runs_payload` | 运行历史与阶段记录 |
| POST | `/api/daily-mainline/queue/{item_id}/watchlist` | `add_daily_queue_item_to_watchlist` | 加入关注池 |
| POST | `/api/daily-mainline/viewpoints/{item_id}/review` | `review_daily_mainline_viewpoint` | 人工复核 pending/accepted/rejected |

路由只做追加，不改既有条目。需求 3.3 的护栏用黄金路由清单测试实现：先抓取变更前 `app/api_routes.py` 的全部 `(method, path)` 快照，再断言该快照为变更后路由表的**子集**，且这些路由的响应包装结构不变。断言口径不硬编码路由数量——实测变更前为 461 条 `(method, path)` / 334 条唯一路径，该数字随其他任务漂移，硬编码会造成假失败。

清单读模型固定结构：

```json
{
  "schema_id": "daily-mainline-queue-v1",
  "status": "passed",
  "run_id": "dmrun_...",
  "as_of_date": "2026-07-24",
  "generated_at": "2026-07-28T02:11:03+00:00",
  "progress": {"current_stage": "", "completed_count": 4, "total_count": 4},
  "stages": [{"stage": "...", "status": "passed", "started_at": "...", "finished_at": "...", "record_count": 12}],
  "items": [{"item_id": "...", "rank": 1, "selection_reason": "涨跌幅异常",
             "trigger_metric": "one_day_return", "trigger_value": 0.1007,
             "as_of_date": "2026-07-24", "completeness_status": "partial",
             "evidence_ref": {"evidence_ids": ["..."], "endpoint": "/api/evidence/..."},
             "watchlist_action": {"endpoint": "/api/daily-mainline/queue/{item_id}/watchlist", "method": "POST"},
             "review_status": "pending", "partition": "researchable"}],
  "pending_evidence_items": [],
  "next_actions": [],
  "paper_only": true,
  "live_execution_allowed": false,
  "usage_boundary": "daily_mainline_is_local_research_queue_paper_only_no_broker_execution"
}
```

### 4.6 CLI（`scripts/daily_mainline_run.py`）

```python
def main() -> None:
    args = _parse_args()
    service = SystemService()
    result = service.run_daily_mainline(
        {"as_of_date": args.as_of_date, "timeout_seconds": args.timeout_seconds,
         "diligence_limit": args.diligence_limit, "artifact_dir": args.artifact_dir},
        actor=args.actor,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if result.get("status") in {"passed", "empty"} else 1)
```

CLI 不含任何判定逻辑，与 HTTP handler 共用同一 facade（需求 1.1）。`make daily-mainline` 追加为便捷入口。

### 4.7 UI 设计（`app/static/index.html`）

首屏 dashboard 顶部新增“今天看什么”区块，位于既有 quick-start 之前：

```html
<section class="panel span-12" id="dailyMainlinePanel" aria-label="今日待研究清单">
  <div class="system-strip">
    <div class="system-box"><strong>数据日期</strong><span id="dailyMainlineAsOf">-</span></div>
    <div class="system-box"><strong>生成时间</strong><span id="dailyMainlineGeneratedAt">-</span></div>
    <div class="system-box"><strong>运行状态</strong><span id="dailyMainlineStatus">待载入</span></div>
    <div class="system-box"><strong>阶段进度</strong><span id="dailyMainlineProgress">0/4</span></div>
  </div>
  <button data-action="run-daily-mainline" class="primary">运行今日主线</button>
  <table><thead><tr><th>排名</th><th>标的</th><th>入选理由</th><th>完整度</th><th>证据</th><th>操作</th></tr></thead>
    <tbody id="dailyMainlineRows"></tbody></table>
  <div id="dailyMainlineEmpty" hidden>
    <p>今日暂无清单。点击“运行今日主线”，或执行：</p>
    <code>python3 scripts/daily_mainline_run.py --as-of-date YYYY-MM-DD</code>
  </div>
</section>
```

导航收敛只改呈现层：`personal` 组保留总览、公司情报、知识图谱、K 线行情、研究结论、模拟反馈与动态配置外链（与当前实现一致，新增仅为清单区块）；治理、签批、发布门禁、投委会入口留在 `maintenance` 组。既有 `setWorkspaceMode`（`app/static/index.html:8780`）已按 `data-workspace-target` 控制可见性，深链访问维护态视图时先切换 mode 再 `openTab`，保证视图可打开（需求 3.5）。

前端落点必须尊重 T-599 已建立的运行期模块化边界（`app/static/ui_modules/`，`manifest.json` 标注 `status=runtime-partial`、`runtime_modules=[dashboard, helpers]`、`scaffold_modules=[company, graph, market, admin]`）：

- 导航事件接线在 `ui_modules/helpers.mjs` 的 `installNavigation` 中，`scripts/ui_static_check.py` 断言导航选择器 **不得**回到 `index.html`。因此深链先切 mode 再 `openTab` 的行为改动落在 `ui_modules/helpers.mjs`（`helpers.mjs:57,71` 已注入 `setWorkspaceMode`），只有 `data-workspace-target` 按钮标记留在 `index.html`。
- 首屏渲染沿用既有 dashboard 模式：渲染函数写入 `ui_modules/dashboard.mjs`（由 `createDashboardRuntime` 导出），`index.html` 只保留薄封装调用。`ui_static_check.py` 目前仅对既有函数名清单强制该拆分，新增渲染函数内联到 `index.html` 不会硬失败，但会背离 T-599 方向并继续推高 12,650 行的单页体量，故设计选择直接写入 `dashboard.mjs`。
- 结构性 DOM（`#dailyMainlinePanel` 与空态卡片）仍写在 `index.html`，与既有 `manifest.preserve.dom_contract`（id / data-action 属性不变）一致。
- 附加门禁：改动 `ui_modules/*.mjs` 时需运行 `node scripts/ui_dashboard_module_check.mjs`（该脚本不在 `make local-ci` 中，需单独执行并记入 handoff）。

### 4.8 完整度口径统一（`completeness_policy.py`）

问题根因：现有 `completeness_verdict` 的 `status=complete` 只看分层可用性与加权分，`missing_fact_fields` 不参与判定，于是出现 `score=0.988` 且 27 项缺失同时为 `complete`。

```python
LAYER_COVERAGE_THRESHOLDS = {
    "profile_field_coverage_score": 0.9,
    "database_coverage_score": 0.9,
    "relationship_coverage_score": 0.9,
}


def resolve_status(
    *,
    profile_available: bool,
    blocking_gaps: Sequence[str],
    warning_gaps: Sequence[str],
    missing_fact_fields: Sequence[str],
    coverage_scores: Mapping[str, float],
) -> dict[str, Any]:
    """唯一判定入口，返回 {"status", "label", "is_complete", "missing_layers"}。
    status="complete" 当且仅当：profile_available ∧ 无 blocking/warning gaps
    ∧ missing_fact_fields 为空 ∧ 所有阈值项 coverage ≥ 阈值。
    其余非 not_found 情况一律 status="partial"，并给出 missing_layers。"""


def coverage_denominator(*, total_fields: int, filled_fields: int) -> dict[str, Any]:
    """返回 {"total_fields", "filled_fields", "score"}，score = filled/total（total=0 → 0.0）。"""


def next_actions(*, status: str, missing_layers: Sequence[str], missing_fact_fields: Sequence[str]) -> list[dict[str, Any]]:
    """非 complete 必返回 ≥1 条，每条含 target_field / source_type / command 或 endpoint。"""
```

`company_intelligence.completeness_verdict` 改为委派 `resolve_status`，`level` / `score` / `sections` 等既有字段保留不变，只让 `status`、`is_complete`、`missing_layers`、`next_actions` 走统一口径。当日清单条目的 `completeness_status` 直接取同一函数返回值，不本地重算（需求 5.3、5.8）。

`status` 与 `label` 的对应：`complete → 完整`、`partial → 部分完整`、`not_found → 未建档`。原有 `usable_with_gaps` / `incomplete` 归并入 `partial`，避免同一概念两套取值；`level`（complete/near_complete/partial/sparse）保留为评分档位，供既有 UI 展示。

### 4.9 行情新鲜度同源（`market_data.py` 扩展）

```python
MARKET_EOD_SOURCES = {"A": "public_eod_market_data", "U": "yahoo_chart_us_eod"}


def market_eod_key(market: str, *, data_type: str = "eod") -> dict[str, str]:
    """返回 {"market", "source_id", "data_type"}；market_freshness 与公司视图共用。"""


def freshness_lag(*, company_as_of_date: str, market_eod_date: str) -> dict[str, Any]:
    """返回 {"lag_days", "reason_code", "is_lagging"}。
    lag_days 为精确日历差；lag_days > 0 时 reason_code ∈
    {"security_not_in_latest_eod_batch", "security_suspended_or_delisted",
     "source_partial_coverage"}；lag_days == 0 时 reason_code=""。"""
```

公司情报视图取最新行情时必须经过 `market_eod_key`，从而与 `market_freshness` 使用同一 `(market, source_id, data_type)` 键（需求 5.6），修正 `2026-05-25` 与市场 EOD `2026-07-24` 并列展示且无解释的问题（需求 5.7）。

### 4.10 证据产物（`daily_mainline_artifact.py`）

```python
SENSITIVE_KEY_PATTERNS = ("api_key", "authorization", "token", "secret", "signature", "x-amz-", "raw_response")


def artifact_payload(*, run: Mapping[str, Any], items: Sequence[Mapping[str, Any]],
                     producer_command: str, environment: str) -> dict[str, Any]:
    return {
        "schema_id": "daily-mainline-run-artifact-v1",
        "run_id": run["run_id"],
        "generated_at": "<UTC ISO 8601>",
        "producer_command": producer_command,      # 例：python3 scripts/daily_mainline_run.py --as-of-date 2026-07-24
        "environment": environment,                # 例：local-compose
        "owner_group": "product_and_ui",
        "classification": "local-only",
        "contains_sensitive_data": False,
        "production_release_gate_eligible": False,
        "stages": [...],                            # 与 DailyMainlineRun.stages 等价
        "items": [...],                             # 观点仅保留摘要文本，不含完整上游响应
        "paper_only": True,
        "live_execution_allowed": False,
    }


def redact(payload: Any) -> Any:
    """递归剔除命中 SENSITIVE_KEY_PATTERNS 的键，并截断超长文本。"""
```

文件名：`artifacts/daily-mainline/daily-mainline-{run_date}-{run_id}.json`。同日多次运行因 `run_id` 不同而互不覆盖（需求 6.4）。

## 5. 错误处理

| 原因码 | 触发阶段 | 处理 | 整体状态 |
| --- | --- | --- | --- |
| `market_data_unavailable` | scan | 阶段 failed，后续 skipped | failed |
| `market_data_stale` | scan | 阶段 partial，继续执行并在清单标注滞后 | partial |
| `no_candidates` | build_candidate_pool | 阶段 passed(record_count=0)，尽调与清单 skipped | empty |
| `llm_gateway_unconfigured` | run_auto_diligence | 阶段 partial，清单仍生成但无观点 | partial |
| `llm_call_failed` / `llm_timeout` | run_auto_diligence | 单候选跳过观点，候选保留并带原因码 | partial |
| `diligence_budget_exhausted` | run_auto_diligence | 超出 `diligence_limit` 的候选 `diligence_status="skipped"` | partial |
| `evidence_missing` | run_auto_diligence | 观点标记 unsupported，进 `pending_evidence` 分区 | passed |
| `timeout_budget_exceeded` | 任意 | 后续阶段全部 skipped，已完成结果保留 | partial |
| `completeness_unavailable` | build_daily_queue | 条目 `completeness_status="unknown"` 并给出补库动作 | partial |
| `store_write_failed` | build_daily_queue | 阶段 failed，artifact 仍写出用于诊断 | failed |

原则：单候选级失败不升级为阶段失败；阶段级失败不清空已完成阶段结果；任何非 `passed` 状态都必须携带至少一条可执行 `next_actions`（含 `command` 或 `endpoint`）。

## 6. Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 阶段序列、阶段记录与进度投影一致

*For any* 行情数据规模、候选数量与失败注入组合，编排输出的阶段序列必须严格等于 `STAGES` 的前缀且顺序一致；每条阶段记录都含 `stage`、`status`、`started_at`、`finished_at`、`record_count`，`status` 落在 `{passed, partial, failed, skipped}`，`finished_at ≥ started_at`，`record_count ≥ 0`；进度投影的 `current_stage` 等于首个未完成阶段、`completed_count` 等于已完成阶段数。

**Validates: Requirements 1.2, 1.3, 2.6**

### Property 2: 候选池条目契约与排名连续性

*For any* 扫市派生指标集合，候选池中每个条目都含 `rank`、`selection_reason`、`trigger_metric`、`trigger_value`、`as_of_date`；`rank` 为 1..n 连续且互不重复；按 `rank` 升序读取时触发强度非递增。

**Validates: Requirements 1.4**

### Property 3: 观点证据绑定或进入待补分区

*For any* 候选集合与任意证据可用性分布，每条生成观点要么关联至少一个在存储中真实存在的证据标识，要么被标记 `unsupported` 且出现在 `pending_evidence` 分区、不出现在主清单分区。

**Validates: Requirements 1.6, 1.7**

### Property 4: 研报只进观点层，不进事实字段

*For any* 混合来源（研报、官方披露、行情）的尽调输入，来源含研报的观点其 `source_layer` 恒为 `viewpoint` 且 `fact_field_writes` 为空；所有事实字段写入的来源类型集合都是 `{official_disclosure, market_data}` 的子集。

**Validates: Requirements 1.8**

### Property 5: LLM lineage 与成功调用计数一致

*For any* 候选集合与任意 LLM 成功/失败模式，本次运行新增的 `llm_task_runs` 记录中 `status == "succeeded"` 的条数等于网关成功调用次数（fallback / needs_review / failed 记录不计入成功计数）；每条记录都含 `template_id`、`model`、`prompt_version`、`latency_ms` 与 `estimated_input_tokens` / `estimated_output_tokens`；每条生成观点都携带对应的 `llm_task_run_id` 与模板标识。

**Validates: Requirements 1.5, 4.3, 4.8**

### Property 6: 状态与可执行下一步一致

*For any* 失败阶段位置或零候选场景，整体 `status` 为 `failed`、`partial` 或 `empty` 中与实际结果对应的取值；失败阶段记录带 `reason_code`；失败之前阶段的结果仍完整保留；`next_actions` 至少一条且每条含 `command` 或 `endpoint`。

**Validates: Requirements 1.9, 1.10, 2.7**

### Property 7: 超时截断保留已完成结果

*For any* 时间预算与任意阶段耗时序列，首次累计耗时越界之后的所有阶段 `status` 均为 `skipped`，整体 `status` 为 `partial`，且越界之前完成的阶段结果与记录数保持不变。

**Validates: Requirements 1.12**

### Property 8: 同日多次运行互不覆盖

*For any* 同一日期上的 N 次（N ≥ 2）编排运行，所有 `run_id` 互不相同，N 份清单均可按 `run_id` 读回，N 份 artifact 文件名互不相同且全部存在于磁盘。

**Validates: Requirements 1.13, 6.4**

### Property 9: 加入关注池往返保真

*For any* 清单条目，执行加入关注池后从存储读回的记录中 `security_id`、加入时间、来源 `run_id` 与入选理由都与来源条目一致。

**Validates: Requirements 1.11**

### Property 10: 清单读模型呈现契约

*For any* 当日清单，payload 顶层都含 `as_of_date` 与 `generated_at`；每个条目都含 `rank`、`selection_reason`、`evidence_ref` 与 `watchlist_action`（含 `endpoint` 与 `method`）。

**Validates: Requirements 2.4, 2.8**

### Property 11: 内置模板幂等写入

*For any* 初始已存在模板子集，连续执行 N 次（N ≥ 2）内置模板写入后，模板集合、模板标识与 prompt 版本标识都与执行一次的结果相同。

**Validates: Requirements 4.2**

### Property 12: 研究结论与复核状态往返

*For any* 生成观点，按 `answer_id` 读回的 `research_answers` 记录都保留候选标识与证据标识关联；复核状态默认 `pending`，任意 `{pending, accepted, rejected}` 内的转移写入后可读回同值，枚举外取值被拒绝。

**Validates: Requirements 4.4, 4.6**

### Property 13: LLM 失败保留候选并记录原因

*For any* 调用失败候选子集，这些候选仍留在候选池中、带非空失败原因码、且不产生对应观点；其余候选的观点生成不受影响。

**Validates: Requirements 4.5**

### Property 14: 凭据与完整上游响应不落盘

*For any* 含密钥、签名 URL 与超长上游响应体的运行输入，本轮新增的持久化对象（内置模板记录、`daily_mainline_queue_items` 条目、`daily_watchlist_entries` 条目）与写出的 artifact 内容中都不出现密钥值、签名 URL 或完整上游响应体；模板记录的 prompt 版本标识非空。断言范围不含既有 `LLMTaskRun.output`——该字段本就持久化上游响应，属既有行为，本设计不改其语义（该边界写入 handoff）。

**Validates: Requirements 4.7, 6.5**

### Property 15: 完整度判定等价规则

*For any* `missing_fact_fields` 与分层覆盖度取值组合，完整度状态为 `complete` 当且仅当 `missing_fact_fields` 为空且所有受阈值约束的覆盖度分值都达到阈值；其余非 `not_found` 情况状态为 `partial` 且 `missing_layers` 恰为缺失分层集合。

**Validates: Requirements 5.1, 5.2**

### Property 16: 跨响应完整度状态一致

*For any* 公司数据状态，公司情报响应与当日清单条目给出的完整度状态取值相同，且清单条目的状态来源于完整度口径服务的返回值而非本地重算。

**Validates: Requirements 5.3, 5.8**

### Property 17: 非完整状态必有可执行下一步

*For any* 非 `complete` 的完整度判定结果，`next_actions` 至少一条，且每条都含目标字段、来源类型与可执行的命令或 API 路径。

**Validates: Requirements 5.4**

### Property 18: 覆盖度分母自述与算术一致

*For any* 字段填充状态，每个覆盖度分值输出都声明统计字段总数与已填字段数，且分值等于已填数除以总数（总数为 0 时分值为 0）。

**Validates: Requirements 5.5**

### Property 19: 行情新鲜度同源与滞后标注

*For any* 市场与公司组合，公司情报视图引用的行情取数键与 `market_freshness` 对该市场的 `(market, source_id, data_type)` 相同；公司最新行情日期早于市场 EOD 时 `lag_days` 等于精确日历差且原因码非空，两者相同时不标注滞后。

**Validates: Requirements 5.6, 5.7**

### Property 20: 证据产物契约

*For any* 编排运行结果，写出的 artifact 读回后都含 `run_id` 与全部阶段结果，并含 producer 命令、可解析为 UTC ISO 8601 的生成时间戳、环境标识、owner group 与敏感数据标记；`classification` 恒为 `local-only`，`production_release_gate_eligible` 恒为 `false`。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 21: 边界声明不变量

*For any* 编排运行输出，`live_execution_allowed` 恒为 `false`，且所有持仓与交易相关节点都带 paper-only 标记。

**Validates: Requirements 7.1, 7.2**

## 7. 测试策略

### 7.1 属性测试实现方式

仓库无 `hypothesis` 依赖（`pyproject.toml` 运行期依赖仅 `PyYAML`），且本任务不扩大依赖面。属性测试以 stdlib `unittest` + 固定种子生成器实现，放在 `tests/test_daily_mainline_properties.py`：

```python
PROPERTY_ITERATIONS = 100


class DailyMainlinePropertyTest(SystemServiceTestBase):
    def test_property_1_stage_sequence_and_progress(self) -> None:
        """Feature: project-usability-improvement, Property 1: 阶段序列、阶段记录与进度投影一致"""
        for iteration in range(PROPERTY_ITERATIONS):
            rng = random.Random(1000 + iteration)
            scenario = _random_scenario(rng)          # 行情规模 / 候选数 / 失败注入 / 耗时序列
            with self.subTest(seed=1000 + iteration, scenario=scenario):
                result = _run_with_scenario(self.service, scenario)
                self.assertEqual([s["stage"] for s in result["stages"]], list(STAGES)[: len(result["stages"])])
                ...
```

约定：

- 每条属性至少 100 次迭代，种子固定以保证可复现。
- `subTest` 携带种子与场景摘要，失败时直接给出反例（等价于 PBT 库的 falsifying example）。
- 生成器覆盖边界：零候选、单候选、并列指标、全失败、首阶段即超时、非 ASCII 标的名、超长文本。
- 每个测试方法 docstring 使用 `Feature: {feature_name}, Property {number}: {property_text}` 标签格式，便于与本文档对照。

LLM 调用一律用注入的假网关（可控成功/失败/超时），不产生真实外部请求，属性测试成本可控。

### 7.2 单元与示例测试

| 检查 | 覆盖需求 | 位置 |
| --- | --- | --- |
| CLI 与 HTTP 入口命中同一 facade（打桩计数） | 1.1 | `tests/test_daily_mainline.py` |
| 内置模板集 task_type 集合等于三类 | 4.1 | `tests/test_daily_mainline.py` |
| 黄金路由清单：变更前 `(method, path)` 快照 ⊆ 变更后路由表（不硬编码数量） | 3.3, 3.4 | `tests/test_system.py` 新增用例 |
| 维护态视图深链逐一可打开（枚举全部 tab id） | 3.5 | `scripts/ui_interaction_acceptance.py` |
| 首屏清单区块、触发按钮、空态命令文本存在 | 2.1, 2.2, 2.5 | `scripts/ui_static_check.py` |
| 失败态渲染阶段名与 reason_code | 2.7 | `scripts/ui_interaction_acceptance.py` |
| 编排只经注入接口访问外部 | 7.3 | `tests/test_daily_mainline.py` + `scripts/security_check.py .` |

### 7.3 集成与门禁

- 首屏清单 p95 < 2 秒（需求 2.3）：本机 Compose 栈上用既有延迟采样方式对 `/api/daily-mainline/queue` 采样，结果写入 `local-only` artifact；不做属性测试。采样入口范围已收窄并获用户批准（2026-07-28）：只在本机 `scripts/daily_data_update_pipeline.py` 的 `_latency_audit` 探针列表追加 `daily_mainline_queue`，**不改** `scripts/staging_acceptance.py`（该脚本属治理/平台组，且贴近“不产出非本机发布证据”边界）。
- 门禁（需求 3.6, 6.6, 7.4-7.10）：`make local-ci`（`py_compile`、`unittest discover -s tests`、`ui_static_check`、`security_check`、`check_markdown_links`、`check_handoffs`、`check_doc_metadata`），`docs/agent-handoffs/` 变更时单独跑 `python3 scripts/check_handoffs.py`；记录变更前后 unittest 用例总数。
- 附加门禁（不在 `make local-ci` 内，改动 `app/static/ui_modules/*.mjs` 时必跑）：`node scripts/ui_dashboard_module_check.mjs`。

## 8. 设计决策记录（对应需求 Open Questions）

| 问题 | 决策 | 理由 |
| --- | --- | --- |
| 候选池上限与入选阈值 | 总上限 20，单市场配额 10；阈值沿用现有异动规则（涨跌幅 7%、量额倍率 3、振幅 8%） | 保持与 `daily_market_insight` 口径一致；单市场配额避免 A 股行数优势占满清单 |
| 自动尽调范围与 LLM 预算 | 默认对前 4 个候选尽调，优先已建档且有可绑定证据的候选；20 个候选仍全部进入清单，超出预算的候选记 `diligence_budget_exhausted` | 2026-07-30 真实 20 候选运行证明旧值 8 会把单次模型预算压到约 36-46 秒并全部超时；修订后兼顾清单广度与模型有效响应 |
| 清单是否独立持久化 | 独立 `daily_mainline_queue_items` + `daily_mainline_runs`，不复用 `observation_items` / `research/tasks` | 需求 1.13 的同日多份清单与 1.11 的 `run_id` 回链需要 run 维度；复用会污染既有观察项语义 |
| 后台维护模式角色默认值 | 不变，沿用现有单一角色选择器 | 需求未要求角色语义变更，避免越出 UI 呈现层范围 |

## 9. 风险

- 完整度状态取值归并（`usable_with_gaps` / `incomplete` → `partial`）会改变 `/api/company-intelligence/{symbol}` 的 `status` 字符串，属于响应取值域收敛，且为**破坏性取值域变更**。状态：**已获用户批准（2026-07-28）**，不再是实施前置阻塞项。既有 UI 通过 `verdict.label` 与 `statusLabel()` 展示（`statusLabel` 亦以依赖注入方式传入 `ui_modules/dashboard.mjs`），实施时仍须同步核对 UI、`ui_modules/*.mjs` 与依赖该字段的脚本、`tests/` 既有断言与 `docs/` 中记录取值的段落（依赖面适配由任务 7.3 承担），并在 handoff 中记为响应取值域契约变更。
- 新增 3 个 store collection 会增加 `records` 表的 collection 数量。实测结论：`scripts/migrate_sqlite_to_postgres.py` 已按 `app.store.COLLECTIONS` 派生（无需改动）；`/api/analysis/latest` 的 `counts` 是显式硬编码字典（`app/services.py:30215` 起），需以**加法**方式补三个键，不得改为按 `COLLECTIONS` 全量派生（会把全部 collection 灌入既有仪表盘契约）。状态：**加法口径已获用户确认（2026-07-28）**——`counts` 只显式追加 `daily_mainline_runs` / `daily_mainline_queue_items` / `daily_watchlist_entries`，既有键一个不改、不做全量派生；落成验证见任务 9.4。若确需改动备份脚本，属跨组（平台与质量）改动，须在 handoff 标注并请对应评审组确认。
- `run_llm_task` 要求模板 `status="approved"`（`app/services.py:540`，否则抛 `ComplianceGateError`），内置模板需在 seed 时明确置为 `approved` 或由编排传 `allow_unapproved`；设计选择 seed 即 `approved` 并记录 prompt 版本，避免编排绕过审批门。
- `run_llm_task` 在 fallback 路径同样写入 `LLMTaskRun`（`status ∈ {fallback, needs_review, failed}`），若成功计数按记录总数统计会虚增 AI 运行量；Property 5 已按 `status == "succeeded"` 约束。
- `app/static/ui_modules/` 并非空目录（T-599 运行期模块化已落地 `dashboard.mjs` / `helpers.mjs` 与 4 个 scaffold 模块），UI 改动需按 §4.7 的落点分工执行，否则会与 `scripts/ui_static_check.py` 的模块抽取断言冲突。
