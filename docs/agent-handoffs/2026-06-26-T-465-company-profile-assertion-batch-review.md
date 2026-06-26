# Handoff: T-465 Company Profile Assertion Batch Review

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-465

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Enhance the company profile field assertion conflict workflow with batch review, reviewer notes, old-vs-new comparison and source/freshness recommendation data.

## Background

T-464 made conflict candidates visible in the company intelligence workbench, but review remained one row at a time and lacked compact old-value comparison or source/freshness recommendation data.

## Problem Statement

Analysts reviewing multiple profile field conflicts need a faster local workflow that still requires explicit human selection. The system should help prioritize conflicts without auto-approving replacements.

## Expected Deliverables

- Batch review support on the existing review endpoint.
- Review note propagation into assertion metadata.
- Old assertion summary and review recommendation data in assertion list payloads.
- UI controls for selection, batch approve/reject and notes.
- Static UI, browser acceptance and unit regression coverage.

## Scope

- In scope: `app/services.py`, company intelligence UI, UI acceptance/static checks, tests, API docs, roadmap and handoff.
- Out of scope: automatic approval, external source downloads, real broker or live trading integrations.

## Current Findings

- Existing conflict records already contain `conflicts_with`, so old-value comparison can be assembled without a new endpoint.
- Recommendation can be a local review assist based on source priority, confidence and freshness; it must not make the final decision.
- The existing review endpoint can preserve compatibility by accepting either `assertion_id` or `assertion_ids`.

## Proposed Work Plan

1. Add recommendation and old-conflict enrichment to field assertion list payloads.
2. Add batch handling to review API.
3. Add UI note, checkbox and batch controls.
4. Extend static/browser acceptance.
5. Add backend regression for batch reject and recommendation fields.
6. Update docs, roadmap and handoff.
7. Run focused and default validation.

## Validation Plan

- Run focused batch review regression.
- Run UI static check and browser interaction acceptance.
- Run Python compile, full unittest suite, security check and handoff validation.

## Current State

- Completed: assertion list responses include `conflicting_assertions` and `review_recommendation`.
- Completed: review API accepts `assertion_ids` for batch approve/reject while preserving single `assertion_id` compatibility.
- Completed: company intelligence workbench has batch approve/reject buttons, a note input, checkboxes, old value summaries and recommendation status.
- Completed: static UI and browser acceptance contracts include the new controls and render path.
- Blocked: none.

## Dependencies

- T-463 assertion conflict review API.
- T-464 company profile assertion review workbench.

## Blockers

- None.

## Files Touched

- `app/services.py`: added assertion recommendation payloads and batch review handling.
- `app/static/index.html`: added batch review UI, note input, checkboxes, old value display and recommendation display.
- `scripts/ui_static_check.py`: added required IDs/functions/interaction marker.
- `scripts/ui_interaction_acceptance.py`: expanded synthetic conflict queue browser check.
- `tests/test_system.py`: added batch reject and recommendation regression.
- `docs/api-contracts.md`: documented batch review and recommendation fields.
- `tasks/todo.md`: added and completed T-465.
- `docs/README.md`, `docs/agent-handoffs/README.md`: updated indexes.
- `docs/agent-handoffs/2026-06-26-T-465-company-profile-assertion-batch-review.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_assertion_batch_approve_supersedes_old_values tests.test_system.SystemServiceTests.test_company_profile_field_assertion_query_recommends_and_batch_rejects_conflicts
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t465
```

Result:

- Passed: focused batch approve/reject tests, 2 tests.
- Passed: UI static check, `required_ids=237`, `required_functions=81`, `interaction_markers=9`.
- Passed: Python compile.
- Passed: full unittest suite, 250 tests.
- Passed: security check, 181 files checked, no findings.
- Passed: browser interaction acceptance on current-code temporary service, 20/20 checks.
- Passed: handoff validation.

## Evidence

- Focused regression proves `review_recommendation` and `conflicting_assertions` are returned, and batch reject preserves old profile values while writing the note.
- UI static check proves new controls and JS functions are present.
- `artifacts/ui-interaction-acceptance-t465/ui-interaction-acceptance.json`: local-only browser acceptance evidence from `127.0.0.1:8768`; not valid as non-local production evidence.

## Decisions

- Recommendation is review assist only; no assertion is auto-approved by score.
- Batch review reuses the existing review endpoint and applies one action/note to selected assertions.
- Old value comparison is a compact summary from conflicting assertion records to avoid adding another lookup endpoint.

## Risks and Open Questions

- Source priority and freshness scoring are intentionally simple and should be calibrated with real review outcomes.
- Batch approve still requires user selection in the UI and does not auto-select recommended candidates.

## Artifacts

- `artifacts/ui-interaction-acceptance-t465/ui-interaction-acceptance.json`: local-only browser evidence when generated; not valid as non-local production evidence.

## Handoff Checklist

- [x] Batch review API added.
- [x] Recommendation payload added.
- [x] UI controls added.
- [x] Static and unit coverage added.
- [x] Roadmap/docs updated.
- [x] Validation run.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Add optional batch review note templates if repeated review reasons become common.
2. Calibrate recommendation scoring after enough real conflict outcomes exist.

## Next Recommended Action

Run browser interaction acceptance on a current-code server and then use real conflict outcomes to calibrate source priority and freshness weights.
