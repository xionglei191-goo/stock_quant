"""Property tests for the daily mainline spec (project-usability-improvement).

Implementation style follows design §7.1: stdlib ``unittest`` plus fixed-seed
``random.Random`` generators, because the repo intentionally carries no
``hypothesis`` dependency. Each property runs at least ``PROPERTY_ITERATIONS``
iterations and every iteration is wrapped in ``subTest`` carrying the seed and a
scenario digest, so a failure prints a reproducible falsifying example.

Generators are constrained to the real input space of the module under test:
rows are the derived market-disturbance rows produced by the existing scan
(``scripts/daily_market_insight.py`` metric names and thresholds), with discrete
value pools chosen so exact threshold hits and tied ranking strengths occur
frequently.

For the stage machine (``app/service_modules/daily_mainline.py``) the generated
input space is the injected ``stage_runners`` mapping plus an injected virtual
clock: market-row and candidate counts drive ``record_count``, one failure kind
can be injected at any stage position, and per-stage costs combined with the
time budget drive timeout truncation.
"""

from __future__ import annotations

import json
import math
import random
import unittest
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.errors import ValidationError
from app.models import (
    DailyMainlineQueueItem,
    DailyMainlineRun,
    DailyWatchlistEntry,
    LLMTaskRun,
    ResearchAnswer,
)
from app.service_modules.completeness_policy import (
    LAYER_COVERAGE_THRESHOLDS,
    MISSING_FACT_FIELDS_LAYER,
    coverage_denominator,
    next_actions as completeness_next_actions,
    resolve_status,
)
from app.service_modules.daily_mainline import (
    REASON_CODES,
    RUN_STATUSES,
    SKIP_REASON_TIMEOUT,
    STAGE_STATUSES,
    STAGES,
    StageResult,
    build_next_actions,
    build_progress,
    derive_run_status,
    run_stages,
    stage_records,
)
from app.service_modules.daily_mainline_artifact import (
    ARTIFACT_CLASSIFICATION,
    ARTIFACT_OWNER_GROUP,
    ARTIFACT_SCHEMA_ID,
    MAX_TEXT_LENGTH,
    SENSITIVE_KEY_PATTERNS,
    artifact_filename,
    artifact_payload,
)
from app.service_modules.daily_mainline_diligence import (
    BUILTIN_TEMPLATES,
    FACT_FIELD_SOURCE_TYPES,
    PROMPT_VERSION,
    TEMPLATE_PAYLOAD_FIELDS,
    build_viewpoint,
    seed_specs,
    template_ids,
)
from app.service_modules.daily_mainline_scan import (
    ABSOLUTE_TRIGGER_METRICS,
    RANKING_METRICS,
    TRIGGER_RULES,
    build_candidate_pool,
)
from app.service_modules.market_data import (
    FRESHNESS_REASON_CODES,
    freshness_lag,
    market_eod_key,
    market_freshness_annotation,
)
from app.services import SystemService
from app.store import InMemoryStore
from app.utils import to_plain

PROPERTY_ITERATIONS = 100

TRIGGER_METRIC_NAMES: tuple[str, ...] = tuple(metric for metric, _threshold, _reason in TRIGGER_RULES)
REQUIRED_CANDIDATE_FIELDS: tuple[str, ...] = (
    "rank",
    "selection_reason",
    "trigger_metric",
    "trigger_value",
    "as_of_date",
)

# Discrete value pools: exact thresholds (0.07 / 3.0 / 0.08), just-below values,
# negative moves, plus unusable values the scan tolerates (None / text / NaN).
ONE_DAY_RETURN_CHOICES: tuple[Any, ...] = (
    0.0,
    0.015,
    0.0699,
    0.07,
    -0.07,
    0.1007,
    -0.12,
    0.3,
    -0.3,
    None,
    "bad",
    float("nan"),
)
AMOUNT_RATIO_CHOICES: tuple[Any, ...] = (0.5, 1.0, 2.9999, 3.0, 3.5, 9.0, 41.0, None)
VOLUME_RATIO_CHOICES: tuple[Any, ...] = (0.8, 1.0, 2.5, 3.0, 4.0, 6.0)
INTRADAY_RANGE_CHOICES: tuple[Any, ...] = (0.0, 0.03, 0.0799, 0.08, 0.2)

# Small id pool so duplicate securities (and the "keep the strongest row" path)
# show up; the empty id exercises the unusable-row branch.
SECURITY_ID_CHOICES: tuple[str, ...] = (
    "sec_000670",
    "sec_600519",
    "sec_300750",
    "sec_AAPL",
    "sec_NVDA",
    "",
)
MARKET_CHOICES: tuple[str, ...] = ("A", "U", "a", "HK", "", "港股")
# Non-ASCII tickers must survive the pool contract unchanged.
TICKER_CHOICES: tuple[str, ...] = ("000670.SZ", "AAPL", "贵州茅台", "宁德时代", "腾讯控股", "")
AS_OF_DATE_CHOICES: tuple[str, ...] = ("2026-07-22", "2026-07-24", "2026-07-27")
NON_MAPPING_ROWS: tuple[Any, ...] = ("not-a-row", None, 42, ["sec_x"])

CANDIDATE_LIMIT_CHOICES: tuple[int, ...] = (0, 1, 2, 3, 5, 8, 20)
MARKET_QUOTA_CHOICES: tuple[int, ...] = (0, 1, 2, 3, 10)
ROW_COUNT_CHOICES: tuple[int, ...] = (0, 1, 1, 2, 3, 4, 6, 9, 14, 22)

_UNCAPPED = 10**6


def _random_row(rng: random.Random, index: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "security_id": rng.choice(SECURITY_ID_CHOICES),
        "market": rng.choice(MARKET_CHOICES),
        "ticker": rng.choice(TICKER_CHOICES),
        "issuer_id": f"iss_{index}",
        "as_of_date": rng.choice(AS_OF_DATE_CHOICES),
        "one_day_return": rng.choice(ONE_DAY_RETURN_CHOICES),
        "amount_ratio": rng.choice(AMOUNT_RATIO_CHOICES),
        "volume_ratio": rng.choice(VOLUME_RATIO_CHOICES),
        "intraday_range": rng.choice(INTRADAY_RANGE_CHOICES),
    }
    if rng.random() < 0.08:
        row.pop("ticker")
    if rng.random() < 0.06:
        row.pop("as_of_date")
    return row


def _random_scenario(rng: random.Random) -> dict[str, Any]:
    rows: list[Any] = [_random_row(rng, index) for index in range(rng.choice(ROW_COUNT_CHOICES))]
    if rows and rng.random() < 0.2:
        rows.insert(rng.randrange(len(rows)), rng.choice(NON_MAPPING_ROWS))
    return {
        "rows": rows,
        "candidate_limit": rng.choice(CANDIDATE_LIMIT_CHOICES),
        "market_quota": rng.choice(MARKET_QUOTA_CHOICES),
    }


def _row_digest(row: Any) -> str:
    if not isinstance(row, Mapping):
        return f"<non-mapping {row!r}>"
    return "|".join(
        [
            str(row.get("security_id", "")),
            str(row.get("market", "")),
            str(row.get("as_of_date", "-")),
            f"odr={row.get('one_day_return')!r}",
            f"amt={row.get('amount_ratio')!r}",
            f"vol={row.get('volume_ratio')!r}",
            f"rng={row.get('intraday_range')!r}",
        ]
    )


def _scenario_summary(scenario: Mapping[str, Any], pool: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_limit": scenario["candidate_limit"],
        "market_quota": scenario["market_quota"],
        "row_count": len(scenario["rows"]),
        "pool_size": len(pool),
        "pool_ids": [entry.get("security_id") for entry in pool],
        "rows": [_row_digest(row) for row in scenario["rows"]],
    }


def _expected_strength(metrics: Mapping[str, Any]) -> list[float]:
    """Ranking strength recomputed from the entry's published metric values."""

    strength: list[float] = []
    for metric in RANKING_METRICS:
        value = float(metrics[metric])
        strength.append(abs(value) if metric in ABSOLUTE_TRIGGER_METRICS else value)
    return strength


def _source_as_of_dates(rows: Sequence[Any], security_id: str) -> set[str]:
    dates: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("security_id") or "").strip() != security_id:
            continue
        dates.add(str(row.get("as_of_date") or "").strip())
    return dates


class DailyMainlineCandidatePoolPropertyTests(unittest.TestCase):
    def test_property_2_candidate_pool_contract_and_rank_continuity(self) -> None:
        """Feature: project-usability-improvement, Property 2: 候选池条目契约与排名连续性"""

        observed = {
            "empty_pool": 0,
            "single_candidate": 0,
            "tied_strength": 0,
            "limit_truncated": 0,
            "quota_truncated": 0,
            "non_ascii_ticker": 0,
        }

        for iteration in range(PROPERTY_ITERATIONS):
            seed = 2000 + iteration
            rng = random.Random(seed)
            scenario = _random_scenario(rng)
            pool = build_candidate_pool(
                scenario["rows"],
                candidate_limit=scenario["candidate_limit"],
                market_quota=scenario["market_quota"],
            )

            with self.subTest(seed=seed, scenario=_scenario_summary(scenario, pool)):
                for entry in pool:
                    for field in REQUIRED_CANDIDATE_FIELDS:
                        self.assertIn(field, entry)
                    self.assertIsInstance(entry["rank"], int)
                    self.assertIsInstance(entry["selection_reason"], str)
                    self.assertNotEqual(entry["selection_reason"].strip(), "")
                    self.assertIn(entry["trigger_metric"], TRIGGER_METRIC_NAMES)
                    self.assertIsInstance(entry["trigger_value"], float)
                    self.assertTrue(math.isfinite(entry["trigger_value"]))
                    self.assertEqual(entry["trigger_value"], entry["metrics"][entry["trigger_metric"]])
                    self.assertIsInstance(entry["as_of_date"], str)
                    self.assertIn(
                        entry["as_of_date"],
                        _source_as_of_dates(scenario["rows"], entry["security_id"]),
                    )

                ranks = [entry["rank"] for entry in pool]
                self.assertEqual(ranks, list(range(1, len(pool) + 1)))
                self.assertEqual(len(set(ranks)), len(ranks))

                strengths = [_expected_strength(entry["metrics"]) for entry in pool]
                self.assertEqual([entry["trigger_strength"] for entry in pool], strengths)
                for higher, lower in zip(strengths, strengths[1:]):
                    self.assertGreaterEqual(higher, lower)

            uncapped = build_candidate_pool(scenario["rows"], candidate_limit=_UNCAPPED, market_quota=_UNCAPPED)
            uncapped_strengths = [entry["trigger_strength"] for entry in pool]
            market_counts: dict[str, int] = {}
            for entry in pool:
                market_key = str(entry["market"]).upper()
                market_counts[market_key] = market_counts.get(market_key, 0) + 1
            if not pool:
                observed["empty_pool"] += 1
            if len(pool) == 1:
                observed["single_candidate"] += 1
            if any(left == right for left, right in zip(uncapped_strengths, uncapped_strengths[1:])):
                observed["tied_strength"] += 1
            if len(pool) < len(uncapped):
                if len(pool) == scenario["candidate_limit"]:
                    observed["limit_truncated"] += 1
                if any(count >= scenario["market_quota"] for count in market_counts.values()):
                    observed["quota_truncated"] += 1
            if any(not str(entry["ticker"]).isascii() for entry in pool):
                observed["non_ascii_ticker"] += 1

        # Guard against a vacuous generator: the boundary cases the property cares
        # about must actually appear in the sampled scenarios.
        for scenario_name, count in observed.items():
            self.assertGreater(count, 0, f"generator never produced {scenario_name}: {observed}")


def _property_candidate(index: int, *, as_of_date: str = "2026-07-28") -> dict[str, Any]:
    market = "A" if index % 2 == 0 else "U"
    return {
        "security_id": f"sec_property_{index:03d}",
        "issuer_id": f"issuer_property_{index:03d}",
        "ticker": f"P{index:03d}",
        "market": market,
        "rank": index + 1,
        "selection_reason": f"property trigger {index}",
        "trigger_metric": "one_day_return",
        "trigger_value": round(0.07 + index / 10000, 4),
        "as_of_date": as_of_date,
        "metrics": {
            "one_day_return": round(0.07 + index / 10000, 4),
            "amount_ratio": 3.0,
            "volume_ratio": 3.0,
            "intraday_range": 0.08,
        },
    }


def _property_evidence(index: int, source_type: str, *, exists: bool = True) -> dict[str, Any]:
    return {
        "evidence_id": f"evi_property_{index:03d}_{source_type}",
        "document_id": f"doc_property_{index:03d}",
        "source_type": source_type,
        "exists": exists,
        "canonical_text": f"Evidence fixture {index} from {source_type}.",
    }


def _property_llm_output(evidence_ids: Sequence[str], *, extra: Mapping[str, Any] | None = None) -> str:
    payload = {
        "viewpoint_summary": "Evidence-backed property summary.",
        "evidence_ids": list(evidence_ids),
        "fact_claims": [
            {
                "target_field": "revenue",
                "source_type": "official_disclosure",
                "evidence_ids": list(evidence_ids),
            }
        ],
        "usage_boundary": "research_only_paper_only",
        **dict(extra or {}),
    }
    return json.dumps(payload, ensure_ascii=False)


def _property_run(run_id: str, *, status: str = "passed", run_date: str = "2026-07-28") -> DailyMainlineRun:
    stages = [
        {
            "stage": stage,
            "status": "passed",
            "started_at": "2026-07-28T00:00:00+00:00",
            "finished_at": "2026-07-28T00:00:01+00:00",
            "record_count": 1,
            "reason_code": "",
        }
        for stage in STAGES
    ]
    return DailyMainlineRun(
        run_id=run_id,
        run_date=run_date,
        status=status,
        stages=stages,
        candidate_count=1,
        queue_count=1,
        artifact_path=f"artifacts/daily-mainline/{artifact_filename(run_date=run_date, run_id=run_id)}",
        created_at=datetime(2026, 7, 28, 0, 0, tzinfo=timezone.utc),
    )


def _property_queue_item(
    index: int,
    run_id: str,
    *,
    completeness_status: str = "partial",
    evidence_ids: Sequence[str] = (),
) -> DailyMainlineQueueItem:
    candidate = _property_candidate(index)
    return DailyMainlineQueueItem(
        item_id=f"dmitem_property_{index:03d}_{run_id}",
        run_id=run_id,
        security_id=candidate["security_id"],
        issuer_id=candidate["issuer_id"],
        ticker=candidate["ticker"],
        market=candidate["market"],
        rank=candidate["rank"],
        selection_reason=candidate["selection_reason"],
        trigger_metric=candidate["trigger_metric"],
        trigger_value=candidate["trigger_value"],
        as_of_date=candidate["as_of_date"],
        completeness_status=completeness_status,
        evidence_ids=list(evidence_ids),
        viewpoint={
            "summary": "Property viewpoint.",
            "diligence_status": "generated",
            "evidence_ids": list(evidence_ids),
            "usage_boundary": "research_only_paper_only",
        },
    )


class DailyMainlineEvidencePropertyTests(unittest.TestCase):
    def test_property_3_viewpoint_evidence_or_pending_partition(self) -> None:
        """Feature: project-usability-improvement, Property 3: 观点证据绑定或进入待补分区"""

        for iteration in range(PROPERTY_ITERATIONS):
            candidate = _property_candidate(iteration)
            evidence = (
                [_property_evidence(iteration, "official_disclosure")]
                if iteration % 3
                else [_property_evidence(iteration, "official_disclosure", exists=False)]
            )
            cited_ids = [evidence[0]["evidence_id"], f"evi_missing_{iteration}"]
            viewpoint = build_viewpoint(
                candidate=candidate,
                llm_output_text=_property_llm_output(cited_ids),
                evidence_candidates=evidence,
                llm_task_run_id=f"llm_property_{iteration}",
                template_id="tpl_daily_candidate_diligence",
                prompt_version=PROMPT_VERSION,
                model="property-model",
            )
            existing_ids = {
                item["evidence_id"] for item in evidence if item.get("exists", True)
            }
            with self.subTest(iteration=iteration, existing_ids=sorted(existing_ids)):
                self.assertTrue(set(viewpoint["evidence_ids"]).issubset(existing_ids))
                if existing_ids:
                    self.assertGreaterEqual(len(viewpoint["evidence_ids"]), 1)
                    self.assertEqual(viewpoint["partition"], "researchable")
                else:
                    self.assertEqual(viewpoint["evidence_ids"], [])
                    self.assertEqual(viewpoint["diligence_status"], "unsupported")
                    self.assertEqual(viewpoint["partition"], "pending_evidence")

    def test_property_4_research_reports_never_write_fact_fields(self) -> None:
        """Feature: project-usability-improvement, Property 4: 研报只进观点层，不进事实字段"""

        source_sets = (
            ("official_disclosure",),
            ("market_data",),
            ("official_disclosure", "market_data"),
            ("research_report",),
            ("official_disclosure", "research_report"),
        )
        for iteration in range(PROPERTY_ITERATIONS):
            source_types = source_sets[iteration % len(source_sets)]
            evidence = [
                _property_evidence(iteration * 10 + offset, source_type)
                for offset, source_type in enumerate(source_types)
            ]
            viewpoint = build_viewpoint(
                candidate=_property_candidate(iteration),
                llm_output_text=_property_llm_output([item["evidence_id"] for item in evidence]),
                evidence_candidates=evidence,
                llm_task_run_id=f"llm_property_{iteration}",
                template_id="tpl_daily_candidate_diligence",
                prompt_version=PROMPT_VERSION,
                model="property-model",
            )
            with self.subTest(iteration=iteration, source_types=source_types):
                write_sources = {
                    write["source_type"] for write in viewpoint["fact_field_writes"]
                }
                self.assertTrue(write_sources.issubset(set(FACT_FIELD_SOURCE_TYPES)))
                if "research_report" in source_types:
                    self.assertEqual(viewpoint["source_layer"], "viewpoint")
                    self.assertEqual(viewpoint["fact_field_writes"], [])


class DailyMainlineTimeoutPropertyTests(unittest.TestCase):
    def test_property_7_timeout_truncates_and_preserves_completed_results(self) -> None:
        """Feature: project-usability-improvement, Property 7: 超时截断保留已完成结果"""

        for iteration in range(PROPERTY_ITERATIONS):
            rng = random.Random(7000 + iteration)
            cutoff = rng.randrange(len(STAGES) - 1)
            timeout_seconds = rng.randint(1, 30)
            clock = _VirtualClock()
            expected_counts = [rng.randint(1, 50) for _ in STAGES]
            costs = [0.0 for _ in STAGES]
            costs[cutoff] = timeout_seconds + rng.random() + 0.1
            runners: dict[str, Any] = {}
            for index, stage in enumerate(STAGES):
                def _runner(
                    _context: Mapping[str, Any],
                    *,
                    index: int = index,
                    stage: str = stage,
                ) -> StageResult:
                    clock.advance(costs[index])
                    return StageResult(
                        stage=stage,
                        status="passed",
                        started_at="",
                        finished_at="",
                        record_count=expected_counts[index],
                        payload={f"payload_{index}": expected_counts[index]},
                    )

                runners[stage] = _runner
            results = run_stages(
                stage_runners=runners,
                timeout_seconds=timeout_seconds,
                clock=clock.monotonic,
                now_iso=clock.now_iso,
            )
            with self.subTest(iteration=iteration, cutoff=cutoff, timeout=timeout_seconds):
                self.assertEqual(
                    [item.status for item in results[cutoff + 1 :]],
                    ["skipped"] * (len(STAGES) - cutoff - 1),
                )
                self.assertTrue(
                    all(item.reason_code == SKIP_REASON_TIMEOUT for item in results[cutoff + 1 :])
                )
                for index in range(cutoff + 1):
                    self.assertEqual(results[index].status, "passed")
                    self.assertEqual(results[index].record_count, expected_counts[index])
                    self.assertEqual(
                        results[index].payload,
                        {f"payload_{index}": expected_counts[index]},
                    )
                self.assertEqual(derive_run_status(results, queue_count=1), "partial")


class DailyMainlineLineagePropertyTests(unittest.TestCase):
    def test_property_5_llm_lineage_matches_success_count(self) -> None:
        """Feature: project-usability-improvement, Property 5: LLM lineage 与成功调用计数一致"""

        service = SystemService(InMemoryStore())
        service.seed_default_llm_task_templates = lambda **_kwargs: {}  # type: ignore[method-assign]
        service.llm_gateway.describe = lambda: {"configured": True}  # type: ignore[method-assign]
        candidates = [_property_candidate(index) for index in range(PROPERTY_ITERATIONS)]
        successful_calls: list[str] = []

        def _candidate_context(candidate: Mapping[str, Any]):
            index = int(str(candidate["security_id"]).rsplit("_", 1)[1])
            evidence = [_property_evidence(index, "official_disclosure")]
            completeness = {
                "status": "complete",
                "missing_layers": [],
            }
            return {}, completeness, evidence

        def _run_llm(payload: Mapping[str, Any], *, actor: str = "system") -> LLMTaskRun:
            del actor
            index = int(str(payload["variables"]["security_id"]).rsplit("_", 1)[1])
            succeeded = index % 4 != 0
            evidence_id = _property_evidence(index, "official_disclosure")["evidence_id"]
            run = LLMTaskRun(
                run_id=f"llm_property_{index:03d}",
                template_id=str(payload["template_id"]),
                task_type="candidate_diligence",
                status="succeeded" if succeeded else "fallback",
                provider="test",
                model="property-model-v1",
                prompt_version=PROMPT_VERSION,
                output={
                    "summary": _property_llm_output([evidence_id]) if succeeded else ""
                },
                latency_ms=index + 1,
                estimated_input_tokens=100 + index,
                estimated_output_tokens=20 + index,
            )
            service.store.llm_task_runs[run.run_id] = run
            if succeeded:
                successful_calls.append(run.run_id)
            return run

        service._daily_mainline_candidate_context = _candidate_context  # type: ignore[method-assign]
        service.run_llm_task = _run_llm  # type: ignore[method-assign]
        stage = service._daily_mainline_diligence_stage(
            {"candidates": candidates},
            {"diligence_limit": PROPERTY_ITERATIONS, "timeout_seconds": 600},
            actor="property",
            remaining_budget_seconds=lambda: 100_000.0,
        )
        items = stage.payload["diligence_items"]
        succeeded_runs = [
            run for run in service.store.llm_task_runs.values() if run.status == "succeeded"
        ]

        self.assertEqual(len(succeeded_runs), len(successful_calls))
        self.assertEqual(stage.record_count, len(successful_calls))
        for iteration, item in enumerate(items):
            run = service.store.llm_task_runs[item["llm_task_run_id"]]
            with self.subTest(iteration=iteration, status=run.status):
                self.assertTrue(run.template_id)
                self.assertTrue(run.model)
                self.assertTrue(run.prompt_version)
                self.assertGreaterEqual(run.latency_ms, 0)
                self.assertGreaterEqual(run.estimated_input_tokens, 0)
                self.assertGreaterEqual(run.estimated_output_tokens, 0)
                if run.status == "succeeded":
                    viewpoint = item["viewpoint"]
                    self.assertEqual(viewpoint["llm_task_run_id"], run.run_id)
                    self.assertEqual(viewpoint["template_id"], run.template_id)
                    self.assertEqual(viewpoint["model"], run.model)
                    self.assertEqual(viewpoint["prompt_version"], run.prompt_version)
                else:
                    self.assertEqual(item["diligence_status"], "failed")
                    self.assertTrue(item["diligence_reason_code"])

    def test_property_13_llm_failures_keep_candidates_and_reasons(self) -> None:
        """Feature: project-usability-improvement, Property 13: LLM 失败保留候选并记录原因"""

        generated = 0
        failed = 0
        for iteration in range(PROPERTY_ITERATIONS):
            candidate = _property_candidate(iteration)
            evidence = [_property_evidence(iteration, "official_disclosure")]
            should_fail = iteration % 3 == 0
            viewpoint = build_viewpoint(
                candidate=candidate,
                llm_output_text="" if should_fail else _property_llm_output([evidence[0]["evidence_id"]]),
                evidence_candidates=evidence,
                llm_task_run_id=f"llm_property_{iteration}",
                template_id="tpl_daily_candidate_diligence",
                prompt_version=PROMPT_VERSION,
                model="property-model",
            )
            with self.subTest(iteration=iteration, should_fail=should_fail):
                self.assertEqual(viewpoint["security_id"], candidate["security_id"])
                self.assertEqual(viewpoint["partition"], "researchable")
                if should_fail:
                    failed += 1
                    self.assertEqual(viewpoint["diligence_status"], "failed")
                    self.assertTrue(viewpoint["diligence_reason_code"])
                    self.assertEqual(viewpoint["summary"], "")
                else:
                    generated += 1
                    self.assertEqual(viewpoint["diligence_status"], "generated")
                    self.assertEqual(viewpoint["diligence_reason_code"], "")
                    self.assertTrue(viewpoint["summary"])
        self.assertGreater(failed, 0)
        self.assertGreater(generated, 0)


class DailyMainlinePersistencePropertyTests(unittest.TestCase):
    def test_property_8_same_day_runs_and_artifacts_do_not_overwrite(self) -> None:
        """Feature: project-usability-improvement, Property 8: 同日多次运行互不覆盖"""

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for iteration in range(PROPERTY_ITERATIONS):
                run_count = 2 + iteration % 3
                store = InMemoryStore()
                run_ids = [f"dmrun_property_{iteration:03d}_{index}" for index in range(run_count)]
                paths: list[Path] = []
                for run_id in run_ids:
                    run = _property_run(run_id)
                    store.daily_mainline_runs[run_id] = run
                    item = _property_queue_item(iteration, run_id)
                    store.daily_mainline_queue_items[item.item_id] = item
                    path = root / artifact_filename(run_date=run.run_date, run_id=run_id)
                    path.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
                    paths.append(path)
                with self.subTest(iteration=iteration, run_ids=run_ids):
                    self.assertEqual(len(set(run_ids)), run_count)
                    self.assertEqual(len(set(paths)), run_count)
                    for run_id, path in zip(run_ids, paths):
                        self.assertEqual(store.daily_mainline_runs[run_id].run_id, run_id)
                        self.assertTrue(
                            any(item.run_id == run_id for item in store.daily_mainline_queue_items.values())
                        )
                        self.assertTrue(path.exists())
                        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["run_id"], run_id)

    def test_property_9_watchlist_round_trip_preserves_source_fields(self) -> None:
        """Feature: project-usability-improvement, Property 9: 加入关注池往返保真"""

        service = SystemService(InMemoryStore())
        service.import_company_watchlist = lambda *_args, **_kwargs: {"status": "ok"}  # type: ignore[method-assign]
        for iteration in range(PROPERTY_ITERATIONS):
            run_id = f"dmrun_watch_{iteration:03d}"
            item = _property_queue_item(iteration, run_id)
            service.store.daily_mainline_queue_items[item.item_id] = item
            result = service.add_daily_queue_item_to_watchlist(
                {"item_id": item.item_id},
                actor=f"analyst_{iteration}",
            )
            entry_id = result["entry"]["entry_id"]
            entry = service.store.daily_watchlist_entries[entry_id]
            with self.subTest(iteration=iteration, entry_id=entry_id):
                self.assertEqual(entry.security_id, item.security_id)
                self.assertEqual(entry.run_id, item.run_id)
                self.assertEqual(entry.item_id, item.item_id)
                self.assertEqual(entry.selection_reason, item.selection_reason)
                self.assertIsNotNone(entry.joined_at)

    def test_property_10_queue_read_model_contract(self) -> None:
        """Feature: project-usability-improvement, Property 10: 清单读模型呈现契约"""

        service = SystemService(InMemoryStore())
        for iteration in range(PROPERTY_ITERATIONS):
            run_id = f"dmrun_queue_{iteration:03d}"
            run = _property_run(run_id)
            item = _property_queue_item(
                iteration,
                run_id,
                evidence_ids=[f"evi_queue_{iteration:03d}"],
            )
            service.store.daily_mainline_runs[run_id] = run
            service.store.daily_mainline_queue_items[item.item_id] = item
            payload = service.daily_mainline_queue_payload({"run_id": run_id})
            projected = payload["items"][0]
            with self.subTest(iteration=iteration, run_id=run_id):
                self.assertTrue(payload["as_of_date"])
                self.assertTrue(payload["generated_at"])
                for field in ("rank", "selection_reason", "evidence_ref", "watchlist_action"):
                    self.assertIn(field, projected)
                self.assertIn("endpoint", projected["watchlist_action"])
                self.assertEqual(projected["watchlist_action"]["method"], "POST")
                self.assertFalse(payload["live_execution_allowed"])
                self.assertTrue(payload["paper_only"])

    def test_property_12_answer_and_review_status_round_trip(self) -> None:
        """Feature: project-usability-improvement, Property 12: 研究结论与复核状态往返"""

        service = SystemService(InMemoryStore())
        statuses = ("pending", "accepted", "rejected")
        answer_statuses = {"pending": "pending", "accepted": "approved", "rejected": "rejected"}
        for iteration in range(PROPERTY_ITERATIONS):
            run_id = f"dmrun_review_{iteration:03d}"
            evidence_id = f"evi_review_{iteration:03d}"
            item = _property_queue_item(iteration, run_id, evidence_ids=[evidence_id])
            item.research_answer_id = f"ans_property_{iteration:03d}"
            answer = ResearchAnswer(
                answer_id=item.research_answer_id,
                question=f"daily_mainline:{item.as_of_date}:{item.security_id}",
                issuer_id=item.issuer_id,
                evidence_ids=[evidence_id],
                human_review_status="pending",
            )
            service.store.daily_mainline_queue_items[item.item_id] = item
            service.store.research_answers[answer.answer_id] = answer
            status = statuses[iteration % len(statuses)]
            service.review_daily_mainline_viewpoint(
                {"item_id": item.item_id, "status": status},
                actor="property-reviewer",
            )
            with self.subTest(iteration=iteration, status=status):
                stored_item = service.store.daily_mainline_queue_items[item.item_id]
                stored_answer = service.store.research_answers[answer.answer_id]
                self.assertEqual(stored_item.review_status, status)
                self.assertEqual(stored_answer.human_review_status, answer_statuses[status])
                self.assertIn(item.security_id, stored_answer.question)
                self.assertEqual(stored_answer.evidence_ids, [evidence_id])
                with self.assertRaises(ValidationError):
                    service.review_daily_mainline_viewpoint(
                        {"item_id": item.item_id, "status": f"invalid_{iteration}"},
                        actor="property-reviewer",
                    )
                self.assertEqual(stored_item.review_status, status)


class DailyMainlineTemplateAndRedactionPropertyTests(unittest.TestCase):
    def test_property_11_builtin_template_seed_is_idempotent(self) -> None:
        """Feature: project-usability-improvement, Property 11: 内置模板幂等写入"""

        ids = list(template_ids())
        for iteration in range(PROPERTY_ITERATIONS):
            rng = random.Random(11000 + iteration)
            existing = {template_id for template_id in ids if rng.random() < 0.5}
            once = {template_id: {"template_id": template_id} for template_id in existing}
            for spec in seed_specs(once):
                once[spec["template_id"]] = spec
            repeated = {template_id: {"template_id": template_id} for template_id in existing}
            repeat_count = 2 + iteration % 4
            for _ in range(repeat_count):
                for spec in seed_specs(repeated):
                    repeated[spec["template_id"]] = spec
            with self.subTest(iteration=iteration, existing=sorted(existing)):
                self.assertEqual(set(once), set(ids))
                self.assertEqual(set(repeated), set(ids))
                for template_id in ids:
                    once_version = once[template_id].get("prompt_version", PROMPT_VERSION)
                    repeated_version = repeated[template_id].get("prompt_version", PROMPT_VERSION)
                    self.assertEqual(once_version, repeated_version)
                    self.assertTrue(repeated_version)

    def test_property_14_sensitive_values_and_raw_responses_do_not_persist(self) -> None:
        """Feature: project-usability-improvement, Property 14: 凭据与完整上游响应不落盘"""

        for iteration in range(PROPERTY_ITERATIONS):
            secret = f"secret-property-{iteration:03d}"
            signed_url = f"https://example.test/file?X-Amz-Signature={secret}"
            raw_response = f"raw-response-{secret}-" + ("x" * (MAX_TEXT_LENGTH + 100))
            evidence = [_property_evidence(iteration, "official_disclosure")]
            viewpoint = build_viewpoint(
                candidate=_property_candidate(iteration),
                llm_output_text=_property_llm_output(
                    [evidence[0]["evidence_id"]],
                    extra={
                        "api_key": secret,
                        "x-amz-signature-url": signed_url,
                        "raw_response": raw_response,
                    },
                ),
                evidence_candidates=evidence,
                llm_task_run_id=f"llm_redaction_{iteration}",
                template_id="tpl_daily_candidate_diligence",
                prompt_version=PROMPT_VERSION,
                model="property-model",
            )
            run = _property_run(f"dmrun_redaction_{iteration:03d}")
            item = _property_queue_item(
                iteration,
                run.run_id,
                evidence_ids=[evidence[0]["evidence_id"]],
            )
            item.viewpoint = viewpoint
            watchlist = DailyWatchlistEntry(
                entry_id=f"dmwatch_property_{iteration:03d}",
                security_id=item.security_id,
                run_id=run.run_id,
                item_id=item.item_id,
                selection_reason=item.selection_reason,
            )
            artifact = artifact_payload(
                run={
                    **to_plain(run),
                    "api_key": secret,
                    "x-amz-signature-url": signed_url,
                    "raw_response": raw_response,
                },
                items=[
                    {
                        **to_plain(item),
                        "authorization": secret,
                        "raw_response": raw_response,
                    }
                ],
                producer_command="python3 scripts/daily_mainline_run.py",
                environment="local",
                generated_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
            )
            persisted = json.dumps(
                {
                    "templates": seed_specs(()),
                    "queue_item": to_plain(item),
                    "watchlist": to_plain(watchlist),
                    "artifact": artifact,
                },
                ensure_ascii=False,
            )
            with self.subTest(iteration=iteration):
                self.assertNotIn(secret, persisted)
                self.assertNotIn(signed_url, persisted)
                self.assertNotIn(raw_response, persisted)
                self.assertTrue(all(spec.get("prompt_version") for spec in seed_specs(())))
                self.assertTrue(
                    all(set(spec).issubset(set(TEMPLATE_PAYLOAD_FIELDS)) for spec in seed_specs(()))
                )
                self.assertTrue(all(template["prompt_version"] for template in BUILTIN_TEMPLATES))
                self.assertTrue(all(pattern not in persisted.lower() for pattern in SENSITIVE_KEY_PATTERNS))


class CompletenessPropertyTests(unittest.TestCase):
    def test_property_15_completeness_equivalence_rule(self) -> None:
        """Feature: project-usability-improvement, Property 15: 完整度判定等价规则"""

        coverage_keys = list(LAYER_COVERAGE_THRESHOLDS)
        for iteration in range(PROPERTY_ITERATIONS):
            rng = random.Random(15000 + iteration)
            blocking = ["documents"] if rng.random() < 0.2 else []
            warning = ["relationships"] if rng.random() < 0.2 else []
            missing_fields = ["revenue"] if rng.random() < 0.35 else []
            coverage = {
                key: rng.choice((0.0, 0.8999, threshold, 0.95, 1.0))
                for key, threshold in LAYER_COVERAGE_THRESHOLDS.items()
            }
            verdict = resolve_status(
                profile_available=True,
                blocking_gaps=blocking,
                warning_gaps=warning,
                missing_fact_fields=missing_fields,
                coverage_scores=coverage,
            )
            unmet = [
                key.removesuffix("_score")
                for key in coverage_keys
                if coverage[key] < LAYER_COVERAGE_THRESHOLDS[key]
            ]
            expected_missing = list(dict.fromkeys([
                *blocking,
                *warning,
                *unmet,
                *([MISSING_FACT_FIELDS_LAYER] if missing_fields else []),
            ]))
            is_complete = not blocking and not warning and not missing_fields and not unmet
            with self.subTest(iteration=iteration, coverage=coverage):
                self.assertEqual(verdict["status"], "complete" if is_complete else "partial")
                self.assertEqual(verdict["is_complete"], is_complete)
                self.assertEqual(verdict["missing_layers"], expected_missing)

    def test_property_16_cross_response_completeness_matches_policy(self) -> None:
        """Feature: project-usability-improvement, Property 16: 跨响应完整度状态一致"""

        service = SystemService(InMemoryStore())
        for iteration in range(PROPERTY_ITERATIONS):
            coverage = {
                key: 1.0 if (iteration + offset) % 4 else 0.5
                for offset, key in enumerate(LAYER_COVERAGE_THRESHOLDS)
            }
            verdict = resolve_status(
                profile_available=iteration % 7 != 0,
                blocking_gaps=["documents"] if iteration % 11 == 0 else [],
                warning_gaps=[],
                missing_fact_fields=["revenue"] if iteration % 5 == 0 else [],
                coverage_scores=coverage,
            )
            candidate = _property_candidate(iteration)
            stage = service._daily_mainline_queue_stage(
                {
                    "diligence_items": [
                        {
                            "candidate": candidate,
                            "completeness": verdict,
                            "viewpoint": {},
                            "partition": "researchable",
                            "diligence_status": "skipped",
                            "diligence_reason_code": "",
                            "llm_task_run_id": "",
                            "template_id": "",
                        }
                    ]
                },
                run_id=f"dmrun_completeness_{iteration:03d}",
                actor="property",
            )
            item_id = stage.payload["item_ids"][0]
            with self.subTest(iteration=iteration, verdict=verdict):
                self.assertEqual(
                    service.store.daily_mainline_queue_items[item_id].completeness_status,
                    verdict["status"],
                )

    def test_property_17_non_complete_has_actionable_next_steps(self) -> None:
        """Feature: project-usability-improvement, Property 17: 非完整状态必有可执行下一步"""

        for iteration in range(PROPERTY_ITERATIONS):
            status = "not_found" if iteration % 4 == 0 else "partial"
            layers = [] if iteration % 3 == 0 else [f"missing_layer_{iteration % 7}"]
            fields = [] if iteration % 5 else ["revenue", "website_url"]
            actions = completeness_next_actions(
                status=status,
                missing_layers=layers,
                missing_fact_fields=fields,
            )
            with self.subTest(iteration=iteration, status=status, layers=layers, fields=fields):
                self.assertGreaterEqual(len(actions), 1)
                for action in actions:
                    self.assertTrue(action["target_field"])
                    self.assertTrue(action["source_type"])
                    self.assertTrue(action["command"] or action["endpoint"])

    def test_property_18_coverage_denominator_arithmetic(self) -> None:
        """Feature: project-usability-improvement, Property 18: 覆盖度分母自述与算术一致"""

        for iteration in range(PROPERTY_ITERATIONS):
            rng = random.Random(18000 + iteration)
            total = rng.randint(-5, 150)
            filled = rng.randint(-10, 180)
            result = coverage_denominator(total_fields=total, filled_fields=filled)
            expected_total = max(0, total)
            expected_filled = min(max(0, filled), expected_total)
            expected_score = round(expected_filled / expected_total, 4) if expected_total else 0.0
            with self.subTest(iteration=iteration, total=total, filled=filled):
                self.assertEqual(result["total_fields"], expected_total)
                self.assertEqual(result["filled_fields"], expected_filled)
                self.assertEqual(result["score"], expected_score)


class MarketFreshnessPropertyTests(unittest.TestCase):
    def test_property_19_market_key_and_lag_annotation_are_consistent(self) -> None:
        """Feature: project-usability-improvement, Property 19: 行情新鲜度同源与滞后标注"""

        base = datetime(2026, 7, 28, tzinfo=timezone.utc)
        markets = ("A", "U", "H", "")
        for iteration in range(PROPERTY_ITERATIONS):
            market = markets[iteration % len(markets)]
            lag_days = iteration % 31
            company_date = (base - timedelta(days=lag_days)).date().isoformat()
            market_date = base.date().isoformat()
            key = market_eod_key(market)
            annotation = market_freshness_annotation(
                market=market,
                company_as_of_date=company_date,
                market_eod_date=market_date,
            )
            direct = freshness_lag(
                company_as_of_date=company_date,
                market_eod_date=market_date,
            )
            with self.subTest(iteration=iteration, market=market, lag_days=lag_days):
                self.assertEqual(
                    {field: annotation[field] for field in ("market", "source_id", "data_type")},
                    key,
                )
                self.assertEqual(annotation["lag_days"], lag_days)
                self.assertEqual(annotation["is_lagging"], lag_days > 0)
                self.assertEqual(annotation["lag_days"], direct["lag_days"])
                if lag_days:
                    self.assertIn(annotation["reason_code"], FRESHNESS_REASON_CODES)
                else:
                    self.assertEqual(annotation["reason_code"], "")


class DailyMainlineArtifactAndBoundaryPropertyTests(unittest.TestCase):
    def test_property_20_artifact_contract_is_local_only(self) -> None:
        """Feature: project-usability-improvement, Property 20: 证据产物契约"""

        for iteration in range(PROPERTY_ITERATIONS):
            run = _property_run(f"dmrun_artifact_{iteration:03d}")
            generated_at = datetime(2026, 7, 28, 1, iteration % 60, tzinfo=timezone.utc)
            payload = artifact_payload(
                run=to_plain(run),
                items=[to_plain(_property_queue_item(iteration, run.run_id))],
                producer_command="python3 scripts/daily_mainline_run.py --as-of-date 2026-07-28",
                environment=f"local-property-{iteration % 3}",
                generated_at=generated_at,
            )
            parsed = datetime.fromisoformat(payload["generated_at"])
            with self.subTest(iteration=iteration, run_id=run.run_id):
                self.assertEqual(payload["schema_id"], ARTIFACT_SCHEMA_ID)
                self.assertEqual(payload["run_id"], run.run_id)
                self.assertEqual(
                    [stage["stage"] for stage in payload["stages"]],
                    list(STAGES),
                )
                self.assertTrue(payload["producer_command"])
                self.assertTrue(payload["environment"])
                self.assertEqual(payload["owner_group"], ARTIFACT_OWNER_GROUP)
                self.assertIsNotNone(parsed.utcoffset())
                self.assertEqual(parsed.utcoffset(), timedelta(0))
                self.assertFalse(payload["contains_sensitive_data"])
                self.assertEqual(payload["classification"], ARTIFACT_CLASSIFICATION)
                self.assertFalse(payload["production_release_gate_eligible"])

    def test_property_21_paper_only_boundary_is_invariant(self) -> None:
        """Feature: project-usability-improvement, Property 21: 边界声明不变量"""

        service = SystemService(InMemoryStore())
        for iteration in range(PROPERTY_ITERATIONS):
            run_id = f"dmrun_boundary_{iteration:03d}"
            run = _property_run(run_id)
            item = _property_queue_item(iteration, run_id)
            service.store.daily_mainline_runs[run_id] = run
            service.store.daily_mainline_queue_items[item.item_id] = item
            queue = service.daily_mainline_queue_payload({"run_id": run_id})
            artifact = artifact_payload(
                run=to_plain(run),
                items=[to_plain(item)],
                producer_command="python3 scripts/daily_mainline_run.py",
                environment="local",
                generated_at=run.created_at,
            )
            nodes = (to_plain(run), queue, artifact)
            with self.subTest(iteration=iteration, run_id=run_id):
                for node in nodes:
                    self.assertFalse(node["live_execution_allowed"])
                    self.assertTrue(node["paper_only"])
                self.assertNotIn("broker_order", json.dumps(nodes, ensure_ascii=False))
                self.assertNotIn("live_trade", json.dumps(nodes, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Property 1: 阶段序列、阶段记录与进度投影一致（design §6 Property 1）
# ---------------------------------------------------------------------------

STAGE_RECORD_FIELDS: tuple[str, ...] = (
    "stage",
    "status",
    "started_at",
    "finished_at",
    "record_count",
)

# 进度投影口径（design §4.1 / 需求 2.6）：只有产出了结果的阶段算已完成，
# failed / skipped 不计入。测试侧独立写出该定义，不复用实现常量。
COMPLETED_STAGE_STATUSES: frozenset[str] = frozenset({"passed", "partial"})

# 阶段耗时（秒）：0.0 覆盖 started_at == finished_at 的边界，700.0 覆盖单个阶段
# 吃掉全部时间预算的情形。
STAGE_COST_CHOICES: tuple[float, ...] = (0.0, 0.0, 0.25, 1.5, 7.0, 120.0, 700.0)
# 时间预算：0 与真实时钟漂移组合可产生“首阶段即超时”，100000 保证不截断。
TIMEOUT_SECONDS_CHOICES: tuple[int, ...] = (0, 1, 5, 10, 600, 1200, 100000)
# 时钟读取漂移：真实 time.monotonic() 每次读取都会前进，0.0 覆盖冻结时钟。
CLOCK_READ_DRIFT_CHOICES: tuple[float, ...] = (0.0, 0.0, 0.001, 0.25)

# 行情数据规模与候选数量：0 覆盖零候选，1 覆盖单候选。
MARKET_ROW_COUNT_CHOICES: tuple[int, ...] = (0, 1, 12, 240, 1200)
CANDIDATE_COUNT_CHOICES: tuple[int, ...] = (0, 0, 1, 1, 2, 8, 20)
DILIGENCE_LIMIT_CHOICES: tuple[int, ...] = (1, 4, 8)
# 阶段 runner 上报的不可用 record_count，验证记录数被归一为非负整数。
RECORD_COUNT_NOISE_CHOICES: tuple[Any, ...] = (-3, None, "5", 3.9, "bad")

# 原因码取自 design §5 错误处理表；`brand_new_unmapped_code` 覆盖未登记原因码。
PARTIAL_REASON_CHOICES: tuple[str, ...] = (
    "market_data_stale",
    "llm_gateway_unconfigured",
    "llm_call_failed",
    "llm_timeout",
    "diligence_budget_exhausted",
    "completeness_unavailable",
)
FAILED_REASON_CHOICES: tuple[str, ...] = (
    "market_data_unavailable",
    "store_write_failed",
    "brand_new_unmapped_code",
)

# 失败注入方式：显式 failed、runner 抛异常、返回非 StageResult、status 越界、
# 以及 facade 漏接线导致的 runner 缺失。
FAILURE_MODES: tuple[str, ...] = (
    "failed",
    "raise",
    "invalid_result",
    "bad_status",
    "missing_runner",
)
FAILURE_POSITION_CHOICES: tuple[int | None, ...] = (None, 0, 1, 2, 3)

_ISO_BASE = datetime(2026, 7, 28, 2, 11, 3, tzinfo=timezone.utc)


class _VirtualClock:
    """注入式虚拟时钟。

    `monotonic` 每次读取前进 `read_drift` 秒（真实 `time.monotonic()` 亦如此），
    阶段实现通过 `advance` 消耗耗时；`now_iso` 从同一虚拟时刻派生 UTC ISO 8601
    字符串，因此时间戳单调不减且不读系统时间。
    """

    def __init__(self, *, read_drift: float = 0.0) -> None:
        self._now = 0.0
        self._read_drift = float(read_drift)

    def monotonic(self) -> float:
        current = self._now
        self._now += self._read_drift
        return current

    def advance(self, seconds: float) -> None:
        self._now += max(0.0, float(seconds))

    def now_iso(self) -> str:
        return (_ISO_BASE + timedelta(seconds=self._now)).isoformat()


def _stage_plan(
    rng: random.Random,
    *,
    market_row_count: int,
    candidate_count: int,
    diligence_limit: int,
) -> list[dict[str, Any]]:
    """按阶段生成 runner 行为计划（记录数沿编排链收敛，与真实数据流一致）。"""

    counts = {
        STAGES[0]: market_row_count,
        STAGES[1]: candidate_count,
        STAGES[2]: min(candidate_count, diligence_limit),
        STAGES[3]: candidate_count,
    }
    plan: list[dict[str, Any]] = []
    for stage in STAGES:
        if candidate_count == 0 and stage in (STAGES[2], STAGES[3]):
            # design §5：no_candidates 时尽调与清单阶段由 facade 上报 skipped。
            mode, reason_code = "skipped", "no_candidates"
        elif candidate_count == 0 and stage == STAGES[1]:
            mode, reason_code = "passed", "no_candidates"
        elif rng.random() < 0.25:
            mode, reason_code = "partial", rng.choice(PARTIAL_REASON_CHOICES)
        else:
            mode, reason_code = "passed", ""
        plan.append(
            {
                "stage": stage,
                "mode": mode,
                "reason_code": reason_code,
                "record_count": counts[stage],
                "cost_seconds": rng.choice(STAGE_COST_CHOICES),
            }
        )
    return plan


def _random_stage_scenario(rng: random.Random) -> dict[str, Any]:
    market_row_count = rng.choice(MARKET_ROW_COUNT_CHOICES)
    candidate_count = min(rng.choice(CANDIDATE_COUNT_CHOICES), market_row_count)
    diligence_limit = rng.choice(DILIGENCE_LIMIT_CHOICES)
    plan = _stage_plan(
        rng,
        market_row_count=market_row_count,
        candidate_count=candidate_count,
        diligence_limit=diligence_limit,
    )

    failure_position = rng.choice(FAILURE_POSITION_CHOICES)
    failure_mode = ""
    if failure_position is not None:
        failure_mode = rng.choice(FAILURE_MODES)
        plan[failure_position]["mode"] = failure_mode
        plan[failure_position]["reason_code"] = (
            rng.choice(FAILED_REASON_CHOICES) if failure_mode == "failed" else ""
        )

    noise_index: int | None = None
    if rng.random() < 0.25:
        noise_index = rng.randrange(len(STAGES))
        plan[noise_index]["record_count"] = rng.choice(RECORD_COUNT_NOISE_CHOICES)

    return {
        "plan": plan,
        "market_row_count": market_row_count,
        "candidate_count": candidate_count,
        "diligence_limit": diligence_limit,
        "failure_position": failure_position,
        "failure_mode": failure_mode,
        "noise_index": noise_index,
        "timeout_seconds": rng.choice(TIMEOUT_SECONDS_CHOICES),
        "clock_read_drift": rng.choice(CLOCK_READ_DRIFT_CHOICES),
    }


def _stage_runner(entry: Mapping[str, Any], *, clock: _VirtualClock):
    def _run(_context: Mapping[str, Any]) -> Any:
        clock.advance(entry["cost_seconds"])
        mode = entry["mode"]
        if mode == "raise":
            raise RuntimeError(f"injected stage failure at {entry['stage']}")
        if mode == "invalid_result":
            return {"stage": entry["stage"], "status": "passed"}
        status = "definitely-not-a-status" if mode == "bad_status" else mode
        return StageResult(
            # 阶段名与时间戳一律由编排器覆盖，runner 上报值不应影响输出契约。
            stage="ignored-by-orchestrator",
            status=status,
            started_at="ignored",
            finished_at="ignored",
            record_count=entry["record_count"],
            reason_code=entry["reason_code"],
            payload={"stage": entry["stage"], "record_count": entry["record_count"]},
        )

    return _run


def _stage_runners(
    plan: Sequence[Mapping[str, Any]], *, clock: _VirtualClock
) -> dict[str, Any]:
    return {
        entry["stage"]: _stage_runner(entry, clock=clock)
        for entry in plan
        if entry["mode"] != "missing_runner"
    }


def _stage_scenario_summary(
    scenario: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "timeout_seconds": scenario["timeout_seconds"],
        "clock_read_drift": scenario["clock_read_drift"],
        "market_row_count": scenario["market_row_count"],
        "candidate_count": scenario["candidate_count"],
        "diligence_limit": scenario["diligence_limit"],
        "failure": f"{scenario['failure_position']}:{scenario['failure_mode'] or '-'}",
        "noise_index": scenario["noise_index"],
        "plan": [
            f"{entry['stage']}|{entry['mode']}|{entry['reason_code'] or '-'}"
            f"|n={entry['record_count']!r}|cost={entry['cost_seconds']}"
            for entry in scenario["plan"]
        ],
        "observed": [
            f"{record['stage']}|{record['status']}|{record['reason_code'] or '-'}"
            f"|n={record['record_count']}"
            for record in records
        ],
        "progress": dict(progress),
    }


class DailyMainlineStageMachinePropertyTests(unittest.TestCase):
    def test_property_1_stage_sequence_records_and_progress(self) -> None:
        """Feature: project-usability-improvement, Property 1: 阶段序列、阶段记录与进度投影一致"""

        observed = {
            "zero_candidates": 0,
            "single_candidate": 0,
            "clean_run": 0,
            "failure_at_stage_0": 0,
            "failure_at_stage_1": 0,
            "failure_at_stage_2": 0,
            "failure_at_stage_3": 0,
            "failed_status": 0,
            "partial_status": 0,
            "skipped_status": 0,
            "timeout_truncated": 0,
            "first_stage_timeout": 0,
            "coerced_record_count": 0,
            "zero_duration_executed_stage": 0,
            "all_stages_completed": 0,
            "incomplete_run_has_current_stage": 0,
        }
        for mode in FAILURE_MODES:
            observed[f"failure_mode_{mode}"] = 0

        for iteration in range(PROPERTY_ITERATIONS):
            seed = 1000 + iteration
            rng = random.Random(seed)
            scenario = _random_stage_scenario(rng)
            clock = _VirtualClock(read_drift=scenario["clock_read_drift"])

            results = run_stages(
                stage_runners=_stage_runners(scenario["plan"], clock=clock),
                timeout_seconds=scenario["timeout_seconds"],
                clock=clock.monotonic,
                now_iso=clock.now_iso,
            )
            records = stage_records(results)
            progress = build_progress(results)

            with self.subTest(
                seed=seed,
                scenario=_stage_scenario_summary(scenario, records, progress),
            ):
                # 阶段序列严格等于 STAGES 的前缀且顺序一致（需求 1.2）。
                sequence = [record["stage"] for record in records]
                self.assertLessEqual(len(sequence), len(STAGES))
                self.assertEqual(sequence, list(STAGES)[: len(sequence)])
                # design §4.1：返回与 STAGES 等长的记录列表，被跳过的阶段同样上报。
                self.assertEqual(len(sequence), len(STAGES))

                # 阶段记录字段完备、取值域收敛（需求 1.3）。
                previous_finished: datetime | None = None
                for record in records:
                    for field in STAGE_RECORD_FIELDS:
                        self.assertIn(field, record)
                    self.assertIn(record["status"], STAGE_STATUSES)
                    self.assertIsInstance(record["record_count"], int)
                    self.assertGreaterEqual(record["record_count"], 0)
                    self.assertIsInstance(record["started_at"], str)
                    self.assertIsInstance(record["finished_at"], str)
                    self.assertNotEqual(record["started_at"], "")
                    self.assertNotEqual(record["finished_at"], "")
                    started_at = datetime.fromisoformat(record["started_at"])
                    finished_at = datetime.fromisoformat(record["finished_at"])
                    self.assertGreaterEqual(finished_at, started_at)
                    if previous_finished is not None:
                        # 固定顺序执行的推论：阶段时间戳跨阶段单调不减。
                        self.assertGreaterEqual(started_at, previous_finished)
                    previous_finished = finished_at

                # 进度投影与阶段记录一致（需求 2.6）。
                completed = [
                    record["stage"]
                    for record in records
                    if record["status"] in COMPLETED_STAGE_STATUSES
                ]
                expected_current = next(
                    (stage for stage in STAGES if stage not in completed), ""
                )
                self.assertEqual(
                    sorted(progress), ["completed_count", "current_stage", "total_count"]
                )
                self.assertEqual(progress["total_count"], len(STAGES))
                self.assertEqual(progress["completed_count"], len(completed))
                self.assertEqual(progress["current_stage"], expected_current)
                self.assertIn(progress["current_stage"], ("", *STAGES))
                self.assertEqual(
                    progress["current_stage"] == "",
                    progress["completed_count"] == progress["total_count"],
                )

            statuses = [record["status"] for record in records]
            reason_codes = [record["reason_code"] for record in records]
            if scenario["candidate_count"] == 0:
                observed["zero_candidates"] += 1
            if scenario["candidate_count"] == 1:
                observed["single_candidate"] += 1
            if scenario["failure_position"] is None:
                observed["clean_run"] += 1
            else:
                observed[f"failure_at_stage_{scenario['failure_position']}"] += 1
                observed[f"failure_mode_{scenario['failure_mode']}"] += 1
            if "failed" in statuses:
                observed["failed_status"] += 1
            if "partial" in statuses:
                observed["partial_status"] += 1
            if "skipped" in statuses:
                observed["skipped_status"] += 1
            if SKIP_REASON_TIMEOUT in reason_codes:
                observed["timeout_truncated"] += 1
            if reason_codes[0] == SKIP_REASON_TIMEOUT:
                observed["first_stage_timeout"] += 1
            noise_index = scenario["noise_index"]
            if noise_index is not None and statuses[noise_index] in COMPLETED_STAGE_STATUSES:
                observed["coerced_record_count"] += 1
            if any(
                record["started_at"] == record["finished_at"]
                and record["status"] != "skipped"
                for record in records
            ):
                observed["zero_duration_executed_stage"] += 1
            if progress["current_stage"]:
                observed["incomplete_run_has_current_stage"] += 1
            else:
                observed["all_stages_completed"] += 1

        # Guard against a vacuous generator: the boundary cases the property cares
        # about must actually appear in the sampled scenarios.
        for scenario_name, count in observed.items():
            self.assertGreater(count, 0, f"generator never produced {scenario_name}: {observed}")


# ---------------------------------------------------------------------------
# Property 6: 状态与可执行下一步一致（design §6 Property 6）
# ---------------------------------------------------------------------------

# 下一步动作的必备字段（需求 1.9、1.10、2.7）。
NEXT_ACTION_FIELDS: tuple[str, ...] = ("action", "stage", "reason_code", "command", "endpoint")

# design §5 表中 `no_candidates` 行：清单为空是正常结果而非异常中断，因此该原因码的
# skipped 不把整体状态压成 partial（该场景整体状态为 empty）。测试侧独立写出该口径，
# 不复用实现常量。
EMPTY_QUEUE_SKIP_REASON_CODES: frozenset[str] = frozenset({"no_candidates"})

# 定向覆盖 design §5 的四类整体状态与四个失败注入位置；`random` 保留 Property 1 的
# 无偏输入空间（失败位置、耗时序列、记录数噪声由 `_random_stage_scenario` 随机产生）。
STATUS_SHAPES: tuple[str, ...] = (
    "random",
    "clean_passed",
    "empty_queue",
    "timeout_truncated",
    "failed_at_0",
    "failed_at_1",
    "failed_at_2",
    "failed_at_3",
)

POSITIVE_CANDIDATE_COUNT_CHOICES: tuple[int, ...] = tuple(
    count for count in CANDIDATE_COUNT_CHOICES if count > 0
)
SHORT_TIMEOUT_SECONDS_CHOICES: tuple[int, ...] = tuple(
    seconds for seconds in TIMEOUT_SECONDS_CHOICES if seconds <= 10
)
# `None` 表示按阶段记录派生清单条目数（facade 口径）；其余取值覆盖“清单非空”与
# “非法 / 负值按 0 处理”的 queue_count 入参。
QUEUE_COUNT_OVERRIDE_CHOICES: tuple[Any, ...] = (None, None, None, None, 7, 0, -4, "3")

# 足够大的预算：定向 shape 下不产生超时截断，让状态由失败注入或清单条目数决定。
_UNBOUNDED_TIMEOUT_SECONDS = 100_000
# 单阶段吃掉全部预算的耗时，用于稳定触发超时截断。
_TIMEOUT_STAGE_COST_SECONDS = 700.0


def _clear_partial_reports(plan: Sequence[dict[str, Any]]) -> None:
    """把计划中的 partial 上报改为 passed，让整体状态可以收敛到 passed / empty。"""

    for entry in plan:
        if entry["mode"] == "partial":
            entry["mode"] = "passed"
            entry["reason_code"] = ""


def _status_scenario(rng: random.Random, shape: str) -> dict[str, Any]:
    """在 Property 1 生成器之上按 `shape` 定向覆盖 design §5 的整体状态取值。

    `random` 直接复用 `_random_stage_scenario`；其余 shape 用同一个 `_stage_plan`
    重建计划后只改动与该 shape 相关的维度（候选数、失败注入位置、耗时与预算），
    其他维度（记录数、时钟漂移、尽调上限）仍随机。
    """

    scenario = _random_stage_scenario(rng)
    scenario["shape"] = shape
    scenario["queue_count_override"] = rng.choice(QUEUE_COUNT_OVERRIDE_CHOICES)
    if shape == "random":
        return scenario

    candidate_count = 0 if shape == "empty_queue" else rng.choice(POSITIVE_CANDIDATE_COUNT_CHOICES)
    market_row_count = max(candidate_count, rng.choice(MARKET_ROW_COUNT_CHOICES))
    diligence_limit = rng.choice(DILIGENCE_LIMIT_CHOICES)
    plan = _stage_plan(
        rng,
        market_row_count=market_row_count,
        candidate_count=candidate_count,
        diligence_limit=diligence_limit,
    )
    failure_position: int | None = None
    failure_mode = ""
    timeout_seconds = _UNBOUNDED_TIMEOUT_SECONDS

    if shape in ("clean_passed", "empty_queue"):
        _clear_partial_reports(plan)
    elif shape == "timeout_truncated":
        for entry in plan:
            entry["cost_seconds"] = 0.0
        # 最后一个阶段之前的某个阶段吃掉预算，保证至少有一个阶段被截断为 skipped。
        plan[rng.randrange(len(STAGES) - 1)]["cost_seconds"] = _TIMEOUT_STAGE_COST_SECONDS
        timeout_seconds = rng.choice(SHORT_TIMEOUT_SECONDS_CHOICES)
    else:
        failure_position = int(shape.rsplit("_", 1)[1])
        failure_mode = rng.choice(FAILURE_MODES)
        plan[failure_position]["mode"] = failure_mode
        # 契约内的失败上报一律带 design §5 表内原因码；`raise` / `invalid_result` /
        # `bad_status` 的原因码由编排器自己补（见 ORCHESTRATOR_REASON_CODES）。
        plan[failure_position]["reason_code"] = (
            rng.choice(FAILED_REASON_CHOICES) if failure_mode == "failed" else ""
        )

    scenario.update(
        {
            "plan": plan,
            "market_row_count": market_row_count,
            "candidate_count": candidate_count,
            "diligence_limit": diligence_limit,
            "failure_position": failure_position,
            "failure_mode": failure_mode,
            "noise_index": None,
            "timeout_seconds": timeout_seconds,
        }
    )
    return scenario


def _recording_stage_runners(
    plan: Sequence[Mapping[str, Any]],
    *,
    clock: _VirtualClock,
    calls: list[str],
) -> dict[str, Any]:
    """在 Property 1 的 runner 外包一层调用记录。

    有了调用记录才能区分“阶段真的执行过”与“被编排跳过”：runner 自己上报的
    `skipped`（design §5 的 `no_candidates`）与编排器补的 `skipped`（超时 / 上游失败 /
    缺失实现）在阶段记录里同为 `skipped`，只靠记录无法判定。
    """

    def _wrap(stage: str, runner: Any) -> Any:
        def _run(context: Mapping[str, Any]) -> Any:
            calls.append(stage)
            return runner(context)

        return _run

    return {
        stage: _wrap(stage, runner) for stage, runner in _stage_runners(plan, clock=clock).items()
    }


def _expected_record_count(raw: Any) -> int:
    """记录数归一口径（需求 1.3）：不可解析或负值一律记 0。"""

    try:
        count = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, count)


def _derived_queue_count(records: Sequence[Mapping[str, Any]]) -> int:
    """facade 口径：清单条目数取 `build_daily_queue` 完成时的 `record_count`，未完成为 0。"""

    for record in records:
        if record["stage"] == STAGES[-1] and record["status"] in COMPLETED_STAGE_STATUSES:
            return int(record["record_count"])
    return 0


def _expected_run_status(records: Sequence[Mapping[str, Any]], *, queue_count: Any) -> str:
    """按 design §5 错误处理表独立重算整体状态（只读阶段记录，不调用实现的判定函数）。"""

    statuses: dict[str, str] = {}
    reasons: dict[str, str] = {}
    for record in records:
        stage = record["stage"]
        if stage in STAGES and stage not in statuses:
            statuses[stage] = record["status"]
            reasons[stage] = record["reason_code"] or ""

    if any(status == "failed" for status in statuses.values()):
        return "failed"
    if any(status == "partial" for status in statuses.values()):
        return "partial"
    if any(
        status == "skipped" and reasons[stage] not in EMPTY_QUEUE_SKIP_REASON_CODES
        for stage, status in statuses.items()
    ):
        return "partial"
    if any(stage not in statuses for stage in STAGES):
        return "partial"
    return "empty" if _expected_record_count(queue_count) == 0 else "passed"


def _status_scenario_summary(
    scenario: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    queue_count: Any,
    status: str,
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = _stage_scenario_summary(scenario, records, {})
    # 进度投影由 Property 1 覆盖，不纳入本属性的反例摘要。
    summary.pop("progress", None)
    summary.update(
        {
            "shape": scenario["shape"],
            "queue_count": repr(queue_count),
            "status": status,
            "next_actions": [
                f"{action.get('action')}|{action.get('reason_code') or '-'}"
                f"|cmd={'y' if str(action.get('command', '')).strip() else 'n'}"
                f"|ep={'y' if str(action.get('endpoint', '')).strip() else 'n'}"
                for action in actions
            ],
        }
    )
    return summary


class DailyMainlineRunStatusPropertyTests(unittest.TestCase):
    def test_property_6_status_and_actionable_next_steps(self) -> None:
        """Feature: project-usability-improvement, Property 6: 状态与可执行下一步一致"""

        observed = {
            "status_passed": 0,
            "status_partial": 0,
            "status_failed": 0,
            "status_empty": 0,
            "zero_candidates": 0,
            "non_empty_queue": 0,
            "zero_queue_count": 0,
            "queue_count_override": 0,
            "timeout_truncated_partial": 0,
            "unmapped_reason_code": 0,
            "preserved_prefix_stage": 0,
            "preserved_prefix_record_count": 0,
            "multiple_next_actions": 0,
            "passed_without_next_actions": 0,
        }
        for position in range(len(STAGES)):
            observed[f"failed_at_stage_{position}"] = 0
        for mode in FAILURE_MODES:
            observed[f"failure_mode_{mode}"] = 0

        for iteration in range(PROPERTY_ITERATIONS):
            seed = 6000 + iteration
            rng = random.Random(seed)
            shape = STATUS_SHAPES[iteration % len(STATUS_SHAPES)]
            scenario = _status_scenario(rng, shape)
            clock = _VirtualClock(read_drift=scenario["clock_read_drift"])
            calls: list[str] = []

            results = run_stages(
                stage_runners=_recording_stage_runners(
                    scenario["plan"], clock=clock, calls=calls
                ),
                timeout_seconds=scenario["timeout_seconds"],
                clock=clock.monotonic,
                now_iso=clock.now_iso,
            )
            records = stage_records(results)
            override = scenario["queue_count_override"]
            queue_count = _derived_queue_count(records) if override is None else override
            status = derive_run_status(results, queue_count=queue_count)
            actions = build_next_actions(results, status=status)

            failure_position = scenario["failure_position"]
            called = set(calls)
            compared_prefix: list[str] = []

            with self.subTest(
                seed=seed,
                scenario=_status_scenario_summary(
                    scenario, records, queue_count=queue_count, status=status, actions=actions
                ),
            ):
                # 整体状态取值域收敛，且与按 design §5 独立重算的结果一致（需求 1.9、1.10）。
                self.assertIn(status, RUN_STATUSES)
                self.assertEqual(status, _expected_run_status(records, queue_count=queue_count))

                # 失败阶段必须带非空原因码，且失败与整体状态互为充要条件（需求 1.9）。
                failed = [record for record in records if record["status"] == "failed"]
                self.assertEqual(status == "failed", bool(failed))
                for record in failed:
                    self.assertIsInstance(record["reason_code"], str)
                    self.assertNotEqual(record["reason_code"].strip(), "")

                if status == "passed":
                    # 通过态不得含失败或部分完成阶段；被跳过的阶段只允许是 design §5 的
                    # `no_candidates`（该原因码不代表异常中断）。
                    self.assertEqual(
                        [
                            record["stage"]
                            for record in records
                            if record["status"] in ("failed", "partial")
                        ],
                        [],
                    )
                    for record in records:
                        if record["status"] == "skipped":
                            self.assertIn(record["reason_code"], EMPTY_QUEUE_SKIP_REASON_CODES)

                # 失败点之前已执行的阶段结果完整保留：逐项等于该阶段 runner 的上报值。
                for index, stage in enumerate(STAGES):
                    if stage not in called or index == failure_position:
                        continue
                    entry = scenario["plan"][index]
                    record = records[index]
                    self.assertEqual(record["stage"], stage)
                    self.assertEqual(record["status"], entry["mode"])
                    self.assertEqual(
                        record["record_count"], _expected_record_count(entry["record_count"])
                    )
                    self.assertEqual(record["reason_code"], entry["reason_code"])
                    self.assertNotEqual(record["started_at"], "")
                    self.assertNotEqual(record["finished_at"], "")
                    if failure_position is not None and index < failure_position:
                        compared_prefix.append(stage)

                # 阶段失败后不再执行后续阶段，已完成阶段结果不被后续覆盖（需求 1.9）。
                if failure_position is not None and records[failure_position]["status"] == "failed":
                    for stage in STAGES[failure_position + 1 :]:
                        self.assertNotIn(stage, called)

                # 非 passed 状态必有至少一条可执行下一步（需求 1.10、2.7）。
                if status != "passed":
                    self.assertGreaterEqual(len(actions), 1)
                for action in actions:
                    for field in NEXT_ACTION_FIELDS:
                        self.assertIn(field, action)
                    self.assertNotEqual(str(action["action"]).strip(), "")
                    self.assertTrue(
                        str(action["command"]).strip() or str(action["endpoint"]).strip(),
                        f"next action carries neither command nor endpoint: {action}",
                    )

                # 每个阶段原因码都能落到一条下一步动作，含 design §5 表外的未登记原因码。
                action_reasons = {str(action["reason_code"]) for action in actions}
                for record in records:
                    if record["reason_code"]:
                        self.assertIn(record["reason_code"], action_reasons)
                if status == "empty":
                    self.assertIn("no_candidates", action_reasons)

            observed[f"status_{status}"] += 1
            if scenario["candidate_count"] == 0:
                observed["zero_candidates"] += 1
            if _expected_record_count(queue_count) > 0:
                observed["non_empty_queue"] += 1
            else:
                observed["zero_queue_count"] += 1
            if override is not None:
                observed["queue_count_override"] += 1
            if status == "partial" and any(
                record["reason_code"] == SKIP_REASON_TIMEOUT for record in records
            ):
                observed["timeout_truncated_partial"] += 1
            if any(
                record["reason_code"] and record["reason_code"] not in REASON_CODES
                for record in records
            ):
                observed["unmapped_reason_code"] += 1
            if failure_position is not None:
                observed[f"failure_mode_{scenario['failure_mode']}"] += 1
                if records[failure_position]["status"] == "failed":
                    observed[f"failed_at_stage_{failure_position}"] += 1
            if compared_prefix:
                observed["preserved_prefix_stage"] += 1
                if any(
                    records[STAGES.index(stage)]["record_count"] > 0 for stage in compared_prefix
                ):
                    observed["preserved_prefix_record_count"] += 1
            if len(actions) >= 2:
                observed["multiple_next_actions"] += 1
            if status == "passed" and not actions:
                observed["passed_without_next_actions"] += 1

        # Guard against a vacuous generator: the boundary cases the property cares
        # about must actually appear in the sampled scenarios.
        for scenario_name, count in observed.items():
            self.assertGreater(count, 0, f"generator never produced {scenario_name}: {observed}")


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()
