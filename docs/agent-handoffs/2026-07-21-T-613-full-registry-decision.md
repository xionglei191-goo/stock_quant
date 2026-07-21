# Handoff: T-613 Full Research-Report Registry Decision

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only

## Objective

Build a reproducible, path-redacted identity manifest for all 11,702 raw research reports and an evidence-backed decision pack that distinguishes historical restore evidence from a new raw reparse. Keep all source stores unchanged and leave full-registry execution unauthorized.

## Scope

- In scope: full-file SHA-256, path-derived identity checks, duplicate/content-conflict classification, current PostgreSQL comparison, OpenSearch ID coverage, local backup classification, restrictive rights policy, deterministic clone-only batches, tests, roadmap, and evidence.
- Out of scope: primary writes, clone execution, raw deletion, duplicate-file deletion, OpenSearch rebuild, object-store writes, report promotion to facts/training data, broker integration, live orders, and non-local release evidence.

## Background

T-612 safely promoted a reviewed 15-report slice. Raw storage and OpenSearch still represented 11,702 report identities, while the historical acceptance artifact claimed 11,702 linked documents and 88,515 citation rows. T-613 was required to determine whether a complete historical database state still exists and to prevent a count-only restore decision.

## Problem Statement

No current artifact bound every raw file to a full content hash without exposing report paths, and no machine-enforced decision distinguished the T-611 11,702-row registry-only clone backup from the historical 11,702-document/88,515-citation state.

## Expected Deliverables

- A read-only full identity-manifest and recovery-decision CLI with no execute mode.
- A real 11,702-file local-only manifest and decision pack.
- Focused regressions for deterministic hashing, redaction, read-only database access, OpenSearch pagination, backup classification, duplicate policy, and conflict refusal.
- An updated roadmap that separates completed decision work from a separately approved clone execution.

## Current State

- Completed: implementation, 6 focused tests, two identical real full-file scans, PostgreSQL/OpenSearch/backup comparison, 44 deterministic batches, artifact redaction scan, roadmap update, 522-test local CI, and handoff validation.
- In progress: none.
- Not started: T-614 batch-0001 clone double run.
- Blocked: no execution blocker affects T-613 because this task is read-only; T-614 requires a new backup and explicit approval bound to the manifest and batch SHA values.

## Current Findings

- The manifest hashed 11,702 files / 22,977,634,524 bytes with coverage `1.0`, zero hash failures, and zero report-ID collisions.
- There are 10,818 unique content hashes, 599 duplicate-content groups, and 884 duplicate path aliases.
- All 15 current PostgreSQL report IDs match the raw full-file SHA-256 values and the restrictive local-reference rights policy. There are zero extra IDs and zero content conflicts.
- OpenSearch has exactly the same 11,702 report IDs as the raw manifest, with zero missing or extra projections. It remains a derived projection, not a recovery source of truth.
- No retained restore-verified backup proves the historical `11,702 reports / 11,702 documents / 88,515 citation evidence` state. T-611 backups prove only `11,702 / 15 / 112` and explicitly disclaim historical coverage.
- Excluding 15 exact primary rows and 884 duplicate aliases leaves 10,803 unique-content recovery candidates in 44 deterministic batches of at most 250 reports.
- Inventory gates pass, but execution remains false because a new pre-execute backup, an independent clone double run, and explicit human approval are intentionally absent.

## Proposed Work Plan

1. Completed: hash all eligible files and emit path-redacted deterministic identities.
2. Completed: compare current PostgreSQL and OpenSearch identities without writes.
3. Completed: classify all local backup manifests against historical and current collection counts.
4. Completed: generate duplicate-aware clone-only batches and keep execution gates false.
5. Completed: finish repository-level validation and mark T-613 complete.
6. Future T-614: after exact approval, produce a new backup and run only batch 0001 twice in an independently attested clone.

## Validation Plan

- Run the focused unittest module and Python compile.
- Run the real full scan twice and require identical manifest/entries SHA-256 values.
- Scan evidence JSON for local paths, filenames, DSNs, credentials, and report bodies.
- Run `make local-ci PYTHON=.venv/bin/python` and `python3 scripts/check_handoffs.py` before completion.

## Dependencies

- Read-only raw archive mounted at `/data/local/research_reports` inside the application container.
- Current local PostgreSQL, OpenSearch, historical acceptance artifact, and local backup manifests.
- T-609 collection-aware backup format and T-612 current 15-report state.

## Blockers

- None for the T-613 decision pack.
- T-614 execution is not authorized until a new collection-aware backup and exact human approval bind manifest SHA `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e` and batch-0001 SHA `2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85`.

## Files Touched

- `scripts/build_research_report_registry_decision.py`: full-file identity, read-only cross-store comparison, backup classification, duplicate policy, deterministic clone-only planning, and execution gates.
- `tests/test_build_research_report_registry_decision.py`: focused coverage for determinism, redaction, read-only SQL, pagination, backup semantics, duplicates, and content conflicts.
- `tasks/todo.md`: marks T-613 decision work complete in scope and creates T-614 as a separately approved execution task.
- `docs/README.md`: extends the roadmap index through T-614.
- `docs/agent-handoffs/2026-07-21-T-613-full-registry-decision.md`: current evidence, decisions, risks, and next action.

## Commands Run

```bash
.venv/bin/python -m py_compile scripts/build_research_report_registry_decision.py tests/test_build_research_report_registry_decision.py
.venv/bin/python -m unittest tests.test_build_research_report_registry_decision -v
docker compose exec -T ai-quant-org python /app/scripts/build_research_report_registry_decision.py \
  --filesystem-root /data/local/research_reports \
  --registry-root /data/local/research_reports \
  --baseline-artifact /app/artifacts/research-report-completion-audit.json \
  --backup-dir /data/local/backups/postgres \
  --opensearch-endpoint http://opensearch:9200 \
  --manifest-output /app/artifacts/t613-full-registry/identity-manifest.json \
  --decision-output /app/artifacts/t613-full-registry/recovery-decision.json
jq -n --slurpfile first artifacts/t613-full-registry/identity-manifest.json \
  --slurpfile second artifacts/t613-full-registry/identity-manifest-rerun.json \
  --slurpfile d1 artifacts/t613-full-registry/recovery-decision.json \
  --slurpfile d2 artifacts/t613-full-registry/recovery-decision-rerun.json \
  '{manifest_sha_equal:($first[0].integrity.manifest_sha256==$second[0].integrity.manifest_sha256),entries_sha_equal:($first[0].integrity.entries_sha256==$second[0].integrity.entries_sha256),batch_plan_equal:($d1[0].recovery_plan==$d2[0].recovery_plan)}'
rg -n '/home/xionglei|/data/local/research_reports|\.pdf|\.txt|password|secret|DSN' \
  artifacts/t613-full-registry/identity-manifest.json \
  artifacts/t613-full-registry/recovery-decision.json
make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
```

Result:

- Passed: 6/6 focused tests and Python compile.
- Passed: real full scan with status `ready_for_manual_strategy_review`; `execution_authorized=false`.
- Passed: second real scan reproduced manifest SHA, entries SHA, summary, and all 44 batches exactly.
- Passed: no path, filename, DSN, credential, or report-body disclosure in generated evidence. The word `token` appears only in the sentence explaining that no approval token is accepted or stored.
- Passed: `make local-ci PYTHON=.venv/bin/python` with 522 tests, UI static check, security scan across 536 files, Markdown links across 249 files, 190 handoff documents, and 5 canonical document metadata checks.
- Pending: none for T-613.
- Failed: none.

## Evidence

- `artifacts/t613-full-registry/identity-manifest.json`: produced by the second `build_research_report_registry_decision.py` run at `2026-07-21T01:49:42.634461+00:00`; local Compose; owner Data and Evidence; sensitive because content hashes fingerprint restricted local reports, but it contains no report paths, names, bodies, credentials, or signed URLs; local-only and unacceptable for non-local release. Manifest SHA-256 `e932f352047eb58b4e0df797215598b7ee0bdd25b920432bf6c89173a301fa5e`; entries SHA-256 `dda7f77f31ad0e0c5416218ef723effca951249617486080b83a117cdebc4fe0`.
- `artifacts/t613-full-registry/recovery-decision.json`: produced by the same second run at `2026-07-21T01:49:43.088556+00:00`; local Compose; owner Data and Evidence; sensitive local topology/count/identity evidence without paths or content; local-only and unacceptable for non-local release. First batch SHA-256 `2909ee8b964a24c9c47cecf2da04ddab4fc409ea1c7b40c3b461eab97838cd85`.
- `artifacts/research-report-completion-audit.json`: historical local-only acceptance evidence from 2026-05-19; reports historical `11702/11702/88515`, but is not current persistence or restore proof.
- `data/local/backups/postgres/ai_quant-20260721T001909Z.manifest.json`: current restore-verified rollback evidence for 15 reports; sensitive local-only backup manifest, not historical full-registry proof or non-local release evidence.

## Decisions

- Treat full-file SHA-256 as content identity and path-derived `report_id` as registry identity. Expose paths only through SHA-256 digests in evidence.
- Preserve all 15 current exact rows. For identical content at multiple paths, prefer a current exact row when present; otherwise retain the lexicographically first report ID as the proposed canonical and exclude aliases pending manual review.
- Do not restore from any current backup as historical complete state. The only full-registry backups have 15 documents and 112 citations, so they require raw reparse rather than restore promotion.
- Keep every generated batch clone-only and insert-only. This command deliberately has no execute mode or approval-input option.

## Risks and Open Questions

- File hashes prove byte identity, not legal redistribution or training rights. All reports remain restricted manual opinion references, and source legal provenance remains independently unverified.
- Duplicate path aliases may contain meaningful filing/location context even when bytes are identical; no duplicate file may be deleted automatically.
- A 250-file clone pilot must measure parser failures, evidence density, elapsed time, and storage growth before extrapolating the remaining 43 batches.
- The historical 88,515 citation rows may not be reproducible byte-for-byte because parser versions and extraction tooling can change; any new state must be labeled reparse output, not historical restoration.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated; no public API, storage schema, or environment contract changed
- [x] `tasks/todo.md` roadmap status updated

## Next Steps

1. Request exact human approval for T-614 using both the manifest and batch-0001 SHA values.
2. After approval, create a new collection-aware primary backup before constructing the isolated clone.
3. Run only batch 0001 twice in the clone and review parser quality/cost before scheduling another batch.

## Next Recommended Action

Do not recover all 10,803 candidates. Review and explicitly approve only T-614 batch 0001, then use its double-run evidence to decide whether the remaining 43 batches are worth the parser and storage cost.
