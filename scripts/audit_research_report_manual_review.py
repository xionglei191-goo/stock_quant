#!/usr/bin/env python3
"""Diagnose approved local PDF review items without exposing names, paths, or text."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_research_report_clone_batch import CloneBatchRefused, _load_json, resolve_batch_paths, utc_iso


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CloneBatchRefused(f"local PDF diagnostic failed: {command[0]}") from exc


def _pdfinfo_fields(output: str) -> dict[str, str]:
    allowed = {"Pages", "Encrypted", "PDF version", "File size", "Page size"}
    fields: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator and key in allowed:
            fields[key.lower().replace(" ", "_")] = value.strip()
    return fields


def diagnose_pdf(path: Path, *, report_id: str, pages: int, timeout: int, local_ocr_sample: bool) -> dict[str, Any]:
    info = _run(["pdfinfo", str(path)], timeout=timeout)
    text = _run(["pdftotext", "-f", "1", "-l", str(pages), "-layout", str(path), "-"], timeout=timeout)
    fonts = _run(["pdffonts", "-f", "1", "-l", str(pages), str(path)], timeout=timeout)
    images = _run(["pdfimages", "-f", "1", "-l", str(pages), "-list", str(path)], timeout=timeout)
    font_rows = [line for line in fonts.stdout.splitlines()[2:] if line.strip()]
    image_rows = [line for line in images.stdout.splitlines()[2:] if line.strip()]
    ocr_chars = 0
    ocr_lines = 0
    ocr_status = "not_requested"
    if local_ocr_sample:
        with TemporaryDirectory(prefix="t615-local-ocr-") as temp_dir:
            prefix = Path(temp_dir) / "page"
            rendered = _run(
                ["pdftoppm", "-f", "1", "-singlefile", "-r", "150", "-png", str(path), str(prefix)],
                timeout=timeout,
            )
            image_path = prefix.with_suffix(".png")
            if rendered.returncode == 0 and image_path.is_file():
                ocr = _run(["tesseract", str(image_path), "stdout", "-l", "eng+chi_sim"], timeout=timeout)
                ocr_chars = len(ocr.stdout.strip())
                ocr_lines = len([line for line in ocr.stdout.splitlines() if line.strip()])
                ocr_status = "extractable" if ocr.returncode == 0 and ocr_chars else "empty_or_failed"
            else:
                ocr_status = "render_failed"
    return {
        "report_id": report_id,
        "content_identity_verified": True,
        "pdfinfo_status": "passed" if info.returncode == 0 else "failed",
        "pdf": _pdfinfo_fields(info.stdout),
        "sample_pages": pages,
        "text_chars": len(text.stdout.strip()),
        "font_rows": len(font_rows),
        "image_rows": len(image_rows),
        "local_ocr_sample_status": ocr_status,
        "local_ocr_chars": ocr_chars,
        "local_ocr_lines": ocr_lines,
        "classification": (
            "image_only_pdf_local_ocr_candidate"
            if info.returncode == 0 and not text.stdout.strip() and not font_rows and image_rows and ocr_chars
            else "requires_manual_review"
        ),
    }


def build_audit(
    preflight: dict[str, Any],
    *,
    filesystem_root: Path,
    registry_root: Path,
    report_ids: list[str],
    pages: int,
    timeout: int,
    local_ocr_sample: bool,
) -> dict[str, Any]:
    entries = [
        dict(item)
        for item in (preflight.get("plan") or {}).get("batch_entries", [])
        if isinstance(item, dict) and item.get("report_id") in report_ids
    ]
    if not report_ids or len(entries) != len(report_ids) or len(set(report_ids)) != len(report_ids):
        raise CloneBatchRefused("every requested report ID must be unique and present in the preflight")
    resolved = resolve_batch_paths(filesystem_root, registry_root=registry_root, entries=entries)
    results = [
        diagnose_pdf(
            resolved[report_id],
            report_id=report_id,
            pages=pages,
            timeout=timeout,
            local_ocr_sample=local_ocr_sample,
        )
        for report_id in report_ids
    ]
    return {
        "schema_version": "research-report-manual-review-audit-v1",
        "related_task": "T-615",
        "producer": "scripts/audit_research_report_manual_review.py",
        "generated_at": utc_iso(),
        "environment": "local_workstation_read_only_raw_files",
        "owner_group": "Data and Evidence",
        "classification": "local-only",
        "contains_sensitive_data": False,
        "acceptable_for_non_local_release": False,
        "report_count": len(results),
        "results": results,
        "decision": "local_clone_ocr_only_keep_manual_review_until_text_quality_is_accepted",
        "external_ocr_invoked": False,
        "raw_files_written": False,
        "primary_writes_allowed": False,
        "delete_operations": [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--filesystem-root", type=Path, required=True)
    parser.add_argument("--registry-root", type=Path, default=Path("/data/local/research_reports"))
    parser.add_argument("--report-id", action="append", required=True)
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--local-ocr-sample", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        audit = build_audit(
            _load_json(args.preflight, label="preflight"),
            filesystem_root=args.filesystem_root,
            registry_root=args.registry_root,
            report_ids=[str(item) for item in args.report_id],
            pages=max(1, min(args.pages, 10)),
            timeout=max(1, args.timeout),
            local_ocr_sample=args.local_ocr_sample,
        )
    except CloneBatchRefused as exc:
        raise SystemExit(f"manual-review audit refused: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report_count": audit["report_count"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
