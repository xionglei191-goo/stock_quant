from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_production_artifact_uri
from scripts.readiness_evidence_package_check import (
    REQUIRED_CHECK_IDS,
    validate_readiness_evidence_package,
)
from scripts.staging_acceptance import DEFAULT_BASE_URL, StagingClient


ALLOWED_DATA_SOURCE_CLASSES = {
    "official_public_disclosure",
    "exchange_regulator_public",
    "tdx_local",
    "local_research_reports",
    "astock_free_connector",
    "free_public_web",
    "simulated_internal",
}

ALLOWED_ASTOCK_CONNECTOR_IDS = {
    "eastmoney_research",
    "cninfo_announcements",
    "tencent_valuation_snapshot",
    "ths_hot_topics",
    "baidu_concepts",
    "dragon_tiger_list",
    "unlock_calendar",
}

SOURCE_GOVERNANCE_UPDATE_FIELDS = {
    "field_whitelist",
    "retention_policy",
    "cache_ttl_days",
    "provenance_ref",
    "usage_scope",
    "collection_method",
    "robots_policy",
    "last_reviewed_at",
    "review_cadence",
    "review_owner",
    "review_owner_role",
    "source_tos_uri",
    "risk_level",
}

SOURCE_REVIEW_FIELDS = {
    "review_id",
    "reviewed_at",
    "review_period",
    "next_review_due_at",
    "reviewer",
    "status",
    "publicness_status",
    "tos_status",
    "robots_status",
    "usage_scope_status",
    "notes",
    "findings",
}

REQUIRED_SOURCE_GOVERNANCE_FIELDS = {
    "source_id",
    "source_class",
    "provenance_ref",
    "source_tos_uri",
    "usage_scope",
    "collection_method",
    "robots_policy",
    "review_cadence",
    "review_status",
    "validation_status",
}

REQUIRED_SOURCE_REVIEW_STATUSES = {"approved", "conditional"}
REQUIRED_SOURCE_VALIDATION_STATUSES = {"verified", "accepted", "passed", "reviewed"}
REQUIRED_ASTOCK_ARTIFACT_FIELDS = {
    "endpoint_artifact_uri",
    "stability_artifact_uri",
    "rate_limit_artifact_uri",
    "license_review_uri",
    "field_sample_uri",
}

REPORT_ENDPOINTS = {
    "storage": ("/api/governance/storage-readiness-report", "platform", "ready_for_storage_production"),
    "security": ("/api/governance/security-readiness-report", "risk_compliance", "ready_for_security_production"),
    "observability": ("/api/observability/readiness-report", "platform", "ready_for_production_observability"),
    "ui": ("/api/readiness/ui-report", "platform", "ready_for_ui_production"),
    "deployment": ("/api/readiness/deployment-report", "platform", "ready_for_production_deployment"),
    "astock_verification": ("/api/connectors/astock/verification-readiness", "risk_compliance", "ready_for_real_acceptance"),
}

DEFAULT_REQUIRED_REPORTS = ["storage", "security", "observability", "ui", "deployment"]


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def load_manifest(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("production closure manifest must be a JSON object")
    return data


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _readiness_checks(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("readiness_checks", manifest.get("checks", {}))
    if isinstance(raw, Mapping):
        return {str(check_id): dict(payload) if isinstance(payload, Mapping) else {"evidence_uri": str(payload)} for check_id, payload in raw.items()}
    checks: dict[str, dict[str, Any]] = {}
    for item in _as_list(raw):
        if isinstance(item, Mapping) and item.get("check_id"):
            checks[str(item["check_id"])] = dict(item)
    return checks


def _required_reports(manifest: Mapping[str, Any], *, require_reports: bool) -> list[str]:
    if not require_reports:
        return []
    raw = manifest.get("required_reports", DEFAULT_REQUIRED_REPORTS)
    return [str(item) for item in _as_list(raw) if str(item)]


def _report_payloads(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("reports", manifest.get("readiness_reports", {}))
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): dict(value) if isinstance(value, Mapping) else {} for key, value in raw.items()}


def _data_sources(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (manifest.get("data_sources", []), manifest.get("source_governance", [])):
        for item in _as_list(raw):
            if not isinstance(item, Mapping):
                continue
            row = dict(item)
            source_id = str(row.get("source_id", "")).strip()
            if source_id and source_id in seen:
                continue
            if source_id:
                seen.add(source_id)
            rows.append(row)
    return rows


def _astock_connector_ids(manifest: Mapping[str, Any]) -> set[str]:
    raw = manifest.get("astock_connectors", manifest.get("connectors", {}))
    if not isinstance(raw, Mapping):
        return set()
    connector_ids = {str(item) for item in _as_list(raw.get("connector_ids", [])) if str(item)}
    for row in _as_list(raw.get("verify", raw.get("verification_results", []))):
        if isinstance(row, Mapping) and row.get("connector_id"):
            connector_ids.add(str(row["connector_id"]))
    readiness = raw.get("verification_readiness", {})
    if isinstance(readiness, Mapping):
        for item in _as_list(readiness.get("connector_ids", readiness.get("connector_id", []))):
            if str(item):
                connector_ids.add(str(item))
    return connector_ids


def _astock_validation_failures(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    raw = manifest.get("astock_connectors", manifest.get("connectors", {}))
    if not isinstance(raw, Mapping):
        return failures
    declared = {str(item) for item in _as_list(raw.get("connector_ids", [])) if str(item)}
    verify_rows = [dict(item) for item in _as_list(raw.get("verify", raw.get("verification_results", []))) if isinstance(item, Mapping)]
    verified_passed = {
        str(item.get("connector_id", ""))
        for item in verify_rows
        if str(item.get("status", "")) == "passed"
    }
    missing_verify = sorted(declared - verified_passed)
    if missing_verify:
        failures.append({"check": "astock_connector_verification", "error": "every declared A-share connector must have passed verification", "missing": missing_verify})

    readiness = raw.get("verification_readiness", {})
    if not isinstance(readiness, Mapping):
        failures.append({"check": "astock_connector_readiness", "error": "verification_readiness payload is required for declared A-share connectors"})
        return failures
    readiness_ids = {
        str(item)
        for item in _as_list(readiness.get("connector_ids", readiness.get("connector_id", [])))
        if str(item)
    }
    missing_readiness = sorted(declared - readiness_ids)
    if missing_readiness:
        failures.append({"check": "astock_connector_readiness_scope", "error": "verification_readiness must include every declared A-share connector", "missing": missing_readiness})
    artifact_uris = readiness.get("artifact_uris", {})
    if not isinstance(artifact_uris, Mapping):
        failures.append({"check": "astock_connector_artifacts", "error": "verification_readiness.artifact_uris must be an object keyed by connector_id"})
        return failures
    for connector_id in sorted(declared):
        connector_artifacts = artifact_uris.get(connector_id, {})
        if not isinstance(connector_artifacts, Mapping):
            failures.append({"check": "astock_connector_artifacts", "connector_id": connector_id, "error": "connector artifact payload is required"})
            continue
        missing_fields = sorted(REQUIRED_ASTOCK_ARTIFACT_FIELDS - set(str(key) for key in connector_artifacts))
        if missing_fields:
            failures.append({"check": "astock_connector_artifact_fields", "connector_id": connector_id, "error": "connector is missing required artifact URIs", "missing": missing_fields})
        for field in sorted(REQUIRED_ASTOCK_ARTIFACT_FIELDS):
            value = str(connector_artifacts.get(field, "")).strip()
            if not is_production_artifact_uri(value):
                failures.append(
                    {
                        "check": "astock_connector_artifact_uri",
                        "connector_id": connector_id,
                        "field": field,
                        "error": "A-share connector artifact URI must be an external production artifact",
                        "value": value,
                    }
                )
    return failures


def _artifact_values(payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    artifact_uris = payload.get("artifact_uris", {})
    if isinstance(artifact_uris, Mapping):
        for key, value in artifact_uris.items():
            if value:
                values.append((str(key), str(value)))
    for key in ("evidence_uri", "artifact_uri"):
        if payload.get(key):
            values.append((key, str(payload[key])))
    return values


def _source_governance_failures(source: Mapping[str, Any], idx: int) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    source_id = str(source.get("source_id", "")).strip()
    source_class = str(source.get("source_class", source.get("class", ""))).strip()
    for field in sorted(REQUIRED_SOURCE_GOVERNANCE_FIELDS):
        value = source.get(field)
        if field == "source_class":
            value = source_class
        if value is None or str(value).strip() == "":
            failures.append({"check": "source_governance_field", "row": idx, "source_id": source_id, "field": field, "error": "required source governance field is missing"})
    field_whitelist = source.get("field_whitelist", [])
    if not isinstance(field_whitelist, list) or not [item for item in field_whitelist if str(item).strip()]:
        failures.append({"check": "source_field_whitelist", "row": idx, "source_id": source_id, "error": "source field whitelist must be a non-empty list"})
    if "cache_ttl_days" not in source:
        failures.append({"check": "source_cache_ttl", "row": idx, "source_id": source_id, "error": "cache_ttl_days is required"})
    else:
        try:
            cache_ttl_days = int(source.get("cache_ttl_days", 0))
        except (TypeError, ValueError):
            cache_ttl_days = -1
        if cache_ttl_days < 0:
            failures.append({"check": "source_cache_ttl", "row": idx, "source_id": source_id, "error": "cache_ttl_days must be >= 0", "value": source.get("cache_ttl_days")})
    rights_tag = source.get("rights_tag", {})
    if not isinstance(rights_tag, Mapping) or not str(rights_tag.get("license_class", "")).strip():
        failures.append({"check": "source_rights_tag", "row": idx, "source_id": source_id, "error": "rights_tag.license_class is required"})
    elif bool(rights_tag.get("training_allowed", False)) or bool(rights_tag.get("redistribution_allowed", False)):
        failures.append({"check": "source_rights_boundary", "row": idx, "source_id": source_id, "error": "production closure sources must not allow training or redistribution by default"})
    review_cadence = str(source.get("review_cadence", "")).strip().lower()
    if review_cadence != "quarterly":
        failures.append({"check": "source_review_cadence", "row": idx, "source_id": source_id, "error": "source review cadence must be quarterly", "value": review_cadence})
    review_status = str(source.get("review_status", source.get("status", ""))).strip()
    if review_status not in REQUIRED_SOURCE_REVIEW_STATUSES:
        failures.append({"check": "source_review_status", "row": idx, "source_id": source_id, "error": "source review status must be approved or conditional", "value": review_status})
    validation_status = str(source.get("validation_status", "")).strip()
    if validation_status not in REQUIRED_SOURCE_VALIDATION_STATUSES:
        failures.append({"check": "source_validation_status", "row": idx, "source_id": source_id, "error": "source validation status must be verified, accepted, passed, or reviewed", "value": validation_status})
    for field in ("governance_artifact_uri", "validation_artifact_uri", "tos_review_artifact_uri", "robots_review_artifact_uri"):
        value = str(source.get(field, "")).strip()
        if value and not is_production_artifact_uri(value):
            failures.append({"check": "source_governance_artifact_uri", "row": idx, "source_id": source_id, "field": field, "error": "source governance artifact URI must be an external production artifact", "value": value})
    return failures


def validate_production_closure_manifest(
    manifest: Mapping[str, Any],
    *,
    require_reports: bool = True,
    require_launch_ready: bool = True,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if require_launch_ready and manifest.get("ready_for_launch") is not True:
        failures.append(
            {
                "check": "ready_for_launch",
                "error": "production closure manifest must set ready_for_launch=true for release validation",
                "value": manifest.get("ready_for_launch"),
            }
        )
    checks = _readiness_checks(manifest)
    missing_checks = sorted(REQUIRED_CHECK_IDS - set(checks))
    if missing_checks:
        failures.append({"check": "readiness_checks", "error": "missing required readiness checks", "missing": missing_checks})
    for check_id, payload in checks.items():
        evidence_uri = str(payload.get("evidence_uri", ""))
        if check_id in REQUIRED_CHECK_IDS and not is_production_artifact_uri(evidence_uri):
            failures.append(
                {
                    "check": "readiness_check_evidence_uri",
                    "check_id": check_id,
                    "error": "readiness check evidence URI must be an external production artifact",
                    "value": evidence_uri,
                }
            )
        status = str(payload.get("status", "passed"))
        if check_id in REQUIRED_CHECK_IDS and status != "passed":
            failures.append({"check": "readiness_check_status", "check_id": check_id, "error": "required readiness check must be passed", "value": status})

    required_reports = _required_reports(manifest, require_reports=require_reports)
    reports = _report_payloads(manifest)
    missing_reports = [name for name in required_reports if name not in reports]
    if missing_reports:
        failures.append({"check": "required_reports", "error": "missing required readiness report payloads", "missing": missing_reports})
    unknown_reports = sorted(set(reports) - set(REPORT_ENDPOINTS))
    if unknown_reports:
        failures.append({"check": "unknown_reports", "error": "unknown readiness report keys", "unknown": unknown_reports})
    for report_name, report in reports.items():
        for key, value in _artifact_values(report):
            if not is_production_artifact_uri(value):
                failures.append(
                    {
                        "check": "report_artifact_uri",
                        "report": report_name,
                        "field": key,
                        "error": "report artifact URI must be an external production artifact",
                        "value": value,
                    }
                )

    for idx, source in enumerate(_data_sources(manifest)):
        source_class = str(source.get("source_class", source.get("class", ""))).strip()
        if source_class and source_class not in ALLOWED_DATA_SOURCE_CLASSES:
            failures.append({"check": "data_source_class", "row": idx, "error": "data source class is outside the frozen production scope", "value": source_class})
        if bool(source.get("requires_paid_license", source.get("paid", False))):
            failures.append({"check": "paid_data_source", "row": idx, "error": "paid or commercial data source is not allowed in production closure"})
        failures.extend(_source_governance_failures(source, idx))

    disallowed_connectors = sorted(_astock_connector_ids(manifest) - ALLOWED_ASTOCK_CONNECTOR_IDS)
    if disallowed_connectors:
        failures.append({"check": "astock_connector_scope", "error": "A-share connector is outside the frozen free/public connector set", "connector_ids": disallowed_connectors})
    failures.extend(_astock_validation_failures(manifest))
    if require_launch_ready:
        package = manifest.get("evidence_package", {})
        if not isinstance(package, Mapping):
            failures.append({"check": "evidence_package", "error": "production closure manifest must include an evidence_package object for release validation"})
        else:
            package_validation = validate_readiness_evidence_package(dict(package))
            if not package_validation["passed"]:
                failures.append({"check": "evidence_package", "error": "embedded evidence_package must pass release validation", "validation": package_validation})

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "required_check_count": len(REQUIRED_CHECK_IDS),
        "required_report_count": len(required_reports),
        "launch_ready_required": require_launch_ready,
        "readiness_check_count": len(checks),
        "report_count": len(reports),
        "allowed_data_source_classes": sorted(ALLOWED_DATA_SOURCE_CLASSES),
        "allowed_astock_connector_ids": sorted(ALLOWED_ASTOCK_CONNECTOR_IDS),
        "failure_count": len(failures),
        "failures": failures,
    }


def _role_for_check(check_id: str) -> str:
    if check_id == "launch_checklist":
        return "CEO"
    if check_id in {"permission_red_team_test", "compliance_review_record"}:
        return "risk_compliance"
    return "platform"


def _record_readiness_checks(client: StagingClient, checks: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for check_id in sorted(checks):
        payload = dict(checks[check_id])
        payload.setdefault("status", "passed")
        payload.setdefault("owner", "production_closure")
        if check_id == "capacity_latency_report" and payload.get("result"):
            record = client.request(
                "POST",
                "/api/readiness/capacity-baseline",
                payload,
                role="platform",
                actor="production_closure",
            )
            records.append(record.get("check", record))
            continue
        body = {
            key: payload[key]
            for key in ["status", "owner", "evidence_uri", "notes", "metrics", "measured_at", "expires_at"]
            if key in payload
        }
        records.append(
            client.request(
                "POST",
                f"/api/readiness/checklist/{check_id}",
                body,
                role=_role_for_check(check_id),
                actor="production_closure",
            )
        )
    return records


def _update_source_governance(client: StagingClient, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if manifest.get("seed_default_sources", True):
        client.request("POST", "/api/ingestion/sources/seed", {}, role="data_engineer", actor="production_closure")
    rows = [item for item in _data_sources(manifest) if item.get("source_id")]
    raw_updates = manifest.get("source_governance_updates", [])
    rows.extend([dict(item) for item in _as_list(raw_updates) if isinstance(item, Mapping) and item.get("source_id")])
    seen: set[str] = set()
    for item in rows:
        source_id = str(item.get("source_id", ""))
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        body = {key: value for key, value in item.items() if key in SOURCE_GOVERNANCE_UPDATE_FIELDS}
        if not body:
            continue
        records.append(
            client.request(
                "POST",
                f"/api/governance/sources/{source_id}",
                body,
                role="risk_compliance",
                actor="production_closure",
            )
        )
    return records


def _source_review_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [dict(item) for item in _as_list(manifest.get("source_reviews", [])) if isinstance(item, Mapping)]
    reviewed = {str(item.get("source_id", "")) for item in rows if item.get("source_id")}
    for source in _data_sources(manifest):
        source_id = str(source.get("source_id", ""))
        if not source_id or source_id in reviewed:
            continue
        review = {key: source[key] for key in SOURCE_REVIEW_FIELDS if key in source}
        review["source_id"] = source_id
        review.setdefault("status", source.get("review_status", "approved"))
        review.setdefault("publicness_status", source.get("publicness_status", "confirmed_public_or_local"))
        review.setdefault("tos_status", source.get("tos_status", "reviewed"))
        review.setdefault("robots_status", source.get("robots_status", "reviewed_or_not_applicable"))
        review.setdefault("usage_scope_status", source.get("usage_scope_status", "within_boundary"))
        notes = str(review.get("notes", "")).strip()
        validation_status = str(source.get("validation_status", "")).strip()
        governance_artifact_uri = str(source.get("governance_artifact_uri", "")).strip()
        review["notes"] = "; ".join(item for item in [notes, f"validation_status={validation_status}" if validation_status else "", f"governance_artifact_uri={governance_artifact_uri}" if governance_artifact_uri else ""] if item)
        rows.append(review)
        reviewed.add(source_id)
    return rows


def _record_source_reviews(client: StagingClient, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _source_review_rows(manifest):
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("source_id", ""))
        if not source_id:
            continue
        body = {key: value for key, value in dict(item).items() if key in SOURCE_REVIEW_FIELDS}
        records.append(
            client.request(
                "POST",
                f"/api/governance/sources/{source_id}/reviews",
                body,
                role="risk_compliance",
                actor="production_closure",
            )
        )
    return records


def _record_secret_rotations(client: StagingClient, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in _as_list(manifest.get("secret_rotations", [])):
        if isinstance(item, Mapping):
            records.append(client.request("POST", "/api/governance/secret-rotations", dict(item), role="risk_compliance", actor="production_closure"))
    return records


def _record_astock_connectors(client: StagingClient, manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw = manifest.get("astock_connectors", manifest.get("connectors", {}))
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, Any] = {}
    if raw.get("seed", False):
        result["seed"] = client.request("POST", "/api/connectors/astock/seed", {}, role="data_engineer", actor="production_closure")
    verify_rows = [dict(item) for item in _as_list(raw.get("verify", raw.get("verification_results", []))) if isinstance(item, Mapping)]
    if verify_rows:
        result["verify"] = client.request("POST", "/api/connectors/astock/verify", {"results": verify_rows}, role="data_engineer", actor="production_closure")
    readiness = raw.get("verification_readiness", {})
    if isinstance(readiness, Mapping) and readiness:
        body = dict(readiness)
        body.setdefault("record_readiness", True)
        result["verification_readiness"] = client.request("POST", "/api/connectors/astock/verification-readiness", body, role="risk_compliance", actor="production_closure")
    return result


def _run_reports(client: StagingClient, reports: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name, payload in reports.items():
        endpoint, role, ready_field = REPORT_ENDPOINTS[name]
        body = dict(payload)
        body.setdefault("record_readiness", True)
        report = client.request("POST", endpoint, body, role=role, actor="production_closure")
        report["_ready_field"] = ready_field
        report["_ready"] = bool(report.get(ready_field))
        results[name] = report
    return results


def run_production_closure(
    *,
    base_url: str = DEFAULT_BASE_URL,
    manifest: Mapping[str, Any],
    timeout: float = 10.0,
    require_reports: bool = True,
    dry_run: bool = False,
    notify_missing: bool = False,
) -> dict[str, Any]:
    manifest_validation = validate_production_closure_manifest(manifest, require_reports=require_reports, require_launch_ready=True)
    if not manifest_validation["passed"] or dry_run:
        return {
            "status": "passed" if manifest_validation["passed"] else "failed",
            "dry_run": dry_run,
            "stage": "manifest_validation",
            "manifest_validation": manifest_validation,
            "production_boundary": "closure_script_validates_real_external_artifacts_without_enabling_live_execution",
        }

    client = StagingClient(base_url, timeout=timeout)
    source_governance = _update_source_governance(client, manifest)
    source_reviews = _record_source_reviews(client, manifest)
    secret_rotations = _record_secret_rotations(client, manifest)
    astock = _record_astock_connectors(client, manifest)
    readiness_records = _record_readiness_checks(client, _readiness_checks(manifest))
    reports = _run_reports(client, _report_payloads(manifest))
    report_failures = [
        {"report": name, "ready_field": report["_ready_field"], "missing_requirements": report.get("missing_requirements", [])}
        for name, report in reports.items()
        if not report.get("_ready")
    ]
    package = client.request(
        "POST",
        "/api/readiness/evidence-package",
        {"include_passed": True, "record_export": True, **dict(manifest.get("evidence_package", {}))},
        role="CEO",
        actor="production_closure",
    )
    package_validation = validate_readiness_evidence_package(package)
    notifications = None
    if notify_missing and not package_validation["passed"]:
        notifications = client.request("POST", "/api/readiness/evidence-package/notify", {}, role="risk_compliance", actor="production_closure")
    passed = manifest_validation["passed"] and not report_failures and package_validation["passed"]
    return {
        "status": "passed" if passed else "failed",
        "dry_run": False,
        "stage": "production_closure",
        "base_url": base_url,
        "manifest_validation": manifest_validation,
        "source_governance": source_governance,
        "source_reviews": source_reviews,
        "secret_rotations": secret_rotations,
        "astock_connectors": astock,
        "readiness_records": readiness_records,
        "reports": reports,
        "report_failures": report_failures,
        "evidence_package": package,
        "evidence_package_validation": package_validation,
        "notifications": notifications,
        "production_boundary": "closure_script_records_release_evidence_only_no_live_broker_or_automatic_order_execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Close production readiness from a real evidence manifest.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--manifest", required=True, help="JSON manifest containing real production/staging evidence URIs.")
    parser.add_argument("--output", default="", help="Optional path to write the closure result JSON.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--dry-run", action="store_true", help="Validate the manifest without writing readiness records.")
    parser.add_argument("--skip-report-readiness", action="store_true", help="Do not require storage/security/observability/UI/deployment report payloads in the manifest.")
    parser.add_argument("--notify-missing", action="store_true", help="Create readiness notification outbox records if the final package is not ready.")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    result = run_production_closure(
        base_url=args.base_url,
        manifest=manifest,
        timeout=args.timeout,
        require_reports=not args.skip_report_readiness,
        dry_run=args.dry_run,
        notify_missing=args.notify_missing,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
