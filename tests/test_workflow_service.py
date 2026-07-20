from __future__ import annotations

from app.service_modules.workflow_reporting import WorkflowReporting
from app.utils import parse_datetime
from tests.support import SystemServiceTestBase


class WorkflowServiceTests(SystemServiceTestBase):
    def test_workflow_reporting_store_module_matches_facade(self) -> None:
        active = self.service.register_workflow_definition(
            {
                "dag_id": "dag_reporting_active",
                "name": "Reporting active",
                "cadence": "business_daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect", "task_type": "ingest_document", "sla_minutes": 15},
                    {"task_id": "extract", "task_type": "extract_evidence", "depends_on": ["collect"], "max_attempts": 3},
                ],
            }
        )
        self.service.register_workflow_definition(
            {
                "dag_id": "dag_reporting_paused",
                "name": "Reporting paused",
                "cadence": "manual",
                "status": "paused",
                "tasks": [{"task_id": "noop", "task_type": "noop"}],
            }
        )
        run = self.service.run_workflow_definition(
            active.dag_id,
            {
                "run_id": "wfrun_reporting",
                "inputs": {"as_of_date": "2026-07-15"},
                "status": "failed",
                "task_statuses": {"collect": "succeeded", "extract": "failed"},
                "started_at": "2026-07-15T09:00:00+00:00",
            },
        )
        self.service.record_lineage_event(
            {"lineage_id": "lin_reporting", "job_run_id": run.run_id, "dataset": "evidence", "model_versions": ["model-v1"]}
        )
        reporting = WorkflowReporting(self.service.store)

        cases = [
            (self.service.workflow_runs_payload, reporting.workflow_runs_payload, {"dag_id": active.dag_id, "limit": 1}),
            (self.service.workflow_sla_report, reporting.workflow_sla_report, {"as_of": "2026-07-15T10:00:00+00:00", "include_all": True}),
            (self.service.workflow_schedule_calendar, reporting.workflow_schedule_calendar, {"as_of": "2026-07-17T09:00:00+00:00", "include_paused": True, "include_manual": True}),
            (self.service.workflow_dependency_graph, reporting.workflow_dependency_graph, {"include_paused": True, "include_lineage": True}),
            (self.service.workflow_definitions_payload, reporting.workflow_definitions_payload, {"status": "active", "limit": 1}),
            (self.service.lineage_events_payload, reporting.lineage_events_payload, {"job_run_id": run.run_id}),
        ]
        for facade_call, module_call, filters in cases:
            with self.subTest(report=facade_call.__name__):
                self.assertEqual(facade_call(filters), module_call(filters))

        self.assertEqual(self.service._workflow_queue_plan(active), reporting.queue_plan(active))
        self.assertEqual(
            self.service._workflow_scheduler_backfill_preview(
                active, as_of=parse_datetime("2026-07-17T09:00:00+00:00"), window_days=10, include_plan=True
            ),
            reporting.scheduler_backfill_preview(
                active, as_of=parse_datetime("2026-07-17T09:00:00+00:00"), window_days=10, include_plan=True
            ),
        )

    def test_workflow_lineage_and_model_version_records_are_idempotent(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_daily_research",
                "name": "Daily research pipeline",
                "cadence": "daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect_filings", "owner": "数据工程", "sla_minutes": 30},
                    {
                        "task_id": "extract_evidence",
                        "owner": "NLP/ML 负责人",
                        "sla_minutes": 15,
                        "depends_on": ["collect_filings"],
                        "input_refs": ["doc:doc_demo"],
                        "output_refs": ["dataset:evidence_chunks"],
                    },
                    {
                        "task_id": "index_evidence",
                        "owner": "平台负责人",
                        "sla_minutes": 20,
                        "depends_on": "extract_evidence missing_external_sensor",
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success)

        first_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_001",
                "inputs": {"as_of_date": "2026-05-15", "market": "A"},
                "started_at": "2026-05-15T09:00:00+00:00",
                "completed_at": "2026-05-15T09:05:00+00:00",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(first_run.success)
        self.assertEqual(first_run.data["status"], "succeeded")
        self.assertEqual(first_run.data["task_statuses"]["collect_filings"], "succeeded")

        second_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {"run_id": "wfrun_daily_duplicate", "inputs": {"as_of_date": "2026-05-15", "market": "U"}},
            actor="platform",
            role="platform",
        )
        self.assertTrue(second_run.success)
        self.assertEqual(second_run.data["run_id"], "wfrun_daily_001")

        schedule_calendar = self.router.dispatch(
            "GET",
            "/api/orchestration/schedule-calendar",
            {"as_of": "2026-05-15T12:00:00+00:00", "horizon_days": 3},
            role="platform",
        )
        self.assertTrue(schedule_calendar.success, schedule_calendar.error)
        daily_schedule = next(item for item in schedule_calendar.data["workflows"] if item["dag_id"] == "dag_daily_research")
        self.assertEqual(daily_schedule["next_run_at"], "2026-05-16T09:00:00+00:00")
        self.assertEqual(len(daily_schedule["upcoming_runs"]), 3)
        self.assertEqual(schedule_calendar.data["adapter_recommendation"]["current_phase"], "lightweight_scheduler")

        model_version = self.router.dispatch(
            "POST",
            "/api/model-versions",
            {
                "model_version_id": "modelv_summary_001",
                "model_name": "research-summary",
                "version": "2026-05-15",
                "model_type": "llm",
                "artifact_uri": "models:/research-summary/2026-05-15",
                "training_dataset_ids": ["evidence_chunks"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
                "metrics": {"coverage": 0.96, "mlflow_run_id": "mlrun_summary_001"},
                "status": "approved",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(model_version.success)

        lineage = self.router.dispatch(
            "POST",
            "/api/lineage/events",
            {
                "lineage_id": "lin_daily_001",
                "job_run_id": "wfrun_daily_001",
                "dataset": "evidence_chunks",
                "input_refs": ["doc:doc_demo"],
                "output_refs": ["evidence:evi_demo"],
                "code_version": "local-test",
                "model_versions": ["modelv_summary_001"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(lineage.success)
        self.assertEqual(lineage.data["dataset"], "evidence_chunks")
        self.assertEqual(self.service.store.audit_log[-1].action, "record_lineage_event")

        dependency_graph = self.router.dispatch(
            "POST",
            "/api/orchestration/dependency-graph",
            {"dag_id": "dag_daily_research"},
            role="platform",
        )
        self.assertTrue(dependency_graph.success, dependency_graph.error)
        self.assertEqual(dependency_graph.data["workflow_count"], 1)
        self.assertEqual(dependency_graph.data["task_count"], 3)
        self.assertEqual(dependency_graph.data["edge_count"], 3)
        self.assertEqual(dependency_graph.data["unresolved_dependency_count"], 1)
        self.assertIn("dependency_graph_is_visualization", dependency_graph.data["usage_boundary"])
        graph = dependency_graph.data["graphs"][0]
        self.assertEqual(graph["topological_order"][:3], ["collect_filings", "extract_evidence", "index_evidence"])
        self.assertEqual(graph["latest_run_id"], "wfrun_daily_001")
        self.assertEqual(graph["lineage"]["event_count"], 1)
        self.assertEqual(graph["lineage"]["datasets"]["evidence_chunks"], 1)
        self.assertEqual(graph["ready_task_ids"], ["collect_filings", "extract_evidence"])
        self.assertEqual(graph["blocked_task_ids"], ["index_evidence"])
        unresolved = graph["unresolved_dependencies"][0]
        self.assertEqual(unresolved["task_id"], "index_evidence")
        self.assertEqual(unresolved["missing_dependency"], "missing_external_sensor")
        node_by_id = {item["task_id"]: item for item in graph["nodes"]}
        self.assertEqual(node_by_id["extract_evidence"]["dependents"], ["index_evidence"])
        self.assertEqual(node_by_id["index_evidence"]["depends_on"], ["extract_evidence", "missing_external_sensor"])

        scheduler_handoff = self.router.dispatch(
            "POST",
            "/api/orchestration/scheduler-handoff",
            {"dag_id": "dag_daily_research", "as_of": "2026-05-18T12:00:00+00:00", "backfill_window_days": 5},
            actor="platform",
            role="platform",
        )
        self.assertTrue(scheduler_handoff.success, scheduler_handoff.error)
        self.assertEqual(scheduler_handoff.data["workflow_count"], 1)
        self.assertEqual(scheduler_handoff.data["recommended_orchestrator"]["recommended"], "airflow_or_dagster")
        self.assertEqual(scheduler_handoff.data["external_sensor_count"], 1)
        self.assertEqual(scheduler_handoff.data["external_sensors"][0]["sensor_id"], "missing_external_sensor")
        self.assertTrue(scheduler_handoff.data["external_deployment_required"])
        self.assertFalse(scheduler_handoff.data["automation_allowed"])
        self.assertIn("scheduler_handoff_is_a_planning_contract", scheduler_handoff.data["usage_boundary"])
        daily_handoff = scheduler_handoff.data["workflows"][0]
        self.assertEqual(daily_handoff["adapter_contract"]["airflow_dag_id"], "dag_daily_research")
        self.assertEqual(daily_handoff["adapter_contract"]["cron_schedule"], "0 9 * * *")
        self.assertGreaterEqual(daily_handoff["backfill"]["candidate_count"], 1)
        self.assertIn("large_window_backfill_run_artifact_uri", scheduler_handoff.data["missing_external_evidence"])

        openlineage_export = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/export",
            {"dag_id": "dag_daily_research", "namespace": "ai_quant_test", "record_export": True},
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage_export.success, openlineage_export.error)
        self.assertEqual(openlineage_export.data["adapter"]["format"], "openlineage_compatible")
        self.assertTrue(openlineage_export.data["adapter"]["external_submission_required"])
        self.assertEqual(openlineage_export.data["count"], 1)
        self.assertEqual(openlineage_export.data["lineage_event_count"], 1)
        openlineage_event = openlineage_export.data["events"][0]
        self.assertEqual(openlineage_event["eventType"], "COMPLETE")
        self.assertEqual(openlineage_event["job"]["namespace"], "ai_quant_test")
        self.assertEqual(openlineage_event["job"]["name"], "dag_daily_research")
        self.assertEqual(openlineage_event["run"]["runId"], "wfrun_daily_001")
        self.assertIn("doc:doc_demo", {item["name"] for item in openlineage_event["inputs"]})
        self.assertIn("evidence_chunks", {item["name"] for item in openlineage_event["outputs"]})
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_run"]["taskStatuses"]["collect_filings"], "succeeded")
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_lineage"]["modelVersions"], ["modelv_summary_001"])
        self.assertEqual(openlineage_event["run"]["facets"]["ai_quant_models"]["models"][0]["model_name"], "research-summary")
        self.assertEqual(self.service.store.audit_log[-1].action, "export_openlineage_payload")

        openlineage_submit = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {
                "dag_id": "dag_daily_research",
                "namespace": "ai_quant_test",
                "channel": "openlineage_submission_outbox",
                "target": "openlineage://local-catalog",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage_submit.success, openlineage_submit.error)
        self.assertEqual(openlineage_submit.data["count"], 1)
        self.assertIn("openlineage_submissions_are_outbox_records", openlineage_submit.data["usage_boundary"])
        openlineage_notification = openlineage_submit.data["notifications"][0]
        self.assertEqual(openlineage_notification["channel"], "openlineage_submission_outbox")
        self.assertEqual(openlineage_notification["status"], "pending")
        self.assertEqual(openlineage_notification["payload"]["type"], "openlineage_submission")
        self.assertEqual(openlineage_notification["payload"]["run_id"], "wfrun_daily_001")
        self.assertTrue(openlineage_notification["payload"]["content_sha256"])
        duplicate_openlineage_submit = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {"dag_id": "dag_daily_research", "namespace": "ai_quant_test"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate_openlineage_submit.success, duplicate_openlineage_submit.error)
        self.assertEqual(duplicate_openlineage_submit.data["count"], 0)
        self.assertEqual(duplicate_openlineage_submit.data["skipped_count"], 1)

        mlflow_export = self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/export",
            {"model_name": "research-summary", "registered_model_prefix": "ai_quant", "record_export": True},
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(mlflow_export.success, mlflow_export.error)
        self.assertEqual(mlflow_export.data["adapter"]["format"], "mlflow_model_registry_compatible")
        self.assertTrue(mlflow_export.data["adapter"]["external_registration_required"])
        self.assertEqual(mlflow_export.data["count"], 1)
        mlflow_model = mlflow_export.data["models"][0]
        self.assertEqual(mlflow_model["registered_model"], "ai_quant.research-summary")
        self.assertEqual(mlflow_model["source"], "models:/research-summary/2026-05-15")
        self.assertEqual(mlflow_model["run_id"], "mlrun_summary_001")
        self.assertEqual(mlflow_model["stage"], "Production")
        self.assertEqual(mlflow_model["metrics"]["coverage"], 0.96)
        self.assertEqual(mlflow_model["lineage"]["lineage_event_ids"], ["lin_daily_001"])
        self.assertEqual(mlflow_model["lineage"]["datasets"], ["evidence_chunks"])
        self.assertIn("production", mlflow_model["aliases"])
        self.assertIn("ai_quant_prompt_versions", mlflow_model["tags"])
        self.assertEqual(self.service.store.audit_log[-1].action, "export_mlflow_model_registry_payload")

        mlflow_submit = self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/register",
            {
                "model_name": "research-summary",
                "registered_model_prefix": "ai_quant",
                "channel": "mlflow_registry_outbox",
                "target": "mlflow://local-registry",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(mlflow_submit.success, mlflow_submit.error)
        self.assertEqual(mlflow_submit.data["count"], 1)
        self.assertIn("mlflow_registrations_are_outbox_records", mlflow_submit.data["usage_boundary"])
        mlflow_notification = mlflow_submit.data["notifications"][0]
        self.assertEqual(mlflow_notification["payload"]["type"], "mlflow_model_registration")
        self.assertEqual(mlflow_notification["payload"]["model_version_id"], "modelv_summary_001")
        self.assertEqual(mlflow_notification["payload"]["registered_model"], "ai_quant.research-summary")
        self.assertEqual(mlflow_notification["payload"]["stage"], "Production")
        self.assertTrue(mlflow_notification["payload"]["content_sha256"])
        adapter_delivery = self.router.dispatch(
            "POST",
            "/api/alerts/notifications/deliver",
            {"channel": "openlineage_submission_outbox", "execute": True, "provider": "dry-run-openlineage"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(adapter_delivery.success, adapter_delivery.error)
        self.assertEqual(adapter_delivery.data["delivered_count"], 1)
        delivered_openlineage = self.service.store.alert_notifications[openlineage_notification["notification_id"]]
        self.assertEqual(delivered_openlineage.status, "sent")
        self.assertEqual(delivered_openlineage.payload["delivery_provider"], "dry-run-openlineage")

        runs = self.router.dispatch("GET", "/api/orchestration/runs", {}, role="platform")
        self.assertTrue(runs.success)
        self.assertEqual(runs.data["total"], 1)
        metrics = self.router.dispatch("GET", "/api/metrics", {}, role="platform")
        self.assertEqual(metrics.data["counts"]["workflow_runs"], 1)
        self.assertEqual(metrics.data["counts"]["lineage_events"], 1)
        self.assertEqual(metrics.data["counts"]["model_versions"], 1)

        failed_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_failed",
                "inputs": {"as_of_date": "2026-05-16", "market": "A"},
                "status": "failed",
                "error": "extract_evidence timeout",
                "task_statuses": {"extract_evidence": "failed"},
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(failed_run.success, failed_run.error)
        self.assertEqual(failed_run.data["task_statuses"]["extract_evidence"], "failed")
        failed_metrics = self.router.dispatch("GET", "/api/metrics", {}, role="platform")
        self.assertEqual(failed_metrics.data["workflow_failed_runs"], 1)

        retry = self.router.dispatch(
            "POST",
            "/api/orchestration/runs/wfrun_daily_failed/retry",
            {"run_id": "wfrun_daily_retry", "status": "succeeded"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(retry.success, retry.error)
        self.assertEqual(retry.data["inputs"]["retry_of"], "wfrun_daily_failed")
        self.assertEqual(retry.data["status"], "succeeded")

        running_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_daily_research/run",
            {
                "run_id": "wfrun_daily_running",
                "inputs": {"as_of_date": "2026-05-17", "market": "A"},
                "status": "running",
                "started_at": "2026-05-15T00:00:00+00:00",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(running_run.success, running_run.error)
        sla_report = self.router.dispatch(
            "GET",
            "/api/orchestration/sla-report",
            {"as_of": "2026-05-15T01:00:00+00:00"},
            role="platform",
        )
        self.assertTrue(sla_report.success, sla_report.error)
        self.assertEqual(sla_report.data["breach_count"], 2)
        breaches = {row["run_id"]: row for row in sla_report.data["runs"]}
        self.assertEqual(breaches["wfrun_daily_failed"]["breach_type"], "failed_run")
        self.assertEqual(breaches["wfrun_daily_failed"]["owner"], "NLP/ML 负责人")
        self.assertEqual(breaches["wfrun_daily_running"]["breach_type"], "runtime_sla_breach")
        incidents = self.router.dispatch(
            "POST",
            "/api/orchestration/incidents/create",
            {"as_of": "2026-05-15T01:00:00+00:00"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(incidents.success, incidents.error)
        self.assertEqual(incidents.data["created_count"], 2)
        self.assertIn("ir_workflow_wfrun_daily_failed", self.service.store.incident_reports)

        self.router.dispatch("POST", "/api/alerts/rules/seed", {}, role="risk_compliance")
        workflow_alerts = self.router.dispatch("POST", "/api/alerts/evaluate", {}, role="risk_compliance")
        self.assertIn("alert_workflow_failed_runs", {item["rule_id"] for item in workflow_alerts.data["alerts"]})
        self.assertIn("alert_workflow_sla_breaches", {item["rule_id"] for item in workflow_alerts.data["alerts"]})

    def test_orchestration_readiness_report_requires_external_scheduler_lineage_and_registry_evidence(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_orchestration_ready",
                "name": "Orchestration readiness",
                "cadence": "daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect", "task_type": "noop", "queue": "ingestion", "output_refs": ["doc:ready"]},
                    {"task_id": "extract", "task_type": "noop", "queue": "document_ai", "depends_on": ["collect"], "output_refs": ["evidence:ready"]},
                    {"task_id": "publish", "task_type": "noop", "queue": "registry", "depends_on": ["extract", "external_catalog_sensor"], "output_refs": ["registry:ready"]},
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)
        run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_orchestration_ready/run",
            {
                "run_id": "wfrun_orch_ready_001",
                "inputs": {"as_of_date": "2026-05-15"},
                "status": "succeeded",
                "output_refs": ["registry:ready"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(run.success, run.error)
        model = self.router.dispatch(
            "POST",
            "/api/model-versions",
            {
                "model_version_id": "modelv_orch_ready",
                "model_name": "research-summary",
                "version": "2026-05-17",
                "model_type": "llm",
                "artifact_uri": "models:/research-summary/2026-05-17",
                "training_dataset_ids": ["evidence_ready"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
                "metrics": {"quality": 0.98, "mlflow_run_id": "mlrun_orch_ready"},
                "status": "approved",
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(model.success, model.error)
        lineage = self.router.dispatch(
            "POST",
            "/api/lineage/events",
            {
                "lineage_id": "lin_orch_ready",
                "job_run_id": "wfrun_orch_ready_001",
                "dataset": "evidence_ready",
                "input_refs": ["doc:ready"],
                "output_refs": ["registry:ready"],
                "code_version": "test-v1",
                "model_versions": ["modelv_orch_ready"],
                "prompt_versions": ["pr_llmtpl_research_summary_v1_baseline"],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(lineage.success, lineage.error)
        self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/submit",
            {"dag_id": "dag_orchestration_ready", "namespace": "ai_quant_test", "target": "openlineage://local-catalog"},
            actor="platform",
            role="platform",
        )
        self.router.dispatch(
            "POST",
            "/api/model-versions/mlflow/register",
            {"model_name": "research-summary", "target": "mlflow://local-registry"},
            actor="ml",
            role="nlp_ml",
        )

        gap = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {"dag_id": "dag_orchestration_ready", "as_of": "2026-05-18T12:00:00+00:00"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(gap.success, gap.error)
        self.assertFalse(gap.data["ready_for_orchestration_production"])
        self.assertIn("scheduler_deployment_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("external_sensor_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("backfill_drill_evidence_uri", gap.data["missing_requirements"])
        self.assertIn("openlineage_real_delivery", gap.data["missing_requirements"])
        self.assertIn("mlflow_real_registry", gap.data["missing_requirements"])
        self.assertFalse(gap.data["automation_allowed"])
        self.assertTrue(gap.data["external_deployment_required"])
        self.assertIn("orchestration_readiness_report_checks_scheduler", gap.data["usage_boundary"])

        ready = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {
                "dag_id": "dag_orchestration_ready",
                "as_of": "2026-05-18T12:00:00+00:00",
                "scheduler_endpoint": "https://airflow.staging.example.com",
                "openlineage_endpoint": "https://lineage.staging.example.com",
                "mlflow_endpoint": "https://mlflow.staging.example.com",
                "artifact_uris": {
                    "scheduler_deployment_uri": "artifact://orchestration/scheduler-deployment.json",
                    "worker_pool_evidence_uri": "artifact://orchestration/worker-pools.json",
                    "external_sensor_evidence_uri": "artifact://orchestration/external-sensors.json",
                    "backfill_drill_uri": "artifact://orchestration/backfill-drill.json",
                    "openlineage_delivery_evidence_uri": "artifact://orchestration/openlineage-delivery.json",
                    "mlflow_registry_evidence_uri": "artifact://orchestration/mlflow-registry.json",
                    "replay_runbook_uri": "artifact://orchestration/replay-runbook.md",
                },
                "record_readiness": True,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(ready.success, ready.error)
        self.assertTrue(ready.data["ready_for_orchestration_production"])
        self.assertEqual(ready.data["missing_requirements"], [])
        self.assertEqual(ready.data["workflow_summary"]["external_sensor_count"], 1)
        self.assertEqual(ready.data["lineage"]["openlineage_export_count"], 1)
        self.assertEqual(ready.data["model_registry"]["approved_artifact_coverage"], 1.0)
        self.assertEqual(self.service.store.audit_log[-1].action, "orchestration_readiness_report")

        simple_workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_orchestration_simple",
                "name": "Single queue reviewed orchestration",
                "cadence": "manual",
                "tasks": [{"task_id": "noop", "task_type": "noop", "queue": "default"}],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(simple_workflow.success, simple_workflow.error)
        simple_gap = self.router.dispatch(
            "POST",
            "/api/orchestration/readiness-report",
            {
                "dag_id": "dag_orchestration_simple",
                "scheduler_endpoint": "https://airflow.staging.example.com",
                "openlineage_endpoint": "https://lineage.staging.example.com",
                "mlflow_endpoint": "https://mlflow.staging.example.com",
                "artifact_uris": {
                    "scheduler_deployment_uri": "artifact://orchestration/scheduler-deployment.json",
                    "openlineage_delivery_evidence_uri": "artifact://orchestration/openlineage-delivery.json",
                    "mlflow_registry_evidence_uri": "artifact://orchestration/mlflow-registry.json",
                    "replay_runbook_uri": "artifact://orchestration/replay-runbook.md",
                },
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(simple_gap.success, simple_gap.error)
        self.assertFalse(simple_gap.data["ready_for_orchestration_production"])
        self.assertIn("worker_pool_evidence_uri", simple_gap.data["missing_requirements"])
        self.assertIn("external_sensor_evidence_uri", simple_gap.data["missing_requirements"])
        self.assertIn("backfill_drill_evidence_uri", simple_gap.data["missing_requirements"])

    def test_workflow_builtin_executor_runs_fact_pipeline_tasks(self) -> None:
        benchmark = self.router.dispatch(
            "POST",
            "/api/benchmarks",
            {
                "benchmark_id": "bm_executor_fact",
                "language": "en",
                "task_type": "term_extraction",
                "sample_size": 0,
                "threshold": {
                    "term_f1": 1.0,
                    "number_recall": 1.0,
                    "period_recall": 1.0,
                    "page_hit_rate": 1.0,
                    "avg_confidence": 0.8,
                },
            },
            actor="ml",
            role="nlp_ml",
        )
        self.assertTrue(benchmark.success, benchmark.error)
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_builtin_fact_pipeline",
                "name": "Built-in fact pipeline",
                "cadence": "manual",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {
                        "task_id": "ingest_doc",
                        "task_type": "ingest_document",
                        "dataset": "documents",
                        "payload": {
                            "document_id": "doc_executor_001",
                            "issuer_id": "issuer_001",
                            "security_id": "sec_001",
                            "source_id": "src_sec",
                            "source_type": "regulatory",
                            "document_type": "10-K",
                            "source_uri": "https://example.invalid/doc-executor-001",
                            "body": "FY2026 revenue grew 12% to RMB 100 million. Operating cash flow improved in 2026.",
                            "rights_tag": {
                                "license_class": "public",
                                "training_allowed": False,
                                "redistribution_allowed": False,
                                "display_use": "allowed",
                                "non_display_use": "restricted",
                                "derived_data_use": "restricted",
                            },
                            "language": "en",
                        },
                    },
                    {
                        "task_id": "extract_evidence",
                        "task_type": "extract_evidence",
                        "dataset": "evidence_chunks",
                        "depends_on": ["ingest_doc"],
                        "payload": {
                            "document_id": "${ingest_doc.output_ids.0}",
                            "parser_version": "workflow-executor",
                            "model_version": "rule-baseline",
                        },
                    },
                    {
                        "task_id": "extract_facts",
                        "task_type": "structured_extraction",
                        "dataset": "structured_facts",
                        "depends_on": ["extract_evidence"],
                        "payload": {
                            "extraction_id": "ext_executor_fact",
                            "evidence_id": "${extract_evidence.output_ids.0}",
                            "benchmark_id": "bm_executor_fact",
                            "expected_terms": ["revenue", "operating_cash_flow"],
                            "expected_numbers": 1,
                            "expected_periods": 1,
                            "parser_version": "workflow-executor",
                        },
                    },
                    {
                        "task_id": "rebuild_search",
                        "task_type": "search_rebuild",
                        "dataset": "search_index",
                        "depends_on": ["extract_facts"],
                        "payload": {"targets": ["keyword", "semantic"], "include_restricted": True},
                    },
                    {
                        "task_id": "register_sample",
                        "task_type": "benchmark_sample_register",
                        "dataset": "benchmark_samples",
                        "depends_on": ["ingest_doc"],
                        "payload": {
                            "benchmark_id": "bm_executor_fact",
                            "sample_id": "bms_executor_fact",
                            "document_id": "${ingest_doc.output_ids.0}",
                            "language": "en",
                            "expected_terms": ["revenue", "operating_cash_flow"],
                            "expected_numbers": 1,
                            "expected_periods": 1,
                            "expected_pages": [1],
                        },
                    },
                    {
                        "task_id": "run_benchmark",
                        "task_type": "benchmark_run",
                        "dataset": "benchmark_runs",
                        "depends_on": ["register_sample", "extract_evidence"],
                        "payload": {
                            "benchmark_id": "bm_executor_fact",
                            "run_id": "bmrn_executor_fact",
                            "sample_ids": ["${register_sample.output_ids.0}"],
                            "min_confidence": 0.8,
                        },
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)

        execute = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_builtin_fact_pipeline/execute",
            {
                "run_id": "wfrun_builtin_fact_001",
                "inputs": {"as_of_date": "2026-05-15"},
                "code_version": "test-executor-v1",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(execute.success, execute.error)
        self.assertFalse(execute.data["existing"])
        run = execute.data["run"]
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(set(run["task_statuses"].values()), {"succeeded"})
        task_results = execute.data["task_results"]
        evidence_id = task_results["extract_evidence"]["output_ids"][0]
        self.assertEqual(task_results["extract_facts"]["payload"]["evidence_id"], evidence_id)
        self.assertEqual(task_results["run_benchmark"]["result"]["passed"], True)
        self.assertIn("document:doc_executor_001", run["output_refs"])
        self.assertIn(f"evidence:{evidence_id}", run["output_refs"])
        self.assertIn("extraction:ext_executor_fact", run["output_refs"])
        self.assertIn("search_index:keyword", run["output_refs"])
        self.assertIn("benchmark_sample:bms_executor_fact", run["output_refs"])
        self.assertIn("benchmark_run:bmrn_executor_fact", run["output_refs"])
        self.assertEqual(len(execute.data["lineage_events"]), 6)
        self.assertEqual({item["dataset"] for item in execute.data["lineage_events"]}, {"documents", "evidence_chunks", "structured_facts", "search_index", "benchmark_samples", "benchmark_runs"})
        self.assertEqual(self.service.store.audit_log[-1].action, "execute_workflow_definition")

        duplicate = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_builtin_fact_pipeline/execute",
            {"inputs": {"as_of_date": "2026-05-15"}},
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertTrue(duplicate.data["existing"])
        self.assertEqual(duplicate.data["run"]["run_id"], "wfrun_builtin_fact_001")

        graph = self.router.dispatch(
            "POST",
            "/api/orchestration/dependency-graph",
            {"dag_id": "dag_builtin_fact_pipeline"},
            role="platform",
        )
        self.assertTrue(graph.success, graph.error)
        self.assertEqual(graph.data["graphs"][0]["latest_run_id"], "wfrun_builtin_fact_001")
        self.assertEqual(graph.data["graphs"][0]["lineage"]["latest_run_event_count"], 6)
        self.assertEqual(graph.data["graphs"][0]["lineage"]["datasets"]["benchmark_runs"], 1)

        openlineage = self.router.dispatch(
            "POST",
            "/api/orchestration/openlineage/export",
            {"run_id": "wfrun_builtin_fact_001", "namespace": "ai_quant_test"},
            actor="platform",
            role="platform",
        )
        self.assertTrue(openlineage.success, openlineage.error)
        self.assertEqual(openlineage.data["lineage_event_count"], 6)
        exported = openlineage.data["events"][0]
        self.assertEqual(exported["eventType"], "COMPLETE")
        self.assertIn("benchmark_run:bmrn_executor_fact", {item["name"] for item in exported["outputs"]})

    def test_workflow_backfill_plans_and_records_queue_isolated_runs(self) -> None:
        workflow = self.router.dispatch(
            "POST",
            "/api/orchestration/dags",
            {
                "dag_id": "dag_queue_backfill",
                "name": "Queue isolated backfill",
                "cadence": "business_daily",
                "idempotency_key_fields": ["as_of_date"],
                "tasks": [
                    {"task_id": "collect", "task_type": "noop", "queue": "ingestion", "payload": {"message": "collect"}},
                    {
                        "task_id": "parse",
                        "task_type": "noop",
                        "queue": "document_ai",
                        "depends_on": ["collect"],
                        "payload": {"message": "parse"},
                    },
                    {
                        "task_id": "evaluate",
                        "task_type": "noop",
                        "queue": "evaluation",
                        "depends_on": ["parse"],
                        "payload": {"message": "evaluate"},
                    },
                ],
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(workflow.success, workflow.error)

        dry_run = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "start_date": "2026-05-15",
                "end_date": "2026-05-18",
                "queues": ["document_ai"],
                "inputs": {"market": "A"},
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(dry_run.success, dry_run.error)
        self.assertTrue(dry_run.data["dry_run"])
        self.assertEqual(dry_run.data["planned_count"], 2)
        self.assertEqual(dry_run.data["created_count"], 0)
        self.assertEqual(dry_run.data["selection"]["queues"], ["document_ai"])
        planned_dates = [item["run_date"] for item in dry_run.data["plan"]]
        self.assertEqual(planned_dates, ["2026-05-15", "2026-05-18"])
        planned_first = dry_run.data["plan"][0]
        self.assertTrue(planned_first["queue_isolation"])
        self.assertTrue(planned_first["partial_execution"])
        self.assertEqual(planned_first["task_statuses"]["parse"], "queued")
        self.assertEqual(planned_first["task_statuses"]["collect"], "skipped")
        self.assertEqual(self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform").data["total"], 0)

        plan_only = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15"],
                "queues": ["document_ai"],
                "dry_run": False,
                "execute": False,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(plan_only.success, plan_only.error)
        self.assertFalse(plan_only.data["dry_run"])
        self.assertFalse(plan_only.data["execute"])
        self.assertEqual(plan_only.data["planned_count"], 1)
        self.assertEqual(plan_only.data["created_count"], 0)
        self.assertEqual(self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform").data["total"], 0)

        execute = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15", "2026-05-18"],
                "queues": "document_ai",
                "inputs": {"market": "A"},
                "dry_run": False,
                "execute": True,
                "run_id_prefix": "wfrun_backfill_queue",
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(execute.success, execute.error)
        self.assertFalse(execute.data["dry_run"])
        self.assertEqual(execute.data["created_count"], 2)
        self.assertEqual(execute.data["reused_count"], 0)
        self.assertIn("built_in_backfill_planner", execute.data["usage_boundary"])
        first_run = execute.data["runs"][0]
        self.assertEqual(first_run["run_id"], "wfrun_backfill_queue_20260515")
        self.assertEqual(first_run["status"], "queued")
        self.assertEqual(first_run["inputs"]["as_of_date"], "2026-05-15")
        self.assertEqual(first_run["inputs"]["market"], "A")
        self.assertEqual(first_run["inputs"]["backfill"]["selection"]["task_ids"], ["parse"])
        self.assertTrue(first_run["inputs"]["backfill"]["queue_isolation"])
        self.assertEqual(first_run["task_statuses"]["parse"], "queued")
        self.assertEqual(first_run["task_statuses"]["collect"], "skipped")
        self.assertEqual(first_run["task_statuses"]["evaluate"], "skipped")

        duplicate = self.router.dispatch(
            "POST",
            "/api/orchestration/dags/dag_queue_backfill/backfill",
            {
                "run_dates": ["2026-05-15", "2026-05-18"],
                "queues": "document_ai",
                "inputs": {"market": "A"},
                "dry_run": False,
                "execute": True,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(duplicate.success, duplicate.error)
        self.assertEqual(duplicate.data["created_count"], 0)
        self.assertEqual(duplicate.data["reused_count"], 2)
        self.assertEqual(duplicate.data["skipped_count"], 2)
        self.assertEqual({item["reason"] for item in duplicate.data["skipped"]}, {"idempotent_run_exists"})
        runs = self.router.dispatch("GET", "/api/orchestration/runs", {"dag_id": "dag_queue_backfill"}, role="platform")
        self.assertTrue(runs.success, runs.error)
        self.assertEqual(runs.data["total"], 2)

        handoff = self.router.dispatch(
            "POST",
            "/api/orchestration/scheduler-handoff",
            {
                "dag_id": "dag_queue_backfill",
                "as_of": "2026-05-20T12:00:00+00:00",
                "backfill_window_days": 10,
            },
            actor="platform",
            role="platform",
        )
        self.assertTrue(handoff.success, handoff.error)
        self.assertEqual(handoff.data["recommended_orchestrator"]["recommended"], "airflow_or_dagster")
        self.assertEqual(handoff.data["queue_count"], 3)
        worker_pools = {item["queue"]: item for item in handoff.data["worker_pools"]}
        self.assertTrue({"ingestion", "document_ai", "evaluation"}.issubset(worker_pools))
        self.assertEqual(worker_pools["document_ai"]["worker_pool"], "wf_document_ai_pool")
        workflow_handoff = handoff.data["workflows"][0]
        self.assertTrue(workflow_handoff["queue_isolation_required"])
        self.assertEqual(workflow_handoff["adapter_contract"]["cron_schedule"], "0 9 * * 1-5")
        self.assertIn("/api/orchestration/dags/dag_queue_backfill/backfill", workflow_handoff["adapter_contract"]["backfill_endpoint"])
        self.assertEqual(workflow_handoff["backfill"]["planned_dates"], ["2026-05-19", "2026-05-20"])
        self.assertIn("worker_pool_deployment_and_queue_binding_evidence", handoff.data["missing_external_evidence"])
