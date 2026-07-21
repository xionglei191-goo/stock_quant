# Handoff: T-615 Research Recovery Execution Architecture

## Metadata

- Status: DOING
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Related tasks: T-613, T-614, T-615
- Artifact classification: local-only

## Objective

Resolve the T-614 parser, registry-scan, idempotency-write, and capacity questions; provide a safer execution architecture and an exact batch-0002 approval request without running batch 0002 or touching primary data.

## Scope

- In scope: three manual-review PDFs, targeted batch registration, read-only run2 verification, MVCC/vacuum policy, later-batch approval units, batch-0002 dry-run, tests, contracts, and roadmap state.
- Out of scope: batch-0002 execution, primary writes or promotion, raw/duplicate/OpenSearch deletion, automatic external OCR, fact/training promotion, brokers, and live trading.

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

- Completed: parser diagnosis, targeted registration, read-only batch-state API, executor update, focused regressions, API contract, capacity/vacuum decision, batch-0002 raw binding, and approval request generation.
- In progress: final verification and commit/push.
- Not started: approval, clone creation/attestation, and batch-0002 execution.
- Blocked: batch 0002 requires new human authorization and a fresh clone attestation; T-614 approval and runtime evidence cannot be reused.

## Current Findings

- IDs `rr_009533636222e1c2`, `rr_046cb3e7368122b3`, and `rr_06048550928948ca` are valid, unencrypted image-only PDFs. The sampled first three pages contain no text or font rows and three image rows each. Local Tesseract extracted 3,606, 1,052, and 3,621 characters from the first page respectively.
- Parser decision: keep all three in manual review until local OCR output quality is accepted. Permit local OCR only inside an approved isolated clone; do not invoke external OCR automatically and do not classify these files as broken.
- `relative_paths` restricts scan registration to the approved batch and rejects absolute paths, traversal, symlinks, duplicates, unavailable files, and extension mismatches.
- Run2 now recomputes raw identity locally and calls only `GET /api/research-reports/batch-state`. That response is path/name/body-free and excluded from audit and usage telemetry writes.
- T-614 run2's 22.2 MiB / 254-audit increase is avoidable write amplification, not required research data growth. Batch 0002 must prove run2 audit and logical row deltas are zero and database growth is at most 1 MiB.
- Primary currently has 21 dead `audit_log` tuples and 92 dead `records` tuples against 35,385 and 32,319 live rows. There is no current need for manual vacuum on primary.
- Batch 0002 is 250 PDFs / 573,286,759 bytes. Batch SHA is `6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1`; raw identity SHA is `dae5a5a9ba73f5dcfbf2894e9ce596e7700dac80999225735986ab05e5b55529`.
- Fresh primary backup `ai_quant-20260721T060949Z` passed restore verification at `32319 records / 35385 audit / 28365474 market bars` and research state `15 / 15 / 112 / 15 / 15 / 3`. Dump SHA is `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`, retained through 2026-07-28.
- The backup-bound batch-0002 plan SHA is `0ec683ac993d4e6017f7ccecc67c659cecaa235e50e18f95215229f587441907`. It remains blocked only on `exact_human_approval_verified` and `independent_clone_attestation_verified`; `execution_performed=false` and no clone was created.

## Proposed Work Plan

1. Commit and deploy the targeted-registration/read-only-run2 architecture; keep batch 0002 blocked.
2. If explicitly authorized with the exact manifest/batch confirmation, record approval against the current backup-bound plan and attest a fresh clone.
3. Execute batch 0002 twice, measure audit/record/database-size deltas, and require the read-only-run2 thresholds before considering a five-batch persistent-clone segment.
4. Keep any primary promotion behind a separate diff, backup, approval, rollback, and post-promotion verification gate.

## Validation Plan

- Run focused executor, preflight, manual-review, content-identity, routing, and usage telemetry tests.
- Run `make local-ci PYTHON=.venv/bin/python` and `python3 scripts/check_handoffs.py`.
- Verify batch-0002 preflight has exactly the two expected failed gates and no mutation.
- Verify primary health/counts and that no T-615 clone container, network, or database exists.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- T-613 batch-0002 SHA `6f1b63257499f3325198a91cc692cc1e8d421ee20c7e04bbae17a1695dd641d1`.
- Restore-verified primary backup `ai_quant-20260721T060949Z`, dump SHA `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`.

## Blockers

- The current batch-0002 plan cannot execute because it has no exact human approval or clone attestation. Generic continuation is not approval.

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

make local-ci PYTHON=.venv/bin/python
```

Result:

- Passed: 26 focused tests.
- Passed: repository-wide CI with 534 tests, UI static check, security scan of 541 files, 251 Markdown links, 192 handoffs, and 5 canonical document metadata checks.
- Passed: all three manual-review files retained exact T-614 content identities and are locally OCR-extractable.
- Passed: fresh primary backup and restore equality; batch-0002 manifest/batch/raw/backup gates; exact expected approval and attestation gates remained closed.
- Failed: none.
- Not run: batch-0002 execution, by design and without authorization.

## Evidence

- `artifacts/t615-research-recovery-decision/manual-review-audit.json`: produced by the manual-review audit script on 2026-07-21; local workstation; local-only; no path/name/text body; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/batch-0002-preflight.json`: produced by the preflight script on 2026-07-21; local workstation; local-only and sensitive because it contains opaque report identities; not valid for non-local release.
- `artifacts/t615-research-recovery-decision/batch-0002-approval-request.json`: produced by the preflight script on 2026-07-21; local-only; no raw path/body; pending approval; not valid for non-local release.
- `data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json`: produced by `postgres_durable_backup.py` on 2026-07-21; local Docker Compose; local-only sensitive backup metadata; restore verified; not valid for non-local release.

## Decisions

- Use exact targeted registration, not full-registry recursive scan, for every approved recovery batch.
- Make run2 a read-only identity/outcome verification. A second mutation workload is not required to prove idempotency.
- Use ordinary `VACUUM (ANALYZE)` only after a clone backup when `n_dead_tup / max(n_live_tup,1) > 10%` or `n_dead_tup > 10000`; never automate `VACUUM FULL`.
- Validate batch 0002 as one independently approved batch before considering five-batch persistent-clone segments. Segment approval must bind every included batch SHA and cannot weaken per-batch preflight/attestation.
- Keep primary promotion entirely separate from clone execution approval.

## Risks and Open Questions

- The backup is retained through 2026-07-28. Approval/attestation and any clone execution must occur while the backup freshness and retention gates remain valid.
- Local OCR extractability does not prove citation quality. The three documents need text-quality sampling in the approved clone before closing their manual reviews.
- The 1 MiB run2 physical-growth threshold has not yet been measured against a real PostgreSQL clone with the new executor.
- Persistent clones reduce restore overhead but increase state-accumulation risk; do not enable them until batch 0002 meets all thresholds.

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

1. Finish full CI, update this handoff with exact results, commit, and push.
2. Obtain exact SHA-bound human approval before creating or mutating any batch-0002 clone.
3. After approval, create and independently attest the clone; do not reuse T-614 runtime evidence.

## Next Recommended Action

Ask the human operator for the exact batch-0002 confirmation in the generated approval request; do not execute the batch from a generic “continue”.
