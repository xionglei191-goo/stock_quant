from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.build_research_report_registry_decision import (
    RIGHTS_POLICY,
    build_identity_manifest,
    build_recovery_decision,
    inventory_backup_manifests,
    inventory_opensearch_ids,
    inventory_postgres,
)


class _FakeCursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.statements.append(" ".join(statement.split()))

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows


class _FakeConnection:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.cursor_value = _FakeCursor(rows)

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return self.cursor_value


class ResearchReportRegistryDecisionTests(unittest.TestCase):
    def _files(self, root: Path) -> None:
        fixtures = {
            "BrokerA/2026/one.txt": b"first local opinion",
            "BrokerA/2026/two.txt": b"duplicate local opinion",
            "BrokerB/2026/copy.txt": b"duplicate local opinion",
            "BrokerB/2026/three.txt": b"third local opinion",
        }
        for relative, body in fixtures.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

    def _baseline(self) -> dict[str, object]:
        return {
            "availability": "available",
            "artifact_name": "historical.json",
            "research_reports": 4,
            "research_documents": 4,
            "citation_evidence": 10,
        }

    def test_full_manifest_is_stable_path_redacted_and_detects_duplicates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._files(root)
            first = build_identity_manifest(
                root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
            )
            second = build_identity_manifest(
                root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
            )

        self.assertEqual(first["integrity"]["manifest_sha256"], second["integrity"]["manifest_sha256"])
        self.assertEqual(first["summary"]["eligible_report_files"], 4)
        self.assertEqual(first["summary"]["content_hash_coverage_rate"], 1.0)
        self.assertEqual(first["summary"]["duplicate_content_group_count"], 1)
        self.assertEqual(first["summary"]["duplicate_alias_count"], 1)
        self.assertEqual(first["summary"]["report_id_collision_count"], 0)
        rendered = json.dumps(first, ensure_ascii=False)
        self.assertNotIn(temp_dir, rendered)
        self.assertNotIn("one.txt", rendered)
        self.assertNotIn("BrokerA", rendered)
        self.assertNotIn("relative_path\"", rendered)
        self.assertTrue(all(len(item["content_sha256"]) == 64 for item in first["entries"]))
        self.assertEqual(first["rights_policy"], RIGHTS_POLICY)

    def test_postgres_inventory_uses_read_only_transaction_and_redacts_dsn(self) -> None:
        connection = _FakeConnection(
            [("rr_one", "a" * 64, dict(RIGHTS_POLICY))]
        )
        result = inventory_postgres(
            "postgresql://user:topsecret@database.internal:5432/ai_quant",
            connect=lambda _dsn: connection,
        )

        self.assertEqual(result["availability"], "available")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["connection"]["endpoint"], "postgresql://database.internal:5432")
        self.assertEqual(connection.cursor_value.statements[0], "SET TRANSACTION READ ONLY")
        self.assertTrue(connection.cursor_value.statements[1].startswith("SELECT"))
        self.assertNotIn("topsecret", json.dumps(result))

    def test_opensearch_inventory_paginates_report_ids(self) -> None:
        calls: list[dict[str, object]] = []

        def request_json(_url: str, body: dict[str, object]) -> dict[str, object]:
            calls.append(body)
            if "search_after" not in body:
                return {
                    "hits": {
                        "total": {"value": 3, "relation": "eq"},
                        "hits": [
                            {"_source": {"resource_id": "rr_a"}, "sort": ["rr_a"]},
                            {"_source": {"resource_id": "rr_b"}, "sort": ["rr_b"]},
                        ],
                    }
                }
            return {
                "hits": {
                    "total": {"value": 3, "relation": "eq"},
                    "hits": [{"_source": {"resource_id": "rr_c"}, "sort": ["rr_c"]}],
                }
            }

        result = inventory_opensearch_ids(
            "http://opensearch:9200",
            "index",
            page_size=2,
            request_json=request_json,
        )

        self.assertEqual(result["availability"], "available")
        self.assertEqual(result["report_ids"], ["rr_a", "rr_b", "rr_c"])
        self.assertEqual(calls[1]["search_after"], ["rr_b"])
        self.assertEqual(calls[0]["query"], {"term": {"resource_type.keyword": "research_report"}})

    def test_backup_inventory_rejects_registry_only_clone_as_historical_state(self) -> None:
        now = datetime.now(timezone.utc)
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "clone.manifest.json"
            counts = {
                "research_reports": 4,
                "research_documents": 1,
                "research_report_citation_evidence": 2,
            }
            path.write_text(
                json.dumps(
                    {
                        "restore_verified": True,
                        "retained_until": (now + timedelta(days=7)).isoformat(),
                        "source_db": "ai_quant_clone",
                        "research_state_coverage": "current_point_in_time_only_not_historical_coverage_proof",
                        "collection_counts": counts,
                        "restored_collection_counts": counts,
                    }
                ),
                encoding="utf-8",
            )
            result = inventory_backup_manifests(
                [path],
                expected_reports=4,
                expected_documents=4,
                expected_evidence=10,
                current_reports=1,
                now=now,
            )

        self.assertEqual(result["historical_complete_state_candidate_count"], 0)
        self.assertEqual(result["registry_only_candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["source_database_role"], "clone")

    def test_decision_preserves_current_rows_excludes_duplicate_aliases_and_never_authorizes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._files(root)
            manifest = build_identity_manifest(
                root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
            )
        current = manifest["entries"][0]
        postgres = {
            "availability": "available",
            "count": 1,
            "rows": [
                {
                    "report_id": current["report_id"],
                    "content_sha256": current["content_sha256"],
                    "rights_tag": dict(RIGHTS_POLICY),
                }
            ],
        }
        opensearch = {
            "availability": "available",
            "count": 4,
            "report_ids": sorted(item["report_id"] for item in manifest["entries"]),
        }
        backups = {
            "historical_complete_state_candidate_count": 0,
            "current_registry_rollback_candidate_count": 1,
            "registry_only_candidate_count": 1,
            "candidates": [],
        }

        decision = build_recovery_decision(
            manifest,
            postgres=postgres,
            opensearch=opensearch,
            baseline=self._baseline(),
            backups=backups,
            batch_size=2,
        )

        self.assertEqual(decision["status"], "ready_for_manual_strategy_review")
        self.assertFalse(decision["execution_authorized"])
        self.assertFalse(decision["historical_state_assessment"]["historical_complete_backup_available"])
        self.assertTrue(decision["historical_state_assessment"]["reparse_required"])
        self.assertEqual(decision["recovery_plan"]["excluded_current_exact_count"], 1)
        self.assertEqual(decision["recovery_plan"]["excluded_duplicate_alias_count"], 1)
        self.assertEqual(decision["recovery_plan"]["candidate_report_count"], 2)
        self.assertEqual(decision["recovery_plan"]["batch_count"], 1)
        self.assertEqual(
            set(decision["failed_execution_gate_ids"]),
            {"new_pre_execute_collection_backup", "independent_clone_double_run", "manual_approval_recorded"},
        )
        self.assertFalse(decision["recovery_plan"]["write_contract"]["primary_writes_allowed"])

    def test_content_conflict_blocks_planning(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._files(root)
            manifest = build_identity_manifest(
                root,
                registry_root=Path("/data/local/research_reports"),
                extensions={".txt"},
            )
        current = manifest["entries"][0]
        decision = build_recovery_decision(
            manifest,
            postgres={
                "availability": "available",
                "count": 1,
                "rows": [
                    {
                        "report_id": current["report_id"],
                        "content_sha256": "0" * 64,
                        "rights_tag": dict(RIGHTS_POLICY),
                    }
                ],
            },
            opensearch={
                "availability": "available",
                "count": 4,
                "report_ids": sorted(item["report_id"] for item in manifest["entries"]),
            },
            baseline=self._baseline(),
            backups={
                "historical_complete_state_candidate_count": 0,
                "current_registry_rollback_candidate_count": 1,
                "registry_only_candidate_count": 0,
                "candidates": [],
            },
            batch_size=2,
        )

        self.assertEqual(decision["status"], "inventory_review_blocked")
        self.assertEqual(decision["identity_comparison"]["postgres_content_conflict_count"], 1)
        self.assertIn("postgres_content_conflict_free", decision["failed_execution_gate_ids"])


if __name__ == "__main__":
    unittest.main()
