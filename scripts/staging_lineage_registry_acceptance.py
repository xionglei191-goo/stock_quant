from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.staging_acceptance import DEFAULT_BASE_URL, StagingClient


def _check(name: str, passed: bool, evidence: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
    return {"check": name, "passed": passed, "evidence": evidence or {}, "error": error}


def _delivery_sent_to_sink(result: dict[str, Any], expected_service: str) -> bool:
    if int(result.get("delivered_count", 0)) < 1 or int(result.get("failed_count", 0)) != 0:
        return False
    for row in result.get("notifications", []):
        response = row.get("response", {})
        if not (200 <= int(response.get("status_code", 0)) < 300):
            continue
        try:
            body = json.loads(str(response.get("body", "{}")))
        except json.JSONDecodeError:
            continue
        if body.get("received") is True and str(body.get("service", "")) == expected_service:
            return True
    return False


def _delivery_failed(result: dict[str, Any]) -> bool:
    return int(result.get("failed_count", 0)) >= 1 and int(result.get("delivered_count", 0)) == 0


def _seed_lineage_and_model(client: StagingClient, suffix: str) -> dict[str, str]:
    dag_id = f"dag_lineage_sender_{suffix}"
    run_id = f"wfrun_lineage_sender_{suffix}"
    model_version_id = f"modelv_lineage_sender_{suffix}"
    lineage_id = f"lin_lineage_sender_{suffix}"
    model_name = "staging-lineage-sender"
    client.request(
        "POST",
        "/api/orchestration/dags",
        {
            "dag_id": dag_id,
            "name": "Staging lineage sender acceptance",
            "cadence": "manual",
            "idempotency_key_fields": ["acceptance_run_id"],
            "tasks": [
                {"task_id": "collect_evidence", "owner": "平台负责人", "sla_minutes": 5},
                {
                    "task_id": "register_model",
                    "owner": "NLP/ML 负责人",
                    "sla_minutes": 5,
                    "depends_on": ["collect_evidence"],
                    "input_refs": ["dataset:sender_acceptance"],
                    "output_refs": ["dataset:lineage_registry_payload"],
                },
            ],
        },
        role="platform",
        actor="lineage_sender_acceptance",
    )
    client.request(
        "POST",
        f"/api/orchestration/dags/{dag_id}/run",
        {
            "run_id": run_id,
            "inputs": {"acceptance_run_id": suffix, "environment": "local_staging"},
            "status": "succeeded",
            "task_statuses": {"collect_evidence": "succeeded", "register_model": "succeeded"},
        },
        role="platform",
        actor="lineage_sender_acceptance",
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
            "training_dataset_ids": ["sender_acceptance"],
            "prompt_versions": ["lineage_sender_acceptance_v1"],
            "metrics": {"acceptance_sender": 1.0, "mlflow_run_id": f"mlrun_sender_{suffix}"},
            "status": "approved",
        },
        role="nlp_ml",
        actor="lineage_sender_acceptance",
    )
    client.request(
        "POST",
        "/api/lineage/events",
        {
            "lineage_id": lineage_id,
            "job_run_id": run_id,
            "dataset": "lineage_registry_payload",
            "input_refs": ["dataset:sender_acceptance"],
            "output_refs": ["dataset:lineage_registry_payload"],
            "code_version": "local-staging",
            "model_versions": [model_version_id],
            "prompt_versions": ["lineage_sender_acceptance_v1"],
        },
        role="platform",
        actor="lineage_sender_acceptance",
    )
    return {
        "dag_id": dag_id,
        "run_id": run_id,
        "model_version_id": model_version_id,
        "model_name": model_name,
        "lineage_id": lineage_id,
    }


def _enqueue_openlineage(client: StagingClient, ids: dict[str, str], target: str, *, force: bool = False) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/orchestration/openlineage/submit",
        {
            "dag_id": ids["dag_id"],
            "run_id": ids["run_id"],
            "namespace": "ai_quant_local_staging",
            "channel": "openlineage_submission_outbox",
            "target": target,
            "force": force,
            "max_delivery_attempts": 2,
        },
        role="platform",
        actor="lineage_sender_acceptance",
    )


def _enqueue_mlflow(client: StagingClient, ids: dict[str, str], target: str, *, force: bool = False) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/model-versions/mlflow/register",
        {
            "model_version_id": ids["model_version_id"],
            "registered_model_prefix": "ai_quant",
            "channel": "mlflow_registry_outbox",
            "target": target,
            "force": force,
            "max_delivery_attempts": 2,
        },
        role="nlp_ml",
        actor="lineage_sender_acceptance",
    )


def _notification_id(enqueued: dict[str, Any]) -> str:
    notifications = enqueued.get("notifications", [])
    if not notifications:
        raise AssertionError(f"no notification enqueued: {enqueued}")
    return str(notifications[0]["notification_id"])


def _deliver(client: StagingClient, notification_id: str, *, timeout_ms: int = 1000) -> dict[str, Any]:
    return client.request(
        "POST",
        "/api/alerts/notifications/deliver",
        {"notification_ids": [notification_id], "execute": True, "provider": "webhook", "timeout_ms": timeout_ms},
        role="platform",
        actor="lineage_sender_acceptance",
    )


def _wait_for_sink_health(target: str, *, timeout: float) -> None:
    parsed = urlparse(target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid sink target: {target}")
    health_url = f"{parsed.scheme}://{parsed.netloc}/health"
    deadline = time.monotonic() + max(1.0, timeout)
    last_error: str = ""
    while time.monotonic() < deadline:
        try:
            with urlopen(Request(health_url, method="GET"), timeout=min(3.0, timeout)) as response:
                if 200 <= int(response.status) < 500:
                    return
        except (HTTPError, URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise TimeoutError(f"sink {target} not ready: {last_error}")


def run_staging_lineage_registry_acceptance(
    *,
    base_url: str = DEFAULT_BASE_URL,
    openlineage_target: str = "http://openlineage:5000/openlineage",
    mlflow_target: str = "http://mlflow:5000/mlflow",
    openlineage_health_url: str = "",
    mlflow_health_url: str = "",
    artifact_prefix: str = "artifact://local-staging",
    timeout: float = 10.0,
) -> dict[str, Any]:
    client = StagingClient(base_url, timeout=timeout)
    suffix = str(int(time.time() * 1000))
    _wait_for_sink_health(openlineage_health_url or openlineage_target, timeout=timeout)
    _wait_for_sink_health(mlflow_health_url or mlflow_target, timeout=timeout)
    ids = _seed_lineage_and_model(client, suffix)
    bad_target = "http://127.0.0.1:1/lineage-registry-acceptance-unreachable"
    checks: list[dict[str, Any]] = [_check("lineage_model_seed", True, ids)]

    failed_openlineage = _deliver(client, _notification_id(_enqueue_openlineage(client, ids, bad_target)), timeout_ms=500)
    checks.append(_check("openlineage_failed_delivery_recorded", _delivery_failed(failed_openlineage), failed_openlineage))
    openlineage_delivery = _deliver(client, _notification_id(_enqueue_openlineage(client, ids, openlineage_target, force=True)))
    checks.append(_check("openlineage_webhook_sender", _delivery_sent_to_sink(openlineage_delivery, "openlineage"), openlineage_delivery))

    failed_mlflow = _deliver(client, _notification_id(_enqueue_mlflow(client, ids, bad_target)), timeout_ms=500)
    checks.append(_check("mlflow_failed_delivery_recorded", _delivery_failed(failed_mlflow), failed_mlflow))
    mlflow_delivery = _deliver(client, _notification_id(_enqueue_mlflow(client, ids, mlflow_target, force=True)))
    checks.append(_check("mlflow_webhook_sender", _delivery_sent_to_sink(mlflow_delivery, "mlflow"), mlflow_delivery))

    failed = [item for item in checks if not item["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "mode": "staging_lineage_registry_acceptance",
        "base_url": base_url,
        "artifact_prefix": artifact_prefix,
        "targets": {"openlineage": openlineage_target, "mlflow": mlflow_target},
        "health_urls": {"openlineage": openlineage_health_url or openlineage_target, "mlflow": mlflow_health_url or mlflow_target},
        "ids": ids,
        "checks": checks,
        "failed_count": len(failed),
        "production_boundary": "local_http_webhook_sender_acceptance_not_protocol_specific_openlineage_or_mlflow_client",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpenLineage/MLflow webhook sender staging acceptance.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--openlineage-target", default="http://openlineage:5000/openlineage")
    parser.add_argument("--mlflow-target", default="http://mlflow:5000/mlflow")
    parser.add_argument("--openlineage-health-url", default="")
    parser.add_argument("--mlflow-health-url", default="")
    parser.add_argument("--artifact-prefix", default="artifact://local-staging")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    result = run_staging_lineage_registry_acceptance(
        base_url=args.base_url,
        openlineage_target=args.openlineage_target,
        mlflow_target=args.mlflow_target,
        openlineage_health_url=args.openlineage_health_url,
        mlflow_health_url=args.mlflow_health_url,
        artifact_prefix=args.artifact_prefix,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
