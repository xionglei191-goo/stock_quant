# Handoff: T-604 Research Report State Reconciliation

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t604_report_reconciliation`
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Provide a dry-run-only inventory and reconciliation tool for the raw research-report filesystem, PostgreSQL workflow registry, OpenSearch projection, and S3-compatible object store. The tool must expose drift and recovery prerequisites without deleting, reindexing, or mutating any source.

## Scope

- In scope: read-only filesystem metadata, PostgreSQL aggregate/identifier queries, OpenSearch count/type inventory, S3 ListObjectsV2 inventory, historical acceptance evidence, backup-manifest inspection, drift findings, and recovery-safety classification.
- Out of scope: recovery writes, full-file content hashing, OCR/reparse, deletion, index rebuild, raw-report changes, database changes, object-store changes, and non-local release evidence.

## Background

T-417/T-423 previously recorded 11,702 indexed reports, 11,702 linked research documents, and 88,515 citation evidence rows. The current PostgreSQL runtime reports no research-report collections while the 22GB raw archive and OpenSearch index still exist. Count comparisons were previously ambiguous because each store has a different grain.

## Problem Statement

The project lacked one safe tool that could distinguish raw sources, authoritative workflow state, derived search projections, and derived object payloads. Without that boundary, a count mismatch could lead to an unsafe delete/reindex decision or a false claim that a generic restore-verified backup protects the missing report state.

## Expected Deliverables

- A read-only multi-store reconciliation CLI with no execute mode.
- Focused regressions for read-only SQL/HTTP behavior, pagination, path aliases, secret redaction, and conservative recovery decisions.
- A real local-only audit artifact and evidence-backed next actions.

## Current State

- Completed: implementation, focused tests, complete local Compose audit, security scan, compile check, and handoff.
- In progress: none for the audit tool.
- Not started: recovery implementation and cloned-database pilot; these require a separate authorized task.
- Blocked: automatic recovery is blocked because the supplied backup manifest does not record research collection counts, so it cannot prove that the historical 11,702-report state is restorable.

## Current Findings

- Raw archive: 11,742 files total; 11,702 eligible PDFs; 40 out-of-scope PNGs; 22,977,634,524 eligible bytes; zero unreadable metadata entries.
- PostgreSQL: `research_reports=0`, `structured_research_reports=0`, `report_viewpoints=0`, `report_forecasts=0`, research citation chunks `=0`; the current database has 26 general documents and 27 general evidence rows.
- Historical evidence: the 2026-05-19 completion artifact reported 11,702 reports, 11,702 research documents, and 88,515 citation evidence rows. This is historical acceptance evidence, not current persistence proof.
- OpenSearch: 24,253 live documents, including exactly 11,702 `research_report` projections; 95,220 deleted documents. The report projection is stale relative to PostgreSQL and must be preserved for forensic comparison, not promoted to source of truth.
- S3/MinIO: 177 objects across `ashare_exchange`, `operating_reports`, and `sec_edgar`; zero objects under a research-named namespace. Object count is not directly comparable to report/document/evidence counts.
- Backup: the supplied T-602 dump exists, its size matches, and its restore was verified, but the manifest has no per-collection research counts. A successful generic restore therefore does not prove that it contains the missing historical report state.
- Reconciliation result: two critical findings (`raw_registry_drift`, `historical_registry_regression`) and two high findings (`search_projection_drift`, `backup_research_coverage_unproven`).
- Safety result: raw-report deletion, search-index deletion, treating OpenSearch as truth, and automatic recovery are all explicitly unsafe/unauthorized.

## Proposed Work Plan

1. Retain the raw directory and current OpenSearch index unchanged.
2. Create or locate restore evidence with explicit `research_reports`, linked research-document, and citation-evidence collection counts plus deterministic ID samples.
3. Generate an exact idempotent raw-file-to-report/document/evidence recovery manifest and prove zero ID collisions.
4. Run a bounded recovery pilot against a cloned database; validate referential integrity and rerun the reconciliation audit before any primary write.
5. Rebuild OpenSearch only after PostgreSQL is restored as the validated workflow source of truth.

## Validation Plan

- Focused unit tests cover filesystem scope, path-based ID aliases, PostgreSQL SELECT-only behavior, referential checks, OpenSearch grain separation, S3 pagination, credential redaction, relocated backup paths, and conservative recovery gates.
- The local Compose run must report all four stores as available and must not expose credentials, object keys, signed URLs, or report content.
- Repository-level CI remains the T-603 parent agent's final integration gate because other agents are concurrently changing shared files.

## Dependencies

- Local Compose PostgreSQL, OpenSearch, and MinIO services.
- The mounted raw archive at `/data/local/research_reports`.
- `psycopg` for PostgreSQL inventory; S3/OpenSearch inventory uses the Python standard library.

## Blockers

- No collection-aware rollback evidence currently proves recovery of the historical 11,702-report state.
- The script intentionally does not perform recovery, deletion, reindexing, or full 22GB content hashing.

## Files Touched

- `scripts/reconcile_research_report_state.py`: new read-only multi-store inventory, drift analysis, secret-safe output, and recovery-safety gate.
- `tests/test_reconcile_research_report_state.py`: eight focused tests for store grain, read-only operations, pagination, redaction, path portability, and safety decisions.
- `docs/agent-handoffs/2026-07-21-T-604-report-state-reconciliation.md`: implementation, evidence, risks, and next-step record.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_reconcile_research_report_state -v
.venv/bin/python -m py_compile app/*.py tests/*.py scripts/*.py
.venv/bin/python scripts/reconcile_research_report_state.py --help
.venv/bin/python scripts/security_check.py .
docker exec sotck_quant-ai-quant-org-1 python /app/scripts/reconcile_research_report_state.py \
  --filesystem-root /data/local/research_reports \
  --registry-root-alias /data/local/research_reports \
  --baseline-artifact /app/artifacts/research-report-completion-audit.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260719T015529Z.manifest.json \
  --output /app/artifacts/research-report-state-reconciliation.json \
  --timeout-seconds 30
git diff --check -- scripts/reconcile_research_report_state.py tests/test_reconcile_research_report_state.py
```

Result:

- Passed: 8/8 focused tests.
- Passed: full Python compile for `app/*.py`, `tests/*.py`, and `scripts/*.py`.
- Passed: CLI help.
- Passed: security scan, zero findings across 509 checked files.
- Passed: real local read-only audit; all four stores available, highest severity `critical`, no mutation performed.
- Passed: diff whitespace check.
- Not run: full unit suite and `make local-ci`; reserved for the T-603 parent integration after concurrent changes settle.

## Evidence

- `artifacts/research-report-state-reconciliation.json`: produced 2026-07-21 CST by the Docker command above; local Compose environment; owner Data and Evidence; classified sensitive because it contains aggregate storage metadata and local paths, but contains no credentials, signed URLs, object keys, report text, or full model output; local-only and not acceptable for non-local production release gates.
- `artifacts/research-report-completion-audit.json`: produced 2026-05-19 by the prior full-ingestion acceptance; historical local-only baseline; no secret content; not proof of current persistence or non-local release readiness.
- `data/local/backups/postgres/ai_quant-20260719T015529Z.manifest.json`: produced by `scripts/postgres_durable_backup.py`; local-only restore evidence for a sensitive dump; restore verified but lacks per-collection research counts; not acceptable for non-local release and not sufficient proof of historical report-state recovery.

## Decisions

- Keep the tool read-only with no `--execute` path. Recovery requires a separately reviewed task and cloned-database evidence.
- Compare only compatible grains. Raw files compare to PostgreSQL report assets; only OpenSearch `resource_type=research_report` compares to report assets; document/evidence/object totals are not treated as report totals.
- Use logical root aliases when reproducing deterministic report IDs because historical registration used the container mount path, not the host path.
- Do not hash 22GB of report content during routine reconciliation. The audit records a cheap metadata-manifest hash and leaves full content verification to a bounded recovery manifest.
- Never infer deletion safety from equal counts. Both raw and index deletion gates remain false even when future counts match.
- A restore-verified backup protects the expected report state only when collection-level report coverage is explicitly recorded and meets the expected baseline.

## Risks and Open Questions

- OpenSearch holds 11,702 report projections, but those projections contain search metadata rather than authoritative full workflow/document/evidence state.
- Historical report IDs depend on the absolute logical mount root. Recovery must include every known historical root alias and prove collision-free identity mapping.
- MinIO's zero research-named namespace count is strong current evidence for configured namespaces, but atypically named keys could require a PostgreSQL object-URI join after registry recovery.
- The raw archive protects original files, not the previously extracted/citation-chunk state; reparsing may be required if no suitable backup exists.
- `tasks/todo.md` was intentionally not touched by this sub-agent; T-603 PM integration owns roadmap status.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly recorded
- [x] Docs/contracts updated; no public API or environment contract changed
- [ ] `tasks/todo.md` roadmap status update delegated to the T-603 parent agent

## Next Steps

1. Add collection-level counts and deterministic ID samples to the next pre-recovery backup/inventory evidence.
2. Build and review a recovery-manifest generator that remains dry-run by default.
3. Restore/rebuild a small bounded sample in a cloned database, then rerun this audit and focused business acceptance.

## Next Recommended Action

Produce collection-aware rollback evidence before authorizing any write-based recovery; the current raw archive and OpenSearch index must remain unchanged.
