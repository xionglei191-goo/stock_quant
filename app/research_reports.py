from __future__ import annotations

from pathlib import Path
import hashlib
import re
from typing import Any


DEFAULT_REPORT_EXTENSIONS = {".pdf"}


def safe_source_part(value: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return safe or "unknown"


def infer_report_metadata(path: Path, root: Path) -> dict[str, Any]:
    relative = path.relative_to(root)
    parts = relative.parts
    broker = parts[0] if len(parts) > 1 else "unknown"
    year = ""
    month = ""
    for part in parts:
        if not year and re.fullmatch(r"20\d{2}|19\d{2}", part):
            year = part
            continue
        if year and not month:
            match = re.search(r"(0?[1-9]|1[0-2])", part)
            if match:
                month = match.group(1).zfill(2)
                break
    title = path.stem.strip() or path.name
    return {
        "broker": broker,
        "year": year,
        "month": month,
        "title": title,
        "relative_path": str(relative),
    }


def report_id_for_path(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"rr_{digest}"


def cheap_fingerprint(path: Path, root: Path) -> str:
    stat = path.stat()
    payload = f"{path.relative_to(root)}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_report_files(root: Path, *, extensions: set[str] | None = None, limit: int = 1000) -> list[Path]:
    extensions = {item.lower() for item in (extensions or DEFAULT_REPORT_EXTENSIONS)}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        files.append(path)
        if len(files) >= limit:
            break
    return sorted(files)
