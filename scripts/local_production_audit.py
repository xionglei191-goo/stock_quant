from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import urljoin
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_external_artifact_uri
from scripts.readiness_evidence_package_check import (
    REQUIRED_CHECK_IDS,
    REQUIRED_EXTERNAL_VALIDATION_SCOPES,
)


LOCAL_ACCEPTED_ARTIFACT_PREFIXES = (
    "artifact://staging-local/",
    "artifact://local-staging/",
    "artifact://local-production/",
    "artifact://local-prod/",
    "s3://ai-quant-local/",
    "minio://ai-quant-local/",
)


def _unwrap_response(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), Mapping):
        return payload["data"]
    return payload


def _fetch_json(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    with urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return data


def _load_json_object(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{path} must be a JSON object")
    return data


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _failure_result(*, check: str, error: BaseException) -> dict[str, Any]:
    return {
        "status": "failed",
        "passed": False,
        "deployment_target": "local_only_personal_production",
        "production_boundary": "valid for this machine as the user's long-running local production profile; not valid as non-local organizational release evidence and does not enable live broker execution",
        "strict_production_gate_unchanged": True,
        "ready_for_launch": False,
        "warning_count": 0,
        "failure_count": 1,
        "warnings": [],
        "failures": [
            {
                "check": check,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        ],
    }


def _local_artifact_uri_ok(value: Any) -> bool:
    uri = str(value or "").strip()
    if not is_external_artifact_uri(uri):
        return False
    return uri.startswith(LOCAL_ACCEPTED_ARTIFACT_PREFIXES) or uri.startswith(("s3://", "gs://", "oss://", "artifact://prod-"))


def build_local_production_audit(
    *,
    health: Mapping[str, Any],
    vision_gate: Mapping[str, Any],
    evidence_package: Mapping[str, Any],
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    health_data = _unwrap_response(health)
    vision_data = _unwrap_response(vision_gate)
    package_data = _unwrap_response(evidence_package)
    metrics_data = _unwrap_response(metrics or {})
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    def warn(condition: bool, check: str, message: str, **extra: Any) -> None:
        if not condition:
            warnings.append({"check": check, "message": message, **extra})

    expect(health_data.get("status") == "ok", "health", "local service health must be ok", value=health_data.get("status"))
    expect(health_data.get("store") == "PostgreSQLStore", "state_store", "local production profile should use PostgreSQLStore", value=health_data.get("store"))
    object_store = health_data.get("object_store", {})
    search_index = health_data.get("search_index", {})
    expect(isinstance(object_store, Mapping) and object_store.get("backend") == "s3", "object_store", "local production profile should use S3/MinIO object storage", value=object_store)
    expect(isinstance(search_index, Mapping) and search_index.get("backend") == "opensearch", "search_index", "local production profile should use OpenSearch", value=search_index)
    warn(bool(health_data.get("tdx_market_data", {}).get("configured")), "tdx_market_data", "TDX market data is not configured; local market-data workflows may be limited")
    llm_gateway = health_data.get("llm_gateway", {})
    document_parser = health_data.get("document_parser", {})
    warn(isinstance(llm_gateway, Mapping) and bool(llm_gateway.get("configured")), "llm_gateway", "LLM gateway is not configured; local AI-assisted workflows will use fallback paths")
    warn(isinstance(document_parser, Mapping) and bool(document_parser.get("configured")), "paddleocr", "PaddleOCR-VL is not configured; scanned-document fallback parsing will be unavailable")

    gates = [dict(item) for item in vision_data.get("gates", []) if isinstance(item, Mapping)]
    failed_gates = [item for item in gates if item.get("passed") is not True]
    expect(vision_data.get("status") == "ready", "vision_gate_status", "vision gate must be ready", value=vision_data.get("status"))
    expect(not failed_gates, "vision_gates", "all vision gates must pass", failures=failed_gates)

    expect(package_data.get("status") == "ready", "evidence_package_status", "readiness evidence package must be ready", value=package_data.get("status"))
    expect(package_data.get("ready_for_launch") is True, "ready_for_launch", "local production package must be ready_for_launch=true")
    expect(int(package_data.get("missing_evidence_count", -1)) == 0, "missing_evidence", "local production package must have no missing required evidence", value=package_data.get("missing_evidence_count"))
    expect(int(package_data.get("failed_gate_count", -1)) == 0, "failed_gate_count", "local production package must have no failed gates", value=package_data.get("failed_gate_count"))
    expect(float(package_data.get("checklist_coverage", 0.0) or 0.0) >= 1.0, "checklist_coverage", "local production checklist coverage must be 1.0", value=package_data.get("checklist_coverage"))

    required_evidence = [dict(item) for item in package_data.get("required_evidence", []) if isinstance(item, Mapping)]
    evidence_by_check = {str(item.get("check_id", "")): item for item in required_evidence}
    missing_checks = sorted(REQUIRED_CHECK_IDS - set(evidence_by_check))
    expect(not missing_checks, "required_check_ids", "local production package must include every required readiness check", missing=missing_checks)
    for check_id in sorted(REQUIRED_CHECK_IDS):
        row = evidence_by_check.get(check_id, {})
        expect(row.get("status") == "passed", "required_evidence_status", "required evidence row must be passed", check_id=check_id, value=row.get("status"))
        expect(row.get("missing_evidence") is False, "required_evidence_missing", "required evidence row must not be missing", check_id=check_id, value=row.get("missing_evidence"))
        expect(_local_artifact_uri_ok(row.get("evidence_uri")), "required_evidence_uri", "required evidence URI must be a concrete local/production artifact URI", check_id=check_id, value=row.get("evidence_uri"))

    validations = [dict(item) for item in package_data.get("external_validations", []) if isinstance(item, Mapping)]
    scopes = {str(item.get("scope", "")) for item in validations}
    missing_scopes = sorted(REQUIRED_EXTERNAL_VALIDATION_SCOPES - scopes)
    expect(not missing_scopes, "external_validation_scopes", "local package should report every external validation scope", missing=missing_scopes)
    not_ready_scopes = [item for item in validations if item.get("ready") is not True or item.get("check_status") != "passed"]
    warn(not not_ready_scopes, "external_validation_ready", "some adapter validation scopes are not marked fully ready in the package; keep the individual staging acceptance artifacts attached", scopes=[item.get("scope") for item in not_ready_scopes])

    if metrics_data:
        expect(int(metrics_data.get("pending_prompt_changes", 0) or 0) == 0, "pending_prompt_changes", "pending prompt changes must be zero", value=metrics_data.get("pending_prompt_changes"))
        expect(int(metrics_data.get("sensitive_findings", 0) or 0) == 0, "sensitive_findings", "sensitive findings must be zero", value=metrics_data.get("sensitive_findings"))
        expect(int(metrics_data.get("source_review_overdue", 0) or 0) == 0, "source_review_overdue", "source review overdue count must be zero", value=metrics_data.get("source_review_overdue"))
        warn(int(metrics_data.get("workflow_failed_runs", 0) or 0) == 0, "workflow_failed_runs", "workflow failed runs remain in local metrics; verify they are expected drill records", value=metrics_data.get("workflow_failed_runs"))
        warn(int(metrics_data.get("open_alerts", 0) or 0) == 0, "open_alerts", "open alerts remain in local metrics; verify they are expected governance/drill alerts", value=metrics_data.get("open_alerts"))

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "deployment_target": "local_only_personal_production",
        "production_boundary": "valid for this machine as the user's long-running local production profile; not valid as non-local organizational release evidence and does not enable live broker execution",
        "strict_production_gate_unchanged": True,
        "health_summary": {
            "store": health_data.get("store", ""),
            "object_store_backend": object_store.get("backend", "") if isinstance(object_store, Mapping) else "",
            "search_backend": search_index.get("backend", "") if isinstance(search_index, Mapping) else "",
            "tdx_market_data_configured": bool(health_data.get("tdx_market_data", {}).get("configured")),
            "llm_gateway_configured": bool(llm_gateway.get("configured")) if isinstance(llm_gateway, Mapping) else False,
            "llm_default_model": str(llm_gateway.get("default_model", "")) if isinstance(llm_gateway, Mapping) else "",
            "paddleocr_configured": bool(document_parser.get("configured")) if isinstance(document_parser, Mapping) else False,
            "paddleocr_model": str(document_parser.get("model", "")) if isinstance(document_parser, Mapping) else "",
        },
        "vision_gate_status": vision_data.get("status", ""),
        "evidence_package_status": package_data.get("status", ""),
        "ready_for_launch": bool(package_data.get("ready_for_launch")),
        "required_evidence_count": len(required_evidence),
        "external_validation_scope_count": len(scopes),
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "warnings": warnings,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the local-only production profile for personal on-machine use.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--health-json", default="")
    parser.add_argument("--vision-gate-json", default="")
    parser.add_argument("--evidence-package-json", default="")
    parser.add_argument("--metrics-json", default="")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    try:
        health = _load_json_object(args.health_json) if args.health_json else _fetch_json(args.base_url, "/api/health", timeout=args.timeout)
        vision_gate = _load_json_object(args.vision_gate_json) if args.vision_gate_json else _fetch_json(args.base_url, "/api/readiness/vision-gate", timeout=args.timeout)
        evidence_package = (
            _load_json_object(args.evidence_package_json)
            if args.evidence_package_json
            else _fetch_json(args.base_url, "/api/readiness/evidence-package?include_passed=true", timeout=args.timeout)
        )
        metrics = _load_json_object(args.metrics_json) if args.metrics_json else _fetch_json(args.base_url, "/api/metrics", timeout=args.timeout)
        result = build_local_production_audit(
            health=health,
            vision_gate=vision_gate,
            evidence_package=evidence_package,
            metrics=metrics,
        )
    except Exception as exc:
        result = _failure_result(check="local_production_audit_input", error=exc)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
