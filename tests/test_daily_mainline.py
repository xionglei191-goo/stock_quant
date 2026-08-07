from __future__ import annotations

import json
import os
import unittest
from contextlib import redirect_stdout
from dataclasses import fields as dataclass_fields
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping
from unittest.mock import MagicMock, patch

from app.errors import ValidationError
from app.llm_gateway import LLMGateway
from app.models import (
    DailyMainlineQueueItem,
    DailyMainlineRun,
    DailyWatchlistEntry,
    Document,
    Evidence,
    LLMTaskRun,
    LLMTaskTemplate,
    MarketDataPoint,
    RightsTag,
)
from app.service_modules.daily_mainline import (
    CONFIG_DEFAULTS,
    CONFIG_ENV_VARS,
    CONFIG_KEYS,
    CONFIG_MINIMUMS,
    DAILY_MAINLINE_CLI_COMMAND,
    DEFAULT_ARTIFACT_DIR,
    ENV_ARTIFACT_DIR,
    ENV_CANDIDATE_LIMIT,
    ENV_DILIGENCE_LIMIT,
    ENV_MARKET_QUOTA,
    ENV_TIMEOUT_SECONDS,
    FAILURE_REASON_RESULT_INVALID,
    FAILURE_REASON_RUNNER_ERROR,
    ORCHESTRATOR_REASON_CODES,
    REASON_CODES,
    RUN_STATUSES,
    SKIP_REASON_RUNNER_UNAVAILABLE,
    SKIP_REASON_TIMEOUT,
    SKIP_REASON_UPSTREAM_FAILED,
    STAGE_REASON_CODES,
    STAGE_STATUSES,
    STAGES,
    StageResult,
    build_next_actions,
    build_progress,
    derive_run_status,
    diligence_call_timeout_seconds,
    queue_stage_reserve_seconds,
    resolve_config,
    run_stages,
)
from app.service_modules.daily_mainline_artifact import SENSITIVE_KEY_PATTERNS, is_sensitive_key
from app.service_modules.daily_mainline_diligence import (
    BUILTIN_TEMPLATES,
    PROMPT_VERSION,
    TASK_TYPES,
    TEMPLATE_PAYLOAD_FIELDS,
    TEMPLATE_STATUS,
    seed_specs,
    template_ids,
)
from app.store import COLLECTIONS, SQLiteStore
from app.utils import env_int
from tests.support import SystemServiceTestBase


class _FakeTime:
    """注入式时钟：`clock` 按预设步长推进，`now_iso` 输出可读时间戳。"""

    def __init__(self, steps: list[float] | None = None) -> None:
        self.seconds = 0.0
        self.steps = list(steps or [])
        self.iso_calls = 0

    def clock(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds

    def now_iso(self) -> str:
        self.iso_calls += 1
        return f"2026-07-28T00:00:{self.iso_calls:02d}+00:00"


def _runner(
    *,
    status: str = "passed",
    record_count: int = 1,
    payload: dict[str, Any] | None = None,
    reason_code: str = "",
    seen: list[Mapping[str, Any]] | None = None,
    fake_time: _FakeTime | None = None,
    cost_seconds: float = 0.0,
):
    def _run(context: Mapping[str, Any]) -> StageResult:
        if seen is not None:
            seen.append(dict(context))
        if fake_time is not None and cost_seconds:
            fake_time.advance(cost_seconds)
        return StageResult(
            stage="ignored-by-orchestrator",
            status=status,
            started_at="ignored",
            finished_at="ignored",
            record_count=record_count,
            reason_code=reason_code,
            payload=dict(payload or {}),
        )

    return _run


class DailyMainlineStageMachineTests(unittest.TestCase):
    def test_stage_contract_constants(self) -> None:
        self.assertEqual(
            STAGES,
            (
                "scan_market_disturbance",
                "build_candidate_pool",
                "run_auto_diligence",
                "build_daily_queue",
            ),
        )
        self.assertEqual(STAGE_STATUSES, ("passed", "partial", "failed", "skipped"))

    def test_happy_path_runs_all_stages_in_fixed_order_and_chains_payload(self) -> None:
        fake_time = _FakeTime()
        seen: list[Mapping[str, Any]] = []
        stage_runners = {
            stage: _runner(payload={"from": stage}, record_count=index + 1, seen=seen)
            for index, stage in enumerate(STAGES)
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual([item.stage for item in results], list(STAGES))
        self.assertEqual([item.status for item in results], ["passed"] * 4)
        self.assertEqual([item.record_count for item in results], [1, 2, 3, 4])
        self.assertEqual(seen[0], {})
        self.assertEqual(
            [context.get("from") for context in seen[1:]],
            list(STAGES[:-1]),
        )
        for item in results:
            self.assertLessEqual(item.started_at, item.finished_at)
            self.assertEqual(item.reason_code, "")

    def test_failed_stage_skips_remaining_and_preserves_completed_results(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {
            STAGES[0]: _runner(record_count=12, payload={"rows": 12}),
            STAGES[1]: _runner(status="failed", record_count=0, reason_code="store_write_failed"),
            STAGES[2]: _runner(),
            STAGES[3]: _runner(),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual([item.stage for item in results], list(STAGES))
        self.assertEqual(
            [item.status for item in results],
            ["passed", "failed", "skipped", "skipped"],
        )
        self.assertEqual(results[0].record_count, 12)
        self.assertEqual(results[0].payload, {"rows": 12})
        self.assertEqual(results[1].reason_code, "store_write_failed")
        self.assertEqual(results[2].reason_code, SKIP_REASON_UPSTREAM_FAILED)
        self.assertEqual(results[3].reason_code, SKIP_REASON_UPSTREAM_FAILED)

    def test_timeout_budget_skips_remaining_stages_without_clearing_history(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {
            STAGES[0]: _runner(record_count=7, fake_time=fake_time, cost_seconds=4.0),
            STAGES[1]: _runner(record_count=5, fake_time=fake_time, cost_seconds=8.0),
            STAGES[2]: _runner(record_count=3),
            STAGES[3]: _runner(record_count=2),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=10,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual(
            [item.status for item in results],
            ["passed", "passed", "skipped", "skipped"],
        )
        self.assertEqual([item.record_count for item in results], [7, 5, 0, 0])
        self.assertEqual(results[2].reason_code, SKIP_REASON_TIMEOUT)
        self.assertEqual(results[3].reason_code, SKIP_REASON_TIMEOUT)

    def test_diligence_timeout_allocator_reserves_queue_budget(self) -> None:
        self.assertEqual(queue_stage_reserve_seconds(600), 30.0)
        self.assertEqual(
            diligence_call_timeout_seconds(
                remaining_seconds=545,
                remaining_candidates=8,
                gateway_timeout_seconds=120,
                total_timeout_seconds=600,
            ),
            52,
        )
        self.assertEqual(
            diligence_call_timeout_seconds(
                remaining_seconds=30,
                remaining_candidates=1,
                gateway_timeout_seconds=120,
                total_timeout_seconds=600,
            ),
            0,
        )

    def test_missing_runner_is_skipped_without_cascading(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {
            STAGES[0]: _runner(),
            STAGES[2]: _runner(),
            STAGES[3]: _runner(),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual(
            [item.status for item in results],
            ["passed", "skipped", "passed", "passed"],
        )
        self.assertEqual(results[1].reason_code, SKIP_REASON_RUNNER_UNAVAILABLE)

    def test_runner_exception_becomes_failed_stage_with_reason_code(self) -> None:
        fake_time = _FakeTime()

        def _boom(_context: Mapping[str, Any]) -> StageResult:
            raise RuntimeError("market data backend down")

        stage_runners = {
            STAGES[0]: _boom,
            STAGES[1]: _runner(),
            STAGES[2]: _runner(),
            STAGES[3]: _runner(),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual(results[0].status, "failed")
        self.assertEqual(results[0].reason_code, FAILURE_REASON_RUNNER_ERROR)
        self.assertEqual(results[0].payload["error_type"], "RuntimeError")
        self.assertEqual(
            [item.status for item in results[1:]],
            ["skipped", "skipped", "skipped"],
        )

    def test_invalid_stage_status_is_normalized_to_failed(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {
            STAGES[0]: _runner(status="unknown", record_count=-5),
            STAGES[1]: _runner(),
            STAGES[2]: _runner(),
            STAGES[3]: _runner(),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )

        self.assertEqual(results[0].status, "failed")
        self.assertEqual(results[0].record_count, 0)
        self.assertIn(results[0].status, STAGE_STATUSES)

    def test_stage_records_projection_excludes_payload(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {stage: _runner(payload={"secret_free": True}) for stage in STAGES}

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )
        record = results[0].to_dict()

        self.assertEqual(
            sorted(record),
            [
                "finished_at",
                "next_actions",
                "reason_code",
                "record_count",
                "stage",
                "started_at",
                "status",
            ],
        )
        self.assertNotIn("payload", record)


def _stage(stage: str, status: str, *, reason_code: str = "", record_count: int = 0) -> StageResult:
    return StageResult(
        stage=stage,
        status=status,
        started_at="2026-07-28T00:00:01+00:00",
        finished_at="2026-07-28T00:00:02+00:00",
        record_count=record_count,
        reason_code=reason_code,
    )


def _all_stages(status: str = "passed", *, record_count: int = 3) -> list[StageResult]:
    return [_stage(stage, status, record_count=record_count) for stage in STAGES]


class DeriveRunStatusTests(unittest.TestCase):
    """需求 1.9 / 1.10：整体状态派生。"""

    def test_all_passed_with_queue_items_is_passed(self) -> None:
        self.assertEqual(derive_run_status(_all_stages(), queue_count=5), "passed")

    def test_all_passed_with_empty_queue_is_empty(self) -> None:
        self.assertEqual(derive_run_status(_all_stages(), queue_count=0), "empty")

    def test_failed_stage_wins_over_skipped_and_queue_count(self) -> None:
        stages = [
            _stage(STAGES[0], "passed", record_count=12),
            _stage(STAGES[1], "failed", reason_code="store_write_failed"),
            _stage(STAGES[2], "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED),
            _stage(STAGES[3], "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED),
        ]

        self.assertEqual(derive_run_status(stages, queue_count=0), "failed")
        self.assertEqual(derive_run_status(stages, queue_count=7), "failed")

    def test_partial_stage_or_non_empty_skip_yields_partial(self) -> None:
        partial_stage = [
            _stage(STAGES[0], "partial", reason_code="market_data_stale", record_count=9),
            *[_stage(stage, "passed", record_count=2) for stage in STAGES[1:]],
        ]
        timeout_skip = [
            _stage(STAGES[0], "passed", record_count=9),
            _stage(STAGES[1], "passed", record_count=4),
            _stage(STAGES[2], "skipped", reason_code=SKIP_REASON_TIMEOUT),
            _stage(STAGES[3], "skipped", reason_code=SKIP_REASON_TIMEOUT),
        ]

        self.assertEqual(derive_run_status(partial_stage, queue_count=4), "partial")
        self.assertEqual(derive_run_status(timeout_skip, queue_count=0), "partial")

    def test_no_candidates_skip_is_empty_per_design_error_table(self) -> None:
        # design §5：no_candidates → build_candidate_pool passed(record_count=0)，
        # 尽调与清单 skipped，整体状态 empty（而非 partial）。
        stages = [
            _stage(STAGES[0], "passed", record_count=1200),
            _stage(STAGES[1], "passed", record_count=0, reason_code="no_candidates"),
            _stage(STAGES[2], "skipped", reason_code="no_candidates"),
            _stage(STAGES[3], "skipped", reason_code="no_candidates"),
        ]

        self.assertEqual(derive_run_status(stages, queue_count=0), "empty")

    def test_truncated_stage_sequence_is_partial(self) -> None:
        self.assertEqual(derive_run_status(_all_stages()[:2], queue_count=3), "partial")

    def test_derived_status_is_always_in_run_statuses(self) -> None:
        for status in STAGE_STATUSES:
            for queue_count in (0, 3, -1, "bad"):
                with self.subTest(status=status, queue_count=queue_count):
                    derived = derive_run_status(_all_stages(status), queue_count=queue_count)
                    self.assertIn(derived, RUN_STATUSES)


class BuildProgressTests(unittest.TestCase):
    """需求 2.6：阶段进度投影。"""

    def test_completed_run_reports_full_progress_without_current_stage(self) -> None:
        self.assertEqual(
            build_progress(_all_stages()),
            {"current_stage": "", "completed_count": 4, "total_count": len(STAGES)},
        )

    def test_current_stage_is_first_incomplete_stage(self) -> None:
        running = [_stage(STAGES[0], "passed", record_count=12)]

        self.assertEqual(
            build_progress(running),
            {"current_stage": STAGES[1], "completed_count": 1, "total_count": 4},
        )

    def test_failed_and_skipped_stages_are_not_counted_as_completed(self) -> None:
        stages = [
            _stage(STAGES[0], "passed", record_count=12),
            _stage(STAGES[1], "partial", reason_code="llm_gateway_unconfigured"),
            _stage(STAGES[2], "failed", reason_code=FAILURE_REASON_RUNNER_ERROR),
            _stage(STAGES[3], "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED),
        ]

        self.assertEqual(
            build_progress(stages),
            {"current_stage": STAGES[2], "completed_count": 2, "total_count": 4},
        )

    def test_empty_stage_list_reports_first_stage(self) -> None:
        self.assertEqual(
            build_progress([]),
            {"current_stage": STAGES[0], "completed_count": 0, "total_count": 4},
        )


class BuildNextActionsTests(unittest.TestCase):
    """需求 1.9 / 1.10 / 2.7：非 passed 状态必须给出可执行下一步。"""

    def _assert_actionable(self, actions: list[dict[str, Any]]) -> None:
        self.assertGreaterEqual(len(actions), 1)
        for action in actions:
            with self.subTest(action=action.get("action")):
                self.assertTrue(action.get("action"))
                self.assertIn("reason_code", action)
                self.assertTrue(action.get("command") or action.get("endpoint"))

    def test_clean_passed_run_has_no_next_actions(self) -> None:
        self.assertEqual(build_next_actions(_all_stages(), status="passed"), [])

    def test_every_reason_code_maps_to_an_actionable_entry(self) -> None:
        for reason_code in REASON_CODES:
            with self.subTest(reason_code=reason_code):
                stages = [
                    _stage(STAGES[0], "partial", reason_code=reason_code, record_count=1),
                    *[_stage(stage, "passed", record_count=1) for stage in STAGES[1:]],
                ]
                actions = build_next_actions(stages, status="partial")
                self._assert_actionable(actions)
                self.assertEqual(actions[0]["reason_code"], reason_code)
                self.assertEqual(actions[0]["stage"], STAGES[0])

    def test_orchestrator_reason_codes_are_covered(self) -> None:
        # 任务 2.1 引入的编排器级原因码不在 design §5 表内，仍必须产生下一步动作，
        # 否则会出现 partial 状态却无 next_actions。
        for reason_code in ORCHESTRATOR_REASON_CODES:
            with self.subTest(reason_code=reason_code):
                self.assertNotIn(reason_code, STAGE_REASON_CODES)
                stages = [
                    _stage(STAGES[0], "passed", record_count=4),
                    _stage(STAGES[1], "skipped", reason_code=reason_code),
                    _stage(STAGES[2], "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED),
                    _stage(STAGES[3], "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED),
                ]
                actions = build_next_actions(stages, status="partial")
                self._assert_actionable(actions)
                self.assertIn(reason_code, {item["reason_code"] for item in actions})

    def test_empty_status_returns_rerun_action_with_command_and_endpoint(self) -> None:
        stages = [
            _stage(STAGES[0], "passed", record_count=1200),
            _stage(STAGES[1], "passed", record_count=0, reason_code="no_candidates"),
            _stage(STAGES[2], "skipped", reason_code="no_candidates"),
            _stage(STAGES[3], "skipped", reason_code="no_candidates"),
        ]

        actions = build_next_actions(stages, status="empty")

        self._assert_actionable(actions)
        self.assertEqual([item["reason_code"] for item in actions], ["no_candidates"])
        self.assertEqual(actions[0]["command"], DAILY_MAINLINE_CLI_COMMAND)
        self.assertEqual(actions[0]["endpoint"], "/api/daily-mainline/run")

    def test_empty_status_without_reason_codes_still_returns_action(self) -> None:
        actions = build_next_actions(_all_stages(record_count=0), status="empty")

        self._assert_actionable(actions)
        self.assertEqual(actions[0]["reason_code"], "no_candidates")

    def test_unknown_reason_code_falls_back_to_inspect_action(self) -> None:
        stages = [
            _stage(STAGES[0], "failed", reason_code="brand_new_unmapped_code"),
            *[_stage(stage, "skipped", reason_code=SKIP_REASON_UPSTREAM_FAILED) for stage in STAGES[1:]],
        ]

        actions = build_next_actions(stages, status="failed")

        self._assert_actionable(actions)
        self.assertEqual(actions[0]["action"], "inspect_daily_mainline_run")
        self.assertEqual(actions[0]["reason_code"], "brand_new_unmapped_code")

    def test_non_passed_status_without_any_reason_code_gets_fallback(self) -> None:
        self._assert_actionable(build_next_actions([], status="partial"))
        self._assert_actionable(build_next_actions(_all_stages(), status="failed"))

    def test_stage_supplied_actions_are_kept_and_incomplete_ones_dropped(self) -> None:
        stage = _stage(STAGES[2], "partial", reason_code="llm_call_failed", record_count=6)
        stage.next_actions = [
            {"action": "retry_candidate_600519", "endpoint": "/api/llm/tasks/run"},
            {"action": "no_command_or_endpoint"},
            {"command": "python3 scripts/daily_mainline_run.py"},
        ]
        stages = [
            _stage(STAGES[0], "passed", record_count=9),
            _stage(STAGES[1], "passed", record_count=4),
            stage,
            _stage(STAGES[3], "passed", record_count=4),
        ]

        actions = build_next_actions(stages, status="partial")

        self._assert_actionable(actions)
        self.assertEqual(actions[0]["action"], "retry_candidate_600519")
        self.assertEqual(actions[0]["stage"], STAGES[2])
        self.assertEqual(actions[0]["reason_code"], "llm_call_failed")
        self.assertNotIn("no_command_or_endpoint", {item["action"] for item in actions})

    def test_end_to_end_status_progress_and_actions_stay_consistent(self) -> None:
        fake_time = _FakeTime()
        stage_runners = {
            STAGES[0]: _runner(record_count=24, payload={"rows": 24}),
            STAGES[1]: _runner(status="unknown", record_count=0),
            STAGES[2]: _runner(),
            STAGES[3]: _runner(),
        }

        results = run_stages(
            stage_runners=stage_runners,
            timeout_seconds=600,
            clock=fake_time.clock,
            now_iso=fake_time.now_iso,
        )
        status = derive_run_status(results, queue_count=0)
        progress = build_progress(results)
        actions = build_next_actions(results, status=status)

        self.assertEqual(status, "failed")
        self.assertEqual(
            progress,
            {"current_stage": STAGES[1], "completed_count": 1, "total_count": 4},
        )
        self._assert_actionable(actions)
        self.assertEqual(actions[0]["reason_code"], FAILURE_REASON_RESULT_INVALID)
        self.assertIn(SKIP_REASON_UPSTREAM_FAILED, {item["reason_code"] for item in actions})


class ResolveConfigTests(unittest.TestCase):
    """任务 9.3：配置项解析（design §3.3，需求 1.4、1.12、4.5、6.1）。"""

    def test_config_contract_constants(self) -> None:
        self.assertEqual(
            CONFIG_KEYS,
            ("timeout_seconds", "candidate_limit", "market_quota", "diligence_limit", "artifact_dir"),
        )
        self.assertEqual(
            CONFIG_ENV_VARS,
            {
                "timeout_seconds": "AI_QUANT_DAILY_BRIEF_TIMEOUT_SECONDS",
                "candidate_limit": "AI_QUANT_DAILY_MAINLINE_CANDIDATE_LIMIT",
                "market_quota": "AI_QUANT_DAILY_MAINLINE_MARKET_QUOTA",
                "diligence_limit": "AI_QUANT_DAILY_MAINLINE_DILIGENCE_LIMIT",
                "artifact_dir": "AI_QUANT_DAILY_MAINLINE_ARTIFACT_DIR",
            },
        )
        self.assertEqual(set(CONFIG_DEFAULTS), set(CONFIG_KEYS))
        self.assertEqual(DEFAULT_ARTIFACT_DIR, "artifacts/daily-mainline")

    def test_empty_env_returns_documented_defaults(self) -> None:
        config = resolve_config({})
        self.assertEqual(
            config,
            {
                "timeout_seconds": 600,
                "candidate_limit": 20,
                "market_quota": 10,
                "diligence_limit": 4,
                "artifact_dir": "artifacts/daily-mainline",
            },
        )
        self.assertEqual(tuple(config), CONFIG_KEYS)

    def test_env_values_are_read_for_every_key(self) -> None:
        config = resolve_config(
            {
                ENV_TIMEOUT_SECONDS: "1200",
                ENV_CANDIDATE_LIMIT: "35",
                ENV_MARKET_QUOTA: " 15 ",
                ENV_DILIGENCE_LIMIT: "3",
                ENV_ARTIFACT_DIR: "artifacts/custom-daily/",
            }
        )
        self.assertEqual(config["timeout_seconds"], 1200)
        self.assertEqual(config["candidate_limit"], 35)
        self.assertEqual(config["market_quota"], 15)
        self.assertEqual(config["diligence_limit"], 3)
        self.assertEqual(config["artifact_dir"], "artifacts/custom-daily")

    def test_non_positive_limits_are_clamped_so_the_queue_never_silently_empties(self) -> None:
        # build_candidate_pool 对 candidate_limit / market_quota <= 0 返回空池，
        # 因此误配必须被下限保护挡住（任务 3.1 的实现发现）。
        config = resolve_config(
            {
                ENV_TIMEOUT_SECONDS: "0",
                ENV_CANDIDATE_LIMIT: "0",
                ENV_MARKET_QUOTA: "-3",
                ENV_DILIGENCE_LIMIT: "-5",
            }
        )
        self.assertEqual(config["timeout_seconds"], CONFIG_MINIMUMS["timeout_seconds"])
        self.assertEqual(config["candidate_limit"], 1)
        self.assertEqual(config["market_quota"], 1)
        self.assertEqual(config["diligence_limit"], 1)

    def test_every_numeric_key_has_a_positive_lower_bound(self) -> None:
        self.assertEqual(set(CONFIG_MINIMUMS), set(CONFIG_KEYS) - {"artifact_dir"})
        for key, minimum in CONFIG_MINIMUMS.items():
            with self.subTest(key=key):
                self.assertEqual(minimum, 1)
                self.assertEqual(resolve_config({CONFIG_ENV_VARS[key]: "0"})[key], 1)

    def test_blank_and_unparsable_values_fall_back_to_defaults(self) -> None:
        for raw in ("", "   ", "abc", "12.5", "1e3"):
            with self.subTest(raw=raw):
                config = resolve_config(
                    {
                        ENV_TIMEOUT_SECONDS: raw,
                        ENV_CANDIDATE_LIMIT: raw,
                        ENV_MARKET_QUOTA: raw,
                        ENV_DILIGENCE_LIMIT: raw,
                        ENV_ARTIFACT_DIR: raw,
                    }
                )
                self.assertEqual(config["timeout_seconds"], 600)
                self.assertEqual(config["candidate_limit"], 20)
                self.assertEqual(config["market_quota"], 10)
                self.assertEqual(config["diligence_limit"], 4)
                # artifact_dir 是自由文本目录名：只有空白值回落默认目录。
                expected_dir = raw.strip() or DEFAULT_ARTIFACT_DIR
                self.assertEqual(config["artifact_dir"], expected_dir)

    def test_artifact_dir_is_normalized_to_posix_without_trailing_separator(self) -> None:
        cases = {
            "artifacts\\daily-mainline\\": "artifacts/daily-mainline",
            " artifacts/nested/dir// ": "artifacts/nested/dir",
            "/tmp/daily-mainline": "/tmp/daily-mainline",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(resolve_config({ENV_ARTIFACT_DIR: raw})["artifact_dir"], expected)

    def test_run_payload_overrides_win_but_stay_clamped(self) -> None:
        env = {ENV_TIMEOUT_SECONDS: "600", ENV_CANDIDATE_LIMIT: "20", ENV_MARKET_QUOTA: "10"}
        config = resolve_config(
            env,
            overrides={
                "as_of_date": "2026-07-24",  # 非配置键，忽略
                "timeout_seconds": 1200,
                "diligence_limit": "16",
                "candidate_limit": 0,  # 误配覆盖同样被下限挡住
                "market_quota": None,  # None 保留环境取值
                "artifact_dir": "artifacts/run-scoped/",
            },
        )
        self.assertEqual(config["timeout_seconds"], 1200)
        self.assertEqual(config["diligence_limit"], 16)
        self.assertEqual(config["candidate_limit"], 1)
        self.assertEqual(config["market_quota"], 10)
        self.assertEqual(config["artifact_dir"], "artifacts/run-scoped")
        self.assertEqual(tuple(config), CONFIG_KEYS)

    def test_unparsable_override_keeps_the_environment_value(self) -> None:
        config = resolve_config(
            {ENV_TIMEOUT_SECONDS: "900"},
            overrides={"timeout_seconds": "not-a-number", "artifact_dir": "   "},
        )
        self.assertEqual(config["timeout_seconds"], 900)
        self.assertEqual(config["artifact_dir"], DEFAULT_ARTIFACT_DIR)

    def test_int_keys_delegate_to_utils_env_int(self) -> None:
        # 整数解析复用既有 app.utils.env_int（注入 env=），不在领域模块内另写一套解析。
        raws = ("", "  ", "abc", "0", "-4", "12.5", " 15 ", "1200")
        for key in CONFIG_KEYS:
            if key == "artifact_dir":
                continue
            for raw in raws:
                with self.subTest(key=key, raw=raw):
                    env = {CONFIG_ENV_VARS[key]: raw}
                    self.assertEqual(
                        resolve_config(env)[key],
                        env_int(
                            CONFIG_ENV_VARS[key],
                            int(CONFIG_DEFAULTS[key]),
                            minimum=CONFIG_MINIMUMS[key],
                            env=env,
                        ),
                    )

    def test_process_environment_is_ignored_when_a_mapping_is_passed(self) -> None:
        # 纯函数护栏：进程环境里有配置也不参与解析（T-424 的配置隔离不能被绕过）。
        polluted = {
            ENV_TIMEOUT_SECONDS: "42",
            ENV_CANDIDATE_LIMIT: "43",
            ENV_MARKET_QUOTA: "44",
            ENV_DILIGENCE_LIMIT: "45",
            ENV_ARTIFACT_DIR: "artifacts/should-not-be-used",
        }
        with patch.dict(os.environ, polluted, clear=False):
            self.assertEqual(resolve_config({}), dict(CONFIG_DEFAULTS))

    def test_os_environ_can_be_passed_directly_as_the_mapping(self) -> None:
        # facade / CLI 显式传 os.environ 时才读进程环境（依赖注入，模块内不隐式读取）。
        env = {
            ENV_TIMEOUT_SECONDS: "0",
            ENV_CANDIDATE_LIMIT: "abc",
            ENV_MARKET_QUOTA: "-3",
            ENV_DILIGENCE_LIMIT: "4",
            ENV_ARTIFACT_DIR: "artifacts/from-process-env/",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(resolve_config(os.environ), resolve_config(env))
        self.assertEqual(
            resolve_config({}),
            {
                "timeout_seconds": 600,
                "candidate_limit": 20,
                "market_quota": 10,
                "diligence_limit": 4,
                "artifact_dir": DEFAULT_ARTIFACT_DIR,
            },
        )


NEW_COLLECTION_SPECS = (
    ("daily_mainline_runs", "run_id", DailyMainlineRun),
    ("daily_mainline_queue_items", "item_id", DailyMainlineQueueItem),
    ("daily_watchlist_entries", "entry_id", DailyWatchlistEntry),
)

RUN_STATUS_DOMAIN = ("passed", "partial", "failed", "empty")
PARTITION_DOMAIN = ("researchable", "pending_evidence")
REVIEW_STATUS_DOMAIN = ("pending", "accepted", "rejected")

SELECTION_REASON = "单日涨跌幅 7.4% 触发扫市阈值（成交额放大 3.2 倍）"


def _mainline_run(run_id: str, *, run_date: str = "2026-07-28") -> DailyMainlineRun:
    return DailyMainlineRun(
        run_id=run_id,
        run_date=run_date,
        status="partial",
        stages=[
            {"stage": STAGES[0], "status": "passed", "record_count": 1200, "reason_code": ""},
            {"stage": STAGES[1], "status": "passed", "record_count": 2, "reason_code": ""},
            {"stage": STAGES[2], "status": "skipped", "record_count": 0, "reason_code": SKIP_REASON_TIMEOUT},
            {"stage": STAGES[3], "status": "passed", "record_count": 2, "reason_code": ""},
        ],
        candidate_count=2,
        queue_count=2,
        unsupported_count=1,
        llm_run_ids=["llm_run_a", "llm_run_b"],
        failure_reason_codes=[SKIP_REASON_TIMEOUT],
        next_actions=[
            {
                "action": "rerun_daily_mainline",
                "reason_code": SKIP_REASON_TIMEOUT,
                "stage": STAGES[2],
                "command": DAILY_MAINLINE_CLI_COMMAND,
            }
        ],
        timeout_seconds=900,
        elapsed_seconds=903.5,
        artifact_path=f"artifacts/daily-mainline/daily-mainline-{run_date}-{run_id}.json",
        created_at=datetime(2026, 7, 28, 9, 30, 15, 250000, tzinfo=timezone.utc),
    )


def _queue_item(
    item_id: str,
    run_id: str,
    *,
    partition: str = "researchable",
    review_status: str = "pending",
) -> DailyMainlineQueueItem:
    return DailyMainlineQueueItem(
        item_id=item_id,
        run_id=run_id,
        security_id="600519.SH",
        issuer_id="issuer_600519",
        ticker="600519",
        market="A",
        rank=1,
        selection_reason=SELECTION_REASON,
        trigger_metric="one_day_return",
        trigger_value=0.074,
        as_of_date="2026-07-28",
        completeness_status="partial",
        missing_layers=["relationship_coverage", "财务快照"],
        partition=partition,
        viewpoint={
            "summary": "放量突破，等待官方披露补齐事实字段",
            "source_layer": "viewpoint",
            "prompt_version": "daily-mainline-v1",
            "model": "test-model",
            "fact_field_writes": [],
        },
        evidence_ids=["ev_1", "ev_2"],
        research_answer_id="answer_1",
        llm_task_run_id="llm_run_a",
        template_id="candidate_diligence",
        review_status=review_status,
        diligence_status="generated" if partition == "researchable" else "unsupported",
        diligence_reason_code="" if partition == "researchable" else "evidence_missing",
        created_at=datetime(2026, 7, 28, 9, 31, 0, 125000, tzinfo=timezone.utc),
    )


def _watchlist_entry(entry_id: str, run_id: str, item_id: str) -> DailyWatchlistEntry:
    return DailyWatchlistEntry(
        entry_id=entry_id,
        security_id="600519.SH",
        run_id=run_id,
        item_id=item_id,
        selection_reason=SELECTION_REASON,
        joined_at=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        actor="analyst_1",
    )


class DailyMainlineDataclassEnumValidationTests(unittest.TestCase):
    """任务 9.5：dataclass 枚举校验（需求 1.11、1.13、4.6，design §3.1）。"""

    def test_run_status_domain_matches_orchestrator_run_statuses(self) -> None:
        # 模型取值域与 derive_run_status 的输出域必须一致，否则 facade 写库时会被自己的校验挡住。
        self.assertEqual(set(RUN_STATUS_DOMAIN), set(RUN_STATUSES))
        for status in RUN_STATUS_DOMAIN:
            with self.subTest(status=status):
                self.assertEqual(DailyMainlineRun(run_id="run_1", run_date="2026-07-28", status=status).status, status)

    def test_run_status_outside_domain_is_rejected(self) -> None:
        # "skipped" 是阶段状态而非整体状态：混用会让整体状态失去可判定语义。
        for status in ("", "skipped", "PASSED", "succeeded", "partial ", "unknown"):
            with self.subTest(status=status):
                with self.assertRaises(ValidationError) as ctx:
                    DailyMainlineRun(run_id="run_1", run_date="2026-07-28", status=status)
                self.assertIn("status", str(ctx.exception))

    def test_queue_item_partition_and_review_status_accept_declared_values(self) -> None:
        for partition in PARTITION_DOMAIN:
            for review_status in REVIEW_STATUS_DOMAIN:
                with self.subTest(partition=partition, review_status=review_status):
                    item = DailyMainlineQueueItem(
                        item_id="item_1",
                        run_id="run_1",
                        security_id="600519.SH",
                        partition=partition,
                        review_status=review_status,
                    )
                    self.assertEqual(item.partition, partition)
                    self.assertEqual(item.review_status, review_status)

    def test_queue_item_partition_outside_domain_is_rejected(self) -> None:
        for partition in ("", "pending", "unsupported", "RESEARCHABLE", "pending_evidence "):
            with self.subTest(partition=partition):
                with self.assertRaises(ValidationError) as ctx:
                    DailyMainlineQueueItem(
                        item_id="item_1",
                        run_id="run_1",
                        security_id="600519.SH",
                        partition=partition,
                    )
                self.assertIn("partition", str(ctx.exception))

    def test_queue_item_review_status_outside_domain_is_rejected(self) -> None:
        # 需求 4.6：人工复核状态只有 pending / accepted / rejected 三种。
        for review_status in ("", "approved", "PENDING", "skipped", "accepted "):
            with self.subTest(review_status=review_status):
                with self.assertRaises(ValidationError) as ctx:
                    DailyMainlineQueueItem(
                        item_id="item_1",
                        run_id="run_1",
                        security_id="600519.SH",
                        review_status=review_status,
                    )
                self.assertIn("review_status", str(ctx.exception))

    def test_review_status_defaults_to_pending(self) -> None:
        item = DailyMainlineQueueItem(item_id="item_1", run_id="run_1", security_id="600519.SH")
        self.assertEqual(item.review_status, "pending")
        self.assertEqual(item.partition, "researchable")


class DailyMainlineStoreRoundTripTests(unittest.TestCase):
    """任务 9.5：三个 collection 的写入/按主键读回（需求 1.11、1.13、4.6，design §3.2）。"""

    def _reloaded_store(self, seed) -> SQLiteStore:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "daily_mainline.db"
        store = SQLiteStore(path)
        seed(store)
        store.commit()
        return SQLiteStore(path)

    def test_records_are_readable_by_primary_key_after_reload(self) -> None:
        def _seed(store: SQLiteStore) -> None:
            store.daily_mainline_runs["run_1"] = _mainline_run("run_1")
            store.daily_mainline_queue_items["item_1"] = _queue_item("item_1", "run_1")
            store.daily_watchlist_entries["entry_1"] = _watchlist_entry("entry_1", "run_1", "item_1")

        reloaded = self._reloaded_store(_seed)
        registered = {collection: key_field for collection, key_field, _model_type in COLLECTIONS}

        for collection, key_field, model_type in NEW_COLLECTION_SPECS:
            with self.subTest(collection=collection):
                self.assertEqual(registered.get(collection), key_field)
                records = getattr(reloaded, collection)
                self.assertEqual(len(records), 1)
                for key, record in records.items():
                    self.assertIsInstance(record, model_type)
                    self.assertEqual(getattr(record, key_field), key)

    def test_list_dict_and_non_ascii_fields_survive_the_round_trip(self) -> None:
        def _seed(store: SQLiteStore) -> None:
            store.daily_mainline_runs["run_1"] = _mainline_run("run_1")
            store.daily_mainline_queue_items["item_1"] = _queue_item("item_1", "run_1")
            store.daily_watchlist_entries["entry_1"] = _watchlist_entry("entry_1", "run_1", "item_1")

        reloaded = self._reloaded_store(_seed)
        expected_run = _mainline_run("run_1")
        expected_item = _queue_item("item_1", "run_1")

        run = reloaded.daily_mainline_runs["run_1"]
        self.assertEqual(run, expected_run)
        self.assertEqual(run.stages, expected_run.stages)
        self.assertEqual(run.llm_run_ids, ["llm_run_a", "llm_run_b"])
        self.assertEqual(run.failure_reason_codes, [SKIP_REASON_TIMEOUT])
        self.assertEqual(run.next_actions[0]["command"], DAILY_MAINLINE_CLI_COMMAND)
        self.assertEqual(run.elapsed_seconds, 903.5)
        self.assertFalse(run.live_execution_allowed)
        self.assertTrue(run.paper_only)
        self.assertEqual(run.created_at, datetime(2026, 7, 28, 9, 30, 15, 250000, tzinfo=timezone.utc))

        item = reloaded.daily_mainline_queue_items["item_1"]
        self.assertEqual(item, expected_item)
        self.assertEqual(item.selection_reason, SELECTION_REASON)
        self.assertEqual(item.missing_layers, ["relationship_coverage", "财务快照"])
        self.assertEqual(item.evidence_ids, ["ev_1", "ev_2"])
        self.assertEqual(item.viewpoint, expected_item.viewpoint)
        self.assertEqual(item.viewpoint["fact_field_writes"], [])
        self.assertEqual(item.trigger_value, 0.074)

        entry = reloaded.daily_watchlist_entries["entry_1"]
        self.assertEqual(entry, _watchlist_entry("entry_1", "run_1", "item_1"))
        self.assertEqual(entry.selection_reason, SELECTION_REASON)

    def test_watchlist_entry_keeps_security_join_time_source_run_and_reason(self) -> None:
        # 需求 1.11：加入关注池必须留下 security_id、加入时间、来源 run_id 与入选理由。
        def _seed(store: SQLiteStore) -> None:
            store.daily_watchlist_entries["entry_1"] = _watchlist_entry("entry_1", "run_2", "item_9")

        entry = self._reloaded_store(_seed).daily_watchlist_entries["entry_1"]

        self.assertEqual(entry.security_id, "600519.SH")
        self.assertEqual(entry.joined_at, datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(entry.run_id, "run_2")
        self.assertEqual(entry.item_id, "item_9")
        self.assertEqual(entry.selection_reason, SELECTION_REASON)
        self.assertEqual(entry.actor, "analyst_1")

    def test_same_day_repeat_runs_keep_independent_rows(self) -> None:
        # 需求 1.13：同日再次触发生成新 run_id，两次运行的清单各自可读。
        def _seed(store: SQLiteStore) -> None:
            store.daily_mainline_runs["run_1"] = _mainline_run("run_1")
            store.daily_mainline_runs["run_2"] = _mainline_run("run_2")
            store.daily_mainline_queue_items["item_1"] = _queue_item("item_1", "run_1")
            store.daily_mainline_queue_items["item_2"] = _queue_item("item_2", "run_2")
            store.daily_watchlist_entries["entry_1"] = _watchlist_entry("entry_1", "run_1", "item_1")

        reloaded = self._reloaded_store(_seed)

        self.assertEqual(sorted(reloaded.daily_mainline_runs), ["run_1", "run_2"])
        self.assertEqual(
            reloaded.daily_mainline_runs["run_1"].run_date,
            reloaded.daily_mainline_runs["run_2"].run_date,
        )
        self.assertEqual(
            reloaded.daily_mainline_runs["run_1"].artifact_path,
            "artifacts/daily-mainline/daily-mainline-2026-07-28-run_1.json",
        )
        self.assertNotEqual(
            reloaded.daily_mainline_runs["run_1"].artifact_path,
            reloaded.daily_mainline_runs["run_2"].artifact_path,
        )
        by_run = {
            run_id: sorted(
                item_id
                for item_id, item in reloaded.daily_mainline_queue_items.items()
                if item.run_id == run_id
            )
            for run_id in ("run_1", "run_2")
        }
        self.assertEqual(by_run, {"run_1": ["item_1"], "run_2": ["item_2"]})
        self.assertEqual(reloaded.daily_watchlist_entries["entry_1"].run_id, "run_1")

    def test_review_status_transitions_round_trip_per_item(self) -> None:
        # 需求 4.6：pending 默认值与 accepted / rejected 流转都要能持久化后读回。
        def _seed(store: SQLiteStore) -> None:
            for index, review_status in enumerate(REVIEW_STATUS_DOMAIN, start=1):
                item_id = f"item_{index}"
                store.daily_mainline_queue_items[item_id] = _queue_item(
                    item_id,
                    "run_1",
                    review_status=review_status,
                )

        reloaded = self._reloaded_store(_seed)

        self.assertEqual(
            {item_id: item.review_status for item_id, item in reloaded.daily_mainline_queue_items.items()},
            {"item_1": "pending", "item_2": "accepted", "item_3": "rejected"},
        )

        # 复核后再改状态并重新提交：新状态覆盖旧行，主键不变。
        reloaded.daily_mainline_queue_items["item_1"] = _queue_item("item_1", "run_1", review_status="accepted")
        reloaded.commit()
        rechecked = SQLiteStore(reloaded.path)
        self.assertEqual(rechecked.daily_mainline_queue_items["item_1"].review_status, "accepted")
        self.assertEqual(len(rechecked.daily_mainline_queue_items), 3)

    def test_pending_evidence_partition_round_trips_with_its_reason_code(self) -> None:
        def _seed(store: SQLiteStore) -> None:
            store.daily_mainline_queue_items["item_1"] = _queue_item(
                "item_1",
                "run_1",
                partition="pending_evidence",
            )

        item = self._reloaded_store(_seed).daily_mainline_queue_items["item_1"]

        self.assertEqual(item.partition, "pending_evidence")
        self.assertEqual(item.diligence_status, "unsupported")
        self.assertEqual(item.diligence_reason_code, "evidence_missing")


BUILTIN_TEMPLATE_TASK_TYPES = ("candidate_diligence", "evidence_summary", "risk_challenge")
"""需求 4.1 声明的三类内置模板任务类型：候选尽调、证据摘要、风险质询。"""

LLM_TASK_TEMPLATE_FIELDS = frozenset(item.name for item in dataclass_fields(LLMTaskTemplate))


def _mapping_keys(payload: Any) -> list[str]:
    """递归收集 payload 内出现的全部 mapping 键（含嵌套 schema 与列表元素）。"""

    keys: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(str(key))
            keys.extend(_mapping_keys(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            keys.extend(_mapping_keys(item))
    return keys


class DailyMainlineBuiltinTemplateContractTests(unittest.TestCase):
    """任务 4.6：内置模板集合契约（需求 4.1、4.7，design §4.3 与 §9 风险 3）。"""

    def test_task_types_are_exactly_the_three_declared_kinds(self) -> None:
        task_types = [str(template["task_type"]) for template in BUILTIN_TEMPLATES]

        self.assertEqual(set(task_types), set(BUILTIN_TEMPLATE_TASK_TYPES))
        self.assertEqual(len(task_types), len(BUILTIN_TEMPLATE_TASK_TYPES))
        self.assertEqual(len(set(task_types)), len(task_types))
        # 对外导出的 TASK_TYPES 必须与实际模板集同步，否则消费方会漏掉一类任务。
        self.assertEqual(tuple(task_types), TASK_TYPES)

    def test_every_template_is_seeded_approved_so_the_approval_gate_is_not_bypassed(self) -> None:
        # run_llm_task 在 status != "approved" 且未传 allow_unapproved 时抛 ComplianceGateError
        # （app/services.py:536）；seed 即 approved 使编排无需绕过审批门（design §9 风险 3）。
        self.assertEqual(TEMPLATE_STATUS, "approved")
        for template in BUILTIN_TEMPLATES:
            with self.subTest(template_id=template["template_id"]):
                self.assertEqual(str(template["status"]), "approved")

    def test_every_template_declares_a_non_empty_prompt_version(self) -> None:
        self.assertTrue(PROMPT_VERSION.strip())
        for template in BUILTIN_TEMPLATES:
            with self.subTest(template_id=template["template_id"]):
                prompt_version = str(template["prompt_version"])
                self.assertTrue(prompt_version.strip())
                self.assertEqual(prompt_version, PROMPT_VERSION)

    def test_template_ids_are_unique_and_non_blank(self) -> None:
        ids = [str(template["template_id"]) for template in BUILTIN_TEMPLATES]

        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(tuple(ids), template_ids())
        for template_id in ids:
            with self.subTest(template_id=template_id):
                self.assertTrue(template_id.strip())

    def test_seed_payloads_carry_status_and_prompt_version_on_the_write_path(self) -> None:
        # 断言落在 seed_specs 输出上：模板常量正确但注册 payload 丢字段同样会打开审批门。
        specs = seed_specs([])

        self.assertEqual(len(specs), len(BUILTIN_TEMPLATES))
        self.assertEqual([str(spec["task_type"]) for spec in specs], list(BUILTIN_TEMPLATE_TASK_TYPES))
        for spec in specs:
            with self.subTest(template_id=spec["template_id"]):
                self.assertEqual(str(spec["status"]), "approved")
                self.assertTrue(str(spec["prompt_version"]).strip())
                # status="approved" 的注册要求 approved_prompt_change_id（app/services.py:272）。
                self.assertTrue(str(spec["approved_prompt_change_id"]).strip())
                for required in ("template_id", "task_type", "prompt_name", "content"):
                    self.assertTrue(str(spec[required]).strip())

    def test_persisted_field_set_carries_no_credential_keys(self) -> None:
        # 需求 4.7：模板持久化字段排除凭据与完整上游响应。键面判定复用 artifact 的
        # SENSITIVE_KEY_PATTERNS，避免测试另建一套凭据词表后与实现漂移。
        self.assertIn("raw_response", SENSITIVE_KEY_PATTERNS)
        for field_name in TEMPLATE_PAYLOAD_FIELDS:
            with self.subTest(field=field_name):
                self.assertFalse(is_sensitive_key(field_name))

        for spec in seed_specs([]):
            with self.subTest(template_id=spec["template_id"]):
                self.assertEqual(sorted(key for key in _mapping_keys(spec) if is_sensitive_key(key)), [])
                # 白名单外的键不得进 payload；且每个键都必须是 LLMTaskTemplate 的真实字段，
                # 否则会出现"写了但存不下"或多存字段的情况。
                self.assertEqual(set(spec) - set(TEMPLATE_PAYLOAD_FIELDS), set())
                self.assertEqual(set(spec) - LLM_TASK_TEMPLATE_FIELDS, set())


COUNTS_KEYS_BEFORE_CHANGE = (
    "sources",
    "astock_connectors",
    "ingestion_jobs",
    "ingestion_schedules",
    "issuers",
    "securities",
    "market_data",
    "corporate_actions",
    "institutional_holdings",
    "disclosure_events",
    "documents",
    "evidence",
    "research_report_citation_evidence",
    "manual_reviews",
    "open_manual_reviews",
    "benchmark_samples",
    "benchmark_runs",
    "extraction_results",
    "research_answers",
    "research_reports",
    "llm_task_templates",
    "llm_task_runs",
    "workflow_definitions",
    "workflow_runs",
    "lineage_events",
    "model_versions",
    "secret_rotations",
    "cache_retention_runs",
    "theses",
    "signals",
    "decisions",
    "pending_decisions",
    "approved_decisions",
    "execution_intents",
    "simulated_executions",
    "portfolio_transactions",
    "reviews",
    "operating_reports",
    "strategy_replays",
    "portfolio_proposals",
    "open_exceptions",
    "source_review_overdue",
    "source_review_due_soon",
    "source_review_missing",
    "sensitive_findings",
    "research_answer_pending_reviews",
    "permission_denied_events",
    "alert_rules",
    "open_alerts",
    "alert_notifications",
)
"""变更前 `counts` 的 50 个键（逐键写死，刻意不从 `COLLECTIONS` 派生）：删掉任何一个既有键都会让断言失败。"""

NEW_COUNTS_KEYS = tuple(collection for collection, _key_field, _model_type in NEW_COLLECTION_SPECS)

SEEDED_NEW_COUNTS = {"daily_mainline_runs": 1, "daily_mainline_queue_items": 2, "daily_watchlist_entries": 1}


class DailyMainlineNewCollectionDownstreamImpactTests(SystemServiceTestBase):
    """任务 9.4：新增 collection 的下游影响（需求 7.4、7.10，design §9 风险 2）。

    风险 2 的两个落点：(1) 三个 collection 必须能按 `COLLECTIONS` 元数据读写；
    (2) `/api/analysis/latest` 的 `counts` 是显式字典，只按加法补三个键（2026-07-28 用户确认），
    既有键一个不少、也不改为按 `COLLECTIONS` 全量派生。
    """

    def _seed_new_collections(self) -> None:
        store = self.service.store
        store.daily_mainline_runs["run_1"] = _mainline_run("run_1")
        store.daily_mainline_queue_items["item_1"] = _queue_item("item_1", "run_1")
        store.daily_mainline_queue_items["item_2"] = _queue_item("item_2", "run_1", partition="pending_evidence")
        store.daily_watchlist_entries["entry_1"] = _watchlist_entry("entry_1", "run_1", "item_1")

    def test_new_collections_are_writable_and_readable_through_collections_specs(self) -> None:
        registered = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}
        self._seed_new_collections()

        for collection, key_field, model_type in NEW_COLLECTION_SPECS:
            with self.subTest(collection=collection):
                self.assertEqual(registered.get(collection), (key_field, model_type))
                # 只经 COLLECTIONS 的 (collection, key_field) 元数据寻址，不走各自的专用属性名。
                records = getattr(self.service.store, collection)
                self.assertTrue(records)
                for key, record in records.items():
                    self.assertIsInstance(record, model_type)
                    self.assertEqual(getattr(record, key_field), key)

    def test_dashboard_counts_add_the_three_keys_and_keep_every_existing_key(self) -> None:
        counts = self.service.dashboard()["counts"]

        self.assertEqual([key for key in COUNTS_KEYS_BEFORE_CHANGE if key not in counts], [])
        self.assertEqual({key: counts[key] for key in NEW_COUNTS_KEYS}, dict.fromkeys(NEW_COUNTS_KEYS, 0))
        # 加法且仅加法：键面恰为"变更前键面 ∪ 三个新键"。
        self.assertEqual(set(counts), set(COUNTS_KEYS_BEFORE_CHANGE) | set(NEW_COUNTS_KEYS))

        self._seed_new_collections()
        seeded = self.service.dashboard()["counts"]

        self.assertEqual(set(seeded), set(counts))
        self.assertEqual({key: seeded[key] for key in NEW_COUNTS_KEYS}, SEEDED_NEW_COUNTS)

    def test_counts_stays_an_explicit_dict_instead_of_deriving_from_collections(self) -> None:
        # 全量派生会把每个 collection 都灌进既有仪表盘契约，属越界变更；这里锁住"没有全量派生"。
        counts = self.service.dashboard()["counts"]
        collection_names = {collection for collection, _key_field, _model_type in COLLECTIONS}

        self.assertTrue(collection_names - set(counts))
        for collection in ("observation_items", "usage_metrics", "audit_log"):
            with self.subTest(collection=collection):
                self.assertNotIn(collection, counts)

    def test_latest_analysis_counts_surfaces_the_new_keys_end_to_end(self) -> None:
        # `/api/analysis/latest` 的 counts 直接取物化产物的 metrics_counts / dashboard_counts
        # （app/api.py:861），产物侧由 scripts/latest_analysis_run.py 原样搬运 /api/dashboard/ceo 的计数。
        self._seed_new_collections()
        dashboard = self.router.dispatch("GET", "/api/dashboard/ceo", {}, role="CEO")
        self.assertTrue(dashboard.success, dashboard.error)
        dashboard_counts = dashboard.data["counts"]

        with TemporaryDirectory() as temp_dir:
            cwd = Path.cwd()
            os.chdir(temp_dir)
            self.addCleanup(os.chdir, cwd)
            artifact_dir = Path("artifacts/latest-analysis")
            artifact_dir.mkdir(parents=True)
            artifact_dir.joinpath("latest-analysis.json").write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "generated_at": "2026-07-28T00:00:00+00:00",
                        "analysis": {
                            "dashboard_counts": dashboard_counts,
                            "metrics_counts": dict(dashboard_counts),
                        },
                    }
                ),
                encoding="utf-8",
            )
            response = self.router.dispatch("GET", "/api/analysis/latest", {}, role="CEO")

        self.assertTrue(response.success, response.error)
        counts = response.data["counts"]
        self.assertEqual({key: counts.get(key) for key in NEW_COUNTS_KEYS}, SEEDED_NEW_COUNTS)
        self.assertEqual([key for key in COUNTS_KEYS_BEFORE_CHANGE if key not in counts], [])


class MigrationScriptDerivesCollectionsTests(unittest.TestCase):
    """任务 9.4：迁移脚本按 `COLLECTIONS` 派生，新增 collection 无需改动脚本（design §9 风险 2）。"""

    def test_migration_script_iterates_collections_without_hardcoding_names(self) -> None:
        source = Path("scripts/migrate_sqlite_to_postgres.py").read_text(encoding="utf-8")

        self.assertIn("from app.store import COLLECTIONS", source)
        self.assertIn("for collection, _key_field, _model_type in COLLECTIONS", source)
        for collection, _key_field, _model_type in NEW_COLLECTION_SPECS:
            with self.subTest(collection=collection):
                self.assertNotIn(collection, source)


class DailyMainlineFacadeIntegrationTests(SystemServiceTestBase):
    def _seed_market_and_evidence(self) -> None:
        rights = RightsTag("public", False, False, "allowed", "allowed", "allowed")
        end_date = date(2026, 7, 28)
        for offset in range(20, -1, -1):
            as_of_date = (end_date - timedelta(days=offset)).isoformat()
            latest = offset == 0
            point = MarketDataPoint(
                data_id=f"md_{as_of_date}",
                security_id="sec_001",
                source_id="public_eod_market_data",
                market="A",
                as_of_date=as_of_date,
                open=100.0,
                high=112.0 if latest else 101.0,
                low=99.0,
                close=110.0 if latest else 100.0,
                adjusted_close=110.0 if latest else 100.0,
                volume=500.0 if latest else 100.0,
                amount=5000.0 if latest else 1000.0,
                rights_tag=rights,
            )
            self.service.store.market_data[point.data_id] = point
        document = Document(
            document_id="doc_daily_mainline",
            issuer_id="issuer_001",
            security_id="sec_001",
            document_type="annual_report",
            source_id="src_sec",
            source_type="regulatory",
            source_uri="https://example.test/annual-report",
            rights_tag=rights,
            body="Revenue increased with public filing evidence.",
            language="en",
        )
        evidence = Evidence(
            evidence_id="evi_daily_mainline",
            document_id=document.document_id,
            section="annual_report_disclosure",
            page_no=1,
            bbox="",
            span_text="Revenue increased with public filing evidence.",
            canonical_text="Revenue increased with public filing evidence.",
            confidence=0.99,
            security_id="sec_001",
            issuer_id="issuer_001",
        )
        self.service.store.documents[document.document_id] = document
        self.service.store.evidence[evidence.evidence_id] = evidence
        self.service.llm_gateway = LLMGateway(
            api_key="local-test-key",
            default_model="qwen3.6-plus",
            http_send=lambda _request, _timeout: json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "viewpoint_summary": "Evidence-backed daily research summary.",
                                        "evidence_ids": [evidence.evidence_id],
                                        "key_drivers": ["public filing"],
                                        "open_questions": ["verify next filing"],
                                        "next_verification_tasks": ["review disclosure"],
                                        "usage_boundary": "research_only",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8"),
        )

    def test_run_persists_lineage_queue_answer_and_artifact(self) -> None:
        self._seed_market_and_evidence()
        with TemporaryDirectory() as temp_dir:
            result = self.service.run_daily_mainline(
                {
                    "as_of_date": "2026-07-28",
                    "artifact_dir": temp_dir,
                    "diligence_limit": 1,
                },
                actor="analyst",
            )
            artifact_path = Path(result["artifact_path"])
            self.assertTrue(artifact_path.exists())
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "passed")
        self.assertEqual([stage["stage"] for stage in result["stages"]], list(STAGES))
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["queue_count"], 1)
        self.assertEqual(result["llm_success_count"], 1)
        self.assertEqual(len(self.service.store.daily_mainline_runs), 1)
        self.assertEqual(len(self.service.store.daily_mainline_queue_items), 1)
        self.assertEqual(len(self.service.store.research_answers), 1)
        queue_item = next(iter(self.service.store.daily_mainline_queue_items.values()))
        self.assertEqual(queue_item.completeness_status, "partial")
        self.assertEqual(queue_item.evidence_ids, ["evi_daily_mainline"])
        self.assertEqual(queue_item.diligence_status, "generated")
        self.assertTrue(queue_item.llm_task_run_id)
        self.assertEqual(
            self.service.store.llm_task_runs[queue_item.llm_task_run_id].status,
            "succeeded",
        )
        self.assertEqual(artifact["classification"], "local-only")
        self.assertFalse(artifact["production_release_gate_eligible"])
        self.assertTrue(artifact["paper_only"])
        self.assertFalse(artifact["live_execution_allowed"])

    def test_run_reserves_total_budget_for_queue_stage(self) -> None:
        fake_time = _FakeTime()
        candidates = [
            {
                "security_id": f"sec_budget_{index}",
                "issuer_id": f"issuer_budget_{index}",
                "ticker": f"B{index:03d}",
                "market": "A",
                "rank": index + 1,
                "selection_reason": "budget regression",
                "trigger_metric": "one_day_return",
                "trigger_value": 0.08,
                "as_of_date": "2026-07-28",
            }
            for index in range(20)
        ]
        timeouts: list[int] = []

        self.service._daily_mainline_scan_stage = MagicMock(
            return_value=StageResult(
                stage=STAGES[0],
                status="passed",
                started_at="",
                finished_at="",
                record_count=20,
                payload={"market_rows": []},
            )
        )
        self.service._daily_mainline_candidate_stage = MagicMock(
            return_value=StageResult(
                stage=STAGES[1],
                status="passed",
                started_at="",
                finished_at="",
                record_count=20,
                payload={"candidates": candidates},
            )
        )
        self.service.seed_default_llm_task_templates = MagicMock(return_value=[])
        self.service.llm_gateway = LLMGateway(
            api_key="budget-test-key",
            timeout=120,
        )
        def _candidate_context(_candidate: Mapping[str, Any]):
            fake_time.advance(12)
            return (
                {},
                {"status": "partial", "missing_layers": ["company_profile"]},
                [],
            )

        self.service._daily_mainline_candidate_context = MagicMock(
            side_effect=_candidate_context,
        )

        def _run_llm(payload: Mapping[str, Any], *, actor: str = "system") -> LLMTaskRun:
            del actor
            timeout = int(payload["timeout_seconds"])
            timeouts.append(timeout)
            fake_time.advance(timeout)
            run = LLMTaskRun(
                run_id=f"llm_budget_{len(timeouts)}",
                template_id=str(payload["template_id"]),
                task_type="candidate_diligence",
                status="fallback",
                provider="test",
                model="budget-model",
                prompt_version=PROMPT_VERSION,
                output={"mode": "rule_summary"},
                fallback_used="rule_summary",
                error="simulated timeout",
            )
            self.service.store.llm_task_runs[run.run_id] = run
            return run

        self.service.run_llm_task = _run_llm  # type: ignore[method-assign]
        with TemporaryDirectory() as temp_dir, patch(
            "app.services.time.monotonic",
            fake_time.clock,
        ):
            result = self.service.run_daily_mainline(
                {
                    "as_of_date": "2026-07-28",
                    "artifact_dir": temp_dir,
                    "candidate_limit": 20,
                    "market_quota": 20,
                    "diligence_limit": 8,
                    "timeout_seconds": 600,
                },
                actor="analyst",
            )

        self.assertEqual(len(timeouts), 8)
        self.assertLessEqual(sum(timeouts), 360)
        self.assertEqual(result["queue_count"], 20)
        self.assertEqual(result["stages"][-1]["stage"], "build_daily_queue")
        self.assertEqual(result["stages"][-1]["status"], "passed")
        persisted_run = self.service.store.daily_mainline_runs[result["run_id"]]
        self.assertNotIn(SKIP_REASON_TIMEOUT, persisted_run.failure_reason_codes)
        self.assertLessEqual(result["elapsed_seconds"], 570)

    def test_http_queue_watchlist_and_review_round_trip(self) -> None:
        self._seed_market_and_evidence()
        with TemporaryDirectory() as temp_dir:
            run = self.router.dispatch(
                "POST",
                "/api/daily-mainline/run",
                {
                    "as_of_date": "2026-07-28",
                    "artifact_dir": temp_dir,
                    "diligence_limit": 1,
                },
                role="分析师",
                actor="analyst",
            )
        self._assert_api_envelope(run)
        item_id = run.data["items"][0]["item_id"]
        queue = self.router.dispatch(
            "GET",
            "/api/daily-mainline/queue",
            {"run_id": run.data["run_id"]},
            role="分析师",
        )
        self._assert_api_envelope(queue)
        self.assertEqual(queue.data["items"][0]["item_id"], item_id)

        with patch.object(
            self.service,
            "import_company_watchlist",
            return_value={"status": "already_exists"},
        ):
            watchlist = self.router.dispatch(
                "POST",
                f"/api/daily-mainline/queue/{item_id}/watchlist",
                {},
                role="分析师",
                actor="analyst",
            )
        self._assert_api_envelope(watchlist)
        self.assertTrue(watchlist.data["created"])
        self.assertEqual(watchlist.data["entry"]["item_id"], item_id)

        review = self.router.dispatch(
            "POST",
            f"/api/daily-mainline/viewpoints/{item_id}/review",
            {"status": "accepted"},
            role="分析师",
            actor="analyst",
        )
        self._assert_api_envelope(review)
        self.assertEqual(review.data["item"]["review_status"], "accepted")
        self.assertEqual(review.data["research_answer"]["human_review_status"], "approved")

    def test_cli_and_http_call_the_same_facade(self) -> None:
        from scripts import daily_mainline_run

        result = {
            "schema_id": "daily-mainline-queue-v1",
            "status": "empty",
            "run_id": "dmrun_shared",
        }
        facade = patch.object(
            self.service,
            "run_daily_mainline",
            MagicMock(return_value=result),
        )
        with facade as run_mock:
            response = self.router.dispatch(
                "POST",
                "/api/daily-mainline/run",
                {"as_of_date": "2026-07-28"},
                role="分析师",
            )
            output = StringIO()
            with redirect_stdout(output):
                exit_code = daily_mainline_run.main(
                    ["--as-of-date", "2026-07-28"],
                    service_factory=lambda: self.service,
                )
        self._assert_api_envelope(response)
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_mock.call_count, 2)
        self.assertIn('"run_id": "dmrun_shared"', output.getvalue())


class DailyMainlineRouteSnapshotTests(SystemServiceTestBase):
    def test_pre_t620_route_snapshot_is_a_subset_of_the_current_route_table(self) -> None:
        from app.api_routes import build_route_table

        snapshot = Path("tests/data/t620-route-snapshot.tsv").read_text(encoding="utf-8")
        before = {
            tuple(line.split("\t", 1))
            for line in snapshot.splitlines()
            if line.strip()
        }
        after = {
            (method, pattern)
            for method, pattern, _handler in build_route_table(self.router)
        }
        self.assertTrue(before)
        self.assertEqual(before - after, set())

    def test_daily_mainline_paths_are_additive_and_keep_api_envelopes(self) -> None:
        route_pairs = {
            (method, pattern)
            for method, pattern, _handler in __import__(
                "app.api_routes", fromlist=["build_route_table"]
            ).build_route_table(self.router)
        }
        expected = {
            ("POST", r"^/api/daily-mainline/run$"),
            ("GET", r"^/api/daily-mainline/queue$"),
            ("POST", r"^/api/daily-mainline/queue$"),
            ("GET", r"^/api/daily-mainline/runs$"),
            ("POST", r"^/api/daily-mainline/runs$"),
            (
                "POST",
                r"^/api/daily-mainline/queue/(?P<item_id>[^/]+)/watchlist$",
            ),
            (
                "POST",
                r"^/api/daily-mainline/viewpoints/(?P<item_id>[^/]+)/review$",
            ),
        }
        self.assertEqual(expected - route_pairs, set())
        queue = self.router.dispatch("GET", "/api/daily-mainline/queue", {}, role="分析师")
        self._assert_api_envelope(queue)
        self.assertEqual(queue.data["schema_id"], "daily-mainline-queue-v1")


if __name__ == "__main__":
    unittest.main()
