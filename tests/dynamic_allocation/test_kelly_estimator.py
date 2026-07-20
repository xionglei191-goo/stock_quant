from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from app.dynamic_allocation.contracts import PointInTimeObservation
from app.dynamic_allocation.risk import HistoricalReturnKellyEstimator


AS_OF = datetime(2026, 7, 17, tzinfo=timezone.utc)


def observation(year: int, month: int, value: float, suffix: str = "") -> PointInTimeObservation:
    observed = date(year, month, 28)
    return PointInTimeObservation(
        observation_id=f"return-{year}-{month}{suffix}",
        series_id="return_3m",
        observation_date=observed,
        value=value,
        release_date=observed,
        available_at=datetime(year, month, 28, tzinfo=timezone.utc),
        vintage_date=observed,
        revision_seq=0,
        source_id="public-market-data",
    )


class HistoricalReturnKellyEstimatorTest(unittest.TestCase):
    def test_estimate_uses_non_overlapping_quarters_and_discloses_clipping(self) -> None:
        rows = []
        year = 2019
        for index in range(28):
            month = (index % 4 + 1) * 3
            if index and month == 3:
                year += 1
            rows.append(observation(year, month, 0.02 if index % 2 else 0.04))
            rows.append(observation(year, month - 1, 0.90, "-overlap"))
        estimator = HistoricalReturnKellyEstimator(
            lookback_years=10,
            minimum_samples=24,
            confidence=0.35,
            expected_return_cap=0.10,
            volatility_floor=0.08,
        )

        result = estimator.estimate(rows, as_of=AS_OF)

        self.assertTrue(result.available)
        self.assertEqual(result.sample_size, 28)
        self.assertEqual(result.expected_return, 0.10)
        self.assertEqual(result.volatility, 0.08)
        self.assertEqual(len(result.source_observation_ids), 28)
        self.assertTrue(all("overlap" not in item for item in result.source_observation_ids))
        self.assertTrue(any("clipped" in item for item in result.warnings))
        self.assertTrue(any("floored" in item for item in result.warnings))
        self.assertIn("non-overlapping", result.explanation)

    def test_insufficient_history_is_explicitly_unavailable(self) -> None:
        estimator = HistoricalReturnKellyEstimator(minimum_samples=24)
        rows = [observation(2025, month, 0.02) for month in (3, 6, 9, 12)]
        result = estimator.estimate(rows, as_of=AS_OF)
        self.assertFalse(result.available)
        self.assertEqual(result.sample_size, 4)
        self.assertIsNone(result.expected_return)
        self.assertIn("below minimum", result.explanation)


if __name__ == "__main__":
    unittest.main()
