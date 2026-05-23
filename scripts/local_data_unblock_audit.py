from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DATA_BLOCKING_REQUIREMENTS = {
    "sample_size",
    "chinese_sample_count",
    "english_sample_count",
}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _load_json_object(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must be a JSON object")
    return data


def _int_value(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def audit_local_data_unblock(
    *,
    quality_package_path: str | Path = ROOT / "artifacts/benchmark-quality-package/quality-package.json",
    sample_manifest_path: str | Path = ROOT / "artifacts/benchmark-quality-package/sample-manifest.json",
    sec_fetch_manifest_path: str | Path = ROOT / "artifacts/benchmark-sample-fetch/fetch-manifest.json",
    ashare_fetch_manifest_path: str | Path = ROOT / "artifacts/benchmark-sample-fetch-ashare/fetch-manifest.json",
    target_sample_size: int = 300,
    min_chinese_samples: int = 150,
    min_english_samples: int = 150,
) -> dict[str, Any]:
    quality_package = _load_json_object(quality_package_path)
    sample_manifest = _load_json_object(sample_manifest_path)
    sec_fetch = _load_json_object(sec_fetch_manifest_path) if Path(sec_fetch_manifest_path).exists() else {}
    ashare_fetch = _load_json_object(ashare_fetch_manifest_path) if Path(ashare_fetch_manifest_path).exists() else {}

    language_counts = dict(quality_package.get("language_counts") or sample_manifest.get("language_counts") or {})
    source_counts = dict(quality_package.get("source_counts") or sample_manifest.get("source_counts") or {})
    sample_count = _int_value(quality_package, "sample_count") or _int_value(sample_manifest, "sample_count")
    target_gap = max(0, target_sample_size - sample_count)
    missing_requirements = [str(item) for item in quality_package.get("readiness_missing_requirements", [])]
    data_blockers = sorted(set(missing_requirements) & DATA_BLOCKING_REQUIREMENTS)
    quality_gaps = [item for item in missing_requirements if item not in DATA_BLOCKING_REQUIREMENTS]

    sec_created = _int_value(sec_fetch, "created_count")
    sec_errors = _int_value(sec_fetch, "error_count")
    ashare_errors = _int_value(ashare_fetch, "error_count")
    ashare_skipped = _int_value(ashare_fetch, "skipped_count")
    ashare_attachment_attempts = sum(
        1
        for row in ashare_fetch.get("skipped", [])
        if isinstance(row, Mapping) and row.get("attachment_attempted") is True
    )

    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    expect(sample_count >= target_sample_size, "sample_count", "benchmark data sample count is below target", value=sample_count, target=target_sample_size)
    expect(target_gap == 0, "target_gap", "benchmark data still has a sample-size gap", value=target_gap)
    expect(int(language_counts.get("zh", 0) or 0) >= min_chinese_samples, "chinese_sample_count", "Chinese benchmark samples are below target", value=language_counts.get("zh"), target=min_chinese_samples)
    expect(int(language_counts.get("en", 0) or 0) >= min_english_samples, "english_sample_count", "English benchmark samples are below target", value=language_counts.get("en"), target=min_english_samples)
    expect(not data_blockers, "readiness_data_blockers", "readiness report still has data-blocking requirements", blockers=data_blockers)
    expect(bool(source_counts), "source_counts", "quality package must record source coverage counts")
    expect(sec_created > 0 and sec_errors == 0, "sec_public_fetch", "SEC public disclosure fetch should have usable samples and no errors", created=sec_created, errors=sec_errors)
    expect(ashare_errors == 0, "ashare_public_fetch_errors", "A-share public fetch should not have connector-level errors", errors=ashare_errors)

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "data_blocked": not passed,
        "deployment_target": "local_only_personal_production",
        "sample_count": sample_count,
        "target_sample_size": target_sample_size,
        "target_gap": target_gap,
        "language_counts": language_counts,
        "source_counts": source_counts,
        "data_blockers": data_blockers,
        "remaining_quality_gaps": quality_gaps,
        "sec_fetch": {
            "status": sec_fetch.get("status", "missing"),
            "created_count": sec_created,
            "error_count": sec_errors,
        },
        "ashare_fetch": {
            "status": ashare_fetch.get("status", "missing"),
            "created_count": _int_value(ashare_fetch, "created_count"),
            "skipped_count": ashare_skipped,
            "error_count": ashare_errors,
            "attachment_attempted_count": ashare_attachment_attempts,
        },
        "failures": failures,
        "production_boundary": "data_unblock_audit_only_confirms_local_sample_availability_and_public_connector_paths; remaining_quality_gaps_are_extraction_or_manual_gold_label_work_not_data_source_blockers",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether local/public data availability still blocks the local workflow.")
    parser.add_argument("--quality-package", default=str(ROOT / "artifacts/benchmark-quality-package/quality-package.json"))
    parser.add_argument("--sample-manifest", default=str(ROOT / "artifacts/benchmark-quality-package/sample-manifest.json"))
    parser.add_argument("--sec-fetch-manifest", default=str(ROOT / "artifacts/benchmark-sample-fetch/fetch-manifest.json"))
    parser.add_argument("--ashare-fetch-manifest", default=str(ROOT / "artifacts/benchmark-sample-fetch-ashare/fetch-manifest.json"))
    parser.add_argument("--target-sample-size", type=int, default=300)
    parser.add_argument("--min-chinese-samples", type=int, default=150)
    parser.add_argument("--min-english-samples", type=int, default=150)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = audit_local_data_unblock(
        quality_package_path=args.quality_package,
        sample_manifest_path=args.sample_manifest,
        sec_fetch_manifest_path=args.sec_fetch_manifest,
        ashare_fetch_manifest_path=args.ashare_fetch_manifest,
        target_sample_size=args.target_sample_size,
        min_chinese_samples=args.min_chinese_samples,
        min_english_samples=args.min_english_samples,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
