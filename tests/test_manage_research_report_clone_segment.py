from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.manage_research_report_clone_segment import (
    SegmentStateRefused,
    abort_state,
    append_checkpoint,
    build_quiescence_proof,
    canonical_sha256,
    init_state,
    validate_quiescence_proof,
)


class CloneSegmentStateTests(unittest.TestCase):
    def _state(self) -> dict[str, object]:
        return init_state(
            segment_id="t613-segment-0001",
            plan_sha256="a" * 64,
            manifest_sha256="b" * 64,
            clone_identity={
                "database_name": "ai_quant_clone",
                "database_oid": "123",
                "postgres_system_identifier": "456",
                "attestation_sha256": "c" * 64,
            },
        )

    def test_checkpoint_binds_run_hashes_and_requires_idempotence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run1 = root / "run1.json"
            run2 = root / "run2.json"
            binding = {"plan_sha256": "a" * 64, "manifest_sha256": "b" * 64, "batch_id": "t613-batch-0005", "batch_sha256": "d" * 64}
            run1.write_text(json.dumps({**binding, "status": "passed", "artifact_sha256": "e" * 64}), encoding="utf-8")
            run2.write_text(json.dumps({**binding, "status": "passed", "idempotency_comparison": {"passed": True, "prior_run_sha256": "e" * 64}}), encoding="utf-8")
            counts = {key: 1 for key in ("records", "audit_log", "market_data_bars", "research_reports", "research_documents", "research_report_citation_evidence", "structured_research_reports", "report_viewpoints", "report_forecasts")}
            state = append_checkpoint(
                self._state(),
                batch_id="t613-batch-0005",
                batch_sha256="d" * 64,
                run1_path=run1,
                run2_path=run2,
                counts=counts,
            )
            self.assertEqual(state["latest_checkpoint"], state["batches"][0]["checkpoint_sha256"])
            self.assertEqual(state["batches"][0]["run2_artifact_sha256"], __import__("hashlib").sha256(run2.read_bytes()).hexdigest())

    def test_checkpoint_rejects_failed_idempotence_and_duplicates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run1 = root / "run1.json"
            run2 = root / "run2.json"
            binding = {"plan_sha256": "a" * 64, "manifest_sha256": "b" * 64, "batch_id": "t613-batch-0005", "batch_sha256": "d" * 64}
            run1.write_text(json.dumps(binding), encoding="utf-8")
            run2.write_text(json.dumps({**binding, "idempotency_comparison": {"passed": False}}), encoding="utf-8")
            with self.assertRaises(SegmentStateRefused):
                append_checkpoint(self._state(), batch_id="t613-batch-0005", batch_sha256="d" * 64, run1_path=run1, run2_path=run2, counts={})

    def test_checkpoint_rejects_incomplete_accumulated_counts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binding = {"plan_sha256": "a" * 64, "manifest_sha256": "b" * 64, "batch_id": "t613-batch-0005", "batch_sha256": "d" * 64}
            run1 = root / "run1.json"
            run2 = root / "run2.json"
            run1.write_text(json.dumps({**binding, "artifact_sha256": "e" * 64}), encoding="utf-8")
            run2.write_text(json.dumps({**binding, "idempotency_comparison": {"passed": True, "prior_run_sha256": "e" * 64}}), encoding="utf-8")
            with self.assertRaisesRegex(SegmentStateRefused, "counts are incomplete"):
                append_checkpoint(self._state(), batch_id="t613-batch-0005", batch_sha256="d" * 64, run1_path=run1, run2_path=run2, counts={"records": 1})

    def test_abort_is_terminal(self) -> None:
        aborted = abort_state(self._state(), reason="scheduler writer was not quiescent")
        self.assertEqual(aborted["status"], "aborted")
        with self.assertRaises(SegmentStateRefused):
            abort_state(aborted, reason="again")

    def test_quiescence_proof_binds_plan_backup_and_stopped_writers(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "quiescence.json"
            core = {
                "schema_version": "research-report-clone-segment-quiescence-proof-v1",
                "producer": "scripts/manage_research_report_clone_segment.py",
                "generated_at": "2026-07-21T12:00:00+00:00",
                "plan_sha256": "a" * 64,
                "backup_dump_sha256": "b" * 64,
                "primary_service_reachable": False,
                "known_scheduler_units": ["ai-quant-daily-update.service"],
                "scheduler_units_stopped": True,
                "scheduler_observations": [{"unit": "ai-quant-daily-update.service", "state": "inactive", "stopped": True}],
                "writer_container_observations": [{"container": "primary-app", "container_id": "abc", "running": False, "returncode": 0, "state": "exited"}],
                "active_writer_sessions": 0,
                "operator_boundary": "primary_writers_and_known_schedulers_stopped_for_clone_segment",
            }
            path.write_text(json.dumps({**core, "status": "passed", "proof_sha256": canonical_sha256(core)}), encoding="utf-8")
            result = validate_quiescence_proof(path, plan_sha256="a" * 64, backup_dump_sha256="b" * 64, now=datetime(2026, 7, 21, 12, 5, tzinfo=timezone.utc))
            self.assertEqual(result["proof_sha256"], canonical_sha256(core))

    def test_quiescence_proof_rejects_running_scheduler(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "quiescence.json"
            core = {
                "schema_version": "research-report-clone-segment-quiescence-proof-v1",
                "producer": "scripts/manage_research_report_clone_segment.py",
                "generated_at": "2026-07-21T12:00:00+00:00",
                "plan_sha256": "a" * 64,
                "backup_dump_sha256": "b" * 64,
                "primary_service_reachable": False,
                "known_scheduler_units": ["ai-quant-daily-update.service"],
                "scheduler_units_stopped": False,
                "scheduler_observations": [{"unit": "ai-quant-daily-update.service", "state": "active", "stopped": False}],
                "writer_container_observations": [{"container": "primary-app", "container_id": "abc", "running": False, "returncode": 0, "state": "exited"}],
                "active_writer_sessions": 0,
                "operator_boundary": "primary_writers_and_known_schedulers_stopped_for_clone_segment",
            }
            path.write_text(json.dumps({**core, "status": "passed", "proof_sha256": canonical_sha256(core)}), encoding="utf-8")
            with self.assertRaises(SegmentStateRefused):
                validate_quiescence_proof(path, plan_sha256="a" * 64, backup_dump_sha256="b" * 64, now=datetime(2026, 7, 21, 12, 5, tzinfo=timezone.utc))

    def test_quiescence_builder_requires_observed_writer_container(self) -> None:
        with self.assertRaises(SegmentStateRefused):
            build_quiescence_proof(
                plan_sha256="a" * 64,
                backup_dump_sha256="b" * 64,
                known_scheduler_units=["ai-quant-daily-update.service"],
                scheduler_units_stopped=True,
                active_writer_sessions=0,
                primary_service_reachable=False,
            )


if __name__ == "__main__":
    unittest.main()
