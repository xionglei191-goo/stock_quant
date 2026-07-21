from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.research_reports import report_id_for_path
from scripts.build_research_report_registry_decision import RIGHTS_POLICY, payload_sha256
from scripts.prepare_research_report_clone_batch import (
    BatchPreparationRefused,
    bind_batch_to_raw_files,
    build_approval_request,
    build_preflight,
    inspect_approval,
    inspect_backup,
    related_task_for_batch,
    verify_decision_batch,
    verify_identity_manifest,
)


class ResearchReportCloneBatchPreparationTests(unittest.TestCase):
    def test_later_batches_are_owned_by_t616(self) -> None:
        self.assertEqual(related_task_for_batch("t613-batch-0001"), "T-614")
        self.assertEqual(related_task_for_batch("t613-batch-0002"), "T-615")
        self.assertEqual(related_task_for_batch("t613-batch-0003"), "T-616")
        self.assertEqual(related_task_for_batch("t613-batch-0044"), "T-616")
        with self.assertRaisesRegex(BatchPreparationRefused, "governed T-613 recovery range"):
            related_task_for_batch("t613-batch-0045")

    def _fixture(self, root: Path) -> tuple[Path, dict[str, object], Path, dict[str, object], str, str]:
        raw = root / "raw"
        registry_root = Path("/data/local/research_reports")
        entries: list[dict[str, object]] = []
        for relative, body in {
            "Broker/one.txt": b"one opinion",
            "Broker/two.txt": b"two opinion",
        }.items():
            path = raw / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            rel = Path(relative)
            report_id = report_id_for_path(registry_root / rel)
            entries.append(
                {
                    "report_id": report_id,
                    "document_id": f"doc_{report_id}",
                    "content_sha256": hashlib.sha256(body).hexdigest(),
                    "relative_path_sha256": hashlib.sha256(rel.as_posix().encode()).hexdigest(),
                    "logical_path_sha256": hashlib.sha256(str(registry_root / rel).encode()).hexdigest(),
                    "size_bytes": len(body),
                    "file_type": "txt",
                    "source_key": "source_demo",
                    "rights_policy_id": RIGHTS_POLICY["policy_id"],
                }
            )
        entries.sort(key=lambda item: str(item["report_id"]))
        stable_core = {
            "identity_policy": {"policy": "test"},
            "rights_policy": RIGHTS_POLICY,
            "entries": entries,
            "hash_failures": [],
        }
        manifest_sha = payload_sha256(stable_core)
        manifest: dict[str, object] = {
            "schema_version": "research-report-full-identity-manifest-v1",
            **stable_core,
            "integrity": {
                "manifest_sha256": manifest_sha,
                "entries_sha256": payload_sha256(entries),
            },
            "report_id_collisions": [],
        }
        manifest_path = root / "identity-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_ids = [str(item["report_id"]) for item in entries]
        batch_sha = payload_sha256({"identity_manifest_sha256": manifest_sha, "report_ids": report_ids})
        decision: dict[str, object] = {
            "schema_version": "research-report-registry-recovery-decision-v1",
            "generated_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            "execution_authorized": False,
            "automatic_recovery_authorized": False,
            "input_evidence": {"identity_manifest_sha256": manifest_sha},
            "identity_comparison": {"postgres_content_conflict_count": 0},
            "recovery_plan": {
                "batch_size": 250,
                "batches": [
                    {
                        "batch_id": "t613-batch-0001",
                        "batch_sha256": batch_sha,
                        "report_count": len(report_ids),
                        "report_ids": report_ids,
                    }
                ],
            },
        }
        decision_path = root / "decision.json"
        decision_path.write_text(json.dumps(decision), encoding="utf-8")
        return manifest_path, manifest, decision_path, decision, manifest_sha, batch_sha

    def _backup(self, root: Path, *, decision_time: datetime) -> Path:
        dump = root / "backup.dump"
        dump.write_bytes(b"restore verified backup")
        counts = {
            "research_reports": 15,
            "research_documents": 15,
            "research_report_citation_evidence": 112,
        }
        path = root / "backup.manifest.json"
        path.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "restore_verified": True,
                    "source_db": "ai_quant",
                    "generated_at": (decision_time + timedelta(minutes=10)).isoformat(),
                    "retained_until": (decision_time + timedelta(days=7)).isoformat(),
                    "dump_path": str(dump),
                    "dump_size_bytes": dump.stat().st_size,
                    "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                    "source_counts": {"records": 10},
                    "restored_counts": {"records": 10},
                    "collection_counts": counts,
                    "restored_collection_counts": counts,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_manifest_and_batch_tamper_are_refused(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _manifest_path, manifest, _decision_path, decision, manifest_sha, batch_sha = self._fixture(root)
            verified = verify_identity_manifest(manifest, expected_manifest_sha256=manifest_sha)
            self.assertEqual(verified["entry_count"], 2)
            batch = verify_decision_batch(
                decision,
                manifest_sha256=manifest_sha,
                batch_id="t613-batch-0001",
                expected_batch_sha256=batch_sha,
            )
            self.assertEqual(batch["report_count"], 2)
            manifest["entries"][0]["content_sha256"] = "0" * 64  # type: ignore[index]
            with self.assertRaisesRegex(BatchPreparationRefused, "manifest SHA-256"):
                verify_identity_manifest(manifest, expected_manifest_sha256=manifest_sha)

    def test_raw_binding_verifies_content_without_exposing_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _manifest_path, manifest, _decision_path, decision, manifest_sha, batch_sha = self._fixture(root)
            verified = verify_identity_manifest(manifest, expected_manifest_sha256=manifest_sha)
            batch = verify_decision_batch(
                decision,
                manifest_sha256=manifest_sha,
                batch_id="t613-batch-0001",
                expected_batch_sha256=batch_sha,
            )
            binding = bind_batch_to_raw_files(
                root / "raw",
                registry_root=Path("/data/local/research_reports"),
                entries_by_id=verified["entries_by_id"],
                report_ids=batch["report_ids"],
            )
        self.assertEqual(binding["report_count"], 2)
        rendered = json.dumps(binding)
        self.assertNotIn(temp_dir, rendered)
        self.assertNotIn("Broker", rendered)
        self.assertNotIn("one.txt", rendered)

    def test_backup_must_be_newer_than_decision_and_restore_verified(self) -> None:
        now = datetime.now(timezone.utc)
        decision_time = now - timedelta(hours=2)
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            backup_path = self._backup(root, decision_time=decision_time)
            accepted = inspect_backup(backup_path, decision_generated_at=decision_time.isoformat(), now=now)
            self.assertTrue(accepted["gates_passed"])
            payload = json.loads(backup_path.read_text())
            payload["generated_at"] = (decision_time - timedelta(minutes=1)).isoformat()
            backup_path.write_text(json.dumps(payload))
            stale = inspect_backup(backup_path, decision_generated_at=decision_time.isoformat(), now=now)
        self.assertFalse(stale["gates_passed"])
        self.assertFalse(stale["checks"]["generated_after_t613_decision"])

    def test_generic_continue_is_not_an_approval_artifact(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertFalse(
            inspect_approval(
                None,
                manifest_sha256="a" * 64,
                batch_id="t613-batch-0001",
                batch_sha256="b" * 64,
                now=now,
            )["gates_passed"]
        )
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "approval.json"
            path.write_text(json.dumps({"status": "继续"}))
            result = inspect_approval(
                path,
                manifest_sha256="a" * 64,
                batch_id="t613-batch-0001",
                batch_sha256="b" * 64,
                now=now,
            )
        self.assertFalse(result["gates_passed"])

    def test_preflight_with_fresh_backup_still_blocks_without_approval_and_clone(self) -> None:
        now = datetime.now(timezone.utc)
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, manifest, decision_path, decision, manifest_sha, batch_sha = self._fixture(root)
            decision_time = datetime.fromisoformat(str(decision["generated_at"]))
            backup_path = self._backup(root, decision_time=decision_time)
            preflight = build_preflight(
                manifest_path=manifest_path,
                manifest=manifest,
                decision_path=decision_path,
                decision=decision,
                filesystem_root=root / "raw",
                registry_root=Path("/data/local/research_reports"),
                backup_manifest_path=backup_path,
                approval_path=None,
                clone_attestation_path=None,
                expected_manifest_sha256=manifest_sha,
                batch_id="t613-batch-0001",
                expected_batch_sha256=batch_sha,
                now=now,
            )
            approval_request = build_approval_request(preflight)

        self.assertEqual(preflight["status"], "blocked_pre_execution")
        self.assertFalse(preflight["execution_ready"])
        self.assertFalse(preflight["execution_performed"])
        self.assertTrue(preflight["backup_evidence"]["gates_passed"])
        self.assertEqual(
            set(preflight["failed_gate_ids"]),
            {"exact_human_approval_verified", "independent_clone_attestation_verified"},
        )
        self.assertIn(manifest_sha, approval_request["required_confirmation"])
        self.assertIn(batch_sha, approval_request["required_confirmation"])
        self.assertFalse(approval_request["primary_writes_allowed"])


if __name__ == "__main__":
    unittest.main()
