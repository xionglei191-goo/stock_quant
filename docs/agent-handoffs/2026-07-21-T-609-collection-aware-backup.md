# Handoff: T-609 Collection-Aware PostgreSQL Backup

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t612_primary_promotion`
- Branch/worktree: `main`, shared dirty worktree; no commit created
- Related tasks: T-603, T-604, T-608, T-609, T-611, T-612
- Artifact classification: local-only

## Objective

Make PostgreSQL backup acceptance collection-aware, then produce a restore-verified final local backup that protects the primary database after the bounded research-report promotion and controlled daily refresh.

## Scope

- In scope: source/restored aggregate counts, six research-state collection counts, bounded deterministic report-ID samples, exact restore comparison, final primary backup evidence, and current-state reconciliation.
- Out of scope: reconstructing the full 11,702-report history, deleting raw reports or search projections, non-local release evidence, broker integration, live orders, and automatic trading.

## Background

Earlier backups proved dump readability through three aggregate table counts but could not show whether research reports, linked documents, citation evidence, structured reports, viewpoints, or forecasts survived restoration. T-609 added those collection gates. T-611 and T-612 then used the contract through clone validation, bounded primary promotion, and the final rollback snapshot.

## Problem Statement

A readable dump can still preserve an incomplete research state. Closure therefore required exact source/restored collection equality and a fresh final backup after all authorized downstream writes, while explicitly avoiding any claim that the current 15-report slice represents the historical 11,702-report registry.

## Expected Deliverables

- Collection-aware source and restored database manifests with exact equality enforcement.
- Compatibility with the existing aggregate count fields and T-604 reconciliation.
- A restore-verified final primary dump with recorded hash, retention, aggregate counts, and all six research counts.
- A post-recovery reconciliation that distinguishes protected current state from unrecovered historical coverage.

## Current State

- Completed: implementation, focused regressions, documentation, clone and promotion use, final primary dump/restore, independent dump hash check, and post-recovery reconciliation.
- In progress: none.
- Not started: full 11,702-report primary recovery; this is intentionally outside T-609.
- Blocked: none for T-609. Historical completeness remains unproven and requires a separately authorized recovery plan.

## Current Findings

- Final manifest `ai_quant-20260721T001909Z.manifest.json` has `status=passed` and `restore_verified=true`; dump size is 837,739,289 bytes.
- Source and restored aggregates match exactly at `records=32,319`, `audit_log=35,385`, and `market_data_bars=28,365,474`.
- Source and restored research counts match exactly at `15 research_reports / 15 research_documents / 112 citation evidence / 15 structured reports / 15 viewpoints / 3 forecasts`.
- Dump SHA-256 is `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`; the manifest retains it through `2026-07-28T00:19:09.031522+00:00`.
- Post-recovery reconciliation still reports `drift_detected`: raw storage and the research-report OpenSearch projection each retain 11,702 entries while primary PostgreSQL intentionally contains only the reviewed 15-report slice.
- The final backup protects the current point-in-time state only. It is not proof that the full historical registry was recovered.

## Proposed Work Plan

1. Completed: add the six research collection counts and bounded safe ID samples to source/restored manifests.
2. Completed: require exact manifest equality before `restore_verified=true`.
3. Completed: produce and restore-check the final primary dump after promotion and the controlled daily refresh.
4. Completed: rerun read-only reconciliation against the final backup and preserve the historical-coverage warning.

## Validation Plan

- Validate focused backup behavior and T-604 compatibility with mocked tests.
- Verify the real dump by restoring to a temporary database and comparing complete source/restored manifests.
- Independently hash the retained dump and inspect final collection counts.
- Run post-recovery reconciliation and repository-level CI after the operational sequence settles.

## Dependencies

- Local Docker Compose PostgreSQL and sufficient temporary restore capacity.
- T-604 reconciliation definitions for research-linked documents and citation evidence.
- Completed T-611 clone proof and T-612 bounded primary promotion.

## Blockers

- None for this task.
- The remaining 11,687 raw/search registry entries are not a T-609 backup blocker, but they remain a separate product/data completeness risk.

## Files Touched

- `scripts/postgres_durable_backup.py`: added collection-aware source/restored manifests and exact restore gating.
- `tests/test_postgres_durable_backup.py`: covers equality, mismatch, cleanup, safe ID samples, identifiers, and T-604 compatibility.
- `docs/postgresql-migrations.md`: documents the current-state versus historical-state backup boundary.
- `docs/agent-handoffs/2026-07-21-T-609-collection-aware-backup.md`: reconciled implementation notes with the completed final operation.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_postgres_durable_backup -v
.venv/bin/python -m unittest \
  tests.test_postgres_durable_backup \
  tests.test_reconcile_research_report_state -v

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant \
  --output-dir data/local/backups/postgres

sha256sum data/local/backups/postgres/ai_quant-20260721T001909Z.dump
make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: 5/5 focused T-609 tests; 13/13 combined T-609/T-604 tests; final dump and temporary restore comparison; independent SHA-256 check; post-recovery reconciliation completed; final repository CI passed 516 tests plus UI, security, link, handoff, and document metadata gates.
- Failed: none in the final accepted run.
- Not run: non-local restore or release validation; all evidence is local-only.

## Evidence

- `data/local/backups/postgres/ai_quant-20260721T001909Z.dump` and `.manifest.json`: produced by `scripts/postgres_durable_backup.py` at `2026-07-21T00:19:09.031522+00:00`; local Docker Compose PostgreSQL; owner Platform and Quality; sensitive; restore-verified; retained through 2026-07-28; local-only and unacceptable for non-local release. Dump SHA-256: `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`.
- `artifacts/research-report-state-reconciliation-post-recovery.json`: produced by the read-only reconciliation workflow at `2026-07-21T00:29:47.992525+00:00`; local primary/raw/search/object state; owner Data and Evidence with Platform review; contains operational paths/counts but no credentials or report bodies; local-only and unacceptable for non-local release.

## Decisions

- A backup is accepted only when complete source/restored database manifests match, not merely when `pg_restore` exits successfully.
- Current-state rollback evidence and historical-coverage evidence remain separate claims. The manifest explicitly states that bounded samples do not prove every unsampled identity.
- Raw reports and the current OpenSearch index remain preserved as forensic/recovery inputs; T-609 authorizes no deletion or search-source promotion.
- The final snapshot was taken after downstream structured research writes, so it supersedes earlier pre-promotion and immediate post-promotion backups for current rollback purposes without invalidating their audit-chain role.

## Risks and Open Questions

- PostgreSQL contains the intentionally reviewed 15-report slice, not the full 11,702-report registry. Global reconciliation therefore remains drifted and must not be described as clean.
- The dump is sensitive, ignored, machine-local evidence with a finite retention window. It is not external staging or production evidence.
- Count plus bounded-sample equality is stronger than aggregate totals but remains point-in-time evidence, not a cryptographic inventory of every row.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated by the parent integration owner

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No; `app/services.py` and application service behavior were not changed.
- Domain placement: Backup and reconciliation behavior remains in focused platform/data scripts.
- Focused regression: `tests/test_postgres_durable_backup.py` plus T-604 compatibility tests protect the manifest and restore gate.
- Contract/boundary changes: Additive local backup-manifest fields only; no API schema, storage schema, UI, paper-only, no-broker, or no-live-trading boundary changed.

## Next Steps

1. Retain the final dump and evidence chain through the recorded retention window and monitor scheduled backup health.
2. Scope any broader 11,702-report recovery as a separate clone-first, review-gated task; do not infer authorization from this backup.

## Next Recommended Action

Treat `ai_quant-20260721T001909Z` as the current local rollback point while keeping the unresolved full-registry drift visible in PM reporting.
