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
- Required artifact fields: 81
- Boundary: owner packets are collection instructions only; they are not release evidence

## CIO

- Task count: 2
- Artifact field count: 7
- Task IDs: T-408, T-409

### T-408

- Readiness endpoint: `/api/portfolio/attribution/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows / Portfolio
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
- Collection procedure:
  - Reconcile simulated portfolio performance against NAV/ledger extracts using paper-only data.
  - Generate the board pack and replay evidence from the same immutable ledger snapshot.
  - Confirm the packet contains no broker connection, order placement, or live execution artifact.
- Minimum artifact contents:
  - Performance and NAV/ledger reconciliation with variance explanation.
  - Board pack artifact and strategy replay acceptance.
  - Paper-only boundary statement and reviewer sign-off.
- Reviewer routing:
  - Governance, Security, and Compliance

### T-409

- Readiness endpoint: `/api/portfolio/optimizer/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows / Portfolio
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
- Collection procedure:
  - Run the production PyPortfolioOpt/CVXPY solver comparison with declared versions and parameters.
  - Capture constraint reports and comparison output using paper-only portfolio inputs.
  - Record infeasible-solver handling and reviewer sign-off.
- Minimum artifact contents:
  - Solver version, parameter artifact, and reproducible input snapshot.
  - Comparison report and constraint report.
  - Paper-only/no-order-execution boundary statement.
- Reviewer routing:
  - Platform and Quality
  - Governance, Security, and Compliance

## NLP/ML 负责人

- Task count: 3
- Artifact field count: 15
- Task IDs: T-402, T-410, T-418

### T-402

- Readiness endpoint: `/api/benchmarks/{benchmark_id}/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows
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
- Collection procedure:
  - Build the benchmark from public filings, official company reports, and explicitly licensed/local documents only.
  - Record the benchmark id, schema version, sample inclusion/exclusion rules, annotator QA process, and pass metrics.
  - Exclude restricted sell-side reports, transcripts, and boundary-unclear material from training or benchmark gold labels.
- Minimum artifact contents:
  - 300-500 real Chinese filing/report samples plus an English SEC sample set with source and rights metadata.
  - OCR bbox/table-cell gold labels, annotation manual, summary quality sample, and regression baseline report.
  - Pass/fail metrics for extraction accuracy, table quality, summary quality, and boundary compliance.
- Reviewer routing:
  - Data and Evidence
  - Governance, Security, and Compliance

### T-410

- Readiness endpoint: `/api/research/answers/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows
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
- Collection procedure:
  - Run real research-answer quality evaluation with declared dataset, rubric, judge/human process, and pass threshold.
  - Check citation provenance, unsupported claims, hallucination rate, and restricted-source exclusion.
  - Compare fallback behavior at scale and archive both model and fallback outputs.
- Minimum artifact contents:
  - Model quality eval, fallback comparison, and summary rubric artifacts.
  - Dataset definition, scoring rubric, pass threshold, and reviewer process.
  - Citation/provenance and source-boundary compliance results.
- Reviewer routing:
  - Governance, Security, and Compliance
  - Data and Evidence

### T-418

- Readiness endpoint: `/api/llm/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows
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
- Collection procedure:
  - Separate LLM gateway readiness from research-answer quality; reuse T-410 evidence only when source URI and scope are explicit.
  - Run gateway smoke covering provider/model versions, timeout/fallback behavior, and redacted request ids.
  - Archive budget/spend limit snapshot and failure-mode evidence without secrets.
- Minimum artifact contents:
  - Real model quality, fallback quality, gateway smoke, and budget sync artifacts.
  - Provider/model version, timeout, fallback, and failure-mode coverage.
  - Secret-free request metadata and spend/limit snapshot.
- Reviewer routing:
  - Governance, Security, and Compliance
  - Platform and Quality

## 分析师

- Task count: 1
- Artifact field count: 4
- Task IDs: T-406A

### T-406A

- Readiness endpoint: `/api/hotspots/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Research and AI Workflows
- External blockers:
  - real hotspot query/gold reference LLM rerank evaluation
- Required artifact fields:
  - `query_gold_refs_uri`
  - `llm_rerank_eval_uri`
  - `company_position_review_uri`
  - `chain_taxonomy_review_uri`
- URI template:
  - `query_gold_refs_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/query_gold_refs_uri`
  - `llm_rerank_eval_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/llm_rerank_eval_uri`
  - `company_position_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/company_position_review_uri`
  - `chain_taxonomy_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/chain_taxonomy_review_uri`
- Collection procedure:
  - Collect hotspot query/gold refs and offline rerank evaluation without invoking live trading or broker workflows.
  - Attach company positioning and industry-chain taxonomy review artifacts required by `/api/hotspots/readiness-report`.
  - Prove persisted or reviewed research tasks through the readiness report gates, not through a standalone queue URI.
- Minimum artifact contents:
  - Hotspot gold refs artifact, rerank evaluation sample count, top-1 accuracy, and model/fallback version.
  - Company positioning review and chain taxonomy review artifacts accepted by the readiness endpoint.
  - Evidence that research tasks are persisted or explicitly reviewed while automation remains disabled.
- Reviewer routing:
  - Data and Evidence
  - Governance, Security, and Compliance

## 平台负责人

- Task count: 6
- Artifact field count: 35
- Task IDs: T-404, T-407, T-411, T-412, T-419, T-420

### T-404

- Readiness endpoint: `/api/governance/storage-readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Run PostgreSQL, S3-compatible object store, and OpenSearch smoke tests in the real non-local environment.
  - Capture capacity, latency, backup restore, and least-privilege policy evidence from the same release target.
  - Record exact environment, command, timestamp, producer, and pass/fail thresholds for every artifact.
- Minimum artifact contents:
  - PostgreSQL/S3/OpenSearch connectivity and read/write/query proof.
  - Capacity and latency baseline with target thresholds.
  - Backup restore drill result and least-privilege access review.
- Reviewer routing:
  - Governance, Security, and Compliance

### T-407

- Readiness endpoint: `/api/readiness/ui-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Run real-volume browser acceptance on desktop and mobile viewports across the declared browser matrix.
  - Record target workflows, screenshot manifest, console errors, overflow criteria, and access-control scenarios.
  - Store screenshots and acceptance logs under immutable external staging/production URIs.
- Minimum artifact contents:
  - Browser matrix with versions, viewport sizes, workflows, and pass/fail result.
  - Screenshot manifest and visual overflow review.
  - Access-control review for unauthorized, analyst, and governance roles.
- Reviewer routing:
  - Product and UI
  - Governance, Security, and Compliance

### T-411

- Readiness endpoint: `/api/observability/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Run OTel collector ingestion against the real backend and capture query examples for metrics, logs, and traces.
  - Prove retention policy execution, alert channel delivery, and incident drill flow.
  - Record timestamps, alert recipient/channel, and drill acceptance criteria.
- Minimum artifact contents:
  - Collector evidence, logs backend proof, and query evidence.
  - Retention policy artifact and external alert delivery evidence.
  - Incident drill evidence with owner, timeline, and result.
- Reviewer routing:
  - Governance, Security, and Compliance

### T-412

- Readiness endpoint: `/api/readiness/deployment-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Complete the production parameter checklist and secret manager integration proof without exposing secret values.
  - Run or reference the backup/restore artifact for this deployment target.
  - Archive canary scope, rollback triggers, release checklist, and owner approval.
- Minimum artifact contents:
  - Production parameters, secret metadata, backup restore evidence, and capacity baseline.
  - Release checklist with named approver.
  - Canary plan and rollback plan with trigger criteria.
- Reviewer routing:
  - Governance, Security, and Compliance
  - PM / Release Coordination

### T-419

- Readiness endpoint: `/api/graph-vector/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Run non-local Neo4j/Qdrant sync jobs and record expected record counts and actual counts.
  - Measure batch throughput against declared thresholds.
  - Inject or document a failure/retry scenario and recovery result.
- Minimum artifact contents:
  - Neo4j and Qdrant sync artifacts with record counts and job identifiers.
  - Throughput baseline with threshold and environment.
  - Failure injection/retry recovery evidence.
- Reviewer routing:
  - Data and Evidence

### T-420

- Readiness endpoint: `/api/orchestration/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Platform and Quality
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
- Collection procedure:
  - Declare scheduler choice and environment, then run deployment evidence for the real orchestration target.
  - Prove external sensor connectivity, distributed worker queue isolation, and a large-window backfill drill.
  - Capture OpenLineage and MLflow client evidence with lineage/run identifiers.
- Minimum artifact contents:
  - Scheduler deployment, worker pool, external sensor, and backfill drill artifacts.
  - OpenLineage client and MLflow registry proof.
  - Run logs with environment, backfill window, status, and failure handling.
- Reviewer routing:
  - Data and Evidence
  - Governance, Security, and Compliance

## 数据工程

- Task count: 3
- Artifact field count: 12
- Task IDs: T-405, T-406, T-416

### T-405

- Readiness endpoint: `/api/13f/filings/mapping-readiness`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Data and Evidence
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
- Collection procedure:
  - Run a large real Form 13F parsing batch for a declared source window.
  - Compare CUSIP/FIGI/issuer mapping against a gold set and record the accuracy threshold.
  - Publish the unresolved/unmapped review queue with owner and next action.
- Minimum artifact contents:
  - Sample size, filing date window, accepted 13F source list, and parser version.
  - CUSIP/FIGI/issuer mapping accuracy report with threshold and failures.
  - Unmapped review queue grouped by issuer/security and severity.
- Reviewer routing:
  - Platform and Quality

### T-406

- Readiness endpoint: `/api/entity-mappings/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Data and Evidence
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
- Collection procedure:
  - Run ADR/Chinese ADR real batch entity mapping and export source-to-entity decisions.
  - Verify entity page browser acceptance and external Neo4j/Qdrant sync artifacts.
  - Route review across data quality, UI acceptance, and platform sync owners.
- Minimum artifact contents:
  - Batch mapping artifact with duplicate/ambiguous entity counts and reviewer decisions.
  - Entity page browser acceptance evidence using real mapped entities.
  - Neo4j/Qdrant sync record counts, failure count, and recovery notes.
- Reviewer routing:
  - Product and UI
  - Platform and Quality

### T-416

- Readiness endpoint: `/api/connectors/astock/verification-readiness`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Data and Evidence
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
- Collection procedure:
  - Verify every approved A-stock connector endpoint and record license/TOS owner review.
  - Use the approved connector list: baidu_concepts, cninfo_announcements, dragon_tiger_list, eastmoney_research, tencent_valuation_snapshot, ths_hot_topics, unlock_calendar.
  - Capture endpoint availability, stability, rate-limit/quota behavior, and field sample artifacts.
- Minimum artifact contents:
  - Endpoint availability and stability artifacts for every approved connector.
  - Rate-limit/quota verification and license/TOS review.
  - Field sample artifact with connector id, timestamp, and schema version.
- Reviewer routing:
  - Governance, Security, and Compliance
  - Platform and Quality

## 风险/合规

- Task count: 2
- Artifact field count: 8
- Task IDs: T-414, T-421

### T-414

- Readiness endpoint: `/api/research/citation-boundary/readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Governance, Security, and Compliance
- External blockers:
  - citation boundary policy review artifact
  - source review artifact
  - manual reference reviewed-empty artifact where applicable
- Required artifact fields:
  - `citation_policy_uri`
  - `source_review_uri`
  - `manual_reference_review_uri`
  - `research_governance_uri`
- URI template:
  - `citation_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/citation_policy_uri`
  - `source_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/source_review_uri`
  - `manual_reference_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/manual_reference_review_uri`
  - `research_governance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/research_governance_uri`
- Collection procedure:
  - Review citation length policy, source review coverage, restricted-source handling, and manual-reference metadata-only behavior.
  - Use `citation_policy_uri` for the policy artifact accepted by `/api/research/citation-boundary/readiness-report`.
  - Record reviewed-empty evidence where no manual-reference bodies are allowed.
- Minimum artifact contents:
  - Citation policy artifact, source review coverage report, and manual-reference review artifact.
  - Restricted-source exclusion and metadata-only proof.
  - Research governance artifact showing no restricted training or unsupported citation behavior.
- Reviewer routing:
  - Research and AI Workflows
  - Data and Evidence

### T-421

- Readiness endpoint: `/api/governance/security-readiness-report`
- Acceptance rule: artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted
- Owner group: Governance, Security, and Compliance
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
- Collection procedure:
  - Collect secret/KMS evidence as metadata only; never archive secret values, tokens, private keys, or signed URLs.
  - Run external delete evidence from the approved executor identity and capture permission-denied/audit or red-team proof.
  - Verify scoped API permissions, key rotation evidence, and object/search delete behavior in the external environment.
- Minimum artifact contents:
  - Secret manager/KMS metadata with no secret values, provider scope, key rotation evidence, and least-privilege policy.
  - External delete executor identity, object/search delete result, and audit trail.
  - Permission review or red-team proof with no credentials in artifacts.
- Reviewer routing:
  - Platform and Quality
  - PM / Release Coordination

## Release Gate Handoff

After owners upload the real evidence objects, run:

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```

Do not use local-only artifacts, demo artifacts, localhost URLs, `file://`, `local://`, or `artifact://staging-local` as production evidence.
