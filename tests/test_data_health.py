from __future__ import annotations

from app.models import MarketDataPoint
from app.services import SystemService
from app.store import InMemoryStore
from tests.support import SystemServiceTestBase


class _LazyTypedMarketDataStore(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self._lazy_collections = {"market_data"}
        self.query_calls: list[dict[str, object]] = []

    def estimate_market_data_points(self) -> int:
        return 28_365_189

    def query_market_data_points(self, **filters: object) -> list[MarketDataPoint]:
        self.query_calls.append(dict(filters))
        return [
            MarketDataPoint(
                data_id="md_latest_lazy",
                security_id="sec_lazy",
                source_id="public_eod_market_data",
                market="A",
                as_of_date="2026-07-20",
                close=10.0,
            )
        ]

    def count_market_data_points(self, **_filters: object) -> int:
        raise AssertionError("exact count must not scan a healthy estimated backend")


class DataHealthSourceOfTruthTests(SystemServiceTestBase):
    def test_summary_uses_lazy_backend_count_and_freshness_without_materialization(self) -> None:
        store = _LazyTypedMarketDataStore()
        service = SystemService(store)
        response = service.data_health_summary(actor="analyst")

        sources = {item["source_key"]: item for item in response["sources"]}
        market = sources["market_data"]
        self.assertEqual(len(store.market_data), 0)
        self.assertEqual(market["status"], "healthy")
        self.assertEqual(market["latest_success_at"], "2026-07-20")
        self.assertEqual(market["evidence"]["market_data_count"], 28_365_189)
        self.assertEqual(market["evidence"]["latest_as_of_date"], "2026-07-20")
        self.assertEqual(market["evidence"]["count_accuracy"], "estimated")
        self.assertEqual(market["evidence"]["storage_mode"], "lazy_typed_backend")
        self.assertEqual(market["evidence"]["materialized_cache_count"], 0)
        self.assertEqual(market["source_of_truth"], "typed_market_data_backend")
        self.assertEqual(market["consistency_status"], "consistent")
        self.assertEqual(store.query_calls, [{"limit": 1, "descending": True}])

        research = sources["research_reports"]
        self.assertEqual(research["evidence"]["research_report_assets"], 0)
        self.assertEqual(research["evidence"]["registry_scope"], "application_registry_only")
        self.assertFalse(research["evidence"]["external_filesystem_and_search_inventory_included"])
        self.assertEqual(research["consistency_status"], "not_reconciled")
        self.assertIn("consistency_counts", response["summary"])

    def test_summary_preserves_existing_source_row_contract_for_in_memory_store(self) -> None:
        response = self.service.data_health_summary({"source_key": "market_data"}, actor="analyst")

        self.assertEqual(response["schema_id"], "data-health-summary-v1")
        self.assertEqual(response["summary"]["source_count"], 1)
        row = response["sources"][0]
        for field in [
            "source_key",
            "domain",
            "label",
            "status",
            "latest_success_at",
            "latest_failure_at",
            "failure_count",
            "pending_count",
            "freshness_level",
            "last_artifact",
            "next_actions",
            "evidence",
            "usage_boundary",
        ]:
            self.assertIn(field, row)
        self.assertEqual(row["source_of_truth"], "materialized_store")
        self.assertEqual(row["consistency_status"], "consistent")
