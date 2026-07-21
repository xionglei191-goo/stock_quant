from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.research_reports import report_id_for_path
from scripts.audit_research_report_manual_review import build_audit
from scripts.execute_research_report_clone_batch import CloneBatchRefused


class ManualReviewAuditTests(unittest.TestCase):
    def test_audit_binds_identity_and_redacts_paths_and_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            relative = Path("Broker/scan.pdf")
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b"pdf bytes")
            report_id = report_id_for_path(Path("/data/local/research_reports") / relative)
            preflight = {
                "plan": {
                    "batch_entries": [
                        {
                            "report_id": report_id,
                            "document_id": f"doc_{report_id}",
                            "relative_path_sha256": hashlib.sha256(relative.as_posix().encode()).hexdigest(),
                            "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "size_bytes": path.stat().st_size,
                            "file_type": "pdf",
                        }
                    ]
                }
            }
            with patch(
                "scripts.audit_research_report_manual_review.diagnose_pdf",
                return_value={"report_id": report_id, "classification": "image_only_pdf_local_ocr_candidate"},
            ):
                audit = build_audit(
                    preflight,
                    filesystem_root=root,
                    registry_root=Path("/data/local/research_reports"),
                    report_ids=[report_id],
                    pages=3,
                    timeout=10,
                    local_ocr_sample=True,
                )
            rendered = json.dumps(audit)
            self.assertEqual(audit["report_count"], 1)
            self.assertFalse(audit["external_ocr_invoked"])
            self.assertNotIn(temp_dir, rendered)
            self.assertNotIn("scan.pdf", rendered)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(CloneBatchRefused, "raw size changed|raw content changed"):
                build_audit(
                    preflight,
                    filesystem_root=root,
                    registry_root=Path("/data/local/research_reports"),
                    report_ids=[report_id],
                    pages=3,
                    timeout=10,
                    local_ocr_sample=False,
                )


if __name__ == "__main__":
    unittest.main()
