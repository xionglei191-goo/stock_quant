#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"browser-profiles", "staging-ui", "all"}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _directory_size(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            try:
                total += child.stat().st_size
            except FileNotFoundError:
                continue
    return total


def _git_tracked_paths(repo_root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def _reference_text(repo_root: Path) -> str:
    paths = [repo_root / "tasks" / "todo.md", *sorted((repo_root / "docs").rglob("*.md"))]
    chunks: list[str] = []
    for path in paths:
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    return "\n".join(chunks)


def _discover(repo_root: Path, target: str) -> list[Path]:
    paths: set[Path] = set()
    if target in {"browser-profiles", "all"}:
        artifact_root = repo_root / "artifacts"
        if artifact_root.exists():
            paths.update(path for path in artifact_root.rglob("chrome-profile") if path.is_dir())
    if target in {"staging-ui", "all"}:
        staging_root = repo_root / "data" / "artifacts" / "staging-ui"
        if staging_root.exists():
            paths.update(path for path in staging_root.iterdir() if path.is_dir())
    return sorted(paths, key=lambda path: (path.stat().st_mtime, str(path)), reverse=True)


def build_retention_report(
    repo_root: Path,
    *,
    target: str = "all",
    older_than_days: int = 14,
    keep_latest: int = 2,
    execute: bool = False,
    now: datetime | None = None,
    tracked_paths: set[str] | None = None,
    reference_text: str | None = None,
) -> dict[str, object]:
    if target not in TARGETS:
        raise ValueError(f"unsupported target: {target}")
    if older_than_days < 0 or keep_latest < 0:
        raise ValueError("retention values must be non-negative")

    repo_root = repo_root.resolve()
    tracked = _git_tracked_paths(repo_root) if tracked_paths is None else tracked_paths
    references = _reference_text(repo_root) if reference_text is None else reference_text
    now = now or datetime.now(timezone.utc)
    cutoff = now.timestamp() - older_than_days * 86400
    discovered = _discover(repo_root, target)
    rows: list[dict[str, object]] = []
    deleted_count = 0
    reclaimed_bytes = 0

    for index, path in enumerate(discovered):
        relative = path.relative_to(repo_root).as_posix()
        reasons: list[str] = []
        resolved = path.resolve()
        if path.is_symlink() or not _is_relative_to(resolved, repo_root):
            reasons.append("unsafe_path")
        if path.name.endswith(".example.json"):
            reasons.append("example_artifact")
        if any(item == relative or item.startswith(relative + "/") for item in tracked):
            reasons.append("git_tracked")
        if relative in references:
            reasons.append("referenced_evidence")
        if index < keep_latest:
            reasons.append("keep_latest")
        try:
            modified_at = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if modified_at > cutoff:
            reasons.append("within_retention_window")

        size_bytes = _directory_size(path)
        eligible = not reasons
        deleted = False
        if execute and eligible:
            shutil.rmtree(path)
            deleted = True
            deleted_count += 1
            reclaimed_bytes += size_bytes
        rows.append(
            {
                "path": relative,
                "size_bytes": size_bytes,
                "modified_at": datetime.fromtimestamp(modified_at, timezone.utc).isoformat(),
                "eligible": eligible,
                "deleted": deleted,
                "protected_reasons": reasons,
            }
        )

    return {
        "status": "passed",
        "generated_at": now.isoformat(),
        "producer": "scripts/local_artifact_retention.py",
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "mode": "execute" if execute else "dry-run",
        "target": target,
        "older_than_days": older_than_days,
        "keep_latest": keep_latest,
        "discovered_count": len(rows),
        "eligible_count": sum(1 for row in rows if row["eligible"]),
        "deleted_count": deleted_count,
        "reclaimed_bytes": reclaimed_bytes,
        "rows": rows,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit or remove expired local browser/staging artifacts.")
    parser.add_argument("--target", choices=sorted(TARGETS), default="all")
    parser.add_argument("--older-than-days", type=int, default=14)
    parser.add_argument("--keep-latest", type=int, default=2)
    parser.add_argument("--execute", action="store_true", help="Delete eligible paths; default is dry-run.")
    parser.add_argument("--output", default="", help="Optional JSON report path.")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = build_retention_report(
            ROOT,
            target=args.target,
            older_than_days=args.older_than_days,
            keep_latest=args.keep_latest,
            execute=args.execute,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: report[key] for key in (
        "status",
        "mode",
        "target",
        "discovered_count",
        "eligible_count",
        "deleted_count",
        "reclaimed_bytes",
    )}
    if args.output:
        summary["output"] = str(Path(args.output))
    else:
        summary["rows"] = report["rows"]
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
