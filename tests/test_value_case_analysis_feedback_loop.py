from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import value_case_analysis_feedback_loop as value_case


class ValueCaseBatchContractTests(unittest.TestCase):
    def test_symbols_are_normalized_deduplicated_and_keep_first_order(self):
        self.assertEqual(
            value_case.parse_tdx_symbols(" SZ000001,sh600519,sz000001 "),
            ["sz000001", "sh600519"],
        )

    def test_symbols_reject_explicit_empty_segments_and_invalid_values(self):
        for raw, code in (("", "symbols_empty"), ("sz000001,", "symbol_empty"), ("000001", "symbol_invalid")):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, f"^{code}$"):
                value_case.parse_tdx_symbols(raw)

    def test_exchange_is_part_of_derived_ids(self):
        sh_ids = value_case._derive_ids("sh000001")
        sz_ids = value_case._derive_ids("sz000001")
        self.assertNotEqual(sh_ids[0], sz_ids[0])
        self.assertNotEqual(sh_ids[1], sz_ids[1])

    @staticmethod
    def _passed(symbol, event_return, verdict="realized"):
        return {
            "status": "passed",
            "tdx_symbol": symbol,
            "paper_only": True,
            "live_execution_allowed": False,
            "broker_connected": False,
            "performance": {
                "realization_status": verdict,
                "event_window_return": event_return,
            },
        }

    @patch.object(value_case, "_build_service", return_value=object())
    @patch.object(value_case, "run_value_case")
    def test_mixed_batch_is_partial_and_averages_successful_numeric_returns(self, run_case, _build):
        run_case.side_effect = [
            self._passed("sz000001", 0.1),
            RuntimeError("private path /secret/value"),
            self._passed("sh600519", 0.2, "missed"),
        ]
        result = value_case.run_value_case_batch(
            db_path="", tdx_symbols=["SZ000001", "sz000002", "sh600519"],
            start_date="2023-01-01", end_date="2023-12-31", vipdoc_path="",
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["average_event_window_return"], 0.15)
        self.assertEqual(result["verdict_rollup"]["realized"], 1)
        self.assertEqual(result["verdict_rollup"]["missed"], 1)
        self.assertEqual(result["verdict_rollup"]["failed"], 1)
        self.assertEqual(result["cases"][1]["reason"], "value_case_execution_error")
        self.assertEqual(result["cases"][1]["error_type"], "RuntimeError")
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(result["classification"], "local-only")
        self.assertFalse(result["acceptable_for_non_local_release_gate"])
        self.assertTrue(result["paper_only"])
        self.assertFalse(result["live_execution_allowed"])
        self.assertFalse(result["broker_connected"])
        self.assertTrue(result["generated_at"])
        self.assertEqual(result["producer"], value_case.ARTIFACT_PRODUCER)

    @patch.object(value_case, "_build_service", return_value=object())
    @patch.object(value_case, "run_value_case", side_effect=LookupError("sensitive details"))
    def test_all_failed_batch_has_failed_status_and_no_average(self, _run_case, _build):
        result = value_case.run_value_case_batch(
            db_path="", tdx_symbols=["sz000001", "sh600519"],
            start_date="2023-01-01", end_date="2023-12-31", vipdoc_path="",
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["passed_count"], 0)
        self.assertIsNone(result["average_event_window_return"])
        self.assertEqual(result["verdict_rollup"]["failed"], 2)

    @patch.object(value_case, "_build_service", return_value=object())
    @patch.object(value_case, "run_value_case")
    def test_duplicate_symbols_run_once_and_ids_are_stable(self, run_case, _build):
        run_case.return_value = self._passed("sz000001", 0.1)
        result = value_case.run_value_case_batch(
            db_path="persistent.sqlite", tdx_symbols=["sz000001", "SZ000001"],
            start_date="2023-01-01", end_date="2023-12-31", vipdoc_path="",
        )
        self.assertEqual(result["symbol_count"], 1)
        self.assertEqual(run_case.call_count, 1)
        self.assertEqual(run_case.call_args.kwargs["issuer_id"], "issuer_valuecase_sz000001")
        self.assertEqual(run_case.call_args.kwargs["security_id"], "sec_valuecase_sz000001")

    @patch.object(value_case, "_import_market_data", return_value={"created_count": 2})
    def test_value_case_can_rerun_against_the_same_persistent_store(self, _import):
        feedback = SimpleNamespace(
            paper_only=True, live_execution_allowed=False, broker_connected=False,
            performance={"realization_status": "realized", "event_window_return": 0.1},
            validation={}, review_result={},
        )
        store = SimpleNamespace(
            analysis_conclusions={}, observation_items={}, simulation_feedback={},
        )
        service = SimpleNamespace(store=store)
        point = SimpleNamespace(close=10.0, as_of_date="2023-01-03")
        service._market_points_for_security = unittest.mock.Mock(return_value=[point])

        def create_conclusion(payload, **_kwargs):
            store.analysis_conclusions[payload["analysis_conclusion_id"]] = object()

        def create_observation(payload, **_kwargs):
            store.observation_items[payload["observation_id"]] = object()

        def create_feedback(payload, **_kwargs):
            store.simulation_feedback[payload["simulation_feedback_id"]] = feedback

        service.create_analysis_conclusion = unittest.mock.Mock(side_effect=create_conclusion)
        service.register_observation_item = unittest.mock.Mock(side_effect=create_observation)
        service.record_simulation_feedback = unittest.mock.Mock(side_effect=create_feedback)
        service.update_simulation_feedback_performance = unittest.mock.Mock(return_value={"updated": 1})
        kwargs = dict(
            service=service, tdx_symbol="sz000001", issuer_id="issuer_valuecase_sz000001",
            security_id="sec_valuecase_sz000001", source_id="public_eod_market_data",
            start_date="2023-01-01", end_date="2023-12-31", vipdoc_path="", entry_hint=0.0,
        )
        first = value_case.run_value_case(**kwargs)
        second = value_case.run_value_case(**kwargs)
        self.assertEqual(first["feedback_id"], second["feedback_id"])
        self.assertEqual(service.create_analysis_conclusion.call_count, 1)
        self.assertEqual(service.register_observation_item.call_count, 1)
        self.assertEqual(service.record_simulation_feedback.call_count, 1)
        self.assertEqual(service.update_simulation_feedback_performance.call_count, 2)

    def test_cli_explicit_empty_symbols_is_an_argument_error(self):
        with patch.object(sys, "argv", ["value-case", "--symbols", ""]), self.assertRaises(SystemExit) as raised:
            value_case.main()
        self.assertEqual(raised.exception.code, 2)

    @patch.object(value_case, "run_value_case_batch")
    def test_cli_writes_batch_artifact_using_normalized_symbols(self, run_batch):
        run_batch.return_value = {
            "status": "passed", "verdict_rollup": {}, "passed_count": 1,
            "average_event_window_return": 0.1, "paper_only": True,
            "live_execution_allowed": False, "broker_connected": False,
        }
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "batch.json"
            argv = ["value-case", "--symbols", "SZ000001,sz000001", "--output", str(output)]
            with patch.object(sys, "argv", argv):
                value_case.main()
            self.assertEqual(run_batch.call_args.kwargs["tdx_symbols"], ["sz000001"])
            artifact = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(artifact["paper_only"])


if __name__ == "__main__":
    unittest.main()
