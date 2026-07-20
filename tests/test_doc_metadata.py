from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_doc_metadata import validate_document


class DocumentMetadataValidationTests(unittest.TestCase):
    def _write_document(self, content: str) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "document.md"
        path.write_text(content, encoding="utf-8")
        return temp_dir, path

    def test_valid_metadata_passes(self) -> None:
        temp_dir, path = self._write_document(
            """# Canonical Document

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-07-17
- Related tasks: T-579
- Scope: Canonical document structure
- Non-goals: Prose validation

## Content
"""
        )
        with temp_dir:
            self.assertEqual(validate_document(path, display_path="document.md"), [])

    def test_missing_metadata_reports_stable_error(self) -> None:
        temp_dir, path = self._write_document(
            """# Canonical Document

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-07-17
- Related tasks: T-579
- Scope: Canonical document structure

## Content
"""
        )
        with temp_dir:
            self.assertEqual(
                validate_document(path, display_path="document.md"),
                ["document.md: missing required metadata `Non-goals`"],
            )

    def test_invalid_status_reports_allowed_values(self) -> None:
        temp_dir, path = self._write_document(
            """# Canonical Document

- Status: complete
- Owner group: Platform and Quality
- Last updated: 2026-07-17
- Related tasks: T-579
- Scope: Canonical document structure
- Non-goals: Prose validation
"""
        )
        with temp_dir:
            self.assertEqual(
                validate_document(path, display_path="document.md"),
                [
                    "document.md: invalid Status `complete`; expected one of: "
                    "active, draft, local-only evidence, superseded"
                ],
            )


if __name__ == "__main__":
    unittest.main()
