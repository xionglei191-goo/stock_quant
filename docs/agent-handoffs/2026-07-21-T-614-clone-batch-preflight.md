# Handoff: T-614 First Full-Registry Clone Batch

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Related tasks: T-613, T-614, T-615
- Artifact classification: local-only

## Objective

Bind T-613 batch 0001 to immutable identity evidence, obtain exact human approval, restore a fresh primary backup into an independently attested clone, parse the 250-report batch twice, prove idempotency and content identity, retain a restore-verified post-run backup, and remove all disposable runtime resources.

## Scope

- In scope: manifest/batch/raw binding, approval, clone restore and isolation, 250-report run1/run2, citation/manual-review classification, capacity/timing evidence, clone backup, teardown, tests, and roadmap state.
- Out of scope: primary writes or promotion, batches 0002-0044, duplicate/raw/OpenSearch deletion, automatic OCR escalation, fact/training promotion, broker integration, and live trading.

## Background

T-613 found 10,803 unique-content recovery candidates in 44 deterministic batches while PostgreSQL retained only a 15-report research slice. T-614 was the first approved full-registry clone-only rehearsal and had to prove that a broader batch could be parsed without touching primary state.

## Problem Statement

The existing T-611 pilot proved isolation for five companies and 15 reports, but it did not prove arbitrary T-613 batch binding, full raw-content identity, broader citation growth, or the capacity/idempotency behavior needed for a later recovery decision.

## Expected Deliverables

- A SHA-bound approval and ready preflight for batch 0001.
- A fresh, restore-verified clone with independent runtime attestation.
- Two successful 250-report executions with exact identity and idempotency evidence.
- A post-run clone backup, capacity/time evidence, and disposable-runtime cleanup.

## Proposed Work Plan

1. Verify T-613 manifest, decision, raw content, and fresh primary backup.
2. Record exact human approval and attest an isolated clone.
3. Execute batch 0001 twice and compare identities, evidence, manual review, and creation flags.
4. Back up the final clone state, restore-verify it, clean up clone resources, and open T-615 for later-batch decisions.

## Validation Plan

- Run focused preflight/executor/probe/recovery tests and full `make local-ci`.
- Require path/body/credential redaction in all T-614 artifacts.
- Require run2 `ingest_created_count=0`, zero identity/outcome mismatches, zero deletes, and preserved raw/OpenSearch inputs.
- Require final clone backup restore equality and explicit proof that primary counts and health are unchanged.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- T-613 batch SHA `2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85`.
- Fresh primary backup `ai_quant-20260721T023537Z`, dump SHA `36279642e3e6501462aab1f45114a3dbe3ee586db8641a81e8e189c66efcaaaa`.

## Blockers

- T-614 has no remaining blocker. Batches 0002-0044 remain intentionally unauthorized pending T-615.

## Current State

- Completed: preflight, approval, clone restore, attestation, run1, run2, idempotency comparison, capacity measurement, restore-verified clone backup, teardown, code/tests, roadmap update, local CI, and handoff validation.
- In progress: none.
- Not started: T-615 decision for the remaining 43 batches and any separate primary promotion.
- Blocked: none for T-614. No later batch is authorized.

## Current Findings

- Batch 0001 is 250 PDFs / 437,754,140 bytes. All report IDs, document IDs, locator hashes, sizes, and full content SHA-256 values matched T-613; raw-content identity SHA is `ee5f59dffe7ae7c774408e417a75c3aa37712cc3f9fc8fe7c543c8ee081edf33`.
- Human approval bound manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`, batch SHA `2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85`, clone-only double-run scope, zero primary writes, and zero deletes.
- The clone restored exact primary counts: `records=32319`, `audit_log=35385`, `market_data_bars=28365474`; research state `15 reports / 15 documents / 112 citations / 15 structured / 15 viewpoints / 3 forecasts`.
- Runtime attestation proved database `ai_quant_t614_clone_20260721`, internal two-member network, loopback-only execution, read-only root filesystem, read-only raw/repo/backup evidence mounts, local object/search backends, unreachable primary service, and exact restored counts.
- Run1 passed 250/250 with zero failures: 247 `text_indexed`, 3 `needs_text_review`, 1,937 citation evidence, 250 created documents, 2,144.972 seconds.
- Run2 passed 250/250 with zero failures: the same 247/3/1,937 outcomes, zero created documents, identical report/document/content/status/evidence/manual-review values, and zero mismatches in 2,705.687 seconds.
- The three manual-review report IDs are `rr_009533636222e1c2`, `rr_046cb3e7368122b3`, and `rr_06048550928948ca`; all were classified as no extractable local text. No automatic external OCR was invoked.
- Clone database size was 15,502,007,319 bytes at restore, 15,541,189,655 after run1, and 15,564,430,359 after run2. Run1 added about 37.4 MiB; run2 added no logical records but about 22.2 MiB of MVCC/audit storage and 254 audit rows.
- A mechanical serial extrapolation for 43 remaining double-run batches is about 57.9 hours. This is planning evidence only and does not authorize another batch.
- The final clone backup restored exactly at `records=46197`, `audit_log=36394`, `market_data_bars=28365474`; research state is `11702 reports / 265 documents / 2049 citations / 15 structured / 15 viewpoints / 3 forecasts`.
- Clone app, database, and network were removed after backup. Primary remained healthy and unchanged at `32319/35385/28365474`.

## Files Touched

- `scripts/prepare_research_report_clone_batch.py`: completed in the preflight phase; binds immutable evidence, approval, backup, and clone attestation without an execute mode.
- `scripts/execute_research_report_clone_batch.py`: new clone-only executor with approval/backup/attestation/runtime gates, exact 250-ID selection, path-redacted artifacts, and prior-run idempotency comparison.
- `tests/test_prepare_research_report_clone_batch.py`: protects preflight integrity and approval behavior.
- `tests/test_execute_research_report_clone_batch.py`: protects execution-bundle binding, raw-content tamper refusal, path redaction, and run2 zero-create identity equality.
- `tasks/todo.md`: marks T-614 done and opens T-615 without authorizing later batches.
- `docs/agent-handoffs/2026-07-21-T-614-clone-batch-preflight.md`: records the complete evidence chain and next decision.

## Commands Run

```bash
.venv/bin/python -m unittest \
  tests.test_execute_research_report_clone_batch \
  tests.test_prepare_research_report_clone_batch \
  tests.test_probe_research_report_clone_runtime \
  tests.test_recover_watchlist_research_reports -v

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --manifest artifacts/t613-full-registry/identity-manifest.json \
  --decision artifacts/t613-full-registry/recovery-decision.json \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T023537Z.manifest.json \
  --approval artifacts/t614-clone-batch/batch-0001-approval.json \
  --clone-attestation artifacts/t614-clone-batch/batch-0001-clone-attestation.json \
  --output artifacts/t614-clone-batch/batch-0001-preflight-ready.json

# Exact clone database only; no command targeted database ai_quant.
docker compose exec -T postgres createdb -U ai_quant ai_quant_t614_clone_20260721
docker compose exec -T postgres pg_restore -U ai_quant \
  -d ai_quant_t614_clone_20260721 --no-owner --no-privileges --exit-on-error \
  < data/local/backups/postgres/ai_quant-20260721T023537Z.dump

# The clone app used an internal network, read-only root/raw/evidence mounts,
# local object/search backends, and a clone-only PostgreSQL DSN. Secrets omitted.
.venv/bin/python scripts/probe_research_report_clone_runtime.py \
  --app-container sotck_quant-t614-clone-app \
  --postgres-container sotck_quant-postgres-1 \
  --isolated-network ai-quant-t614-isolated \
  --database-name ai_quant_t614_clone_20260721 \
  --base-url http://127.0.0.1:18002 \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T023537Z.manifest.json \
  --plan artifacts/t614-clone-batch/batch-0001-preflight-approved.json \
  --output artifacts/t614-clone-batch/batch-0001-clone-attestation.json

# Run inside the attested clone container. Run2 added --prior-run with run1.
python /app/scripts/execute_research_report_clone_batch.py \
  --preflight /evidence/batch-0001-preflight-ready.json \
  --approval /evidence/batch-0001-approval.json \
  --clone-attestation /evidence/batch-0001-clone-attestation.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260721T023537Z.manifest.json \
  --base-url http://127.0.0.1:18002 \
  --execute \
  --confirm-plan-sha256 bf1010e92c1a5b193b7bea62e1d2df3f4087a84f2a489d4be8815e89055a8ece \
  --confirm-batch-sha256 2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85 \
  --acknowledge-opinion-boundary \
  --allow-full-registry-scan \
  --confirm-clone-target

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant_t614_clone_20260721 \
  --output-dir data/local/backups/postgres \
  --retention-days 7 \
  --timeout-seconds 3600

docker rm -f sotck_quant-t614-clone-app
docker compose exec -T postgres dropdb -U ai_quant ai_quant_t614_clone_20260721
docker network disconnect ai-quant-t614-isolated sotck_quant-postgres-1
docker network rm ai-quant-t614-isolated

make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: 25/25 focused preflight/executor/probe/recovery safety tests before runtime execution.
- Passed: ready preflight with all six gates; clone restore and attestation; both 250-report executions; path/body/credential redaction scans; zero-delete/raw/OpenSearch preservation assertions.
- Passed: run2 `all_ingest_created_false=true`, `same_report_ids=true`, `same_identity_and_outcomes=true`, and `mismatch_count=0`.
- Passed: final clone dump and temporary restore equality; complete app/database/network teardown; unchanged primary counts and healthy `/api/health`.
- Passed: full local CI with 530 tests, UI static check, security scan, Markdown links, handoff validation, and canonical metadata validation.
- Expected failure: the first attempt to `docker cp` evidence into a read-only root filesystem was rejected before API access. The app container was recreated with separate `/evidence:ro` and `/output:rw` mounts, then freshly re-attested before either formal run.
- Failed: none in the formal run1/run2 or final verification chain.

## Evidence

- `artifacts/t614-clone-batch/batch-0001-approval.json`: explicit human approval recorded at `2026-07-21T03:09:44.257244+00:00`; local workspace; owner PM / Release Coordination; no sensitive data; local-only and unacceptable for non-local release. File SHA `b4df2a756a6dc00893374b8af1f18a77a5aebbe222a0d5468e3d515253c307f7`.
- `artifacts/t614-clone-batch/batch-0001-clone-attestation.json`: produced by `probe_research_report_clone_runtime.py` at `2026-07-21T03:24:58.053753+00:00`; isolated local clone; owner Platform and Quality; sensitive topology/count metadata without DSN; local-only and unacceptable for non-local release. File SHA `cf4ab487b897e3b557d3cd1657a754aab0a49d1c9d262bbe2a44b37a68f8ebeb`.
- `artifacts/t614-clone-batch/batch-0001-preflight-ready.json`: produced by `prepare_research_report_clone_batch.py`; local host/clone evidence; owner Data and Evidence; sensitive identity/count metadata but path/body-free; local-only and unacceptable for non-local release. File SHA `d92ed98758231e62ea796da44a1d7559b64885b6e63128867d0de509a812d664`.
- `artifacts/t614-clone-batch/runtime/t614-clone-execution-1.json`: produced by `execute_research_report_clone_batch.py` at `2026-07-21T04:01:44.266866+00:00`; isolated local clone; owner Data and Evidence; sensitive report/content identities without paths/names/bodies; local-only and unacceptable for non-local release. File SHA `60a0600d1b47c1e9c3b20a55b74d22f42c1b3d918466d5279a6d174259872226`; payload SHA `255d669a0ddd6920558f513ace6b4682fb0218c920a6d5cb123a085b05638f5a`.
- `artifacts/t614-clone-batch/runtime/t614-clone-execution-2.json`: same producer/classification, generated at `2026-07-21T04:48:06.764452+00:00`; file SHA `98b234bb02792441402bd5131def32c0e839fcc0521fbe6490c864e2e56a5658`; payload SHA `a5cc93f45bf99b431708bcffee2327056e99a790a28929a0707140f75dc1a909`.
- `data/local/backups/postgres/ai_quant_t614_clone_20260721-20260721T045056Z.dump` and `.manifest.json`: produced by `postgres_durable_backup.py` at `2026-07-21T04:50:56.138584+00:00`; local Docker Compose PostgreSQL clone; owner Platform and Quality; sensitive, restore-verified, retained through 2026-07-28; local-only and unacceptable for non-local release. Manifest SHA `638782003f9453a4b7160859de20967e0bd3270edc3245efebdad8db49ed7fca`; dump SHA `2ef3caf00e758f0da03f0a32f826576a5d29021f4c297c56218d1fa628a6eae1`.

## Decisions

- Keep execution in a dedicated operator script. No new business behavior was added to `SystemService`.
- Require a ready preflight plus the exact approval, backup dump, attestation file, current container identity, plan SHA, batch SHA, opinion boundary acknowledgement, full-registry-scan acknowledgement, and clone-target acknowledgement before API access.
- Preserve path redaction in all T-614 artifacts. The executor resolves opaque locator hashes inside the clone and emits only stable IDs, hashes, categories, and aggregates.
- Treat the three no-text reports as explicit manual-review work. Do not invoke external OCR automatically or call the classification a parser success.
- Do not infer authorization for batch 0002 from batch 0001. T-615 must decide targeted registration versus a persistent clone, vacuum/bloat controls, and the approval unit for later batches.
- Back up before teardown. Cleanup removed only the disposable app, clone database, and isolated network; raw files, primary PostgreSQL, OpenSearch, artifacts, and backups were preserved.

## Risks and Open Questions

- The current API scan registers the full 11,702-report registry for a 250-report batch. Repeating that in a fresh clone for every batch is operationally wasteful and needs a T-615 design decision.
- Run2 created no logical report/document/evidence records but still added 254 audit rows and about 22.2 MiB of physical storage. Later execution design should benchmark vacuum and avoid treating physical growth as logical data growth.
- The three manual-review IDs need PDF-level inspection before choosing OCR, skip, or manual transcription; local research remains opinion/reference-only either way.
- The 57.9-hour remaining-batch estimate assumes serial execution and comparable files. It is not a completion forecast or approval.
- Primary still contains only the reviewed 15-report slice. Any promotion from broader clone results is a separate high-risk task with a new backup, conflict review, and explicit approval.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No; `app/services.py` was not changed.
- Domain placement: Clone execution and evidence validation remain in focused operator scripts under `scripts/`.
- Focused regression: `tests/test_execute_research_report_clone_batch.py` plus existing preflight/probe/recovery tests protect facade-independent behavior.
- Contract/boundary changes: No API schema, storage schema, UI, paper-only, no-broker, or no-live-trading boundary changed. Local reports remain opinion/reference evidence only.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated; no public API or storage contract changed
- [x] `tasks/todo.md` roadmap status updated
- [x] Local-only artifacts classified and hashed
- [x] Disposable runtime removed; primary unchanged

## Next Steps

1. T-615: inspect the three `needs_text_review` IDs and decide OCR/skip/manual handling.
2. Compare targeted registration with a persistent isolated clone so later batches do not repeat the full registry scan unnecessarily.
3. Define vacuum/capacity controls and request a new SHA-bound approval only if batch 0002 is selected.

## Next Recommended Action

Do not run batch 0002 yet. First close T-615's parser-quality, registry-scan, and storage-bloat decisions using the T-614 evidence.
