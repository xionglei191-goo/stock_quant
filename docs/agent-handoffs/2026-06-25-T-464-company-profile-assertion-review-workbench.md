# Handoff: T-464 Company Profile Assertion Review Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-464

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Expose the T-463 company profile field assertion conflict workflow in the company intelligence workbench, so analysts can see conflict candidates and approve or reject replacements without manually calling the API.

## Background

T-463 added `CompanyProfileFieldAssertion` conflict candidates and review endpoints. That made the data model safer, but the operation was still API-only. The company intelligence platform needs operational review surfaces for company database quality work, especially when official/IR materials produce competing values for the same company profile field.

## Problem Statement

The UI could run profile field extraction and quality reconciliation, but it did not show pending field assertion conflicts. Analysts could not tell whether a refresh created a conflict candidate, nor approve or reject a replacement from the workbench. This left the company database safer at the API layer but incomplete as a usable local research workflow.

## Expected Deliverables

- Add a visible field assertion conflict queue to the company database补齐 panel.
- Show review status, conflict count and superseded count.
- Render `conflict_candidate` / `needs_review` assertions with field, value, evidence and old assertion links.
- Provide approve/reject buttons that call the existing T-463 review API.
- Refresh the queue and company intelligence view after review actions.
- Add UI static contract coverage and browser interaction acceptance for the queue.
- Add backend regression for rejecting a conflict candidate.
- Update roadmap, docs index and handoff records.

## Scope

- In scope: `app/static/index.html`, UI static check, browser interaction acceptance, field assertion reject regression, roadmap and handoff docs.
- Out of scope: new backend endpoints, batch review, review note input widgets, source priority scoring, external data downloads, real broker or live trading integrations.

## Current Findings

- Existing T-463 endpoints are sufficient: `POST /api/company-database/profile-field-assertions` for list and `POST /api/company-database/profile-field-assertions/review` for approve/reject.
- The best UI placement is the existing `公司数据库补齐` block next to deep-field extraction, because that is where conflict candidates are created.
- `company_intelligence` already returns `company_profile.profile_field_assertions`, so the queue can render from loaded company data and refresh through the list API.
- The production-like service on `127.0.0.1:8000` was serving stale UI during validation; a current-code temporary service on `127.0.0.1:8768` proved the new UI behavior.

## Proposed Work Plan

1. Add DOM controls and summary boxes for field assertion review.
2. Add JS payload, render, load and review functions using existing API helpers.
3. Wire the queue into `renderCompanyIntelligence` and global click delegation.
4. Extend static UI contract with new IDs, functions and interaction marker.
5. Extend browser acceptance with a synthetic conflict render check.
6. Add reject-path regression for T-463 review behavior.
7. Update roadmap and handoff records.
8. Run Python, unit, static, browser, security and handoff checks.

## Validation Plan

- Run Python compile for app, tests and scripts.
- Run focused field assertion conflict/reject tests.
- Run full unittest suite.
- Run UI static check.
- Run browser interaction acceptance against current-code temporary service.
- Run security check.
- Run handoff validation.
- Run `git diff --check` before commit.

## Current State

- Completed: company database补齐 panel has `查看字段冲突`, field review status, conflict count, superseded count and conflict assertion table.
- Completed: conflict rows show assertion ID, field, issuer, candidate value, document/evidence and conflicting old assertion IDs.
- Completed: approve/reject buttons call the T-463 review endpoint through event delegation.
- Completed: queue reloads after extraction execution and after review actions.
- Completed: company intelligence load renders existing profile field assertions into the queue without a separate call.
- Completed: static UI and browser interaction checks cover the new queue.
- Completed: reject regression proves old active profile value/evidence remains when a conflict candidate is rejected.
- Blocked: none.

## Dependencies

- T-460 company profile field assertions.
- T-461 local company material inbox.
- T-463 assertion conflict review API.
- Existing company intelligence workbench in `app/static/index.html`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: added field assertion conflict queue UI, render/load/review JS and event wiring.
- `scripts/ui_static_check.py`: added required DOM IDs, JS functions and `review-company-profile-assertion` interaction marker.
- `scripts/ui_interaction_acceptance.py`: added synthetic conflict queue browser check.
- `tests/test_system.py`: added reject-path regression for conflict candidates.
- `tasks/todo.md`: added T-464 completion entry.
- `docs/README.md`: updated task range and workbench capability summary.
- `docs/agent-handoffs/README.md`: added T-464 to related tasks.
- `docs/agent-handoffs/2026-06-25-T-464-company-profile-assertion-review-workbench.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_assertion_conflict_requires_review_before_replacement tests.test_system.SystemServiceTests.test_company_profile_field_assertion_reject_keeps_existing_profile_value
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t464 --timeout 60
python3 -c "from app.server import serve; serve(port=8768)"
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t464 --timeout 60
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
```

Result:

- Passed: UI static check, `required_ids=229`, `required_functions=78`, `interaction_markers=7`.
- Passed: Python compile for app, tests and scripts.
- Passed: focused field assertion conflict/reject tests, 2 tests.
- Failed then diagnosed: browser acceptance against `127.0.0.1:8000` failed because that running service served stale UI, including missing T-462 verdict rendering.
- Passed: browser acceptance against current-code temporary service `127.0.0.1:8768`, 19/19 checks.
- Passed: full unittest suite, 246 tests.
- Passed: security check, 180 files checked, no findings.

## Evidence

Commands run:

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t464 --timeout 60
python3 scripts/security_check.py .
```

Result:

- Passed: UI static check.
- Passed: Python compile.
- Passed: full unittest suite, 246 tests.
- Passed: browser interaction acceptance on current-code temporary service, 19/19 checks.
- Passed: security check.

## Decisions

- Reused existing T-463 APIs rather than adding backend endpoints.
- Put the queue in the company database补齐 block, next to profile field extraction where conflicts are generated.
- Used synthetic browser acceptance data for the queue so the UI check does not depend on a live database already containing conflict candidates.
- Kept review actions limited to approve/reject in the first UI slice; `supersede` remains available through API.

## Risks and Open Questions

- The queue does not yet provide batch approve/reject or a user-entered review note.
- The UI currently shows IDs and compact evidence references; richer before/after old value comparison would need a backend include-conflicts expansion or an assertion-by-ID lookup.
- Source priority and freshness scoring remain future work.

## Artifacts

- `artifacts/ui-interaction-acceptance-t464/ui-interaction-acceptance.json`: local-only browser acceptance evidence from `127.0.0.1:8768`; not valid as non-local production evidence.

## Handoff Checklist

- [x] Workbench conflict queue added.
- [x] Approve/reject actions wired.
- [x] Static UI contract updated.
- [x] Browser acceptance updated and passed on current-code service.
- [x] Backend reject regression added.
- [x] Roadmap updated.
- [x] Handoff created.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Add batch approve/reject and review note input for field assertion conflicts.
2. Add richer old-vs-new field value comparison for conflicts.
3. Add configurable source priority and freshness recommendation rules.

## Next Recommended Action

Implement field-level source priority and freshness scoring so the queue can recommend which conflict candidate should be trusted first, while still requiring review before replacement.
