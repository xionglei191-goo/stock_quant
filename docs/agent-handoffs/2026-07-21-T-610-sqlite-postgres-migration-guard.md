# Handoff: T-610 SQLite To PostgreSQL Migration Guard

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t610_migration_guard`
- Branch/worktree: `main` at `0463630`; shared T-603 worktree, T-610 changes uncommitted
- Artifact classification: local-only

## Objective

Prevent a small or incomplete SQLite snapshot from silently deleting richer PostgreSQL records or audit history. Keep a guarded path for intentional exact replacement without changing global store commit semantics.

## Scope

- In scope: migration preflight, insert-only merge, exact-replacement loss acknowledgement, restore-verified backup validation, DSN redaction, focused fake-PostgreSQL regressions, and CLI help.
- Out of scope: live database migration, data recovery, backup creation, schema changes, `PostgreSQLStore.commit()` changes, service/API/UI behavior, raw reports, OpenSearch, object storage, brokers, and automatic orders.
- Risk level: high because the legacy entry point could delete target-only workflow state and audit events.
- Related tasks: T-603, T-604, T-609, T-610.

## Background

The prior script required `--replace`, copied every registered SQLite collection into the loaded PostgreSQL store, replaced the audit list, and called a full `PostgreSQLStore.commit()`. That commit can delete loaded target keys that are absent from the SQLite snapshot and can replace the audit chain.

T-604 found a current PostgreSQL report-registry gap while raw reports and a stale OpenSearch projection remain. The migration script is therefore a plausible loss path worth closing, but there is no event-level evidence establishing it as the root cause of the current registry gap.

## Problem Statement

The migration entry point had no source/target preflight, no merge mode, and no backup or acknowledgement gate before full replacement. An operator could therefore supply an incomplete SQLite snapshot and remove target-only registered records or audit events without seeing the prospective loss.

## Expected Deliverables

- Per-collection source/target preflight with prospective delete and overwrite counts.
- Read-only default and insert-only merge preserving target-only records, target conflicts, and audit events.
- Evidence-backed exact-replacement gate with a count-bound confirmation token and validated backup manifest.
- Focused tests proving the guard behavior without touching live PostgreSQL.

## Current State

- Completed: implementation, focused tests, legacy compatibility regression, full Python compile, CLI help, security scan, diff check, and handoff.
- In progress: parent T-603 integration and shared full-suite verification.
- Not started: live migration; intentionally excluded.
- Blocked: none for this code guard.

## Current Findings

- The legacy `--replace` path could delete target-only registered JSON records and audit events when PostgreSQL contained more state than SQLite.
- The default CLI now performs read-only preflight and emits all registered collection counts, audit counts, prospective loss, storage boundary, and an exact confirmation token.
- A missing SQLite path is rejected before PostgreSQL is connected; a path typo can no longer create an empty SQLite database and masquerade as a valid migration source.
- `merge` inserts only missing IDs. Target conflicts win, target-only IDs remain, and source audit events append only when their IDs are absent.
- Exact replacement validates actual target table totals for `ai_quant.records`, `ai_quant.audit_log`, and typed `market_data_bars` before mutation.
- Typed `market_data_bars` remain merge-only under existing store semantics; exact replacement does not delete target-only market bars.

## Safe CLI Examples

Read-only preflight, recommended before every migration:

```bash
python3 scripts/migrate_sqlite_to_postgres.py \
  ./data/state.db "$AI_QUANT_POSTGRES_DSN" \
  > /tmp/sqlite-postgres-preflight.json
```

Insert-only merge; existing target values and target-only audit events win:

```bash
python3 scripts/migrate_sqlite_to_postgres.py \
  ./data/state.db "$AI_QUANT_POSTGRES_DSN" \
  --mode merge
```

Intentional exact replacement of a populated target requires the exact token from the immediately reviewed preflight and a current restore-verified backup:

```bash
python3 scripts/migrate_sqlite_to_postgres.py \
  ./data/state.db "$AI_QUANT_POSTGRES_DSN" \
  --mode exact-replace \
  --confirm-exact-replace 'EXACT_REPLACE:DELETE_RECORDS=<n>:OVERWRITE_RECORDS=<n>:DELETE_AUDIT=<n>:OVERWRITE_AUDIT=<n>' \
  --backup-manifest data/local/backups/postgres/<backup>.manifest.json
```

Do not reuse a confirmation token after either database changes. Rerun preflight so its loss counts match the current source and target.

## Proposed Work Plan

1. Make read-only source/target preflight the default and expose loss counts without leaking DSN credentials.
2. Add an insert-only, target-wins merge path that suppresses full-store deletion reconciliation.
3. Gate exact replacement on a count-bound confirmation token and restore-verified backup evidence whenever loss is possible.
4. Prove each path with fake-store tests and leave live PostgreSQL untouched.

## Validation Plan

- Fake PostgreSQL tests cover missing-source rejection, default immutability, per-collection counts, URL DSN credential/query redaction, insert-only merge, target-wins conflicts, audit preservation, exact-replace refusal, backup count coverage, dump hash verification, and successful intentional replacement.
- Parent T-603 runs the full local CI after concurrent work settles.

## Dependencies

- Existing `SQLiteStore`, `PostgreSQLStore`, and restore-verified manifest contract from `scripts/postgres_durable_backup.py`.
- A readable retained dump is required only when exact replacement has prospective loss.

## Blockers

- None. The full shared-suite result remains owned by the parent integration task.

## Files Touched

- `scripts/migrate_sqlite_to_postgres.py`: added preflight/merge/exact modes, loss token, backup validation, full DSN redaction, and direct CLI execution bootstrap.
- `tests/test_sqlite_postgres_migration_guard.py`: added five focused fake-store safety regressions.
- `tests/test_system.py`: changed only the legacy migration test's default-call assertion from required failure to successful read-only preflight; unrelated hunks belong to concurrent tasks.
- `docs/agent-handoffs/2026-07-21-T-610-sqlite-postgres-migration-guard.md`: records behavior, evidence, risks, and operator examples.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_sqlite_postgres_migration_guard -v
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_sqlite_to_postgres_migration_rewrites_target_with_counts -v
.venv/bin/python -m py_compile app/*.py tests/*.py scripts/*.py
.venv/bin/python scripts/migrate_sqlite_to_postgres.py --help
.venv/bin/python scripts/security_check.py .
git diff --check -- scripts/migrate_sqlite_to_postgres.py tests/test_sqlite_postgres_migration_guard.py tests/test_system.py
```

Result:

- Passed: 5/5 focused guard tests.
- Passed: 1/1 legacy migration compatibility regression.
- Passed: full Python compile.
- Passed: CLI help.
- Passed: security scan, zero findings across 509 checked files.
- Passed: diff whitespace check.
- Failed: none.
- Not run: live PostgreSQL migration, intentionally prohibited; full unit suite/local CI, reserved for parent integration because the shared worktree has concurrent changes.

## Evidence

- Focused unittest output from the commands above: generated 2026-07-21 in the local development worktree; owner Platform and Quality; no secrets or database content; local-only and not eligible for non-local release gates.
- No persistent migration or backup artifact was generated. Backup tests use temporary files and a fake PostgreSQL adapter.

## Decisions

- Default to read-only preflight. Explicit `--mode merge` is the normal write path.
- Merge is insert-only and target-wins on ID conflicts. Silent source-overwrite of existing target state is not considered non-destructive.
- Keep `--replace` only as a compatibility alias for guarded `exact-replace`; it no longer bypasses safety gates.
- Require the confirmation token to encode exact prospective delete/overwrite counts so acknowledgement is tied to the reviewed preflight.
- When prospective loss exists, require `status=passed`, `restore_verified=true`, equal source/restored counts, backup counts covering current target totals, existing dump, matching SHA-256/size, non-expired retention when provided, and equal source/restored database manifests when provided.
- Do not change `PostgreSQLStore.commit()`. The migration script uses dirty-collection commits for merge so deletion reconciliation is suppressed.

## Risks and Open Questions

- This closes a plausible prevention gap; it does not prove the migration script caused the current research-report registry loss.
- Conflict resolution is intentionally target-wins in merge mode. Operators needing source-wins behavior must use reviewed exact replacement or implement a separately reviewed per-record conflict workflow.
- The confirmation token is count-bound, not snapshot-bound. The backup gate and immediate preflight review remain required; do not reuse tokens after source or target changes.
- Direct table counts can be expensive on very large typed market-data tables. Safety takes precedence on the destructive path; the normal preflight also reports this exact count.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [ ] `tasks/todo.md` status updated if roadmap state changed; parent owns shared roadmap integration

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No; `app/services.py` and `SystemService` were not touched.
- Domain placement: Migration safety remains in the one-shot platform script; no domain service module is needed.
- Focused regression: Five fake-store tests plus the existing migration compatibility test protect storage behavior.
- Contract/boundary changes: CLI semantics are additive except that unsafe `--replace` now requires gates when loss is possible. API, UI, storage schema, paper-only, and no-broker boundaries are unchanged.

## Storage Boundary Review

- `PostgreSQLStore.commit()` was not modified or weakened.
- Preflight performs only `SELECT` operations after normal store initialization.
- Merge marks only changed collections dirty, uses upsert/append semantics, and emits no `DELETE` in regression coverage.
- Exact replacement retains existing typed-market-data behavior: registered JSON record collections and audit can be replaced, while target-only typed bars are preserved.
- No live database, raw report, search index, or object-store mutation was run for T-610.

## Next Steps

1. Parent agent integrates the T-610 roadmap/docs references without overwriting concurrent T-603 changes.
2. Run full `make local-ci` after all delegated changes settle.
3. Before any real SQLite-to-PostgreSQL operation, retain the preflight JSON and backup manifest as local-only operator evidence.

## Next Recommended Action

Adopt `--mode merge` as the standard migration command and treat exact replacement as an exceptional, backup-gated operation reviewed from a fresh preflight.
