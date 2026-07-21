# Handoff: T-603 Personal Research Stabilization

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Platform and Quality; Research and AI Workflows; Product and UI; Governance, Security, and Compliance
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared integration worktree; final implementation changes are ready for commit
- Artifact classification: local-only
- Risk level: high

## Objective

Restore a trustworthy personal research loop after the 2026-07-21 runtime audit found report-state drift, misleading data-health counts, slow latest-analysis reads, mixed daily status semantics, and telemetry polluted by automation. Preserve existing URLs, local-only research boundaries, and paper-only feedback behavior.

## Scope

- In scope: restore-verified PostgreSQL backups, multi-store report reconciliation, typed/lazy data-health reads, materialized latest-analysis reads, split daily execution/content status, origin-segmented usage metrics, bounded five-company report recovery, primary promotion, runtime probes, roadmap and handoff evidence.
- Out of scope: full 11,702-report registry reconstruction, deletion of raw reports or OpenSearch, live broker integration, automatic orders, report-to-fact/training promotion, non-local production evidence, and fabricated longitudinal results.

## Background

T-602 reduced the PostgreSQL relation footprint from about 42 GiB to about 16 GiB. A subsequent live audit found that the historical report completion artifact no longer matched the active PostgreSQL registry: raw files and filtered OpenSearch projections remained while the workflow registry was empty. The recovery path therefore required a collection-aware backup, a disposable clone pilot, and a bounded insert-only primary promotion.

## Problem Statement

The system needed a current-state source-of-truth contract before any recovery write. It also needed to distinguish infrastructure execution health from research-content readiness and to keep scheduled/acceptance traffic out of the product-use KPI.

## Expected Deliverables

- A restore-verified local backup with research collection counts and deterministic ID samples.
- A read-only multi-store reconciliation and explicit recovery boundary.
- Fast materialized latest-analysis reads and separate daily execution/content status.
- Origin-aware usage metrics with a UI-only product KPI.
- A clone-first, idempotent five-company recovery and an insert-only primary slice.
- A final local runtime pass, schedule audit, full CI, roadmap update, and complete handoffs.

## Current State

- Completed: T-604 through T-612 implementation and integration; PostgreSQL recovery backup; clone double-run; primary promotion; controlled daily run; final schedule audit; full local quality gates.
- In progress: none in T-603.
- Not started: T-613 full-registry identity reconciliation and recovery decision package.
- Blocked: non-local organizational release remains intentionally blocked by external evidence requirements; this is outside the local product route.

## Current Findings

- Final primary PostgreSQL counts are `records=32319`, `audit_log=35385`, `market_data_bars=28365474`.
- Final research counts are `research_reports=15`, `research_documents=15`, citation evidence `112`, `structured_research_reports=15`, `report_viewpoints=15`, and `report_forecasts=3`.
- The preserved raw archive contains 11,702 eligible report files and filtered OpenSearch contains 11,702 `research_report` projections. The post-recovery identity coverage is `15 / 11702 = 0.001282`; the reconciliation remains `drift_detected` and explicitly forbids automatic full recovery.
- The controlled daily run has `execution_status=passed`, `content_status=ready`, zero failures, five companies with direct report evidence, and a maximum latency of 69.75 ms against a 2-second gate.
- The scheduler audit passed all 27 gates; `ai-quant-daily-update.timer` is enabled and active. The application health endpoint reports PostgreSQL, S3-compatible object storage, and OpenSearch backends.
- Five-company intelligence remains honest: each company has three structured reports and three viewpoints, completeness `0.8462`, and missing official `financial_snapshot` and `disclosure_events`; `ready_count=0` is not treated as a failure or hidden.

## Proposed Work Plan

Status: completed for T-603; the remaining full-registry work is tracked separately as T-613.

1. Freeze the T-602 baseline and create a restore-verified backup.
2. Reconcile raw files, PostgreSQL, OpenSearch and object storage without mutation.
3. Fix data-health, latest-analysis, daily status and usage-origin semantics with focused regressions.
4. Recover a bounded watchlist slice in an isolated clone, promote only the reviewed slice, and rerun the local daily loop.
5. Re-run local quality, scheduler, health and handoff gates; preserve the full-registry drift as an explicit follow-up.

## Dependencies

- Docker Compose PostgreSQL, OpenSearch and S3-compatible services.
- Read-only access to the raw report archive and local backup directory.
- Local systemd user timer for the daily refresh.

## Blockers

- None for the completed T-603 local scope.
- T-613 remains a separate TODO because the current evidence cannot authorize an automatic 11,702-report recovery.

## Validation Plan

Completed checks:

- Clone run 1: 15 selected, 15 created, 112 evidence rows, 15/15 content hashes verified.
- Clone run 2: 15 selected, 0 created, 112 evidence rows, 15/15 content hashes verified.
- Primary promotion: one source, 15 reports, 15 documents, 112 evidence rows, one audit event; no update/delete operations.
- Final backup: `restore_verified=true`, source/restored table and research manifests equal, retained through 2026-07-28.
- `make local-ci PYTHON=.venv/bin/python`: 516 tests passed, Python compile passed, UI static check passed, security scan passed, Markdown links passed, handoff validation passed for 189 documents, and canonical document metadata passed.

## Files Touched

- `app/api.py`, `app/server.py`, `app/models.py`, `app/services.py`, `app/service_modules/data_health.py`, `app/service_modules/usage_metrics.py`: API origin propagation, materialized latest-analysis reads, typed/lazy health aggregation, and compatibility facades.
- `scripts/daily_data_update_pipeline.py`, `scripts/latest_analysis_run.py`, `scripts/personal_intelligence_refresh.py`, `scripts/audit_daily_update_schedule.py`: execution/content status and scheduled-origin propagation.
- `scripts/postgres_durable_backup.py`, `scripts/reconcile_research_report_state.py`, `scripts/recover_watchlist_research_reports.py`, `scripts/probe_research_report_clone_runtime.py`, `scripts/promote_research_report_clone_to_primary.py`: collection-aware backup, read-only reconciliation, clone proof/recovery, and bounded primary promotion.
- `scripts/migrate_sqlite_to_postgres.py`: preflight/merge/exact-replace safety gates.
- `tests/`: focused regressions for data health, usage origins, content identity, backups, reconciliation, clone runtime, recovery and migration safety; audit tests now use explicit roadmap fixtures so live DOING tasks are not hidden.
- `tasks/todo.md`, `README.md`, `docs/README.md`, `docs/api-contracts.md`, `docs/postgresql-migrations.md`, `docs/production-runbook.md`: roadmap, document index, operation and API boundary updates.

## Commands Run

```bash
make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
python3 scripts/check_doc_metadata.py
curl -fsS http://127.0.0.1:8000/api/health
systemctl --user is-enabled ai-quant-daily-update.timer
systemctl --user is-active ai-quant-daily-update.timer
```

Result:

- Passed: all commands above; the final health response reports `PostgreSQLStore`, S3-compatible object storage, and OpenSearch.
- Passed: clone and primary runtime evidence recorded under `artifacts/t611-executions/` and `artifacts/t612-primary-promotion-*.json`.
- Passed: final controlled daily run and 27-gate scheduler audit.
- Failed: none in the completed local scope.
- Not run: non-local staging/production release validation, intentionally outside this local-only plan.

## Evidence

- `data/local/backups/postgres/ai_quant-20260721T001909Z.manifest.json`: produced by `scripts/postgres_durable_backup.py`; local Docker PostgreSQL; sensitive database metadata and dump; retained through 2026-07-28; `restore_verified=true`; not eligible for non-local release.
- `artifacts/research-report-state-reconciliation-post-recovery.json`: produced by `scripts/reconcile_research_report_state.py`; read-only local inventory; records raw 11,702 versus PostgreSQL 15 and the four critical/high findings; no secrets; not a release gate.
- `artifacts/t611-executions/t611-clone-execution-1.json` and `t611-clone-execution-2.json`: clone-only local recovery proofs; report IDs/hashes and counts only; no broker access; not eligible for non-local release.
- `artifacts/t612-primary-promotion-result.json`: local insert-only promotion result with masked DSNs, slice hash and audit event; sensitive database evidence; not eligible for non-local release.
- `artifacts/daily-update-local/runs/t612-post-promotion-20260721T001207Z/`: controlled local daily and personal-intelligence outputs; no fabricated historical window; not eligible for non-local release.
- `artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json`: generated 2026-07-21T00:32:15Z; local systemd timer evidence; no secrets; not eligible for non-local release.

## Decisions

- Treat PostgreSQL as the authoritative workflow registry after recovery; treat raw files as the authoritative source archive and OpenSearch as a rebuildable projection.
- Use clone-first, insert-only, idempotent recovery. No automatic full-registry write is authorized by the current reconciliation.
- Keep research reports in opinion/reference scope only; they do not enter fact, training, broker, or live execution paths.
- Preserve legacy API fields while adding execution/content status and origin metadata.
- Keep `SystemService` as a compatibility facade and move new health/telemetry behavior into domain modules.

## Risks and Open Questions

- T-613 must determine whether the 11,702 raw files can be mapped to a trustworthy historical registry; current 15-row identity coverage is not historical coverage.
- Official company facts remain incomplete for the five-company watchlist, so `ready_count=0` is expected until disclosure sources are ingested and reviewed.
- The retained backup contains sensitive local database content and must not be copied to a non-local release channel.
- The 17 M6-M9 external evidence tasks remain separate `BLOCKED` operational work and are not implied complete by local CI.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests and repository checks completed
- [x] Docs/contracts and roadmap updated
- [x] Cross-group handoffs updated or delegated with final evidence

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No. Data-health and usage-origin behavior moved into `app/service_modules/`; research content-hash verification extends an existing compatibility path.
- Domain placement: `data_health.py` owns typed/lazy aggregation and `usage_metrics.py` owns origin normalization/aggregation; `SystemService` retains thin facade methods and store plumbing.
- Focused regression: `tests.test_data_health`, `tests.test_usage_metrics`, latest-analysis regressions, and the full 516-test suite pass; audit tests explicitly protect active roadmap semantics.
- Contract/boundary changes: additive API metadata and content-identity validation only; no URL removal, broker integration, automatic order execution, or fact/training promotion.

## Next Steps

1. Open T-613 with Data and Evidence ownership and produce a dry-run identity/content-hash manifest for all 11,702 raw reports.
2. Continue daily timer monitoring and collect official company profile/disclosure evidence without manufacturing readiness.
3. Keep the final backup and clone/promotion artifacts under local retention policy; do not delete raw or OpenSearch inputs.

## Next Recommended Action

Start T-613 with a read-only, identity-level manifest and collision report; require a fresh clone double-run and collection-aware backup before any broader recovery write.
