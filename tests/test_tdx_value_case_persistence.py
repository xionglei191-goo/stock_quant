from __future__ import annotations

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services import SystemService
from app.store import SQLiteStore
from scripts.value_case_analysis_feedback_loop import run_value_case, run_value_case_batch


class TDXValueCasePersistenceTest(unittest.TestCase):
    @staticmethod
    def _write_day_file(vipdoc: Path) -> None:
        day_dir = vipdoc / "sz" / "lday"
        day_dir.mkdir(parents=True)
        (day_dir / "sz000001.day").write_bytes(b"".join([
            struct.pack("<IIIIIfII", 20230103, 1000, 1050, 980, 1000, 10000.0, 1000, 0),
            struct.pack("<IIIIIfII", 20231229, 1100, 1200, 1080, 1150, 12000.0, 1200, 0),
        ]))

    def test_import_and_feedback_survive_sqlite_reopen(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            vipdoc = root / "vipdoc"
            self._write_day_file(vipdoc)
            database = root / "value-case.sqlite"
            service = SystemService(SQLiteStore(database))

            result = run_value_case(
                service=service,
                tdx_symbol="sz000001",
                issuer_id="issuer_valuecase_sz000001",
                security_id="sec_valuecase_sz000001",
                source_id="public_eod_market_data",
                start_date="2023-01-01",
                end_date="2023-12-31",
                vipdoc_path=str(vipdoc),
                entry_hint=0.0,
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["import_summary"]["created"], 2)
            self.assertTrue(result["paper_only"])
            self.assertFalse(result["live_execution_allowed"])
            self.assertFalse(result["broker_connected"])

            reloaded = SystemService(SQLiteStore(database))
            points = reloaded._market_points_for_security("sec_valuecase_sz000001", limit=10)
            feedback = reloaded.store.simulation_feedback["sf_valuecase_sec_valuecase_sz000001"]
            self.assertEqual([point.as_of_date for point in points], ["2023-01-03", "2023-12-29"])
            self.assertEqual(feedback.performance["latest_price"], 11.5)
            self.assertEqual(feedback.performance["realization_status"], "realized")
            self.assertTrue(feedback.validation["performance_measured"])
            self.assertTrue(feedback.paper_only)
            self.assertFalse(feedback.live_execution_allowed)
            self.assertFalse(feedback.broker_connected)

    def test_batch_db_path_persists_state_without_injected_service(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            vipdoc = root / "vipdoc"
            self._write_day_file(vipdoc)
            database = root / "batch-value-case.sqlite"

            result = run_value_case_batch(
                db_path=str(database),
                tdx_symbols=["sz000001"],
                start_date="2023-01-01",
                end_date="2023-12-31",
                vipdoc_path=str(vipdoc),
            )

            self.assertEqual(result["status"], "passed")
            reloaded = SystemService(SQLiteStore(database))
            self.assertEqual(
                len(reloaded._market_points_for_security("sec_valuecase_sz000001", limit=10)),
                2,
            )
            feedback = reloaded.store.simulation_feedback["sf_valuecase_sec_valuecase_sz000001"]
            self.assertEqual(feedback.performance["latest_price"], 11.5)
            self.assertTrue(feedback.paper_only)
            self.assertFalse(feedback.live_execution_allowed)
            self.assertFalse(feedback.broker_connected)


if __name__ == "__main__":
    unittest.main()
