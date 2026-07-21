from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models import AuditEvent, SourceDefinition
from app.store import COLLECTIONS, PostgreSQLStore, SQLiteStore
from scripts.migrate_sqlite_to_postgres import migrate_sqlite_to_postgres
from tests.support import _FakePostgresDatabase


def _source(source_id: str, description: str) -> SourceDefinition:
    return SourceDefinition.from_dict(
        {
            "source_id": source_id,
            "source_type": "regulatory",
            "description": description,
            "rights_tag": {
                "license_class": "public",
                "training_allowed": False,
                "redistribution_allowed": False,
                "display_use": "allowed",
                "non_display_use": "restricted",
                "derived_data_use": "restricted",
            },
        }
    )


def _audit(event_id: str, resource_id: str) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        actor="migration-test",
        action="register",
        resource_type="source",
        resource_id=resource_id,
        source="test",
        timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )


class SQLitePostgresMigrationGuardTests(unittest.TestCase):
    def _seed_sqlite(self, path: Path) -> None:
        store = SQLiteStore(path)
        store.sources = {
            "shared": _source("shared", "source version"),
            "source_only": _source("source_only", "source only"),
        }
        store.audit_log = [_audit("audit_source", "source_only")]
        store.commit()

    def _seed_postgres(self, database: _FakePostgresDatabase, dsn: str) -> None:
        store = PostgreSQLStore(dsn, connect=database.connect)
        store.sources = {
            "shared": _source("shared", "target version"),
            "target_only": _source("target_only", "target only"),
        }
        store.audit_log = [_audit("audit_target", "target_only")]
        store.mark_dirty_for_resource("sources")
        store.commit()

    def _backup_manifest(
        self,
        root: Path,
        *,
        records: int,
        audit_log: int,
        market_data_bars: int = 0,
    ) -> Path:
        dump = root / "target.dump"
        dump.write_bytes(b"restore-verified-test-dump")
        counts = {
            "records": records,
            "audit_log": audit_log,
            "market_data_bars": market_data_bars,
        }
        manifest = root / "target.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "restore_verified": True,
                    "source_db": "ai_quant",
                    "dump_path": str(dump),
                    "dump_size_bytes": dump.stat().st_size,
                    "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                    "retained_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                    "source_counts": counts,
                    "restored_counts": counts,
                    "source_database_manifest": {"table_counts": counts},
                    "restored_database_manifest": {"table_counts": counts},
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_missing_sqlite_source_is_rejected_before_target_connection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.db"
            database = _FakePostgresDatabase()

            with self.assertRaisesRegex(FileNotFoundError, "SQLite migration source does not exist"):
                migrate_sqlite_to_postgres(
                    missing,
                    "postgresql://example.invalid/ai_quant",
                    connect=database.connect,
                )

        self.assertEqual(database.dsns, [])

    def test_default_preflight_reports_each_collection_and_does_not_mutate_target(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "state.db"
            self._seed_sqlite(sqlite_path)
            database = _FakePostgresDatabase()
            dsn = "postgresql://user:p%40ss@example.invalid/ai_quant?sslpassword=hidden"
            self._seed_postgres(database, dsn)
            records_before = deepcopy(database.records)
            audit_before = deepcopy(database.audit)
            statement_start = len(database.statements)

            summary = migrate_sqlite_to_postgres(sqlite_path, dsn, connect=database.connect)

        self.assertEqual(summary["mode"], "preflight")
        self.assertFalse(summary["executed"])
        self.assertEqual(summary["postgres_dsn"], "postgresql://user:***@example.invalid/ai_quant?***")
        self.assertNotIn("p%40ss", json.dumps(summary))
        self.assertNotIn("hidden", json.dumps(summary))
        self.assertEqual(summary["preflight"]["collections"]["sources"]["source_count"], 2)
        self.assertEqual(summary["preflight"]["collections"]["sources"]["target_count"], 2)
        self.assertEqual(set(summary["preflight"]["collections"]), {item[0] for item in COLLECTIONS})
        self.assertEqual(database.records, records_before)
        self.assertEqual(database.audit, audit_before)
        statements = "\n".join(database.statements[statement_start:]).upper()
        self.assertNotIn("DELETE FROM", statements)

    def test_merge_is_insert_only_and_preserves_target_conflicts_and_audit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "state.db"
            self._seed_sqlite(sqlite_path)
            database = _FakePostgresDatabase()
            dsn = "postgresql://example.invalid/ai_quant"
            self._seed_postgres(database, dsn)
            statement_start = len(database.statements)

            summary = migrate_sqlite_to_postgres(
                sqlite_path,
                dsn,
                mode="merge",
                connect=database.connect,
            )
            reloaded = PostgreSQLStore(dsn, connect=database.connect)

        self.assertTrue(summary["executed"])
        self.assertEqual(summary["result"]["strategy"], "insert_only_target_wins_conflicts")
        self.assertEqual(summary["result"]["inserted_counts"]["sources"], 1)
        self.assertEqual(summary["result"]["preserved_conflict_counts"]["sources"], 1)
        self.assertEqual(reloaded.sources["shared"].description, "target version")
        self.assertIn("target_only", reloaded.sources)
        self.assertIn("source_only", reloaded.sources)
        self.assertEqual({event.event_id for event in reloaded.audit_log}, {"audit_source", "audit_target"})
        statements = "\n".join(database.statements[statement_start:]).upper()
        self.assertNotIn("DELETE FROM", statements)

    def test_exact_replace_rejects_loss_without_evidence_and_leaves_target_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "state.db"
            self._seed_sqlite(sqlite_path)
            database = _FakePostgresDatabase()
            dsn = "postgresql://example.invalid/ai_quant"
            self._seed_postgres(database, dsn)
            records_before = deepcopy(database.records)
            audit_before = deepcopy(database.audit)

            preflight = migrate_sqlite_to_postgres(sqlite_path, dsn, connect=database.connect)
            with self.assertRaisesRegex(RuntimeError, "required_exact_replace_confirmation"):
                migrate_sqlite_to_postgres(
                    sqlite_path,
                    dsn,
                    mode="exact-replace",
                    connect=database.connect,
                )

        self.assertTrue(preflight["preflight"]["requires_loss_acknowledgement"])
        self.assertGreater(preflight["preflight"]["prospective_loss"]["total_affected"], 0)
        self.assertEqual(database.records, records_before)
        self.assertEqual(database.audit, audit_before)

    def test_exact_replace_requires_backup_coverage_then_allows_intentional_replacement(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sqlite_path = root / "state.db"
            self._seed_sqlite(sqlite_path)
            database = _FakePostgresDatabase()
            dsn = "postgresql://example.invalid/ai_quant"
            self._seed_postgres(database, dsn)
            preflight = migrate_sqlite_to_postgres(sqlite_path, dsn, connect=database.connect)
            confirmation = preflight["preflight"]["required_exact_replace_confirmation"]
            insufficient = self._backup_manifest(root, records=1, audit_log=1)

            with self.assertRaisesRegex(RuntimeError, "records count does not exactly match"):
                migrate_sqlite_to_postgres(
                    sqlite_path,
                    dsn,
                    mode="exact-replace",
                    confirm_exact_replace=confirmation,
                    backup_manifest=insufficient,
                    connect=database.connect,
                )

            valid = self._backup_manifest(root, records=2, audit_log=1)
            summary = migrate_sqlite_to_postgres(
                sqlite_path,
                dsn,
                mode="exact-replace",
                confirm_exact_replace=confirmation,
                backup_manifest=valid,
                connect=database.connect,
            )
            reloaded = PostgreSQLStore(dsn, connect=database.connect)

        self.assertTrue(summary["backup_validation"]["dump_sha256_verified"])
        self.assertTrue(summary["backup_validation"]["target_count_coverage"]["records"]["covered"])
        self.assertEqual(reloaded.sources["shared"].description, "source version")
        self.assertIn("source_only", reloaded.sources)
        self.assertNotIn("target_only", reloaded.sources)
        self.assertEqual([event.event_id for event in reloaded.audit_log], ["audit_source"])

    def test_exact_replace_rejects_backup_from_another_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            sqlite_path = root / "source.db"
            self._seed_sqlite(sqlite_path)
            database = _FakePostgresDatabase()
            dsn = "postgresql://example.invalid/ai_quant"
            self._seed_postgres(database, dsn)
            preflight = migrate_sqlite_to_postgres(sqlite_path, dsn, connect=database.connect)
            manifest_path = self._backup_manifest(root, records=2, audit_log=1)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_db"] = "another_database"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "source_db must exactly match"):
                migrate_sqlite_to_postgres(
                    sqlite_path,
                    dsn,
                    mode="exact-replace",
                    confirm_exact_replace=preflight["preflight"]["required_exact_replace_confirmation"],
                    backup_manifest=manifest_path,
                    connect=database.connect,
                )


if __name__ == "__main__":
    unittest.main()
