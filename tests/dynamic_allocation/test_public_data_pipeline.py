from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from app.dynamic_allocation.application import DynamicAllocationApplication
from app.dynamic_allocation.config import load_config
from app.dynamic_allocation.data.public_pipeline import FRED_SERIES, PublicDataPipeline
from app.dynamic_allocation.data.public_sources import RawPoint
from app.dynamic_allocation.data.repository import SQLiteObservationRepository
from app.dynamic_allocation.records import SQLiteAllocationRecordRepository


ROOT = Path(__file__).resolve().parents[2]
AS_OF = datetime(2026, 7, 17, 15, 0, tzinfo=timezone.utc)


def _monthly(start_year: int = 1990, end_year: int = 2026) -> list[RawPoint]:
    result = []
    index = 0
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            day = date(year, month, 1)
            if day > AS_OF.date():
                return result
            result.append(RawPoint(day, 100.0 + index * 0.2))
            index += 1
    return result


def _daily() -> list[RawPoint]:
    start = date(2000, 1, 1)
    result = []
    day = start
    index = 0
    while day <= date(2026, 7, 16):
        if day.weekday() < 5:
            result.append(RawPoint(day, 100.0 + index * 0.03 + (index % 31) * 0.01))
            index += 1
        day += timedelta(days=1)
    return result


class FakePublicClient:
    def fred_batch(self, series_ids: list[str]) -> dict[str, list[RawPoint]]:
        return {series_id: self.fred(series_id) for series_id in series_ids}

    def fred(self, series_id: str) -> list[RawPoint]:
        points = _monthly()
        if series_id in {"BAMLH0A0HYM2", "BAMLC0A0CM", "DGS10", "DTWEXBGS"}:
            points = _daily()
        if series_id == "ICSA":
            return [RawPoint(point.observation_date, 200000 + index) for index, point in enumerate(_daily())]
        if series_id == "BOGZ1FL893064105Q":
            return [RawPoint(point.observation_date, point.value * 1_000_000) for point in points]
        if series_id in {"WALCL", "WTREGEN", "RRPONTSYD"}:
            return [RawPoint(point.observation_date, point.value * 1000) for point in _daily()]
        if series_id == "NFCI":
            return [RawPoint(point.observation_date, -0.5 + index / 100000) for index, point in enumerate(_daily())]
        return points

    def cboe(self, index_id: str) -> list[RawPoint]:
        multiplier = 1.15 if index_id == "VIX3M" else 1.0
        return [RawPoint(point.observation_date, (18 + index % 17 / 10) * multiplier) for index, point in enumerate(_daily())]

    def yahoo_adjusted_close(self, ticker: str, start: date, end: date) -> list[RawPoint]:
        scale = {"SPY": 1.0, "HYG": 0.5, "RSP": 0.8}[ticker]
        return [RawPoint(point.observation_date, point.value * scale) for point in _daily() if start <= point.observation_date <= end]

    def finra_margin_debt(self) -> list[RawPoint]:
        return [RawPoint(point.observation_date, 100000 + index * 500) for index, point in enumerate(_monthly(1997))]


class PublicDataPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(ROOT / "config" / "dynamic_allocation.yaml")
        self.pipeline = PublicDataPipeline(self.config, FakePublicClient())

    def test_collect_builds_every_registered_series_with_disclosures(self) -> None:
        result = self.pipeline.collect(as_of=AS_OF)
        self.assertFalse(result.source_errors)
        self.assertFalse(result.missing_series)
        self.assertEqual(set(result.series_counts), set(self.config.series))
        self.assertTrue(all(count >= 3 for count in result.series_counts.values()))
        latest = {row.series_id: row for row in result.observations}
        self.assertTrue(latest["forward_pe"].rights_tag["proxy"])
        self.assertFalse(latest["vix_level"].rights_tag["proxy"])
        self.assertFalse(latest["vix_level"].rights_tag["backtest_eligible"])
        self.assertEqual(latest["vix_level"].available_at, datetime(2026, 7, 17, tzinfo=timezone.utc))
        self.assertEqual(latest["vix_level"].source_id, self.config.series["vix_level"].source_id)

    def test_ingest_produces_ready_paper_decision_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dynamic.sqlite"
            observations = SQLiteObservationRepository(path)
            records = SQLiteAllocationRecordRepository(path)
            collected, first = self.pipeline.ingest(observations, as_of=AS_OF)
            _, repeated = self.pipeline.ingest(observations, as_of=AS_OF)
            self.assertFalse(collected.missing_series)
            self.assertGreater(first.inserted, 100)
            self.assertEqual(repeated.inserted, 0)
            self.assertEqual(repeated.duplicates, first.received)
            app = DynamicAllocationApplication(observation_repository=observations, record_repository=records)
            decision = app.evaluate({"as_of": AS_OF.isoformat()}, persist=True)
            self.assertTrue(decision["ready"])
            self.assertTrue(decision["data_health"]["ready_for_factor_calculation"])
            self.assertTrue(decision["kelly"]["available"])
            self.assertEqual(decision["kelly_input"]["source"], "estimated")
            self.assertGreaterEqual(decision["kelly_input"]["sample_size"], 24)
            self.assertEqual(len(decision["factors"]), 8)
            self.assertIn(decision["target_equity_allocation"], (0.1, 0.3, 0.5, 0.7, 0.9))
            proxy_rows = [row for row in decision["paper_snapshot"]["data_observations"] if row["rights_tag"].get("proxy")]
            self.assertTrue(proxy_rows)
            self.assertTrue(all(not row["rights_tag"]["backtest_eligible"] for row in proxy_rows))

    def test_source_failure_is_reported_and_missing_series_are_not_filled(self) -> None:
        class BrokenClient(FakePublicClient):
            def yahoo_adjusted_close(self, ticker: str, start: date, end: date) -> list[RawPoint]:
                if ticker == "SPY":
                    raise RuntimeError("rate limited")
                return super().yahoo_adjusted_close(ticker, start, end)

        result = PublicDataPipeline(self.config, BrokenClient()).collect(as_of=AS_OF)
        self.assertIn("yahoo:SPY", result.source_errors)
        self.assertIn("price_to_ma_200", result.missing_series)
        self.assertIn("forward_pe", result.missing_series)

    def test_strict_ingest_does_not_write_partial_source_results(self) -> None:
        class BrokenClient(FakePublicClient):
            def fred_batch(self, series_ids: list[str]) -> dict[str, list[RawPoint]]:
                return {}

        with tempfile.TemporaryDirectory() as temp:
            repository = SQLiteObservationRepository(Path(temp) / "strict.sqlite")
            result, summary = PublicDataPipeline(
                self.config,
                BrokenClient(),
            ).ingest_strict(repository, as_of=AS_OF)
            stored_count = repository.count()

        self.assertTrue(result.missing_series)
        self.assertEqual(summary.inserted, 0)
        self.assertEqual(stored_count, 0)


if __name__ == "__main__":
    unittest.main()
