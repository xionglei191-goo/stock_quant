from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.research_reports import report_id_for_path
from scripts.build_research_report_registry_decision import payload_sha256
from scripts.execute_research_report_clone_batch import (
    CloneBatchRefused,
    compare_with_prior_run,
    execute_batch,
    resolve_batch_paths,
    validate_execution_bundle,
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeClient:
    def __init__(self, report_ids: list[str]) -> None:
        self.report_ids = report_ids
        self.created: set[str] = set()
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append((method, path, dict(body or {})))
        if path == "/api/research-reports/scan":
            return {
                "indexed_count": len(self.report_ids),
                "reports": [{"report_id": item} for item in self.report_ids],
            }
        if path.startswith("/api/research-reports/batch-state?"):
            return {
                "missing_report_ids": [],
                "reports": [
                    {
                        "report_id": report_id,
                        "document_id": f"doc_{report_id}",
                        "content_sha256": next(
                            str(call_body.get("content_sha256") or "")
                            for method, call_path, call_body in self.calls
                            if method == "POST" and call_path == f"/api/research-reports/{report_id}/ingest"
                        ),
                        "document_content_sha256": next(
                            str(call_body.get("content_sha256") or "")
                            for method, call_path, call_body in self.calls
                            if method == "POST" and call_path == f"/api/research-reports/{report_id}/ingest"
                        ),
                        "status": "text_indexed",
                        "evidence_count": 1,
                        "manual_review": False,
                    }
                    for report_id in self.report_ids
                ],
            }
        if path == "/api/issuers":
            return {"issuer_id": "issuer_local_research_reference"}
        if path.endswith("/ingest"):
            report_id = path.split("/")[-2]
            created = report_id not in self.created
            self.created.add(report_id)
            content_hash = str((body or {}).get("content_sha256") or "")
            document_id = str((body or {}).get("document_id") or "")
            return {
                "created": created,
                "report": {"content_sha256": content_hash},
                "document": {"document_id": document_id, "content_sha256": content_hash},
            }
        if path.endswith("/extract"):
            report_id = path.split("/")[-2]
            return {
                "status": "text_indexed",
                "evidence": [{"evidence_id": f"evi_{report_id}"}],
                "manual_review": None,
            }
        raise AssertionError(path)


class ResearchReportCloneBatchExecutionTests(unittest.TestCase):
    def _plan_and_raw(self, root: Path) -> tuple[dict[str, object], Path]:
        raw = root / "raw"
        registry_root = Path("/data/local/research_reports")
        entries: list[dict[str, object]] = []
        for relative, body in {
            "Broker/one.txt": b"one opinion with evidence",
            "Broker/two.txt": b"two opinion with evidence",
        }.items():
            path = raw / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            relative_path = Path(relative)
            report_id = report_id_for_path(registry_root / relative_path)
            entries.append(
                {
                    "report_id": report_id,
                    "document_id": f"doc_{report_id}",
                    "content_sha256": hashlib.sha256(body).hexdigest(),
                    "relative_path_sha256": hashlib.sha256(relative_path.as_posix().encode()).hexdigest(),
                    "size_bytes": len(body),
                    "file_type": "txt",
                    "source_key": "source_demo",
                    "rights_policy_id": "local_research_reference_only_v1",
                }
            )
        entries.sort(key=lambda item: str(item["report_id"]))
        plan: dict[str, object] = {
            "schema_version": "research-report-clone-batch-plan-v1",
            "related_task": "T-614",
            "manifest_sha256": "a" * 64,
            "batch_id": "t613-batch-0001",
            "batch_sha256": "b" * 64,
            "raw_content_identity_sha256": "c" * 64,
            "backup_dump_sha256": "",
            "batch_entries": entries,
            "write_contract": {
                "target": "independently_attested_clone_only",
                "primary_writes_allowed": False,
                "insert_only": True,
                "updates_allowed": False,
                "deletes_allowed": False,
                "raw_files_preserved": True,
                "opensearch_preserved": True,
                "local_opinion_reference_only": True,
                "training_allowed": False,
                "broker_connected": False,
                "live_execution_allowed": False,
            },
        }
        return plan, raw

    def _runtime_bundle(self, root: Path) -> tuple[dict[str, object], Path, Path, Path]:
        plan, _raw = self._plan_and_raw(root)
        dump = root / "backup.dump"
        dump.write_bytes(b"restore verified")
        dump_sha = _file_sha256(dump)
        plan["backup_dump_sha256"] = dump_sha
        counts = {"records": 10, "audit_log": 20, "market_data_bars": 30}
        collections = {
            "research_reports": 15,
            "research_documents": 15,
            "research_report_citation_evidence": 112,
        }
        backup_path = root / "backup.manifest.json"
        backup_path.write_text(json.dumps({"dump_path": str(dump), "dump_sha256": dump_sha}), encoding="utf-8")

        now = datetime.now(timezone.utc)
        approval_path = root / "approval.json"
        approval_path.write_text(
            json.dumps(
                {
                    "schema_version": "research-report-clone-batch-approval-v1",
                    "status": "approved",
                    "approved_at": now.isoformat(),
                    "approved_by": "human_operator",
                    "manifest_sha256": "a" * 64,
                    "batch_id": "t613-batch-0001",
                    "batch_sha256": "b" * 64,
                    "scope": "isolated_clone_double_run_only",
                    "primary_writes_allowed": False,
                    "delete_operations_allowed": False,
                }
            ),
            encoding="utf-8",
        )

        plan_sha = payload_sha256(plan)
        database_name = "ai_quant_t614_clone_test"
        runtime_identity = {
            "app_container_id": "d" * 64,
            "app_container_hostname": "d" * 12,
            "app_image_id": "sha256:" + "1" * 64,
            "postgres_container_id": "e" * 64,
            "postgres_image_id": "sha256:" + "2" * 64,
            "isolated_network_id": "f" * 64,
            "database_oid": "16384",
            "postgres_system_identifier": "7612345678901234567",
        }
        base_url = "http://127.0.0.1:18002"
        runtime_proof: dict[str, object] = {
            "schema_version": "research-report-clone-runtime-proof-v1",
            "producer": "scripts/probe_research_report_clone_runtime.py",
            "generated_at": now.isoformat(),
            "base_url": base_url,
            "execution_scope": "inside_clone_app_container",
            "health_probe": {
                "status": "ok",
                "store": "PostgreSQLStore",
                "object_store_backend": "local",
                "search_backend": "local",
                "transport": "docker_exec_loopback",
            },
            "database_probe": {
                "query_id": "select_current_database",
                "success": True,
                "current_database": database_name,
                "database_oid": runtime_identity["database_oid"],
                "postgres_system_identifier": runtime_identity["postgres_system_identifier"],
                "table_counts": counts,
                "collection_counts": collections,
            },
            "environment_summary": {
                "runtime_database_name": database_name,
                "object_store_backend": "local",
                "search_backend": "local",
                "network_isolation": True,
                "isolated_network_name": "ai-quant-t614-isolated",
                "network_names": ["ai-quant-t614-isolated"],
                "network_internal": True,
                "network_members_limited_to_app_and_postgres": True,
                "raw_mount_read_only": True,
                "root_filesystem_read_only": True,
                "primary_service_reachable": False,
                "execution_scope": "inside_clone_app_container",
            },
            "runtime_identity": runtime_identity,
        }
        attestation = {
            "schema_version": "research-report-clone-attestation-v1",
            "status": "passed",
            "generated_at": now.isoformat(),
            "environment": "cloned_database_pilot",
            "base_url": base_url,
            "execution_scope": "inside_clone_app_container",
            "database_name": database_name,
            "runtime_database_name": database_name,
            "object_store_backend": "local",
            "search_backend": "local",
            "network_isolation": True,
            "raw_mount_read_only": True,
            "primary_service_reachable": False,
            "restore_verified": True,
            "source_backup_dump_sha256": dump_sha,
            "plan_sha256": plan_sha,
            "source_counts": counts,
            "restored_counts": counts,
            "collection_counts": collections,
            "restored_collection_counts": collections,
            "runtime_identity": runtime_identity,
            "runtime_proof": runtime_proof,
            "runtime_proof_sha256": payload_sha256(runtime_proof),
        }
        attestation_path = root / "attestation.json"
        attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
        gates = [
            {"gate_id": gate_id, "passed": True}
            for gate_id in (
                "identity_manifest_verified",
                "decision_batch_verified",
                "raw_batch_content_verified",
                "fresh_primary_backup_verified",
                "exact_human_approval_verified",
                "independent_clone_attestation_verified",
            )
        ]
        preflight: dict[str, object] = {
            "schema_version": "research-report-clone-batch-preflight-v1",
            "status": "ready_for_separate_clone_executor",
            "execution_ready": True,
            "execution_performed": False,
            "automatic_recovery_authorized": False,
            "failed_gate_ids": [],
            "gates": gates,
            "plan_sha256": plan_sha,
            "input_evidence": {
                "backup_dump_sha256": dump_sha,
                "backup_source_counts": counts,
                "backup_collection_counts": collections,
            },
            "plan": plan,
            "approval_evidence": {"approval_file_sha256": _file_sha256(approval_path)},
            "clone_attestation_evidence": {"attestation_file_sha256": _file_sha256(attestation_path)},
        }
        return preflight, approval_path, attestation_path, backup_path

    def test_ready_bundle_binds_approval_backup_and_attestation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preflight, approval, attestation, backup = self._runtime_bundle(root)
            plan, loaded_attestation = validate_execution_bundle(
                preflight=preflight,
                approval_path=approval,
                attestation_path=attestation,
                backup_manifest_path=backup,
                base_url="http://127.0.0.1:18002",
                confirm_plan_sha256=str(preflight["plan_sha256"]),
                confirm_batch_sha256="b" * 64,
                acknowledge_opinion_boundary=True,
                confirm_targeted_registration=True,
                confirm_clone_target=True,
            )
            self.assertEqual(plan["batch_id"], "t613-batch-0001")
            self.assertEqual(loaded_attestation["database_name"], "ai_quant_t614_clone_test")

            plan["write_contract"]["updates_allowed"] = True  # type: ignore[index]
            preflight["plan_sha256"] = payload_sha256(plan)
            with self.assertRaisesRegex(CloneBatchRefused, "write contract"):
                validate_execution_bundle(
                    preflight=preflight,
                    approval_path=approval,
                    attestation_path=attestation,
                    backup_manifest_path=backup,
                    base_url="http://127.0.0.1:18002",
                    confirm_plan_sha256=str(preflight["plan_sha256"]),
                    confirm_batch_sha256="b" * 64,
                    acknowledge_opinion_boundary=True,
                    confirm_targeted_registration=True,
                    confirm_clone_target=True,
                )

    def test_raw_locator_resolution_rejects_changed_content_without_exposing_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan, raw = self._plan_and_raw(root)
            resolved = resolve_batch_paths(
                raw,
                registry_root=Path("/data/local/research_reports"),
                entries=plan["batch_entries"],  # type: ignore[arg-type]
            )
            self.assertEqual(len(resolved), 2)
            first_path = next(iter(resolved.values()))
            first_path.write_bytes(b"changed")
            with self.assertRaisesRegex(CloneBatchRefused, "raw size changed|raw content changed") as raised:
                resolve_batch_paths(
                    raw,
                    registry_root=Path("/data/local/research_reports"),
                    entries=plan["batch_entries"],  # type: ignore[arg-type]
                )
            self.assertNotIn(temp_dir, str(raised.exception))

    def test_two_runs_are_identity_equal_and_second_run_creates_nothing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan, raw = self._plan_and_raw(root)
            report_ids = [str(item["report_id"]) for item in plan["batch_entries"]]  # type: ignore[index]
            client = FakeClient(report_ids)
            run1 = execute_batch(
                plan,
                client=client,  # type: ignore[arg-type]
                filesystem_root=raw,
                registry_root=Path("/data/local/research_reports"),
                api_root="/data/local/research_reports",
                citation_char_limit=1200,
                max_text_chars=50000,
                pdf_pages=3,
                pdftotext_timeout=10,
            )
            run2 = execute_batch(
                plan,
                client=client,  # type: ignore[arg-type]
                filesystem_root=raw,
                registry_root=Path("/data/local/research_reports"),
                api_root="/data/local/research_reports",
                citation_char_limit=1200,
                max_text_chars=50000,
                pdf_pages=3,
                pdftotext_timeout=10,
                prior_run=run1,
            )
        self.assertEqual(run1["status"], "passed")
        self.assertEqual(run1["ingest_created_count"], 2)
        self.assertEqual(run2["status"], "passed")
        self.assertEqual(run2["ingest_created_count"], 0)
        self.assertEqual(run1["registry_scan_mode"], "targeted_relative_paths")
        self.assertEqual(run2["registry_scan_mode"], "read_only_batch_state")
        self.assertTrue(run2["idempotency_comparison"]["passed"])
        self.assertEqual(compare_with_prior_run(run2, run1)["mismatch_count"], 0)
        rendered = json.dumps(run2)
        self.assertNotIn(temp_dir, rendered)
        self.assertNotIn("one.txt", rendered)
        run2_calls = client.calls[len(client.calls) - 1 :]
        self.assertEqual(run2_calls[0][0], "GET")
        scan_body = next(body for method, path, body in client.calls if method == "POST" and path == "/api/research-reports/scan")
        self.assertEqual(len(scan_body["relative_paths"]), 2)
        self.assertEqual(scan_body["limit"], 2)
        self.assertNotEqual(scan_body["limit"], 50000)


if __name__ == "__main__":
    unittest.main()
