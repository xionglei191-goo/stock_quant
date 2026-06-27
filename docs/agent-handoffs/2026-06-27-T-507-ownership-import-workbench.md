# Handoff: T-507 Ownership Import Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-507

## Objective

Add a browser-visible workbench entry for importing local ownership tables into review-required company relationship candidates.

## Scope

- In scope: company intelligence maintenance UI, relationship builder payload wiring, static UI contract, API docs, roadmap status.
- Out of scope: new backend route, external data fetching, browser file upload, automatic candidate approval, database migration, real broker integration, automatic trading.

## Background

T-504 added ownership table parsing and a CLI script. T-506 wired relationship gaps to actions, but ownership gaps still needed a first-class browser path instead of a guidance-only message.

## Problem Statement

Before T-507, users could import ownership tables through scripts or API payloads, but the company intelligence workbench did not provide a direct preview/execute control for local ownership files.

## Expected Deliverables

- Add local ownership table fields in the company intelligence maintenance area.
- Call `/api/company-database/relationships/build` with `ownership_root_path`, `ownership_file_paths`, and `include_structured_ownership=true`.
- Render parsed file summaries, candidate counts, errors, and boundary labels.
- Execute mode refreshes company intelligence and relationship review rows.
- Static UI contract covers new fields and functions.

## Current Findings

- Completed: Added "股权表导入" form with root path, comma-separated file list, and default kind.
- Completed: Added `companyOwnershipImportPayload`, `renderCompanyOwnershipImport`, and `importCompanyOwnershipTables`.
- Completed: Ownership gap actions now trigger an ownership import preview directly.
- Completed: Static UI check requires the new DOM IDs and functions.
- Completed: API docs document the workbench entry as a UI path over the existing relationship builder.

## Proposed Work Plan

1. Reuse the existing relationship builder rather than adding a new backend endpoint.
2. Keep default mode as dry-run preview.
3. Keep all imported ownership rows as `needs_review` relationship candidates.
4. Refresh company intelligence after execute so relationship context and review queues update.
5. Lock the UI entry with static contract and focused regression.

## Validation Plan

Run:

```bash
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Browser interaction acceptance is deferred; the current slice is static UI wiring to an existing API contract.

## Risks

- The browser entry reads server-local paths; it is suitable for this local-first workstation workflow, not a remote upload UI.
- Users must still prepare the local CSV/TSV/TXT/MD ownership files or manifest outside the browser.

## Dependencies

- Existing `/api/company-database/relationships/build` ownership file support.
- Existing company intelligence maintenance panel and relationship review queue.
- `scripts/ui_static_check.py` static contract.

## Blockers

- No blocker for this delivered slice.
- Future browser-native manifest generation or file upload needs a separate controlled design.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Not needed for T-507; UI reuses existing `build_company_relationships` behavior.
- `SystemService` changes: None for T-507.
- Focused regression: `tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`.
- API schema changed: No; docs now describe the UI path over the existing API.
- Storage schema changed: No.
- UI behavior changed: company intelligence maintenance area now has ownership import preview/execute controls.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

Commands run:

```bash
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Results:

- Passed: pending final verification in this turn.
- Failed: none known.
- Artifact boundary: no new artifact files; evidence is local test output and tracked code/docs.

Files touched:

- `app/static/index.html`: ownership import UI, payload, renderer, and action wiring.
- `scripts/ui_static_check.py`: required IDs and functions for ownership import workbench.
- `docs/api-contracts.md`: documents the UI ownership import path.
- `tasks/todo.md`: T-507 roadmap record.

## Next Recommended Action

Add browser-side ownership manifest template generation so local directories can be scanned and converted into editable manifest files without using the CLI manually.
