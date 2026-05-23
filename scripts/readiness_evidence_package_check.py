from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_external_artifact_uri, is_production_artifact_uri


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


REQUIRED_EXTERNAL_VALIDATION_SCOPES = {
    "state_store_object_store_fulltext_search",
    "metrics_logs_traces",
    "graph_vector_semantic_search",
    "lineage_model_registry",
    "kms_rotation_cache_retention_external_delete",
    "desktop_mobile_cross_browser",
}

REQUIRED_CHECK_IDS = {
    "real_data_smoke_test",
    "production_ui_screenshot_acceptance",
    "cross_browser_acceptance",
    "capacity_latency_report",
    "backup_restore_drill",
    "otel_collector_drill",
    "permission_red_team_test",
    "compliance_review_record",
    "launch_checklist",
}

def validate_readiness_evidence_package(
    package: dict[str, Any],
    *,
    required_scopes: set[str] | None = None,
    production_artifacts: bool = True,
) -> dict[str, Any]:
    required_scopes = required_scopes or REQUIRED_EXTERNAL_VALIDATION_SCOPES
    artifact_uri_ok = is_production_artifact_uri if production_artifacts else is_external_artifact_uri
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    expect(package.get("status") == "ready", "package_status", "status must be ready", value=package.get("status"))
    expect(package.get("ready_for_launch") is True, "ready_for_launch", "ready_for_launch must be true", value=package.get("ready_for_launch"))
    expect(int(package.get("missing_evidence_count", -1) or 0) == 0, "missing_evidence_count", "missing evidence count must be 0", value=package.get("missing_evidence_count"))
    expect(int(package.get("failed_gate_count", -1) or 0) == 0, "failed_gate_count", "failed gate count must be 0", value=package.get("failed_gate_count"))
    expect(not package.get("pending_checklist", []), "pending_checklist", "pending checklist must be empty", value=package.get("pending_checklist"))
    try:
        checklist_coverage = float(package.get("checklist_coverage", 0.0))
    except (TypeError, ValueError):
        checklist_coverage = 0.0
    expect(checklist_coverage >= 1.0, "checklist_coverage", "checklist coverage must be 1.0", value=package.get("checklist_coverage"))

    required_evidence_rows = [dict(item) for item in package.get("required_evidence", []) if isinstance(item, dict)]
    check_ids = {str(row.get("check_id", "")) for row in required_evidence_rows}
    missing_check_ids = sorted(REQUIRED_CHECK_IDS - check_ids)
    expect(not missing_check_ids, "required_evidence_check_ids", "required evidence export must include every required readiness check; export with include_passed=true", missing=missing_check_ids)
    duplicate_check_ids = sorted(check_id for check_id in check_ids if sum(1 for row in required_evidence_rows if str(row.get("check_id", "")) == check_id) > 1)
    expect(not duplicate_check_ids, "required_evidence_duplicates", "required evidence export must not contain duplicate check ids", duplicates=duplicate_check_ids)

    raw_required_evidence = package.get("required_evidence", []) or []
    for idx, item in enumerate(raw_required_evidence):
        if not isinstance(item, dict):
            failures.append({"check": "required_evidence_row", "row": idx, "error": "row must be an object"})
    for idx, row in enumerate(required_evidence_rows):
        if not isinstance(row, dict):
            failures.append({"check": "required_evidence_row", "row": idx, "error": "row must be an object"})
            continue
        evidence_uri = row.get("evidence_uri", "")
        expect(str(row.get("status", "")) == "passed", "required_evidence_status", "required evidence row must be passed", row=idx, value=row.get("status"))
        expect(row.get("missing_evidence") is False, "required_evidence_missing", "required evidence row must not be missing evidence", row=idx, value=row.get("missing_evidence"))
        expect(
            artifact_uri_ok(evidence_uri),
            "required_evidence_uri",
            "required evidence URI must be a production/staging archive reference to a concrete object or path",
            row=idx,
            value=evidence_uri,
        )

    validations = [dict(item) for item in package.get("external_validations", []) if isinstance(item, dict)]
    scopes = {str(item.get("scope", "")) for item in validations}
    missing_scopes = sorted(required_scopes - scopes)
    expect(not missing_scopes, "external_validation_scopes", "required external validation scopes missing", missing=missing_scopes)
    for idx, row in enumerate(validations):
        scope = str(row.get("scope", ""))
        evidence_uri = row.get("evidence_uri", "")
        expect(row.get("ready") is True, "external_validation_ready", "external validation must be ready", row=idx, scope=scope, value=row.get("ready"))
        expect(str(row.get("check_status", "")) == "passed", "external_validation_status", "external validation check status must be passed", row=idx, scope=scope, value=row.get("check_status"))
        expect(row.get("outbox_channels_ready") is not False, "external_validation_outbox", "required outbox channels must be present", row=idx, scope=scope, value=row.get("outbox_channels_ready"))
        expect(
            artifact_uri_ok(evidence_uri),
            "external_validation_evidence_uri",
            "external validation evidence URI must be a production/staging archive reference to a concrete object or path",
            row=idx,
            scope=scope,
            value=evidence_uri,
        )

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "package_id": str(package.get("package_id", "")),
        "required_scope_count": len(required_scopes),
        "external_validation_count": len(validations),
        "required_evidence_count": len(required_evidence_rows),
        "missing_check_ids": missing_check_ids if "missing_check_ids" in locals() else sorted(REQUIRED_CHECK_IDS),
        "missing_scopes": missing_scopes if "missing_scopes" in locals() else sorted(required_scopes),
        "failure_count": len(failures),
        "failures": failures,
    }


def load_and_validate_readiness_evidence_package(path: str | Path) -> dict[str, Any]:
    package_path = Path(path)
    data = json.loads(package_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("readiness evidence package must be a JSON object")
    return validate_readiness_evidence_package(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an exported readiness evidence package JSON.")
    parser.add_argument("package_json")
    parser.add_argument("--output", default="", help="Optional path to write the validation result JSON.")
    args = parser.parse_args()
    validation = load_and_validate_readiness_evidence_package(args.package_json)
    rendered = json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
