#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = [Path("README.md"), Path("docs")]
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def _iter_markdown_files(targets: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for target in targets:
        path = (ROOT / target).resolve()
        if path.is_file() and path.suffix == ".md":
            files.add(path)
        elif path.is_dir():
            files.update(p.resolve() for p in path.rglob("*.md"))
    return sorted(files)


def _normalize_link(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1]
    return raw


def _is_local_file_link(raw: str) -> bool:
    if raw.startswith(EXTERNAL_PREFIXES):
        return False
    if "://" in raw:
        return False
    return bool(raw.split("#", 1)[0])


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for file in files:
        text = file.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            raw = _normalize_link(match.group(1))
            if not _is_local_file_link(raw):
                continue
            target = raw.split("#", 1)[0]
            resolved = (file.parent / target).resolve()
            if not resolved.exists():
                rel_file = file.relative_to(ROOT)
                errors.append(f"{rel_file}: missing link target `{raw}` -> {resolved}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check local Markdown relative links in README.md and docs/."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        type=Path,
        default=DEFAULT_TARGETS,
        help="Markdown files or directories to check, relative to repo root by default.",
    )
    args = parser.parse_args(argv)

    files = _iter_markdown_files(args.targets)
    if not files:
        print("markdown link check failed: no markdown files found")
        return 1

    errors = check_links(files)
    if errors:
        print("markdown link check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("markdown link check passed")
    print(f"checked {len(files)} markdown file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
