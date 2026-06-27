# Handoff: T-533 Graph Recommendation Priority

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-533

## Objective

Prioritize concrete second-hop graph recommendations, especially approved factual shareholder and 13F holder networks, ahead of generic relationship-type graph entries.

## Scope

- `app/service_modules/company_intelligence.py`: reorder `dynamic_graph.recommended_queries[]`.
- `scripts/ui_interaction_acceptance.py`: add browser acceptance for the 13F holder graph recommendation entry.
- `tasks/todo.md`: record T-533 closure.

## Background

T-532 added 13F holder graph expansion. The API generated `institutional_holder_key` recommendations, but the UI renders only the first eight graph recommendations. Generic `relationship_type` recommendations could push specific holder-network entries below the visible cutoff.

## Problem Statement

The user wants dynamic relationship graph exploration to expose complete logic chains. A concrete "same holder" second-hop graph is more actionable than a generic relationship-type filter and should not be hidden behind lower-priority recommendations.

## Expected Deliverables

- Recommended query order: company center, industry-chain nodes, approved factual shareholder networks, 13F holder networks, then generic relationship types.
- Browser acceptance proves the 13F holder recommendation row opens the same-holder graph network.

## Current Findings

- Before T-533, generic relationship types were appended before holder-network recommendations.
- `recommendedGraphQueryAttrs` already supports `institutional_holder_key`, so no UI helper change was needed.

## Proposed Work Plan

1. Move generic relationship-type recommendation generation after approved shareholder and 13F holder recommendations.
2. Add `company_recommended_13f_holder_graph_query_click_loads_network` to the browser acceptance matrix.
3. Update roadmap and handoff.
4. Run focused unit/static/browser/handoff checks.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t533 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: Recommendation ordering lives in `app/service_modules/company_intelligence.py`.
- Focused regression: existing company-intelligence unit coverage still checks that `institutional_holder_key` recommendations exist; browser acceptance checks the visible recommendation entry opens the graph.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI-visible recommendation ordering changed; API/storage schema and paper-only/no-broker boundaries are unchanged.

## Risks

- Recommendation ranking is still deterministic rule ordering rather than a scored ranking model. This is acceptable for now because specific second-hop graph paths are intentionally prioritized over generic filters.

## Dependencies

- T-532 `institutional_holder_key` graph support.
- Existing graph recommendation UI row rendering.

## Blockers

- None.

## Handoff Checklist

- [x] Verified recommendation ordering gap.
- [x] Reordered recommendations in the domain module.
- [x] Added browser acceptance for 13F holder recommendation entry.
- [x] Ran focused validation and recorded evidence.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=23`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t533 --timeout 60`: passed on a clean local SQLite/object-store service; 39/39 checks passed, including `company_recommended_13f_holder_graph_query_click_loads_network`.
- `git diff --check`: passed.

## Next Recommended Action

Continue the relationship-logic completion pass by auditing missing-data next actions and whether every relationship dimension has a direct remediation entry.
