# Handoff: T-611 Isolated Research-Report Clone Pilot

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t612_primary_promotion`
- Branch/worktree: `main`, shared dirty worktree; no commit created
- Related tasks: T-603, T-604, T-608, T-609, T-611, T-612
- Artifact classification: local-only

## Objective

Prove the bounded T-608 recovery twice in a technically isolated PostgreSQL clone, demonstrate second-run idempotency and content identity, preserve all raw/search inputs, retain a restore-verified qualifying clone backup, and remove the disposable runtime after review.

## Scope

- In scope: clone restore, isolated app runtime, independent attestation, deterministic plan, two executions, identity comparison, post-run backup, and clone database/container/network cleanup.
- Out of scope: primary writes, full-registry primary recovery, OpenSearch/MinIO writes, raw report mutation, deletion, non-local release evidence, broker integration, live orders, and automatic trading.

## Background

T-604 found 11,702 eligible raw files and an equally sized stale OpenSearch projection while primary PostgreSQL had no active research-report collections. T-609 supplied a restore-verified zero-state rollback point. T-611 made the first recovery execution possible only inside a disposable clone whose database, network, local backends, read-only mount, and primary-service isolation were independently proven.

## Problem Statement

A declared clone name was not enough to prevent accidental primary or shared-service writes. The pilot needed runtime-bound proof, two identical-input executions, durable evidence of idempotency, and explicit teardown after a recoverable post-run snapshot.

## Expected Deliverables

- A canonical 15-report plan bound to the 11,702-file raw manifest.
- A passing runtime attestation for the clone database and isolated application.
- Two passing execution artifacts showing first-write success and second-run idempotency.
- Exact 15/15 report ID, document ID, and content-hash identity across both runs.
- A restore-verified post-clone backup followed by removal of the clone database, application container, and isolated network.

## Current State

- Completed: clone restore, isolation proof, canonical plan, formal run 1, formal run 2, identity checks, restore-verified post-clone backup, and complete disposable-runtime cleanup.
- In progress: none.
- Not started: broader primary recovery of all 11,702 registry entries; this was never authorized by T-611.
- Blocked: none.

## Current Findings

- Canonical plan `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d` scanned 11,702 eligible files with zero report-ID collisions and selected 15 reports, three each for AAPL, NVDA, MSFT, 300750, and 600519.
- Attestation passed for database `ai_quant_t611_pilot_20260721`, loopback endpoint `127.0.0.1:18001`, in-container execution, local object/search backends, internal-network isolation, read-only raw mount, unreachable primary service, and exact restored zero-state counts.
- Run 1 passed with registry count 11,702, 15 selected reports, 112 citation-evidence rows, zero needs-evidence results, and all 15 `ingest_created=true`.
- Run 2 passed against the same plan with all 15 `ingest_created=false`. Report IDs, document IDs, and content SHA-256 values match run 1 exactly for all 15 reports.
- Both runs record `delete_operations=[]`, `raw_files_preserved=true`, and `opensearch_index_preserved=true`.
- The qualifying post-clone backup is restore-verified at `records=43,941`, `audit_log=35,375`, `market_data_bars=28,365,189`; research state is `11,702 reports / 15 documents / 112 citation evidence / 0 structured reports / 0 viewpoints / 0 forecasts`.
- After backup review, container `sotck_quant-t611-clone-app`, database `ai_quant_t611_pilot_20260721`, and network `ai-quant-t611-isolated` were removed. The evidence artifacts and qualifying dump were retained.

## Proposed Work Plan

1. Completed: restore the exact T-609 zero-state backup into the explicitly named clone database.
2. Completed: start and attest an internal-network, loopback-only app with local search/object backends and read-only raw input.
3. Completed: execute the canonical plan twice and compare all selected identities and hashes.
4. Completed: produce a collection-aware post-clone backup and verify its temporary restore.
5. Completed: remove clone app, clone database, PostgreSQL network attachment, and isolated network while retaining evidence.

## Validation Plan

- Validate attestation/planner behavior with focused tests and tamper/isolation rejection cases.
- Require the real runtime proof before either execution.
- Require pass status, zero deletes, preserved raw/search inputs, exact identity equality, and all-false second-run creation flags.
- Restore-verify the post-clone database before teardown, then prove all disposable resources are absent.

## Dependencies

- T-609 zero-state backup `ai_quant-20260720T214759Z` and pre-recovery reconciliation.
- Read-only 11,702-file local research archive.
- Docker Compose PostgreSQL plus the clone application image with PDF extraction dependencies.

## Blockers

- None. The clone is deliberately gone; any new pilot must restore a fresh clone and generate a fresh attestation.

## Files Touched

- `scripts/recover_watchlist_research_reports.py`: enforces structured clone-runtime proof before execution.
- `scripts/probe_research_report_clone_runtime.py`: independently probes Docker, health, database, backend, network, mount, and primary reachability state.
- `tests/test_recover_watchlist_research_reports.py`: covers attestation validation, unsafe fields, tamper refusal, recovery identity, and idempotency behavior.
- `tests/test_probe_research_report_clone_runtime.py`: covers passing proof production and shared-network refusal.
- `docs/agent-handoffs/2026-07-21-T-611-clone-pilot-design.md`: reconciled the original procedure with the completed pilot and cleanup evidence.

## Commands Run

```bash
.venv/bin/python -m unittest \
  tests.test_recover_watchlist_research_reports \
  tests.test_probe_research_report_clone_runtime -v

# The same in-container recovery command was executed twice; only output changed.
docker exec sotck_quant-t611-clone-app python scripts/recover_watchlist_research_reports.py \
  --filesystem-root /data/local/research_reports \
  --api-root /data/local/research_reports \
  --registry-root /data/local/research_reports \
  --extensions .pdf,.txt,.md \
  --reconciliation /app/artifacts/research-report-state-reconciliation-pre-recovery.json \
  --backup-manifest /data/local/backups/postgres/ai_quant-20260720T214759Z.manifest.json \
  --base-url http://127.0.0.1:18001 \
  --max-reports-per-symbol 3 \
  --content-hash-budget-mb 2048 \
  --execute \
  --clone-attestation /tmp/t611-clone-attestation.json \
  --confirm-plan-sha256 921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d \
  --acknowledge-opinion-boundary \
  --allow-full-registry-scan \
  --confirm-clone-target \
  --output /tmp/t611-clone-execution-1.json

.venv/bin/python scripts/postgres_durable_backup.py \
  --source-db ai_quant_t611_pilot_20260721 \
  --output-dir data/local/backups/postgres

docker rm -f sotck_quant-t611-clone-app
docker compose exec -T postgres dropdb -U ai_quant ai_quant_t611_pilot_20260721
docker network disconnect ai-quant-t611-isolated "$(docker compose ps -q postgres)"
docker network rm ai-quant-t611-isolated
```

Result:

- Passed: focused isolation/recovery tests; independent runtime attestation; both formal clone runs; 15/15 report/document/content identity comparison; no-delete/raw-preservation/search-preservation assertions; post-clone dump and temporary restore equality; container/database/network absence checks after cleanup.
- Failed: an earlier non-evidence attempt exposed a missing PDF runtime dependency. The image was rebuilt, the clone was restored cleanly, and only the two subsequent passing formal runs were retained as acceptance evidence.
- Not run: non-local or primary execution through the clone recovery client; both remain prohibited.

## Evidence

- `artifacts/t611-executions/t611-clone-plan-runtime.json`: generated by `recover_watchlist_research_reports.py` at `2026-07-20T23:30:19.722324+00:00`; isolated local clone; owner Data and Evidence; identity/path metadata but no credentials or report bodies; local-only and unacceptable for non-local release. Canonical plan SHA-256 `921fce6a12bba48a2356cf041e0bd0e7db5a869c1603b7c82ad583e93c50bc9d`; artifact-file SHA-256 `734d0eaaaa4ddec5755c99101bf3efedd12df5792dd726287faf3c0dfed08173`.
- `artifacts/t611-clone-attestation.json`: generated by `probe_research_report_clone_runtime.py` at `2026-07-20T23:30:37.159776+00:00`; isolated local clone; owner Platform and Quality; topology/count metadata, no DSN or credential; local-only and unacceptable for non-local release. Runtime-proof SHA-256 `b310b784a8f0fc7824594dbe5cb7fd8a4993f0c7c75a93eb2373d219c8f9fcc7`.
- `artifacts/t611-executions/t611-clone-execution-1.json`: first formal execution; owner Data and Evidence; selected identities and operational metadata; local-only, sensitive, and unacceptable for non-local release. Artifact-file SHA-256 `56e95721ba70d938716a75e38a27f16d8c769d76ab880736391db00fea21dcab`.
- `artifacts/t611-executions/t611-clone-execution-2.json`: idempotent second formal execution; same classification and ownership as run 1. Artifact-file SHA-256 `560849edd2006c95ec092f7503fad8b63a52ec27b409184f04da56fd245e36dc`.
- `data/local/backups/postgres/ai_quant_t611_pilot_20260721-20260720T233925Z.dump` and `.manifest.json`: produced by `scripts/postgres_durable_backup.py` at `2026-07-20T23:39:25.653021+00:00`; stopped local clone; owner Platform and Quality; sensitive 839,233,126-byte restore-verified dump; retained through 2026-07-27; local-only and unacceptable for non-local release. Dump SHA-256 `f4d4517a6b8e857924a43b8f2c7d0cf192161eeb19747f25134da6bec9b5a650`.

## Decisions

- Execute only inside the attested clone app. The recovery client remains clone-only and must never target the primary `:8000` endpoint.
- Treat the full registry scan as clone-side identity construction, not authorization to promote all 11,702 reports. Only the reviewed 15-report dependency slice qualified for T-612.
- Require exact report ID, document ID, and content-hash equality across runs in addition to aggregate counts.
- Back up before teardown. Cleanup removed only disposable clone resources; raw files, OpenSearch, primary PostgreSQL, retained artifacts, and the qualifying backup were not deleted or modified.

## Risks and Open Questions

- The full 11,702 registry existed only in the disposable clone backup; primary received only 15 reviewed reports. Global recovery remains incomplete by design.
- Runtime artifacts and the dump are sensitive, ignored, machine-local evidence with finite retention. They do not satisfy external staging or production gates.
- Repeating the pilot requires a clean restore and new attestation; the removed runtime must not be reconstructed from stale proof alone.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated by the parent integration owner

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No; `app/services.py` and the application facade were not changed.
- Domain placement: Recovery and runtime proof remain in focused operator scripts.
- Focused regression: recovery and probe test modules protect isolation, tamper refusal, identity, and idempotency behavior.
- Contract/boundary changes: No public API, storage schema, UI, paper-only, no-broker, or no-live-trading boundary changed; local reports remain opinion/reference evidence only.

## Next Steps

1. Retain the canonical plan, two execution artifacts, attestation, and qualifying clone dump for the audit/retention window.
2. Use only the T-612 insert-only promotion evidence for the completed primary slice; open a separate clone-first task for any broader registry recovery.

## Next Recommended Action

Do not recreate the cleaned clone unless a separately reviewed broader-recovery task requires a new isolated pilot and fresh evidence chain.
