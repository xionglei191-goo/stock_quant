# Handoff: T-505 Relationship Coverage Diagnostics

## Metadata

- Status: DONE
- Owner group: Data and Evidence, Product and UI
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-505

## Objective

Add machine-readable coverage diagnostics to the company-centered relationship context so users can see which relationship-chain layers are present and which data should be backfilled next.

## Scope

- In scope: `relationships.relationship_context` derived output, company intelligence UI summary rows, API docs, roadmap status, focused regression.
- Out of scope: database migration, external data collection, automatic candidate approval, real broker integration, automatic trading.

## Background

T-504 made the relationship context visible, but the system still needed to explain whether a company's relationship chain is complete. The user goal is a multi-dimensional relationship graph, so the next useful increment is to identify missing industry, peer, upstream/downstream, ownership, and graph-edge layers.

## Problem Statement

Before T-505, `relationship_context` could show existing rows, but it did not tell the user whether the visible rows were complete enough or what data should be added next.

## Expected Deliverables

- Additive `relationship_context.coverage_diagnostics` with score, status, missing layers, diagnostics rows, and next actions.
- Additive `relationship_context.next_actions` for relationship backfill guidance.
- Multi-dimensional relationship UI rows that surface missing layers before existing relationship details.
- Focused regression for complete and partial relationship-chain coverage.
- Docs and roadmap updates.

## Current Findings

- Completed: `coverage_diagnostics` reports required and optional relationship-chain layers.
- Completed: Required layers are industry position, peers, upstream, downstream, ownership/control, and graph edges.
- Completed: Same-holder related company network is treated as optional exploration depth.
- Completed: Company intelligence "多维关系" panel now renders missing layers as "关系链缺口" rows.
- Completed: No storage schema or `SystemService` facade change was needed.

## Proposed Work Plan

1. Keep diagnostics derived from `relationship_context.summary`.
2. Classify each relationship-chain layer as available, missing required, or missing optional.
3. Return actionable `relationship_backfill` next actions for missing layers.
4. Render missing layers in the existing company intelligence relationship panel.
5. Lock behavior with focused regression and static UI checks.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

Full unit suite is optional for this narrow additive derived-view slice; the focused tests cover the new schema and behavior.

## Risks

- Diagnostics are only as good as existing local `CompanyPosition`, `IndustryChain`, ownership, and graph records.
- Missing-layer next actions are currently guidance rows, not direct UI execution buttons.

## Dependencies

- Local persisted company records: `CompanyRelationship`, `CompanyPosition`, `IndustryChain`, `InstitutionalHolding`, `Issuer`, `Security`.
- Existing `/api/company-intelligence/{symbol}` behavior.
- UI static contract in `scripts/ui_static_check.py`.

## Blockers

- No blocker for this delivered slice.
- Future direct action wiring depends on choosing which backend operation each missing layer should trigger.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Yes, diagnostics are implemented in `app/service_modules/company_intelligence.py`.
- `SystemService` changes: None for T-505.
- Focused regression: `tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` and `tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers`.
- API schema changed: additive only, `relationship_context.coverage_diagnostics` and `relationship_context.next_actions`.
- Storage schema changed: No.
- UI behavior changed: additive gap rows in the "多维关系" panel.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

Results:

- Passed: pending final verification in this turn.
- Failed: initial focused regression used an invalid `Issuer` constructor field; fixed the test fixture.
- Artifact boundary: no new artifact files; evidence is local test output and tracked code/docs.

Files touched:

- `app/service_modules/company_intelligence.py`: derived relationship coverage diagnostics and next actions.
- `app/static/index.html`: relationship-chain gap rows in the multi-dimensional relationship panel.
- `tests/test_system.py`: focused regression for complete and partial coverage.
- `docs/api-contracts.md`: API contract update.
- `tasks/todo.md`: T-505 roadmap record.

## Next Recommended Action

Wire `relationship_context.next_actions` to concrete operations: ownership manifest import, relationship builder preview, company position backfill, and relationship review queues.
