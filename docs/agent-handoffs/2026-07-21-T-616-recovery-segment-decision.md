# Handoff: T-616 Research Recovery Segment Decision

## Metadata

- Status: DOING
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Related tasks: T-613, T-614, T-615, T-616
- Artifact classification: local-only

## Objective

Compare one-batch fresh clones with an at-most-five-batch persistent clone, choose the next bounded recovery unit, and generate its exact SHA-bound approval package without creating a clone or mutating primary data.

## Scope

- In scope: observed-cost comparison, accumulated-state risk, dead-tuple projection, attestation/checkpoint capability review, batch-0003 raw binding, approval request generation, task ownership correction, tests, and roadmap state.
- Out of scope: batch execution, clone creation, primary writes or promotion, raw/duplicate/OpenSearch deletion, external OCR, fact/training promotion, brokers, and live trading.

## Background

T-615 proved that targeted registration plus read-only run2 eliminates the second-run audit, logical-row, and physical-storage growth. The remaining decision is whether repeated clone restore/backup cost justifies widening the execution unit beyond one batch.

## Problem Statement

A five-batch persistent clone mechanically saves repeated restore and backup work, but the current attestation binds only a clone restored from the primary backup. It cannot attest a clone that already contains prior segment batches, and there is no checkpoint/resume contract for a partial segment failure.

## Expected Deliverables

- A fact/assumption-separated cost and risk comparison.
- A conservative next execution-unit decision.
- A content-bound batch-0003 preflight and exact approval request.
- Explicit blocked gates and proof that no execution occurred.

## Current State

- Completed: T-615 metric extraction, option comparison, persistent-state contract review, batch-0003 raw binding, exact approval request generation, task mapping fix, focused tests, roadmap update, and handoff.
- In progress: commit/push and exact approval handoff to the operator.
- Not started: exact human approval, fresh clone attestation, batch-0003 double run, final clone backup, and clone cleanup.
- Blocked: batch 0003 requires exact SHA-bound approval and a new independent clone attestation. A generic continuation is not approval.

## Current Findings

- T-615 observed 1,179.372 seconds for run1, 7.54 seconds for read-only run2, 537.637 seconds for the final backup, and approximately 775 seconds from approval to completed clone attestation. The setup value is a conservative proxy that includes restore and attestation work, not dedicated restore telemetry.
- Mechanical projection: five fresh clones take about 208.3 minutes; one five-batch persistent clone takes about 120.8 minutes, saving about 87.5 minutes or 42.0%. This is an estimate, not execution evidence.
- Linear dead-tuple projection from T-615 reaches 6,220 dead tuples against about 43,994 live records after five batches, or 14.1%. The projection is not a forecast, but it crosses the 10% maintenance threshold and therefore weakens the five-batch choice.
- The current attestation contract validates backup-restored source and research counts. It cannot bind accumulated clone state before batch 0004, and no segment checkpoint/resume/abort artifact exists.
- Decision: do not authorize a persistent clone yet. Use one fresh clone for batch 0003, then reconsider a segment only after a second optimized batch and after accumulated-state attestation plus checkpoint/resume rules exist.
- Batch 0003 binds 250 PDFs / 484,140,668 bytes. Batch SHA is `c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0`; raw identity SHA is `47002ba169b0c836d146b29dd700be7e8a2cee8b2d2aa6b9cffacdee09d79d8f`.
- The plan SHA is `2393788a3e594310c1c1e04686092cf53e624bc887303f2dfee4a3167fb421c2`. All manifest, batch, raw, and retained restore-verified backup gates pass. Only exact approval and independent clone attestation remain closed.
- Preflight reports `execution_performed=false`; no clone was created and primary remains `32319 records / 35385 audit / 28365474 market bars`.

## Proposed Work Plan

1. Correct later-batch task ownership and regenerate the batch-0003 plan.
2. Run focused and repository-wide verification, then commit and push the decision package code/docs.
3. Stop until the operator provides the exact batch-0003 confirmation.
4. After exact approval, create a fresh clone, independently attest it, double-run only batch 0003, restore-verify the final backup, and remove only clone resources.

## Validation Plan

- Run the focused batch-preparation suite and Python compilation.
- Validate JSON artifacts and scan them for local paths and inline configuration values.
- Run `make local-ci PYTHON=.venv/bin/python` and `python3 scripts/check_handoffs.py`.
- Verify primary health/counts and absence of T-616 clone resources.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- Batch-0003 SHA `c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0`.
- Restore-verified primary backup `ai_quant-20260721T060949Z`, dump SHA `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`, retained through 2026-07-28.

## Blockers

- Exact approval must bind the manifest and batch SHA shown above.
- A new clone attestation must bind plan SHA `2393788a3e594310c1c1e04686092cf53e624bc887303f2dfee4a3167fb421c2` and the retained backup.
- Persistent clone execution remains unauthorized.

## Files Touched

- `scripts/prepare_research_report_clone_batch.py`: map governed later batches 0003-0044 to T-616 and reject out-of-range IDs.
- `tests/test_prepare_research_report_clone_batch.py`: protect T-614/T-615/T-616 ownership and upper-bound rejection.
- `tasks/todo.md`: record the option decision, exact next batch, gates, and artifact locations.
- `docs/agent-handoffs/2026-07-21-T-616-recovery-segment-decision.md`: current cross-group handoff.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_prepare_research_report_clone_batch -v
.venv/bin/python -m py_compile scripts/prepare_research_report_clone_batch.py tests/test_prepare_research_report_clone_batch.py

.venv/bin/python scripts/prepare_research_report_clone_batch.py \
  --batch-id t613-batch-0003 \
  --expected-batch-sha256 c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0 \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json \
  --output artifacts/t616-research-recovery-segment/batch-0003-preflight.json \
  --approval-output artifacts/t616-research-recovery-segment/batch-0003-approval-request.json

make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
```

Result:

- Passed: 6 focused batch-preparation tests and Python compilation.
- Passed: batch-0003 manifest, batch, raw content, and backup gates; JSON validity and redaction scan.
- Passed: repository-wide CI with 535 tests, UI static check, security scan of 544 files, 252 Markdown links, 193 handoffs, and 5 canonical document metadata checks.
- Failed: none.
- Not run: batch execution, clone creation, primary writes, deletion, and persistent-clone execution by design.

## Evidence

- `artifacts/t616-research-recovery-segment/segment-strategy-decision.json`: manually assembled from T-615 measured evidence on 2026-07-21; local-only; fact/assumption separated; no paths or secrets; not valid for non-local release; SHA `90f4ec29bd1d7a30e3693bbd7241f0c83cda9a3ca80e3cd59bfcd50a9146334a`.
- `artifacts/t616-research-recovery-segment/batch-0003-preflight.json`: produced by `prepare_research_report_clone_batch.py` on 2026-07-21; local-only and sensitive because it contains opaque identities; no execution; not valid for non-local release; SHA `4c60f3029ac8450b82d5ce343097bcaea7df0a68063974374f10b974457ee458`.
- `artifacts/t616-research-recovery-segment/batch-0003-approval-request.json`: produced by the same command; local-only; no path/body; pending approval; not valid for non-local release; SHA `b70d0ea525745d5a9d8c9d20ce1bf9de8d25e6085dca64b77fc3ffd7c78faa4f`.
- `data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json`: produced by `postgres_durable_backup.py`; local Docker Compose; local-only sensitive backup metadata; restore verified and retained through 2026-07-28; not valid for non-local release.

## Decisions

- Select one fresh-clone batch 0003 as the next execution unit; do not authorize batches 0004-0007 or a persistent clone.
- Treat the 42.0% time saving as a planning estimate only.
- Require a dedicated accumulated-state attestation and checkpoint/resume/abort contract before widening to a persistent segment.
- Preserve the per-batch run2 zero record/audit/database-byte thresholds and existing vacuum policy.
- Keep primary promotion entirely separate.

## Risks and Open Questions

- The retained backup expires on 2026-07-28; approval and attestation must pass freshness gates before execution.
- Batch 0003 parser/manual-review distribution is unknown until run1.
- A single extra batch may still be insufficient to choose the optimal segment size; the next review should use batch 0002 and 0003 observed distributions.
- The time model holds backup duration constant even though accumulated research state grows.

## Handoff Checklist

- [x] Code changes completed
- [x] Full tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Finish full CI and handoff validation, then commit and push.
2. Obtain the exact generated approval; do not treat a generic continuation as approval.
3. After approval, create and attest a fresh clone before any batch-0003 mutation.

## Next Recommended Action

Ask the operator for the exact batch-0003 confirmation from the generated approval request; keep persistent clone execution blocked.
