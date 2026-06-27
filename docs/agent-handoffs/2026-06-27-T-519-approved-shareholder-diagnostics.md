# Handoff: T-519 Approved Shareholder Diagnostics

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Split relationship coverage diagnostics so the 13F/institutional same-holder network and approved fact shareholder network are visible as separate diagnostic layers.

## Scope

- In scope: relationship context coverage diagnostics, optional layer labels, UI backfill action mapping, focused regressions, API contract note, roadmap entry, handoff.
- Out of scope: database schema changes, ownership import script behavior, graph query filtering behavior, canonical holder identity matching, real broker or execution behavior.

## Background

`relationship_context.summary` already separates `shareholder_related_companies` from `approved_shareholder_related_companies`. The diagnostic layer still exposed only one generic `shareholder_network`, which could make 13F/holding-derived relationships look equivalent to manually approved fact ownership relationships.

## Problem Statement

Analysts need to know whether the company has a same-holder network from institutional holdings, approved fact ownership records, or both. The coverage response should expose that distinction without making optional manual-review coverage reduce the core required coverage score.

## Expected Deliverables

- Add an optional `approved_shareholder_network` diagnostic layer based on `summary.approved_shareholder_related_companies`.
- Keep `shareholder_network` as the 13F/institutional holdings same-holder layer and clarify its label.
- Keep `next_actions` focused on missing required layers while optional gaps remain visible in diagnostics.
- Route the new layer to existing ownership import/review guidance in the UI.
- Update focused tests, API contracts, roadmap state, and handoff.

## Current Findings

- `app/service_modules/company_intelligence.py` already passes both source-specific counts into `summary`.
- `_relationship_coverage_diagnostics()` was the only place still collapsing shareholder network coverage into one diagnostic layer.
- `renderCompanyRelationshipContext()` already has a backfill action mapper for ownership-related diagnostic layers.

## Proposed Work Plan

- Completed: add `approved_shareholder_network` as an optional diagnostic layer.
- Completed: relabel `shareholder_network` to `13F/持仓股东关联公司`.
- Completed: restrict `next_actions` to missing required layers so optional enhancements do not block complete relationship coverage.
- Completed: map `approved_shareholder_network` to the existing ownership import guidance action.
- Completed: add regression assertions for sparse optional gaps and approved fact same-holder availability.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers
python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- Consumers that list all missing optional layers will now see one more optional diagnostic when approved fact same-holder coverage is absent.
- The diagnostic still depends on approved active ownership relationship quality; it does not solve holder identity canonicalization across differently named entities.

## Dependencies

- Existing `relationship_context.summary.approved_shareholder_related_companies` and `summary.shareholder_related_companies`.
- Existing ownership import/review workflow for creating approved `CompanyRelationship` facts.
- Existing UI relationship context rendering.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers` passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py` passed.
- `python3 scripts/ui_static_check.py` passed.
- `git diff --check` passed.
- `python3 scripts/check_handoffs.py` failed before this rewrite because the handoff used the older template section names; rerun after this rewrite.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module used: yes, the change stays in `app/service_modules/company_intelligence.py` where relationship context diagnostics already live.
- Focused regression: `tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies` and `test_company_relationship_context_reports_missing_chain_layers`.
- API schema, storage schema, UI behavior, paper-only/no-broker boundaries changed: response diagnostics add one optional layer; storage schema and paper-only/no-broker boundaries are unchanged; UI only maps the new layer to an existing action.

## Next Recommended Action

Continue the relationship-context completeness pass by checking whether optional diagnostic layers need analyst-facing grouping or source badges in the relationship panel.
