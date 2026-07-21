# Handoff: T-614 Clone Batch Preflight

## Metadata

- Status: BLOCKED
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only

## Objective

Bind T-613 batch 0001 to its immutable identity evidence, verify all 250 raw files and a fresh primary rollback backup, and produce a clone-compatible preflight plan. Do not create or write a clone until exact human approval is recorded.

## Scope

- In scope: manifest/entries/batch integrity, full content verification for batch 0001, fresh collection-aware primary backup, approval schema, reuse of the existing clone attestation validator, path-redacted operation artifacts, tests, and roadmap state.
- Out of scope: clone creation, report ingestion/extraction, primary writes, promotion, later batches, duplicate deletion, raw mutation, OpenSearch writes, broker integration, and live trading.

## Background

T-613 identified 10,803 unique-content recovery candidates and split them into 44 deterministic batches. It deliberately left execution disabled and required a new primary backup, exact SHA-bound approval, and an independently attested clone before any batch write.

## Problem Statement

The repository had strong clone runtime proof for the earlier 15-report watchlist pilot but no path-redacted preflight that could bind an arbitrary T-613 batch to raw content, a fresh backup, a human approval record, and that same runtime validator.

## Expected Deliverables

- A no-execute batch preflight CLI.
- Focused tests for manifest tamper, raw binding, fresh backup, generic continuation rejection, and remaining approval/clone gates.
- A restore-verified post-T-613 primary backup.
- A real batch-0001 preflight and exact approval request.

## Current State

- Completed: implementation, 5 focused tests, 22 combined preflight/clone safety tests, real 250-file content binding, fresh restore-verified backup, artifact redaction scan, application health check, 527-test local CI, and handoff validation.
- In progress: none until exact approval is received.
- Not started: clone creation, attestation, run 1, run 2, clone backup, and teardown.
- Blocked: exact human approval is absent. Clone attestation cannot be generated until an approved clone is created from the bound backup.

## Current Findings

- Batch 0001 contains 250 PDF files / 437,754,140 bytes across six hashed source scopes.
- All 250 report IDs, document IDs, sizes, locator hashes, and full content SHA-256 values match T-613. Batch raw-content identity SHA is `ee5f59dffe7ae7c774408e417a75c3aa37712cc3f9fc8fe7c543c8ee081edf33`.
- The new primary backup `ai_quant-20260721T023537Z` completed dump, temporary restore, table-count comparison, six research-collection comparisons, bounded ID sample comparison, and an independent preflight re-hash of the dump in 542.11 seconds.
- Backup table counts are `records=32319`, `audit_log=35385`, `market_data_bars=28365474`; research counts are `15 reports / 15 documents / 112 citations / 15 structured / 15 viewpoints / 3 forecasts`.
- Preflight plan SHA is `bf1010e92c1a5b193b7bea62e1d2df3f4087a84f2a489d4be8815e89055a8ece`. The fresh-backup gate passes.
- Execution remains blocked only by `exact_human_approval_verified` and `independent_clone_attestation_verified`; `execution_ready=false`, `execution_performed=false`, and `automatic_recovery_authorized=false`.

## Proposed Work Plan

1. Completed: verify T-613 manifest, entries, decision, and batch SHA values.
2. Completed: resolve the 250 opaque locators and verify full file content without emitting paths or names.
3. Completed: create and restore-verify a fresh collection-aware primary backup.
4. Completed: emit a plan compatible with the existing runtime probe/attestation validator and an exact approval request.
5. Blocked: record exact human approval for only batch 0001.
6. After approval: restore the new backup to an isolated clone, attest it, run batch 0001 twice, back it up, and tear it down.

## Validation Plan

- Run focused preflight tests plus the existing clone probe/recovery safety suites.
- Run the real batch preflight with and without the new backup and require the expected failed-gate transition.
- Scan artifacts for report paths, filenames, DSNs, credentials, and report content.
- Run `make local-ci PYTHON=.venv/bin/python` and handoff validation before committing.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- T-613 batch-0001 SHA `2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85`.
- Fresh primary backup dump SHA `36279642e3e6501462aab1f45114a3dbe3ee586db8641a81e8e189c66efcaaaa`.
- Existing `probe_research_report_clone_runtime.py` and clone attestation validator.

## Blockers

- Human approval must exactly match the request artifact. The messages “继续” and “重试” do not bind the immutable SHA values or authorize a clone write.
- A clone attestation can only be produced after approval permits creating the isolated runtime; stale T-611 attestation cannot be reused.

## Files Touched

- `scripts/prepare_research_report_clone_batch.py`: immutable evidence checks, raw binding, backup/approval/attestation gates, clone-compatible plan, and approval request.
- `tests/test_prepare_research_report_clone_batch.py`: tamper, path redaction, backup freshness, generic approval rejection, and blocked-preflight regressions.
- `tasks/todo.md`: records completed preparation and the exact approval blocker without claiming the clone run is complete.
- `docs/agent-handoffs/2026-07-21-T-614-clone-batch-preflight.md`: reproducible evidence and next action.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_prepare_research_report_clone_batch -v
.venv/bin/python -m unittest \
  tests.test_prepare_research_report_clone_batch \
  tests.test_probe_research_report_clone_runtime \
  tests.test_recover_watchlist_research_reports -v

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --manifest artifacts/t613-full-registry/identity-manifest.json \
  --decision artifacts/t613-full-registry/recovery-decision.json \
  --filesystem-root '/home/xionglei/文档/6大投行研报汇总' \
  --registry-root /data/local/research_reports \
  --output artifacts/t614-clone-batch/batch-0001-preflight.json \
  --approval-output artifacts/t614-clone-batch/batch-0001-approval-request.json

make local-ci PYTHON=.venv/bin/python
.venv/bin/python scripts/check_handoffs.py

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant \
  --output-dir data/local/backups/postgres \
  --retention-days 7 \
  --timeout-seconds 3600

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --manifest artifacts/t613-full-registry/identity-manifest.json \
  --decision artifacts/t613-full-registry/recovery-decision.json \
  --filesystem-root '/home/xionglei/文档/6大投行研报汇总' \
  --registry-root /data/local/research_reports \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T023537Z.manifest.json \
  --output artifacts/t614-clone-batch/batch-0001-preflight.json \
  --approval-output artifacts/t614-clone-batch/batch-0001-approval-request.json
```

Result:

- Passed: 5/5 focused tests and 22/22 combined preflight/clone safety tests.
- Passed: raw binding for all 250 reports; zero emitted report paths, names, DSNs, credentials, or bodies.
- Passed: new backup and temporary restore comparison; preflight re-read all 837,739,289 dump bytes and matched SHA `36279642e3e6501462aab1f45114a3dbe3ee586db8641a81e8e189c66efcaaaa`.
- Passed: current application `/api/health` after backup.
- Passed: full local CI with 527 tests, UI static check, security scan across 536 files, links across 250 Markdown files, 191 handoff documents, and 5 canonical document metadata checks.
- Expected blocked result: exact human approval and new clone attestation are not supplied.
- Pending: no additional preparation check; runtime work remains blocked on exact approval.
- Failed: none.

## Evidence

- `artifacts/t614-clone-batch/batch-0001-preflight.json`: produced by `prepare_research_report_clone_batch.py` at `2026-07-21T02:53:17.242910+00:00`; local host/Compose inputs; owner Data and Evidence; sensitive identity/count evidence but path-redacted and body-free; local-only and unacceptable for non-local release. File SHA `cdaa9804569f3169e4371404a36b9add3a7f563296d0192ecddb45bbfe1383d6`.
- `artifacts/t614-clone-batch/batch-0001-approval-request.json`: same producer and environment; exact non-secret approval text; local-only and unacceptable for non-local release. File SHA `7476e5343941875e90ff4f5891f2e477dbc231a045d5450cfe054a663e5b25cf`.
- `data/local/backups/postgres/ai_quant-20260721T023537Z.dump` and `.manifest.json`: produced by `postgres_durable_backup.py` at `2026-07-21T02:35:37.682889+00:00`; local Docker Compose PostgreSQL; owner Platform and Quality; sensitive, restore-verified, retained through 2026-07-28; local-only and unacceptable for non-local release. Manifest SHA `8b2902fec30ba649771c0fe9bdb95d9c368023c5b3391b7b724eeb628f824ad9`; dump SHA `36279642e3e6501462aab1f45114a3dbe3ee586db8641a81e8e189c66efcaaaa`.

## Decisions

- Keep preflight and execution separate. The new command cannot create a clone or call any report mutation API.
- Reuse the complete T-611 clone validator, including container/database identities, internal network membership, read-only mount, local backends, loopback URL, root filesystem, primary unreachability, and restored counts.
- Require the backup to be generated after the T-613 decision and retained at execution time.
- Recompute the full backup dump SHA during preflight instead of trusting only the adjacent manifest.
- Require structured approval with immutable manifest/batch SHA values; conversational continuation words are intentionally insufficient.

## Risks and Open Questions

- The 250-file batch is about 417.5 MiB; parse time and citation growth are not yet known.
- The approval record is valid for 24 hours and clone attestation for 30 minutes; expired evidence must be regenerated.
- The backup protects the current 15-report primary state, not historical full-registry content.
- No capacity estimate for the remaining 43 batches is valid until batch 0001 finishes twice.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated; no API, storage schema, UI, or environment contract changed
- [x] `tasks/todo.md` roadmap status updated

## Next Steps

1. Obtain the exact approval sentence from `batch-0001-approval-request.json`.
2. Record the approval artifact and create the isolated clone from the bound backup.
3. Generate a fresh attestation, then execute only batch 0001 twice.

## Next Recommended Action

Approve or reject only the exact 250-report batch request; do not authorize the remaining 43 batches before parser quality and storage growth are measured.
