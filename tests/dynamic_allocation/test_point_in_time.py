from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from app.dynamic_allocation.contracts import PointInTimeObservation
from app.dynamic_allocation.data.repository import SQLiteObservationRepository


def observation(
    observation_id: str,
    *,
    observation_date: date = date(2024, 1, 1),
    value: float = 3.1,
    release_date: date = date(2024, 2, 10),
    available_at: datetime = datetime(2024, 2, 10, 13, 30, tzinfo=timezone.utc),
    vintage_date: date = date(2024, 2, 10),
    revision_seq: int = 0,
    series_id: str = "fred:CPI",
    payload_hash: str = "initial",
) -> PointInTimeObservation:
    return PointInTimeObservation(
        observation_id=observation_id,
        series_id=series_id,
        observation_date=observation_date,
        value=value,
        release_date=release_date,
        available_at=available_at,
        vintage_date=vintage_date,
        revision_seq=revision_seq,
        source_id="fred-public",
        source_uri="https://fred.stlouisfed.org/series/CPI",
        ingested_at=datetime(2024, 4, 1, tzinfo=timezone.utc),
        rights_tag={"license_class": "public"},
        payload_hash=payload_hash,
    )


class PointInTimeRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = SQLiteObservationRepository(Path(self.temp_dir.name) / "pit.sqlite3")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_historical_query_selects_version_known_at_cutoff(self) -> None:
        initial = observation("cpi-initial")
        revised = observation(
            "cpi-revised",
            value=3.0,
            release_date=date(2024, 3, 12),
            available_at=datetime(2024, 3, 12, 13, 30, tzinfo=timezone.utc),
            vintage_date=date(2024, 3, 12),
            revision_seq=1,
            payload_hash="revised",
        )
        future_period = observation(
            "cpi-feb",
            observation_date=date(2024, 2, 1),
            value=3.2,
            release_date=date(2024, 3, 10),
            available_at=datetime(2024, 3, 10, 13, 30, tzinfo=timezone.utc),
            vintage_date=date(2024, 3, 10),
            payload_hash="future-period",
        )
        self.repository.upsert([initial, revised, future_period])

        february = self.repository.history_available(
            ["fred:CPI"], datetime(2024, 2, 29, tzinfo=timezone.utc)
        )
        april = self.repository.history_available(
            ["fred:CPI"], datetime(2024, 4, 1, tzinfo=timezone.utc)
        )

        self.assertEqual([(row.observation_date, row.value) for row in february], [(date(2024, 1, 1), 3.1)])
        self.assertEqual([(row.observation_date, row.value) for row in april], [
            (date(2024, 1, 1), 3.0),
            (date(2024, 2, 1), 3.2),
        ])
        self.assertEqual([row.observation_id for row in self.repository.vintages("fred:CPI", date(2024, 1, 1))], [
            "cpi-initial", "cpi-revised"
        ])

    def test_duplicate_is_idempotent_and_changed_vintage_is_retained(self) -> None:
        initial = observation("cpi-initial")
        first = self.repository.upsert([initial])
        duplicate = self.repository.upsert([initial])
        revised = observation(
            "cpi-revised", value=3.0, release_date=date(2024, 3, 12),
            available_at=datetime(2024, 3, 12, 13, 30, tzinfo=timezone.utc),
            vintage_date=date(2024, 3, 12), revision_seq=1, payload_hash="revised",
        )
        changed = self.repository.upsert([revised])
        conflict = self.repository.upsert([replace(initial, value=99.0, payload_hash="mutated")])

        self.assertEqual((first.inserted, duplicate.duplicates, changed.inserted), (1, 1, 1))
        self.assertEqual(conflict.conflicts, 1)
        self.assertEqual(self.repository.count(), 2)
        self.assertEqual(len(self.repository.vintages("fred:CPI", date(2024, 1, 1))), 2)

    def test_contract_rejects_naive_availability(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone"):
            observation("bad", available_at=datetime(2024, 2, 10, 13, 30))


if __name__ == "__main__":
    unittest.main()
