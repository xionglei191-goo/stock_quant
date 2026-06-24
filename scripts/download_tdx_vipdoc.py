from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

from app.errors import ValidationError


def download_tdx_vipdoc_archive(
    source_url: str,
    target_dir: str | Path,
    *,
    expected_sha256: str = "",
    extract: bool = True,
    user_agent: str = "company-intelligence-platform/0.1",
    max_bytes: int = 2_000_000_000,
) -> dict[str, Any]:
    source_url = str(source_url).strip()
    if not source_url:
        raise ValidationError("source_url is required")
    parsed = urlparse(source_url)
    if parsed.scheme and parsed.scheme not in {"https", "file"}:
        raise ValidationError("TDX vipdoc download only accepts https or file URLs")
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    archive_path = target / _archive_name(source_url)
    size = _download_to_file(source_url, archive_path, user_agent=user_agent, max_bytes=max_bytes)
    sha256 = _sha256_file(archive_path)
    if expected_sha256 and sha256.lower() != expected_sha256.lower():
        archive_path.unlink(missing_ok=True)
        raise ValidationError("downloaded TDX vipdoc archive sha256 does not match expected_sha256")
    extracted_files: list[str] = []
    if extract:
        extracted_files = _extract_zip(archive_path, target)
    return {
        "source_url": source_url,
        "archive_path": str(archive_path),
        "bytes": size,
        "sha256": sha256,
        "extracted": extract,
        "extracted_files": extracted_files[:100],
        "extracted_count": len(extracted_files),
        "target_dir": str(target),
    }


def _download_to_file(source_url: str, archive_path: Path, *, user_agent: str, max_bytes: int) -> int:
    parsed = urlparse(source_url)
    if not parsed.scheme:
        source_path = Path(source_url)
        if not source_path.exists():
            raise ValidationError(f"source file not found: {source_url}")
        size = source_path.stat().st_size
        if size > max_bytes:
            raise ValidationError("source file exceeds max_bytes")
        shutil.copyfile(source_path, archive_path)
        return size
    request = Request(source_url, headers={"User-Agent": user_agent})
    total = 0
    with urlopen(request, timeout=60) as response, archive_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                archive_path.unlink(missing_ok=True)
                raise ValidationError("download exceeds max_bytes")
            output.write(chunk)
    return total


def _extract_zip(archive_path: Path, target: Path) -> list[str]:
    if not zipfile.is_zipfile(archive_path):
        raise ValidationError("TDX vipdoc archive must be a zip file when extract=true")
    extracted: list[str] = []
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = target / member.filename
            resolved = member_path.resolve()
            if not str(resolved).startswith(str(target.resolve())):
                raise ValidationError("zip archive contains unsafe path")
            archive.extract(member, target)
            if not member.is_dir():
                extracted.append(str(target / member.filename))
    return extracted


def _archive_name(source_url: str) -> str:
    parsed = urlparse(source_url)
    name = Path(parsed.path if parsed.scheme else source_url).name
    return name or "tdx_vipdoc.zip"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and verify a public/local TongDaXin vipdoc archive.")
    parser.add_argument("source_url", help="HTTPS or file URL for a publicly reviewable vipdoc zip archive")
    parser.add_argument("--target-dir", default="data/local/tdx/vipdoc_downloads")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--no-extract", action="store_true")
    parser.add_argument("--user-agent", default="company-intelligence-platform/0.1")
    parser.add_argument("--max-bytes", type=int, default=2_000_000_000)
    args = parser.parse_args()
    result = download_tdx_vipdoc_archive(
        args.source_url,
        args.target_dir,
        expected_sha256=args.expected_sha256,
        extract=not args.no_extract,
        user_agent=args.user_agent,
        max_bytes=args.max_bytes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
