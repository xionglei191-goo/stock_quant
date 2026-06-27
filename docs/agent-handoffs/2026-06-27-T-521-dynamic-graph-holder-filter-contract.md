# Handoff: T-521 Dynamic Graph Holder Filter Contract

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Expose `ownership_holder_key` in `relationship_context.dynamic_graph.recommended_filters` so API consumers can discover the same-holder fact shareholder graph filter from the relationship context response.

## Scope

- In scope: relationship context dynamic graph metadata, focused regression, API contract note, roadmap entry, handoff.
- Out of scope: `/api/graph/query` implementation changes, UI interaction changes, storage schema changes, holder identity canonicalization.

## Background

T-515 added `/api/graph/query` support for `ownership_holder_key`, and the UI uses that key from `approved_shareholder_related_companies` when opening a same fact shareholder network. The relationship context `dynamic_graph.recommended_filters` still listed only issuer/security/relationship/chain filters.

## Problem Statement

The API response should be self-describing. Without `ownership_holder_key` in recommended filters, a downstream consumer can miss the dedicated same-holder fact shareholder network expansion path even though the graph API and UI already support it.

## Expected Deliverables

- Add `ownership_holder_key` to `relationship_context.dynamic_graph.recommended_filters`.
- Add a regression assertion in the approved same-shareholder context test.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `relationship_context()` constructs `dynamic_graph.recommended_filters` in `app/service_modules/company_intelligence.py`.
- The holder-key graph filter is already proven by `test_relationship_context_links_approved_same_shareholder_companies`.
- No frontend change is required because the UI already passes `data-ownership-holder-key`.

## Proposed Work Plan

- Completed: add `ownership_holder_key` to recommended filters.
- Completed: assert the filter in the same-shareholder relationship context regression.
- Completed: document the filter list in `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- This is an additive API metadata change. Consumers that assume an exact recommended filter list length could need adjustment, but the field is intended as a discoverable list.
- This does not solve holder-key normalization across differently named holders; it only exposes the existing stable filter.

## Dependencies

- T-515 holder-key graph filtering.
- Existing `approved_shareholder_related_companies.holder_key` relationship context rows.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies` passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py` passed.
- `python3 scripts/check_handoffs.py` passed, checking 95 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Continue tightening relationship context API self-description by adding source-specific labels or filter examples if downstream consumers need generated graph query links.
