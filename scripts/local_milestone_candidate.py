#!/usr/bin/env python3
"""Audit a local milestone candidate without committing, pushing, or deleting."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
DEFAULT_COMMAND_TIMEOUT_SECONDS = 1800.0


def _run(
    command: list[str],
    cwd: Path,
    *,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def _command_gate(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = runner(command, cwd)
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "failed",
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "stdout_tail": _output_tail(exc.stdout),
            "stderr_tail": _output_tail(exc.stderr),
            "error": f"command timed out after {exc.timeout} seconds",
        }
    except OSError as exc:
        return {
            "name": name,
            "status": "failed",
            "return_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "stdout_tail": [],
            "stderr_tail": [],
            "error": f"command could not start: {exc}",
        }
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    return {
        "name": name,
        "status": "passed" if result.returncode == 0 else "failed",
        "return_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": command,
        "stdout_tail": stdout.splitlines()[-20:],
        "stderr_tail": stderr.splitlines()[-20:],
    }


def _output_tail(value: str | bytes | None) -> list[str]:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "").splitlines()[-20:]


def _git_inventory(root: Path, runner: CommandRunner) -> dict[str, Any]:
    try:
        status = runner(["git", "status", "--short", "--branch"], root)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _failed_git_inventory(f"git status failed: {exc}")
    if status.returncode != 0:
        return _failed_git_inventory(f"git status failed with return code {status.returncode}")
    lines = status.stdout.splitlines()
    branch = lines[0].removeprefix("## ") if lines and lines[0].startswith("## ") else ""
    rows = [line for line in lines[1:] if line]
    untracked = [line[3:] for line in rows if line.startswith("?? ")]
    modified = [line[3:] for line in rows if not line.startswith("?? ")]
    try:
        head = runner(["git", "rev-parse", "HEAD"], root)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return _failed_git_inventory(f"git rev-parse failed: {exc}")
    if head.returncode != 0:
        return _failed_git_inventory(f"git rev-parse failed with return code {head.returncode}")
    return {
        "status": "passed",
        "branch": branch,
        "head": head.stdout.strip(),
        "clean": not rows,
        "modified_count": len(modified),
        "untracked_count": len(untracked),
        "modified_paths": modified,
        "untracked_paths": untracked,
    }


def _failed_git_inventory(error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "error": error,
        "branch": None,
        "head": None,
        "clean": None,
        "modified_count": None,
        "untracked_count": None,
        "modified_paths": [],
        "untracked_paths": [],
    }


def build_candidate_report(
    *,
    root: Path = ROOT,
    python: str = sys.executable,
    runner: CommandRunner | None = None,
    command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo_root = root.resolve()
    if not (repo_root / "tasks" / "todo.md").is_file():
        raise ValueError("repository root must contain tasks/todo.md")
    generated_at = now or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("now must include a timezone")
    if not math.isfinite(command_timeout_seconds) or command_timeout_seconds <= 0:
        raise ValueError("command_timeout_seconds must be finite and positive")
    command_runner = runner or (
        lambda command, cwd: _run(command, cwd, timeout_seconds=command_timeout_seconds)
    )

    with tempfile.TemporaryDirectory(prefix="ai-quant-milestone-") as directory:
        temp = Path(directory)
        completion_output = temp / "project-completion-audit.json"
        artifact_output = temp / "artifact-retention-audit.json"
        gates = [
            _command_gate(
                "local_ci",
                ["make", "local-ci", f"PYTHON={python}"],
                cwd=repo_root,
                runner=command_runner,
            ),
            _command_gate(
                "project_completion_audit",
                [
                    python,
                    "scripts/project_completion_audit.py",
                    "--local-production-audit",
                    "artifacts/local-production-audit.json",
                    "--local-ai-acceptance",
                    "artifacts/local-ai-capability-acceptance.json",
                    "--output",
                    str(completion_output),
                ],
                cwd=repo_root,
                runner=command_runner,
            ),
            _command_gate(
                "artifact_retention_dry_run",
                [
                    python,
                    "scripts/local_artifact_retention.py",
                    "--target",
                    "all",
                    "--output",
                    str(artifact_output),
                ],
                cwd=repo_root,
                runner=command_runner,
            ),
        ]
        completion, completion_error = _read_json_report(completion_output, "project completion audit")
        artifact_audit, artifact_error = _read_json_report(artifact_output, "artifact retention audit")
        _apply_audit_validation(
            gates,
            "project_completion_audit",
            completion_error or _completion_validation_error(completion),
        )
        _apply_audit_validation(
            gates,
            "artifact_retention_dry_run",
            artifact_error or _artifact_validation_error(artifact_audit),
        )

    inventory = _git_inventory(repo_root, command_runner)
    failed = [gate["name"] for gate in gates if gate["status"] != "passed"]
    if inventory["status"] != "passed":
        failed.append("git_inventory")
    completion_achieved = completion.get("achieved") is True
    artifact_safe = artifact_audit.get("mode") == "dry-run" and artifact_audit.get("deleted_count") == 0
    passed = not failed and completion_achieved and artifact_safe
    return {
        "schema_version": "local-milestone-candidate/v1",
        "status": "passed" if passed else "failed",
        "generated_at": generated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "repository_root": str(repo_root),
        "git_inventory": inventory,
        "gates": gates,
        "failed_gates": failed,
        "completion_audit": {
            "achieved": completion.get("achieved"),
            "local_production_ready": completion.get("local_production_ready"),
            "doing_task_count": completion.get("doing_task_count"),
            "open_task_count": completion.get("open_task_count"),
        },
        "artifact_retention": {
            "dry_run": artifact_audit.get("mode") == "dry-run",
            "eligible_count": artifact_audit.get("eligible_count"),
            "deleted_count": artifact_audit.get("deleted_count"),
        },
        "candidate": {
            "ready_for_commit_review": passed,
            "commit_performed": False,
            "push_performed": False,
            "files_deleted": False,
            "clean_worktree_required": False,
            "note": "A dirty worktree is inventoried for review; this command never commits, pushes, or deletes it.",
        },
    }


def _read_json_report(path: Path, name: str) -> tuple[dict[str, Any], str | None]:
    if path.is_symlink():
        return {}, f"{name} output must not be a symbolic link"
    if not path.is_file():
        return {}, f"{name} did not produce its required JSON output"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"{name} output is unreadable or malformed: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{name} output must be a JSON object"
    return payload, None


def _completion_validation_error(payload: dict[str, Any]) -> str | None:
    if payload.get("achieved") is not True:
        return "project completion audit must report achieved=true"
    if payload.get("local_production_ready") is not True:
        return "project completion audit must report local_production_ready=true"
    for field in ("doing_task_count", "open_task_count"):
        if not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool):
            return f"project completion audit {field} must be an integer"
        if payload[field] < 0:
            return f"project completion audit {field} must be non-negative"
    return None


def _artifact_validation_error(payload: dict[str, Any]) -> str | None:
    if payload.get("mode") != "dry-run":
        return "artifact retention audit must report mode=dry-run"
    for field in ("eligible_count", "deleted_count"):
        if not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool):
            return f"artifact retention audit {field} must be an integer"
        if payload[field] < 0:
            return f"artifact retention audit {field} must be non-negative"
    if payload["deleted_count"] != 0:
        return "artifact retention dry-run must report deleted_count=0"
    return None


def _apply_audit_validation(gates: list[dict[str, Any]], name: str, error: str | None) -> None:
    if error is None:
        return
    gate = next(item for item in gates if item["name"] == name)
    gate["status"] = "failed"
    gate["validation_error"] = error


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--python", default=sys.executable, help="Python interpreter used by repository gates")
    result.add_argument("--timeout-seconds", type=float, default=DEFAULT_COMMAND_TIMEOUT_SECONDS)
    result.add_argument("--output", help="optional local-only JSON output; stdout is always emitted")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = build_candidate_report(
        python=args.python,
        command_timeout_seconds=args.timeout_seconds,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        if output.exists() and output.is_symlink():
            raise ValueError("milestone report output must not be a symbolic link")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
