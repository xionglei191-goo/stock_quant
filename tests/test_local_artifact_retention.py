from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.local_artifact_retention import build_retention_report


class LocalArtifactRetentionTests(unittest.TestCase):
    def _profile(self, root: Path, name: str, *, age_days: int) -> Path:
        path = root / "artifacts" / name / "chrome-profile"
        path.mkdir(parents=True)
        (path / "state.bin").write_bytes(b"profile")
        timestamp = datetime(2026, 7, 17, tzinfo=timezone.utc).timestamp() - age_days * 86400
        os.utime(path, (timestamp, timestamp))
        return path

    def test_dry_run_reports_candidate_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = self._profile(root, "old", age_days=30)
            report = build_retention_report(
                root,
                target="browser-profiles",
                older_than_days=14,
                keep_latest=0,
                now=datetime(2026, 7, 17, tzinfo=timezone.utc),
                tracked_paths=set(),
                reference_text="",
            )
            self.assertEqual(report["eligible_count"], 1)
            self.assertEqual(report["deleted_count"], 0)
            self.assertTrue(old.exists())

    def test_execute_deletes_only_eligible_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = self._profile(root, "old", age_days=30)
            recent = self._profile(root, "recent", age_days=1)
            report = build_retention_report(
                root,
                target="browser-profiles",
                older_than_days=14,
                keep_latest=0,
                execute=True,
                now=datetime(2026, 7, 17, tzinfo=timezone.utc),
                tracked_paths=set(),
                reference_text="",
            )
            self.assertEqual(report["deleted_count"], 1)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())

    def test_tracked_referenced_and_latest_profiles_are_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tracked = self._profile(root, "tracked", age_days=40)
            referenced = self._profile(root, "referenced", age_days=30)
            latest = self._profile(root, "latest", age_days=20)
            report = build_retention_report(
                root,
                target="browser-profiles",
                older_than_days=14,
                keep_latest=1,
                execute=True,
                now=datetime(2026, 7, 17, tzinfo=timezone.utc),
                tracked_paths={"artifacts/tracked/chrome-profile/state.bin"},
                reference_text="artifacts/referenced/chrome-profile",
            )
            reasons = {row["path"]: row["protected_reasons"] for row in report["rows"]}
            self.assertIn("git_tracked", reasons["artifacts/tracked/chrome-profile"])
            self.assertIn("referenced_evidence", reasons["artifacts/referenced/chrome-profile"])
            self.assertIn("keep_latest", reasons["artifacts/latest/chrome-profile"])
            self.assertTrue(tracked.exists() and referenced.exists() and latest.exists())

    def test_symlink_is_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            profile = root / "artifacts" / "linked" / "chrome-profile"
            profile.parent.mkdir(parents=True)
            profile.symlink_to(outside, target_is_directory=True)
            report = build_retention_report(
                root,
                target="browser-profiles",
                older_than_days=0,
                keep_latest=0,
                execute=True,
                now=datetime(2026, 7, 17, tzinfo=timezone.utc),
                tracked_paths=set(),
                reference_text="",
            )
            self.assertEqual(report["deleted_count"], 0)
            self.assertTrue(outside.exists())


if __name__ == "__main__":
    unittest.main()
