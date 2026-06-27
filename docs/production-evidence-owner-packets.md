# Production External Evidence Owner Packets

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421
- Scope: owner-by-owner external evidence collection instructions for non-local production closure
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Purpose

These packets convert the production evidence collection plan into owner-specific work. They are collection instructions only and are not release evidence. Every artifact URI must later be replaced with a concrete external staging/production archive URI, validated by `scripts/production_evidence_plan_check.py --require-filled-uris`, covered by artifact inventory, and passed through the strict release gate.

## Summary

- Owner packets: 6
- External evidence tasks: 17
- Required artifact fields: 80
- Boundary: owner packets are collection instructions only; they are not release evidence

## CIO

- Task count: 2
- Artifact field count: 7
- Task IDs: T-408, T-409

### T-408

- Readiness endpoint: `/api/portfolio/attribution/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - performance reconciliation
  - NAV/ledger reconciliation
  - board pack artifact
  - large replay acceptance
- Required artifact fields:
  - `performance_reconciliation_uri`
  - `ledger_extract_uri`
  - `board_pack_uri`
  - `strategy_replay_uri`
- URI template:
  - `performance_reconciliation_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/performance_reconciliation_uri`
  - `ledger_extract_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/ledger_extract_uri`
  - `board_pack_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/board_pack_uri`
  - `strategy_replay_uri`: `s3://<production-evidence-bucket>/<release-id>/T-408/strategy_replay_uri`

### T-409

- Readiness endpoint: `/api/portfolio/optimizer/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - production PyPortfolioOpt/CVXPY solver comparison
  - solver version/parameter artifact
- Required artifact fields:
  - `solver_artifact_uri`
  - `comparison_report_uri`
  - `constraint_report_uri`
- URI template:
  - `solver_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/solver_artifact_uri`
  - `comparison_report_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/comparison_report_uri`
  - `constraint_report_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/constraint_report_uri`

## NLP/ML 负责人

- Task count: 3
- Artifact field count: 15
- Task IDs: T-402, T-410, T-418

### T-402

- Readiness endpoint: `/api/benchmarks/{benchmark_id}/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - 300-500 real CN filing/report samples
  - English SEC sample set
  - human annotation manual
  - OCR bbox/table cell gold labels
  - summary quality samples
  - regression baseline report
- Required artifact fields:
  - `sample_manifest_uri`
  - `chinese_sample_set_uri`
  - `english_sample_set_uri`
  - `annotation_manual_uri`
  - `bbox_gold_uri`
  - `table_cell_gold_uri`
  - `summary_quality_uri`
  - `regression_baseline_uri`
- URI template:
  - `sample_manifest_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/sample_manifest_uri`
  - `chinese_sample_set_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/chinese_sample_set_uri`
  - `english_sample_set_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/english_sample_set_uri`
  - `annotation_manual_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/annotation_manual_uri`
  - `bbox_gold_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/bbox_gold_uri`
  - `table_cell_gold_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/table_cell_gold_uri`
  - `summary_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/summary_quality_uri`
  - `regression_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-402/regression_baseline_uri`

### T-410

- Readiness endpoint: `/api/research/answers/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - real model quality evaluation
  - fallback comparison at scale
- Required artifact fields:
  - `model_quality_eval_uri`
  - `fallback_comparison_uri`
  - `summary_rubric_uri`
- URI template:
  - `model_quality_eval_uri`: `s3://<production-evidence-bucket>/<release-id>/T-410/model_quality_eval_uri`
  - `fallback_comparison_uri`: `s3://<production-evidence-bucket>/<release-id>/T-410/fallback_comparison_uri`
  - `summary_rubric_uri`: `s3://<production-evidence-bucket>/<release-id>/T-410/summary_rubric_uri`

### T-418

- Readiness endpoint: `/api/llm/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - real model quality evaluation
  - fallback comparison at scale
  - LLM gateway smoke
  - budget sync artifact
- Required artifact fields:
  - `real_model_quality_uri`
  - `fallback_quality_uri`
  - `llm_gateway_smoke_uri`
  - `budget_sync_evidence_uri`
- URI template:
  - `real_model_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/real_model_quality_uri`
  - `fallback_quality_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/fallback_quality_uri`
  - `llm_gateway_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/llm_gateway_smoke_uri`
  - `budget_sync_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-418/budget_sync_evidence_uri`

## 分析师

- Task count: 1
- Artifact field count: 3
- Task IDs: T-406A

### T-406A

- Readiness endpoint: `/api/hotspots/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - real hotspot query/gold reference LLM rerank evaluation
- Required artifact fields:
  - `query_gold_refs_uri`
  - `llm_rerank_eval_uri`
  - `research_task_queue_uri`
- URI template:
  - `query_gold_refs_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/query_gold_refs_uri`
  - `llm_rerank_eval_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/llm_rerank_eval_uri`
  - `research_task_queue_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/research_task_queue_uri`

## 平台负责人

- Task count: 6
- Artifact field count: 35
- Task IDs: T-404, T-407, T-411, T-412, T-419, T-420

### T-404

- Readiness endpoint: `/api/governance/storage-readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - PostgreSQL/S3/OpenSearch real environment smoke
  - capacity and latency baseline
  - backup restore drill
- Required artifact fields:
  - `postgres_smoke_uri`
  - `s3_smoke_uri`
  - `opensearch_smoke_uri`
  - `capacity_baseline_uri`
  - `backup_restore_uri`
  - `least_privilege_policy_uri`
- URI template:
  - `postgres_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/postgres_smoke_uri`
  - `s3_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/s3_smoke_uri`
  - `opensearch_smoke_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/opensearch_smoke_uri`
  - `capacity_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/capacity_baseline_uri`
  - `backup_restore_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/backup_restore_uri`
  - `least_privilege_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-404/least_privilege_policy_uri`

### T-407

- Readiness endpoint: `/api/readiness/ui-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - non-local real-volume UI workflow acceptance
  - desktop/mobile cross-browser matrix artifact
- Required artifact fields:
  - `browser_acceptance_uri`
  - `screenshot_manifest_uri`
  - `cross_browser_matrix_uri`
  - `real_data_workflow_uri`
  - `visual_overflow_review_uri`
  - `access_control_review_uri`
- URI template:
  - `browser_acceptance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/browser_acceptance_uri`
  - `screenshot_manifest_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/screenshot_manifest_uri`
  - `cross_browser_matrix_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/cross_browser_matrix_uri`
  - `real_data_workflow_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/real_data_workflow_uri`
  - `visual_overflow_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/visual_overflow_review_uri`
  - `access_control_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-407/access_control_review_uri`

### T-411

- Readiness endpoint: `/api/observability/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - non-local OTel collector backend query evidence
  - retention policy execution
  - external alert delivery evidence
- Required artifact fields:
  - `collector_evidence_uri`
  - `logs_backend_uri`
  - `query_evidence_uri`
  - `retention_policy_uri`
  - `external_alert_evidence_uri`
  - `drill_evidence_uri`
- URI template:
  - `collector_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/collector_evidence_uri`
  - `logs_backend_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/logs_backend_uri`
  - `query_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/query_evidence_uri`
  - `retention_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/retention_policy_uri`
  - `external_alert_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/external_alert_evidence_uri`
  - `drill_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-411/drill_evidence_uri`

### T-412

- Readiness endpoint: `/api/readiness/deployment-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - production parameter confirmation
  - external secret manager integration
  - backup restore artifact
  - release checklist
  - canary/rollback artifact
- Required artifact fields:
  - `production_parameters_uri`
  - `secret_manager_evidence_uri`
  - `backup_restore_evidence_uri`
  - `capacity_baseline_uri`
  - `release_checklist_uri`
  - `canary_plan_uri`
  - `rollback_plan_uri`
- URI template:
  - `production_parameters_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/production_parameters_uri`
  - `secret_manager_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/secret_manager_evidence_uri`
  - `backup_restore_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/backup_restore_evidence_uri`
  - `capacity_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/capacity_baseline_uri`
  - `release_checklist_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/release_checklist_uri`
  - `canary_plan_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/canary_plan_uri`
  - `rollback_plan_uri`: `s3://<production-evidence-bucket>/<release-id>/T-412/rollback_plan_uri`

### T-419

- Readiness endpoint: `/api/graph-vector/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - Neo4j/Qdrant non-local sync artifact
  - batch throughput baseline
  - failure injection/retry recovery evidence
- Required artifact fields:
  - `neo4j_sync_artifact_uri`
  - `qdrant_sync_artifact_uri`
  - `throughput_baseline_uri`
  - `failure_recovery_uri`
- URI template:
  - `neo4j_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-419/neo4j_sync_artifact_uri`
  - `qdrant_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-419/qdrant_sync_artifact_uri`
  - `throughput_baseline_uri`: `s3://<production-evidence-bucket>/<release-id>/T-419/throughput_baseline_uri`
  - `failure_recovery_uri`: `s3://<production-evidence-bucket>/<release-id>/T-419/failure_recovery_uri`

### T-420

- Readiness endpoint: `/api/orchestration/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - Airflow/Dagster/Cron deployment evidence
  - external sensor connectivity
  - distributed worker queue isolation
  - large-window backfill drill
  - OpenLineage/MLflow real client evidence
- Required artifact fields:
  - `scheduler_deployment_uri`
  - `worker_pool_uri`
  - `external_sensor_uri`
  - `backfill_drill_uri`
  - `openlineage_client_uri`
  - `mlflow_registry_uri`
- URI template:
  - `scheduler_deployment_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/scheduler_deployment_uri`
  - `worker_pool_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/worker_pool_uri`
  - `external_sensor_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/external_sensor_uri`
  - `backfill_drill_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/backfill_drill_uri`
  - `openlineage_client_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/openlineage_client_uri`
  - `mlflow_registry_uri`: `s3://<production-evidence-bucket>/<release-id>/T-420/mlflow_registry_uri`

## 数据工程

- Task count: 3
- Artifact field count: 12
- Task IDs: T-405, T-406, T-416

### T-405

- Readiness endpoint: `/api/13f/filings/mapping-readiness`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - real Form 13F large sample parse run
  - CUSIP/FIGI/issuer gold mapping accuracy evidence
- Required artifact fields:
  - `batch_parse_artifact_uri`
  - `gold_mapping_uri`
  - `unmapped_review_queue_uri`
- URI template:
  - `batch_parse_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-405/batch_parse_artifact_uri`
  - `gold_mapping_uri`: `s3://<production-evidence-bucket>/<release-id>/T-405/gold_mapping_uri`
  - `unmapped_review_queue_uri`: `s3://<production-evidence-bucket>/<release-id>/T-405/unmapped_review_queue_uri`

### T-406

- Readiness endpoint: `/api/entity-mappings/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - ADR/Chinese ADR real batch mapping evidence
  - entity page browser acceptance
  - Neo4j external sync evidence
  - Qdrant external sync evidence
- Required artifact fields:
  - `batch_mapping_artifact_uri`
  - `entity_page_acceptance_uri`
  - `neo4j_sync_artifact_uri`
  - `qdrant_sync_artifact_uri`
- URI template:
  - `batch_mapping_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/batch_mapping_artifact_uri`
  - `entity_page_acceptance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/entity_page_acceptance_uri`
  - `neo4j_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/neo4j_sync_artifact_uri`
  - `qdrant_sync_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406/qdrant_sync_artifact_uri`

### T-416

- Readiness endpoint: `/api/connectors/astock/verification-readiness`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - connector endpoint availability artifacts
  - endpoint stability artifacts
  - rate-limit/quota verification
  - license/TOS reviews
  - field sample artifacts for every approved connector
- Required artifact fields:
  - `endpoint_artifact_uri`
  - `stability_artifact_uri`
  - `rate_limit_artifact_uri`
  - `license_review_uri`
  - `field_sample_uri`
- URI template:
  - `endpoint_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/endpoint_artifact_uri`
  - `stability_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/stability_artifact_uri`
  - `rate_limit_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/rate_limit_artifact_uri`
  - `license_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/license_review_uri`
  - `field_sample_uri`: `s3://<production-evidence-bucket>/<release-id>/T-416/field_sample_uri`

## 风险/合规

- Task count: 2
- Artifact field count: 8
- Task IDs: T-414, T-421

### T-414

- Readiness endpoint: `/api/research/citation-boundary/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - citation boundary policy review artifact
  - source review artifact
  - manual reference reviewed-empty artifact where applicable
- Required artifact fields:
  - `policy_review_uri`
  - `source_review_uri`
  - `manual_reference_review_uri`
  - `research_governance_uri`
- URI template:
  - `policy_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/policy_review_uri`
  - `source_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/source_review_uri`
  - `manual_reference_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/manual_reference_review_uri`
  - `research_governance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/research_governance_uri`

### T-421

- Readiness endpoint: `/api/governance/security-readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- External blockers:
  - external KMS/secret manager evidence
  - external API key least privilege review
  - object store/search external delete executor evidence
- Required artifact fields:
  - `secret_manager_evidence_uri`
  - `least_privilege_policy_uri`
  - `external_delete_evidence_uri`
  - `permission_review_uri`
- URI template:
  - `secret_manager_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/secret_manager_evidence_uri`
  - `least_privilege_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/least_privilege_policy_uri`
  - `external_delete_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/external_delete_evidence_uri`
  - `permission_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/permission_review_uri`

## Release Gate Handoff

After owners upload the real evidence objects, run:

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```

Do not use local-only artifacts, demo artifacts, localhost URLs, `file://`, `local://`, or `artifact://staging-local` as production evidence.
