from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts.probe_research_report_clone_runtime import build_attestation


class CloneRuntimeProbeTests(unittest.TestCase):
    def _inspect_payloads(self, *, extra_member: bool = False) -> dict[str, dict[str, object]]:
        app_id = "a" * 64
        postgres_id = "b" * 64
        network_id = "c" * 64
        members: dict[str, object] = {app_id: {}, postgres_id: {}}
        if extra_member:
            members["live-opensearch-id"] = {}
        return {
            "clone-app": {
                "Id": app_id,
                "Image": "sha256:" + "1" * 64,
                "Config": {
                    "Hostname": app_id[:12],
                    "Env": [
                        "AI_QUANT_POSTGRES_DSN=postgresql://user:secret@postgres:5432/ai_quant_t608_clone",
                        "AI_QUANT_OBJECT_STORE_BACKEND=local",
                        "AI_QUANT_SEARCH_BACKEND=local",
                    ]
                },
                "HostConfig": {"ReadonlyRootfs": True},
                "NetworkSettings": {"Networks": {"pilot-network": {}}},
                "Mounts": [{"Destination": "/data/local/research_reports", "RW": False}],
            },
            "postgres": {"Id": postgres_id, "Image": "sha256:" + "2" * 64},
            "pilot-network": {"Id": network_id, "Internal": True, "Containers": members},
        }

    def _plan_and_backup(self) -> tuple[dict[str, object], dict[str, object]]:
        counts = {"records": 10, "audit_log": 20, "market_data_bars": 30}
        collections = {
            "research_reports": 0,
            "research_documents": 0,
            "research_report_citation_evidence": 0,
        }
        backup = {
            "dump_sha256": "a" * 64,
            "source_counts": counts,
            "collection_counts": collections,
        }
        plan = {
            "plan_sha256": "b" * 64,
            "input_evidence": {
                "backup_dump_sha256": backup["dump_sha256"],
                "backup_source_counts": counts,
                "backup_collection_counts": collections,
            },
        }
        return plan, backup

    def _run_side_effect(self, inspect_payloads: dict[str, dict[str, object]]):
        def run(command: list[str], *, timeout: float, allowed_returncodes: set[int] | None = None):
            del timeout, allowed_returncodes
            if command[:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(command, 0, json.dumps([inspect_payloads[command[2]]]), "")
            if command[:3] == ["docker", "exec", "clone-app"] and "select_current_database" in command[5]:
                payload = {
                    "query_id": "select_current_database",
                    "success": True,
                    "current_database": "ai_quant_t608_clone",
                    "database_oid": "16384",
                    "postgres_system_identifier": "7612345678901234567",
                    "table_counts": {"records": 10, "audit_log": 20, "market_data_bars": 30},
                    "collection_counts": {
                        "research_reports": 0,
                        "research_documents": 0,
                        "research_report_citation_evidence": 0,
                    },
                }
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
            if command[:3] == ["docker", "exec", "clone-app"] and "api/health" in command[5]:
                payload = {"success": True, "data": self._health()}
                return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
            if command[:3] == ["docker", "exec", "clone-app"]:
                return subprocess.CompletedProcess(command, 3, "", "")
            raise AssertionError(command)

        return run

    def _health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "store": "PostgreSQLStore",
            "object_store": {"backend": "local", "root": "/tmp/objects"},
            "search_index": {"backend": "local"},
        }

    def test_probe_builds_hash_bound_structured_attestation(self) -> None:
        plan, backup = self._plan_and_backup()
        with patch(
            "scripts.probe_research_report_clone_runtime._run",
            side_effect=self._run_side_effect(self._inspect_payloads()),
        ):
            attestation = build_attestation(
                app_container="clone-app",
                postgres_container="postgres",
                isolated_network="pilot-network",
                database_name="ai_quant_t608_clone",
                base_url="http://127.0.0.1:18001",
                primary_service_url="http://ai-quant-org:8000/api/health",
                raw_mount_target="/data/local/research_reports",
                backup_manifest=backup,
                plan=plan,
                timeout=5,
            )

        self.assertEqual(attestation["status"], "passed")
        self.assertEqual(attestation["runtime_database_name"], "ai_quant_t608_clone")
        self.assertTrue(attestation["network_isolation"])
        self.assertFalse(attestation["primary_service_reachable"])
        self.assertEqual(attestation["runtime_proof"]["database_probe"]["query_id"], "select_current_database")
        self.assertEqual(attestation["runtime_identity"]["app_container_id"], "a" * 64)
        self.assertEqual(attestation["runtime_identity"]["database_oid"], "16384")
        self.assertEqual(len(attestation["runtime_proof_sha256"]), 64)
        self.assertNotIn("secret", json.dumps(attestation))

    def test_probe_rejects_network_with_live_service_member(self) -> None:
        plan, backup = self._plan_and_backup()
        with patch(
            "scripts.probe_research_report_clone_runtime._run",
            side_effect=self._run_side_effect(self._inspect_payloads(extra_member=True)),
        ):
            with self.assertRaisesRegex(RuntimeError, "network_isolation"):
                build_attestation(
                    app_container="clone-app",
                    postgres_container="postgres",
                    isolated_network="pilot-network",
                    database_name="ai_quant_t608_clone",
                    base_url="http://127.0.0.1:18001",
                    primary_service_url="http://ai-quant-org:8000/api/health",
                    raw_mount_target="/data/local/research_reports",
                    backup_manifest=backup,
                    plan=plan,
                    timeout=5,
                )

    def test_probe_rejects_non_loopback_execution_url_before_docker_access(self) -> None:
        plan, backup = self._plan_and_backup()
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            build_attestation(
                app_container="clone-app",
                postgres_container="postgres",
                isolated_network="pilot-network",
                database_name="ai_quant_t608_clone",
                base_url="http://clone-app:18001",
                primary_service_url="http://ai-quant-org:8000/api/health",
                raw_mount_target="/data/local/research_reports",
                backup_manifest=backup,
                plan=plan,
                timeout=5,
            )


if __name__ == "__main__":
    unittest.main()
