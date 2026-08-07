"""Daily mainline store wiring tests (COLLECTIONS registration + round-trip, design §3.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models import DailyMainlineQueueItem, DailyMainlineRun, DailyWatchlistEntry
from app.store import (
    COLLECTIONS,
    InMemoryStore,
    PostgreSQLStore,
    SQLiteStore,
    _candidate_collections_for_resource,
)
from tests.support import SystemServiceTestBase, _FakePostgresDatabase


EXPECTED_SPECS = (
    ("daily_mainline_runs", "run_id", DailyMainlineRun),
    ("daily_mainline_queue_items", "item_id", DailyMainlineQueueItem),
    ("daily_watchlist_entries", "entry_id", DailyWatchlistEntry),
)

NEW_DASHBOARD_COUNT_KEYS = tuple(collection for collection, _key_field, _model_type in EXPECTED_SPECS)

# Dashboard `counts` contract as it stood before design §9 risk 2 was implemented:
# the three new keys are additive, none of these pre-existing keys may disappear.
PRE_EXISTING_DASHBOARD_COUNT_KEYS = (
    "sources",
    "astock_connectors",
    "ingestion_jobs",
    "ingestion_schedules",
    "issuers",
    "securities",
    "market_data",
    "corporate_actions",
    "institutional_holdings",
    "disclosure_events",
    "documents",
    "evidence",
    "research_report_citation_evidence",
    "manual_reviews",
    "open_manual_reviews",
    "benchmark_samples",
    "benchmark_runs",
    "extraction_results",
    "research_answers",
    "research_reports",
    "llm_task_templates",
    "llm_task_runs",
    "workflow_definitions",
    "workflow_runs",
    "lineage_events",
    "model_versions",
    "secret_rotations",
    "cache_retention_runs",
    "theses",
    "signals",
    "decisions",
    "pending_decisions",
    "approved_decisions",
    "execution_intents",
    "simulated_executions",
    "portfolio_transactions",
    "reviews",
    "operating_reports",
    "strategy_replays",
    "portfolio_proposals",
    "open_exceptions",
    "source_review_overdue",
    "source_review_due_soon",
    "source_review_missing",
    "sensitive_findings",
    "research_answer_pending_reviews",
    "permission_denied_events",
    "alert_rules",
    "open_alerts",
    "alert_notifications",
)


def _run(run_id: str, run_date: str = "2026-07-28") -> DailyMainlineRun:
    return DailyMainlineRun(
        run_id=run_id,
        run_date=run_date,
        status="partial",
        stages=[
            {"stage": "scan_market_disturbance", "status": "passed", "record_count": 3},
            {"stage": "run_auto_diligence", "status": "skipped", "reason_code": "diligence_budget_exhausted"},
        ],
        candidate_count=3,
        queue_count=2,
        unsupported_count=1,
        llm_run_ids=["llm_run_1"],
        failure_reason_codes=["diligence_budget_exhausted"],
        next_actions=[{"action": "rerun_diligence", "reason_code": "diligence_budget_exhausted", "endpoint": "/api/daily-mainline/run"}],
        timeout_seconds=600,
        elapsed_seconds=12.5,
        artifact_path=f"artifacts/daily-mainline/daily-mainline-{run_date}-{run_id}.json",
        created_at=datetime(2026, 7, 28, 1, 2, 3, 456789, tzinfo=timezone.utc),
    )


def _queue_item(item_id: str, run_id: str, *, partition: str = "researchable") -> DailyMainlineQueueItem:
    return DailyMainlineQueueItem(
        item_id=item_id,
        run_id=run_id,
        security_id="600519.SH",
        issuer_id="issuer_600519",
        ticker="600519",
        market="A",
        rank=1,
        selection_reason="单日涨跌幅 7.4% 超阈值",
        trigger_metric="one_day_return",
        trigger_value=0.074,
        as_of_date="2026-07-28",
        completeness_status="partial",
        missing_layers=["relationship_coverage"],
        partition=partition,
        viewpoint={"summary": "放量突破，等待证据补齐", "prompt_version": "daily-mainline-v1", "model": "test-model"},
        evidence_ids=["ev_1", "ev_2"],
        research_answer_id="answer_1",
        llm_task_run_id="llm_run_1",
        template_id="candidate_diligence",
        review_status="pending",
        diligence_status="generated" if partition == "researchable" else "unsupported",
        diligence_reason_code="" if partition == "researchable" else "evidence_missing",
        created_at=datetime(2026, 7, 28, 1, 2, 4, 123456, tzinfo=timezone.utc),
    )


def _watchlist_entry(entry_id: str, run_id: str, item_id: str) -> DailyWatchlistEntry:
    return DailyWatchlistEntry(
        entry_id=entry_id,
        security_id="600519.SH",
        run_id=run_id,
        item_id=item_id,
        selection_reason="单日涨跌幅 7.4% 超阈值",
        joined_at=datetime(2026, 7, 28, 2, 0, 0, tzinfo=timezone.utc),
        actor="analyst_1",
    )


def _seed(store: InMemoryStore) -> None:
    store.daily_mainline_runs = {"run_1": _run("run_1")}
    store.daily_mainline_queue_items = {
        "item_1": _queue_item("item_1", "run_1"),
        "item_2": _queue_item("item_2", "run_1", partition="pending_evidence"),
    }
    store.daily_watchlist_entries = {"entry_1": _watchlist_entry("entry_1", "run_1", "item_1")}


class DailyMainlineCollectionRegistrationTests(unittest.TestCase):
    def test_collections_declare_expected_key_field_and_model(self) -> None:
        registered = {collection: (key_field, model_type) for collection, key_field, model_type in COLLECTIONS}
        for collection, key_field, model_type in EXPECTED_SPECS:
            with self.subTest(collection=collection):
                self.assertIn(collection, registered)
                self.assertEqual(registered[collection], (key_field, model_type))

    def test_in_memory_store_exposes_a_dict_per_new_collection(self) -> None:
        store = InMemoryStore()
        for collection, _key_field, _model_type in EXPECTED_SPECS:
            with self.subTest(collection=collection):
                self.assertEqual(getattr(store, collection), {})

    def test_existing_collections_are_preserved(self) -> None:
        names = [collection for collection, _key_field, _model_type in COLLECTIONS]
        self.assertEqual(len(names), len(set(names)))
        for collection in ("sources", "observation_items", "usage_metrics", "llm_task_runs"):
            with self.subTest(collection=collection):
                self.assertIn(collection, names)


class DailyMainlineResourceLookupTests(unittest.TestCase):
    """The alias table needs no new entries: generic pluralisation already resolves all three."""

    def test_singular_resource_types_resolve_without_new_aliases(self) -> None:
        expectations = {
            "daily_mainline_run": "daily_mainline_runs",
            "daily-mainline-run": "daily_mainline_runs",
            "daily_mainline_queue_item": "daily_mainline_queue_items",
            "daily-mainline-queue-item": "daily_mainline_queue_items",
            "daily_watchlist_entry": "daily_watchlist_entries",
            "daily-watchlist-entry": "daily_watchlist_entries",
        }
        for resource_type, collection in expectations.items():
            with self.subTest(resource_type=resource_type):
                self.assertIn(collection, _candidate_collections_for_resource(resource_type))

    def test_plural_resource_types_resolve_to_themselves(self) -> None:
        for collection, _key_field, _model_type in EXPECTED_SPECS:
            with self.subTest(collection=collection):
                self.assertEqual(_candidate_collections_for_resource(collection), [collection])


class DailyMainlineSQLiteRoundTripTests(unittest.TestCase):
    def _assert_round_trip(self, store: InMemoryStore) -> None:
        run = store.daily_mainline_runs["run_1"]
        self.assertEqual(run, _run("run_1"))
        self.assertEqual(run.created_at, datetime(2026, 7, 28, 1, 2, 3, 456789, tzinfo=timezone.utc))
        self.assertEqual(store.daily_mainline_queue_items["item_1"], _queue_item("item_1", "run_1"))
        item_2 = store.daily_mainline_queue_items["item_2"]
        self.assertEqual(item_2.partition, "pending_evidence")
        self.assertEqual(item_2.diligence_status, "unsupported")
        self.assertEqual(item_2.viewpoint["prompt_version"], "daily-mainline-v1")
        entry = store.daily_watchlist_entries["entry_1"]
        self.assertEqual(entry, _watchlist_entry("entry_1", "run_1", "item_1"))
        self.assertEqual(entry.joined_at, datetime(2026, 7, 28, 2, 0, 0, tzinfo=timezone.utc))

    def test_records_partition_round_trips_every_new_collection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.db"
            store = SQLiteStore(path)
            _seed(store)
            store.commit()

            reloaded = SQLiteStore(path)

        self._assert_round_trip(reloaded)

    def test_same_day_runs_keep_separate_queues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.db"
            store = SQLiteStore(path)
            store.daily_mainline_runs = {"run_1": _run("run_1"), "run_2": _run("run_2")}
            store.daily_mainline_queue_items = {
                "item_1": _queue_item("item_1", "run_1"),
                "item_2": _queue_item("item_2", "run_2"),
            }
            store.commit()

            reloaded = SQLiteStore(path)

        self.assertEqual(sorted(reloaded.daily_mainline_runs), ["run_1", "run_2"])
        self.assertEqual(reloaded.daily_mainline_runs["run_1"].run_date, reloaded.daily_mainline_runs["run_2"].run_date)
        self.assertEqual(reloaded.daily_mainline_queue_items["item_1"].run_id, "run_1")
        self.assertEqual(reloaded.daily_mainline_queue_items["item_2"].run_id, "run_2")


class DailyMainlinePostgresRoundTripTests(unittest.TestCase):
    def test_records_partition_round_trips_under_postgres_store(self) -> None:
        database = _FakePostgresDatabase()
        dsn = "postgresql://example.invalid/ai_quant"
        store = PostgreSQLStore(dsn, connect=database.connect)
        _seed(store)
        for resource_type in ("daily_mainline_run", "daily_mainline_queue_item", "daily_watchlist_entry"):
            store.mark_dirty_for_resource(resource_type)
        store.commit()

        persisted = {key[0] for key in database.records}
        for collection, _key_field, _model_type in EXPECTED_SPECS:
            with self.subTest(collection=collection):
                self.assertIn(collection, persisted)

        reloaded = PostgreSQLStore(dsn, connect=database.connect)
        self.assertEqual(reloaded.daily_mainline_runs["run_1"], _run("run_1"))
        self.assertEqual(reloaded.daily_mainline_queue_items["item_1"], _queue_item("item_1", "run_1"))
        self.assertEqual(
            reloaded.daily_mainline_queue_items["item_2"],
            _queue_item("item_2", "run_1", partition="pending_evidence"),
        )
        self.assertEqual(reloaded.daily_watchlist_entries["entry_1"], _watchlist_entry("entry_1", "run_1", "item_1"))

    def test_dirty_marking_persists_new_collections_alongside_existing_ones(self) -> None:
        database = _FakePostgresDatabase()
        dsn = "postgresql://example.invalid/ai_quant"
        store = PostgreSQLStore(dsn, connect=database.connect)
        _seed(store)
        store.mark_dirty_for_resource("daily_mainline_run")
        store.commit()

        self.assertIn(("daily_mainline_runs", "run_1"), database.records)
        self.assertNotIn(("daily_mainline_queue_items", "item_1"), database.records)

        store.mark_dirty_for_resource("daily_mainline_queue_item")
        store.mark_dirty_for_resource("daily_watchlist_entry")
        store.commit()

        self.assertIn(("daily_mainline_queue_items", "item_1"), database.records)
        self.assertIn(("daily_watchlist_entries", "entry_1"), database.records)


class DailyMainlineDownstreamCollectionImpactTests(SystemServiceTestBase):
    """design §9 risk 2: new collections stay readable/writable and the dashboard counts them."""

    def test_new_collections_round_trip_through_declared_collections_specs(self) -> None:
        _seed(self.service.store)
        registered = {collection: key_field for collection, key_field, _model_type in COLLECTIONS}
        for collection in NEW_DASHBOARD_COUNT_KEYS:
            with self.subTest(collection=collection):
                key_field = registered[collection]
                records = getattr(self.service.store, collection)
                self.assertTrue(records)
                for key, record in records.items():
                    self.assertEqual(getattr(record, key_field), key)

    def test_dashboard_counts_add_new_keys_without_dropping_existing_ones(self) -> None:
        baseline = self.service.dashboard()["counts"]
        for key in PRE_EXISTING_DASHBOARD_COUNT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, baseline)
        for key in NEW_DASHBOARD_COUNT_KEYS:
            with self.subTest(key=key):
                self.assertEqual(baseline[key], 0)

        _seed(self.service.store)
        counts = self.service.dashboard()["counts"]
        self.assertEqual(set(baseline), set(counts))
        self.assertEqual(counts["daily_mainline_runs"], 1)
        self.assertEqual(counts["daily_mainline_queue_items"], 2)
        self.assertEqual(counts["daily_watchlist_entries"], 1)

    def test_dashboard_counts_are_not_derived_from_all_collections(self) -> None:
        counts = self.service.dashboard()["counts"]
        collection_names = {collection for collection, _key_field, _model_type in COLLECTIONS}
        self.assertTrue(collection_names - set(counts))
        self.assertNotIn("audit_log", counts)


class MigrationScriptCollectionCoverageTests(unittest.TestCase):
    """The sqlite→postgres migration derives its collection list from COLLECTIONS, so it needs no edit."""

    def test_migration_script_imports_collections_instead_of_hardcoding_them(self) -> None:
        source = Path("scripts/migrate_sqlite_to_postgres.py").read_text(encoding="utf-8")
        self.assertIn("from app.store import COLLECTIONS", source)
        for collection in NEW_DASHBOARD_COUNT_KEYS:
            with self.subTest(collection=collection):
                self.assertNotIn(f'"{collection}"', source)


if __name__ == "__main__":
    unittest.main()
