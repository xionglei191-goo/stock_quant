from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from app.errors import ValidationError
from tests.support import SystemServiceTestBase


class ResearchReportContentIdentityTests(SystemServiceTestBase):
    def test_targeted_scan_registers_only_relative_paths_and_rejects_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "Broker" / "2026" / "one.txt"
            second = root / "Broker" / "2026" / "two.txt"
            first.parent.mkdir(parents=True)
            first.write_text("one", encoding="utf-8")
            second.write_text("two", encoding="utf-8")

            scanned = self.service.scan_research_reports(
                {
                    "root_path": str(root),
                    "extensions": [".txt"],
                    "relative_paths": ["Broker/2026/two.txt"],
                    "limit": 1,
                },
                actor="data",
            )
            self.assertEqual(scanned["scan_mode"], "targeted_relative_paths")
            self.assertEqual(scanned["indexed_count"], 1)
            self.assertEqual(scanned["reports"][0]["file_name"], "two.txt")
            with self.assertRaisesRegex(ValidationError, "normalized relative paths"):
                self.service.scan_research_reports(
                    {
                        "root_path": str(root),
                        "extensions": [".txt"],
                        "relative_paths": ["../outside.txt"],
                    },
                    actor="data",
                )
            with self.assertRaisesRegex(ValidationError, "normalized relative paths"):
                self.service.scan_research_reports(
                    {
                        "root_path": str(root),
                        "extensions": [".txt"],
                        "relative_paths": ["Broker//2026/two.txt"],
                    },
                    actor="data",
                )

    def test_batch_state_is_read_only_and_opaque(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "Broker" / "2026" / "DEMO.txt"
            report_path.parent.mkdir(parents=True)
            report_path.write_text("local opinion", encoding="utf-8")
            scanned = self.service.scan_research_reports(
                {"root_path": str(root), "extensions": [".txt"]}, actor="data"
            )
            report_id = scanned["reports"][0]["report_id"]
            expected_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
            self.service.ingest_research_report(
                report_id,
                {"issuer_id": "issuer_001", "document_id": f"doc_{report_id}", "content_sha256": expected_sha256},
                actor="data",
            )
            self.service.extract_research_report_text(report_id, {"text": "local opinion"}, actor="data")
            audit_count = len(self.service.store.audit_log)
            state = self.service.research_report_batch_state({"report_ids": [report_id]})
        self.assertEqual(state["missing_report_ids"], [])
        self.assertEqual(state["reports"][0]["content_sha256"], expected_sha256)
        self.assertEqual(state["reports"][0]["evidence_count"], 1)
        self.assertNotIn("file_path", state["reports"][0])
        self.assertEqual(len(self.service.store.audit_log), audit_count)

    def test_ingest_verifies_persists_and_preserves_report_content_sha256(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "Broker" / "2026" / "DEMO-company-update.txt"
            report_path.parent.mkdir(parents=True)
            report_path.write_bytes(b"local opinion reference")
            expected_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
            scanned = self.service.scan_research_reports(
                {"root_path": str(root), "extensions": [".txt"], "hash_files": False},
                actor="data",
            )
            report_id = scanned["reports"][0]["report_id"]

            ingested = self.service.ingest_research_report(
                report_id,
                {
                    "issuer_id": "issuer_001",
                    "security_id": "sec_001",
                    "document_id": f"doc_{report_id}",
                    "content_sha256": expected_sha256,
                },
                actor="data",
            )

            self.assertEqual(ingested["report"]["content_sha256"], expected_sha256)
            self.assertEqual(ingested["document"]["content_sha256"], expected_sha256)

            rescanned = self.service.scan_research_reports(
                {"root_path": str(root), "extensions": [".txt"], "hash_files": False},
                actor="data",
            )

        self.assertEqual(rescanned["reports"][0]["content_sha256"], expected_sha256)

    def test_ingest_rejects_content_sha256_that_does_not_match_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "Broker" / "2026" / "DEMO-company-update.txt"
            report_path.parent.mkdir(parents=True)
            report_path.write_bytes(b"local opinion reference")
            scanned = self.service.scan_research_reports(
                {"root_path": str(root), "extensions": [".txt"], "hash_files": False},
                actor="data",
            )

            with self.assertRaisesRegex(ValidationError, "does not match"):
                self.service.ingest_research_report(
                    scanned["reports"][0]["report_id"],
                    {
                        "issuer_id": "issuer_001",
                        "security_id": "sec_001",
                        "content_sha256": "0" * 64,
                    },
                    actor="data",
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
