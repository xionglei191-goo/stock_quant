"""Store-backed, read-only workflow reporting.

The reporting service receives the narrow store dependency directly. Public API,
audit, mutation, and cross-domain orchestration remain in ``SystemService``.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Mapping

from ..errors import ValidationError
from ..models import WorkflowDefinition, WorkflowRun
from ..utils import parse_datetime, to_plain, utcnow
from . import safe_identifier
from . import normalizers, workflow_planning


class WorkflowReporting:
    def __init__(self, store: Any) -> None:
        self.store = store

    @staticmethod
    def _bounded_limit(value: Any, max_value: int = 100) -> int:
        return max(1, min(max_value, int(value)))

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def workflow_runs_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        dag_id = str(filters.get("dag_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        runs = list(self.store.workflow_runs.values())
        if dag_id:
            runs = [item for item in runs if item.dag_id == dag_id]
        if status:
            runs = [item for item in runs if item.status == status]
        runs = sorted(runs, key=lambda item: parse_datetime(item.started_at), reverse=True)[:limit]
        return {"runs": [to_plain(item) for item in runs], "total": len(runs)}

    def workflow_sla_report(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        dag_id = str(filters.get("dag_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        as_of = parse_datetime(filters.get("as_of")) if filters.get("as_of") else utcnow()
        default_sla_minutes = int(filters.get("default_sla_minutes", 60))
        include_all = self._truthy(filters.get("include_all", False))
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        runs = list(self.store.workflow_runs.values())
        if dag_id:
            runs = [item for item in runs if item.dag_id == dag_id]
        if status:
            runs = [item for item in runs if item.status == status]
        runs.sort(key=lambda item: parse_datetime(item.started_at), reverse=True)

        rows: list[dict[str, Any]] = []
        breach_count = 0
        incident_needed_count = 0
        for run in runs:
            workflow = self.store.workflow_definitions.get(run.dag_id)
            sla_minutes = workflow_planning.workflow_sla_minutes(workflow, default_sla_minutes=default_sla_minutes)
            started_at = parse_datetime(run.started_at)
            elapsed_minutes = max(0.0, (as_of - started_at).total_seconds() / 60.0)
            failed_tasks = sorted(task_id for task_id, task_status in run.task_statuses.items() if task_status in {"failed", "needs_review"})
            breach_type = ""
            if run.status == "failed":
                breach_type = "failed_run"
            elif run.status == "needs_review":
                breach_type = "needs_review"
            elif run.status in {"queued", "running"} and elapsed_minutes > sla_minutes:
                breach_type = "runtime_sla_breach"
            breached = bool(breach_type)
            incident_report_id = f"ir_workflow_{run.run_id}"
            incident_needed = breached and incident_report_id not in self.store.incident_reports
            breach_count += int(breached)
            incident_needed_count += int(incident_needed)
            if not include_all and not breached:
                continue
            rows.append(
                {
                    "run_id": run.run_id,
                    "dag_id": run.dag_id,
                    "workflow_name": workflow.name if workflow else "",
                    "status": run.status,
                    "breached": breached,
                    "breach_type": breach_type or "none",
                    "sla_minutes": sla_minutes,
                    "elapsed_minutes": round(elapsed_minutes, 2),
                    "failed_tasks": failed_tasks,
                    "owner": workflow_planning.run_owner(workflow, failed_tasks),
                    "error": run.error,
                    "started_at": to_plain(run.started_at),
                    "completed_at": to_plain(run.completed_at),
                    "incident_report_id": incident_report_id if incident_report_id in self.store.incident_reports else "",
                    "incident_needed": incident_needed,
                    "retry_available": run.status in {"failed", "needs_review"},
                }
            )
            if len(rows) >= limit:
                break
        return {
            "as_of": as_of.isoformat(),
            "default_sla_minutes": default_sla_minutes,
            "count": len(rows),
            "breach_count": breach_count,
            "incident_needed_count": incident_needed_count,
            "runs": rows,
        }

    def workflow_schedule_calendar(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        dag_id = str(filters.get("dag_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        as_of = parse_datetime(filters.get("as_of")) if filters.get("as_of") else utcnow()
        horizon_days = int(filters.get("horizon_days", 14))
        per_workflow_limit = self._bounded_limit(filters.get("per_workflow_limit", 5), max_value=30)
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        include_manual = self._truthy(filters.get("include_manual", False))
        include_paused = self._truthy(filters.get("include_paused", False))
        workflows = list(self.store.workflow_definitions.values())
        if dag_id:
            workflows = [item for item in workflows if item.dag_id == dag_id]
        if status:
            workflows = [item for item in workflows if item.status == status]
        if not include_paused:
            workflows = [item for item in workflows if item.status == "active"]
        rows: list[dict[str, Any]] = []
        manual_count = 0
        for workflow in sorted(workflows, key=lambda item: (item.cadence, item.dag_id)):
            last_run = self.last_run(workflow.dag_id)
            upcoming = self.upcoming_runs(workflow, as_of=as_of, horizon_days=horizon_days, limit=per_workflow_limit)
            if not upcoming and workflow.cadence == "manual":
                manual_count += 1
                if not include_manual:
                    continue
            rows.append(
                {
                    "dag_id": workflow.dag_id,
                    "name": workflow.name,
                    "cadence": workflow.cadence,
                    "status": workflow.status,
                    "owner_role": workflow.owner_role,
                    "task_count": len(workflow.tasks),
                    "last_run_id": last_run.run_id if last_run else "",
                    "last_run_status": last_run.status if last_run else "",
                    "last_run_at": parse_datetime(last_run.started_at).isoformat() if last_run else "",
                    "next_run_at": upcoming[0].isoformat() if upcoming else "",
                    "upcoming_runs": [item.isoformat() for item in upcoming],
                    "requires_external_scheduler": workflow.cadence not in {"manual", "hourly", "daily", "business_daily", "weekly", "monthly"},
                }
            )
            if len(rows) >= limit:
                break
        return {
            "as_of": as_of.isoformat(),
            "horizon_days": horizon_days,
            "count": len(rows),
            "scheduled_count": sum(1 for row in rows if row["upcoming_runs"]),
            "manual_count": manual_count,
            "workflows": rows,
            "adapter_recommendation": {
                "current_phase": "lightweight_scheduler",
                "production_choice": "keep built-in cadence preview until concurrency, retries, or external dependencies require Airflow/Dagster",
                "airflow_dagster_trigger": "multiple cross-system DAGs, schedule backfills, task-level retries, or queue isolation requirements",
            },
        }

    def workflow_dependency_graph(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        dag_id = str(filters.get("dag_id", "")).strip()
        status = str(filters.get("status", "")).strip()
        include_paused = self._truthy(filters.get("include_paused", False))
        include_runs = self._truthy(filters.get("include_runs", True))
        include_lineage = self._truthy(filters.get("include_lineage", True))
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        workflows = list(self.store.workflow_definitions.values())
        if dag_id:
            workflows = [item for item in workflows if item.dag_id == dag_id]
        if status:
            workflows = [item for item in workflows if item.status == status]
        if not include_paused:
            workflows = [item for item in workflows if item.status == "active"]
        workflows = sorted(workflows, key=lambda item: item.dag_id)[:limit]

        graphs = [self.dependency_graph_row(item, include_runs=include_runs, include_lineage=include_lineage) for item in workflows]
        run_status_counts: dict[str, int] = {}
        for graph in graphs:
            latest_status = graph["latest_run_status"]
            if latest_status:
                run_status_counts[latest_status] = run_status_counts.get(latest_status, 0) + 1
        return {
            "count": len(graphs),
            "workflow_count": len(graphs),
            "task_count": sum(len(item["nodes"]) for item in graphs),
            "edge_count": sum(len(item["edges"]) for item in graphs),
            "unresolved_dependency_count": sum(len(item["unresolved_dependencies"]) for item in graphs),
            "cycle_count": sum(1 for item in graphs if item["has_cycle"]),
            "ready_task_count": sum(len(item["ready_task_ids"]) for item in graphs),
            "blocked_task_count": sum(len(item["blocked_task_ids"]) for item in graphs),
            "latest_run_status_counts": run_status_counts,
            "usage_boundary": "dependency_graph_is_visualization_and_triage_only_not_a_production_scheduler",
            "adapter_recommendation": {
                "current_phase": "lightweight_dependency_visualization",
                "production_choice": "keep built-in dependency graph until task-level retries, distributed workers, or external sensors require Airflow/Dagster",
                "openlineage_adapter_trigger": "cross-system lineage export, external data catalog sync, or regulated model governance evidence",
            },
            "graphs": graphs,
        }

    def workflow_definitions_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        status = str(filters.get("status", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        definitions = list(self.store.workflow_definitions.values())
        if status:
            definitions = [item for item in definitions if item.status == status]
        definitions = sorted(definitions, key=lambda item: item.updated_at, reverse=True)[:limit]
        return {"workflows": [to_plain(item) for item in definitions], "total": len(definitions)}

    def lineage_events_payload(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        job_run_id = str(filters.get("job_run_id", "")).strip()
        dataset = str(filters.get("dataset", "")).strip()
        limit = self._bounded_limit(filters.get("limit", 100), max_value=1000)
        events = list(self.store.lineage_events.values())
        if job_run_id:
            events = [item for item in events if item.job_run_id == job_run_id]
        if dataset:
            events = [item for item in events if item.dataset == dataset]
        events = sorted(events, key=lambda item: item.created_at, reverse=True)[:limit]
        return {"lineage_events": [to_plain(item) for item in events], "total": len(events)}

    def last_run(self, dag_id: str) -> WorkflowRun | None:
        runs = [item for item in self.store.workflow_runs.values() if item.dag_id == dag_id]
        if not runs:
            return None
        runs.sort(key=lambda item: parse_datetime(item.started_at), reverse=True)
        return runs[0]

    def dependency_graph_row(self, workflow: WorkflowDefinition, *, include_runs: bool, include_lineage: bool) -> dict[str, Any]:
        latest_run = self.last_run(workflow.dag_id) if include_runs else None
        task_ids = [str(task.get("task_id", "")).strip() for task in workflow.tasks if str(task.get("task_id", "")).strip()]
        task_id_set = set(task_ids)
        dependency_map: dict[str, list[str]] = {}
        dependents: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
        unresolved: list[dict[str, str]] = []
        edges: list[dict[str, Any]] = []
        nodes: list[dict[str, Any]] = []
        for task in workflow.tasks:
            task_id = str(task.get("task_id", "")).strip()
            if not task_id:
                continue
            dependencies = workflow_planning.task_dependencies(task)
            dependency_map[task_id] = dependencies
            for dependency in dependencies:
                edges.append({"from": dependency, "to": task_id, "status": "resolved" if dependency in task_id_set else "unresolved", "type": "task_dependency"})
                if dependency in task_id_set:
                    dependents.setdefault(dependency, []).append(task_id)
                else:
                    unresolved.append({"task_id": task_id, "missing_dependency": dependency})
        for task in workflow.tasks:
            task_id = str(task.get("task_id", "")).strip()
            if not task_id:
                continue
            task_status = latest_run.task_statuses.get(task_id, "") if latest_run else ""
            dependencies = dependency_map.get(task_id, [])
            unresolved_for_task = [item["missing_dependency"] for item in unresolved if item["task_id"] == task_id]
            nodes.append({
                "task_id": task_id, "label": str(task.get("name") or task.get("label") or task_id),
                "owner": str(task.get("owner", workflow.owner_role)), "task_type": str(task.get("task_type") or task.get("type") or "task"),
                "sla_minutes": workflow_planning.task_sla_minutes(task), "depends_on": dependencies,
                "dependents": sorted(set(dependents.get(task_id, []))), "unresolved_dependencies": unresolved_for_task,
                "latest_status": task_status,
                "ready": not dependencies or all(latest_run and latest_run.task_statuses.get(dep) == "succeeded" for dep in dependencies if dep in task_id_set),
                "blocked": bool(unresolved_for_task) or any(latest_run and latest_run.task_statuses.get(dep) in {"failed", "needs_review"} for dep in dependencies if dep in task_id_set),
                "inputs": [str(item) for item in task.get("input_refs", [])], "outputs": [str(item) for item in task.get("output_refs", [])],
            })
        topological_order, has_cycle = workflow_planning.topological_order(task_ids, dependency_map)
        return {
            "dag_id": workflow.dag_id, "name": workflow.name, "status": workflow.status, "cadence": workflow.cadence,
            "owner_role": workflow.owner_role, "latest_run_id": latest_run.run_id if latest_run else "",
            "latest_run_status": latest_run.status if latest_run else "",
            "latest_run_started_at": parse_datetime(latest_run.started_at).isoformat() if latest_run else "",
            "nodes": nodes, "edges": edges, "topological_order": topological_order, "has_cycle": has_cycle,
            "unresolved_dependencies": unresolved,
            "ready_task_ids": sorted(node["task_id"] for node in nodes if node["ready"] and not node["blocked"]),
            "blocked_task_ids": sorted(node["task_id"] for node in nodes if node["blocked"]),
            "lineage": self.lineage_summary(workflow.dag_id, latest_run.run_id if latest_run else "") if include_lineage else {},
        }

    def lineage_summary(self, dag_id: str, latest_run_id: str = "") -> dict[str, Any]:
        run_ids = {item.run_id for item in self.store.workflow_runs.values() if item.dag_id == dag_id}
        if latest_run_id:
            run_ids.add(latest_run_id)
        events = [item for item in self.store.lineage_events.values() if item.job_run_id in run_ids]
        latest_events = [item for item in events if item.job_run_id == latest_run_id] if latest_run_id else []
        datasets: dict[str, int] = {}
        model_versions: set[str] = set()
        prompt_versions: set[str] = set()
        for event in events:
            datasets[event.dataset] = datasets.get(event.dataset, 0) + 1
            model_versions.update(event.model_versions)
            prompt_versions.update(event.prompt_versions)
        return {"event_count": len(events), "latest_run_event_count": len(latest_events), "datasets": datasets,
                "model_versions": sorted(model_versions), "prompt_versions": sorted(prompt_versions),
                "input_ref_count": sum(len(item.input_refs) for item in events), "output_ref_count": sum(len(item.output_refs) for item in events)}

    def queue_plan(self, workflow: WorkflowDefinition) -> dict[str, dict[str, Any]]:
        queues: dict[str, dict[str, Any]] = {}
        for task in workflow.tasks:
            task_type = str(task.get("task_type") or task.get("type") or "noop").strip().lower()
            raw_queue = task.get("queue", task.get("execution_queue", task.get("worker_queue", "")))
            queue = str(raw_queue).strip() if raw_queue is not None else ""
            queue = safe_identifier(queue or workflow_planning.default_queue_for_task_type(task_type)).lower()
            raw_policy = task.get("retry_policy", {})
            policy = dict(raw_policy) if isinstance(raw_policy, Mapping) else {}
            try:
                max_attempts = int(task.get("max_attempts", policy.get("max_attempts", 1)) or 1)
            except (TypeError, ValueError):
                max_attempts = 1
            max_attempts = max(1, min(max_attempts, 10))
            row = queues.setdefault(queue, {"queue": queue, "worker_pool": f"wf_{queue}_pool", "task_count": 0,
                                                   "task_ids": [], "task_types": [], "max_attempts": 1,
                                                   "requires_external_worker_pool": queue != "default"})
            row["task_count"] += 1
            row["task_ids"].append(str(task.get("task_id", "")).strip())
            row["task_types"] = normalizers.unique_strings([*row["task_types"], task_type])
            row["max_attempts"] = max(row["max_attempts"], max_attempts)
        return queues

    def scheduler_backfill_preview(self, workflow: WorkflowDefinition, *, as_of: Any, window_days: int, include_plan: bool) -> dict[str, Any]:
        if workflow.cadence == "manual":
            return {"candidate_count": 0, "planned_dates": [], "requires_backfill": False, "reason": "manual_workflow"}
        last_logical_date = self.latest_logical_run_date(workflow)
        start_date = last_logical_date + timedelta(days=1) if last_logical_date else as_of.date()
        end_date = min(as_of.date(), start_date + timedelta(days=max(0, window_days - 1)))
        if start_date > end_date:
            return {"candidate_count": 0, "planned_dates": [], "requires_backfill": False, "reason": "no_gap_after_latest_run"}
        dates = self.backfill_dates({"start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
                                     "cadence": workflow.cadence, "max_runs": window_days}, workflow=workflow)
        return {"candidate_count": len(dates), "planned_dates": [item.isoformat() for item in dates] if include_plan else [],
                "requires_backfill": bool(dates), "reason": "latest_run_gap" if last_logical_date else "no_previous_run",
                "preview_endpoint": f"/api/orchestration/dags/{workflow.dag_id}/backfill"}

    def latest_logical_run_date(self, workflow: WorkflowDefinition) -> date | None:
        dates: list[date] = []
        date_fields = normalizers.unique_strings([*workflow.idempotency_key_fields, "as_of_date", "run_date", "date"])
        for run in self.store.workflow_runs.values():
            if run.dag_id != workflow.dag_id:
                continue
            backfill = run.inputs.get("backfill", {})
            if isinstance(backfill, Mapping) and backfill.get("run_date"):
                dates.append(workflow_planning.backfill_date(backfill["run_date"]))
                continue
            for field in date_fields:
                if run.inputs.get(field):
                    dates.append(workflow_planning.backfill_date(run.inputs[field]))
                    break
            else:
                dates.append(parse_datetime(run.started_at).date())
        return max(dates) if dates else None

    def upcoming_runs(self, workflow: WorkflowDefinition, *, as_of: Any, horizon_days: int, limit: int) -> list[Any]:
        cadence = workflow.cadence.strip().lower()
        if cadence == "manual":
            return []
        last_run = self.last_run(workflow.dag_id)
        candidate = parse_datetime(last_run.started_at) if last_run else as_of
        horizon_end = as_of + timedelta(days=max(0, horizon_days))
        upcoming: list[Any] = []
        guard = 0
        while candidate <= as_of and guard < 1000:
            candidate = workflow_planning.advance_schedule(candidate, cadence)
            guard += 1
        while candidate <= horizon_end and len(upcoming) < limit and guard < 2000:
            if cadence != "business_daily" or candidate.weekday() < 5:
                upcoming.append(candidate)
            candidate = workflow_planning.advance_schedule(candidate, cadence)
            guard += 1
        return upcoming

    def backfill_dates(self, payload: Mapping[str, Any], *, workflow: WorkflowDefinition) -> list[date]:
        raw_dates = payload.get("run_dates", payload.get("dates"))
        if isinstance(raw_dates, str):
            raw_values = [item for item in re.split(r"[,\s]+", raw_dates) if item]
        elif isinstance(raw_dates, (list, tuple, set)):
            raw_values = list(raw_dates)
        elif raw_dates is None:
            raw_values = []
        else:
            raw_values = [raw_dates]
        dates = [workflow_planning.backfill_date(value) for value in raw_values]
        if dates:
            return sorted(set(dates))
        start_value = payload.get("start_date", payload.get("from_date"))
        end_value = payload.get("end_date", payload.get("to_date", start_value))
        if not start_value:
            raise ValidationError("workflow backfill requires run_dates or start_date")
        start_date = workflow_planning.backfill_date(start_value)
        end_date = workflow_planning.backfill_date(end_value)
        if start_date > end_date:
            raise ValidationError("workflow backfill start_date must be on or before end_date")
        cadence = str(payload.get("cadence", workflow.cadence)).strip().lower() or workflow.cadence.strip().lower()
        max_runs = self._bounded_limit(payload.get("max_runs", 90), max_value=366)
        current = start_date
        guard = 0
        while current <= end_date and len(dates) < max_runs and guard < 1000:
            if cadence != "business_daily" or current.weekday() < 5:
                dates.append(current)
            current = workflow_planning.advance_schedule_date(current, cadence)
            guard += 1
        return sorted(set(dates))
