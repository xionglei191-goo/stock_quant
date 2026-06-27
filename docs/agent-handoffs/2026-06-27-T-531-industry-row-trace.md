# Handoff: T-531 Industry Row Trace

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: `/home/xionglei/Project/sotck_quant`
- Related task: T-531

## Objective

Make each company intelligence industry-chain relationship row traceable to its chain, node, direction, and graph filter attributes.

## Scope

- `app/static/index.html`: add structured row-level industry trace attributes for industry position, peer, upstream, and downstream rows.
- `scripts/ui_static_check.py`: guard the new helper and direction attribute marker.
- `docs/api-contracts.md`: document the row-level UI trace contract.
- `tasks/todo.md`: record T-531 status and validation.

## Background

T-529 and T-530 added aggregate industry-network summary fields and top-counter trace attributes. The relationship table rows still relied mostly on readable labels and advanced trace JSON, which made automated checks and manual DOM inspection weaker than the top summary counters.

## Problem Statement

The user wants the relationship graph and multi-dimensional company logic to be complete and dynamically explorable. For industry-chain rows, users and tests need to know not only that a peer/upstream/downstream company exists, but also which chain and node produced the row and which direction it represents.

## Expected Deliverables

- Industry position, peer, upstream, and downstream rows include `data-industry-relationship` and `data-industry-direction`.
- Rows preserve graph filters through `data-chain-id` and `data-chain-node-id`.
- Rows add trace metadata for `data-chain-node-ids`, `data-chain-node-label`, and `data-position-id` when available.
- Static contract and API contract reflect the row-level trace surface.

## Current Findings

- `renderInsightTable` applies `item.actionAttrs` to the `<tr>`, so row-level trace attributes can be added without changing the shared table renderer.
- `graphActionAttrs` already centralizes graph-click filters; T-531 wraps it instead of duplicating graph filter logic.
- Backend relationship context already includes `chain_id`, `node_ids`, `node_name`, and `position_id` where available.

## Proposed Work Plan

1. Add `industryRelationshipTraceAttrs` beside `graphActionAttrs`.
2. Use it for industry position, peer, upstream, and downstream rows.
3. Add static contract markers and API contract documentation.
4. Update roadmap and this handoff.
5. Run focused validation.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t531 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module usage: Not applicable; T-531 only adds UI row trace attributes using existing `relationship_context` payload fields.
- Focused regression: `python3 scripts/ui_static_check.py` guards `industryRelationshipTraceAttrs` and `data-industry-direction`; `company_industry_relationship_rows_have_trace_attrs` in `scripts/ui_interaction_acceptance.py` verifies the row attributes in a browser DOM.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI behavior changed by adding DOM trace attributes to existing rows; API schema, storage schema, and paper-only/no-broker boundaries are unchanged.

## Risks

- Browser-level assertions use a self-contained UI fixture rather than live local database rows. This keeps the check deterministic, but it does not prove every production data row has all optional fields populated.

## Dependencies

- Existing `relationship_context.industry` payload.
- Existing `renderInsightTable` row attribute behavior.
- Existing `/api/graph/query` filters for `chain_id` and `chain_node_id`.

## Blockers

- None.

## Handoff Checklist

- [x] Read current relationship-context and UI rendering code.
- [x] Keep changes scoped to UI trace, static contract, and docs.
- [x] Avoid backend logic and `app/services.py` edits.
- [x] Run validation commands.
- [x] Update evidence section with actual results.

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`: passed.
- `python3 scripts/ui_static_check.py`: passed with `required_ids=379`, `required_functions=162`, `interaction_markers=21`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t531 --timeout 60`: passed on clean local SQLite/object-store service; 37/37 checks passed, including `company_industry_relationship_rows_have_trace_attrs`.
- `python3 scripts/check_handoffs.py`: passed; checked 105 markdown files.
- `git diff --check`: passed.

## Next Recommended Action

Continue the relationship-logic completion pass by moving to the next uncovered relationship dimension.
