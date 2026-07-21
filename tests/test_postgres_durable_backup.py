from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import postgres_durable_backup as backup
from scripts.reconcile_research_report_state import inspect_backup_manifest


def _research_state(*, report_count: int = 2) -> dict[str, object]:
    counts = {
        "research_reports": report_count,
        "research_documents": report_count,
        "research_report_citation_evidence": report_count * 3,
        "structured_research_reports": report_count,
        "report_viewpoints": report_count,
        "report_forecasts": report_count * 2,
    }
    samples = {
        key: ["rr_z", "rr_a", "rr_a", "unsafe/path"]
        for key in backup.RESEARCH_STATE_COUNT_KEYS
    }
    return {"counts": counts, "report_id_samples": samples}


class PostgresDurableBackupTests(unittest.TestCase):
    def test_research_state_manifest_is_bounded_sorted_and_contains_ids_only(self) -> None:
        raw = _research_state()
        raw["report_id_samples"]["research_reports"] = [  # type: ignore[index]
            f"rr_{index:02d}" for index in range(40, -1, -1)
        ] + ["private/report.pdf"]

        result = backup._normalize_research_state(raw)

        samples = result["report_id_samples"]["research_reports"]  # type: ignore[index]
        self.assertEqual(samples, [f"rr_{index:02d}" for index in range(25)])
        self.assertEqual(result["sample_limit"], 25)
        self.assertNotIn("private/report.pdf", json.dumps(result))
        self.assertNotIn("file_path", json.dumps(result))
        self.assertIn("current database state", result["coverage_limitation"])

    def test_create_backup_requires_source_and_restored_database_manifest_equality(self) -> None:
        scalar_queries: list[tuple[str, str]] = []

        def fake_scalar(database: str, sql: str, **_kwargs: object) -> str:
            scalar_queries.append((database, sql))
            if "jsonb_build_object" in sql:
                return json.dumps(_research_state())
            if "audit_log" in sql:
                return "11"
            if "market_data_bars" in sql:
                return "22"
            return "33"

        compose_calls: list[tuple[str, ...]] = []

        def fake_compose(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            compose_calls.append(args)
            stdout = "postgres-container\n" if args[:3] == ("ps", "-q", "postgres") else ""
            return subprocess.CompletedProcess(["docker", "compose", *args], 0, stdout=stdout, stderr="")

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if command[:2] == ["docker", "cp"]:
                Path(command[-1]).write_bytes(b"test-dump")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(backup, "_scalar", side_effect=fake_scalar),
                patch.object(backup, "_compose", side_effect=fake_compose),
                patch.object(backup, "_run", side_effect=fake_run),
            ):
                result = backup.create_durable_backup(output_dir=temp_dir, timeout_seconds=5)
            manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
            reconciliation_view = inspect_backup_manifest(Path(result["manifest_path"]))

        self.assertTrue(result["restore_verified"])
        self.assertEqual(result["source_database_manifest"], result["restored_database_manifest"])
        self.assertEqual(result["collection_counts"]["research_reports"], 2)
        self.assertEqual(result["restored_collection_counts"], result["collection_counts"])
        self.assertEqual(
            result["source_database_manifest"]["research_state"]["report_id_samples"]["research_reports"],
            ["rr_a", "rr_z"],
        )
        self.assertEqual(manifest["research_state_coverage"], "current_point_in_time_only_not_historical_coverage_proof")
        self.assertTrue(reconciliation_view["research_collection_count_recorded"])
        self.assertEqual(reconciliation_view["research_report_count_in_backup"], 2)
        self.assertTrue(any("dropdb" in call for call in compose_calls))
        self.assertTrue(any("rm" in call for call in compose_calls))
        self.assertTrue(
            all(sql.lstrip().upper().startswith(("SELECT", "WITH")) for _database, sql in scalar_queries)
        )
        self.assertTrue(all("ai_quant_t602_restore" not in sql for _database, sql in scalar_queries))

    def test_collection_mismatch_fails_restore_verification_and_still_cleans_up(self) -> None:
        cleanup_calls: list[tuple[str, ...]] = []

        def fake_scalar(database: str, sql: str, **_kwargs: object) -> str:
            if "jsonb_build_object" in sql:
                report_count = 2 if database == "ai_quant" else 1
                return json.dumps(_research_state(report_count=report_count))
            return "1"

        def fake_compose(*args: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            cleanup_calls.append(args)
            stdout = "postgres-container\n" if args[:3] == ("ps", "-q", "postgres") else ""
            return subprocess.CompletedProcess(["docker", "compose", *args], 0, stdout=stdout, stderr="")

        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if command[:2] == ["docker", "cp"]:
                Path(command[-1]).write_bytes(b"test-dump")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(backup, "_scalar", side_effect=fake_scalar),
                patch.object(backup, "_compose", side_effect=fake_compose),
                patch.object(backup, "_run", side_effect=fake_run),
            ):
                with self.assertRaisesRegex(RuntimeError, "research_state"):
                    backup.create_durable_backup(output_dir=temp_dir, timeout_seconds=5)

        self.assertTrue(any("dropdb" in call for call in cleanup_calls))
        self.assertTrue(any("rm" in call for call in cleanup_calls))

    def test_unsafe_postgres_identifiers_are_rejected_before_compose(self) -> None:
        with patch.object(backup, "_compose") as compose:
            with self.assertRaisesRegex(ValueError, "source_db"):
                backup.create_durable_backup(output_dir="ignored", source_db="ai_quant;drop")
            with self.assertRaisesRegex(ValueError, "db_user"):
                backup.create_durable_backup(output_dir="ignored", db_user="ai-quant")
        compose.assert_not_called()

    def test_research_state_sql_is_read_only_and_uses_bounded_samples(self) -> None:
        normalized = " ".join(backup.RESEARCH_STATE_SQL.upper().split())
        self.assertTrue(normalized.startswith("WITH "))
        for mutation in (" INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ", " TRUNCATE "):
            self.assertNotIn(mutation, f" {normalized} ")
        self.assertEqual(normalized.count(f"LIMIT {backup.RESEARCH_STATE_SAMPLE_LIMIT}"), 6)


if __name__ == "__main__":
    unittest.main()
