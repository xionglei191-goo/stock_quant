from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.staging_acceptance import DEFAULT_BASE_URL, StagingClient


def _post_json(url: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        status = int(response.status)
    return {
        "status_code": status,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "body": body[:500],
    }


def _endpoint(base_logs_endpoint: str, signal: str) -> str:
    parsed = urlparse(base_logs_endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("otel endpoint must be an HTTP(S) OTLP logs endpoint")
    path = parsed.path.rstrip("/")
    if path.endswith("/v1/logs"):
        path = path[: -len("/v1/logs")]
    return f"{parsed.scheme}://{parsed.netloc}{path}/v1/{signal}"


def _trace_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _span_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _common_resource(service_name: str, environment: str) -> dict[str, Any]:
    return {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": service_name}},
            {"key": "service.namespace", "value": {"stringValue": "ai-native-quant-org"}},
            {"key": "deployment.environment", "value": {"stringValue": environment}},
        ]
    }


def _metrics_payload(service_name: str, environment: str, timestamp_nano: str, audit_events: int, open_alerts: int) -> dict[str, Any]:
    return {
        "resourceMetrics": [
            {
                "resource": _common_resource(service_name, environment),
                "scopeMetrics": [
                    {
                        "scope": {"name": "ai_quant.staging_otel_acceptance", "version": "1.0"},
                        "metrics": [
                            {
                                "name": "ai_quant.audit_events",
                                "description": "Audit event count observed during staging OTEL acceptance.",
                                "unit": "1",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": timestamp_nano,
                                            "asInt": str(audit_events),
                                            "attributes": [{"key": "acceptance.signal", "value": {"stringValue": "metrics"}}],
                                        }
                                    ]
                                },
                            },
                            {
                                "name": "ai_quant.open_alerts",
                                "description": "Open alert count observed during staging OTEL acceptance.",
                                "unit": "1",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": timestamp_nano,
                                            "asInt": str(open_alerts),
                                            "attributes": [{"key": "acceptance.signal", "value": {"stringValue": "alert_linkage"}}],
                                        }
                                    ]
                                },
                            },
                        ],
                    }
                ],
            }
        ]
    }


def _traces_payload(service_name: str, environment: str, timestamp_nano: str, trace_id: str) -> dict[str, Any]:
    start = int(timestamp_nano)
    return {
        "resourceSpans": [
            {
                "resource": _common_resource(service_name, environment),
                "scopeSpans": [
                    {
                        "scope": {"name": "ai_quant.staging_otel_acceptance", "version": "1.0"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": _span_id(trace_id),
                                "name": "staging_otel_acceptance",
                                "kind": 2,
                                "startTimeUnixNano": str(start),
                                "endTimeUnixNano": str(start + 5_000_000),
                                "attributes": [
                                    {"key": "acceptance.signal", "value": {"stringValue": "traces"}},
                                    {"key": "ai_quant.live_execution_allowed", "value": {"boolValue": False}},
                                ],
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _record_readiness(client: StagingClient, artifact_prefix: str, result: dict[str, Any]) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/readiness/checklist/otel_collector_drill",
        {
            "status": result["status"],
            "owner": "platform_otel_acceptance",
            "evidence_uri": f"{artifact_prefix.rstrip('/')}/otel-collector-drill.json",
            "notes": "Submitted OTLP logs, metrics, and traces to the staging OpenTelemetry collector and exercised alert notification linkage.",
            "metrics": result,
        },
        role="platform",
        actor="otel_acceptance",
    )


def run_staging_otel_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    otel_endpoint: str = "http://127.0.0.1:4318/v1/logs",
    artifact_prefix: str = "artifact://staging-local",
    record_readiness: bool = False,
    timeout: float = 10.0,
) -> dict[str, Any]:
    client = StagingClient(base_url, timeout=timeout)
    suffix = str(int(time.time() * 1000))
    trace_id = _trace_id(f"{base_url}:{suffix}")
    timestamp_nano = str(int(time.time() * 1_000_000_000))
    service_name = "ai-quant-staging"
    environment = "local-staging"

    client.request("POST", "/api/demo/full-flow", {}, role="platform", actor="otel_acceptance")
    client.request(
        "POST",
        "/api/orchestration/dags",
        {
            "dag_id": f"dag_otel_acceptance_{suffix}",
            "name": "OTEL acceptance failed workflow drill",
            "tasks": [{"task_id": "submit_otel", "owner": "平台负责人", "sla_minutes": 1}],
        },
        role="platform",
        actor="otel_acceptance",
    )
    client.request(
        "POST",
        f"/api/orchestration/dags/dag_otel_acceptance_{suffix}/run",
        {"run_id": f"wfrun_otel_acceptance_{suffix}", "status": "failed", "error": "otel acceptance failure drill"},
        role="platform",
        actor="otel_acceptance",
    )
    client.request("POST", "/api/alerts/rules/seed", {}, role="risk_compliance", actor="otel_acceptance")
    alerts = client.request("POST", "/api/alerts/evaluate", {"seed_defaults": True}, role="risk_compliance", actor="otel_acceptance")
    workflow_alerts = [item for item in alerts.get("alerts", []) if str(item.get("rule_id")) == "alert_workflow_failed_runs"]
    notification = client.request(
        "POST",
        "/api/alerts/notify",
        {
            "alert_ids": [item["alert_id"] for item in workflow_alerts],
            "channel": "otel_alert_outbox",
            "target": "platform-otel-oncall",
            "mark_sent": False,
        },
        role="risk_compliance",
        actor="otel_acceptance",
    )
    delivered = client.request(
        "POST",
        "/api/alerts/notifications/deliver",
        {"channel": "otel_alert_outbox", "execute": True, "provider": "dry-run-otel"},
        role="risk_compliance",
        actor="otel_acceptance",
    )
    otel_logs = client.request(
        "POST",
        "/api/observability/otel/export",
        {"sources": ["audit", "alerts", "workflow", "notifications"], "service_name": service_name, "environment": environment, "record_export": True, "limit": 100},
        role="platform",
        actor="otel_acceptance",
    )
    metrics = client.request("GET", "/api/metrics", role="unknown", actor="otel_acceptance")
    submissions = {
        "logs": _post_json(_endpoint(otel_endpoint, "logs"), otel_logs, timeout=timeout),
        "metrics": _post_json(
            _endpoint(otel_endpoint, "metrics"),
            _metrics_payload(service_name, environment, timestamp_nano, int(metrics.get("audit_events", 0)), int(metrics.get("counts", {}).get("open_alerts", 0))),
            timeout=timeout,
        ),
        "traces": _post_json(_endpoint(otel_endpoint, "traces"), _traces_payload(service_name, environment, timestamp_nano, trace_id), timeout=timeout),
    }
    passed = (
        int(otel_logs.get("log_count", 0)) > 0
        and all(200 <= item["status_code"] < 300 for item in submissions.values())
        and bool(workflow_alerts)
        and int(notification.get("count", 0)) >= 1
        and int(delivered.get("delivered_count", 0)) >= 1
    )
    result: dict[str, Any] = {
        "status": "passed" if passed else "failed",
        "base_url": base_url,
        "otel_endpoint": otel_endpoint,
        "signals": ["logs", "metrics", "traces"],
        "submissions": submissions,
        "log_count": otel_logs.get("log_count", 0),
        "trace_id": trace_id,
        "workflow_alert_count": len(workflow_alerts),
        "notification_count": notification.get("count", 0),
        "delivered_count": delivered.get("delivered_count", 0),
        "production_boundary": "local_staging_otel_collector_acceptance_no_live_execution",
    }
    if record_readiness:
        result["readiness_record"] = _record_readiness(client, artifact_prefix, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpenTelemetry collector staging acceptance.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--otel-endpoint", default="http://127.0.0.1:4318/v1/logs")
    parser.add_argument("--artifact-prefix", default="artifact://staging-local")
    parser.add_argument("--record-readiness", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run_staging_otel_acceptance(
        base_url=args.base_url,
        otel_endpoint=args.otel_endpoint,
        artifact_prefix=args.artifact_prefix,
        record_readiness=args.record_readiness,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
