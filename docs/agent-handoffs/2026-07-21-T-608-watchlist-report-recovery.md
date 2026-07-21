# Handoff: T-608 Five-Company Research Evidence Recovery And Controlled Operation

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows; Governance, Security, and Compliance; Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/pm_docs_review`
- Branch/worktree: `main`, shared dirty worktree; no commit made by this agent
- Related tasks: T-603, T-604, T-609, T-611, T-612
- Artifact classification: local-only
- Risk level: high

## Objective

Recover a bounded, identity-proven research-report evidence slice for AAPL, NVDA, MSFT, 300750, and 600519; prove it twice in an isolated clone; promote that exact slice into local primary PostgreSQL; and demonstrate one controlled product refresh and its installed schedule without weakening the opinion/reference-only or paper-only boundaries.

This objective is complete. T-608 proves the five-company slice and one current local operating cycle; it does not claim recovery of the full 11,702-report registry, historical research continuity, fact-source completeness, training eligibility, non-local release readiness, or live trading.

## Scope

- In scope: deterministic five-company selection, content identity, isolated clone execution, idempotency, exact-slice primary promotion, restore verification, post-recovery reconciliation, one controlled daily product refresh, installed-schedule audit, full local CI, and local-only acceptance evidence.
- Out of scope: automatic recovery of the full 11,702-report archive, raw-file or OpenSearch deletion, ambiguous company binding, fact-source or training-data promotion, fabricated longitudinal history, non-local release evidence, broker integration, live orders, and automatic trading.

## Background

T-604 reconciled 11,702 eligible raw report files and 11,702 stale OpenSearch projections against a primary PostgreSQL state whose research collections had regressed. T-608 first produced a dry-run-only recovery planner. T-609, T-611, and T-612 then supplied collection-aware rollback evidence, isolated clone proof, and an independent insert-only primary promotion path. The final backup, controlled daily run, post-recovery reconciliation, schedule audit, and full CI now close the bounded five-company task.

## Problem Statement

The project needed usable direct research evidence for five active companies without treating stale OpenSearch projections as source truth or attempting an unbounded archive rebuild. Recovery had to preserve deterministic identities, opinion-only governance, no-delete behavior, clone isolation, transactional primary writes, point-in-time rollback, and paper-only product operation.

## Expected Deliverables

- [x] Canonical five-company plan with deterministic content and logical identity.
- [x] Two isolated-clone executions proving first-write success and second-run idempotency.
- [x] Independent, insert-only promotion of the exact clone slice into primary PostgreSQL.
- [x] One controlled daily run proving direct report evidence and structured product views for all five companies.
- [x] Final restore-verified backup after all controlled downstream product writes.
- [x] Read-only post-recovery reconciliation with referential-integrity checks.
- [x] Installed daily schedule audit with all 27 gates passing.
- [x] Full local CI with all 516 tests and supporting quality gates passing.

## Current State

- Completed: canonical plan; clone attestation; two clone executions; exact-slice primary promotion; controlled five-company product refresh; final restore-verified backup; post-recovery reconciliation; 27-gate schedule audit; and 516-test full local CI.
- In progress: none within T-608.
- Not started: none within T-608.
- Blocked: none.
- Follow-up boundary: full-registry reconciliation, missing financial/disclosure fact layers, and longitudinal daily history require separate roadmap work and do not reopen this bounded recovery task.

## Current Findings

- The canonical plan SHA-256 is `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d`. It indexes the full 11,702-file registry but selects only 15 content-identified reports, three per requested company.
- Clone run 1 passed with 15 newly created reports, 112 citation-evidence rows, and 15 verified content identities. Clone run 2 passed with zero newly created reports, the same 112 evidence rows, and the same 15 verified content identities. Both runs recorded no delete operations and retained the opinion/reference-only boundary.
- Primary promotion completed as one reviewed, insert-only slice: 1 source, 15 reports, 15 documents, and 112 citation-evidence rows. The exact promoted slice SHA-256 is `d2c1b3253de2ddb816eba708f91cd9b3e39a41cf9e3f330513f745eabf8b6b5b`.
- The controlled daily run completed with `status=passed`, `execution_status=passed`, `content_status=ready`, zero blocking failures, and direct report evidence for all five requested companies.
- The refresh produced 15 structured research reports, 15 viewpoints, and 3 forecasts in total. Each requested company has exactly 3 structured reports and 3 viewpoints.
- Each company remains honestly `partial` at completeness `0.8462`; `financial_snapshot` and `disclosure_events` are missing for all five. Therefore `ready_count=0` and `needs_attention_count=5` are correct fact-layer signals, not a report-recovery failure.
- The final backup `ai_quant-20260721T001909Z` passed restore verification. Source and restored aggregate counts match at 32,319 records, 35,385 audit rows, and 28,365,474 market bars; research counts match at 15 reports, 15 documents, 112 citation-evidence rows, 15 structured reports, 15 viewpoints, and 3 forecasts.
- The final backup dump is 837,739,289 bytes with SHA-256 `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`, retained through `2026-07-28T00:19:09.031522+00:00`. It is point-in-time local rollback evidence, not historical coverage proof.
- Post-recovery reconciliation found zero missing document references across report/document/citation relationships and confirmed all 15 research assets have content SHA, fingerprint, file path, and document identity.
- The installed systemd timer is enabled and active. The schedule audit passed 27/27 gates, including runner/service/timer shape, morning and evening schedules, persistence, typed storage, latest execution, actionable content, and artifact shape.
- Full `make local-ci PYTHON=.venv/bin/python` passed 516/516 unit tests plus the applicable UI, security, Markdown-link, handoff, and document-metadata gates.
- Raw storage and the stale OpenSearch projection still contain 11,702 research-report entries while primary intentionally contains the reviewed 15-report slice. The reconciliation therefore still reports global drift and refuses automatic full recovery; this is an explicit separate follow-up, not a T-608 failure.

## Proposed Work Plan

No implementation or closure work remains in T-608. Separate follow-up tasks should:

1. Decide whether and how to rebuild the remaining 11,687 raw reports into PostgreSQL, using a new bounded plan, clone proof, and rollback evidence before any write.
2. Add official financial snapshots and disclosure-event sources for the five companies without promoting opinion reports into fact or training layers.
3. Accumulate future daily observations from real scheduled dates; do not fabricate or backfill a longitudinal operating history.
4. Keep OpenSearch as a derived projection and rebuild it only after PostgreSQL registry scope is explicitly approved.

## Validation Plan

- Completed: immutable plan and clone execution chain verified against the canonical plan SHA.
- Completed: exact promoted slice verified by transaction result and slice SHA.
- Completed: final post-refresh backup verified by matching source/restored table and research-collection counts.
- Completed: read-only reconciliation verified current point-in-time collection identity and referential integrity while preserving the global drift warning.
- Completed: controlled daily execution/content, five-company coverage, installed schedule, and full local CI passed.
- No required T-608 validation remains.

## Dependencies

- Satisfied: T-609 collection-aware rollback evidence.
- Satisfied: T-611 isolated clone plan, runtime attestation, and two execution results.
- Satisfied: T-612 quiescence proof, exact-slice promotion, and post-commit verification.
- Satisfied: Platform and Quality final restore-verified backup, schedule audit, and full local CI.

## Blockers

- None.
- The global 11,702-to-15 registry drift is deliberately routed to separate follow-up work and does not authorize automatic recovery under T-608.

## Knowledge Closeout Matrix

- Code: `verified-current`; the recovery, clone-proof, promotion, backup, reconciliation, daily, and scheduling paths are protected by focused regressions and the 516-test full local CI. No code changed in this handoff-only update.
- Runtime: `verified-current` for this local machine; final restore verification, one controlled daily run, and the active/enabled schedule are evidenced. Non-local runtime is out of scope.
- Documentation: `changed-and-verified`; this handoff is the current T-608 answer and removes the stale pending-closure state.
- Rules: `verified-current`; repository `AGENTS.md` and `CLAUDE.md` boundaries remain applicable and were not changed.
- Memory: `not-applicable`; no authorized long-term memory write was requested or performed.
- Workspace: `pending/out-of-scope`; the shared worktree has pre-existing tracked and untracked changes. No cleanup, deletion, commit, or unrelated edit was performed.

## Files Touched

- `docs/agent-handoffs/2026-07-21-T-608-watchlist-report-recovery.md`: advanced T-608 from `DOING` to final `DONE`, recorded the final backup/reconciliation/daily/schedule/CI evidence, and preserved explicit follow-up boundaries. No code, database, artifact, roadmap, rule, memory, or other documentation file was changed by this update.

## Commands Run

The exact clone and primary-promotion commands remain recorded in the T-611 and T-612 handoffs. The final local closure used these commands or their artifact-recorded equivalents:

```bash
.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant \
  --output-dir data/local/backups/postgres

docker exec sotck_quant-ai-quant-org-1 python /app/scripts/reconcile_research_report_state.py \
  --filesystem-root /data/local/research_reports \
  --registry-root-alias /data/local/research_reports \
  --baseline-artifact /app/artifacts/research-report-completion-audit.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260721T001909Z.manifest.json \
  --output /app/artifacts/research-report-state-reconciliation-post-recovery.json \
  --timeout-seconds 30

.venv/bin/python scripts/audit_daily_update_schedule.py \
  --require-latest-run \
  --output artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json

make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
```

Result:

- Passed: 37 combined focused recovery/clone/promotion/backup regressions; clone run 1; idempotent clone run 2; exact primary promotion; controlled daily execution/content; five-company personal refresh; final restore verification; read-only post-recovery reconciliation; 27/27 schedule gates; and 516/516 full local CI tests with all supporting quality gates.
- Passed with one documented nonblocking warning: local production audit retains one expected historical workflow-failure drill record.
- Failed: none in the T-608 closure chain.
- Not run: external staging/non-local release validation, full 11,702-report recovery, and live-broker checks; all are explicitly outside T-608 and the project boundary.

## Evidence

- `artifacts/t611-executions/t611-clone-plan-runtime.json`: produced by `recover_watchlist_research_reports.py` on 2026-07-21 in the isolated local clone workflow; owner Data and Evidence; contains local identity/hash metadata but no credentials or report bodies; local-only and not valid for non-local release. Canonical plan SHA-256: `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d`.
- `artifacts/t611-clone-attestation.json`, `artifacts/t611-executions/t611-clone-execution-1.json`, and `artifacts/t611-executions/t611-clone-execution-2.json`: produced by the runtime probe and recovery CLI on 2026-07-21 against isolated database `ai_quant_t611_pilot_20260721`; owners Platform and Quality / Data and Evidence; contain local topology and report/evidence identities but no credentials or source bodies; local-only and not valid for non-local release.
- `artifacts/t612-primary-promotion-result.json`: produced by `promote_research_report_clone_to_primary.py` on 2026-07-21 against quiescent local primary PostgreSQL; owner Platform and Quality; contains database identities, counts, hashes, and audit metadata; local-only and not valid for non-local release. Exact slice SHA-256: `d2c1b3253de2ddb816eba708f91cd9b3e39a41cf9e3f330513f745eabf8b6b5b`.
- `artifacts/daily-update-local/runs/t612-post-promotion-20260721T001207Z`: produced by the local daily-update runner from `2026-07-21T00:12:28.178508+00:00` through `2026-07-21T00:15:23.691127+00:00`; owner Data and Evidence with Product/UI review; may contain restricted local source references and operational metadata but no credentials; local-only and not valid for non-local release.
- `data/local/backups/postgres/ai_quant-20260721T001909Z.dump` and `.manifest.json`: produced by `postgres_durable_backup.py` at `2026-07-21T00:19:09.031522+00:00`; local Docker Compose PostgreSQL; owner Platform and Quality; sensitive 837,739,289-byte restore-verified backup retained through `2026-07-28T00:19:09.031522+00:00`; local-only and not valid for non-local release. Dump SHA-256: `90717a718196abe9bf2e006d4db10071144930d72f91ca5c7c4a7023fb870e4c`.
- `artifacts/research-report-state-reconciliation-post-recovery.json`: produced read-only by `reconcile_research_report_state.py` at `2026-07-21T00:29:47.992525+00:00`; local Compose stores; owner Data and Evidence; contains sensitive aggregate storage/path metadata but no credentials or report bodies; local-only and not valid for non-local release. It verifies the 15-report point-in-time primary slice while explicitly retaining global raw/OpenSearch drift.
- `artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json`: produced by `audit_daily_update_schedule.py` at `2026-07-21T00:32:15.667412+00:00`; local systemd/user-service environment; owner Platform and Quality; contains local paths and timer metadata but no credentials; local-only and not valid for non-local release. All 27 gates passed and the timer was enabled/active.
- Full local CI console evidence: produced by `make local-ci PYTHON=.venv/bin/python` on 2026-07-21; local shared worktree; owner Platform and Quality; no report bodies or credentials; ephemeral local-only evidence, corroborated by `tasks/todo.md` and the T-607 handoff, and not valid for non-local release. All 516 tests and supporting gates passed.

## Decisions

- T-608 closes a reviewed five-company slice, not the full 11,702-report archive. The larger raw/OpenSearch reconciliation requires a separate plan and authorization.
- Research reports remain opinion/reference evidence. Neither clone execution, primary promotion, structured views, nor forecasts promote them into automated facts or training data.
- The primary promotion used a separate transaction-bound T-612 tool. The T-608 recovery client remains clone-only and continues to reject the primary endpoint.
- The promotion write set was limited to one source, reports, documents, citation evidence, and one audit event. There were no deletes or updates; equal identities were preserved and unequal conflicts were refused.
- The daily acceptance was intentionally run once with broad market imports and report rebinding excluded. Repeating it would add timestamped operational/audit history without increasing T-608 confidence.
- `ready_count=0` remains authoritative: report evidence is complete for the bounded slice, while financial snapshots and disclosure events are absent.
- The final backup protects the complete post-refresh point-in-time state. Its explicit coverage limitation prevents it from being presented as proof of historical research continuity.
- The schedule is accepted only for local personal production with no live broker or automatic order path.

## Risks and Open Questions

- Primary contains 15 reviewed reports while raw storage and the stale OpenSearch projection contain 11,702. Search results outside the five-company slice must not be presented as primary-backed evidence until a separate reconciliation completes.
- The post-recovery audit remains `drift_detected`, `automatic_recovery_authorized=false`, and `clone_pilot_review_required` for any broader registry work. T-608 `DONE` does not override those full-archive gates.
- `financial_snapshot` and `disclosure_events` are missing for all five companies. Any feature requiring full fact-layer readiness must continue to show partial/needs-attention status.
- The controlled run is one current-date observation, not longitudinal operating history. Future history must accumulate from real scheduled runs.
- Evidence and backups are ignored, machine-local artifacts with a finite retention window. They are not external staging or production evidence.
- The local production audit contains one nonblocking expected workflow-failure drill record; it should remain classified as drill history unless future runs show a new failure.
- The authoritative roadmap entry in `tasks/todo.md` remains parent-owned and was not changed by this handoff-only task.

## Handoff Checklist

- [x] Bounded recovery and exact primary promotion completed
- [x] Five-company structured product refresh completed
- [x] Final downstream restore-verified backup completed
- [x] Post-recovery reconciliation and referential-integrity checks completed
- [x] Installed schedule audit passed 27/27 gates
- [x] Full local CI passed 516/516 tests and supporting gates
- [x] Public API, storage schema, UI contract, opinion boundary, and paper-only boundary preserved
- [x] Full-registry, fact-layer, history, and non-local limitations documented
- [x] Parent roadmap synchronization explicitly delegated; `tasks/todo.md` remained out of scope

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No. This handoff-only update changes no application code, and the recovery/promotion path added no new business behavior directly to `app/services.py`.
- Domain placement: Recovery, clone proof, promotion, backup, reconciliation, and acceptance orchestration remain in focused operator scripts. The controlled product refresh calls existing service behavior through established APIs.
- Focused regression: 37 combined focused recovery-path tests protect deterministic identity, clone isolation, attestation, idempotency, exact-slice promotion, rollback, and facade behavior; full local CI adds 516/516 passing tests and supporting gates.
- API schema changed: No.
- Storage schema changed: No. Storage contents changed intentionally through the reviewed promotion and one controlled product refresh.
- UI behavior changed: No.
- Local reports promoted to facts or training data: No; the opinion/reference-only boundary remains explicit.
- Broker/live-trading boundary changed: No; all product feedback and execution remain paper/simulated only, with no broker or automatic order path.

## Next Steps

1. PM / Release Coordination should synchronize the T-608 roadmap line to `DONE` in its parent integration update.
2. Create a separate task before any attempt to recover the remaining 11,687 raw reports or rebuild OpenSearch.
3. Create separate fact-layer work for official financial snapshots and disclosure events.
4. Let longitudinal evidence accumulate through real scheduled runs; do not synthesize historical observations.

## Next Recommended Action

Treat T-608 as closed, synchronize its parent roadmap status, and keep the 11,702-report global reconciliation and missing fact layers as explicitly separate follow-up work.
