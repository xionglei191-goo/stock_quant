from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import SystemService, TERM_LEXICON
from app.utils import chunk_text, pdf_bytes_to_text, to_plain


TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".html", ".htm", ".json", ".jsonl", ".csv"}
PDF_SUFFIXES = {".pdf"}
RIGHTS_TAG = {
    "license_class": "public",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "allowed",
    "non_display_use": "restricted",
    "derived_data_use": "restricted",
}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _json_dump(path: str | Path, payload: Mapping[str, Any] | list[Any]) -> None:
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _iter_candidate_files(paths: Iterable[str | Path]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in TEXT_SUFFIXES | PDF_SUFFIXES:
                files.append(path)
            continue
        for item in path.rglob("*"):
            if item.is_file() and item.suffix.lower() in TEXT_SUFFIXES | PDF_SUFFIXES:
                files.append(item)
    return sorted({item.resolve() for item in files}, key=lambda item: str(item))


def _read_document_text(path: Path, *, char_limit: int) -> str:
    if path.suffix.lower() in PDF_SUFFIXES:
        try:
            text = pdf_bytes_to_text(path.read_bytes())
        except Exception:
            text = ""
        if not text.strip():
            with tempfile.TemporaryDirectory() as tmpdir:
                pdf_path = Path(tmpdir) / "input.pdf"
                txt_path = Path(tmpdir) / "input.txt"
                try:
                    pdf_path.write_bytes(path.read_bytes())
                    subprocess.run(["pdftotext", "-layout", str(pdf_path), str(txt_path)], check=True, capture_output=True, timeout=30)
                    text = txt_path.read_text(encoding="utf-8", errors="replace")
                except (FileNotFoundError, OSError, subprocess.SubprocessError):
                    text = ""
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
    text = " ".join(chunk_text(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:char_limit]


def _language_for_text(text: str) -> str:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    return "zh" if chinese_chars >= max(8, latin_chars // 4) else "en"


def _expected_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms: list[str] = []
    for canonical, aliases in TERM_LEXICON.items():
        if any(alias.lower() in lowered for alias in aliases):
            terms.append(canonical)
    return sorted(set(terms))


def _expected_number_count(text: str) -> int:
    return min(5, len(re.findall(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%?(?![\w.])|(?<![\w.])[-+]?\d+(?:\.\d+)?(?=年)", text)))


def _expected_period_count(text: str) -> int:
    return min(5, len(re.findall(r"\b(?:FY)?20\d{2}\b|20\d{2}年", text, flags=re.IGNORECASE)))


def _sample_source(language: str) -> tuple[str, str, str]:
    if language == "zh":
        return "ashare_exchange", "exchange", "annual_report"
    return "sec_edgar", "regulatory", "10-K"


def _artifact_uri(prefix: str, name: str) -> str:
    return f"{prefix.rstrip('/')}/{name}"


def _count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "") or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_local_benchmark_quality_package(
    *,
    input_paths: Iterable[str | Path],
    output_dir: str | Path,
    benchmark_id: str = "bm_local_quality_large_sample",
    target_sample_size: int = 300,
    min_chinese_samples: int = 150,
    min_english_samples: int = 150,
    max_samples: int = 500,
    max_files_scanned: int = 2000,
    char_limit: int = 20000,
    artifact_prefix: str = "minio://ai-quant-local/benchmark-quality",
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    service = SystemService()
    service.seed_default_sources(actor="benchmark_quality_package")
    service.register_issuer(
        {
            "issuer_id": "issuer_local_benchmark",
            "legal_name": "Local Benchmark Corpus",
            "market": ["A", "U"],
            "country": "mixed",
        },
        actor="benchmark_quality_package",
    )
    service.register_security(
        {
            "security_id": "security_local_benchmark",
            "issuer_id": "issuer_local_benchmark",
            "ticker": "LOCALBM",
            "market": "U",
            "currency": "USD",
        },
        actor="benchmark_quality_package",
    )
    service.register_benchmark(
        {
            "benchmark_id": benchmark_id,
            "language": "mixed",
            "task_type": "term_extraction",
            "sample_size": 0,
            "threshold": {
                "term_f1": 0.9,
                "number_recall": 0.8,
                "period_recall": 0.8,
                "page_hit_rate": 0.95,
                "evidence_locator_rate": 0.95,
                "avg_confidence": 0.75,
            },
        },
        actor="benchmark_quality_package",
    )

    manifest_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidate_files = _iter_candidate_files(input_paths)
    scanned_count = 0
    deferred_rows: list[dict[str, Any]] = []
    for index, path in enumerate(candidate_files, start=1):
        if len(manifest_rows) >= max_samples:
            break
        if max_files_scanned > 0 and scanned_count >= max_files_scanned:
            break
        scanned_count += 1
        text = _read_document_text(path, char_limit=char_limit)
        terms = _expected_terms(text)
        if not text or not terms:
            skipped.append({"path": str(path), "reason": "empty_or_no_supported_financial_terms"})
            continue
        expected_numbers = _expected_number_count(text)
        expected_periods = _expected_period_count(text)
        if expected_numbers <= 0 or expected_periods <= 0:
            skipped.append(
                {
                    "path": str(path),
                    "reason": "missing_auto_verifiable_number_or_period",
                    "expected_numbers": expected_numbers,
                    "expected_periods": expected_periods,
                }
            )
            continue
        language = _language_for_text(text)
        if (
            language == "en"
            and min_chinese_samples > 0
            and _count_by_key(manifest_rows, "language").get("zh", 0) < min_chinese_samples
            and len(manifest_rows) >= max(0, max_samples - min_chinese_samples)
        ):
            deferred_rows.append(
                {
                    "index": index,
                    "path": path,
                    "text": text,
                    "terms": terms,
                    "expected_numbers": expected_numbers,
                    "expected_periods": expected_periods,
                    "language": language,
                }
            )
            continue
        source_id, source_type, document_type = _sample_source(language)
        document_id = f"doc_local_benchmark_{index:04d}"
        sample_id = f"bms_local_benchmark_{index:04d}"
        service.ingest_document(
            {
                "document_id": document_id,
                "issuer_id": "issuer_local_benchmark",
                "security_id": "security_local_benchmark",
                "source_id": source_id,
                "source_type": source_type,
                "document_type": document_type,
                "source_uri": path.resolve().as_uri(),
                "body": text,
                "title": path.name,
                "rights_tag": RIGHTS_TAG,
                "language": language,
            },
            actor="benchmark_quality_package",
        )
        sample = service.register_benchmark_sample(
            benchmark_id,
            {
                "sample_id": sample_id,
                "document_id": document_id,
                "language": language,
                "expected_terms": terms,
                "expected_numbers": expected_numbers,
                "expected_periods": expected_periods,
                "expected_pages": [1],
                "notes": f"local_quality_package_source={path}",
            },
            actor="benchmark_quality_package",
        )
        manifest_rows.append(
            {
                "sample_id": sample.sample_id,
                "document_id": document_id,
                "language": language,
                "source_id": source_id,
                "source_path": str(path),
                "source_uri": path.resolve().as_uri(),
                "expected_terms": terms,
                "expected_numbers": sample.expected_numbers,
                "expected_periods": sample.expected_periods,
                "expected_pages": sample.expected_pages,
            }
        )

    for deferred in deferred_rows:
        if len(manifest_rows) >= max_samples:
            break
        index = int(deferred["index"])
        path = deferred["path"]
        text = str(deferred["text"])
        terms = list(deferred["terms"])
        expected_numbers = int(deferred["expected_numbers"])
        expected_periods = int(deferred["expected_periods"])
        language = str(deferred["language"])
        source_id, source_type, document_type = _sample_source(language)
        document_id = f"doc_local_benchmark_{index:04d}"
        sample_id = f"bms_local_benchmark_{index:04d}"
        service.ingest_document(
            {
                "document_id": document_id,
                "issuer_id": "issuer_local_benchmark",
                "security_id": "security_local_benchmark",
                "source_id": source_id,
                "source_type": source_type,
                "document_type": document_type,
                "source_uri": path.resolve().as_uri(),
                "body": text,
                "title": path.name,
                "rights_tag": RIGHTS_TAG,
                "language": language,
            },
            actor="benchmark_quality_package",
        )
        sample = service.register_benchmark_sample(
            benchmark_id,
            {
                "sample_id": sample_id,
                "document_id": document_id,
                "language": language,
                "expected_terms": terms,
                "expected_numbers": expected_numbers,
                "expected_periods": expected_periods,
                "expected_pages": [1],
                "notes": f"local_quality_package_source={path}",
            },
            actor="benchmark_quality_package",
        )
        manifest_rows.append(
            {
                "sample_id": sample.sample_id,
                "document_id": document_id,
                "language": language,
                "source_id": source_id,
                "source_path": str(path),
                "source_uri": path.resolve().as_uri(),
                "expected_terms": terms,
                "expected_numbers": sample.expected_numbers,
                "expected_periods": sample.expected_periods,
                "expected_pages": sample.expected_pages,
            }
        )

    run_payload: dict[str, Any] = {"run_id": f"bmrn_{benchmark_id}", "min_confidence": 0.75}
    run = service.run_benchmark_suite(benchmark_id, run_payload, actor="benchmark_quality_package") if manifest_rows else None

    sample_manifest = {
        "benchmark_id": benchmark_id,
        "sample_count": len(manifest_rows),
        "target_sample_size": target_sample_size,
        "source_paths": [str(Path(path).expanduser()) for path in input_paths],
        "candidate_file_count": len(candidate_files),
        "scanned_file_count": scanned_count,
        "scan_truncated": bool(max_files_scanned > 0 and scanned_count < len(candidate_files) and len(manifest_rows) < max_samples),
        "max_files_scanned": max_files_scanned,
        "language_counts": _count_by_key(manifest_rows, "language"),
        "source_counts": _count_by_key(manifest_rows, "source_id"),
        "samples": manifest_rows,
        "skipped_count": len(skipped),
        "skipped": skipped[:100],
        "usage_boundary": "local_quality_package_for_large_sample_benchmark_enhancement_no_training_no_live_trading",
    }
    baseline_report = {
        "benchmark_id": benchmark_id,
        "status": "passed" if run and run.passed else "failed",
        "run": to_plain(run) if run else None,
        "sample_count": len(manifest_rows),
        "language_counts": {
            language: sum(1 for row in manifest_rows if row["language"] == language)
            for language in sorted({row["language"] for row in manifest_rows})
        },
        "target_sample_size": target_sample_size,
        "target_gap": max(0, target_sample_size - len(manifest_rows)),
        "notes": "Use real manually reviewed 300-500 sample inputs before treating T-402 as large-sample complete.",
    }
    summary_rows = [
        {
            "sample_id": row["sample_id"],
            "document_id": row["document_id"],
            "language": row["language"],
            "expected_terms": row["expected_terms"],
            "summary_quality_status": "pending_manual_review",
        }
        for row in manifest_rows
    ]
    annotation_manual = "\n".join(
        [
            "# Local Benchmark Annotation Manual",
            "",
            "- Label canonical financial terms only when the source text explicitly supports them.",
            "- Keep source URI, page, bbox, and table-cell references when available.",
            "- Do not use local research reports as training data or undisclosed fact sources.",
            "- Failed samples must be retained in the regression baseline report.",
            "",
        ]
    )
    bbox_gold_rows = [
        {"sample_id": row["sample_id"], "document_id": row["document_id"], "status": "pending_manual_bbox_label"}
        for row in manifest_rows
    ]
    table_gold_rows = [
        {"sample_id": row["sample_id"], "document_id": row["document_id"], "status": "pending_manual_table_cell_label"}
        for row in manifest_rows
    ]

    _json_dump(output_path / "sample-manifest.json", sample_manifest)
    _json_dump(output_path / "baseline-report.json", baseline_report)
    _atomic_write_text(output_path / "annotation-manual.md", annotation_manual)
    _atomic_write_text(output_path / "summary-quality-samples.jsonl", "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in summary_rows) + ("\n" if summary_rows else ""))
    _atomic_write_text(output_path / "bbox-gold.jsonl", "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in bbox_gold_rows) + ("\n" if bbox_gold_rows else ""))
    _atomic_write_text(output_path / "table-cell-gold.jsonl", "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in table_gold_rows) + ("\n" if table_gold_rows else ""))

    readiness_payload = {
        "target_sample_size": target_sample_size,
        "min_chinese_samples": min_chinese_samples,
        "min_english_samples": min_english_samples,
        "sample_manifest_uri": _artifact_uri(artifact_prefix, "sample-manifest.json"),
        "chinese_sample_set_uri": _artifact_uri(artifact_prefix, "zh-samples.jsonl"),
        "english_sample_set_uri": _artifact_uri(artifact_prefix, "en-samples.jsonl"),
        "annotation_manual_uri": _artifact_uri(artifact_prefix, "annotation-manual.md"),
        "bbox_gold_uri": _artifact_uri(artifact_prefix, "bbox-gold.jsonl"),
        "table_cell_gold_uri": _artifact_uri(artifact_prefix, "table-cell-gold.jsonl"),
        "summary_quality_uri": _artifact_uri(artifact_prefix, "summary-quality-samples.jsonl"),
        "baseline_report_uri": _artifact_uri(artifact_prefix, "baseline-report.json"),
        "bbox_label_count": len(bbox_gold_rows),
        "table_cell_label_count": len(table_gold_rows),
        "summary_sample_count": len(summary_rows),
    }
    readiness_report = service.benchmark_readiness_report(
        benchmark_id,
        readiness_payload,
        actor="benchmark_quality_package",
    )
    _json_dump(output_path / "readiness-payload.json", readiness_payload)
    _json_dump(output_path / "readiness-report.json", readiness_report)

    package = {
        "status": "generated",
        "benchmark_id": benchmark_id,
        "output_dir": str(output_path),
        "sample_count": len(manifest_rows),
        "language_counts": _count_by_key(manifest_rows, "language"),
        "source_counts": _count_by_key(manifest_rows, "source_id"),
        "candidate_file_count": len(candidate_files),
        "scanned_file_count": scanned_count,
        "scan_truncated": bool(max_files_scanned > 0 and scanned_count < len(candidate_files) and len(manifest_rows) < max_samples),
        "target_sample_size": target_sample_size,
        "target_gap": max(0, target_sample_size - len(manifest_rows)),
        "large_sample_ready": bool(readiness_report.get("ready_for_real_acceptance")),
        "run_passed": bool(run and run.passed),
        "readiness_missing_requirements": readiness_report.get("missing_requirements", []),
        "artifacts": {
            "sample_manifest": str(output_path / "sample-manifest.json"),
            "baseline_report": str(output_path / "baseline-report.json"),
            "readiness_payload": str(output_path / "readiness-payload.json"),
            "readiness_report": str(output_path / "readiness-report.json"),
            "annotation_manual": str(output_path / "annotation-manual.md"),
            "bbox_gold": str(output_path / "bbox-gold.jsonl"),
            "table_cell_gold": str(output_path / "table-cell-gold.jsonl"),
            "summary_quality_samples": str(output_path / "summary-quality-samples.jsonl"),
        },
        "production_boundary": "local package makes T-402 repeatable; large-sample completion still requires enough real manually reviewed samples and gold labels",
    }
    _json_dump(output_path / "quality-package.json", package)
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and run a local large-sample benchmark quality package.")
    parser.add_argument("inputs", nargs="+", help="Input files or directories containing local benchmark source documents.")
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts/benchmark-quality-package"))
    parser.add_argument("--benchmark-id", default="bm_local_quality_large_sample")
    parser.add_argument("--target-sample-size", type=int, default=300)
    parser.add_argument("--min-chinese-samples", type=int, default=150)
    parser.add_argument("--min-english-samples", type=int, default=150)
    parser.add_argument("--max-samples", type=int, default=500)
    parser.add_argument("--max-files-scanned", type=int, default=2000, help="Stop scanning after this many candidate files; use 0 for unlimited.")
    parser.add_argument("--char-limit", type=int, default=20000)
    parser.add_argument("--artifact-prefix", default="minio://ai-quant-local/benchmark-quality")
    args = parser.parse_args()

    result = build_local_benchmark_quality_package(
        input_paths=args.inputs,
        output_dir=args.output_dir,
        benchmark_id=args.benchmark_id,
        target_sample_size=args.target_sample_size,
        min_chinese_samples=args.min_chinese_samples,
        min_english_samples=args.min_english_samples,
        max_samples=args.max_samples,
        max_files_scanned=args.max_files_scanned,
        char_limit=args.char_limit,
        artifact_prefix=args.artifact_prefix,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["run_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
