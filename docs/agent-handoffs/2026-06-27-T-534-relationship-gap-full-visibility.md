# Handoff: T-534 Relationship Gap Full Visibility

## Metadata

- Status: DONE
- Owner group: Product and UI, Research and AI Workflows
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-534

## Objective

Ensure every required relationship-chain gap remains visible and actionable from both the API and company intelligence UI. The relationship diagnostics must not hide later missing layers behind arbitrary display limits.

## Scope

- `app/service_modules/company_intelligence.py`: relationship coverage diagnostics and next-action output.
- `app/static/index.html`: company intelligence relationship gap row rendering.
- `tests/test_system.py`: API regression for next-action layer coverage.
- `scripts/ui_interaction_acceptance.py`: browser regression for all relationship gap buttons.
- `docs/api-contracts.md` and `tasks/todo.md`: contract and roadmap closure.

## Background

T-505 added relationship diagnostics and T-506 wired diagnostics to UI actions. Later slices completed ownership, fact-shareholder, 13F holder, industry summary, and graph recommendation behavior. During the completion pass, the API still capped relationship `next_actions` and the UI capped displayed missing diagnostics, which could hide some required gap layers on sparse companies.

## Problem Statement

The user wants complete logic-chain visibility. If a company is missing industry position, peers, upstream, downstream, ownership/control, and graph edges, every required layer must be visible and actionable. Showing only the first few gaps can make the system look more complete than it is.

## Expected Deliverables

- API `relationship_context.coverage_diagnostics.next_actions` covers all `missing_required_layers`.
- Company intelligence UI renders all unavailable diagnostic layers as "关系链缺口" rows.
- Browser acceptance proves all missing gap buttons render and route to preview/import/graph entry points.
- Documentation states that relationship-context next actions are not a truncated sample.

## Current Findings

- Before T-534, `next_actions` returned `next_actions[:5]`.
- Before T-534, the UI rendered only `.slice(0, 4)` unavailable diagnostics.
- Sparse relationship contexts can have six required missing layers, so those caps could hide required remediation paths.

## Proposed Work Plan

1. Remove the API `next_actions` cap.
2. Remove the UI unavailable-diagnostic row cap.
3. Add API regression to compare next-action layers with `missing_required_layers`.
4. Expand browser acceptance to a six-layer relationship gap fixture.
5. Update contract, roadmap, and handoff.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t534 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: Relationship diagnostic behavior lives in `app/service_modules/company_intelligence.py`.
- Focused regression: `test_company_relationship_context_reports_missing_chain_layers` checks API next actions cover all missing required layers.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API/UI behavior changed by removing truncation; storage schema and paper-only/no-broker boundaries are unchanged.

## Risks

- Rendering all missing diagnostics can create a longer table for sparse companies. This is intentional because missing required relationship layers must remain visible.
- Graph recommendations still have a separate visible limit; T-533 prioritizes specific second-hop network recommendations inside that display area.

## Dependencies

- T-505 relationship coverage diagnostics.
- T-506 relationship gap action wiring.
- Existing company intelligence UI and graph entry helpers.

## Blockers

- None.

## Handoff Checklist

- [x] Removed API next-action truncation.
- [x] Removed UI relationship gap row truncation.
- [x] Added focused API regression.
- [x] Added browser acceptance fixture for six missing layers.
- [x] Updated API contract and roadmap.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=23`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t534 --timeout 60`: passed on a clean local SQLite/object-store service; 40/40 checks passed, including `company_relationship_gap_buttons_open_expected_entry`.
- `python3 scripts/check_handoffs.py`: passed with 108 markdown files checked.
- `git diff --check`: passed.
- A mistaken attempt to py-compile `app/static/index.html` failed because HTML/CSS is not Python; the proper static UI validator passed.

## Next Recommended Action

Continue the relationship-logic completion audit beyond gap visibility, especially whether every displayed relationship dimension has both source provenance and a direct remediation or graph entry.
