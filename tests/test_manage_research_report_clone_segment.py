from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.manage_research_report_clone_segment import (
    SegmentStateRefused,
    abort_state,
    append_checkpoint,
    init_state,
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
            run1.write_text(json.dumps({"status": "passed"}), encoding="utf-8")
            run2.write_text(json.dumps({"status": "passed", "idempotency_comparison": {"passed": True}}), encoding="utf-8")
            state = append_checkpoint(
                self._state(),
                batch_id="t613-batch-0005",
                batch_sha256="d" * 64,
                run1_path=run1,
                run2_path=run2,
                counts={"records": 10, "audit_log": 20},
            )
            self.assertEqual(state["latest_checkpoint"], state["batches"][0]["checkpoint_sha256"])
            self.assertEqual(state["batches"][0]["run2_artifact_sha256"], __import__("hashlib").sha256(run2.read_bytes()).hexdigest())

    def test_checkpoint_rejects_failed_idempotence_and_duplicates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run1 = root / "run1.json"
            run2 = root / "run2.json"
            run1.write_text("{}", encoding="utf-8")
            run2.write_text(json.dumps({"idempotency_comparison": {"passed": False}}), encoding="utf-8")
            with self.assertRaises(SegmentStateRefused):
                append_checkpoint(self._state(), batch_id="t613-batch-0005", batch_sha256="d" * 64, run1_path=run1, run2_path=run2, counts={})

    def test_abort_is_terminal(self) -> None:
        aborted = abort_state(self._state(), reason="scheduler writer was not quiescent")
        self.assertEqual(aborted["status"], "aborted")
        with self.assertRaises(SegmentStateRefused):
            abort_state(aborted, reason="again")


if __name__ == "__main__":
    unittest.main()
