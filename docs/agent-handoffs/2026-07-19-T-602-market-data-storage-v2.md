# Handoff: T-602 Market Data Storage V2

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-19
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Reduce the 42GiB typed market-data relation to at most 22GiB without changing market-data API semantics, numeric precision, governance, or paper-only boundaries.

## Scope

- In scope: compact schema, immutable rights-policy deduplication, payload compatibility, shared writers, resumable migration, durable backup, clone rehearsal, primary cutover, acceptance, and local-only storage evidence.
- Out of scope: `NUMERIC` conversion, unrelated tables, UI redesign, brokers, real orders, and non-local release claims.

## Background

The original typed market-data table repeated the complete JSON payload and rights snapshot on every row, while a security/date index duplicated the primary-key access path. At 28.36 million rows this made the PostgreSQL relation grow to about 42GiB.

## Problem Statement

The storage layout needed to be compacted without changing the public `MarketDataPoint`, HTTP, governance, or simulated-only contracts, and without deleting the old relation before a real restore was verified.

## Expected Deliverables

- Compact schema and shared writer/reader implementation.
- Resumable migration with exact parity validation, rollback, and guarded cleanup.
- Restore-verified backup, clone rehearsal, primary evidence, tests, and operator documentation.

## Current State

- Completed: implementation, restore-verified backup, full clone rehearsal, 28,363,995-row primary migration, exact validation, atomic cutover, runtime acceptance, legacy cleanup, and timer restoration.
- In progress: none.
- Not started: none.
- Blocked: none.

## Results

- Relation size fell from 45,041,180,672 to 16,853,549,056 bytes: 28,187,631,616 bytes saved, or 62.6% (about 42GiB to 16GiB).
- Full validation matched 28,363,995 source and compact rows with zero missing keys, scalar/rights mismatches, or reconstructed payload mismatches.
- Copy took 2,803.453 seconds; validation took 820.389 seconds; cutover took 0.107 seconds.
- All five bounded query scenarios passed. Security-history warm median improved from 0.471ms to 0.432ms; other medians remained below 0.1ms.
- PostgreSQLStore, SystemService, `/api/health`, `/api/market-data`, schema migration state, compact write/rollback, and storage audit passed after cutover.
- `ai-quant-daily-update.timer` was restored to enabled/active; next run remained scheduled for 2026-07-20 07:08 CST.

## Current Findings

- The two immutable rights policies account for only 49,152 bytes; the dominant reduction came from removing repeated payload/rights JSONB.
- The compact table has four supporting indexes plus its primary key; the removed security/date index was not needed by the measured query plans.
- The final API view reconstructs the same payload shape and rights tag expected by existing callers.

## Proposed Work Plan

1. Create a durable custom-format backup and verify a temporary full restore.
2. Prepare a shadow compact table, copy in resumable keyset batches, repair historical numeric representation overrides, and validate every key/scalar/rights/payload field.
3. Compare bounded query plans, cut over atomically, run API/storage acceptance, and only then delete the legacy relation under a verified backup manifest.

## Validation Plan

- Focused compact-storage unit tests and fake-PostgreSQL contract tests.
- Full clone and primary row-parity/size validation, five query-plan benchmarks, storage audit, HTTP smoke, compile, full unit suite, UI/security/doc/handoff gates.

## Dependencies

- PostgreSQL container and `psycopg` project extra.
- Existing local schema, timer unit, and ignored backup directory.

## Blockers

- None for the local migration. Non-local release remains out of scope and requires separate external staging evidence.

## Files Touched

- `app/market_data_storage.py`: canonical payload mask, exact reconstruction, immutable rights-policy hash, and compact upsert.
- `app/store.py`: compact writes and policy-backed reads.
- `scripts/import_tdx_vipdoc_postgres.py`, `scripts/import_ashare_eod_baostock.py`, `scripts/import_us_eod_yahoo_chart.py`: shared compact writer.
- `docs/postgresql-schema.sql`: compact fresh-install table, rights-policy table, compatibility view, and reduced index set.
- `scripts/migrate_market_data_storage_v2.py`: resumable prepare/copy/repair/validate/cutover/rollback/cleanup workflow and backup-integrity gate.
- `scripts/postgres_durable_backup.py`: retained custom-format dump with actual restore/count verification.
- `scripts/benchmark_market_data_storage_v2.py`: legacy/compact plan and latency comparison.
- `scripts/market_data_storage_audit.py`: compact schema, index, plan, and API gate.
- `tests/test_market_data_storage_v2.py`, `tests/support.py`, `tests/test_system.py`: focused compact-storage regression coverage and fake-store compatibility.
- `docs/postgresql-migrations.md`, `docs/production-runbook.md`, `tasks/todo.md`: operator procedure and roadmap closure.

## Commands Run

```bash
.venv/bin/python scripts/postgres_durable_backup.py --output-dir data/local/backups/postgres --source-db ai_quant --retention-days 7 --timeout-seconds 3600
.venv/bin/python scripts/migrate_market_data_storage_v2.py <prepare|copy|repair|validate|cutover|cleanup> --run-id <run-id> ...
.venv/bin/python scripts/benchmark_market_data_storage_v2.py ...
.venv/bin/python scripts/market_data_storage_audit.py ...
.venv/bin/python -m unittest tests.test_market_data_storage_v2 tests.test_system.SystemServiceTests.test_market_data_storage_audit_requires_typed_only_runtime_storage
make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: focused 8 tests, temporary lifecycle, full clone rehearsal, primary parity/size/plan checks, HTTP smoke, post-cleanup storage audit, compile, and diff check.
- Failed then fixed: psycopg batch transaction lifecycle, date serialization, JSON reset literal, 6,173 historical JSON-number representations, and missing writer `created_at` default.
- Final `make local-ci PYTHON=.venv/bin/python`: 457/457 tests passed; UI static check, security scan, Markdown links, handoff validation, and canonical document metadata all passed.

## Decisions

- Keep `NUMERIC`; the measured saving came from removing duplicated row JSONB and one redundant security/date index.
- Preserve exact rights snapshots through immutable policy rows rather than mutable source-definition joins.
- Store only non-structured payload keys plus a presence mask. When historical JSON numeric representation differs from the typed value, retain only that exact key as a compact override.
- Cleanup requires exact run-ID confirmation plus an existing restore-verified dump whose SHA-256 still matches its manifest.

## Risks and Open Questions

- Atomic table rollback ended after accepted legacy cleanup. Until 2026-07-26, rollback requires restoring the retained dump and rerunning acceptance.
- Evidence is local-only, contains no authorization for non-local release, and does not alter the no-broker/no-auto-order boundary.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module decision: compact behavior lives in `app/market_data_storage.py`; the existing `SystemService` facade and public API were preserved.
- Focused regression: direct PostgreSQLStore/SystemService reads and HTTP `/api/market-data` smoke passed against the migrated primary.
- Contract/boundary changes: physical PostgreSQL schema changed; API schema, UI behavior, `NUMERIC` precision, and paper-only/no-broker boundaries did not.

## Evidence

- `data/local/backups/postgres/ai_quant-20260719T015529Z.manifest.json`: produced by `scripts/postgres_durable_backup.py`; 1,505,817,669-byte sensitive dump, SHA-256 `4ad529910bd3ba5f3f08beaf6ba13907aae0622f1d8d23f998692c860d4f3f6e`; restore/count verified; retained through 2026-07-26; local-only and invalid for non-local release.
- `artifacts/t602-rehearsal-*.json`: clone prepare/copy/repair/validate/cutover/benchmark/audit/cleanup evidence; local-only, no secret content, invalid for non-local release.
- `artifacts/t602-primary-*.json`: primary prepare/copy/validate/cutover/benchmark/HTTP/storage/cleanup evidence; local-only, no secret content, invalid for non-local release.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly recorded
- [x] Docs/contracts updated
- [x] `tasks/todo.md` roadmap status updated

## Next Steps

1. Retain the verified dump through 2026-07-26; do not delete it early.
2. Monitor the next scheduled daily update for compact-writer errors and relation growth.
3. Treat any non-local rollout as a separate change with external staging evidence.

## Next Recommended Action

Review the first scheduled daily-update result after 2026-07-20 07:08 CST; no additional migration action is required now.
