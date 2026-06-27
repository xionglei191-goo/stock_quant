# Handoff: T-530 Industry Network UI Trace

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-530

## Objective

Expose the industry relationship summary from `coverage_diagnostics.industry_network_summary` on the company intelligence UI counters for peers, upstream companies, and downstream companies.

## Scope

- `app/static/index.html`: add structured trace attributes and tooltip title to the three industry relationship counters.
- `scripts/ui_static_check.py`: guard the new UI trace helper marker.
- `docs/api-contracts.md`: document the UI trace attributes for `industry_network_summary`.
- `tasks/todo.md`: record T-530 as completed after validation.

## Background

T-529 added API-level `summary.industry_related_companies_total` and `coverage_diagnostics.industry_network_summary`. The UI already showed separate peer/upstream/downstream counts, but those counters did not expose the aggregate diagnostic summary to automated acceptance or manual inspection.

## Problem Statement

The user asked to continue completing the multi-dimensional relationship logic, especially visible company industry-chain links and graph-ready relationship context. Without UI trace attributes, the top industry counters were visible but not directly auditable against the API diagnostic summary.

## Expected Deliverables

- Peer/upstream/downstream counters include `data-network-total`, `data-network-part`, `data-chain-nodes`, and a readable title.
- Static UI contract detects accidental removal of the trace helper.
- API contract and roadmap reflect the new trace surface.
- Handoff captures validation and remaining risk.

## Current Findings

- `relationship_context.coverage_diagnostics.industry_network_summary` is present in the API contract.
- `renderCompanyRelationshipContext` already receives `diagnostics` and can use the summary without extra API calls.
- No backend or storage schema change is required.

## Proposed Work Plan

1. Add a small local helper in `renderCompanyRelationshipContext` to write industry network trace attributes to the three counters.
2. Add the helper marker to `scripts/ui_static_check.py`.
3. Update `docs/api-contracts.md`, `tasks/todo.md`, and this handoff.
4. Run focused static and handoff validation.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: Not applicable; T-530 only exposes existing `relationship_context.coverage_diagnostics.industry_network_summary` values in the static UI.
- Focused regression: `python3 scripts/ui_static_check.py` guards the UI trace helper marker.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed only by adding trace attributes and title metadata to existing counters; API schema, storage schema, and paper-only/no-broker boundaries are unchanged.

## Risks

- Browser-level assertion was not added for T-530 because this change only exposes existing API data as static UI trace attributes and the static contract now guards the helper marker. A future browser fixture with richer industry relationship data can assert exact `data-network-total` and `data-network-part` values.

## Dependencies

- T-529 API-level `industry_network_summary`.
- Existing company intelligence UI route and static contract.

## Blockers

- None.

## Handoff Checklist

- [x] Read relevant task context.
- [x] Keep changes scoped to UI trace, static contract, and docs.
- [x] Avoid `app/services.py` changes.
- [x] Run validation commands.
- [x] Update evidence section with actual results.

## Evidence

- `python3 -m py_compile scripts/ui_static_check.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=19`, `node_check=passed`.
- `git diff --check`: passed.
- `python3 scripts/check_handoffs.py`: first run failed because this handoff mentioned `app/services.py` without a growth-freeze review; review section was added.
- `python3 scripts/check_handoffs.py`: passed after the growth-freeze review was added; checked 104 markdown files.

## Next Recommended Action

Continue the relationship-logic completion pass by adding browser-level assertions for industry network trace values once a fixture with non-empty peer/upstream/downstream data is available.
