from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.dynamic_allocation.config import load_config
from app.dynamic_allocation.data.quality import DataQualityService
from app.dynamic_allocation.data.repository import SQLiteObservationRepository
from tests.dynamic_allocation.test_point_in_time import observation


ROOT = Path(__file__).resolve().parents[2]


class RepositoryContractTest(unittest.TestCase):
    def test_postgresql_schema_has_pit_typed_table_and_indexes(self) -> None:
        schema = (ROOT / "docs" / "postgresql-schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS ai_quant.economic_observations", schema)
        self.assertIn("available_at TIMESTAMPTZ NOT NULL", schema)
        self.assertIn("PRIMARY KEY (series_id, observation_date, vintage_date, revision_seq)", schema)
        self.assertIn("idx_ai_quant_economic_observations_pit", schema)

    def test_config_hash_is_stable_and_boundary_is_locked(self) -> None:
        first = load_config(ROOT / "config" / "dynamic_allocation.yaml")
        second = load_config(ROOT / "config" / "dynamic_allocation.yaml")
        self.assertEqual(first.config_hash, second.config_hash)
        self.assertTrue(first.paper_only)
        self.assertFalse(first.live_execution_allowed)
        self.assertFalse(first.broker_connected)

    def test_data_health_exposes_coverage_freshness_missing_and_boundary(self) -> None:
        config = load_config(ROOT / "config" / "dynamic_allocation.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteObservationRepository(Path(temp_dir) / "health.sqlite3")
            repository.upsert([
                observation(
                    "unrate", series_id="unemployment_rate", observation_date=datetime(2024, 3, 1).date(),
                    release_date=datetime(2024, 4, 5).date(),
                    available_at=datetime(2024, 4, 5, 12, 30, tzinfo=timezone.utc),
                    vintage_date=datetime(2024, 4, 5).date(), payload_hash="unrate",
                ),
                observation(
                    "cpi", series_id="cpi", observation_date=datetime(2023, 1, 1).date(),
                    release_date=datetime(2023, 2, 10).date(),
                    available_at=datetime(2023, 2, 10, 13, 30, tzinfo=timezone.utc),
                    vintage_date=datetime(2023, 2, 10).date(), payload_hash="cpi",
                ),
            ])
            report = DataQualityService(repository, config).evaluate(
                datetime(2024, 4, 10, tzinfo=timezone.utc),
                ("unemployment_rate", "cpi", "vix_level", "high_yield_spread"),
            )
        self.assertEqual(report.coverage_ratio, 0.5)
        self.assertEqual(report.missing_series, ("vix_level", "high_yield_spread"))
        self.assertEqual(report.stale_series, ("cpi",))
        self.assertFalse(report.ready_for_factor_calculation)
        self.assertTrue(report.paper_only)
        self.assertFalse(report.live_execution_allowed)
        self.assertFalse(report.broker_connected)

    def test_critical_quality_flag_blocks_factor_readiness(self) -> None:
        config = load_config(ROOT / "config" / "dynamic_allocation.yaml")
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SQLiteObservationRepository(Path(temp_dir) / "quality.sqlite3")
            flagged = observation(
                "vix-flagged", series_id="vix_level",
                observation_date=datetime(2024, 4, 9).date(),
                release_date=datetime(2024, 4, 9).date(),
                available_at=datetime(2024, 4, 9, 20, tzinfo=timezone.utc),
                vintage_date=datetime(2024, 4, 9).date(), payload_hash="flagged",
            )
            from dataclasses import replace
            repository.upsert([replace(flagged, quality_flags=("source_disagreement",))])
            report = DataQualityService(repository, config).evaluate(
                datetime(2024, 4, 10, tzinfo=timezone.utc), ("vix_level",)
            )
        self.assertEqual(report.series[0].status, "quality_blocked")
        self.assertFalse(report.ready_for_factor_calculation)


if __name__ == "__main__":
    unittest.main()
