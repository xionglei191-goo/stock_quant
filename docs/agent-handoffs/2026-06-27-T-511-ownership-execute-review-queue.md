# Handoff: T-511 Ownership Execute Review Queue

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main `/home/xionglei/Project/sotck_quant`
- Related tasks: T-511

## Objective

Complete the browser workflow from ownership table manifest preview to executed ownership candidate import and visible relationship review queue.

## Scope

- In scope: relationship builder response payload, company intelligence UI ownership import/review rendering, browser interaction acceptance, roadmap status.
- Out of scope: schema migration, external data fetching, automatic relationship approval, real broker integration, automatic trading.

## Background

T-510 proved the preview flow. The next missing link was execution-mode visibility: after importing ownership candidates, the user should immediately see the review queue that decides whether those candidates become trusted graph relationships.

## Problem Statement

The UI already had a run button for ownership import, but the review queue refresh relied on re-reading company intelligence and passed array-shaped data into a renderer that expected a wrapped payload. That could leave users with an executed import but an empty-looking relationship review queue.

## Expected Deliverables

- Relationship builder returns review-ready relationship candidate rows.
- Ownership import execution renders those rows directly in the relationship review queue.
- Relationship review renderer accepts the payload shapes used by existing callers.
- Browser acceptance covers the execute path and visible review candidate.

## Current State

- Completed: `build_company_relationships` returns `relationship_review_candidates` and `relationship_review_candidate_count`.
- Completed: `renderCompanyRelationshipReview` now accepts arrays and wrapped relationship payloads.
- Completed: Ownership import execution reuses the latest manifest when no explicit file list is entered.
- Completed: Browser acceptance includes `company_ownership_import_execute_refreshes_review_queue`.
- In progress: none.
- Not started: approving an imported ownership candidate and verifying the active graph edge in the browser.
- Blocked: none.

## Current Findings

- Existing backend candidate rows already have the recommendation data needed by the review UI.
- Returning a small review-ready slice from the builder is enough; no storage schema change is needed.
- The execution browser check should run against isolated SQLite/object-store paths because it writes local candidate relationships.

## Proposed Work Plan

1. Extend relationship build result with review-ready candidate rows.
2. Make the relationship review renderer tolerant of existing payload shapes.
3. Wire ownership import execution to render returned candidates before refreshing company intelligence.
4. Add static, unit, and browser acceptance coverage.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_static_check.py
python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8772 --output-dir artifacts/ui-interaction-acceptance-t511 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Files Touched

- `app/services.py`: relationship builder returns review-ready candidates and total candidate count.
- `app/static/index.html`: ownership import execution reuses manifest input and renders returned review candidates; relationship review renderer accepts multiple payload shapes.
- `scripts/ui_static_check.py`: protects the new ownership review helper functions.
- `scripts/ui_interaction_acceptance.py`: adds execution-mode browser acceptance for review queue visibility.
- `tests/test_system.py`: verifies local ownership file execution returns review-ready candidate rows.
- `tasks/todo.md`: records T-511 status and validation.
- `docs/agent-handoffs/2026-06-27-T-511-ownership-execute-review-queue.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_static_check.py
python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8772 --output-dir artifacts/ui-interaction-acceptance-t511 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: unit/static/py_compile checks before this handoff was written.
- Passed: `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8772 --output-dir artifacts/ui-interaction-acceptance-t511 --timeout 60` with `check_count=31`, `failure_count=0`; included `company_ownership_import_execute_refreshes_review_queue`.
- Pending: handoff validation and whitespace check after this handoff update.
- Failed: none known.
- Not run: graph active-edge verification after approving the imported candidate.

## Decisions

- Keep the relationship builder as the existing API surface and return a review-ready slice instead of adding a separate import status endpoint.
- Keep imported ownership relationships in `needs_review` and `unknown` status; execution means candidate persistence, not approval.
- Reuse the latest manifest for execution only when the user has not entered explicit file paths, so explicit file input still wins.

## Dependencies

- T-507 ownership import workbench.
- T-508 ownership manifest template workbench.
- T-509 manifest-to-import bridge.
- T-510 preview browser acceptance.
- Current relationship review API and UI.

## Blockers

- No blocker for the completed execution-to-review slice.
- Approval-to-active-graph browser validation remains a follow-up.

## Risks and Open Questions

- The returned review-ready slice is capped at 50 rows while the count reflects all candidates; bulk imports may still require a dedicated paginated review list.
- Execution-mode browser acceptance writes to the active service store, so it should keep using isolated local startup settings.

## Artifacts

- `artifacts/ui-interaction-acceptance-t511`: local-only browser acceptance output generated by `scripts/ui_interaction_acceptance.py`; valid for this machine and isolated test service only.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: Minimal response shaping only; no new relationship creation rules were added.
- Domain module used: Existing relationship builder and company quality helpers are reused; no new domain module was needed for response shaping.
- `SystemService` changes: `build_company_relationships` now includes review-ready candidate rows from already planned/created relationships.
- Focused regression: `tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files` checks `relationship_review_candidates` and recommendations.
- API schema changed: Additive response fields on `/api/company-database/relationships/build`: `relationship_review_candidates`, `relationship_review_candidate_count`.
- Storage schema changed: No.
- UI behavior changed: Ownership import execution now immediately populates the relationship review queue.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`: passed before this handoff was written.
- `python3 scripts/ui_static_check.py`: passed before this handoff was written.
- `python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`: passed before this handoff was written.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8772 --output-dir artifacts/ui-interaction-acceptance-t511 --timeout 60`: passed, `31/31` checks, `failure_count=0`.
- Handoff validation and `git diff --check`: pending final rerun.

## Next Steps

1. Add isolated browser acceptance for approving an imported ownership candidate.
2. Verify the approved ownership relationship appears as an active relationship graph edge.
3. Consider paginated review list loading for imports with more than 50 candidates.

## Next Recommended Action

Add approval-to-active-graph browser validation for an imported ownership candidate using isolated local service storage.
