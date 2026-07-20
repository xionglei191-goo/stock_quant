from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.dynamic_allocation.operations import build_longitudinal_report
from app.dynamic_allocation.paper import build_paper_snapshot
from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository
from app.dynamic_allocation.performance import (
    METHODOLOGY_VERSION,
    SCHEMA_VERSION,
    build_performance_evidence,
)
from tests.dynamic_allocation.test_operations import daily_report
from tests.dynamic_allocation.test_paper_run import valid_payload
from scripts.dynamic_allocation_operations_report import main as report_main


def price(asset: str, day: str, value: float) -> dict[str, object]:
    return {
        "adjusted_close": value,
        "observation_id": f"price-{asset}-{day}",
        "source_id": "governed-public-adjusted-close",
        "source_uri": f"https://example.test/prices/{asset}",
        "rights_tag": {
            "automated_use_allowed": True,
            "paper_performance_eligible": True,
            "backtest_eligible": False,
        },
    }


def session(day: str, spy: float, qqq: float, sgov: float) -> dict[str, object]:
    return {
        "date": day,
        "market_status": "open",
        "close_at": f"{day}T20:00:00Z",
        "available_at": f"{day}T21:00:00Z",
        "prices": {
            "SPY": price("SPY", day, spy),
            "QQQ": price("QQQ", day, qqq),
            "SGOV": price("SGOV", day, sgov),
        },
    }


def performance_input() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "collection_started_at": "2026-07-16T20:00:00Z",
        "initial_nav": 1.0,
        "transaction_cost_bps": 5.0,
        "annual_advisory_fee_bps": 0.0,
        "calendar": {
            "calendar_id": "XNYS",
            "version": "2026-07-18",
            "source_id": "governed-market-calendar",
            "source_uri": "https://example.test/calendar/XNYS",
            "available_at": "2026-07-16T00:00:00Z",
        },
        "sessions": [
            session("2026-07-16", 100.0, 100.0, 100.0),
            session("2026-07-17", 101.0, 102.0, 100.01),
            session("2026-07-20", 102.01, 104.04, 100.02),
        ],
        "reviews": [],
    }


def gate_evidence() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "methodology_version": METHODOLOGY_VERSION,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "performance_evidence_ready": True,
        "coverage": {
            "evidence_start_at": "2026-07-16T21:00:00Z",
            "evidence_end_at": "2026-10-18T21:00:00Z",
        },
        "reviews": [],
    }


class PaperPerformanceContractTests(unittest.TestCase):
    def test_next_session_nav_turnover_fees_benchmarks_and_lineage(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        result = build_performance_evidence(
            [snapshot],
            performance_input(),
            as_of=datetime(2026, 7, 21, tzinfo=timezone.utc),
        )
        self.assertTrue(result["performance_evidence_ready"])
        self.assertEqual(result["coverage"]["evaluated_interval_count"], 1)
        point = result["paper_nav"]["points"][0]
        self.assertEqual(point["signal_run_id"], snapshot.run_id)
        self.assertEqual(point["period_start_date"], "2026-07-17")
        self.assertAlmostEqual(point["turnover"], 0.5)
        self.assertAlmostEqual(point["transaction_cost"], 0.00025)
        self.assertAlmostEqual(point["net_return"], 0.0063, places=6)
        self.assertEqual(set(point["price_observation_ids"]), {"SPY", "QQQ", "SGOV"})
        self.assertEqual(
            point["price_observation_ids"]["SPY"],
            {"period_start": "price-SPY-2026-07-17", "period_end": "price-SPY-2026-07-20"},
        )
        self.assertAlmostEqual(point["benchmark_returns"]["spy_buy_hold"], 0.01)
        self.assertIn("spy_buy_hold", result["benchmarks"])
        self.assertEqual(result["methodology"]["cash_asset"], "SGOV")
        self.assertFalse(result["source_catalog"][0]["backtest_eligible"])
        self.assertEqual(result["source_catalog"][0]["usage_scope"], "forward_paper_only")
        self.assertFalse(result["efficacy_proven"])

    def test_signal_after_prior_availability_cannot_earn_current_interval(self) -> None:
        base = build_paper_snapshot(valid_payload())
        late = replace(base, run_id="dap_late", as_of="2026-07-17T22:00:00Z", evaluated_at="2026-07-17T22:00:00Z")
        payload = performance_input()
        payload["sessions"].append(session("2026-07-21", 103.03, 106.1208, 100.03))  # type: ignore[union-attr]
        result = build_performance_evidence(
            [late], payload, as_of=datetime(2026, 7, 22, tzinfo=timezone.utc)
        )
        self.assertEqual(result["coverage"]["evaluated_interval_count"], 1)
        self.assertEqual(result["paper_nav"]["points"][0]["period_start_date"], "2026-07-20")

    def test_missing_open_price_blocks_evidence_and_return_does_not_cross_gap(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        payload = performance_input()
        del payload["sessions"][2]["prices"]["QQQ"]  # type: ignore[index]
        payload["sessions"].append(session("2026-07-21", 103.03, 106.1208, 100.03))  # type: ignore[union-attr]
        result = build_performance_evidence(
            [snapshot], payload, as_of=datetime(2026, 7, 22, tzinfo=timezone.utc)
        )
        self.assertFalse(result["performance_evidence_ready"])
        self.assertEqual(result["coverage"]["incomplete_open_sessions"], ["2026-07-20"])
        self.assertEqual(result["coverage"]["evaluated_interval_count"], 0)

        missing_day = performance_input()
        del missing_day["sessions"][1]  # type: ignore[index]
        result = build_performance_evidence(
            [snapshot], missing_day, as_of=datetime(2026, 7, 22, tzinfo=timezone.utc)
        )
        self.assertEqual(result["coverage"]["missing_weekdays"], ["2026-07-17"])
        self.assertEqual(result["coverage"]["evaluated_interval_count"], 0)

    def test_boundaries_future_data_and_premature_reviews_are_rejected(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        live = performance_input()
        live["broker_connected"] = True
        with self.assertRaisesRegex(ValueError, "broker_connected"):
            build_performance_evidence([snapshot], live, as_of=datetime(2026, 7, 21, tzinfo=timezone.utc))

        future = performance_input()
        with self.assertRaisesRegex(ValueError, "unavailable as of"):
            build_performance_evidence([snapshot], future, as_of=datetime(2026, 7, 19, tzinfo=timezone.utc))

        premature = performance_input()
        premature["reviews"] = [{
            "gate_months": 3,
            "status": "completed",
            "outcome": "effective",
            "reviewer": "human-reviewer",
            "reviewed_at": "2026-07-21T00:00:00Z",
            "rationale": "premature",
        }]
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            build_performance_evidence(
                [snapshot], premature, as_of=datetime(2026, 7, 22, tzinfo=timezone.utc)
            )

        backfill = performance_input()
        backfill["collection_started_at"] = "2026-07-17T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "predate collection"):
            build_performance_evidence(
                [snapshot], backfill, as_of=datetime(2026, 7, 22, tzinfo=timezone.utc)
            )

    def test_gate_requires_performance_coverage_then_human_review(self) -> None:
        base = build_paper_snapshot(valid_payload())
        snapshots = [
            base,
            replace(base, run_id="dap_oct", as_of="2026-10-18T00:00:00Z", evaluated_at="2026-10-18T00:00:00Z"),
        ]
        reports = [daily_report(f"2026-{month:02d}-17T00:00:00Z") for month in (7, 8, 9, 10)]
        evidence = gate_evidence()
        pending = build_longitudinal_report(
            snapshots,
            reports,
            as_of=datetime(2026, 10, 18, tzinfo=timezone.utc),
            performance_evidence=evidence,
        )
        self.assertEqual(pending["review_gates"][0]["status"], "human_review_required")
        self.assertFalse(pending["review_gates"][0]["efficacy_proven"])

        reviewed = deepcopy(evidence)
        reviewed["reviews"] = [{
            "gate_months": 3,
            "status": "completed",
            "outcome": "effective",
            "reviewer": "human-reviewer",
            "reviewed_at": "2026-10-18T00:00:00Z",
            "rationale": "governed evidence review",
        }]
        completed = build_longitudinal_report(
            snapshots,
            reports,
            as_of=datetime(2026, 10, 18, tzinfo=timezone.utc),
            performance_evidence=reviewed,
        )
        self.assertEqual(completed["review_gates"][0]["status"], "human_review_completed")
        self.assertTrue(completed["review_gates"][0]["efficacy_proven"])

    def test_cli_accepts_explicit_performance_input_without_writing(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "paper.jsonl"
            evidence = root / "performance.json"
            JsonlPaperSnapshotRepository(ledger).append(snapshot)
            evidence.write_text(json.dumps(performance_input()), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    report_main([
                        "--ledger", str(ledger),
                        "--performance-input", str(evidence),
                        "--as-of", "2026-07-21T00:00:00Z",
                    ]),
                    0,
                )
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["performance_evidence"]["performance_evidence_ready"])
            self.assertFalse(result["efficacy_evidence"]["financial_benefit_claimed"])


if __name__ == "__main__":
    unittest.main()
