# Handoff: T-616 Research Recovery Segment Decision

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Related tasks: T-613, T-614, T-615, T-616
- Artifact classification: local-only

## Objective

Compare one-batch fresh clones with an at-most-five-batch persistent clone, choose the next bounded recovery unit, and prove batch 0003 through an exact operator-approved double run in a fresh isolated clone without T-616 executor writes or deletes on primary.

## Scope

- In scope: observed-cost comparison, accumulated-state risk, dead-tuple projection, attestation/checkpoint capability review, batch-0003 raw binding and approval, fresh clone restore/attestation, double run, final backup, clone cleanup, task ownership correction, tests, and roadmap state.
- Out of scope: T-616 executor writes or deletes on primary, primary promotion, batches 0004-0044, raw/duplicate/OpenSearch deletion, external OCR, fact/training promotion, brokers, and live trading.

## Background

T-615 proved that targeted registration plus read-only run2 eliminates the second-run audit, logical-row, and physical-storage growth. The remaining decision is whether repeated clone restore/backup cost justifies widening the execution unit beyond one batch.

## Problem Statement

A five-batch persistent clone mechanically saves repeated restore and backup work, but the current attestation binds only a clone restored from the primary backup. It cannot attest a clone that already contains prior segment batches, and there is no checkpoint/resume contract for a partial segment failure.

## Expected Deliverables

- A fact/assumption-separated cost and risk comparison.
- A conservative next execution-unit decision.
- A content-bound batch-0003 preflight and exact approval request.
- A fresh clone double-run proof, restore-verified final backup, cleanup evidence, and explicit primary-write attribution.

## Current State

- Completed: option comparison, persistent-state contract review, batch-0003 raw binding, exact approval, task mapping fix, fresh clone restore/attestation, run1/run2, idempotency/capacity verification, final restore-verified backup, clone cleanup, primary attribution review, roadmap closeout, and tests.
- In progress: none.
- Not started: T-617 accumulated-state attestation/checkpoint work and all batches 0004-0044.
- Blocked: none for T-616. Persistent clone and later batches remain unauthorized under T-617.

## Current Findings

- T-615 observed 1,179.372 seconds for run1, 7.54 seconds for read-only run2, 537.637 seconds for the final backup, and approximately 775 seconds from approval to completed clone attestation. The setup value is a conservative proxy that includes restore and attestation work, not dedicated restore telemetry.
- Mechanical projection: five fresh clones take about 208.3 minutes; one five-batch persistent clone takes about 120.8 minutes, saving about 87.5 minutes or 42.0%. This is an estimate, not execution evidence.
- Linear dead-tuple projection from T-615 reaches 6,220 dead tuples against about 43,994 live records after five batches, or 14.1%. The projection is not a forecast, but it crosses the 10% maintenance threshold and therefore weakens the five-batch choice.
- The current attestation contract validates backup-restored source and research counts. It cannot bind accumulated clone state before batch 0004, and no segment checkpoint/resume/abort artifact exists.
- Decision: do not authorize a persistent clone yet. Use one fresh clone for batch 0003, then reconsider a segment only after a second optimized batch and after accumulated-state attestation plus checkpoint/resume rules exist.
- Batch 0003 binds 250 PDFs / 484,140,668 bytes. Batch SHA is `c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0`; raw identity SHA is `47002ba169b0c836d146b29dd700be7e8a2cee8b2d2aa6b9cffacdee09d79d8f`.
- The plan SHA is `2393788a3e594310c1c1e04686092cf53e624bc887303f2dfee4a3167fb421c2`. Exact approval and the fresh clone attestation passed all six gates. Approval, attestation, and ready-preflight file SHAs are `abc335b2916ece2781792dace8a9a182eed0316268f890401f5f516e871337b3`, `bdffac525519475d6348d127dbfb6da283bf844adc8f4eb75d873e3a5c0ccc44`, and `fc5f06b6415ad0ec2df9ab471fa215fe375df02e0fc2dd7529727d821c095c37`.
- Fresh clone `ai_quant_t616_clone_20260721` restored at `32319 records / 35385 audit / 28365474 market bars`. Runtime attestation proved an internal two-member network, primary service unreachable, raw and root filesystem read-only, no host ports, local object/search, and exact database/plan/backup identity.
- Run1 passed 250/250: 237 text-indexed, 13 manual-review, 1,810 citation evidence, 250 new ingests, 0 failures, and 1,180.946 seconds. It used targeted relative paths, performed no deletes, and preserved raw/OpenSearch.
- Run1 changed only the clone from `32319/35385/28365474` to `34643/36150/28365474`; database size changed `15502007319 -> 15512083479`, a 10,076,160-byte increase.
- Run2 passed 250/250 through read-only batch state in 6.418 seconds. It created 0 ingests, matched run1 outcomes after excluding the expected ingest flag, and produced zero records/audit/market-bars/database-byte delta.
- Post-run dead tuples were 1,239/34,643 for records and 0/36,150 for audit; no vacuum threshold was reached.
- Final clone backup `ai_quant_t616_clone_20260721-20260721T110934Z` passed restore equality at `34643/36150/28365474` and research state `265/265/1922/15/15/3`. Dump SHA is `9e29de55a7ca5e966b4114c19f35cd173465d5d969cc068e4f0606ad62a789ae`, size 838,083,052 bytes, retained through 2026-07-28.
- Clone application, database, and isolated network were removed after backup verification.
- Primary did change during the execution window, but not through the T-616 executor: the pre-existing `ai-quant-daily-update.service` ran successfully from 18:49:28 to 19:06:45 CST and changed primary from `32319/35385/28365474` to `32325/35405/28367250`. Read-only audit grouping attributes the 20 audit events to normal API/connectors. No rollback or deletion was performed.

## Proposed Work Plan

1. Correct later-batch task ownership and regenerate the batch-0003 plan.
2. Obtain exact approval, restore and independently attest a fresh clone, and execute only batch 0003 twice.
3. Require run2 zero logical/audit/physical delta, create a restore-verified final backup, then remove only clone resources.
4. Attribute any primary drift to an independently identified producer instead of claiming blanket zero change.
5. Keep persistent clone and batches 0004-0044 blocked for T-617 architecture.

## Validation Plan

- Focused batch-preparation tests and Python compilation passed.
- Approval, preflight, attestation, run1/run2, backup JSON, and redaction checks passed.
- Clone run2 zero-delta and exact outcome comparison passed.
- Final backup restore equality and clone cleanup passed.
- Primary service health passed; primary drift was attributed to the successful daily-update service, not T-616.
- Final `make local-ci PYTHON=.venv/bin/python` passed with 535 tests, UI static checks, a 545-file security scan, 252 Markdown links, 193 handoffs, and 5 canonical document metadata checks.

## Dependencies

- T-613 manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`.
- Batch-0003 SHA `c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0`.
- Restore-verified primary backup `ai_quant-20260721T060949Z`, dump SHA `784300659b51110d8c9779c8af4dbab832d2f2b0239148a077ad5b2d4e1acb99`, retained through 2026-07-28.

## Blockers

- None for T-616.
- Persistent clone execution and batches 0004-0044 remain unauthorized until T-617 implements and validates accumulated-state attestation, checkpoint/resume/abort, and scheduler-quiescence evidence.

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

.venv/bin/python scripts/probe_research_report_clone_runtime.py \
  --app-container sotck_quant-t616-clone-app \
  --postgres-container sotck_quant-postgres-1 \
  --isolated-network ai-quant-t616-isolated \
  --database-name ai_quant_t616_clone_20260721 \
  --base-url http://127.0.0.1:18004 \
  --backup-manifest data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json \
  --plan artifacts/t616-research-recovery-segment/batch-0003-preflight-approved.json \
  --output artifacts/t616-research-recovery-segment/batch-0003-clone-attestation.json

docker exec sotck_quant-t616-clone-app \
  python /app/scripts/execute_research_report_clone_batch.py \
  --preflight /evidence/batch-0003-preflight-ready.json \
  --approval /evidence/batch-0003-approval.json \
  --clone-attestation /evidence/batch-0003-clone-attestation.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json \
  --base-url http://127.0.0.1:18004 \
  --output /output/t616-clone-execution-1.json \
  --confirm-plan-sha256 2393788a3e594310c1c1e04686092cf53e624bc887303f2dfee4a3167fb421c2 \
  --confirm-batch-sha256 c029846b6596ff28e85e385e8eca2fe9c69fc8e31d37e01ef180ea8bd61a74c0 \
  --execute --acknowledge-opinion-boundary \
  --confirm-targeted-registration --confirm-clone-target

# Run2 used the same immutable gates plus the prior-run artifact.
--prior-run /output/t616-clone-execution-1.json \
--output /output/t616-clone-execution-2.json

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant_t616_clone_20260721 \
  --output-dir data/local/backups/postgres \
  --retention-days 7 --timeout-seconds 3600

make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
```

Result:

- Passed: 6 focused batch-preparation tests and Python compilation.
- Passed: batch-0003 manifest, batch, raw content, and backup gates; JSON validity and redaction scan.
- Passed: repository-wide CI with 535 tests, UI static check, security scan of 545 files, 252 Markdown links, 193 handoffs, and 5 canonical document metadata checks.
- Passed: six-gate clone preflight and fresh runtime attestation.
- Passed: run1 250/250 and run2 250/250; 237 text-indexed, 13 manual-review, 1,810 evidence; run2 zero ingest, zero records/audit/database-byte delta, and exact outcome equality.
- Passed: final clone backup restore equality, clone cleanup, primary service health, timer/service attribution, and artifact redaction scan.
- Failed: none.
- Not run: vacuum because thresholds were not reached; primary promotion and persistent-clone/later-batch execution because they were not authorized.

## Evidence

- `artifacts/t616-research-recovery-segment/segment-strategy-decision.json`: manually assembled from T-615 measured evidence on 2026-07-21; local-only; fact/assumption separated; no paths or secrets; not valid for non-local release; SHA `90f4ec29bd1d7a30e3693bbd7241f0c83cda9a3ca80e3cd59bfcd50a9146334a`.
- `artifacts/t616-research-recovery-segment/batch-0003-preflight.json`: produced by `prepare_research_report_clone_batch.py` on 2026-07-21; local-only and sensitive because it contains opaque identities; no execution; not valid for non-local release; SHA `4c60f3029ac8450b82d5ce343097bcaea7df0a68063974374f10b974457ee458`.
- `artifacts/t616-research-recovery-segment/batch-0003-approval-request.json`: produced by the same command; local-only; no path/body; pending approval; not valid for non-local release; SHA `b70d0ea525745d5a9d8c9d20ce1bf9de8d25e6085dca64b77fc3ffd7c78faa4f`.
- `artifacts/t616-research-recovery-segment/batch-0003-approval.json`: recorded from the exact operator approval at 2026-07-21T10:30:11Z; local-only; binds manifest and batch SHA; not valid for non-local release; SHA `abc335b2916ece2781792dace8a9a182eed0316268f890401f5f516e871337b3`.
- `artifacts/t616-research-recovery-segment/batch-0003-clone-attestation.json`: produced by the runtime probe at 2026-07-21T10:44:51Z; local-only sensitive runtime identity; status passed; not valid for non-local release; SHA `bdffac525519475d6348d127dbfb6da283bf844adc8f4eb75d873e3a5c0ccc44`.
- `artifacts/t616-research-recovery-segment/batch-0003-preflight-ready.json`: produced by the preflight script after approval and attestation; local-only sensitive opaque identities; all six gates passed; not valid for non-local release; SHA `fc5f06b6415ad0ec2df9ab471fa215fe375df02e0fc2dd7529727d821c095c37`.
- `artifacts/t616-research-recovery-segment/runtime/t616-clone-execution-1.json`: produced by the clone executor at 2026-07-21T11:06:18Z; local-only and sensitive; file SHA `cf158d66fbf61f1cf5ab02cb8bfa913805df56203e07c13f6b321cddb0710afd`; not valid for non-local release.
- `artifacts/t616-research-recovery-segment/runtime/t616-clone-execution-2.json`: produced by the clone executor at 2026-07-21T11:08:09Z; local-only and sensitive; file SHA `44b73dc60e095040ff722e1df8871eee921ae81fa492efeab5b5fcc5ea6f565a`; not valid for non-local release.
- `data/local/backups/postgres/ai_quant-20260721T060949Z.manifest.json`: produced by `postgres_durable_backup.py`; local Docker Compose; local-only sensitive backup metadata; restore verified and retained through 2026-07-28; not valid for non-local release.
- `data/local/backups/postgres/ai_quant_t616_clone_20260721-20260721T110934Z.manifest.json`: produced by `postgres_durable_backup.py` at 2026-07-21T11:09:34Z; local Docker Compose; local-only and sensitive; restore verified and retained through 2026-07-28; manifest SHA `0c3e24a856786ca825628b4708166c463fd676e7c1f4d529f5a99ac50b15579b`; not valid for non-local release.

## Decisions

- Select one fresh-clone batch 0003 as the next execution unit; do not authorize batches 0004-0007 or a persistent clone.
- Treat the 42.0% time saving as a planning estimate only.
- Require a dedicated accumulated-state attestation and checkpoint/resume/abort contract before widening to a persistent segment.
- Preserve the per-batch run2 zero record/audit/database-byte thresholds and existing vacuum policy.
- Keep primary promotion entirely separate.

## Risks and Open Questions

- The source and final clone backups expire on 2026-07-28 and remain local-only evidence.
- Batch 0003 has 13 manual-review documents; successful ingest does not assert citation-text quality for them.
- Two optimized batches have consistent time and storage profiles, but the optimal segment size is still unknown without accumulated-state attestation and checkpoint behavior.
- The time model holds backup duration constant even though accumulated research state grows.
- The daily timer can overlap clone measurement windows. T-617 must require scheduler quiescence or an explicit external-write attribution baseline before claiming primary zero change.

## Handoff Checklist

- [x] Code changes completed
- [x] Full tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Under T-617, implement accumulated-state attestation and checkpoint/resume/abort contracts before considering a persistent clone.
2. Add scheduler-quiescence or attributable external-write evidence to the next execution window.
3. Do not prepare or execute batch 0004 until a new exact SHA-bound plan and approval exist.

## Next Recommended Action

Implement T-617 safety architecture; keep all remaining 41 batches and primary promotion blocked.
