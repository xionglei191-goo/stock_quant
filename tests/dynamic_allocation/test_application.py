from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app.api import ApiRouter
from app.dynamic_allocation.application import DynamicAllocationApplication
from app.dynamic_allocation.contracts import PointInTimeObservation
from app.dynamic_allocation.data.repository import SQLiteObservationRepository
from app.dynamic_allocation.records import SQLiteAllocationRecordRepository
from app.services import SystemService
from app.store import InMemoryStore


AS_OF = datetime(2026, 7, 17, 20, 0, tzinfo=timezone.utc)


class DynamicAllocationApplicationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "dynamic.sqlite"
        self.observations = SQLiteObservationRepository(path)
        self.records = SQLiteAllocationRecordRepository(path)
        self.app = DynamicAllocationApplication(
            observation_repository=self.observations,
            record_repository=self.records,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _seed_complete_history(self) -> None:
        rows = []
        for series_index, series_id in enumerate(self.app.config.series):
            definition = self.app.config.series[series_id]
            for offset, value in enumerate((1.0, 2.0, 3.0), start=3):
                available = AS_OF - timedelta(days=offset)
                observed = available.date()
                rows.append(PointInTimeObservation(
                    observation_id=f"{series_id}-{offset}", series_id=series_id,
                    observation_date=observed, value=value + series_index / 100,
                    release_date=observed, available_at=available, vintage_date=observed,
                    revision_seq=0, source_id=definition.source_id,
                    payload_hash=f"{series_id}-{offset}",
                ))
        self.observations.upsert(rows)

    def test_missing_data_blocks_decision_without_neutral_fill(self) -> None:
        result = self.app.evaluate({"as_of": AS_OF.isoformat()})
        self.assertFalse(result["ready"])
        self.assertIsNone(result["target_equity_allocation"])
        self.assertEqual(len(result["factors"]), 8)
        self.assertTrue(result["paper_only"])

    def test_complete_pit_history_produces_explained_persisted_decision(self) -> None:
        self._seed_complete_history()
        result = self.app.evaluate({"as_of": AS_OF.isoformat()}, persist=True)
        self.assertTrue(result["ready"])
        self.assertIn(result["target_equity_allocation"], (0.1, 0.3, 0.5, 0.7, 0.9))
        self.assertAlmostEqual(sum(result["allocations"].values()), 1.0)
        self.assertTrue(result["source_observation_ids"])
        self.assertIn("final=", result["explanation"])
        self.assertEqual(self.app.history()["items"][0]["decision_id"], result["decision_id"])
        repeated = self.app.evaluate({"as_of": AS_OF.isoformat()}, persist=True)
        self.assertEqual(repeated, result)
        self.assertEqual(len(self.app.history()["items"]), 1)

    def test_explicit_kelly_inputs_take_priority_and_partial_inputs_do_not_mix(self) -> None:
        self._seed_complete_history()
        explicit = self.app.evaluate({
            "as_of": AS_OF.isoformat(),
            "expected_return": 0.08,
            "volatility": 0.20,
            "confidence": 0.50,
            "sample_size": 60,
        })
        self.assertTrue(explicit["kelly"]["available"])
        self.assertEqual(explicit["kelly_input"]["source"], "explicit")
        self.assertEqual(explicit["kelly_input"]["expected_return"], 0.08)

        partial = self.app.evaluate({"as_of": AS_OF.isoformat(), "expected_return": 0.08})
        self.assertFalse(partial["kelly"]["available"])
        self.assertEqual(partial["kelly_input"]["source"], "explicit")
        self.assertTrue(any("requires both" in item for item in partial["warnings"]))

    def test_critical_observation_date_staleness_blocks_otherwise_calculable_factors(self) -> None:
        rows = []
        for series_index, series_id in enumerate(self.app.config.series):
            definition = self.app.config.series[series_id]
            for offset, value in enumerate((1.0, 2.0, 3.0), start=3):
                available = AS_OF - timedelta(hours=offset)
                observed = date(2025, 1, offset) if series_id == "vix_level" else AS_OF.date() - timedelta(days=offset)
                rows.append(PointInTimeObservation(
                    observation_id=f"health-{series_id}-{offset}", series_id=series_id,
                    observation_date=observed, value=value + series_index / 100,
                    release_date=observed, available_at=available,
                    vintage_date=available.date(), revision_seq=0,
                    source_id=definition.source_id, payload_hash=f"health-{series_id}-{offset}",
                ))
        self.observations.upsert(rows)
        result = self.app.evaluate({"as_of": AS_OF.isoformat()})
        self.assertFalse(result["ready"])
        self.assertFalse(result["data_health"]["ready_for_factor_calculation"])
        self.assertIn("critical data health vix_level", result["explanation"])

    def test_api_contract_and_permission_boundary(self) -> None:
        router = ApiRouter(SystemService(store=InMemoryStore()), dynamic_allocation=self.app)
        response = router.dispatch("GET", "/api/dynamic-allocation/current", {"as_of": AS_OF.isoformat()}, role="analyst")
        self.assertTrue(response.success)
        self.assertTrue(response.data["paper_only"])
        denied = router.dispatch("POST", "/api/dynamic-allocation/evaluate", {"as_of": AS_OF.isoformat()}, role="ceo")
        self.assertEqual(denied.status_code, 403)

    def test_backtest_is_persisted_and_retrievable(self) -> None:
        rows = []
        for index in range(36):
            rows.append({
                "date": (date(2020, 1, 1) + timedelta(days=index)).isoformat(),
                "returns": {"SPY": 0.001, "QQQ": 0.0012, "SGOV": 0.0001},
                "target_equity_weight": 0.5,
            })
        record = self.app.run_backtest({"rows": rows, "as_of": AS_OF.isoformat()})
        repeated = self.app.run_backtest({"rows": rows, "as_of": AS_OF.isoformat()})
        self.assertEqual(repeated, record)
        self.assertEqual(self.app.get_backtest(record["run_id"])["run_id"], record["run_id"])
        self.assertEqual(self.app.backtests()["items"][0]["run_id"], record["run_id"])
        self.assertIn("maximum_drawdown", record["result"]["metrics"])
        self.assertFalse(record["live_execution_allowed"])


if __name__ == "__main__":
    unittest.main()
