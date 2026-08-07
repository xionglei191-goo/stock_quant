"""每日主线编排的阶段状态机（纯函数领域模块）。

设计参考 `.kiro/specs/project-usability-improvement/design.md` §4.1：

- 阶段顺序恒为 `STAGES`，与数据状态无关（需求 1.2）。
- 每个阶段输出 `stage` / `status` / `started_at` / `finished_at` / `record_count`（需求 1.3）。
- 任一阶段 `failed` 或累计耗时越界后，剩余阶段一律 `skipped`，已完成阶段结果不清空
  （需求 1.9、1.12）。
- 时间来源以 `clock` / `now_iso` 参数注入，模块内不读系统时间，便于测试可控（需求 7.4）。
- 整体状态（`derive_run_status`）、进度投影（`build_progress`）与下一步动作（`build_next_actions`）
  均为纯函数，状态与可执行下一步的一致性可脱离 IO 验证（需求 1.9、1.10、2.6、2.7）。
- 下一步动作的原因码取值域见 `REASON_CODES`：design §5 错误处理表的阶段级原因码，加上本模块
  编排器自身产生的 4 个原因码（`ORCHESTRATOR_REASON_CODES`）。
- 配置项解析（`resolve_config`，design §3.3）同样集中在本模块：facade 只消费返回值，
  配置解析不散落进 `app/services.py`（需求 1.4、1.12、4.5、6.1）。取值解析复用既有
  `app.utils.env_int` / `env_text`，环境映射由调用方以 `env` 注入，模块内不读 `os.environ`。

本模块不做 IO，也不感知 store / LLM gateway：阶段实现由调用方（facade）以
`stage_runners` 注入，阶段之间只通过 `StageResult.payload` 传递数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..utils import env_int, env_text
from .daily_mainline_artifact import ARTIFACT_DIR

STAGES: tuple[str, ...] = (
    "scan_market_disturbance",
    "build_candidate_pool",
    "run_auto_diligence",
    "build_daily_queue",
)

STAGE_STATUSES: tuple[str, ...] = ("passed", "partial", "failed", "skipped")

# 编排器自身产生的原因码（阶段内部原因码由各阶段 runner 返回，取值见 design §5）。
SKIP_REASON_UPSTREAM_FAILED = "upstream_stage_failed"
SKIP_REASON_TIMEOUT = "timeout_budget_exceeded"
SKIP_REASON_RUNNER_UNAVAILABLE = "stage_runner_unavailable"
FAILURE_REASON_RUNNER_ERROR = "stage_runner_error"
FAILURE_REASON_RESULT_INVALID = "stage_result_invalid"

_MAX_ERROR_CHARS = 500
QUEUE_STAGE_RESERVE_FRACTION = 0.10
QUEUE_STAGE_RESERVE_MAX_SECONDS = 30.0
MIN_LLM_CALL_TIMEOUT_SECONDS = 1
DILIGENCE_NON_LLM_RESERVE_SECONDS = 12.0


@dataclass(slots=True)
class StageResult:
    """单个阶段的结构化记录（design §4.1）。"""

    stage: str
    status: str
    started_at: str
    finished_at: str
    record_count: int = 0
    reason_code: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    next_actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """阶段记录的序列化形式，供 `DailyMainlineRun.stages` 与 artifact 复用。"""

        return {
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "record_count": self.record_count,
            "reason_code": self.reason_code,
            "next_actions": [dict(action) for action in self.next_actions],
        }


def stage_records(stages: Sequence[StageResult]) -> list[dict[str, Any]]:
    """把阶段序列投影为可持久化的字典列表（不含 `payload`，避免中间数据落盘）。"""

    return [stage.to_dict() for stage in stages]


def _coerce_record_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _truncate(text: str) -> str:
    if len(text) <= _MAX_ERROR_CHARS:
        return text
    return text[:_MAX_ERROR_CHARS] + "..."


def _skipped(stage: str, *, reason_code: str, timestamp: str) -> StageResult:
    return StageResult(
        stage=stage,
        status="skipped",
        started_at=timestamp,
        finished_at=timestamp,
        record_count=0,
        reason_code=reason_code,
    )


def _normalize(
    result: Any,
    *,
    stage: str,
    started_at: str,
    finished_at: str,
) -> StageResult:
    """把 runner 返回值规整为契约内的 `StageResult`。

    - `stage` 恒取编排器的固定阶段名，runner 无法改写阶段顺序；
    - `started_at` / `finished_at` 恒取注入时钟的观测值，保证 `finished_at >= started_at`；
    - `status` 越出 `STAGE_STATUSES` 时按 `failed` 处理并记原因码；
    - `record_count` 负值归零。
    """

    if not isinstance(result, StageResult):
        return StageResult(
            stage=stage,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            record_count=0,
            reason_code=FAILURE_REASON_RESULT_INVALID,
            payload={"result_type": type(result).__name__},
        )

    status = result.status if result.status in STAGE_STATUSES else "failed"
    reason_code = result.reason_code or ""
    if status != result.status and not reason_code:
        reason_code = FAILURE_REASON_RESULT_INVALID
    payload = dict(result.payload) if isinstance(result.payload, Mapping) else {}
    next_actions = [
        dict(action) for action in (result.next_actions or []) if isinstance(action, Mapping)
    ]
    return StageResult(
        stage=stage,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        record_count=_coerce_record_count(result.record_count),
        reason_code=reason_code,
        payload=payload,
        next_actions=next_actions,
    )


def _budget_exceeded(elapsed: float, timeout_seconds: Any) -> bool:
    try:
        budget = float(timeout_seconds)
    except (TypeError, ValueError):
        return False
    return elapsed > budget


def queue_stage_reserve_seconds(timeout_seconds: Any) -> float:
    """Reserve a bounded portion of the total budget for queue persistence."""

    try:
        budget = max(0.0, float(timeout_seconds))
    except (TypeError, ValueError):
        return 0.0
    if budget <= 0.0:
        return 0.0
    return min(
        QUEUE_STAGE_RESERVE_MAX_SECONDS,
        max(float(MIN_LLM_CALL_TIMEOUT_SECONDS), budget * QUEUE_STAGE_RESERVE_FRACTION),
    )


def diligence_call_timeout_seconds(
    *,
    remaining_seconds: Any,
    remaining_candidates: Any,
    remaining_contexts: Any | None = None,
    gateway_timeout_seconds: Any,
    total_timeout_seconds: Any,
) -> int:
    """Allocate one bounded LLM timeout without consuming context or queue reserves.

    ``remaining_candidates`` counts LLM calls that may still run, while
    ``remaining_contexts`` counts all candidate-context reads still required to
    preserve the final queue. They differ when ``diligence_limit`` is smaller
    than the candidate pool.
    """

    try:
        remaining = max(0.0, float(remaining_seconds))
        pending = max(1, int(remaining_candidates))
        pending_contexts = (
            pending
            if remaining_contexts is None
            else max(0, int(remaining_contexts))
        )
        gateway_timeout = max(MIN_LLM_CALL_TIMEOUT_SECONDS, int(gateway_timeout_seconds))
    except (TypeError, ValueError):
        return 0
    available = (
        remaining
        - queue_stage_reserve_seconds(total_timeout_seconds)
        - pending_contexts * DILIGENCE_NON_LLM_RESERVE_SECONDS
    )
    if available < MIN_LLM_CALL_TIMEOUT_SECONDS:
        return 0
    fair_window = available / pending
    if fair_window < MIN_LLM_CALL_TIMEOUT_SECONDS:
        return 0
    fair_share = max(MIN_LLM_CALL_TIMEOUT_SECONDS, int(fair_window))
    return min(gateway_timeout, fair_share)


def run_stages(
    *,
    stage_runners: Mapping[str, Callable[[Mapping[str, Any]], StageResult]],
    timeout_seconds: int,
    clock: Callable[[], float],
    now_iso: Callable[[], str],
) -> list[StageResult]:
    """按 `STAGES` 固定顺序执行；越界或失败后剩余阶段一律 `skipped`。

    参数：
        stage_runners: 阶段名 → 阶段实现。实现接收上一阶段的 `StageResult.payload`
            （首个阶段收到空 Mapping），返回 `StageResult`。缺失或不可调用的阶段实现
            记为 `skipped` + `stage_runner_unavailable`，不中断其余阶段。
        timeout_seconds: 编排总预算（秒）。累计耗时严格超过该值后，剩余阶段全部
            `skipped` + `timeout_budget_exceeded`，已完成阶段结果保持不变。
        clock: 单调计时源，返回秒。仅用于计算累计耗时。
        now_iso: 时间戳字符串来源，用于阶段 `started_at` / `finished_at`。

    返回：
        与 `STAGES` 等长、顺序一致的阶段记录列表（含被 `skipped` 的阶段）。
    """

    started_clock = float(clock())
    results: list[StageResult] = []
    context: Mapping[str, Any] = {}
    cascade_reason = ""

    for stage in STAGES:
        if cascade_reason:
            results.append(_skipped(stage, reason_code=cascade_reason, timestamp=now_iso()))
            continue

        if _budget_exceeded(float(clock()) - started_clock, timeout_seconds):
            cascade_reason = SKIP_REASON_TIMEOUT
            results.append(_skipped(stage, reason_code=cascade_reason, timestamp=now_iso()))
            continue

        runner = stage_runners.get(stage)
        if not callable(runner):
            results.append(
                _skipped(stage, reason_code=SKIP_REASON_RUNNER_UNAVAILABLE, timestamp=now_iso())
            )
            context = {}
            continue

        started_at = now_iso()
        try:
            raw_result: Any = runner(context)
        except Exception as exc:  # noqa: BLE001 - 阶段级失败不得中断编排
            finished_at = now_iso()
            results.append(
                StageResult(
                    stage=stage,
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    record_count=0,
                    reason_code=FAILURE_REASON_RUNNER_ERROR,
                    payload={
                        "error_type": type(exc).__name__,
                        "error_message": _truncate(str(exc)),
                    },
                )
            )
            cascade_reason = SKIP_REASON_UPSTREAM_FAILED
            continue

        finished_at = now_iso()
        result = _normalize(raw_result, stage=stage, started_at=started_at, finished_at=finished_at)
        results.append(result)

        if result.status == "failed":
            cascade_reason = SKIP_REASON_UPSTREAM_FAILED
            continue

        context = result.payload

        if _budget_exceeded(float(clock()) - started_clock, timeout_seconds):
            cascade_reason = SKIP_REASON_TIMEOUT

    return results


RUN_STATUSES: tuple[str, ...] = ("passed", "partial", "failed", "empty")

# 阶段视角的“已完成”＝产出了结果的阶段；failed / skipped 不计入已完成（需求 2.6）。
PROGRESS_COMPLETED_STATUSES: tuple[str, ...] = ("passed", "partial")

# design §5 错误处理表的阶段级原因码（`timeout_budget_exceeded` 同时由编排器产生）。
STAGE_REASON_CODES: tuple[str, ...] = (
    "market_data_unavailable",
    "market_data_stale",
    "no_candidates",
    "llm_gateway_unconfigured",
    "llm_call_failed",
    "llm_timeout",
    "diligence_budget_exhausted",
    "evidence_missing",
    "timeout_budget_exceeded",
    "completeness_unavailable",
    "store_write_failed",
)

# 编排器自身产生的原因码（见本模块常量定义），design §5 表未列出但必须有下一步动作。
ORCHESTRATOR_REASON_CODES: tuple[str, ...] = (
    SKIP_REASON_UPSTREAM_FAILED,
    SKIP_REASON_RUNNER_UNAVAILABLE,
    FAILURE_REASON_RUNNER_ERROR,
    FAILURE_REASON_RESULT_INVALID,
)

REASON_CODES: tuple[str, ...] = STAGE_REASON_CODES + ORCHESTRATOR_REASON_CODES

# `no_candidates` 导致的 skipped 属“清单为空”而非异常中断：design §5 规定该场景整体状态
# 为 `empty`，因此这类 skipped 不触发 partial。
EMPTY_SKIP_REASON_CODES: frozenset[str] = frozenset({"no_candidates"})

DAILY_MAINLINE_CLI_COMMAND = "python3 scripts/daily_mainline_run.py --as-of-date YYYY-MM-DD"
DAILY_MAINLINE_RUN_ENDPOINT = "/api/daily-mainline/run"
DAILY_MAINLINE_RUNS_ENDPOINT = "/api/daily-mainline/runs"

# 原因码 → 下一步动作模板。每条都含 `command` 与 `endpoint` 两个键且至少一个非空
# （需求 1.9、1.10、2.7）。命令与路径均为项目内既有入口，不引入外部依赖。
_REASON_ACTIONS: dict[str, dict[str, str]] = {
    "market_data_unavailable": {
        "action": "backfill_market_data",
        "label": "回补本机行情数据后重跑主线",
        "command": "python3 scripts/backfill_market_data.py --market both",
        "endpoint": "/api/market-data/backfill",
        "reason": "扫市阶段读不到行情数据，需先回补行情再重跑主线",
    },
    "market_data_stale": {
        "action": "refresh_stale_market_data",
        "label": "刷新滞后市场的 EOD 数据",
        "command": "python3 scripts/backfill_market_data.py --market A --refresh-existing",
        "endpoint": "/api/market-data/backfill/coverage-report",
        "reason": "行情日期落后于市场 EOD，清单已标注滞后，建议刷新后复核",
    },
    "no_candidates": {
        "action": "rerun_daily_mainline_for_trading_day",
        "label": "换一个交易日重跑今日主线",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUN_ENDPOINT,
        "reason": "当日清单为空（无候选或候选未进入清单），可换交易日重跑或复核触发阈值",
    },
    "llm_gateway_unconfigured": {
        "action": "configure_llm_gateway",
        "label": "配置 LLM 网关后重跑自动尽调",
        "command": "",
        "endpoint": "/api/llm/readiness-report",
        "reason": "LLM 网关未配置，清单已生成但无观点；配置 AI_QUANT_LLM_* 凭据后重跑（凭据值不写入响应）",
    },
    "llm_call_failed": {
        "action": "retry_auto_diligence",
        "label": "重跑自动尽调补齐观点",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUN_ENDPOINT,
        "reason": "部分候选的 LLM 调用失败，候选已保留，可重跑补齐观点",
    },
    "llm_timeout": {
        "action": "retry_auto_diligence_with_longer_llm_timeout",
        "label": "放宽 LLM 超时后重跑自动尽调",
        "command": f"AI_QUANT_LLM_TIMEOUT_SECONDS=180 {DAILY_MAINLINE_CLI_COMMAND}",
        "endpoint": DAILY_MAINLINE_RUN_ENDPOINT,
        "reason": "部分候选的 LLM 调用超时，候选已保留，可放宽超时后重跑",
    },
    "diligence_budget_exhausted": {
        "action": "raise_diligence_limit",
        "label": "提高单次尽调候选上限后重跑",
        "command": "python3 scripts/daily_mainline_run.py --diligence-limit 16",
        "endpoint": DAILY_MAINLINE_RUN_ENDPOINT,
        "reason": "超出 diligence_limit 的候选未做尽调，可提高上限或分批重跑",
    },
    "evidence_missing": {
        "action": "backfill_candidate_evidence",
        "label": "为待补证据分区的观点补齐证据",
        "command": "python3 scripts/backfill_document_evidence.py",
        "endpoint": "/api/evidence/extract",
        "reason": "观点缺少可绑定证据，已置于待补证据分区，需补齐证据后复核",
    },
    "timeout_budget_exceeded": {
        "action": "raise_daily_brief_timeout",
        "label": "提高运行时间预算后重跑主线",
        "command": "python3 scripts/daily_mainline_run.py --timeout-seconds 1200",
        "endpoint": DAILY_MAINLINE_RUN_ENDPOINT,
        "reason": "累计运行时间超过预算，剩余阶段被跳过，已完成阶段结果已保留",
    },
    "completeness_unavailable": {
        "action": "backfill_company_completeness",
        "label": "补齐公司库字段以恢复完整度口径",
        "command": "python3 scripts/build_company_database_minimum.py",
        "endpoint": "/api/company-database/profile-fields/extract",
        "reason": "完整度口径不可用，条目完整度记为 unknown，需补齐公司库字段",
    },
    "store_write_failed": {
        "action": "check_store_health",
        "label": "检查存储健康后重跑主线",
        "command": "python3 scripts/smoke_test.py http://127.0.0.1:8000",
        "endpoint": "/api/health",
        "reason": "清单写入存储失败，artifact 已写出用于诊断，需先确认存储可写",
    },
    SKIP_REASON_UPSTREAM_FAILED: {
        "action": "resolve_upstream_stage_failure",
        "label": "先修复上游失败阶段再重跑主线",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUNS_ENDPOINT,
        "reason": "该阶段因上游阶段失败被跳过，需按上游失败原因码处置后重跑",
    },
    SKIP_REASON_RUNNER_UNAVAILABLE: {
        "action": "register_missing_stage_runner",
        "label": "补齐缺失的阶段实现接线后重跑",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUNS_ENDPOINT,
        "reason": "编排未注入该阶段实现（stage_runners 缺项），需补齐 facade 接线后重跑",
    },
    FAILURE_REASON_RUNNER_ERROR: {
        "action": "inspect_stage_runner_error",
        "label": "查看阶段异常详情后重跑主线",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUNS_ENDPOINT,
        "reason": "阶段实现抛出异常，运行记录中保留了异常类型与截断后的消息",
    },
    FAILURE_REASON_RESULT_INVALID: {
        "action": "fix_stage_result_contract",
        "label": "修正阶段返回值契约后重跑主线",
        "command": DAILY_MAINLINE_CLI_COMMAND,
        "endpoint": DAILY_MAINLINE_RUNS_ENDPOINT,
        "reason": "阶段返回值不符合 StageResult 契约（类型或 status 越界），已按 failed 记录",
    },
}

# 无法归因到具体原因码时的兜底动作，保证非 passed 状态至少有一条可执行下一步。
_FALLBACK_ACTION: dict[str, str] = {
    "action": "inspect_daily_mainline_run",
    "label": "查看本次运行的阶段记录后重跑主线",
    "command": DAILY_MAINLINE_CLI_COMMAND,
    "endpoint": DAILY_MAINLINE_RUNS_ENDPOINT,
    "reason": "运行未全部通过但缺少可识别原因码，需先查看阶段记录定位问题",
}

_ACTION_KEYS = ("action", "label", "stage", "reason_code", "command", "endpoint", "reason")


def _stage_status_map(stages: Sequence[StageResult]) -> dict[str, StageResult]:
    """按阶段名取首条记录（重复上报时以首条为准，未知阶段名忽略）。"""

    known: dict[str, StageResult] = {}
    for stage in stages or ():
        if not isinstance(stage, StageResult):
            continue
        if stage.stage in STAGES and stage.stage not in known:
            known[stage.stage] = stage
    return known


def _effective_status(stage: StageResult) -> str:
    """越界 status 与 `run_stages._normalize` 保持一致：一律按 `failed` 处理。"""

    return stage.status if stage.status in STAGE_STATUSES else "failed"


def derive_run_status(stages: Sequence[StageResult], *, queue_count: int) -> str:
    """failed 阶段 → failed；skipped/partial → partial；全 passed 且清单为空 → empty；否则 passed。

    与 design §5 的一致处置：
    - `no_candidates` 导致的 skipped 不算异常中断，整体状态取 `empty`（表中 `no_candidates` 行）；
    - 阶段记录未覆盖全部 `STAGES`（运行被截断上报）按 `partial` 处理，避免把未跑完的运行报成 passed。

    `queue_count` 为今日待研究清单条目数，非法或负值按 0 处理（需求 1.10）。
    """

    known = _stage_status_map(stages)
    statuses = {name: _effective_status(stage) for name, stage in known.items()}

    if any(status == "failed" for status in statuses.values()):
        return "failed"

    partial_signal = any(status == "partial" for status in statuses.values())
    partial_signal = partial_signal or any(
        status == "skipped" and (known[name].reason_code or "") not in EMPTY_SKIP_REASON_CODES
        for name, status in statuses.items()
    )
    partial_signal = partial_signal or any(name not in statuses for name in STAGES)
    if partial_signal:
        return "partial"

    return "empty" if _coerce_record_count(queue_count) == 0 else "passed"


def build_progress(stages: Sequence[StageResult]) -> dict[str, Any]:
    """返回 `{"current_stage", "completed_count", "total_count"}`，供首屏运行中展示。

    `current_stage` 取首个未完成阶段（无记录、`failed` 或 `skipped` 都算未完成），全部完成时为空串；
    `completed_count` 为 `status ∈ PROGRESS_COMPLETED_STATUSES` 的阶段数；`total_count` 恒为
    `len(STAGES)`（需求 2.6）。
    """

    known = _stage_status_map(stages)
    completed = [
        name
        for name in STAGES
        if name in known and _effective_status(known[name]) in PROGRESS_COMPLETED_STATUSES
    ]
    current_stage = next((name for name in STAGES if name not in completed), "")
    return {
        "current_stage": current_stage,
        "completed_count": len(completed),
        "total_count": len(STAGES),
    }


def _action_entry(
    *,
    stage: str,
    reason_code: str,
    template: Mapping[str, str],
) -> dict[str, Any]:
    entry = {
        "action": str(template.get("action", "")),
        "label": str(template.get("label", "")),
        "stage": stage,
        "reason_code": reason_code,
        "command": str(template.get("command", "")),
        "endpoint": str(template.get("endpoint", "")),
        "reason": str(template.get("reason", "")),
    }
    return {key: entry[key] for key in _ACTION_KEYS}


def _stage_supplied_actions(stage: StageResult) -> list[dict[str, Any]]:
    """规整阶段自带的 `next_actions`：补 `stage` / `reason_code`，剔除不可执行条目。"""

    entries: list[dict[str, Any]] = []
    for raw in stage.next_actions or ():
        if not isinstance(raw, Mapping):
            continue
        action = str(raw.get("action", "")).strip()
        command = str(raw.get("command", "")).strip()
        endpoint = str(raw.get("endpoint", "")).strip()
        if not action or not (command or endpoint):
            continue
        entry = dict(raw)
        entry["action"] = action
        entry["command"] = command
        entry["endpoint"] = endpoint
        entry["stage"] = str(raw.get("stage", "") or stage.stage)
        entry["reason_code"] = str(raw.get("reason_code", "") or stage.reason_code or "")
        entries.append(entry)
    return entries


def build_next_actions(stages: Sequence[StageResult], *, status: str) -> list[dict[str, Any]]:
    """非 passed 状态必须返回 ≥1 条，每条含 action / reason_code 与 command 或 endpoint。

    组装顺序：阶段自带的 `next_actions` → 按阶段顺序展开的原因码动作 → 兜底动作。
    同 `(action, reason_code)` 只保留首条。`status="empty"` 恒包含清单为空的重跑动作
    （需求 1.10）；`passed` 不补兜底动作，但仍会带出 `evidence_missing` 这类
    “整体 passed 且有待办”的原因码动作（design §5）。
    """

    normalized_status = str(status or "").strip()
    known = _stage_status_map(stages)
    ordered = [known[name] for name in STAGES if name in known]

    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(entry: Mapping[str, Any]) -> None:
        key = (str(entry.get("action", "")), str(entry.get("reason_code", "")))
        if key in seen:
            return
        seen.add(key)
        actions.append(dict(entry))

    for stage in ordered:
        for entry in _stage_supplied_actions(stage):
            _add(entry)

    for stage in ordered:
        reason_code = stage.reason_code or ""
        template = _REASON_ACTIONS.get(reason_code)
        if reason_code and template is None:
            template = _FALLBACK_ACTION
        if template is None:
            continue
        _add(_action_entry(stage=stage.stage, reason_code=reason_code, template=template))

    if normalized_status == "empty":
        _add(
            _action_entry(
                stage="build_daily_queue",
                reason_code="no_candidates",
                template=_REASON_ACTIONS["no_candidates"],
            )
        )

    if not actions and normalized_status != "passed":
        _add(_action_entry(stage="", reason_code="", template=_FALLBACK_ACTION))

    return actions


# ---------------------------------------------------------------------------
# 配置项解析（design §3.3）：集中在本模块的纯函数里，facade 只消费返回值，
# 避免配置解析散落进 `app/services.py`（需求 1.4、1.12、4.5、6.1、7.4）。
# ---------------------------------------------------------------------------

ENV_TIMEOUT_SECONDS = "AI_QUANT_DAILY_BRIEF_TIMEOUT_SECONDS"
ENV_CANDIDATE_LIMIT = "AI_QUANT_DAILY_MAINLINE_CANDIDATE_LIMIT"
ENV_MARKET_QUOTA = "AI_QUANT_DAILY_MAINLINE_MARKET_QUOTA"
ENV_DILIGENCE_LIMIT = "AI_QUANT_DAILY_MAINLINE_DILIGENCE_LIMIT"
ENV_ARTIFACT_DIR = "AI_QUANT_DAILY_MAINLINE_ARTIFACT_DIR"

DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_CANDIDATE_LIMIT = 20
DEFAULT_MARKET_QUOTA = 10
# The production gateway commonly needs 50-60 seconds per evidence-backed
# diligence call. Four calls keep the default 20-candidate run inside the
# 600-second orchestration budget while preserving all candidates in the queue.
DEFAULT_DILIGENCE_LIMIT = 4
# artifact 目录默认值与 `daily_mainline_artifact.ARTIFACT_DIR` 同源，避免两处漂移。
DEFAULT_ARTIFACT_DIR = ARTIFACT_DIR

CONFIG_KEYS: tuple[str, ...] = (
    "timeout_seconds",
    "candidate_limit",
    "market_quota",
    "diligence_limit",
    "artifact_dir",
)

CONFIG_ENV_VARS: dict[str, str] = {
    "timeout_seconds": ENV_TIMEOUT_SECONDS,
    "candidate_limit": ENV_CANDIDATE_LIMIT,
    "market_quota": ENV_MARKET_QUOTA,
    "diligence_limit": ENV_DILIGENCE_LIMIT,
    "artifact_dir": ENV_ARTIFACT_DIR,
}

CONFIG_DEFAULTS: dict[str, Any] = {
    "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
    "candidate_limit": DEFAULT_CANDIDATE_LIMIT,
    "market_quota": DEFAULT_MARKET_QUOTA,
    "diligence_limit": DEFAULT_DILIGENCE_LIMIT,
    "artifact_dir": DEFAULT_ARTIFACT_DIR,
}

# 下限保护：四个数值项都是“上限 / 预算”语义，非正值等于“什么都不做”。
# `build_candidate_pool`（`daily_mainline_scan.py`）对 `candidate_limit <= 0` 或
# `market_quota <= 0` 一律返回空池，误配会让当日清单静默为空；`timeout_seconds <= 0`
# 会让所有阶段直接 `timeout_budget_exceeded`；`diligence_limit <= 0` 会让所有候选
# 记 `diligence_budget_exhausted`。因此四项统一夹到 ≥1。
# 想跑“无 LLM 观点”的主线应通过不配置 LLM 网关（走 `llm_gateway_unconfigured`
# 降级路径）表达，而不是把 `diligence_limit` 设为 0。
CONFIG_MINIMUMS: dict[str, int] = {
    "timeout_seconds": 1,
    "candidate_limit": 1,
    "market_quota": 1,
    "diligence_limit": 1,
}

# 整数型配置键（`artifact_dir` 为字符串，单独解析）。
CONFIG_INT_KEYS: tuple[str, ...] = tuple(CONFIG_MINIMUMS)


def _clamp_int(raw: Any, default: int, *, minimum: int) -> int:
    """解析单次运行的覆盖入参：不可解析回落默认值，再按下限夹取。

    环境取值一律走 `app.utils.env_int`（同语义）；本函数只服务 `overrides`，
    因为覆盖入参是 CLI / API 传入的 Python 值而不是环境字符串。
    """

    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _resolve_int(env: Mapping[str, str], key: str) -> int:
    """按配置键从传入映射读取整数：复用 `app.utils.env_int`，并注入 `env` 保持纯函数。"""

    return env_int(
        CONFIG_ENV_VARS[key],
        int(CONFIG_DEFAULTS[key]),
        minimum=CONFIG_MINIMUMS[key],
        env=env,
    )


def normalize_artifact_dir(value: Any) -> str:
    """归一 artifact 目录：反斜杠转 POSIX 分隔符、去尾部分隔符，空值回落默认目录。"""

    text = str(value or "").strip().replace("\\", "/").rstrip("/")
    return text or DEFAULT_ARTIFACT_DIR


def resolve_config(
    env: Mapping[str, str],
    *,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """解析每日主线的 5 个配置项（design §3.3），返回 facade 直接可用的取值。

    参数：
        env: 环境变量映射，必须显式传入（facade / CLI 传 `os.environ`）。取值解析复用既有
            `app.utils.env_int` / `env_text`，并把该映射作为 `env=` 注入，因此本模块不读
            `os.environ`：函数保持纯函数，无需 patch 进程环境即可测试（也不影响 T-424 的
            “导入应用模块不加载 `.env`” 约束）。
        overrides: 单次运行的入参覆盖（CLI `--timeout-seconds` / `--diligence-limit`
            / `--artifact-dir` 与 `POST /api/daily-mainline/run` 的 payload）。
            键与返回值同名，`None` / 空串 / 不可解析的值忽略并保留环境取值，
            因此覆盖值同样受下限保护，不会绕过 `CONFIG_MINIMUMS`。

    返回：
        `{"timeout_seconds", "candidate_limit", "market_quota", "diligence_limit",
        "artifact_dir"}`。全部有默认值，五个环境变量都缺省时返回
        `600 / 20 / 10 / 8 / "artifacts/daily-mainline"`，即缺省不改变既有行为。
    """

    config: dict[str, Any] = {key: _resolve_int(env, key) for key in CONFIG_INT_KEYS}
    config["artifact_dir"] = normalize_artifact_dir(env_text(ENV_ARTIFACT_DIR, env=env))

    for key, raw in (overrides or {}).items():
        if key not in CONFIG_KEYS or raw is None:
            continue
        if key == "artifact_dir":
            text = str(raw).strip()
            if text:
                config["artifact_dir"] = normalize_artifact_dir(text)
            continue
        config[key] = _clamp_int(raw, int(config[key]), minimum=CONFIG_MINIMUMS[key])

    return {key: config[key] for key in CONFIG_KEYS}
