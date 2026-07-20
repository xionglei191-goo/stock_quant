#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CANONICAL_DOCUMENTS = (
    "README.md",
    "docs/README.md",
    "docs/system-architecture.md",
    "docs/risk-register.md",
    "docs/systemservice-modularization-adr.md",
)
REQUIRED_METADATA = (
    "Status",
    "Owner group",
    "Last updated",
    "Related tasks",
    "Scope",
    "Non-goals",
)
ALLOWED_STATUSES = frozenset(
    {"draft", "active", "superseded", "local-only evidence"}
)


def validate_document(path: Path, *, display_path: str | None = None) -> list[str]:
    label = display_path or str(path)
    if not path.is_file():
        return [f"{label}: file not found"]

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# ") or not lines[0][2:].strip():
        return [f"{label}: first line must be a non-empty level-one title"]

    metadata: dict[str, str] = {}
    metadata_started = False
    for line in lines[1:]:
        if not line.strip():
            if metadata_started:
                break
            continue
        if not line.startswith("- ") or ":" not in line[2:]:
            break
        metadata_started = True
        key, value = line[2:].split(":", 1)
        metadata[key.strip()] = value.strip()

    errors: list[str] = []
    for key in REQUIRED_METADATA:
        if key not in metadata:
            errors.append(f"{label}: missing required metadata `{key}`")
        elif not metadata[key]:
            errors.append(f"{label}: metadata `{key}` must not be empty")

    status = metadata.get("Status")
    if status and status not in ALLOWED_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_STATUSES))
        errors.append(
            f"{label}: invalid Status `{status}`; expected one of: {allowed}"
        )
    return errors


def validate_canonical_documents(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative_path in CANONICAL_DOCUMENTS:
        errors.extend(
            validate_document(root / relative_path, display_path=relative_path)
        )
    return errors


def main() -> int:
    errors = validate_canonical_documents()
    if errors:
        print("canonical document metadata validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("canonical document metadata validation passed")
    print(f"checked {len(CANONICAL_DOCUMENTS)} canonical document(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
