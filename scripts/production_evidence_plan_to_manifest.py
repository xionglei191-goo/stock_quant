from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_closure import load_manifest, validate_production_closure_manifest
from scripts.production_evidence_plan_check import validate_evidence_collection_plan
from scripts.readiness_evidence_package_check import (
    REQUIRED_CHECK_IDS,
    REQUIRED_EXTERNAL_VALIDATION_SCOPES,
    validate_readiness_evidence_package,
)


READINESS_CHECK_FIELD_MAPPINGS: dict[tuple[str, str], str] = {
    ("T-416", "field_sample_uri"): "real_data_smoke_test",
    ("T-407", "screenshot_manifest_uri"): "production_ui_screenshot_acceptance",
    ("T-407", "cross_browser_matrix_uri"): "cross_browser_acceptance",
    ("T-412", "capacity_baseline_uri"): "capacity_latency_report",
    ("T-412", "backup_restore_evidence_uri"): "backup_restore_drill",
    ("T-411", "drill_evidence_uri"): "otel_collector_drill",
    ("T-421", "permission_review_uri"): "permission_red_team_test",
    ("T-414", "citation_policy_uri"): "compliance_review_record",
    ("T-412", "release_checklist_uri"): "launch_checklist",
}

REPORT_FIELD_MAPPINGS: dict[tuple[str, str], str] = {
    ("T-404", "postgres_smoke_uri"): "storage",
    ("T-404", "s3_smoke_uri"): "storage",
    ("T-404", "opensearch_smoke_uri"): "storage",
    ("T-404", "capacity_baseline_uri"): "storage",
    ("T-404", "backup_restore_uri"): "storage",
    ("T-404", "least_privilege_policy_uri"): "storage",
    ("T-407", "browser_acceptance_uri"): "ui",
    ("T-407", "screenshot_manifest_uri"): "ui",
    ("T-407", "cross_browser_matrix_uri"): "ui",
    ("T-407", "real_data_workflow_uri"): "ui",
    ("T-407", "visual_overflow_review_uri"): "ui",
    ("T-407", "access_control_review_uri"): "ui",
    ("T-411", "collector_evidence_uri"): "observability",
    ("T-411", "logs_backend_uri"): "observability",
    ("T-411", "query_evidence_uri"): "observability",
    ("T-411", "retention_policy_uri"): "observability",
    ("T-411", "external_alert_evidence_uri"): "observability",
    ("T-411", "drill_evidence_uri"): "observability",
    ("T-412", "production_parameters_uri"): "deployment",
    ("T-412", "secret_manager_evidence_uri"): "deployment",
    ("T-412", "backup_restore_evidence_uri"): "deployment",
    ("T-412", "capacity_baseline_uri"): "deployment",
    ("T-412", "release_checklist_uri"): "deployment",
    ("T-412", "canary_plan_uri"): "deployment",
    ("T-412", "rollback_plan_uri"): "deployment",
    ("T-421", "secret_manager_evidence_uri"): "security",
    ("T-421", "least_privilege_policy_uri"): "security",
    ("T-421", "external_delete_evidence_uri"): "security",
    ("T-421", "permission_review_uri"): "security",
}

ASTOCK_CONNECTOR_FIELD_MAPPINGS = {
    "endpoint_artifact_uri",
    "stability_artifact_uri",
    "rate_limit_artifact_uri",
    "license_review_uri",
    "field_sample_uri",
}

EXTERNAL_VALIDATION_SCOPE_MAPPINGS: dict[str, tuple[str, str]] = {
    "state_store_object_store_fulltext_search": ("T-404", "postgres_smoke_uri"),
    "metrics_logs_traces": ("T-411", "collector_evidence_uri"),
    "graph_vector_semantic_search": ("T-419", "neo4j_sync_artifact_uri"),
    "lineage_model_registry": ("T-420", "openlineage_client_uri"),
    "kms_rotation_cache_retention_external_delete": ("T-421", "secret_manager_evidence_uri"),
    "desktop_mobile_cross_browser": ("T-407", "cross_browser_matrix_uri"),
}

EXTERNAL_VALIDATION_COMPONENT_TASKS = {
    "state_store_object_store_fulltext_search": "T-404",
    "metrics_logs_traces": "T-411",
    "graph_vector_semantic_search": "T-419",
    "lineage_model_registry": "T-420",
    "kms_rotation_cache_retention_external_delete": "T-421",
    "desktop_mobile_cross_browser": "T-407",
}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{label} must be a JSON object")
    return data


def _plan_rows(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in plan.get("tasks", []) if isinstance(item, Mapping)]


def _plan_artifacts(plan: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    artifacts: dict[str, dict[str, str]] = {}
    for row in _plan_rows(plan):
        task_id = str(row.get("task_id", ""))
        raw = row.get("artifact_uri_template", {})
        if not task_id or not isinstance(raw, Mapping):
            continue
        artifacts[task_id] = {str(key): str(value) for key, value in raw.items()}
    return artifacts


def _set_report_artifact(manifest: dict[str, Any], report_name: str, field: str, uri: str) -> None:
    reports = manifest.setdefault("reports", {})
    if not isinstance(reports, dict):
        manifest["reports"] = {}
        reports = manifest["reports"]
    report = reports.setdefault(report_name, {})
    if not isinstance(report, dict):
        reports[report_name] = {}
        report = reports[report_name]
    artifact_uris = report.setdefault("artifact_uris", {})
    if not isinstance(artifact_uris, dict):
        report["artifact_uris"] = {}
        artifact_uris = report["artifact_uris"]
    artifact_uris[field] = uri


def _set_readiness_check(manifest: dict[str, Any], check_id: str, uri: str, *, task_id: str, field: str) -> None:
    checks = manifest.setdefault("readiness_checks", {})
    if not isinstance(checks, dict):
        manifest["readiness_checks"] = {}
        checks = manifest["readiness_checks"]
    check = checks.setdefault(check_id, {})
    if not isinstance(check, dict):
        checks[check_id] = {}
        check = checks[check_id]
    check.update(
        {
            "status": "passed",
            "evidence_uri": uri,
            "source_task_id": task_id,
            "source_field": field,
        }
    )


def _set_astock_connector_artifacts(manifest: dict[str, Any], field: str, uri: str) -> list[str]:
    astock = manifest.setdefault("astock_connectors", {})
    if not isinstance(astock, dict):
        manifest["astock_connectors"] = {}
        astock = manifest["astock_connectors"]
    readiness = astock.setdefault("verification_readiness", {})
    if not isinstance(readiness, dict):
        astock["verification_readiness"] = {}
        readiness = astock["verification_readiness"]
    connector_ids = [str(item) for item in readiness.get("connector_ids", astock.get("connector_ids", [])) if str(item)]
    artifact_uris = readiness.setdefault("artifact_uris", {})
    if not isinstance(artifact_uris, dict):
        readiness["artifact_uris"] = {}
        artifact_uris = readiness["artifact_uris"]
    touched: list[str] = []
    for connector_id in connector_ids:
        connector_payload = artifact_uris.setdefault(connector_id, {})
        if not isinstance(connector_payload, dict):
            artifact_uris[connector_id] = {}
            connector_payload = artifact_uris[connector_id]
        connector_payload[field] = uri
        touched.append(connector_id)
    return touched


def _task_evidence(plan: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    task_evidence: dict[str, dict[str, Any]] = {}
    for row in _plan_rows(plan):
        task_id = str(row.get("task_id", ""))
        if not task_id:
            continue
        raw_artifacts = row.get("artifact_uri_template", {})
        task_evidence[task_id] = {
            "source_status": row.get("status", ""),
            "owner_role": row.get("owner_role", ""),
            "readiness_endpoint": row.get("readiness_endpoint", ""),
            "external_evidence_blockers": row.get("external_evidence_blockers", []),
            "artifact_fields": row.get("artifact_fields", []),
            "artifact_uris": dict(raw_artifacts) if isinstance(raw_artifacts, Mapping) else {},
            "acceptance_rule": row.get("acceptance_rule", ""),
            "source_plan_id": plan.get("plan_id", ""),
        }
    return task_evidence


def _build_draft_evidence_package(
    *,
    manifest: Mapping[str, Any],
    task_artifacts: Mapping[str, Mapping[str, str]],
    mapped_check_ids: set[str],
    mapped_scopes: set[str],
) -> dict[str, Any]:
    checks = manifest.get("readiness_checks", {})
    required_evidence = []
    if isinstance(checks, Mapping):
        for check_id in sorted(REQUIRED_CHECK_IDS):
            payload = checks.get(check_id, {})
            if not isinstance(payload, Mapping):
                continue
            required_evidence.append(
                {
                    "check_id": check_id,
                    "status": payload.get("status", "passed"),
                    "missing_evidence": False,
                    "evidence_uri": payload.get("evidence_uri", ""),
                    "source_task_id": payload.get("source_task_id", ""),
                    "source_field": payload.get("source_field", ""),
                }
            )

    external_validations = []
    for scope in sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES):
        task_id, field = EXTERNAL_VALIDATION_SCOPE_MAPPINGS.get(scope, ("", ""))
        artifacts = dict(task_artifacts.get(task_id, {}))
        external_validations.append(
            {
                "scope": scope,
                "check_status": "passed" if scope in mapped_scopes else "pending",
                "ready": scope in mapped_scopes,
                "outbox_channels_ready": True,
                "evidence_uri": artifacts.get(field, ""),
                "source_task_id": task_id,
                "source_field": field,
                "component_evidence_uris": artifacts,
            }
        )

    missing_checks = sorted(REQUIRED_CHECK_IDS - mapped_check_ids)
    missing_scopes = sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES - mapped_scopes)
    return {
        "package_id": "production_closure_manifest_draft",
        "status": "draft",
        "ready_for_launch": False,
        "missing_evidence_count": len(missing_checks),
        "failed_gate_count": 0,
        "checklist_coverage": round(len(mapped_check_ids) / max(len(REQUIRED_CHECK_IDS), 1), 4),
        "pending_checklist": missing_checks,
        "required_evidence": required_evidence,
        "external_validations": external_validations,
        "missing_external_validation_scopes": missing_scopes,
        "production_boundary": "draft package assembled from owner-filled task evidence; export a real readiness package before release",
    }


def build_manifest_from_evidence_plan(
    plan: Mapping[str, Any],
    *,
    base_manifest: Mapping[str, Any],
    allow_placeholders: bool = False,
    evidence_package: Mapping[str, Any] | None = None,
    release_ready: bool = False,
) -> dict[str, Any]:
    structural_validation = validate_evidence_collection_plan(plan, require_filled_uris=False)
    if not structural_validation["passed"]:
        raise AssertionError(json.dumps({"stage": "plan_structure", "validation": structural_validation}, ensure_ascii=False, sort_keys=True))

    filled_validation = validate_evidence_collection_plan(plan, require_filled_uris=True)
    if not allow_placeholders and not filled_validation["passed"]:
        raise AssertionError(json.dumps({"stage": "filled_uri_validation", "validation": filled_validation}, ensure_ascii=False, sort_keys=True))

    manifest = deepcopy(dict(base_manifest))
    manifest["ready_for_launch"] = False
    task_artifacts = _plan_artifacts(plan)
    manifest["task_evidence"] = _task_evidence(plan)

    release_field_mapping_enabled = bool(filled_validation["passed"])
    mapped_fields: list[dict[str, Any]] = []
    skipped_mappings: list[dict[str, Any]] = []
    mapped_check_ids: set[str] = set()
    mapped_scopes: set[str] = set()

    def record_mapping(task_id: str, field: str, target: str, uri: str, **extra: Any) -> None:
        mapped_fields.append({"task_id": task_id, "field": field, "target": target, "uri": uri, **extra})

    for task_id, fields in sorted(task_artifacts.items()):
        for field, uri in sorted(fields.items()):
            key = (task_id, field)
            if not release_field_mapping_enabled:
                if key in READINESS_CHECK_FIELD_MAPPINGS or key in REPORT_FIELD_MAPPINGS or (task_id == "T-416" and field in ASTOCK_CONNECTOR_FIELD_MAPPINGS):
                    skipped_mappings.append(
                        {
                            "task_id": task_id,
                            "field": field,
                            "uri": uri,
                            "reason": "artifact URI still contains placeholder or is not a concrete production/staging archive URI",
                        }
                    )
                continue
            check_id = READINESS_CHECK_FIELD_MAPPINGS.get(key)
            if check_id:
                _set_readiness_check(manifest, check_id, uri, task_id=task_id, field=field)
                mapped_check_ids.add(check_id)
                record_mapping(task_id, field, f"readiness_checks.{check_id}.evidence_uri", uri)
            report_name = REPORT_FIELD_MAPPINGS.get(key)
            if report_name:
                _set_report_artifact(manifest, report_name, field, uri)
                record_mapping(task_id, field, f"reports.{report_name}.artifact_uris.{field}", uri)
            if task_id == "T-416" and field in ASTOCK_CONNECTOR_FIELD_MAPPINGS:
                connector_ids = _set_astock_connector_artifacts(manifest, field, uri)
                record_mapping(
                    task_id,
                    field,
                    "astock_connectors.verification_readiness.artifact_uris.*",
                    uri,
                    connector_ids=connector_ids,
                )

    if release_field_mapping_enabled:
        for scope, (task_id, field) in sorted(EXTERNAL_VALIDATION_SCOPE_MAPPINGS.items()):
            if task_artifacts.get(task_id, {}).get(field):
                mapped_scopes.add(scope)

    if evidence_package is not None:
        package = deepcopy(dict(evidence_package))
        package_validation = validate_readiness_evidence_package(package)
        if not package_validation["passed"]:
            raise AssertionError(json.dumps({"stage": "evidence_package_validation", "validation": package_validation}, ensure_ascii=False, sort_keys=True))
        manifest["evidence_package"] = package
    else:
        manifest["evidence_package"] = _build_draft_evidence_package(
            manifest=manifest,
            task_artifacts=task_artifacts,
            mapped_check_ids=mapped_check_ids,
            mapped_scopes=mapped_scopes,
        )

    if release_ready:
        if evidence_package is None:
            raise AssertionError("release_ready requires --evidence-package exported from the real staging/production readiness endpoint")
        manifest["ready_for_launch"] = True

    template_validation = validate_production_closure_manifest(manifest, require_launch_ready=False)
    release_validation = validate_production_closure_manifest(manifest, require_launch_ready=True)
    missing_readiness_checks = sorted(REQUIRED_CHECK_IDS - mapped_check_ids)
    missing_external_validation_scopes = sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES - mapped_scopes)
    manifest["manifest_generation"] = {
        "generator": "scripts/production_evidence_plan_to_manifest.py",
        "plan_id": plan.get("plan_id", ""),
        "structural_validation": structural_validation,
        "filled_uri_validation": filled_validation,
        "release_field_mapping_enabled": release_field_mapping_enabled,
        "mapped_field_count": len(mapped_fields),
        "mapped_fields": mapped_fields,
        "skipped_mapping_count": len(skipped_mappings),
        "skipped_mappings": skipped_mappings,
        "mapped_readiness_check_count": len(mapped_check_ids),
        "mapped_readiness_checks": sorted(mapped_check_ids),
        "mapped_external_validation_scope_count": len(mapped_scopes),
        "mapped_external_validation_scopes": sorted(mapped_scopes),
        "missing_readiness_check_count": len(missing_readiness_checks),
        "missing_readiness_checks_from_plan": missing_readiness_checks,
        "missing_external_validation_scope_count": len(missing_external_validation_scopes),
        "missing_external_validation_scopes_from_plan": missing_external_validation_scopes,
        "template_validation": template_validation,
        "release_validation": release_validation,
        "next_gate": "run production_closure_manifest_check.py; strict release validation still requires ready_for_launch=true and a real exported evidence_package",
    }
    if release_ready and not release_validation["passed"]:
        raise AssertionError(json.dumps({"stage": "release_manifest_validation", "validation": release_validation}, ensure_ascii=False, sort_keys=True))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a production closure manifest draft from a filled external evidence collection plan.")
    parser.add_argument("--plan", required=True, help="External evidence collection plan JSON.")
    parser.add_argument(
        "--base",
        default=str(ROOT / "artifacts/production-closure-manifest.example.json"),
        help="Base production closure manifest template.",
    )
    parser.add_argument("--output", default="", help="Optional path to write the generated manifest JSON.")
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow template plans that still contain placeholder URI tokens; release fields will not be overwritten by placeholders.",
    )
    parser.add_argument(
        "--evidence-package",
        default="",
        help="Optional real readiness evidence package export to embed in the manifest.",
    )
    parser.add_argument(
        "--release-ready",
        action="store_true",
        help="Set ready_for_launch=true after embedding a valid real evidence package and passing strict manifest validation.",
    )
    args = parser.parse_args()

    try:
        plan = load_json_object(args.plan, label="evidence plan")
        base_manifest = load_manifest(args.base)
        package = load_json_object(args.evidence_package, label="readiness evidence package") if args.evidence_package else None
        manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            allow_placeholders=args.allow_placeholders,
            evidence_package=package,
            release_ready=args.release_ready,
        )
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    rendered = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
