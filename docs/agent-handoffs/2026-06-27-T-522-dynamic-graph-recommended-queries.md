# Handoff: T-522 Dynamic Graph Recommended Queries

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Add concrete graph query suggestions to `relationship_context.dynamic_graph` so downstream consumers can directly expand the current company's relationship graph without reconstructing query parameters from several sections.

## Scope

- In scope: relationship context `dynamic_graph.recommended_queries`, focused regression, API contract note, roadmap entry, handoff.
- Out of scope: graph query execution behavior, UI click handlers, storage schema, holder identity canonicalization.

## Background

T-521 added `ownership_holder_key` to the recommended filter list. That made available filters discoverable, but consumers still had to infer concrete query payloads from industry rows, relationship types, and approved shareholder rows.

## Problem Statement

The relationship context should act as a dynamic exploration handoff. It should provide graph query suggestions for the company center, chain nodes, relationship types, and approved fact shareholder networks in a consistent structure.

## Expected Deliverables

- Add `dynamic_graph.recommended_queries[]` entries with `label`, `query`, and `reason`.
- Include company-centered, chain-node, relationship-type, and same fact shareholder query suggestions.
- Add regression coverage for company-centered and holder-key same-shareholder queries.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `relationship_context()` already has focus issuer IDs, chain nodes, expansion relationship types, and approved same-holder rows in one place.
- Existing UI graph entry points already use equivalent query parameters; this change only exposes them in API metadata.
- The same-shareholder regression has the fixture needed to prove the holder-key recommended query.

## Proposed Work Plan

- Completed: build `recommended_graph_queries` in `app/service_modules/company_intelligence.py`.
- Completed: include up to 10 query suggestions under `dynamic_graph.recommended_queries`.
- Completed: assert company-center and holder-key same-shareholder query suggestions in `test_relationship_context_links_approved_same_shareholder_companies`.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- `recommended_queries` is additive response metadata. Consumers that snapshot the exact `dynamic_graph` object may need to accept the new field.
- Query suggestions are capped at 10 to keep the response compact; they are not a full graph expansion plan.

## Dependencies

- Existing relationship context industry rows, expansion relationship types, and approved shareholder related rows.
- `/api/graph/query` support for issuer, relationship type, chain, and `ownership_holder_key` filters.

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
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py` passed.
- `python3 scripts/check_handoffs.py` passed, checking 96 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Consider rendering `dynamic_graph.recommended_queries` as a compact graph entry menu if users need a visible list of all suggested graph expansions.
