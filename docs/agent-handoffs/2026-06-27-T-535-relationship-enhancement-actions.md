# Handoff: T-535 Relationship Enhancement Actions

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows, Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-535

## Objective

Expose machine-readable remediation for optional relationship enhancement layers, not only required backfill layers. API consumers should not need to infer enhancement next steps from diagnostic text.

## Scope

- `app/service_modules/company_intelligence.py`: relationship coverage diagnostic payload.
- `tests/test_system.py`: focused relationship context regression.
- `docs/api-contracts.md`: API contract for `enhancement_actions`.
- `tasks/todo.md`: roadmap closure.

## Background

T-534 made required relationship gaps fully visible and ensured `next_actions` covered all `missing_required_layers`. The remaining optional gaps, such as 13F/holding same-holder networks and approved factual shareholder networks, were still only represented by `missing_optional_layers` and diagnostics rows.

## Problem Statement

Optional does not mean irrelevant. "该股东还有哪些公司" can be answered by fact shareholder networks or 13F holder networks, and both should be discoverable by scripts, UI, and future agents. Without an explicit action list, non-UI consumers must parse labels or recommended text.

## Expected Deliverables

- `relationship_context.coverage_diagnostics.enhancement_actions[]` covers every missing optional layer.
- Outer `relationship_context.enhancement_actions[]` mirrors the diagnostics-level list.
- Required backfill actions remain in `next_actions[]`; optional enhancement actions use `relationship_enhancement`.
- Tests and docs describe the split.

## Current Findings

- Before T-535, optional layers were visible in `missing_optional_layers` and UI gap rows, but had no dedicated machine-readable action list.
- The UI already maps `shareholder_network` and `approved_shareholder_network` to ownership import/review guidance, so this task is API self-description rather than a new UI flow.

## Proposed Work Plan

1. Add `enhancement_actions` for unavailable non-required diagnostic layers.
2. Expose it at the outer relationship context level.
3. Add focused unit assertions for action/layer parity.
4. Update API contract, roadmap, and handoff.
5. Run focused checks.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: The new action split lives in `app/service_modules/company_intelligence.py`.
- Focused regression: `test_company_relationship_context_reports_missing_chain_layers` checks enhancement-action layer parity with `missing_optional_layers`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API payload gains `enhancement_actions`; storage/UI/no-broker boundaries are unchanged.

## Risks

- API clients that only read `next_actions` will continue to see required backfill work but not optional enhancement work. This is intentional; consumers that want full relationship depth should read both lists.

## Dependencies

- T-505 relationship coverage diagnostics.
- T-519/T-527 split fact shareholder and 13F holder network diagnostics.
- T-534 full required gap visibility.

## Blockers

- None.

## Handoff Checklist

- [x] Added enhancement action payload.
- [x] Exposed enhancement actions at relationship context top level.
- [x] Added focused regression.
- [x] Updated API contract and roadmap.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py scripts/ui_static_check.py app/services.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=23`, `node_check=passed`.
- `python3 scripts/check_handoffs.py`: passed with 109 markdown files checked.
- `git diff --check`: passed.

## Next Recommended Action

Run final validation commands and continue auditing whether every relationship dimension has source provenance plus either a graph entry, a required backfill action, or an enhancement action.
