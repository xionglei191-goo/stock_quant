from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SECRET_PATTERNS = {
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "paddleocr_token_literal": re.compile(r"\b[A-Fa-f0-9]{40}\b"),
    "assigned_secret": re.compile(r"\b(?:TOKEN|API_KEY|SECRET|PASSWORD)\s*=\s*['\"]?[A-Za-z0-9._/-]{16,}"),
}

ALLOWED_PLACEHOLDERS = {
    "AI_QUANT_LLM_API_KEY=",
    "AI_QUANT_PADDLEOCR_TOKEN=",
    "export AI_QUANT_LLM_API_KEY=...",
    "export AI_QUANT_PADDLEOCR_TOKEN=...",
}

SKIP_PREFIXES = ("data/", ".git/", "__pycache__/")


def tracked_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
        files = [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = [path for path in root.rglob("*") if path.is_file()]
    return [path for path in files if not _skip_path(root, path)]


def scan_repository(root: str | Path = ".") -> dict[str, Any]:
    repo_root = Path(root).resolve()
    findings: list[dict[str, Any]] = []
    for path in tracked_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        relative = path.relative_to(repo_root).as_posix()
        if relative in {".env", ".env.local"}:
            findings.append({"path": relative, "line": 1, "type": "tracked_env_file", "match": relative})
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if line.strip() in ALLOWED_PLACEHOLDERS:
                continue
            for kind, pattern in SECRET_PATTERNS.items():
                match = pattern.search(line)
                if match:
                    findings.append({"path": relative, "line": line_no, "type": kind, "match": _redact(match.group(0))})
    return {"ok": not findings, "findings": findings, "checked_files": len(tracked_files(repo_root))}


def _skip_path(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return True
    return any(relative.startswith(prefix) for prefix in SKIP_PREFIXES)


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    root = argv[0] if argv else "."
    result = scan_repository(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
