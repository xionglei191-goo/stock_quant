# Handoff: T-615 Research Recovery Execution Architecture

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Related tasks: T-613, T-614, T-615
- Artifact classification: local-only

## Objective

Resolve the T-614 parser, registry-scan, idempotency-write, and capacity questions; implement the safer execution architecture; and prove it with an operator-approved batch-0002 double run in a fresh isolated clone without primary writes or deletes.

## Scope

- In scope: three manual-review PDFs, targeted batch registration, read-only run2 verification, MVCC/vacuum policy, later-batch approval units, batch-0002 dry-run and exact approval, fresh clone restore/attestation, double run, final backup, clone cleanup, tests, contracts, and roadmap state.
- Out of scope: primary writes or promotion, batches 0003-0044, raw/duplicate/OpenSearch deletion, automatic external OCR, fact/training promotion, brokers, and live trading.

## Background

T-614 double-ran 250 reports in an isolated clone. Both runs agreed, but each run recursively scanned 11,702 registered files, and run2 repeated ingest/extract calls. Run2 added no logical research records yet added 254 audit rows and about 22.2 MiB of physical PostgreSQL storage.

## Problem Statement

The old executor made a logical idempotency proof through a second write workload. That inflated audit/MVCC storage, widened the scan surface beyond the approved batch, and made later 43-batch recovery unnecessarily expensive. Three image-only PDFs also needed an explicit parser-quality decision.

## Expected Deliverables

- A reproducible, redacted diagnosis for the three T-614 manual-review IDs.
- Exact-path registration and a truly read-only second-run state comparison.
- Capacity thresholds and a non-blocking vacuum policy.
- A conservative per-batch-to-segment approval progression.
- A blocked batch-0002 preflight and exact human approval request.

## Current State

- Completed: parser diagnosis, targeted registration, read-only batch-state API, executor update, focused regressions, API contract, capacity/vacuum decision, batch-0002 raw binding, exact approval, fresh clone restore and attestation, run1/run2, idempotency and capacity verification, final restore-verified clone backup, clone cleanup, primary verification, and roadmap closeout.
- In progress: none.
- Not started: T-616 decision and any batch 0003-0044 execution.
- Blocked: none for T-615. Remaining batches require new plans, attestations, and explicit approvals under T-616.

## Current Findings

- IDs `rr_009533636222e1c2`, `rr_046cb3e7368122b3`, and `rr_06048550928948ca` are valid, unencrypted image-only PDFs. The sampled first three pages contain no text or font rows and three image rows each. Local Tesseract extracted 3,606, 1,052, and 3,621 characters from the first page respectively.
- Parser decision: keep all three in manual review until local OCR output quality is accepted. Permit local OCR only inside an approved isolated clone; do not invoke external OCR automatically and do not classify these files as broken.
- `relative_paths` restricts scan registration to the approved batch and rejects absolute paths, traversal, symlinks, duplicates, unavailable files, and extension mismatches.
- Run2 now recomputes raw identity locally and calls only `GET /api/research-reports/batch-state`. That response is path/name/body-free and excluded from audit and usage telemetry writes.
- T-614 run2's 22.2 MiB / 254-audit increase is avoidable write amplification, not required research data growth. Batch 0002 must prove run2 audit and logical row deltas are zero and database growth is at most 1 MiB.
- Primary currently has 21 dead `audit_log` tuples and 92 dead `records` tuples against 35,385 and 32,319 live rows. There is no current need for manual vacuum on primary.
- Batch 0002 is 250 PDFs / 573,286,759 bytes. Batch SHA is `6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1`; raw identity SHA is `dae5a5a9ba73f5dcfbf2894e9ce596e7700dac80999225735986ab05e5b55529`.
- Fresh primary backup `ai_quant-20260721T060949Z` passed restore verification at `32319 records / 35385 audit / 28365474 market bars` and research state `15 / 15 / 112 / 15 / 15 / 3`. Dump SHA is `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`, retained through 2026-07-28.
- The backup-bound batch-0002 plan SHA is `0ec683ac993d4e6017f7ccecc67c659cecaa235e50e18f95215229f587441907`. Exact approval bound manifest `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e` and batch `6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1`; approval file SHA is `e30a4bda0508f02f4dfdbe227bd761adc2476c3d7aa51b505487683184e75fe5`.
- Fresh clone `ai_quant_t615_clone_20260721` restored the approved backup at `32319 records / 35385 audit / 28365474 market bars`. Its independent attestation proved an internal two-member network, primary service unreachable, raw/evidence read-only, root filesystem read-only, local object/search backends, and exact database/plan identity. Attestation file SHA is `a7037d077c419c6e3c1a7d8f5701f26299757cfab890c48f23b74e2ac2cd9815`.
- The final ready preflight passed all six gates. Its file SHA is `925f6d15793f4e77fa62b4cabee9f036e3391f1ecbfb99c559cab1db16c46542`.
- Run1 passed 250/250: 242 text-indexed, 8 manual-review, 1,826 citation evidence, and 250 newly ingested reports in 1,179.372 seconds. It used `targeted_relative_paths`, verified all 250 content identities, performed no deletes, and preserved raw and the existing OpenSearch index.
- Run1 changed only the clone: records `32319 -> 34654`, audit `35385 -> 36145`, market bars unchanged, research reports/documents `15 -> 265`, and research citation evidence `112 -> 1938`. Database size changed `15502007319 -> 15512034327` bytes, a 10,027,008-byte increase.
- Run2 passed 250/250 through `read_only_batch_state` in 7.54 seconds. It created 0 ingests, its 250 outcomes matched run1 after excluding the expected `ingest_created` flag, and records/audit/market bars/database bytes all had zero delta.
- Post-run dead tuples were 1,244/34,654 for `records` and 0/36,145 for `audit_log`; neither the 10% ratio nor 10,000-row threshold was reached, so no vacuum was run.
- Final clone backup `ai_quant_t615_clone_20260721-20260721T072013Z` passed independent restore equality for all table and research collection counts. Dump SHA is `fcfd04c15dc1a241bca5fd1ddc07301939df6b09c1c9dc9271ec855d5c8c127c`, size 838,107,589 bytes, retained through 2026-07-28.
- The exact clone application, clone database, and isolated network were removed after backup verification. Primary remained `32319/35385/28365474`, database size `17108941847`, and `/api/health` returned success.

## Proposed Work Plan

1. Committed and deployed the targeted-registration/read-only-run2 architecture while batch 0002 remained blocked.
2. Recorded the exact operator approval, restored a fresh clone from the approved backup, and independently attested its runtime isolation.
3. Executed batch 0002 twice and proved run2 zero audit, record, and database-size deltas with exact outcome equality.
4. Created and restore-verified the final clone backup before removing only the clone resources.
5. Kept primary promotion and batches 0003-0044 outside this authorization.

## Validation Plan

- Focused executor, preflight, manual-review, content-identity, routing, and usage telemetry tests passed during the architecture phase.
- Pre-execution preflight passed all six approval, identity, backup, and clone gates.
- Run1 and run2 passed; read-only run2 produced zero logical, audit, and physical database growth.
- Final backup restore equality and retention metadata passed.
- Primary health/counts passed and no T-615 clone container, network, or database remains.
- Final `make local-ci PYTHON=.venv/bin/python` passed 534 tests, UI static validation, a 544-file security scan, 251 Markdown link checks, 192 handoff checks, and 5 canonical document metadata checks.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- T-613 batch-0002 SHA `6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1`.
- Restore-verified primary backup `ai_quant-20260721T060949Z`, dump SHA `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`.

## Blockers

- None for T-615.
- T-616 and every remaining batch are unauthorized until a new exact execution unit, SHA-bound approval, fresh backup, and attestation are provided.

## Files Touched

- `app/service_modules/research_reports.py`: domain validation for targeted files and opaque read-only batch state.
- `app/services.py`: facade plumbing for the domain helpers.
- `app/api.py`, `app/api_routes.py`: read-only batch-state route.
- `app/service_modules/usage_metrics.py`: excludes the batch-state verifier from telemetry writes.
- `scripts/execute_research_report_clone_batch.py`: exact registration and read-only run2; supports deterministic T-613 batches 0001-0044.
- `scripts/prepare_research_report_clone_batch.py`: emits T-615 plans and approval requests for later batches.
- `scripts/audit_research_report_manual_review.py`: redacted local PDF/OCR diagnosis.
- `tests/test_audit_research_report_manual_review.py`, `tests/test_execute_research_report_clone_batch.py`, `tests/test_research_report_content_identity.py`: focused safety regressions.
- `docs/api-contracts.md`, `tasks/todo.md`: contract and roadmap decisions.

## Commands Run

```bash
.venv/bin/python -m unittest \
  tests.test_audit_research_report_manual_review \
  tests.test_execute_research_report_clone_batch \
  tests.test_prepare_research_report_clone_batch \
  tests.test_research_report_content_identity \
  tests.test_usage_metrics -v

.venv/bin/python scripts/audit_research_report_manual_review.py \
  --preflight artifacts/t614-clone-batch/batch-0001-preflight-ready.json \
  --filesystem-root /home/xionglei/文档/6大投行研报汇总 \
  --report-id rr_009533636222e1c2 \
  --report-id rr_046cb3e7368122b3 \
  --report-id rr_06048550928948ca \
  --pages 3 --local-ocr-sample \
  --output artifacts/t615-research-recovery-decision/manual-review-audit.json

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --batch-id t613-batch-0002 \
  --expected-batch-sha256 6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1 \
  --output artifacts/t615-research-recovery-decision/batch-0002-preflight.json \
  --approval-output artifacts/t615-research-recovery-decision/batch-0002-approval-request.json

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant --output-dir data/local/backups/postgres \
  --retention-days 7 --timeout-seconds 3600

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --batch-id t613-batch-0002 \
  --expected-batch-sha256 6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1 \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json \
  --approval artifacts/t615-research-recovery-decision/batch-0002-approval.json \
  --clone-attestation artifacts/t615-research-recovery-decision/batch-0002-clone-attestation.json \
  --output artifacts/t615-research-recovery-decision/batch-0002-preflight-ready.json

docker exec sotck_quant-t615-clone-app \
  python /app/scripts/execute_research_report_clone_batch.py \
  --preflight /evidence/batch-0002-preflight-ready.json \
  --approval /evidence/batch-0002-approval.json \
  --clone-attestation /evidence/batch-0002-clone-attestation.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json \
  --base-url http://127.0.0.1:18003 \
  --output /output/t615-clone-execution-1.json \
  --confirm-plan-sha256 0ec683ac993d4e6017f7ccecc67c659cecaa235e50e18f95215229f587441907 \
  --confirm-batch-sha256 6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1 \
  --execute --acknowledge-opinion-boundary \
  --confirm-targeted-registration --confirm-clone-target

# The second invocation used the same gates plus:
--prior-run /output/t615-clone-execution-1.json \
--output /output/t615-clone-execution-2.json

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant_t615_clone_20260721 \
  --output-dir data/local/backups/postgres \
  --retention-days 7 --timeout-seconds 3600

make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
```

Result:

- Passed: 26 focused tests.
- Passed: architecture-phase repository-wide CI with 534 tests, UI static check, security scan of 541 files, 251 Markdown links, 192 handoffs, and 5 canonical document metadata checks.
- Passed: all three manual-review files retained exact T-614 content identities and are locally OCR-extractable.
- Passed: fresh primary backup and restore equality; batch-0002 manifest/batch/raw/backup/approval/attestation gates.
- Passed: run1 250/250 and run2 250/250; 242 text-indexed, 8 manual-review, 1,826 evidence; run2 zero ingest, zero audit/record/database-size delta, and exact outcome equality.
- Passed: final clone backup restore equality, clone cleanup, primary count/size preservation, main service health, and artifact redaction scan.
- Failed: none.
- Not run: vacuum, because the measured clone dead-tuple thresholds were not reached; primary promotion and remaining batches, because they were not authorized.
- Passed: final post-documentation repository-wide CI with 534 tests, UI static check, security scan of 544 files, 251 Markdown links, 192 handoffs, and 5 canonical document metadata checks.

## Evidence

- `artifacts/t615-research-recovery-decision/manual-review-audit.json`: produced by the manual-review audit script on 2026-07-21; local workstation; local-only; no path/name/text body; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/batch-0002-approval.json`: recorded from the exact operator authorization on 2026-07-21; local-only; binds the manifest and batch SHA; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/batch-0002-clone-attestation.json`: produced by the runtime probe on 2026-07-21; local-only sensitive runtime identity; status passed; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/batch-0002-preflight-ready.json`: produced by the preflight script on 2026-07-21; local-only sensitive opaque identities; all six gates passed; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/runtime/t615-clone-execution-1.json`: produced by the clone executor at 2026-07-21T07:15:41Z; local-only and sensitive; file SHA `cee7f1e2067cccb8fff5dedfad1e35f7b8f7ff058052b140ddb32815f4b8af39`; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/runtime/t615-clone-execution-2.json`: produced by the clone executor at 2026-07-21T07:16:42Z; local-only and sensitive; file SHA `72740a4dda3b3f82ff77970b85dc1a29ec71dddb05e213c2f93e9ca2adb6ffdf`; not valid for non-local release.
- `data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json`: produced by `postgres_durable_backup.py` on 2026-07-21; local Docker Compose; local-only sensitive backup metadata; restore verified; not valid for non-local release.
- `data/local/backups/postgres/ai_quant_t615_clone_20260721-20260721T072013Z.manifest.json`: produced by `postgres_durable_backup.py` at 2026-07-21T07:20:13Z; local Docker Compose; local-only and sensitive; restore verified and retained through 2026-07-28; manifest SHA `21876c41b9e64023e6e7b618e297844b8d59370ab31dc056bf2a844aea5393c6`; not valid for non-local release.

## Decisions

- Use exact targeted registration, not full-registry recursive scan, for every approved recovery batch.
- Make run2 a read-only identity/outcome verification. A second mutation workload is not required to prove idempotency.
- Use ordinary `VACUUM (ANALYZE)` only after a clone backup when `n_dead_tup / max(n_live_tup,1) > 10%` or `n_dead_tup > 10000`; never automate `VACUUM FULL`.
- Validate batch 0002 as one independently approved batch before considering five-batch persistent-clone segments. Segment approval must bind every included batch SHA and cannot weaken per-batch preflight/attestation.
- Keep primary promotion entirely separate from clone execution approval.

## Risks and Open Questions

- The source and final clone backups are retained through 2026-07-28. They are local-only recovery evidence and must not be presented as non-local release proof.
- Eight batch-0002 documents remain in manual review. A successful batch does not assert that their citation text quality is acceptable.
- Batch 0002 met the run2 thresholds, but one successful batch does not by itself authorize or fully de-risk a five-batch persistent clone.
- Persistent clones reduce restore overhead but increase accumulated-state and partial-segment rollback risk; T-616 must decide and bind the next exact execution unit.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No. `SystemService` only validates facade input and delegates file selection/state projection to `app/service_modules/research_reports.py`.
- Domain placement: path safety and batch-state projection live in the research-report domain module.
- Focused regression: targeted scan escape tests, opaque read-only state test, executor run2 zero-POST test, and usage telemetry suite.
- Contract/boundary changes: additive scan field and GET endpoint only; no storage schema, UI, paper-only/no-broker, fact/opinion, or primary-write boundary change.

## Next Steps

1. Under T-616, compare one-batch fresh clones with at-most-five-batch persistent-clone segments and generate the next exact approval request.
2. Do not create a batch-0003 clone or execute any remaining batch without new SHA-bound human authorization and fresh runtime evidence.
3. Continue normal primary service and daily-timer observation independently of research recovery execution.

## Next Recommended Action

Prepare the T-616 decision package; keep all remaining 42 batches blocked until the operator approves an exact SHA-bound execution unit.
