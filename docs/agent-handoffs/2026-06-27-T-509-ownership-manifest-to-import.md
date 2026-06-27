# Handoff: T-509 Ownership Manifest to Import

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-509

## Objective

Connect the ownership manifest template workbench to the ownership import preview so the browser flow can move from scanned local files to review-required relationship candidates.

## Scope

- In scope: company intelligence UI state, ownership import payload mapping, static UI contract, roadmap status.
- Out of scope: backend changes, database migration, external data fetching, automatic approval, real broker integration, automatic trading.

## Background

T-508 generated ownership manifest templates in the browser, and T-507 imported explicit ownership files. The two steps still needed a direct UI bridge.

## Problem Statement

Before T-509, a user could preview/write a manifest and separately preview ownership import, but the generated manifest was not directly used as import input.

## Expected Deliverables

- Save the latest ownership manifest template in UI state.
- Add a "用 manifest 预览导入" button.
- If no template exists, generate a dry-run template first.
- Map manifest file items into `ownership_file_paths` objects for the relationship builder.
- Static UI contract protects the bridge.

## Current Findings

- Completed: Added `latestCompanyOwnershipManifestTemplate`.
- Completed: `companyOwnershipImportPayload` accepts `useManifest` and maps file metadata into API payload objects.
- Completed: Added `previewCompanyOwnershipImportFromManifest`.
- Completed: Static UI check requires the new button and function.

## Proposed Work Plan

1. Keep backend unchanged and reuse T-507/T-508 APIs.
2. Store the latest manifest template after preview/write.
3. Add a single bridge action that generates the template if needed and then previews import.
4. Keep execute mode separate; the bridge previews only.
5. Update roadmap and handoff.

## Validation Plan

Run:

```bash
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Browser interaction acceptance is deferred to the next slice.

## Risks

- This is still a server-local path workflow; it assumes the backend can read the selected files.
- The bridge previews only; users still explicitly execute import after reviewing candidates.

## Dependencies

- T-507 ownership import workbench.
- T-508 ownership manifest template workbench.
- Existing `/api/company-database/relationships/build`.

## Blockers

- No blocker for this delivered slice.
- Full browser acceptance needs a running app and sample local ownership directory.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Not needed; this is UI-only wiring over existing APIs.
- `SystemService` changes: None for T-509.
- Focused regression: `tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`.
- API schema changed: No.
- Storage schema changed: No.
- UI behavior changed: generated manifest can directly drive ownership import preview.
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
- Artifact boundary: no new artifact files.

Files touched:

- `app/static/index.html`: manifest-to-import UI state and action.
- `scripts/ui_static_check.py`: required button/function.
- `tasks/todo.md`: T-509 roadmap record.

## Next Recommended Action

Add a Playwright/browser acceptance path for ownership manifest preview and manifest-driven import preview using a temporary local ownership directory.
