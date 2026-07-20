from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from scripts.local_milestone_candidate import build_candidate_report


ROOT = Path(__file__).resolve().parents[1]


def initialize_root(directory: str) -> Path:
    root = Path(directory)
    (root / "tasks").mkdir()
    (root / "tasks" / "todo.md").write_text("# Todo\n", encoding="utf-8")
    return root


def write_valid_audit(command: list[str]) -> None:
    output = Path(command[command.index("--output") + 1])
    payload = (
        {"achieved": True, "local_production_ready": True, "doing_task_count": 0, "open_task_count": 17}
        if any(item.endswith("project_completion_audit.py") for item in command)
        else {"mode": "dry-run", "eligible_count": 0, "deleted_count": 0}
    )
    output.write_text(json.dumps(payload), encoding="utf-8")


class LocalMilestoneCandidateTests(unittest.TestCase):
    def test_green_candidate_inventories_dirty_tree_without_mutation(self) -> None:
        with TemporaryDirectory() as directory:
            root = initialize_root(directory)
            commands: list[list[str]] = []

            def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                self.assertEqual(cwd, root)
                commands.append(command)
                if command[:3] == ["git", "status", "--short"]:
                    return subprocess.CompletedProcess(command, 0, "## main...origin/main\n M README.md\n?? new.py\n", "")
                if command[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(command, 0, "abc123\n", "")
                output = Path(command[command.index("--output") + 1]) if "--output" in command else None
                if any(item.endswith("project_completion_audit.py") for item in command):
                    output.write_text(json.dumps({"achieved": True, "local_production_ready": True, "doing_task_count": 0, "open_task_count": 17}), encoding="utf-8")
                if any(item.endswith("local_artifact_retention.py") for item in command):
                    output.write_text(json.dumps({"mode": "dry-run", "eligible_count": 0, "deleted_count": 0}), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "passed\n", "")

            report = build_candidate_report(
                root=root,
                python=".venv/bin/python",
                runner=runner,
                now=datetime(2026, 7, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(report["status"], "passed")
            self.assertFalse(report["git_inventory"]["clean"])
            self.assertEqual(report["git_inventory"]["modified_count"], 1)
            self.assertEqual(report["git_inventory"]["untracked_count"], 1)
            self.assertTrue(report["candidate"]["ready_for_commit_review"])
            self.assertFalse(report["candidate"]["commit_performed"])
            self.assertFalse(report["candidate"]["push_performed"])
            self.assertFalse(report["candidate"]["files_deleted"])
            local_ci = next(command for command in commands if command[:2] == ["make", "local-ci"])
            self.assertIn("PYTHON=.venv/bin/python", local_ci)
            completion = next(command for command in commands if any(item.endswith("project_completion_audit.py") for item in command))
            self.assertEqual(completion[0], ".venv/bin/python")
            flattened = [item for command in commands for item in command]
            self.assertNotIn("commit", flattened)
            self.assertNotIn("push", flattened)
            self.assertNotIn("--execute", flattened)
            self.assertNotIn("rm", flattened)

    def test_failed_gate_prevents_commit_review(self) -> None:
        with TemporaryDirectory() as directory:
            root = initialize_root(directory)

            def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["git", "status", "--short"]:
                    return subprocess.CompletedProcess(command, 0, "## main\n", "")
                if command[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(command, 0, "abc123\n", "")
                if command[:2] == ["make", "local-ci"]:
                    return subprocess.CompletedProcess(command, 2, "", "tests failed")
                output = Path(command[command.index("--output") + 1])
                payload = (
                    {"achieved": True, "local_production_ready": True, "doing_task_count": 0, "open_task_count": 0}
                    if any(item.endswith("project_completion_audit.py") for item in command)
                    else {"mode": "dry-run", "eligible_count": 0, "deleted_count": 0}
                )
                output.write_text(json.dumps(payload), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            report = build_candidate_report(root=root, runner=runner)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failed_gates"], ["local_ci"])
            self.assertFalse(report["candidate"]["ready_for_commit_review"])

    def test_timeout_is_a_visible_failed_gate(self) -> None:
        with TemporaryDirectory() as directory:
            root = initialize_root(directory)

            def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["make", "local-ci"]:
                    raise subprocess.TimeoutExpired(command, 10, output="partial output")
                if command[:3] == ["git", "status", "--short"]:
                    return subprocess.CompletedProcess(command, 0, "## main\n", "")
                if command[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(command, 0, "abc123\n", "")
                write_valid_audit(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            report = build_candidate_report(root=root, runner=runner)
            gate = next(item for item in report["gates"] if item["name"] == "local_ci")
            self.assertEqual(report["status"], "failed")
            self.assertIn("timed out", gate["error"])
            self.assertEqual(gate["stdout_tail"], ["partial output"])

    def test_missing_and_malformed_audit_outputs_fail_the_named_gate(self) -> None:
        for mode, expected in (
            ("missing", "did not produce"),
            ("malformed", "malformed"),
            ("wrong_type", "must be an integer"),
        ):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = initialize_root(directory)

                def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                    if command[:3] == ["git", "status", "--short"]:
                        return subprocess.CompletedProcess(command, 0, "## main\n", "")
                    if command[:2] == ["git", "rev-parse"]:
                        return subprocess.CompletedProcess(command, 0, "abc123\n", "")
                    if any(item.endswith("local_artifact_retention.py") for item in command):
                        output = Path(command[command.index("--output") + 1])
                        if mode == "malformed":
                            output.write_text("{bad json", encoding="utf-8")
                        elif mode == "wrong_type":
                            output.write_text(
                                json.dumps({"mode": "dry-run", "eligible_count": "zero", "deleted_count": 0}),
                                encoding="utf-8",
                            )
                    elif any(item.endswith("project_completion_audit.py") for item in command):
                        write_valid_audit(command)
                    return subprocess.CompletedProcess(command, 0, "", "")

                report = build_candidate_report(root=root, runner=runner)
                gate = next(item for item in report["gates"] if item["name"] == "artifact_retention_dry_run")
                self.assertEqual(report["status"], "failed")
                self.assertIn(expected, gate["validation_error"])

    def test_git_timeout_is_reported_without_crashing(self) -> None:
        with TemporaryDirectory() as directory:
            root = initialize_root(directory)

            def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["git", "status", "--short"]:
                    raise subprocess.TimeoutExpired(command, 10)
                if command[:2] == ["make", "local-ci"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                write_valid_audit(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            report = build_candidate_report(root=root, runner=runner)
            self.assertEqual(report["status"], "failed")
            self.assertIn("git_inventory", report["failed_gates"])
            self.assertIn("timed out", report["git_inventory"]["error"])

    def test_malformed_completion_output_fails_completion_gate(self) -> None:
        with TemporaryDirectory() as directory:
            root = initialize_root(directory)

            def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
                if command[:3] == ["git", "status", "--short"]:
                    return subprocess.CompletedProcess(command, 0, "## main\n", "")
                if command[:2] == ["git", "rev-parse"]:
                    return subprocess.CompletedProcess(command, 0, "abc123\n", "")
                if any(item.endswith("project_completion_audit.py") for item in command):
                    output = Path(command[command.index("--output") + 1])
                    output.write_text("[]", encoding="utf-8")
                elif any(item.endswith("local_artifact_retention.py") for item in command):
                    write_valid_audit(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            report = build_candidate_report(root=root, runner=runner)
            gate = next(item for item in report["gates"] if item["name"] == "project_completion_audit")
            self.assertEqual(report["status"], "failed")
            self.assertIn("JSON object", gate["validation_error"])


class LocalProductionStackActionTests(unittest.TestCase):
    def _run_action(self, *actions: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with TemporaryDirectory() as directory:
            binary_dir = Path(directory)
            log = binary_dir / "docker.log"
            docker = binary_dir / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > \"$T596_DOCKER_LOG\"\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_dir}:/usr/bin:/bin"
            environment["T596_DOCKER_LOG"] = str(log)
            result = subprocess.run(
                ["bash", "scripts/local_production_stack.sh", *actions],
                cwd=ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )
            return result, log.read_text(encoding="utf-8").strip() if log.exists() else ""

    def test_status_is_read_only_and_stop_preserves_volumes(self) -> None:
        status, status_command = self._run_action("status")
        self.assertEqual(status.returncode, 0)
        self.assertEqual(status_command, "compose ps")

        stop, stop_command = self._run_action("stop")
        self.assertEqual(stop.returncode, 0)
        self.assertEqual(stop_command, "compose stop")
        self.assertNotIn("down", stop_command)
        self.assertNotIn("-v", stop_command)

    def test_unknown_or_extra_action_fails_before_docker(self) -> None:
        unknown, unknown_command = self._run_action("destroy")
        self.assertEqual(unknown.returncode, 2)
        self.assertEqual(unknown_command, "")
        self.assertIn("Usage:", unknown.stderr)

        extra, extra_command = self._run_action("status", "unexpected")
        self.assertEqual(extra.returncode, 2)
        self.assertEqual(extra_command, "")


if __name__ == "__main__":
    unittest.main()
