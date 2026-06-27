# Handoff: T-510 Ownership Browser Acceptance

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main `/home/xionglei/Project/sotck_quant`
- Related tasks: T-510

## Objective

Add real browser acceptance coverage for the ownership manifest to import preview workflow.

## Scope

- In scope: `scripts/ui_interaction_acceptance.py`, roadmap status, this handoff.
- Out of scope: backend API behavior changes, database migrations, external data fetching, automatic approval, real broker integration, automatic trading.

## Background

T-507 added ownership table import preview, T-508 added ownership manifest template preview, and T-509 connected the latest manifest to import preview in the UI. T-510 verifies that sequence with a browser and real local API calls.

## Problem Statement

The ownership workflow was functionally connected, but the default real browser acceptance suite did not prove that a user could fill a local directory, preview a manifest, and immediately use that manifest to preview ownership relationship candidates.

## Expected Deliverables

- A fixture-backed browser check for ownership manifest preview.
- A second browser check for manifest-to-import preview using the latest manifest.
- Failure diagnostics that include ownership manifest/import status and rows.
- Roadmap and handoff updates with reproducible validation commands.

## Current State

- Completed: Browser diagnostics now capture ownership manifest and ownership import statuses and table rows.
- Completed: The browser script creates a local CSV ownership fixture under the acceptance output directory.
- Completed: Added `company_ownership_manifest_preview_real_api` to fill the ownership root/glob/default kind, click preview, and assert the manifest result.
- Completed: Added `company_ownership_manifest_to_import_preview_real_api` to click the manifest-to-import bridge and assert the import preview result.
- In progress: none.
- Not started: execution-mode import browser validation with isolated candidate review persistence.
- Blocked: none.

## Current Findings

- The local browser suite can cover this workflow without external data by generating a small CSV fixture in the output directory.
- The new preview bridge succeeds against a current-code SQLite-backed local server.
- Exact file-display text is not the right assertion boundary; workflow state, candidate count, non-empty parsed rows, and operation summary are more stable.

## Proposed Work Plan

1. Add concise diagnostics for ownership manifest/import failures.
2. Generate a deterministic ownership CSV fixture during browser acceptance setup.
3. Add one browser check for manifest preview and one for manifest-to-import preview.
4. Run static, browser, handoff, and whitespace validation.

## Validation Plan

Run:

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/sotck_quant_t510.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/sotck_quant_t510_objects AI_QUANT_SEARCH_BACKEND=local python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8771 --output-dir artifacts/ui-interaction-acceptance-t510 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Files Touched

- `scripts/ui_interaction_acceptance.py`: added fixture-backed ownership manifest and manifest-to-import browser checks plus focused diagnostics.
- `tasks/todo.md`: added T-510 as the completed acceptance slice.
- `docs/agent-handoffs/2026-06-27-T-510-ownership-browser-acceptance.md`: records the task state and validation.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8771 --output-dir artifacts/ui-interaction-acceptance-t510 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: `python3 -m py_compile scripts/ui_interaction_acceptance.py`.
- Passed: `python3 scripts/ui_static_check.py`.
- Passed: `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8771 --output-dir artifacts/ui-interaction-acceptance-t510 --timeout 60` with `check_count=30`, `failure_count=0`; included `company_ownership_manifest_preview_real_api` and `company_ownership_manifest_to_import_preview_real_api`.
- Failed: none known.
- Not run: execution-mode import browser validation; kept out of scope because it writes local candidate relationships and should use isolated data storage.

## Decisions

- The browser acceptance uses a generated local CSV fixture instead of external data so the test remains reproducible and within local-only data boundaries.
- The import preview assertion checks status, candidate count, non-empty parsed rows, and the operation summary rather than exact display text for a file name, because UI label normalization can change without breaking the workflow.
- The bridge remains preview-only; users must explicitly run the import after reviewing candidates.

## Dependencies

- T-507 ownership table import workbench.
- T-508 ownership manifest template workbench.
- T-509 manifest-to-import UI bridge.
- Local Chrome/Chromium for the browser acceptance script.

## Blockers

- No blocker for the completed preview acceptance.
- Execution-mode acceptance is intentionally deferred until the test can isolate local candidate relationship writes.

## Risks and Open Questions

- The full `ui_interaction_acceptance.py` suite depends on a current-code local server and Chrome availability.
- A future execution-mode test should isolate data paths before writing candidate relationships.

## Artifacts

- `artifacts/ui-interaction-acceptance-t510`: local-only browser acceptance output, generated by `scripts/ui_interaction_acceptance.py`; contains generated CSV fixture, Chrome profile, screenshots/JSON results if the script completes.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Not needed for T-510; this is browser acceptance coverage over existing APIs.
- `SystemService` changes: None for T-510.
- Focused regression: `scripts/ui_interaction_acceptance.py` real browser checks `company_ownership_manifest_preview_real_api` and `company_ownership_manifest_to_import_preview_real_api`.
- API schema changed: No.
- Storage schema changed: No.
- UI behavior changed: No user-facing behavior added in T-510; acceptance coverage only.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py`: passed.
- `python3 scripts/ui_static_check.py`: passed.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8771 --output-dir artifacts/ui-interaction-acceptance-t510 --timeout 60`: passed, `30/30` checks, `failure_count=0`.
- `python3 scripts/check_handoffs.py`: pending rerun after this handoff format fix.
- `git diff --check`: passed before this handoff format fix; pending rerun.

## Next Steps

1. Add an isolated execution-mode browser check for ownership import when a clean data directory strategy is available.
2. Keep ownership candidate review queue validation separate from preview-only manifest wiring.
3. If the browser suite becomes slow, add a focused filter flag to `scripts/ui_interaction_acceptance.py`.

## Next Recommended Action

Add an isolated execution-mode browser check for ownership import and candidate review refresh after a clean data directory strategy is available.
