#!/usr/bin/env python3
"""Render a local-only systemd user timer for paper-allocation operations."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import sys
from typing import Sequence


def _unit_safe(value: str, name: str) -> None:
    if not value or any(character in value for character in ("\n", "\r", "\0", "%")):
        raise ValueError(f"{name} contains unsupported systemd unit characters")


def _absolute_file(value: str, name: str, *, allow_symlink: bool = False) -> Path:
    _unit_safe(value, name)
    path = Path(value)
    if not path.is_absolute() or not path.is_file() or (path.is_symlink() and not allow_symlink):
        raise ValueError(f"{name} must be an absolute, existing, non-symlink file")
    return path


def _absolute_dir(value: str, name: str, *, must_exist: bool) -> Path:
    _unit_safe(value, name)
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or (must_exist and not path.is_dir()):
        raise ValueError(f"{name} must be an absolute, non-symlink directory")
    return path


def render(*, project_root: Path, python: Path, state_dir: Path, artifact_dir: Path, calendar: str) -> tuple[str, str]:
    for value, name in (
        (str(project_root), "project root"),
        (str(python), "python"),
        (str(state_dir), "state dir"),
        (str(artifact_dir), "artifact dir"),
        (calendar, "calendar"),
    ):
        _unit_safe(value, name)
    runner = _absolute_file(str(project_root / "scripts" / "dynamic_allocation_daily_run.py"), "daily runner")
    ledger = state_dir / "dynamic-allocation-paper.jsonl"
    latest = artifact_dir / "daily-run-latest.json"
    history = artifact_dir / "daily-history"
    command = " ".join(
        shlex.quote(str(item))
        for item in (
            python,
            runner,
            "--execute",
            "--ledger",
            ledger,
            "--output",
            latest,
            "--history-dir",
            history,
        )
    )
    service = f"""[Unit]
Description=Local-only dynamic allocation paper operation

[Service]
Type=oneshot
WorkingDirectory={shlex.quote(str(project_root))}
ExecStart={command}
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
"""
    timer = f"""[Unit]
Description=Schedule local-only dynamic allocation paper operation

[Timer]
OnCalendar={calendar}
Persistent=true
RandomizedDelaySec=10m
Unit=ai-quant-dynamic-allocation-paper.service

[Install]
WantedBy=timers.target
"""
    return service, timer


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--project-root", required=True, help="absolute repository directory")
    result.add_argument("--python", required=True, help="absolute Python executable path")
    result.add_argument("--state-dir", required=True, help="absolute local state directory")
    result.add_argument("--artifact-dir", required=True, help="absolute local-only report directory")
    result.add_argument("--calendar", default="Mon..Fri *-*-* 07:30:00 Asia/Shanghai")
    result.add_argument("--install-dir", help="absolute systemd user unit directory; requires --execute")
    result.add_argument("--execute", action="store_true", help="write units; does not enable or start the timer")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if bool(args.install_dir) != bool(args.execute):
        parser().error("--install-dir and --execute must be supplied together")
    root = _absolute_dir(args.project_root, "project root", must_exist=True)
    python = _absolute_file(args.python, "python", allow_symlink=True)
    state = _absolute_dir(args.state_dir, "state dir", must_exist=False)
    artifacts = _absolute_dir(args.artifact_dir, "artifact dir", must_exist=False)
    service, timer = render(project_root=root, python=python, state_dir=state, artifact_dir=artifacts, calendar=args.calendar)
    if args.execute:
        destination = _absolute_dir(args.install_dir, "install dir", must_exist=True)
        for name, content in (
            ("ai-quant-dynamic-allocation-paper.service", service),
            ("ai-quant-dynamic-allocation-paper.timer", timer),
        ):
            target = destination / name
            if target.exists() and target.is_symlink():
                raise ValueError("unit output must not be a symbolic link")
            target.write_text(content, encoding="utf-8")
    print("# ai-quant-dynamic-allocation-paper.service")
    print(service, end="")
    print("# ai-quant-dynamic-allocation-paper.timer")
    print(timer, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
