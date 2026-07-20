# Handoff: T-601 Staging Idempotency And Capacity Classes

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination; Governance, Security, and Compliance
- Last updated: 2026-07-18
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Make the local PostgreSQL staging acceptance repeatable and separate interactive latency protection from explicitly identified external synchronization batch work.

## Scope

- In scope: demo market-data seed idempotency, append-only PostgreSQL audit persistence performance, staging capacity threshold mapping, local stack parameters, focused regression, runbook, and real local verification.
- Out of scope: database cleanup, market-data schema changes, broker connectivity, automatic execution, and non-local release claims.

## Background

The current-code Compose audit exposed a duplicate demo market-data conflict after a prior seed. The same run also showed that large external graph/vector synchronization calls were evaluated against the global interactive threshold.

## Problem Statement

`seed_demo_full_flow` checked the in-memory market-data mapping even when PostgreSQL used direct typed-table queries. Capacity acceptance also lacked a distinct threshold for bounded, explicitly listed external synchronization endpoints.

## Expected Deliverables

- Repeated demo seed uses the existing backend-aware market-data existence helper.
- Separate batch and acceptance-setup thresholds apply only to named endpoint classes.
- Interactive and simulated-execution thresholds remain independently enforced.
- Focused and real local staging verification is recorded.

## Current State

- Completed: implementation, focused regressions, real Compose acceptance, full local readiness drills, backup/restore, and PM status reconciliation.
- In progress: none.
- Not started: none.
- Blocked: none.

## Current Findings

- The PostgreSQL instance contained about 28.4 million typed market-data bars when the defect was reproduced.
- The duplicate was `md_demo_us_2026_05_14_eod`; the backend-aware existence helper already queried the typed table correctly.
- External graph/vector synchronization took materially longer than interactive requests on this local dataset.

## Proposed Work Plan

1. Add focused regressions for backend-aware seed idempotency and exact threshold mapping.
2. Rerun the real local staging acceptance against the current Compose data.
3. Record remaining breaches honestly and close only if the current-code acceptance passes.

## Validation Plan

- Run focused system tests for demo and staging acceptance.
- Run Python and Bash syntax checks.
- Run `bash scripts/local_production_stack.sh start` or equivalent current-stack acceptance with the documented thresholds.
- Run final local CI and handoff validation through T-594/T-596 integration.

## Dependencies

- Existing PostgreSQL typed market-data query path.
- Existing readiness capacity-baseline API.
- Local Compose services started during the PM audit.

## Blockers

- None.

## Files Touched

- `app/services.py`: demo seed now calls the existing backend-aware existence helper.
- `app/store.py`: PostgreSQL commits hash and persist only appended audit events while retaining full reconciliation after list replacement or shrinkage; graph sync audits are scoped to their `alert_notifications` write collection.
- `scripts/staging_acceptance.py`: adds an explicit batch threshold for five named synchronization endpoints.
- `scripts/local_staging_stack.sh`: passes the batch threshold.
- `scripts/local_staging_stack.sh`: also passes the configured acceptance timeout to the vision-gate workflow so large PostgreSQL writes do not fall back to 10 seconds.
- `scripts/local_production_stack.sh`: defines the local personal-production batch default.
- `scripts/local_backup_restore_drill.py`: replaces the unsafe 180-second fixed limit with a configurable 30-minute default and in-container timeout termination.
- `tests/test_system.py`: focused idempotency, threshold mapping, and stack-contract regressions.
- `docs/production-runbook.md`: documents the latency classes and their boundaries.
- `tasks/todo.md`: records T-601 and acceptance scope.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_graph_quality -v
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_staging_acceptance_runs_against_http_server_and_records_readiness -v
.venv/bin/python scripts/local_backup_restore_drill.py --artifact-prefix artifact://staging-local --record-readiness-url http://127.0.0.1:8000 --timeout-seconds 1800
.venv/bin/python scripts/staging_governance_acceptance.py http://127.0.0.1:8000 --artifact-prefix artifact://staging-local --record-readiness
.venv/bin/python scripts/staging_security_acceptance.py http://127.0.0.1:8000 --artifact-prefix artifact://staging-local --secret-manager-provider local-development-metadata-only
.venv/bin/python scripts/staging_otel_acceptance.py http://127.0.0.1:8000 --otel-endpoint http://127.0.0.1:4318/v1/logs --artifact-prefix artifact://staging-local --record-readiness
.venv/bin/python scripts/staging_graph_vector_acceptance.py http://127.0.0.1:8000 --neo4j-url http://127.0.0.1:7474/db/neo4j/tx/commit --qdrant-url http://127.0.0.1:6333
.venv/bin/python scripts/staging_lineage_registry_acceptance.py http://127.0.0.1:8000 --openlineage-target http://openlineage:5000/openlineage --mlflow-target http://mlflow:5000/mlflow --openlineage-health-url http://127.0.0.1:5001 --mlflow-health-url http://127.0.0.1:5002 --artifact-prefix artifact://staging-local
.venv/bin/python scripts/staging_vision_gate_acceptance.py http://127.0.0.1:8000 --artifact-prefix artifact://staging-local --timeout 120 --record-launch-checklist
AI_QUANT_LOCAL_PRODUCTION_SKIP_AI_ACCEPTANCE=true bash scripts/local_production_stack.sh audit
```

Result:

- Passed: graph focused 41/41; idempotency, PostgreSQL append-only audit, dirty-scope, and staging threshold regressions; staging acceptance 18/18 with zero capacity breach; governance, security, OTel, graph/vector, lineage/registry, and vision-gate drills; 42GB PostgreSQL backup/restore; final local production audit.
- Failed then fixed: duplicate demo market data; global audit rehash latency; repeated graph expansion; unmapped graph dirty collection; fixed 180-second backup timeout; vision-gate 10-second wrapper timeout.
- Not run: final repository-wide local CI, owned by T-594/T-596 integration.

## Decisions

- Reuse `_market_data_point_exists` rather than add a PostgreSQL-specific seed path.
- Keep the global interactive threshold unchanged.
- Apply the 60-second batch threshold only to Neo4j, Qdrant, OTel, OpenLineage, and MLflow synchronization endpoints; apply the 20-second setup threshold only to demo, DAG, model, and lineage acceptance setup.

## Risks and Open Questions

- Batch classification must not expand silently to interactive endpoints.
- The 60-second graph/vector batch allowance is local capacity policy; interactive search and simulated execution remain protected by 5 seconds.

## Artifacts

- `artifacts/local-production-audit.json`: local-only audit; `passed=true`, `ready_for_launch=true`, and not acceptable for non-local release.

## Evidence

- Final staging acceptance: 18/18, capacity breach 0; local runtime evidence only.
- Backup/restore: 1,371,596 ms; source/restored `records=31,991`, `audit_log=35,130`; temporary database and dump removed.
- Final local production audit: vision `ready`, package `ready`, nine required evidence rows, zero failures, one external-validation warning.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Handoff Checklist

- [x] Task brief and owner/reviewer groups recorded
- [x] Exact batch endpoint scope recorded
- [x] Real current-code staging acceptance passed
- [x] PM roadmap status reconciled

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; one existing seed guard now uses the already-established backend-aware existence helper.
- Domain placement: no new domain module is warranted for a one-line compatibility correction inside the existing facade seed workflow.
- Focused regression: direct-query existence behavior and repeated demo-flow acceptance, followed by the golden/full local gate.
- Contract/boundary changes: no API or storage schema change; capacity reporting adds a CLI/environment threshold class; UI and paper-only/no-broker boundaries are unchanged.

## Next Steps

1. Run T-594/T-596 final full local CI and milestone-candidate gate.
2. Keep the 17 non-local evidence tasks blocked until real external artifacts exist.
3. Rebaseline the batch threshold only from recorded production-like measurements.

## Next Recommended Action

Treat any remaining interactive latency breach as a performance defect rather than adding it to the batch exception list.
