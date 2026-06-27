# Handoff: T-536 Relationship Action Targets

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows, Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-536

## Objective

Make relationship-chain remediation actions directly routable. `next_actions` and `enhancement_actions` should explain which API/UI entry point can handle each missing layer.

## Scope

- `app/service_modules/company_intelligence.py`: relationship action target metadata.
- `tests/test_system.py`: focused regression for target endpoint/UI action metadata.
- `docs/api-contracts.md`: action `target` contract.
- `tasks/todo.md`: roadmap closure.

## Background

T-534 made required gap actions complete. T-535 added optional enhancement actions. Both lists still required consumers to know hard-coded routing rules for company database batch build, ownership import/review, or graph query.

## Problem Statement

The relationship logic chain should be navigable by UI, scripts, and future agents without parsing Chinese text or duplicating frontend routing logic. A gap action must describe the endpoint and UI action that can handle it.

## Expected Deliverables

- Every relationship backfill/enhancement action includes a `target` object.
- Industry/peer/upstream/downstream actions target `/api/company-database/batch/build`.
- Ownership/shareholder-network actions target `/api/company-database/relationships/build`, with review and manifest endpoints.
- Graph-edge actions target `/api/graph/query`.
- Tests and docs lock the target contract.

## Current Findings

- Before T-536, action objects contained `action`, `layer`, `label`, and `reason`.
- UI already knew routing via `backfillActionForLayer`, but API consumers did not.

## Proposed Work Plan

1. Add a domain helper mapping relationship layers to target endpoint metadata.
2. Attach target metadata to required and optional action objects.
3. Add focused tests for representative required and optional targets.
4. Update API contract, roadmap, and handoff.
5. Run focused validation.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: The routing metadata lives in `app/service_modules/company_intelligence.py`.
- Focused regression: `test_company_relationship_context_reports_missing_chain_layers` checks endpoint/UI action metadata on required and optional relationship actions.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API payload gains action `target` metadata; storage/UI/no-broker boundaries are unchanged.

## Risks

- Target metadata is advisory and defaults to `default_execute=false`; callers must still pass explicit execute flags for write operations.
- If future routes change, this target map must be updated with the UI routing helper.

## Dependencies

- T-534 full required gap visibility.
- T-535 optional enhancement action split.
- Existing company database batch build, ownership import/review, and graph query APIs.

## Blockers

- None.

## Handoff Checklist

- [x] Added relationship action target metadata.
- [x] Added focused regression.
- [x] Updated API contract and roadmap.
- [x] Run final validation commands after this handoff is added.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=23`, `node_check=passed`.
- `python3 scripts/check_handoffs.py`: passed with 110 markdown files checked.
- `git diff --check`: passed.

## Next Recommended Action

Run final validation commands and continue auditing whether each relationship action is also surfaced in the UI with source provenance.
