from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from urllib.parse import urlparse
import socket
import statistics
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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


def run_staging_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    artifact_prefix: str = "artifact://staging-acceptance",
    record_readiness: bool = False,
    notify_missing: bool = False,
    timeout: float = 10.0,
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
            "contains_app_name": "AI Native Quant Org" in client.raw_get("/ui")[1],
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
            lambda: _exercise_lineage_and_model_registry(client, env, suffix),
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
        capacity_record = client.request(
            "POST",
            "/api/readiness/capacity-baseline",
            {
                "result": latency,
                "thresholds": {},
                "default_threshold_ms": 1000,
                "evidence_uri": f"{artifact_prefix.rstrip('/')}/capacity-latency.json",
                "notes": "HTTP staging latency baseline from acceptance script.",
            },
            role="platform",
            actor="platform_staging",
        )
        readiness_records.append(capacity_record["check"])

    evidence_package = _run_step(
        checks,
        "readiness_evidence_package",
        lambda: client.request("POST", "/api/readiness/evidence-package", {"record_export": True}, role="CEO", actor="ceo_staging"),
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
        "notifications": notifications,
        "health": health,
    }


def _exercise_lineage_and_model_registry(client: StagingClient, env: dict[str, str], suffix: str) -> dict[str, Any]:
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
            "artifact_uri": f"artifact://local-staging/models/{model_name}/{suffix}",
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
    args = parser.parse_args()
    result = run_staging_acceptance(
        base_url=args.base_url,
        artifact_prefix=args.artifact_prefix,
        record_readiness=args.record_readiness,
        notify_missing=args.notify_missing,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
