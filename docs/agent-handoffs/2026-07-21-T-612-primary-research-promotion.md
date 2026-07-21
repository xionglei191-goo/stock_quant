# Handoff: T-612 Primary Research-Report Slice Promotion

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared integration worktree; final implementation changes are ready for commit
- Artifact classification: local-only

## Objective

Provide a separate, default-read-only PostgreSQL-to-PostgreSQL promotion path for the exact research-report slice proven by the T-611 clone double run. The path must preserve the clone-only HTTP executor, refuse drift or unequal conflicts before mutation, and apply only insert-only primary changes in one transaction.

## Scope

- In scope: source/target database identity gates, restore-verified backup binding, primary-writer quiescence proof, deterministic plan and clone-run validation, bounded dependency discovery, reviewed primary insert-only promotion, audit event, exact post-commit verification, focused tests, runtime evidence, and this handoff.
- Out of scope: changing T-608/T-610 behavior, copying the 11,702-row full registry into primary, changing application services or schema, deleting/updating rows, writing OpenSearch/object storage, touching raw reports, real broker integration, and order execution.

## Background

T-611 rebuilds the raw registry in an isolated clone and executes the T-608 watchlist plan twice. The full registry scan is a clone-side implementation prerequisite, but only the plan-selected reports with verified documents and citation evidence are qualified for primary promotion. Reusing the clone-only HTTP executor against `:8000` or weakening T-610 exact replacement would bypass the isolation decision, so T-612 is an independent insert-only path.

## Problem Statement

A successful clone pilot alone does not establish that the current primary is stopped, backed up, unchanged since review, free of unequal ID conflicts, or able to receive only the qualified dependency slice atomically. A promotion tool must bind all of those facts to one confirmation token and recheck the target inside the write transaction.

## Expected Deliverables

- A three-mode CLI: `prove-quiescence`, default `preflight`, and explicitly confirmed `promote`.
- Strict validation of the canonical plan and both retained clone execution JSON files.
- Exact source/target binding to fresh collection-aware restored backups and same-cluster, distinct-database identities.
- An allowlisted source slice containing only required `sources`, selected `research_reports`, linked `documents`, and linked research-citation `evidence`.
- One serializable target transaction using `INSERT ... ON CONFLICT DO NOTHING`, with no `DELETE` or `UPDATE` path.
- Failure, tamper, conflict, idempotency, and default-immutability regressions.
- A restore-verified post-promotion primary backup before application/timer restart.

## Current State

- Completed: implementation and focused validation; retained clone run1/run2 evidence; restore-verified source and target backups; stopped-writer proof; exact preflight; reviewed insert-only promotion; bounded audit append; exact post-commit verification; immediate post-promotion backup; application/timer restart; controlled daily/product checks; final downstream backup; schedule audit; and full local CI.
- In progress: none.
- Not started: no T-612 closure work. Full 11,702-report recovery is a separate T-613 scope.
- Blocked: none.

## Current Findings

- The qualified slice is derived only from the deterministic plan IDs; the clone's other registry rows are never selected by the promotion query.
- Every selected report must be `text_indexed`, content-SHA-bound to its plan and linked document, carry the restricted local-reference rights tag, and have the exact citation evidence count in both clone runs and the clone database.
- Source and target must be different database OIDs on the same PostgreSQL system identifier. The source name must identify a clone/pilot/restore/test database and the target name must be exactly `ai_quant`.
- Both databases must report zero sessions other than the probe. The primary proof also binds stopped Docker writer identities, current counts, target backup SHA, and a 15-minute freshness window.
- A target row with the same identity and same payload/position is preserved; the same identity with any unequal value closes the gate.
- The post-clone source backup `ai_quant_t611_pilot_20260721-20260720T233925Z` is restore-verified at `records=43,941`, `audit_log=35,375`, `market_data_bars=28,365,189`; its research state is `11,702 reports / 15 documents / 112 citation evidence / 0 structured reports / 0 viewpoints / 0 forecasts`.
- The primary pre-backup `ai_quant-20260720T234936Z` is restore-verified at `records=32,115`, `audit_log=35,330`, `market_data_bars=28,365,474`; all six research-state counts are zero.
- Quiescence proof SHA-256 `167a1bcafe9df3b938b4bdf17d331d38958ceddd96f1e4f9b8f45ceee80baed5` records the primary app container as exited and zero other primary database sessions.
- Preflight found zero equal-existing rows and planned exactly `1 source / 15 reports / 15 documents / 112 citation evidence` inserts.
- Promotion completed with those exact insert counts and audit event `evt_t612_49ff6054059fe9e4f02e9d000bcc4df7`. Post-commit verification passed at `records=32,258`, `audit_log=35,331`, `market_data_bars=28,365,474`; research state is `15 reports / 15 documents / 112 citation evidence / 0 structured reports / 0 viewpoints / 0 forecasts`.
- The promoted slice SHA-256 is `d2c1b3253de2ddb816eba708f91cd9b3e39a41cf9e3f330513f745eabf8b6b5b` before and after commit.
- Immediate post-promotion backup `ai_quant-20260720T235934Z` passed restore verification at the exact post-commit counts; dump SHA-256 is `38eee70295a27f77bbce59c5252b42ef6e245d2761a23c5644d43249e7f3fadf`.
- After the application and timer restart, the controlled daily run passed with `execution_status=passed`, `content_status=ready`, direct report evidence for all five companies, and derived counts of `15 structured reports / 15 viewpoints / 3 forecasts`.
- Final downstream backup `ai_quant-20260721T001909Z` passed restore verification at `records=32,319`, `audit_log=35,385`, `market_data_bars=28,365,474`; research state is `15 reports / 15 documents / 112 citation evidence / 15 structured reports / 15 viewpoints / 3 forecasts`. Dump SHA-256 is `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`.
- The application is healthy and `ai-quant-daily-update.timer` is enabled/active. The final scheduler audit passed 27/27 gates and full local CI passed 516 tests plus all supporting gates.

## Proposed Work Plan

1. Completed: retain successful T-611 run1/run2 evidence and stop the clone application.
2. Completed: restore-verify the stopped post-clone source and quiescent primary pre-state backups.
3. Completed: generate the proof, preflight the exact slice, review the snapshot-bound confirmation, promote, and verify the committed primary rows/counts.
4. Completed: restore-verify the immediate post-promotion primary backup before restarting writers.
5. Completed: restart the app and timer, run controlled product checks, create the final downstream backup, and pass health, schedule, reconciliation, and full-CI gates.

## Validation Plan

- Run focused tests and Python compile for the new script/test.
- Run CLI help, whitespace check, security scan, and handoff validation.
- Parent integration completed full local CI after the shared work settled.
- Runtime execution preserved source/target backup manifests, quiescence proof, preflight, promotion result, immediate/final backups, daily output and schedule audit as ignored local-only artifacts.

## Dependencies

- Satisfied: passing T-611 clone run1 and run2 JSON artifacts with canonical plan SHA-256 `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d`.
- Satisfied: stopped clone database containing the proven selected rows.
- Satisfied: fresh T-609-style restore-verified backups for the post-clone source and pre-promotion primary.
- Satisfied: primary application/timer quiescence during promotion, followed by a verified restart; DSNs were supplied through environment variables and retained artifacts mask them.

## Blockers

- None.

## Files Touched

- `scripts/promote_research_report_clone_to_primary.py`: independent proof/preflight/promotion tool with backup, evidence, quiescence, transaction, audit, and verification gates.
- `tests/test_promote_research_report_clone_to_primary.py`: focused regressions for tamper refusal, source allowlisting, conflicts, idempotency, backup drift, proof integrity, transaction rollback, default immutability, and mutation-SQL boundaries.
- `docs/agent-handoffs/2026-07-21-T-612-primary-research-promotion.md`: implementation decisions, validation, operational handoff, and completed runtime evidence.

## Commands Run

```bash
.venv/bin/python -m py_compile \
  scripts/promote_research_report_clone_to_primary.py \
  tests/test_promote_research_report_clone_to_primary.py
.venv/bin/python -m unittest tests.test_promote_research_report_clone_to_primary -v
.venv/bin/python -m unittest \
  tests.test_recover_watchlist_research_reports \
  tests.test_probe_research_report_clone_runtime \
  tests.test_promote_research_report_clone_to_primary -v
.venv/bin/python scripts/promote_research_report_clone_to_primary.py --help
git diff --check -- \
  scripts/promote_research_report_clone_to_primary.py \
  tests/test_promote_research_report_clone_to_primary.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant_t611_pilot_20260721 \
  --output-dir data/local/backups/postgres
.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant \
  --output-dir data/local/backups/postgres

.venv/bin/python scripts/promote_research_report_clone_to_primary.py \
  --mode prove-quiescence \
  --target-backup data/local/backups/postgres/ai_quant-20260720T234936Z.manifest.json \
  --writer-container sotck_quant-ai-quant-org-1 \
  --output artifacts/t612-primary-quiescence-proof.json

.venv/bin/python scripts/promote_research_report_clone_to_primary.py \
  --plan artifacts/t611-executions/t611-clone-plan-runtime.json \
  --run1 artifacts/t611-executions/t611-clone-execution-1.json \
  --run2 artifacts/t611-executions/t611-clone-execution-2.json \
  --source-backup data/local/backups/postgres/ai_quant_t611_pilot_20260721-20260720T233925Z.manifest.json \
  --target-backup data/local/backups/postgres/ai_quant-20260720T234936Z.manifest.json \
  --quiescence-proof artifacts/t612-primary-quiescence-proof.json \
  --output artifacts/t612-primary-promotion-preflight.json

# The reviewed exact confirmation emitted by preflight was supplied here but is not retained in documentation.
.venv/bin/python scripts/promote_research_report_clone_to_primary.py \
  --mode promote \
  --plan artifacts/t611-executions/t611-clone-plan-runtime.json \
  --run1 artifacts/t611-executions/t611-clone-execution-1.json \
  --run2 artifacts/t611-executions/t611-clone-execution-2.json \
  --source-backup data/local/backups/postgres/ai_quant_t611_pilot_20260721-20260720T233925Z.manifest.json \
  --target-backup data/local/backups/postgres/ai_quant-20260720T234936Z.manifest.json \
  --quiescence-proof artifacts/t612-primary-quiescence-proof.json \
  --confirm '<reviewed required_confirmation>' \
  --output artifacts/t612-primary-promotion-result.json

# Run once immediately after promotion, and once after the controlled daily refresh.
.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant \
  --output-dir data/local/backups/postgres

docker compose up -d ai-quant-org
systemctl --user enable --now ai-quant-daily-update.timer
curl -fsS http://127.0.0.1:8000/api/health
.venv/bin/python scripts/audit_daily_update_schedule.py \
  --require-latest-run \
  --output artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json
make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: 8/8 T-612 focused tests; 25/25 combined T-608/T-611/T-612 tests; Python compile; CLI help; diff whitespace check; security scan over 509 files with zero findings; handoff validation over 189 documents; both pre-promotion backup/restore gates; quiescence proof; default preflight; confirmed promotion; exact post-commit verification; immediate and final post-promotion backups; controlled daily/product checks; 27/27 schedule gates; and 516/516 full local CI tests.
- Failed: none.
- Not run: non-local staging/production release validation and full-registry recovery, intentionally outside T-612.

## Evidence

- `tests/test_promote_research_report_clone_to_primary.py`: owner Platform and Quality; local-only synthetic evidence produced by `python -m unittest`; no sensitive source content or credentials; current with this handoff; not acceptable for non-local release.
- `artifacts/t611-executions/t611-clone-plan-runtime.json`, `t611-clone-execution-1.json`, and `t611-clone-execution-2.json`: owner Data and Evidence / Platform and Quality; T-608/T-611 producers; consumed locally by T-612 during the same 2026-07-21 operation; canonical plan SHA-256 `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d`; sensitive, ignored/local-only, and unacceptable for non-local release.
- `data/local/backups/postgres/ai_quant_t611_pilot_20260721-20260720T233925Z.dump` and `.manifest.json`: owner Platform and Quality; produced by `scripts/postgres_durable_backup.py` at `2026-07-20T23:39:25.653021+00:00`; stopped post-clone local PostgreSQL; restore-verified; 839,233,126-byte sensitive dump; SHA-256 `f4d4517a6b8e857924a43b8f2c7d0cf192161eeb19747f25134da6bec9b5a650`; retained through `2026-07-27T23:39:25.653021+00:00`; ignored/local-only and unacceptable for non-local release.
- `data/local/backups/postgres/ai_quant-20260720T234936Z.dump` and `.manifest.json`: owner Platform and Quality; produced by `scripts/postgres_durable_backup.py` at `2026-07-20T23:49:36.157380+00:00`; stopped primary pre-promotion local PostgreSQL; restore-verified; 837,733,663-byte sensitive dump; SHA-256 `893655aec5f946f9bf9c87e16948c7af61c8ad8274f991872f1e4cfb0e39bdbc`; retained through `2026-07-27T23:49:36.157380+00:00`; ignored/local-only and unacceptable for non-local release.
- `artifacts/t612-primary-quiescence-proof.json`: owner Platform and Quality; produced by T-612 `prove-quiescence` at `2026-07-20T23:58:44.174907+00:00`; proof SHA-256 `167a1bcafe9df3b938b4bdf17d331d38958ceddd96f1e4f9b8f45ceee80baed5`; primary app container exited and database other-session count zero; sensitive, ignored/local-only, and unacceptable for non-local release.
- `artifacts/t612-primary-promotion-preflight.json`: owner Platform and Quality; produced by the default T-612 mode immediately after the proof; `status=ready`, `executed=false`, selected 15 reports, zero equal-existing rows, and exact planned insert counts `1/15/15/112`; sensitive, ignored/local-only, and unacceptable for non-local release.
- `artifacts/t612-primary-promotion-result.json`: owner Platform and Quality; produced by confirmed T-612 `promote` during the same quiescent window; `status=completed`, `executed=true`, one bounded audit event inserted, and post-commit count/row/slice verification passed; sensitive, ignored/local-only, and unacceptable for non-local release.
- `data/local/backups/postgres/ai_quant-20260720T235934Z.manifest.json`: owner Platform and Quality; producer `scripts/postgres_durable_backup.py`; immediate post-promotion local PostgreSQL snapshot; `restore_verified=true`, dump SHA-256 `38eee70295a27f77bbce59c5252b42ef6e245d2761a23c5644d43249e7f3fadf`; local-only and not eligible for non-local release.
- `data/local/backups/postgres/ai_quant-20260721T001909Z.manifest.json`: owner Platform and Quality; producer `scripts/postgres_durable_backup.py`; final post-daily local PostgreSQL snapshot; `restore_verified=true`, dump SHA-256 `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`, retained through 2026-07-28; sensitive, local-only and not eligible for non-local release.
- `artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json`: owner Platform and Quality; local systemd audit; 27/27 gates passed, timer enabled/active; local-only and not eligible for non-local release.

## Decisions

- Do not reuse or relax `recover_watchlist_research_reports.py`; it remains clone-only and continues to reject the primary endpoint.
- Do not use T-610 exact replacement. T-612 copies a bounded allowlisted slice and has no deletion/update operation.
- Copy only reports selected by the canonical plan, not all registry assets created by the clone's required scan.
- Require restored backups on both sides. The source backup proves the post-clone slice is recoverable; the target backup proves the exact primary pre-state is recoverable.
- Require a snapshot-bound confirmation hash incorporating both database identities, both backup dump SHAs, plan/run/proof hashes, slice hash, current target counts, and insert/equal counts.
- Use one stable bounded audit event per plan/slice. A repeat run with fresh backup/proof preserves identical rows and the existing identical audit event instead of duplicating it.

## Risks and Open Questions

- Source and target are separate databases in one local PostgreSQL cluster. The tool verifies this identity relationship, but a cluster-level failure still affects both live databases; retained dump files remain the recovery boundary.
- The quiescence proof was valid for the completed preflight/promotion and must not be reused. Any later operation requires a fresh proof and preflight.
- Post-commit verification can detect an unexpected result but cannot roll back an already committed transaction. The serializable transaction, stopped writers, exact row prechecks, and deterministic inserts reduce that residual risk.
- The proof technically binds the Docker app container and primary database session count. The separately stopped user systemd timer was recorded as operator/systemd evidence and was restarted only after the immediate post-promotion backup passed.
- The final backup was created after the controlled daily/product writes, so it is the current rollback point; it does not replace the earlier pre-write rollback evidence.
- All runtime artifacts are ignored and local-only. Retain them on this machine through their stated backup/evidence windows; Git does not preserve them.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable; this is a new operator CLI with no public HTTP/schema change
- [x] `tasks/todo.md` status updated by the parent integration owner

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No; `app/services.py`, `SystemService`, API handlers, and store behavior were not touched.
- Domain placement: One-shot high-risk platform behavior is isolated in an operator script rather than added to the application facade.
- Focused regression: Eight tests protect evidence validation, allowlisting, conflict refusal, idempotency, rollback, default read-only behavior, and mutation SQL constraints.
- Contract/boundary changes: No API, UI, storage schema, paper-only, no-broker, or no-live-trading boundary changed. Local reports remain restricted opinion/reference evidence and are not promoted to facts or training data.

## Runtime Sequence

- Source backup gate passed first against the stopped post-clone database.
- Primary app and user systemd timer were stopped before the primary pre-backup. The proof then verified the app container was exited and the target database had zero other sessions.
- Default preflight remained read-only and emitted the exact snapshot-bound confirmation. The reviewed confirmation was consumed once by `promote`; it is intentionally omitted from this document.
- Promotion inserted only the allowlisted slice and one audit event in one serializable transaction. The result artifact independently records the exact committed rows, aggregate counts, audit ID, and slice SHA.
- Do not rerun the consumed confirmation or promotion sequence. Any broader recovery requires a new plan, quiescence proof, backup pair and independent clone review.

## Next Steps

1. Retain the immediate and final restore-verified backups through their stated local retention windows.
2. Continue daily timer monitoring and keep the five-company official-fact gaps visible.
3. Route any broader 11,702-report recovery to T-613; require a fresh clone proof and new collection-aware rollback point.

## Next Recommended Action

Treat T-612 as closed and use `ai_quant-20260721T001909Z` as the current local rollback point; do not infer full-registry recovery from this bounded slice.
