from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
import socket
import statistics
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils import env_float
from scripts.ui_browser_acceptance import run_ui_browser_acceptance
from scripts.ui_cross_browser_matrix_check import load_and_validate_cross_browser_matrix, validate_cross_browser_matrix
from scripts.readiness_evidence_package_check import validate_readiness_evidence_package


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class StagingClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.latencies: dict[str, list[float]] = defaultdict(list)

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, role: str = "system", actor: str = "staging_acceptance") -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Role": role,
                "X-Actor": actor,
            },
        )
        started = time.perf_counter()
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        finally:
            self.latencies[f"{method} {path.split('?')[0]}"].append((time.perf_counter() - started) * 1000)
        if not payload.get("success"):
            raise AssertionError(f"{method} {path} failed: {payload}")
        return payload["data"]

    def request_any(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        role: str = "system",
        actor: str = "staging_acceptance",
    ) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Role": role,
                "X-Actor": actor,
            },
        )
        started = time.perf_counter()
        status_code = 0
        payload: dict[str, Any] = {}
        try:
            with urlopen(req, timeout=self.timeout) as response:
                status_code = int(response.status)
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
        except HTTPError as exc:
            status_code = int(exc.code)
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        finally:
            self.latencies[f"{method} {path.split('?')[0]}"].append((time.perf_counter() - started) * 1000)
        return {"status_code": status_code, "payload": payload}

    def raw_get(self, path: str) -> tuple[int, str]:
        started = time.perf_counter()
        with urlopen(Request(f"{self.base_url}{path}", method="GET"), timeout=self.timeout) as response:
            data = response.read().decode("utf-8")
            status = int(response.status)
        self.latencies[f"GET {path}"].append((time.perf_counter() - started) * 1000)
        return status, data


def _check(name: str, passed: bool, evidence: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    return {"check": name, "passed": passed, "evidence": evidence or {}, "error": error}


def _run_step(checks: list[dict[str, Any]], name: str, fn) -> Any:
    try:
        evidence = fn()
        checks.append(_check(name, True, evidence if isinstance(evidence, dict) else {"result": evidence}))
        return evidence
    except Exception as exc:  # pragma: no cover - exercised by real staging failures
        checks.append(_check(name, False, {}, str(exc)))
        return None


def _configured_external_targets(env: dict[str, str]) -> list[dict[str, Any]]:
    definitions = [
        ("postgres", "AI_QUANT_POSTGRES_DSN", "PostgreSQL state store DSN configured"),
        ("postgres", "AI_QUANT_DATABASE_URL", "PostgreSQL-compatible database URL configured"),
        ("s3", "AI_QUANT_S3_BUCKET", "S3-compatible object bucket configured"),
        ("opensearch", "AI_QUANT_OPENSEARCH_URL", "OpenSearch endpoint configured"),
        ("otel", "AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT", "OpenTelemetry collector endpoint configured"),
        ("neo4j", "AI_QUANT_NEO4J_SYNC_TARGET", "Neo4j sync target configured"),
        ("neo4j", "AI_QUANT_NEO4J_HTTP_URL", "Neo4j HTTP endpoint configured"),
        ("qdrant", "AI_QUANT_QDRANT_SYNC_TARGET", "Qdrant sync target configured"),
        ("openlineage", "AI_QUANT_OPENLINEAGE_TARGET", "OpenLineage target configured"),
        ("mlflow", "AI_QUANT_MLFLOW_TRACKING_URI", "MLflow registry/tracking URI configured"),
        ("secret_manager", "AI_QUANT_SECRET_MANAGER_PROVIDER", "External secret manager provider configured"),
    ]
    rows: list[dict[str, Any]] = []
    for adapter, key, description in definitions:
        value = env.get(key, "")
        rows.append(
            {
                "adapter": adapter,
                "env": key,
                "configured": bool(value),
                "value_preview": _redact_config_value(value),
                "description": description,
            }
        )
    return rows


def _probe_external_services(env: dict[str, str], *, timeout: float = 3.0) -> list[dict[str, Any]]:
    probes = [
        ("postgres", env.get("AI_QUANT_POSTGRES_DSN") or env.get("AI_QUANT_DATABASE_URL", ""), "tcp"),
        ("s3", env.get("AI_QUANT_S3_ENDPOINT", ""), "http"),
        ("opensearch", env.get("AI_QUANT_OPENSEARCH_URL", ""), "http"),
        ("otel", env.get("AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT", ""), "http"),
        ("neo4j", env.get("AI_QUANT_NEO4J_HTTP_URL") or env.get("AI_QUANT_NEO4J_SYNC_TARGET", ""), "http"),
        ("qdrant", env.get("AI_QUANT_QDRANT_SYNC_TARGET", ""), "http"),
        ("openlineage", env.get("AI_QUANT_OPENLINEAGE_TARGET", ""), "http"),
        ("mlflow", env.get("AI_QUANT_MLFLOW_TRACKING_URI", ""), "http"),
    ]
    rows: list[dict[str, Any]] = []
    for adapter, target, mode in probes:
        if not target:
            rows.append({"adapter": adapter, "target": "", "configured": False, "reachable": False, "status": "not_configured"})
            continue
        if mode == "tcp":
            row = _probe_tcp_url(adapter, target, timeout=timeout)
        else:
            row = _probe_http_url(adapter, target, timeout=timeout)
        rows.append(row)
    return rows


def _probe_tcp_url(adapter: str, target: str, *, timeout: float) -> dict[str, Any]:
    parsed = urlparse(target)
    host = parsed.hostname or ""
    port = parsed.port or (5432 if parsed.scheme.startswith("postgres") else 0)
    if not host or not port:
        return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": False, "status": "invalid_target"}
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": True, "status": "tcp_reachable"}
    except OSError as exc:
        return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": False, "status": "unreachable", "error": str(exc)}


def _probe_http_url(adapter: str, target: str, *, timeout: float) -> dict[str, Any]:
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": False, "status": "not_http_probeable"}
    probe_url = target.rstrip("/")
    if adapter == "qdrant":
        probe_url = f"{probe_url}/readyz"
    elif adapter == "otel" and probe_url.endswith("/v1/logs"):
        probe_url = probe_url.rsplit("/", 2)[0] + "/"
    try:
        with urlopen(Request(probe_url, method="GET"), timeout=timeout) as response:
            return {
                "adapter": adapter,
                "target": _redact_config_value(target),
                "configured": True,
                "reachable": 200 <= int(response.status) < 500,
                "status": f"http_{int(response.status)}",
            }
    except HTTPError as exc:
        try:
            exc.close()
        except Exception:
            pass
        return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": int(exc.code) < 500, "status": f"http_{int(exc.code)}"}
    except (URLError, OSError) as exc:
        return {"adapter": adapter, "target": _redact_config_value(target), "configured": True, "reachable": False, "status": "unreachable", "error": str(exc)}


def _redact_config_value(value: str) -> str:
    if not value:
        return ""
    if "://" in value:
        scheme, rest = value.split("://", 1)
        if "@" in rest:
            rest = "***@" + rest.split("@", 1)[1]
        return f"{scheme}://{rest[:80]}"
    return value[:4] + "***" if len(value) > 4 else "***"


def _latency_result(latencies: dict[str, list[float]]) -> dict[str, Any]:
    flat = [(name, value) for name, values in latencies.items() for value in values]
    if not flat:
        return {"records": 0, "avg_ms": {}, "max_ms": {}}
    avg_ms = {name: round(statistics.mean(values), 3) for name, values in latencies.items() if values}
    max_ms = {name: round(max(values), 3) for name, values in latencies.items() if values}
    return {
        "records": len(flat),
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "p95_ms": round(sorted(value for _name, value in flat)[max(0, int(len(flat) * 0.95) - 1)], 3),
    }


def _load_cross_browser_matrix(path: str) -> dict[str, Any]:
    if not path:
        return {}
    return load_and_validate_cross_browser_matrix(path)


def _capacity_thresholds(
    latency: dict[str, Any],
    *,
    simulate_threshold_ms: float,
    batch_threshold_ms: float,
    setup_threshold_ms: float,
) -> dict[str, float]:
    thresholds = {
        "POST /api/execution-intents/intent_demo/simulate": simulate_threshold_ms,
        "POST /api/graph/neo4j/sync": batch_threshold_ms,
        "POST /api/search/qdrant/sync": batch_threshold_ms,
        "POST /api/observability/otel/submit": batch_threshold_ms,
        "POST /api/orchestration/openlineage/submit": batch_threshold_ms,
        "POST /api/model-versions/mlflow/register": batch_threshold_ms,
        "POST /api/demo/full-flow": setup_threshold_ms,
        "POST /api/orchestration/dags": setup_threshold_ms,
        "POST /api/model-versions": setup_threshold_ms,
        "POST /api/lineage/events": setup_threshold_ms,
    }
    for metric in dict(latency.get("max_ms", {})):
        if metric.startswith("POST /api/orchestration/dags/") and metric.endswith("/run"):
            thresholds[metric] = setup_threshold_ms
    return thresholds


def run_staging_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    artifact_prefix: str = "artifact://staging-acceptance",
    record_readiness: bool = False,
    notify_missing: bool = False,
    timeout: float = 10.0,
    capacity_default_threshold_ms: float = 1000.0,
    capacity_simulate_threshold_ms: float = 2000.0,
    capacity_batch_threshold_ms: float = 60000.0,
    capacity_setup_threshold_ms: float = 20000.0,
    cross_browser_matrix: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    client = StagingClient(base_url, timeout=timeout)
    checks: list[dict[str, Any]] = []

    health = _run_step(checks, "health", lambda: client.request("GET", "/api/health", role="unknown"))
    _run_step(
        checks,
        "ui_loads",
        lambda: {
            "status": client.raw_get("/ui")[0],
            "contains_app_name": "公司情报与市场综合分析平台" in client.raw_get("/ui")[1],
        },
    )
    demo = _run_step(checks, "demo_full_flow", lambda: client.request("POST", "/api/demo/full-flow", {}, role="platform", actor="platform_staging"))
    intent_id = str((demo or {}).get("intent_id", ""))
    suffix = str(int(time.time() * 1000))
    if intent_id:
        _run_step(
            checks,
            "simulated_trade_only",
            lambda: client.request(
                "POST",
                f"/api/execution-intents/{intent_id}/simulate",
                {
                    "execution_id": f"simexec_staging_{suffix}",
                    "transaction_id": f"ptxn_staging_{suffix}",
                    "quantity": 10,
                    "fill_price": 100.0,
                    "account_id": f"staging_paper_{suffix}",
                },
                role="pm",
                actor="pm_staging",
            ),
        )
    query = urlencode({"q": "services resilience", "issuer_id": "issuer_demo", "limit": 5})
    _run_step(checks, "keyword_search", lambda: {"result_count": len(client.request("GET", f"/api/search?{query}", role="ceo")["results"])})
    _run_step(checks, "semantic_search", lambda: client.request("POST", "/api/search/semantic", {"q": "resilient services demand", "issuer_id": "issuer_demo"}, role="ceo"))
    _run_step(checks, "graph_traceability", lambda: client.request("GET", "/api/graph/traceability-report?issuer_id=issuer_demo", role="ceo"))
    _run_step(checks, "metrics", lambda: client.request("GET", "/api/metrics", role="unknown"))
    ui_browser = _run_step(
        checks,
        "ui_browser_acceptance",
        lambda: run_ui_browser_acceptance(
            base_url,
            output_dir=Path("data/artifacts/staging-ui") / suffix,
            timeout=timeout,
        ),
    )

    external_targets = _configured_external_targets(env)
    external_probes = _probe_external_services(env, timeout=min(timeout, 3.0))
    configured_adapters = {row["adapter"] for row in external_targets if row["configured"]}
    reachable_adapters = {row["adapter"] for row in external_probes if row["reachable"]}
    checks.append(
        _check(
            "external_configuration",
            {"postgres", "s3", "opensearch"}.issubset(configured_adapters),
            {
                "configured_adapters": sorted(configured_adapters),
                "targets": external_targets,
                "minimum_required": ["postgres", "s3", "opensearch"],
            },
        )
    )
    checks.append(
        _check(
            "external_reachability",
            {"postgres", "s3", "opensearch"}.issubset(reachable_adapters),
            {
                "reachable_adapters": sorted(reachable_adapters),
                "probes": external_probes,
                "minimum_required": ["postgres", "s3", "opensearch"],
            },
        )
    )

    if env.get("AI_QUANT_NEO4J_SYNC_TARGET"):
        _run_step(
            checks,
            "neo4j_sync_outbox",
            lambda: client.request("POST", "/api/graph/neo4j/sync", {"issuer_id": "issuer_demo", "target": env["AI_QUANT_NEO4J_SYNC_TARGET"], "channel": "neo4j_graph_sync_outbox"}, role="platform"),
        )
    if env.get("AI_QUANT_QDRANT_SYNC_TARGET"):
        _run_step(
            checks,
            "qdrant_sync_outbox",
            lambda: client.request("POST", "/api/search/qdrant/sync", {"issuer_id": "issuer_demo", "target": env["AI_QUANT_QDRANT_SYNC_TARGET"], "channel": "qdrant_vector_sync_outbox"}, role="platform"),
        )
    if env.get("AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT"):
        _run_step(
            checks,
            "otel_submit_outbox",
            lambda: client.request("POST", "/api/observability/otel/submit", {"target": env["AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT"], "provider": "webhook"}, role="platform"),
        )
    if env.get("AI_QUANT_OPENLINEAGE_TARGET") or env.get("AI_QUANT_MLFLOW_TRACKING_URI"):
        _run_step(
            checks,
            "lineage_model_registry_outbox",
            lambda: _exercise_lineage_and_model_registry(client, env, suffix, artifact_prefix),
        )

    latency = _latency_result(client.latencies)
    smoke_passed = all(item["passed"] for item in checks if item["check"] not in {"external_configuration", "external_reachability"})
    readiness_records: list[dict[str, Any]] = []
    if record_readiness:
        smoke_record = client.request(
            "POST",
            "/api/readiness/checklist/real_data_smoke_test",
            {
                "status": "passed" if smoke_passed else "failed",
                "owner": "platform_staging",
                "evidence_uri": f"{artifact_prefix.rstrip('/')}/real-data-smoke.json",
                "notes": "HTTP staging smoke acceptance against deployed service; trading remains simulated.",
                "metrics": {"base_url": base_url, "checks": checks, "external_targets": external_targets, "external_probes": external_probes},
            },
            role="platform",
            actor="platform_staging",
        )
        readiness_records.append(smoke_record)
        if ui_browser and ui_browser.get("status") == "passed":
            ui_screenshot_record = client.request(
                "POST",
                "/api/readiness/checklist/production_ui_screenshot_acceptance",
                {
                    "status": "passed",
                    "owner": "platform_staging",
                    "evidence_uri": f"{artifact_prefix.rstrip('/')}/ui-browser-screenshots.json",
                    "notes": "Headless Chrome desktop/mobile screenshot acceptance against deployed UI.",
                    "metrics": ui_browser,
                },
                role="platform",
                actor="platform_staging",
            )
            readiness_records.append(ui_screenshot_record)
        if cross_browser_matrix:
            matrix = dict(cross_browser_matrix)
            if ui_browser:
                matrix.setdefault("ui_url", ui_browser.get("ui_url", ""))
                matrix.setdefault("screenshots", ui_browser.get("screenshots", []))
                matrix.setdefault("required_text", ui_browser.get("required_text", []))
                matrix.setdefault("missing_text", ui_browser.get("missing_text", []))
            validation = dict(matrix.get("validation") or validate_cross_browser_matrix(matrix))
            matrix_status = str(validation.get("status") or matrix.get("status", "passed")).strip().lower()
            browser_matrix_record = client.request(
                "POST",
                "/api/readiness/checklist/cross_browser_acceptance",
                {
                    "status": "passed" if matrix_status in {"", "pass", "passed", "ok", "success"} else "failed",
                    "owner": "platform_staging",
                    "evidence_uri": str(matrix.get("evidence_uri") or f"{artifact_prefix.rstrip('/')}/ui-browser-matrix.json"),
                    "notes": "Reviewed cross-browser matrix for supported browser families and desktop/mobile viewports.",
                    "metrics": {
                        **matrix,
                        "validation": validation,
                        "ui_url": matrix.get("ui_url", (ui_browser or {}).get("ui_url", "")),
                        "screenshots": matrix.get("screenshots", (ui_browser or {}).get("screenshots", [])),
                        "required_text": matrix.get("required_text", (ui_browser or {}).get("required_text", [])),
                        "missing_text": matrix.get("missing_text", (ui_browser or {}).get("missing_text", [])),
                        "failure_count": matrix.get("failure_count", validation.get("failure_count", 0)),
                    },
                },
                role="platform",
                actor="platform_staging",
            )
            readiness_records.append(browser_matrix_record)
            checks.append(_check("cross_browser_matrix_record", browser_matrix_record.get("status") == "passed", browser_matrix_record))
        capacity_record = client.request(
            "POST",
            "/api/readiness/capacity-baseline",
            {
                "result": latency,
                "thresholds": _capacity_thresholds(
                    latency,
                    simulate_threshold_ms=capacity_simulate_threshold_ms,
                    batch_threshold_ms=capacity_batch_threshold_ms,
                    setup_threshold_ms=capacity_setup_threshold_ms,
                ),
                "default_threshold_ms": capacity_default_threshold_ms,
                "evidence_uri": f"{artifact_prefix.rstrip('/')}/capacity-latency.json",
                "notes": "HTTP staging latency baseline from acceptance script.",
            },
            role="platform",
            actor="platform_staging",
        )
        readiness_records.append(capacity_record["check"])
        checks.append(_check("capacity_readiness_record", bool(capacity_record.get("passed")), capacity_record))

    evidence_package = _run_step(
        checks,
        "readiness_evidence_package",
        lambda: client.request("POST", "/api/readiness/evidence-package", {"record_export": True}, role="CEO", actor="ceo_staging"),
    )
    evidence_package_validation = (
        validate_readiness_evidence_package(evidence_package, production_artifacts=False)
        if isinstance(evidence_package, dict)
        else None
    )
    notifications = None
    if notify_missing:
        notifications = _run_step(
            checks,
            "readiness_missing_evidence_notifications",
            lambda: client.request("POST", "/api/readiness/evidence-package/notify", {}, role="risk_compliance", actor="risk_staging"),
        )

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "mode": "staging_acceptance",
        "base_url": base_url,
        "trading_mode": "simulated_only",
        "production_boundary": "does_not_enable_live_broker_or_automatic_order_execution",
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
        "latency": latency,
        "external_probes": external_probes,
        "readiness_records": readiness_records,
        "evidence_package": evidence_package,
        "evidence_package_validation": evidence_package_validation,
        "notifications": notifications,
        "health": health,
    }


def _exercise_lineage_and_model_registry(client: StagingClient, env: dict[str, str], suffix: str, artifact_prefix: str) -> dict[str, Any]:
    dag_id = f"dag_staging_readiness_{suffix}"
    run_id = f"wfrun_staging_readiness_{suffix}"
    model_version_id = f"modelv_staging_readiness_{suffix}"
    lineage_id = f"lin_staging_readiness_{suffix}"
    model_name = "staging-readiness-summary"
    client.request(
        "POST",
        "/api/orchestration/dags",
        {
            "dag_id": dag_id,
            "name": "Staging readiness lineage pipeline",
            "cadence": "manual",
            "idempotency_key_fields": ["acceptance_run_id"],
            "tasks": [
                {"task_id": "collect_readiness_evidence", "owner": "平台负责人", "sla_minutes": 10},
                {
                    "task_id": "export_lineage",
                    "owner": "平台负责人",
                    "sla_minutes": 10,
                    "depends_on": ["collect_readiness_evidence"],
                    "input_refs": ["dataset:readiness_checks"],
                    "output_refs": ["dataset:readiness_lineage"],
                },
            ],
        },
        role="platform",
        actor="platform_staging",
    )
    client.request(
        "POST",
        f"/api/orchestration/dags/{dag_id}/run",
        {
            "run_id": run_id,
            "inputs": {"acceptance_run_id": suffix, "environment": "local_staging"},
        },
        role="platform",
        actor="platform_staging",
    )
    client.request(
        "POST",
        "/api/model-versions",
        {
            "model_version_id": model_version_id,
            "model_name": model_name,
            "version": suffix,
            "model_type": "governance_adapter",
            "artifact_uri": f"{artifact_prefix.rstrip('/')}/models/{model_name}/{suffix}",
            "training_dataset_ids": ["readiness_checks"],
            "prompt_versions": ["staging_acceptance_v1"],
            "metrics": {"acceptance_smoke": 1.0, "mlflow_run_id": f"mlrun_staging_{suffix}"},
            "status": "approved",
        },
        role="nlp_ml",
        actor="ml_staging",
    )
    client.request(
        "POST",
        "/api/lineage/events",
        {
            "lineage_id": lineage_id,
            "job_run_id": run_id,
            "dataset": "readiness_lineage",
            "input_refs": ["dataset:readiness_checks"],
            "output_refs": ["dataset:readiness_evidence_package"],
            "code_version": "local-staging",
            "model_versions": [model_version_id],
            "prompt_versions": ["staging_acceptance_v1"],
        },
        role="platform",
        actor="platform_staging",
    )
    result: dict[str, Any] = {"dag_id": dag_id, "run_id": run_id, "model_version_id": model_version_id, "lineage_id": lineage_id}
    if env.get("AI_QUANT_OPENLINEAGE_TARGET"):
        result["openlineage"] = client.request(
            "POST",
            "/api/orchestration/openlineage/submit",
            {
                "dag_id": dag_id,
                "namespace": "ai_quant_local_staging",
                "channel": "openlineage_submission_outbox",
                "target": env["AI_QUANT_OPENLINEAGE_TARGET"],
            },
            role="platform",
            actor="platform_staging",
        )
    if env.get("AI_QUANT_MLFLOW_TRACKING_URI"):
        result["mlflow"] = client.request(
            "POST",
            "/api/model-versions/mlflow/register",
            {
                "model_name": model_name,
                "registered_model_prefix": "ai_quant",
                "channel": "mlflow_registry_outbox",
                "target": env["AI_QUANT_MLFLOW_TRACKING_URI"],
            },
            role="nlp_ml",
            actor="ml_staging",
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HTTP staging acceptance and optionally record readiness evidence.")
    parser.add_argument("base_url", nargs="?", default=os.environ.get("AI_QUANT_STAGING_URL", DEFAULT_BASE_URL))
    parser.add_argument("--artifact-prefix", default=os.environ.get("AI_QUANT_STAGING_ARTIFACT_PREFIX", "artifact://staging-acceptance"))
    parser.add_argument("--record-readiness", action="store_true")
    parser.add_argument("--notify-missing", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--cross-browser-matrix",
        default=os.environ.get("AI_QUANT_CROSS_BROWSER_MATRIX", ""),
        help="Optional JSON matrix from real cross-browser acceptance; only when provided is cross_browser_acceptance recorded.",
    )
    parser.add_argument(
        "--capacity-default-threshold-ms",
        type=float,
        default=env_float("AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS", 1000.0, minimum=1.0),
        help="Default max latency threshold for HTTP staging capacity readiness checks.",
    )
    parser.add_argument(
        "--capacity-simulate-threshold-ms",
        type=float,
        default=env_float("AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS", 2000.0, minimum=1.0),
        help="Max latency threshold for the simulated execution HTTP readiness check.",
    )
    parser.add_argument(
        "--capacity-batch-threshold-ms",
        type=float,
        default=env_float("AI_QUANT_STAGING_CAPACITY_BATCH_THRESHOLD_MS", 60000.0, minimum=1.0),
        help="Max latency threshold for explicitly listed external sync/export batch checks.",
    )
    parser.add_argument(
        "--capacity-setup-threshold-ms",
        type=float,
        default=env_float("AI_QUANT_STAGING_CAPACITY_SETUP_THRESHOLD_MS", 20000.0, minimum=1.0),
        help="Max latency threshold for acceptance fixture and lineage setup operations.",
    )
    args = parser.parse_args()
    result = run_staging_acceptance(
        base_url=args.base_url,
        artifact_prefix=args.artifact_prefix,
        record_readiness=args.record_readiness,
        notify_missing=args.notify_missing,
        timeout=args.timeout,
        capacity_default_threshold_ms=args.capacity_default_threshold_ms,
        capacity_simulate_threshold_ms=args.capacity_simulate_threshold_ms,
        capacity_batch_threshold_ms=args.capacity_batch_threshold_ms,
        capacity_setup_threshold_ms=args.capacity_setup_threshold_ms,
        cross_browser_matrix=_load_cross_browser_matrix(args.cross_browser_matrix),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
