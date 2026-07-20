from __future__ import annotations

from datetime import date, datetime, timezone
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.dynamic_allocation.paper import build_paper_snapshot
from app.dynamic_allocation.contracts import UpsertSummary
from scripts.dynamic_allocation_daily_run import DailyRunGateError, main, run_daily
from tests.dynamic_allocation.test_paper_run import valid_payload


AS_OF = datetime(2026, 7, 17, 15, 30, tzinfo=timezone.utc)


class FakeApplication:
    config = object()
    observations = object()

    def __init__(self) -> None:
        self.snapshot = build_paper_snapshot(valid_payload()).to_dict()

    def history(self, _payload):
        return {"items": [{"target_equity_allocation": 0.7}]}

    def evaluate(self, _payload, *, persist):
        return {
            "as_of": AS_OF.isoformat(),
            "ready": True,
            "decision_id": self.snapshot["run_id"],
            "market_regime": "risk_on",
            "target_equity_allocation": 0.5,
            "allocations": {"SPY": 0.35, "QQQ": 0.15, "SGOV": 0.5},
            "caps": {"binding_limit": "kelly_cap", "kelly_cap": 0.5},
            "kelly_input": {
                "source": "estimated", "sample_size": 40,
                "source_observation_ids": ["obs-1", "obs-2"],
            },
            "warnings": [],
            "explanation": "quarter Kelly binds",
            "factors": [{"ready": True} for _ in range(8)],
            "data_health": {"series": [{"status": "fresh"} for _ in range(38)]},
            "source_observation_ids": ["obs-1", "obs-2"],
            "config_hash": "cfg",
            "model_version": "rules-v1",
            "paper_snapshot": self.snapshot,
        }


class FakePipeline:
    def ingest(self, _repository, *, as_of, market_start):
        summary = {
            "missing_series": [], "source_errors": {}, "series_counts": {"return_3m": 40},
        }
        return SimpleNamespace(summary=lambda: summary), UpsertSummary(40, 1, 39, 0)


class FailingPipeline:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def ingest(self, _repository, *, as_of, market_start):
        summary = {
            "missing_series": ["vix"], "source_errors": {"credit_spread": "redacted"},
        }
        return SimpleNamespace(summary=lambda: summary), UpsertSummary(1, 0, 0, 1)


class DynamicAllocationDailyRunTest(unittest.TestCase):
    def test_execute_persists_hash_chain_and_reports_auditable_delta(self) -> None:
        with TemporaryDirectory() as temp:
            ledger = Path(temp) / "paper.jsonl"
            report = run_daily(
                as_of=AS_OF,
                market_start=date(2000, 1, 1),
                execute=True,
                ledger_path=ledger,
                application=FakeApplication(),
                pipeline=FakePipeline(),
            )
            self.assertEqual(report["status"], "completed")
            self.assertTrue(report["paper_ledger"]["appended"])
            self.assertEqual(report["paper_ledger"]["ledger_records"], 1)
            self.assertEqual(report["decision"]["allocation_change"], -0.2)
            self.assertEqual(report["decision"]["kelly_input"]["source_observation_count"], 2)
            self.assertEqual(report["auditability"]["fresh_series_count"], 38)
            self.assertFalse(report["efficacy_evidence"]["financial_benefit_claimed"])
            self.assertFalse(report["live_execution_allowed"])

    def test_preview_is_read_only(self) -> None:
        report = run_daily(
            as_of=AS_OF,
            market_start=date(2000, 1, 1),
            execute=False,
            application=FakeApplication(),
        )
        self.assertEqual(report["mode"], "read_only_preview")
        self.assertEqual(report["refresh"]["pipeline"]["status"], "not_run")
        self.assertFalse(report["paper_ledger"]["appended"])

    def test_cli_requires_explicit_outputs_for_execute(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["--execute"])
        self.assertEqual(raised.exception.code, 2)

    def test_strict_failure_exposes_structured_health_without_source_messages(self) -> None:
        with TemporaryDirectory() as temp:
            with self.assertRaises(DailyRunGateError) as raised:
                run_daily(
                    as_of=AS_OF,
                    market_start=date(2000, 1, 1),
                    execute=True,
                    ledger_path=Path(temp) / "paper.jsonl",
                    application=FakeApplication(),
                    pipeline=FailingPipeline(),
                )
        self.assertEqual(raised.exception.details["missing_series"], ["vix"])
        self.assertEqual(raised.exception.details["source_error_series"], ["credit_spread"])
        self.assertEqual(raised.exception.details["insert_conflicts"], 1)
        self.assertNotIn("redacted", str(raised.exception.details))

    def test_execute_failure_is_archived_for_longitudinal_visibility(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "latest.json"
            history = root / "history"
            stderr = StringIO()
            with (
                patch("scripts.dynamic_allocation_daily_run.DynamicAllocationApplication", FakeApplication),
                patch("scripts.dynamic_allocation_daily_run.PublicDataPipeline", FailingPipeline),
                redirect_stderr(stderr),
            ):
                result = main(
                    [
                        "--as-of", AS_OF.isoformat(),
                        "--execute",
                        "--ledger", str(root / "paper.jsonl"),
                        "--output", str(output),
                        "--history-dir", str(history),
                    ]
                )
            self.assertEqual(result, 1)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["failure"]["missing_series"], ["vix"])
            self.assertEqual(len(list(history.glob("*.json"))), 1)
            self.assertFalse((root / "paper.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
