#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANDOFF_DIR = ROOT / "docs" / "agent-handoffs"

FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-T-\d{3,}-[a-z0-9-]+\.md$")
REQUIRED_HEADINGS = [
    "# Handoff:",
    "## Metadata",
    "## Objective",
    "## Scope",
    "## Background",
    "## Problem Statement",
    "## Expected Deliverables",
    "## Current Findings",
    "## Proposed Work Plan",
    "## Validation Plan",
    "## Risks",
    "## Dependencies",
    "## Blockers",
    "## Handoff Checklist",
    "## Evidence",
    "## Next Recommended Action",
]


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []

    if path.name in {"README.md", "TEMPLATE.md"}:
        return errors

    if not FILENAME_RE.match(path.name):
        errors.append(
            f"{path}: invalid filename, expected YYYY-MM-DD-T-<id>-<slug>.md"
        )

    text = path.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"{path}: missing required section `{heading}`")

    return errors


def main() -> int:
    if not HANDOFF_DIR.exists():
        print(f"missing directory: {HANDOFF_DIR}")
        return 1

    files = sorted(HANDOFF_DIR.glob("*.md"))
    if not files:
        print(f"no markdown files found in {HANDOFF_DIR}")
        return 1

    errors: list[str] = []
    for file in files:
        errors.extend(validate_file(file))

    if errors:
        print("handoff validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("handoff validation passed")
    print(f"checked {len(files)} markdown file(s) in {HANDOFF_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
