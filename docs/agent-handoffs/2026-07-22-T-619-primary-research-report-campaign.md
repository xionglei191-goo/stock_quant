# Handoff: T-619 Primary Research Report Campaign

## Metadata

- Status: DONE
- Owner group: Platform and Quality; Data and Evidence
- Reviewer groups: Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-24
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only
- Related tasks: T-613, T-617, T-619

## Objective

Import each authorized T-613 batch into PostgreSQL only after an isolated clone has passed two hash-bound runs and a fresh primary backup, quiescence proof, conflict preflight, and single-transaction insert-only promotion all pass.

## Scope

- In scope: batch 0006-0044 clone verification and insert-only primary promotion, local backup/clone evidence, and promotion control scripts.
- Out of scope: deletion or update of PostgreSQL records, raw reports, duplicate aliases, or OpenSearch; fact/training promotion; broker connectivity; live execution.

## Background

The user authorized primary import only after every batch completes isolated clone validation, while explicitly preserving raw files, duplicate aliases, and OpenSearch.

## Problem Statement

The clone executor deliberately had no primary-write permission, so a separate hash-bound and auditable promotion path was required for the validated results.

## Expected Deliverables

- Per-batch clone run evidence, restore-verified backups, static preflight, primary promotion result, and audit event.
- A resumed healthy local Compose application after each primary maintenance window.

## Current State

- Completed: batches 0006-0014 primary promotion. Batch 0014 clone run1/run2 passed (250 selected, 0 failed, 241 text-indexed, 9 manual-review, 1,933 evidence); run2 created zero records. Both its clone backup and fresh primary rollback backup passed restore verification. The serializable promotion inserted 250 reports, 250 documents, and 1,933 evidence records with audit event `evt_t619_05db6ddf904104eb7ed843eb00223923`; post-commit verification passed at 2,265 reports, 2,265 documents, and 17,316 citation evidence.
- Completed: B0015-B0044 bulk clone run completed all 30 source batches: 7,303 reports processed, 0 failed, 55,802 evidence, result SHA-256 `7e2d20ba4f27631aa59afaf8dc7b0c87371b5287d0ed33280c3bdd6e6dcfd5cd`. The one-time primary preflight passed, then its serializable insert-only transaction inserted 7,303 reports, 7,303 documents, and 55,802 evidence with no source insert, update, or delete.
- Completed: post-commit verification passed with audit event `evt_t619_bulk_ec25e98f1dd7073760a5925b681f454e`, 9,568 research reports, 9,568 research documents, and 73,118 research-report citation evidence. The primary Compose application and `ai-quant-daily-update.timer` were restored and healthy.
- Blocked: none.

## Current Findings

- Batch 0006 passed clone run1/run2 with 250 selected reports, 0 failures, 1,916 citation evidence records, and 7 restricted manual-review records with zero evidence.
- An independent PostgreSQL clone can share a database OID with primary; system identifier plus attested runtime identity is the correct topology discriminator.
- Batch 0014's first clone restore attempt exhausted local disk while rebuilding the `market_data_bars` key. It did not reach a manifest or primary-write stage. The failed temporary restore database and the completed 0006-0013 derived clone volumes were removed only after verifying their restore manifests; raw report files, duplicate aliases, OpenSearch, backups, manifests, clone runs, and promotion artifacts were preserved. Free space increased from 1.9GB to 141GB before the successful retry.
- The B0015-B0044 one-time transaction was intentionally used only after the user accepted loss of per-batch rollback points. Its preflight required the exact passed clone result and rejected any incomplete, failed, or unequal primary slice before writing.

## Proposed Work Plan

1. Preserve the local-only run, preflight, and promotion artifacts as the campaign evidence.
2. Keep the restored Compose application and daily timer under normal local operational monitoring.
3. Treat any future ingestion as a new, separately authorized migration rather than reopening this closed campaign.

## Validation Plan

- Run focused promotion/backup tests, `python3 scripts/check_handoffs.py`, `make local-ci`, and `git diff --check`.
- Verify B0006-B0014 with their post-commit artifacts and B0015-B0044 with the passed bulk result, preflight, promotion result, direct PostgreSQL counts, audit event, and `/api/health` after service restart.

## Dependencies

- Local Docker Compose PostgreSQL, S3/MinIO, OpenSearch, immutable registry manifest, and user campaign authorization.

## Blockers

- None. The `ai-quant-daily-update.timer` and primary Compose application were restored after the B0015-B0044 maintenance window.

## Files Touched

- `scripts/promote_research_report_clone_batch_to_primary.py`: T-619-only promotion contract. It validates the immutable plan and user campaign scope, both clone runs, restricted rights, manual-review no-citation state, fresh source/target backups, primary quiescence, unequal target conflicts, and post-commit equality before using the existing serializable insert-only transaction primitive.
- `tests/test_promote_research_report_clone_batch_to_primary.py`: synthetic regression for text-indexed and manual-review rows, campaign scope, forbidden citation state, and independently attested cross-PostgreSQL source identity.
- `scripts/postgres_durable_backup.py`: permits an explicitly named isolated clone PostgreSQL container for clone-only restore-verified backups; defaults remain the primary Compose database.
- `scripts/execute_research_report_bulk_clone.py`: resumes and concurrently executes only B0015-B0044 against the isolated clone, persists each source-batch result, and never accepts primary-write permission.
- `scripts/promote_research_report_bulk_clone_to_primary.py`: validates the passed bulk result and target quiescence, then performs the one authorized serializable insert-only primary transaction and post-commit count/audit verification.
- `artifacts/t619-primary-campaign-approval.json`: local-only user authorization record, bound to manifest `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e` and batch IDs 0006-0044.
- `tasks/todo.md`: closes T-619 as `DONE` with final reconciliation counts and artifact references.

## Commands Run

```bash
PATH=".venv/bin:$PATH" python -m unittest \
  tests.test_promote_research_report_clone_batch_to_primary \
  tests.test_promote_research_report_clone_to_primary \
  tests.test_execute_research_report_clone_batch -v
PATH=".venv/bin:$PATH" python scripts/postgres_durable_backup.py \
  --source-db ai_quant --output-dir data/local/backups/postgres \
  --retention-days 7 --timeout-seconds 3600
PATH=".venv/bin:$PATH" python scripts/promote_research_report_clone_batch_to_primary.py \
  --mode preflight ... --output artifacts/t619-batch-0006/primary-preflight.json
PATH=".venv/bin:$PATH" python scripts/promote_research_report_clone_batch_to_primary.py \
  --mode promote --confirm T619_PROMOTE:<hash-bound-token> ... \
  --output artifacts/t619-batch-0006/primary-promotion-result.json
PATH=".venv/bin:$PATH" python scripts/execute_research_report_bulk_clone.py \
  --approval artifacts/t619-bulk-0015-0044/approval.json --workers 2 ...
PATH=".venv/bin:$PATH" python scripts/promote_research_report_bulk_clone_to_primary.py \
  --mode preflight ... --output artifacts/t619-bulk-0015-0044/primary-preflight.json
PATH=".venv/bin:$PATH" python scripts/promote_research_report_bulk_clone_to_primary.py \
  --mode promote --confirm T619_BULK_PROMOTE:<hash-bound-token> ... \
  --output artifacts/t619-bulk-0015-0044/primary-promotion-result.json
```

Result:

- Passed: 16 focused promotion/executor tests, including the bulk `failed_count=0` regression; `py_compile` and `git diff --check`; clone run1/run2 (250 selected, 0 failed, 1,916 evidence, 7 manual-review); clone and primary restore-verified backups; primary quiescence proof; preflight and promotion post-commit verification.
- Passed: batch 0006 inserted 250 research reports, 250 documents, and 1,916 evidence records. It inserted no source rows, updates, deletes, raw-file changes, alias changes, or OpenSearch changes.
- Passed: after restarting `ai-quant-org`, `GET /api/health` reported `status=ok`, PostgreSQL, S3, and OpenSearch configured.
- Passed: batch 0014 clone run1/run2 (250 selected, 0 failed, 241 text-indexed, 9 manual-review, 1,933 evidence; run2 created zero records); clone backup `ai_quant_t619_clone_0014-20260722T113853Z` and primary rollback backup `ai_quant-20260722T115135Z` both restore verified; quiescence, preflight, insert-only promotion, post-commit verification, service health, and timer restoration all passed.
- Passed: B0015-B0044 bulk clone completed 30/30 source batches with 7,303 processed, 0 failed, 55,802 evidence, and result SHA-256 `7e2d20ba4f27631aa59afaf8dc7b0c87371b5287d0ed33280c3bdd6e6dcfd5cd`; it made no primary write, update, delete, raw-file, alias, or OpenSearch change.
- Passed: final preflight planned exactly 0 sources, 7,303 reports, 7,303 documents, and 55,802 evidence inserts. The one-time serializable transaction completed with those exact counts, audit event `evt_t619_bulk_ec25e98f1dd7073760a5925b681f454e`, and post-commit research counts of 9,568 reports, 9,568 documents, and 73,118 citation evidence.
- Passed: after final promotion, direct PostgreSQL collection counts were `research_reports=9568`, `documents=9596`, and `evidence=75519`; `GET /api/health` returned `status=ok`, Docker Compose application health became healthy, and `ai-quant-daily-update.timer` was active.
- Passed: `PATH=".venv/bin:$PATH" make local-ci` completed 551 tests plus UI static, security, Markdown-link, handoff, and canonical-document-metadata checks. The unprefixed host-Python attempt was rejected as environment drift because it lacked project dependencies; it made no project change.

## Decisions

- Keep T-612's legacy watchlist promotion tool untouched. T-619 uses a separate protocol because a 250-report batch can contain `needs_text_review` items; those are permitted as restricted local references but must have zero citation evidence.
- Clone executor evidence remains clone-only (`primary_writes_allowed=false`). The separate campaign approval is the sole authority for the later primary insert-only transaction.
- Preserve all exact-equal target records. Refuse unequal conflicts. The tool has no delete or update path.
- An independently hosted PostgreSQL clone may share a database OID with primary. T-619 therefore requires a distinct PostgreSQL system identifier and binds the live clone OID/system identifier to its immutable isolated-runtime attestation; it does not accept an arbitrary cross-instance source.
- Pre-commit quiescence is a mandatory gate; post-commit data verification must not fail solely because a transient observer session exists after the transaction commits. Exact database identity, table/research counts, promoted rows, and audit payload remain mandatory.
- The user explicitly replaced B0015-B0044 per-batch rollback/promotion with one isolated bulk clone followed by one primary transaction. The passed B0014 primary state remains the retained whole-range rollback checkpoint; no data was deleted to create this path.

## SystemService Growth Freeze Review

- New `SystemService` business logic: none.
- Domain module decision: no service behavior changed; this is an offline migration/control script using existing PostgreSQL storage contracts.
- Focused regression: `tests/test_promote_research_report_clone_batch_to_primary.py` plus legacy promotion/executor tests.
- Contract/boundary changes: no API or UI schema change. PostgreSQL may receive new restricted research-reference records only after gates pass. Paper-only/no-broker and fact/training boundaries remain unchanged.

## Risks and Open Questions

- The B0015-B0044 user-authorized bulk path has no per-batch primary rollback point. The B0014 primary checkpoint is the retained whole-range rollback baseline, and all current evidence is local-only.
- The 11,702 raw local files remain opinion/reference material only. They must not be elevated to a fact source or model-training corpus without a separate rights and governance decision.
- Normal local capacity monitoring remains necessary before any future clone or backup work. This completed campaign does not authorize deletion of raw files, aliases, OpenSearch, backups, or migration evidence.

## Artifacts

- `artifacts/t619-primary-campaign-approval.json`: producer `apply_patch` from explicit user instruction; local-only; no sensitive raw paths; acceptable only as local migration authority, not non-local release evidence.
- `artifacts/t619-batch-0006/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; contains only identifiers/counts/hashes; batch 0006 completed primary promotion and post-commit verification; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0006-20260721T225246Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0006-postgres`; local-only; restore verified source-clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260721T232036Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0006 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0008/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0008; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0008-20260722T020716Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0008-postgres`; local-only; restore-verified batch 0008 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T021917Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0008 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0009/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0009; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0009-20260722T032743Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0009-postgres`; local-only; restore-verified batch 0009 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T033923Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0009 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T035505Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0010 primary clone baseline; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0010/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0010; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0010-20260722T045223Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0010-postgres`; local-only; restore-verified batch 0010 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T050625Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0010 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0011/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0011; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0011-20260722T062037Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0011-postgres`; local-only; restore-verified batch 0011 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T063153Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0011 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0012/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0012; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0012-20260722T080142Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0012-postgres`; local-only; restore-verified batch 0012 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T081706Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0012 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0013/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0013; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0013-20260722T094201Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0013-postgres`; local-only; restore-verified batch 0013 clone checkpoint retained after the derived clone volume was released; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T100256Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0013 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-batch-0014/primary-promotion-result.json`: producer `scripts/promote_research_report_clone_batch_to_primary.py`; local-only; completed insert-only promotion and post-commit count/audit evidence for batch 0014; not non-local release evidence.
- `data/local/backups/postgres/ai_quant_t619_clone_0014-20260722T113853Z.manifest.json`: producer `scripts/postgres_durable_backup.py --postgres-container t619-batch0014-postgres`; local-only; restore-verified batch 0014 clone checkpoint; contains database data; not non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260722T115135Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only; restore-verified batch 0014 primary rollback checkpoint; contains database data; not reusable for later batches or non-local release evidence.
- `artifacts/t619-bulk-0015-0044/approval.json`: producer `apply_patch` from the explicit user decision to use one bulk clone and one final primary transaction; local-only; authorizes no clone-time primary writes, updates, or deletes; not non-local release evidence.
- `artifacts/t619-bulk-0015-0044/run.json`: producer `scripts/execute_research_report_bulk_clone.py`; local-only; passed 30-source-batch clone result with selected identifiers, content hashes, and counts; not non-local release evidence.
- `artifacts/t619-bulk-0015-0044/primary-preflight.json`: producer `scripts/promote_research_report_bulk_clone_to_primary.py`; local-only; exact planned insert-only slice and confirmation token; no raw content; not non-local release evidence.
- `artifacts/t619-bulk-0015-0044/primary-promotion-result.json`: producer `scripts/promote_research_report_bulk_clone_to_primary.py`; local-only; final insert/audit/post-commit counts; no raw content; not non-local release evidence.

## Evidence

- `artifacts/t619-batch-0006/run1.json` and `run2.json`: clone executor; local-only; hash-bound double-run evidence; sensitive report identifiers only; not non-local release evidence.
- `artifacts/t619-batch-0006/primary-preflight.json` and `primary-promotion-result.json`: T-619 promoter; local-only; batch 0006 count/hash/audit evidence; no raw report content; not non-local release evidence.
- `artifacts/t619-batch-0014/run1.json`, `run2.json`, `primary-preflight.json`, and `primary-promotion-result.json`: clone executor and T-619 promoter; local-only; batch 0014 hash/count/audit evidence; no raw report content; not non-local release evidence.
- `artifacts/t619-bulk-0015-0044/run.json`, `primary-preflight.json`, and `primary-promotion-result.json`: T-619 bulk executor and promoter; local-only; B0015-B0044 hash/count/audit evidence; no raw report content; not non-local release evidence.

## Next Steps

1. Retain the local-only bulk artifacts and B0014 rollback checkpoint according to the existing retention policy.
2. Monitor the restored local Compose application and daily timer as normal operations.
3. Require a new task, authorization, clone validation, and insert-only preflight for any future research-report migration.

## Handoff Checklist

- [x] Code changes completed for batch 0006 promotion support.
- [x] Focused tests and primary promotion evidence recorded.
- [x] `tasks/todo.md` updated with final campaign completion and reconciliation counts.
- [x] Bulk execution and one-time final promotion completed; 7,303 reports were promoted with post-commit verification.

## Next Recommended Action

Begin normal local monitoring; any further report ingestion requires a newly authorized migration task.
