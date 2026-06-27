# Handoff: T-532 Institutional Holder Graph

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI; Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-532

## Objective

Let 13F/institutional holding same-holder networks expand in the relationship graph the same way approved factual shareholder networks already can.

## Scope

- `app/service_modules/company_intelligence.py`: add normalized 13F holder keys to relationship context rows and expose `institutional_holder_key` in graph recommendations.
- `app/services.py`: support `institutional_holder_key` filters in `/api/graph/query` and return same-holder institutional holding graph edges.
- `app/static/index.html`: add UI data attributes, graph filter chip support, and cross-company holder graph behavior.
- `scripts/ui_interaction_acceptance.py`: add browser acceptance for 13F holder graph expansion and loosen an older total-count assertion to allow fact plus holding networks together.
- `scripts/ui_static_check.py`: guard institutional holder UI markers.
- `tests/test_system.py`: add API and graph regression coverage.
- `docs/api-contracts.md` and `tasks/todo.md`: record the contract and roadmap closure.

## Background

Approved factual shareholder relationships already supported `ownership_holder_key` graph expansion. The parallel 13F/holding-derived `shareholder_related_companies` rows were visible but could only open a general company graph, so the user-visible answer to "this shareholder/holder also has which companies" was incomplete for the holding network layer.

## Problem Statement

The relationship model separated fact shareholder networks from 13F/holding networks, but only the fact network had a dedicated graph filter and readable chip. This left the 13F branch less dynamic and harder to inspect from the UI.

## Expected Deliverables

- 13F shareholder/holder rows expose a stable `holder_key`.
- `/api/graph/query` accepts `institutional_holder_key` aliases and returns same-holder institutional holdings across issuers.
- UI rows carry `data-institutional-holder-key` and `data-institutional-holder-label`.
- Graph filter chips show a readable "13F持有人" chip while preserving raw key trace.
- Browser acceptance proves the UI click opens the same-holder network.

## Current Findings

- `relationship_context.ownership.shareholder_related_companies` previously had `holder_id` and `holder_name`, but no normalized `holder_key`.
- `openRelationshipGraphContext` previously defaulted to the active security id, which is too narrow for cross-company holder networks. It now suppresses that default when holder-key filters are present.
- `register_13f_holding` requires `report_period` in `YYYY-MM-DD`; the browser fixture uses `2026-03-31`.

## Proposed Work Plan

1. Add `institutional_holder_key` normalization and relationship-context fields.
2. Add graph query filtering and same-holder holding expansion.
3. Add UI row attributes, graph filter chips, and click propagation.
4. Add focused API regression and browser acceptance.
5. Update contracts, todo, and this handoff.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t532-clean --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: Limited graph-query filter behavior was added in `SystemService.query_graph`.
- Domain module usage: holder-key normalization lives in `app/service_modules/company_intelligence.py`; `SystemService` only wires the existing graph facade to the new filter because `/api/graph/query` graph assembly currently resides there.
- Focused regression: `test_company_intelligence_first_class_models_are_exposed_and_aggregated` now asserts `institutional_holder_key` context/recommendation output and same-holder graph results.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API query behavior and UI graph behavior changed; storage schema is unchanged; paper-only/no-broker boundaries are unchanged and the new path remains 13F/holding research context only.

## Risks

- `institutional_holder_key` is based on filer CIK when present and filer/holder name otherwise. Name-only keys can collide across unrelated filers if source data lacks CIK.
- The graph filter represents 13F/holding co-ownership context, not factual shareholder/control ownership.

## Dependencies

- Existing `InstitutionalHolding` records and `/api/13f/holdings`.
- Existing company intelligence relationship-context view.
- Existing graph UI click and chip mechanisms.

## Blockers

- None.

## Handoff Checklist

- [x] Read current relationship-context, graph query, and UI graph code.
- [x] Keep behavior within research/13F graph context; no broker or execution flow touched.
- [x] Add SystemService growth-freeze review.
- [x] Run focused unit, static, browser, handoff, and diff checks.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py tests/test_system.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=23`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t532-clean --timeout 60`: passed on a clean local SQLite/object-store service; 38/38 checks passed, including `company_13f_holder_graph_click_loads_same_holder_network`.
- `git diff --check`: passed.

## Next Recommended Action

Continue the relationship-logic completion pass by auditing whether graph recommendations expose all UI-clickable relationship dimensions, especially mixed fact/holding shareholder summaries and missing-data next actions.
