"""Pure workflow scheduling / DAG planning helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(domain boundary #6: workflow orchestration). These are deterministic
functions of their arguments only: they do not touch the store, audit log,
permissions, or any ``SystemService`` state. ``SystemService`` keeps the same
method names as thin facades that delegate here.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Mapping

from ..utils import parse_datetime, to_plain

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids runtime import cost
    from ..models import WorkflowDefinition


def supported_task_types() -> list[str]:
    return [
        "benchmark_run",
        "benchmark_sample_register",
        "document_parse",
        "extract_evidence",
        "extract_structured_facts",
        "ingest_document",
        "market_data_backfill",
        "noop",
        "paddleocr",
        "search_rebuild",
        "structured_extraction",
    ]


def default_queue_for_task_type(task_type: str) -> str:
    task_type = str(task_type).strip().lower()
    if task_type in {"ingest_document"}:
        return "ingestion"
    if task_type in {
        "document_parse",
        "paddleocr",
        "extract_evidence",
        "extract_structured_facts",
        "structured_extraction",
    }:
        return "document_ai"
    if task_type == "search_rebuild":
        return "search"
    if task_type == "market_data_backfill":
        return "market_data"
    if task_type in {"benchmark_sample_register", "register_benchmark_sample", "benchmark_run"}:
        return "evaluation"
    return "default"


def task_dependencies(task: Mapping[str, Any]) -> list[str]:
    raw = task.get("depends_on", task.get("dependencies", task.get("upstream", [])))
    if isinstance(raw, str):
        items: list[Any] = re.split(r"[,\s]+", raw)
    elif isinstance(raw, list):
        items = raw
    elif isinstance(raw, tuple) or isinstance(raw, set):
        items = list(raw)
    else:
        items = []
    dependencies: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in dependencies:
            dependencies.append(value)
    return dependencies


def task_sla_minutes(task: Mapping[str, Any]) -> int:
    try:
        return int(task.get("sla_minutes", 0) or 0)
    except (TypeError, ValueError):
        return 0


def topological_order(
    task_ids: list[str], dependency_map: Mapping[str, list[str]]
) -> tuple[list[str], bool]:
    task_id_set = set(task_ids)
    remaining = set(task_ids)
    order: list[str] = []
    while remaining:
        ready = sorted(
            task_id
            for task_id in remaining
            if all(
                dependency not in task_id_set or dependency in order
                for dependency in dependency_map.get(task_id, [])
            )
        )
        if not ready:
            order.extend(sorted(remaining))
            return order, True
        for task_id in ready:
            remaining.remove(task_id)
            order.append(task_id)
    return order, False


def cron_schedule(cadence: str) -> str:
    cadence = str(cadence).strip().lower()
    if cadence == "hourly":
        return "0 * * * *"
    if cadence == "daily":
        return "0 9 * * *"
    if cadence == "business_daily":
        return "0 9 * * 1-5"
    if cadence == "weekly":
        return "0 9 * * 1"
    if cadence == "monthly":
        return "0 9 1 * *"
    return ""


def workflow_sla_minutes(workflow: "WorkflowDefinition | None", *, default_sla_minutes: int) -> int:
    if workflow is None:
        return max(1, default_sla_minutes)
    task_slas = []
    for task in workflow.tasks:
        try:
            minutes = int(task.get("sla_minutes", 0))
        except (TypeError, ValueError):
            minutes = 0
        if minutes > 0:
            task_slas.append(minutes)
    return max(1, min(task_slas) if task_slas else default_sla_minutes)


def run_owner(workflow: "WorkflowDefinition | None", failed_tasks: list[str]) -> str:
    if workflow is None:
        return "平台负责人"
    task_owners = {
        str(task.get("task_id")): str(task.get("owner", workflow.owner_role))
        for task in workflow.tasks
    }
    for task_id in failed_tasks:
        owner = task_owners.get(task_id)
        if owner:
            return owner
    return workflow.owner_role


def idempotency_key(workflow: "WorkflowDefinition", inputs: Mapping[str, Any]) -> str:
    if workflow.idempotency_key_fields:
        material: Any = {field: inputs.get(field) for field in workflow.idempotency_key_fields}
    else:
        material = inputs
    raw = json.dumps(to_plain(material), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(f"{workflow.dag_id}:{raw}".encode("utf-8")).hexdigest()[:24]


def backfill_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_datetime(str(value)).date()


def advance_schedule_date(value: date, cadence: str) -> date:
    if cadence == "hourly":
        return value + timedelta(days=1)
    if cadence in {"daily", "business_daily"}:
        return value + timedelta(days=1)
    if cadence == "weekly":
        return value + timedelta(days=7)
    if cadence == "monthly":
        month = value.month + 1
        year = value.year
        if month > 12:
            month = 1
            year += 1
        return value.replace(year=year, month=month, day=min(value.day, 28))
    if cadence == "manual":
        return value + timedelta(days=1)
    return value + timedelta(days=1)


def advance_schedule(value: Any, cadence: str) -> Any:
    if cadence == "hourly":
        return value + timedelta(hours=1)
    if cadence in {"daily", "business_daily"}:
        return value + timedelta(days=1)
    if cadence == "weekly":
        return value + timedelta(days=7)
    if cadence == "monthly":
        month = value.month + 1
        year = value.year
        if month > 12:
            month = 1
            year += 1
        return value.replace(year=year, month=month, day=min(value.day, 28))
    return value + timedelta(days=1)


def scheduler_choice(
    *,
    workflow_count: int,
    queue_count: int,
    sensor_count: int,
    backfill_candidate_count: int,
) -> dict[str, Any]:
    if sensor_count or queue_count > 2 or backfill_candidate_count > 30:
        recommended = "airflow_or_dagster"
        reason = "external_sensors_worker_pools_or_large_backfills"
    elif workflow_count <= 3 and queue_count <= 1 and backfill_candidate_count == 0:
        recommended = "cron_plus_api"
        reason = "simple_cadence_without_external_dependencies"
    else:
        recommended = "airflow_or_dagster"
        reason = "multi_dag_governance_and_lineage_handoff"
    return {
        "recommended": recommended,
        "reason": reason,
        "cron_allowed_for_simple_dags": recommended == "cron_plus_api",
        "airflow_fit": "strong" if recommended == "airflow_or_dagster" else "optional",
        "dagster_fit": "strong" if recommended == "airflow_or_dagster" else "optional",
    }


def dependency_snapshots(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("dependency_snapshots", payload.get("previous_task_results", {}))
    snapshots: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, Mapping):
        return snapshots
    for task_id, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        snapshots[str(task_id)] = {
            "task_id": str(value.get("task_id", task_id)),
            "task_type": str(value.get("task_type", "")),
            "status": str(value.get("status", "snapshot")),
            "output_refs": [str(item) for item in value.get("output_refs", [])],
            "output_ids": [str(item) for item in value.get("output_ids", [])],
            "result": to_plain(value.get("result", {})),
            "error": str(value.get("error", "")),
        }
    return snapshots
