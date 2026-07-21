from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from scripts.reconcile_research_report_state import (
    _sanitize_error,
    analyze_reconciliation,
    inspect_backup_manifest,
    inventory_filesystem,
    inventory_opensearch,
    inventory_postgres,
    inventory_s3,
)


class FakeCursor:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.current: object = []
        self.queries: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _params: object = None) -> None:
        self.queries.append(query)
        self.current = self.responses.pop(0)

    def fetchall(self) -> list[object]:
        return list(self.current) if isinstance(self.current, list) else []

    def fetchone(self) -> object:
        return self.current


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


class ResearchReportReconciliationTests(unittest.TestCase):
    def test_filesystem_inventory_counts_only_in_scope_files_and_builds_alias_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "desk" / "2026").mkdir(parents=True)
            (root / "desk" / "2026" / "one.pdf").write_bytes(b"pdf")
            (root / "desk" / "two.txt").write_text("text", encoding="utf-8")
            (root / "desk" / "image.png").write_bytes(b"png")

            result, ids_by_alias = inventory_filesystem(
                root,
                extensions={".pdf", ".txt"},
                registry_root_aliases=["/data/local/research_reports"],
            )

            self.assertEqual(result["availability"], "available")
            self.assertEqual(result["counts"]["all_files"], 3)
            self.assertEqual(result["counts"]["eligible_report_files"], 2)
            self.assertEqual(result["counts"]["out_of_scope_files"], 1)
            self.assertFalse(result["identifier_policy"]["content_hashing_performed"])
            self.assertEqual(len(ids_by_alias["/data/local/research_reports"]), 2)
            self.assertTrue((root / "desk" / "2026" / "one.pdf").exists())

    def test_postgres_inventory_uses_selects_and_reports_referential_gaps(self) -> None:
        cursor = FakeCursor(
            [
                [
                    ("research_reports", 2),
                    ("documents", 2),
                    ("evidence", 2),
                    ("structured_research_reports", 0),
                ],
                [
                    ("rr_one", "text_indexed", "doc_one", "/reports/one.pdf", "fp1", "sha1"),
                    ("rr_two", "indexed", "doc_missing", "/reports/two.pdf", "fp2", ""),
                ],
                [("doc_one", "research-report://rr_one"), ("doc_orphan", "research-report://rr_old")],
                (2, 2, ["doc_one", "doc_citation_missing"]),
            ]
        )

        result, report_ids = inventory_postgres(
            "postgresql://user:secret@db:5432/ai_quant",
            connect_fn=lambda *_args, **_kwargs: FakeConnection(cursor),
        )

        self.assertEqual(result["availability"], "available")
        self.assertEqual(report_ids, {"rr_one", "rr_two"})
        self.assertEqual(result["research_asset_status_counts"], {"indexed": 1, "text_indexed": 1})
        self.assertEqual(result["referential_integrity"]["report_document_ids_missing_document"], 1)
        self.assertEqual(result["referential_integrity"]["research_documents_without_report_reference"], 1)
        self.assertEqual(result["referential_integrity"]["citation_document_ids_missing_document"], 1)
        self.assertNotIn("secret", json.dumps(result))
        self.assertTrue(all(query.lstrip().upper().startswith("SELECT") for query in cursor.queries))

    def test_opensearch_inventory_separates_resource_types_and_deleted_docs(self) -> None:
        def send(request: object) -> bytes:
            url = str(getattr(request, "full_url"))
            if url.endswith("/_count"):
                return json.dumps({"count": 12}).encode()
            if url.endswith("/_search"):
                return json.dumps(
                    {
                        "aggregations": {
                            "resource_types": {
                                "buckets": [
                                    {"key": "research_report", "doc_count": 5},
                                    {"key": "document", "doc_count": 4},
                                    {"key": "evidence", "doc_count": 3},
                                ]
                            }
                        }
                    }
                ).encode()
            if url.endswith("/_stats/docs,store"):
                return json.dumps(
                    {"_all": {"primaries": {"docs": {"count": 12, "deleted": 7}, "store": {"size_in_bytes": 99}}}}
                ).encode()
            raise AssertionError(url)

        result = inventory_opensearch(
            "http://search:9200",
            "research",
            username="user",
            password="secret",
            http_send=send,
        )

        self.assertEqual(result["availability"], "available")
        self.assertEqual(result["counts"]["live_documents"], 12)
        self.assertEqual(result["counts"]["deleted_documents"], 7)
        self.assertEqual(result["resource_type_counts"]["research_report"], 5)
        self.assertNotIn("secret", json.dumps(result))

    def test_s3_inventory_paginates_without_exposing_keys_or_credentials(self) -> None:
        requests: list[object] = []

        def send(request: object) -> bytes:
            requests.append(request)
            url = str(getattr(request, "full_url"))
            if "continuation-token" not in url:
                return b"""
                    <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
                      <IsTruncated>true</IsTruncated>
                      <NextContinuationToken>next-token</NextContinuationToken>
                      <Contents><Key>raw/local_research_goldman/doc.txt</Key><Size>10</Size></Contents>
                    </ListBucketResult>
                """
            return b"""
                <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
                  <IsTruncated>false</IsTruncated>
                  <Contents><Key>raw/operating_reports/run.pdf</Key><Size>20</Size></Contents>
                </ListBucketResult>
            """

        result = inventory_s3(
            endpoint_url="http://minio:9000",
            bucket="bucket",
            prefix="raw",
            access_key="access-secret",
            secret_key="secret-secret",
            region="us-east-1",
            http_send=send,
        )

        self.assertEqual(result["availability"], "available")
        self.assertEqual(result["counts"]["objects"], 2)
        self.assertEqual(result["counts"]["research_named_namespace_objects"], 1)
        self.assertEqual(result["size_bytes"], 30)
        self.assertEqual(result["top_namespace_counts"]["local_research_goldman"], 1)
        self.assertNotIn("doc.txt", json.dumps(result))
        self.assertNotIn("secret-secret", json.dumps(result))
        self.assertTrue(all(getattr(item, "method") == "GET" for item in requests))

    def test_reconciliation_never_marks_deletion_or_automatic_recovery_safe(self) -> None:
        filesystem = {
            "availability": "available",
            "counts": {"eligible_report_files": 1},
        }
        postgres = {
            "availability": "available",
            "collection_counts": {"research_reports": 0},
            "referential_integrity": {},
        }
        opensearch = {
            "availability": "available",
            "resource_type_counts": {"research_report": 1},
        }
        object_store = {"availability": "available"}
        baseline = {
            "availability": "available",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "reported_counts": {"research_reports": 1},
        }
        backup = {
            "availability": "available",
            "restore_verified": True,
            "dump_exists": True,
            "dump_size_matches_manifest": True,
            "research_collection_count_recorded": False,
        }

        findings, summary, recovery = analyze_reconciliation(
            filesystem=filesystem,
            filesystem_ids_by_alias={"/reports": {"rr_one"}},
            postgres=postgres,
            postgres_report_ids=set(),
            opensearch=opensearch,
            object_store=object_store,
            historical_baseline=baseline,
            backup=backup,
        )

        self.assertEqual(summary["highest_severity"], "critical")
        self.assertIn("raw_registry_drift", {item["finding_id"] for item in findings})
        self.assertFalse(recovery["safe_to_delete_raw_reports"])
        self.assertFalse(recovery["safe_to_delete_search_index"])
        self.assertFalse(recovery["automatic_recovery_authorized"])
        self.assertFalse(recovery["backup_protects_current_research_state"])
        self.assertEqual(recovery["recovery_readiness"], "blocked_missing_collection_aware_rollback_evidence")

    def test_zero_state_collection_backup_allows_clone_review_but_not_historical_recovery(self) -> None:
        filesystem = {"availability": "available", "counts": {"eligible_report_files": 1}}
        postgres = {
            "availability": "available",
            "collection_counts": {"research_reports": 0},
            "referential_integrity": {},
        }
        opensearch = {"availability": "available", "resource_type_counts": {"research_report": 1}}
        object_store = {"availability": "available"}
        baseline = {
            "availability": "available",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "reported_counts": {"research_reports": 1},
        }
        backup = {
            "availability": "available",
            "restore_verified": True,
            "dump_exists": True,
            "dump_size_matches_manifest": True,
            "source_restore_counts_match": True,
            "collection_restore_counts_match": True,
            "research_collection_count_recorded": True,
            "research_report_count_in_backup": 0,
        }

        _findings, _summary, recovery = analyze_reconciliation(
            filesystem=filesystem,
            filesystem_ids_by_alias={"/reports": {"rr_one"}},
            postgres=postgres,
            postgres_report_ids=set(),
            opensearch=opensearch,
            object_store=object_store,
            historical_baseline=baseline,
            backup=backup,
        )

        self.assertTrue(recovery["backup_protects_current_research_state"])
        self.assertFalse(recovery["backup_protects_expected_research_state"])
        self.assertEqual(recovery["recovery_readiness"], "clone_pilot_review_required")
        self.assertFalse(recovery["automatic_recovery_authorized"])

    def test_backup_manifest_records_restore_matched_research_collection_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dump = root / "backup.dump"
            dump.write_bytes(b"dump")
            manifest = root / "backup.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "dump_path": str(dump),
                        "dump_size_bytes": 4,
                        "restore_verified": True,
                        "source_counts": {"records": 10},
                        "restored_counts": {"records": 10},
                        "collection_counts": {"research_reports": 0},
                        "restored_collection_counts": {"research_reports": 0},
                    }
                ),
                encoding="utf-8",
            )

            result = inspect_backup_manifest(manifest)

        self.assertTrue(result["restore_verified"])
        self.assertTrue(result["dump_size_matches_manifest"])
        self.assertTrue(result["research_collection_count_recorded"])
        self.assertTrue(result["collection_restore_counts_match"])

    def test_backup_manifest_without_research_collection_counts_is_not_collection_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dump = root / "backup.dump"
            dump.write_bytes(b"dump")
            manifest = root / "backup.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "dump_path": str(dump),
                        "dump_size_bytes": 4,
                        "restore_verified": True,
                        "source_counts": {"records": 10},
                        "restored_counts": {"records": 10},
                    }
                ),
                encoding="utf-8",
            )

            result = inspect_backup_manifest(manifest)

        self.assertFalse(result["research_collection_count_recorded"])
        self.assertFalse(result["collection_restore_counts_match"])

    def test_backup_manifest_resolves_relocated_dump_from_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dump = root / "backup.dump"
            dump.write_bytes(b"dump")
            manifest = root / "backup.manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "dump_path": "/different/host/path/backup.dump",
                        "dump_size_bytes": 4,
                        "restore_verified": True,
                        "source_counts": {"records": 10},
                        "restored_counts": {"records": 10},
                    }
                ),
                encoding="utf-8",
            )

            result = inspect_backup_manifest(manifest)

        self.assertTrue(result["dump_exists"])
        self.assertTrue(result["dump_size_matches_manifest"])
        self.assertEqual(result["dump_path_resolution"], "manifest_sibling_relocated_environment")

    def test_error_sanitizer_removes_credentials_and_signed_values(self) -> None:
        raw = RuntimeError(
            "postgresql://user:pass@db/ai_quant?password=hunter2 X-Amz-Signature=abc123 token=xyz"
        )
        sanitized = _sanitize_error(raw, ["hunter2"])
        self.assertNotIn("user:pass", sanitized)
        self.assertNotIn("hunter2", sanitized)
        self.assertNotIn("abc123", sanitized)
        self.assertNotIn("token=xyz", sanitized)


if __name__ == "__main__":
    unittest.main()
