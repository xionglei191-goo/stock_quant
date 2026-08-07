# Handoff: T-619 Historical Backup Retention Cleanup

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination; Governance, Security, and Compliance
- Last updated: 2026-07-24
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only
- Related tasks: T-619

## Objective

Replace migration-era PostgreSQL backups with one fresh restore-verified current-state backup, then remove the user-authorized historical local backup set to release disk space.

## Scope

- In scope: `data/local/backups/postgres` historical dump and manifest files, a fresh primary backup, service/timer maintenance window, and post-cleanup verification.
- Out of scope: PostgreSQL source data, raw reports, duplicate aliases, OpenSearch, migration artifacts outside the backup directory, application code, broker connectivity, and live execution.

## Background

T-619 completed the research-report campaign at 9,568 research reports. The latest historical primary backup represented only 2,265 reports, so it was not a sufficient current recovery point. The user then explicitly authorized deletion of historical backups to release storage.

## Problem Statement

The 46 historical dump/manifest pairs and one orphan dump occupied 40,133,114,185 bytes. Retaining them after migration completion consumed local disk without preserving the final research-report state.

## Expected Deliverables

- One restore-verified primary snapshot covering the final T-619 state.
- Removal of the exact historical backup inventory only after verification passes.
- Restored local application, daily timer, health, and storage checks.

## Current State

- Completed: created current primary backup `ai_quant-20260724T122027Z.dump` and verified restore equality.
- Completed: removed 93 historical dump/manifest files totaling 40,133,114,185 bytes (37.38 GiB), including the orphan clone dump.
- Completed: restored `ai-quant-org` and `ai-quant-daily-update.timer`; health is `ok` with PostgreSQL, S3, and OpenSearch configured.
- In progress: none.
- Not started: none.
- Blocked: none.

## Current Findings

- The new backup has SHA-256 `b02f49b0c09aa5728757876bbf968ba354918db773516aa0b2899edb038fdc3e`, is 855,500,508 bytes, and its restore manifest passed exact source/restored database equality.
- The backup manifest verifies `research_reports=9568`, `research_documents=9568`, and `research_report_citation_evidence=73118` in both source and restored states.
- The temporary restore database was removed after validation. The backup directory now contains only the fresh dump and its manifest, consuming about 816 MiB. Root free space is 184 GiB (59% used).

## Proposed Work Plan

1. Keep the current restore-verified backup until its manifest retention timestamp of 2026-07-31T12:20:27.983232+00:00.
2. Before any future backup cleanup, create and verify a replacement that covers the then-current primary state.

## Validation Plan

- Validate backup manifest status, SHA-256, source/restored equality, and T-619 research counts.
- Confirm the historical deletion set count and byte total before deletion.
- Confirm the backup directory contents, service health, timer state, direct PostgreSQL counts, and filesystem capacity after cleanup.

## Dependencies

- Local Docker Compose PostgreSQL, the local application stack, and explicit user cleanup authorization.

## Blockers

- None.

## Files Touched

- `data/local/backups/postgres/*`: deleted 93 historical local backup files after replacement verification; retained only the current dump and manifest.
- `docs/agent-handoffs/2026-07-22-T-619-primary-research-report-campaign.md`: marks historical backup references as retired and links this operational update.
- `docs/agent-handoffs/2026-07-24-T-619-backup-retention-cleanup.md`: records authorization, exact cleanup scope, and validation evidence.

## Commands Run

```bash
PATH=".venv/bin:$PATH" python scripts/postgres_durable_backup.py \
  --output-dir data/local/backups/postgres \
  --source-db ai_quant \
  --retention-days 7 \
  --timeout-seconds 3600
jq -e '<passed, restore-verified, equality, and T-619 count checks>' \
  data/local/backups/postgres/ai_quant-20260724T122027Z.manifest.json
find data/local/backups/postgres -maxdepth 1 -type f \
  \( -name '*.dump' -o -name '*.manifest.json' \) \
  ! -name 'ai_quant-20260724T122027Z.dump' \
  ! -name 'ai_quant-20260724T122027Z.manifest.json' -exec rm -- {} +
docker compose start ai-quant-org
systemctl --user start ai-quant-daily-update.timer
curl --fail --silent http://127.0.0.1:8000/api/health
```

Result:

- Passed: backup status `passed`, `restore_verified=true`, source/restored database manifests equal, and dump SHA-256 matched the manifest.
- Passed: exact pre-delete inventory matched 93 files and 40,133,114,185 bytes; only those historical backup extensions were removed.
- Passed: backup directory now contains only `ai_quant-20260724T122027Z.dump` and `ai_quant-20260724T122027Z.manifest.json`.
- Passed: `/api/health` returned `ok`; PostgreSQL store, S3 object store, and OpenSearch search index were configured; daily timer is active.
- Passed: direct PostgreSQL collection counts after cleanup were `research_reports=9568`, `documents=9596`, and `evidence=75519`.

## Evidence

- `data/local/backups/postgres/ai_quant-20260724T122027Z.dump`: producer `scripts/postgres_durable_backup.py`; local Docker Compose PostgreSQL snapshot generated 2026-07-24T12:20:27.983232+00:00; contains sensitive database data; local-only; not acceptable for non-local release evidence.
- `data/local/backups/postgres/ai_quant-20260724T122027Z.manifest.json`: producer `scripts/postgres_durable_backup.py`; local-only restore and research-state verification; contains counts, hashes, and safe samples; not acceptable for non-local release evidence.

## Decisions

- Do not delete any historical backup until a new current-state backup passes an actual restore check. The old backups predated the final bulk promotion and covered at most 2,265 research reports.
- Delete only immediate regular `.dump` and `.manifest.json` files in the backup directory after the pre-delete file-count and byte-total invariants matched the approved inventory. Preserve the fresh pair by exact filename.
- Do not use broad Docker or filesystem pruning. The cleanup excludes the primary database volume, raw reports, duplicate aliases, and OpenSearch.

## Risks and Open Questions

- This local-only backup is a single recovery point and expires under the seven-day retention setting. A later cleanup requires a newly verified replacement.
- The backup contains sensitive local database data and must remain outside non-local release evidence or external sharing paths.

## Handoff Checklist

- [x] No code change was needed for this operational cleanup.
- [x] Backup restore, manifest, storage, service, and timer checks passed.
- [x] Historical handoff retention status updated and this cleanup handoff added.
- [x] `tasks/todo.md` status unchanged because T-619 remains DONE.

## Next Steps

1. Monitor normal local operations and the daily timer.
2. Create a new restore-verified snapshot before the retained backup expires or before a future cleanup.

## Next Recommended Action

Run normal local monitoring; any new research-report ingestion or storage cleanup requires a separate authorized task.
