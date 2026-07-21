"""Usage telemetry tests (local feature-access counters via dispatch)."""

from __future__ import annotations

from copy import deepcopy
from threading import Event, Thread
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.api import ApiRouter
from app.models import AuditEvent, UsageMetric
from app.services import SystemService
from app.store import InMemoryStore, PostgreSQLStore, SQLiteStore
from tests.support import SystemServiceTestBase, _FakePostgresConnection, _FakePostgresDatabase


class _DirtyTrackingStore(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.dirty_resources: list[str] = []

    def mark_dirty_for_resource(self, resource_type: str) -> None:
        self.dirty_resources.append(resource_type)


class _ScopedCommitStore(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.dirty_resources: list[str] = []
        self.commit_scopes: list[tuple[str, ...]] = []
        self.persisted_source_ids: set[str] = set()

    def mark_dirty_for_resource(self, resource_type: str) -> None:
        self.dirty_resources.append(resource_type)

    def commit(self) -> None:
        self.commit_scopes.append(tuple(self.dirty_resources))
        self.dirty_resources.clear()

    def commit_all(self) -> None:
        self.commit_scopes.append(("__all__",))
        self.persisted_source_ids = set(self.sources)
        self.dirty_resources.clear()


class _TelemetryFailStore(_ScopedCommitStore):
    def commit(self) -> None:
        if self.dirty_resources == ["usage_metric"]:
            self.commit_scopes.append(tuple(self.dirty_resources))
            raise RuntimeError("telemetry commit failed")
        super().commit()


class _RollbackOnceConnection(_FakePostgresConnection):
    def __enter__(self):
        self._snapshot = {
            "records": deepcopy(self.database.records),
            "market_data_bars": deepcopy(self.database.market_data_bars),
            "audit": deepcopy(self.database.audit),
        }
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None and self.database.fail_next_commit:
            self.database.records = self._snapshot["records"]
            self.database.market_data_bars = self._snapshot["market_data_bars"]
            self.database.audit = self._snapshot["audit"]
            self.database.fail_next_commit = False
            raise RuntimeError("transaction commit failed")
        return None


class _RollbackOnceDatabase(_FakePostgresDatabase):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_commit = False

    def connect(self, dsn):
        self.dsns.append(dsn)
        return _RollbackOnceConnection(self)


class _ConcurrentCommitStore(InMemoryStore):
    def __init__(self) -> None:
        super().__init__()
        self.pending: set[str] = set()
        self.persisted: set[str] = set()

    def commit_all(self) -> None:
        self.persisted.update(self.pending)


class _BlockingWriteRouter(ApiRouter):
    PATH = "/api/test-concurrent-write"

    def __init__(self, service: SystemService) -> None:
        super().__init__(service)
        self.first_entered = Event()
        self.second_entered = Event()
        self.release_first = Event()

    def _resolve(self, method: str, path: str):
        if method == "POST" and path == self.PATH:
            return self._write_marker
        return super()._resolve(method, path)

    def _authorize(self, method: str, path: str, role: str) -> bool:
        if method == "POST" and path == self.PATH:
            return True
        return super()._authorize(method, path, role)

    def _write_marker(self, _path: str, body: dict, *, actor: str) -> dict:
        marker = str(body["marker"])
        if marker == "first":
            self.first_entered.set()
            if not self.release_first.wait(timeout=2):
                raise RuntimeError("timed out waiting to release first request")
        else:
            self.second_entered.set()
        self.service.store.pending.add(marker)
        return {"marker": marker, "actor": actor}


class UsageMetricsTests(SystemServiceTestBase):
    def test_read_only_research_batch_state_does_not_write_usage_or_audit(self) -> None:
        audit_count = len(self.service.store.audit_log)
        response = self.router.dispatch(
            "GET",
            "/api/research-reports/batch-state",
            {"report_ids": ["rr_missing"]},
            role="analyst",
            origin="scheduled",
        )

        self.assertTrue(response.success)
        self.assertEqual(response.data["missing_report_ids"], ["rr_missing"])
        self.assertEqual(len(self.service.store.audit_log), audit_count)
        self.assertNotIn("research_reports", self.service.store.usage_metrics)

    def test_dispatch_records_feature_usage(self) -> None:
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 5}, role="analyst")
        self.router.dispatch("GET", "/api/observation-items", {}, role="analyst")
        self.router.dispatch("GET", "/api/observation-items", {}, role="analyst")
        resp = self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        self._assert_api_envelope(resp)
        features = {row["feature"]: row for row in resp.data["features"]}
        self.assertIn("company_intelligence", features)
        self.assertIn("observation_items", features)
        self.assertEqual(features["observation_items"]["hit_count"], 2)
        self.assertEqual(features["observation_items"]["read_count"], 2)
        self.assertGreaterEqual(resp.data["total_hits"], 3)

    def test_health_metrics_and_self_excluded(self) -> None:
        self.router.dispatch("GET", "/api/health", {}, role="analyst")
        self.router.dispatch("GET", "/api/metrics", {}, role="analyst")
        self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        resp = self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        features = {row["feature"] for row in resp.data["features"]}
        self.assertNotIn("health", features)
        self.assertNotIn("metrics", features)
        self.assertNotIn("usage_metrics", features)

    def test_failed_requests_not_counted(self) -> None:
        # unknown route -> 404, must not create a usage row
        self.router.dispatch("GET", "/api/company-events", {}, role="analyst")
        before = self.service.usage_metrics_summary()["total_hits"]
        self.router.dispatch("GET", "/api/does-not-exist", {}, role="analyst")
        after = self.service.usage_metrics_summary()["total_hits"]
        self.assertEqual(before, after)

    def test_summary_surfaced_in_metrics(self) -> None:
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 5}, role="analyst")
        summary = self.service.usage_metrics_summary()
        self.assertGreaterEqual(summary["total_hits"], 1)
        self.assertGreaterEqual(summary["feature_count"], 1)
        self.assertTrue(any(item["feature"] == "company_intelligence" for item in summary["top_features"]))

    def test_usage_origins_keep_product_and_automation_counts_separate(self) -> None:
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="ui")
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="scheduled")
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="acceptance")
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="invalid")

        payload = self.service.usage_metrics_payload()
        metric = next(item for item in payload["features"] if item["feature"] == "company_intelligence")
        self.assertEqual(payload["product_hits"], 1)
        self.assertEqual(payload["automation_hits"], 2)
        self.assertEqual(payload["api_hits"], 1)
        self.assertEqual(metric["origin_counts"], {"acceptance": 1, "api": 1, "scheduled": 1, "ui": 1})
        self.assertEqual(metric["product_hit_count"], 1)
        self.assertEqual(metric["automation_hit_count"], 2)
        self.assertEqual(metric["unclassified_hit_count"], 0)

    def test_legacy_usage_counts_are_not_claimed_as_product_usage(self) -> None:
        self.service.store.usage_metrics["legacy"] = UsageMetric(feature="legacy", hit_count=7)
        payload = self.service.usage_metrics_payload()
        metric = next(item for item in payload["features"] if item["feature"] == "legacy")
        self.assertEqual(metric["unclassified_hit_count"], 7)
        self.assertEqual(payload["unclassified_hits"], 7)
        self.assertEqual(payload["product_hits"], 0)

    def test_usage_origin_counts_survive_sqlite_reopen(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "usage.sqlite"
            router = ApiRouter(SystemService(SQLiteStore(path)))
            response = router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="ui")
            self.assertTrue(response.success, response.error)

            reopened = SystemService(SQLiteStore(path))
            payload = reopened.usage_metrics_payload()

        metric = next(item for item in payload["features"] if item["feature"] == "company_intelligence")
        self.assertEqual(metric["origin_counts"]["ui"], 1)
        self.assertEqual(metric["last_origin"], "ui")
        self.assertEqual(payload["product_hits"], 1)

    def test_usage_write_marks_only_the_usage_collection_dirty_when_supported(self) -> None:
        store = _DirtyTrackingStore()
        router = ApiRouter(SystemService(store))
        response = router.dispatch("GET", "/api/company-intelligence/DEMO", {}, role="analyst", origin="ui")
        self.assertTrue(response.success, response.error)
        self.assertEqual(store.dirty_resources, ["usage_metric"])

    def test_post_business_mutations_flush_before_usage_dirty_scope(self) -> None:
        store = _ScopedCommitStore()
        router = ApiRouter(SystemService(store))

        response = router.dispatch(
            "POST",
            "/api/ingestion/sources/seed",
            {},
            role="data_engineer",
            origin="scheduled",
        )

        self.assertTrue(response.success, response.error)
        self.assertTrue(store.persisted_source_ids)
        self.assertIn(("__all__",), store.commit_scopes)
        self.assertEqual(store.commit_scopes[-1], ("usage_metric",))

    def test_failed_usage_commit_rolls_back_in_memory_metric_without_failing_business_request(self) -> None:
        store = _TelemetryFailStore()
        router = ApiRouter(SystemService(store))

        response = router.dispatch(
            "POST",
            "/api/ingestion/sources/seed",
            {},
            role="data_engineer",
            origin="scheduled",
        )

        self.assertTrue(response.success, response.error)
        self.assertTrue(store.persisted_source_ids)
        self.assertEqual(store.usage_metrics, {})

    def test_postgres_commit_failure_restores_hashes_and_retry_persists_records_and_audit(self) -> None:
        database = _RollbackOnceDatabase()
        store = PostgreSQLStore("postgresql://example.invalid/ai_quant", connect=database.connect)
        metric = UsageMetric(feature="retry", hit_count=1)
        event = AuditEvent(
            event_id="evt_retry",
            actor="platform",
            action="retry",
            resource_type="usage_metric",
            resource_id="retry",
            source="api",
        )
        store.usage_metrics[metric.feature] = metric
        store.audit_log.append(event)
        store.mark_dirty_for_resource("usage_metric")
        database.fail_next_commit = True

        with self.assertRaisesRegex(RuntimeError, "transaction commit failed"):
            store.commit_all()

        self.assertNotIn(("usage_metrics", metric.feature), database.records)
        self.assertNotIn(event.event_id, database.audit)
        self.assertNotIn(("usage_metrics", metric.feature), store._record_hashes)
        self.assertNotIn(event.event_id, store._audit_hashes)
        self.assertIn("usage_metrics", store._dirty_collections)

        store.commit_all()

        self.assertIn(("usage_metrics", metric.feature), database.records)
        self.assertIn(event.event_id, database.audit)

    def test_dispatch_serializes_shared_store_write_boundaries(self) -> None:
        store = _ConcurrentCommitStore()
        router = _BlockingWriteRouter(SystemService(store))
        responses = []

        first = Thread(
            target=lambda: responses.append(
                router.dispatch("POST", router.PATH, {"marker": "first"}, role="system")
            )
        )
        second_started = Event()

        def run_second() -> None:
            second_started.set()
            responses.append(router.dispatch("POST", router.PATH, {"marker": "second"}, role="system"))

        second = Thread(target=run_second)
        first.start()
        self.assertTrue(router.first_entered.wait(timeout=1))
        second.start()
        self.assertTrue(second_started.wait(timeout=1))
        self.assertFalse(router.second_entered.wait(timeout=0.1))
        router.release_first.set()
        first.join(timeout=2)
        second.join(timeout=2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertTrue(router.second_entered.is_set())
        self.assertEqual(store.persisted, {"first", "second"})
        self.assertEqual(len(responses), 2)
        self.assertTrue(all(response.success for response in responses))


if __name__ == "__main__":
    unittest.main()
