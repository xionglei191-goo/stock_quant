# Handoff: T-526 Shareholder Related Total Summary

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Add `relationship_context.summary.shareholder_related_companies_total` so API consumers share the same shareholder-related total used by the UI.

## Scope

- In scope: relationship context summary field, UI read path, focused regressions, API contract note, roadmap entry, handoff.
- Out of scope: storage schema changes, graph query behavior, ownership import behavior, browser acceptance expansion.

## Background

T-525 fixed the UI summary by adding approved fact shareholder network count and 13F/holding same-holder count together. That total still lived only in the frontend expression, leaving API consumers to repeat the same calculation.

## Problem Statement

The relationship context should expose a canonical total for shareholder-related companies. Without a backend summary field, UI, scripts, and future agents can drift in how they add fact and holding-derived networks.

## Expected Deliverables

- Add `summary.shareholder_related_companies_total`.
- Keep existing source-specific fields unchanged.
- Make the UI prefer the total field while retaining a fallback expression.
- Add focused test assertions for both source-specific scenarios.
- Update API contracts, roadmap, and handoff.

## Current Findings

- Backend already has both `approved_shareholder_related_rows` and `shareholder_related_rows` when building `summary`.
- Existing tests cover one 13F/holding network case and one approved fact shareholder network case.
- UI top metric can read the new total without changing visible behavior from T-525.

## Proposed Work Plan

- Completed: add `shareholder_related_companies_total` to `relationship_context.summary`.
- Completed: update UI summary rendering to prefer the new total field.
- Completed: add regression assertions in `test_company_intelligence_first_class_models_are_exposed_and_aggregated` and `test_relationship_context_links_approved_same_shareholder_companies`.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- This is an additive API field. Consumers that snapshot exact summary keys should accept the new field.
- The total intentionally adds two source layers with different provenance; source-specific fields remain available and should be used when provenance matters.

## Dependencies

- Existing `summary.approved_shareholder_related_companies`.
- Existing `summary.shareholder_related_companies`.
- T-525 UI split count rendering.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_static_check.py` passed.
- `python3 scripts/ui_static_check.py` passed with `interaction_markers=17`, `required_functions=162`, `required_ids=379`, and `node_check=passed`.
- `python3 scripts/check_handoffs.py` passed, checking 100 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Consider adding source-specific percentage or freshness metadata if the two shareholder-related layers start driving prioritization decisions.
