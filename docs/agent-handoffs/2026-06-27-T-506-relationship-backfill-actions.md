# Handoff: T-506 Relationship Backfill Actions

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-506

## Objective

Turn relationship-chain gap diagnostics into clickable UI actions so a user can move from "what is missing" to an existing backfill, import, graph, or review path.

## Scope

- In scope: company intelligence UI action wiring, static UI contract, roadmap status, handoff.
- Out of scope: new backend API, database migration, automatic external ownership ingestion, automatic relationship approval, real broker integration, automatic trading.

## Background

T-505 added `relationship_context.coverage_diagnostics`, but those diagnostics were still mostly explanatory. To keep the relationship graph work moving toward a complete workflow, the next slice wires missing layers to existing UI operations.

## Problem Statement

Before T-506, users could see that peer, upstream, downstream, ownership, or graph layers were missing, but the relationship panel did not provide an immediate action for backfilling or reviewing that layer.

## Expected Deliverables

- Relationship gap rows include a visible action button.
- Gap layer types map to existing operations: batch build preview, ownership/material import guidance, graph opening, or relationship review queue.
- Static UI contract protects the new function and event marker.
- Roadmap and handoff record the UI-only action wiring.

## Current Findings

- Completed: Added `runRelationshipBackfillAction` in `app/static/index.html`.
- Completed: Missing industry, peer, upstream, and downstream layers trigger `buildCompanyDatabaseBatch(false)`.
- Completed: Missing ownership and shareholder-network layers open the maintenance area and guide the user to local material/ownership manifest import.
- Completed: Missing graph edges open the relationship graph centered on the current company.
- Completed: Static UI checks now require `runRelationshipBackfillAction` and `data-action="run-relationship-backfill-action"`.

## Proposed Work Plan

1. Reuse T-505 diagnostics without changing backend schema.
2. Add per-layer UI action mapping in `renderCompanyRelationshipContext`.
3. Route gap buttons through a single delegated click action.
4. Reuse existing UI operations instead of adding new backend routes.
5. Lock the behavior with static UI contract and focused UI regression.

## Validation Plan

Run:

```bash
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Browser interaction acceptance is deferred because this slice only wires already-existing UI operations through static event delegation.

## Risks

- Ownership import still lacks a native browser form for ownership tables; current UI action guides the user to the maintenance area and existing material/manifest workflows.
- Batch build preview is a broad backfill operation, not a dedicated industry-position editor.

## Dependencies

- T-505 `relationship_context.coverage_diagnostics`.
- Existing UI helpers: `buildCompanyDatabaseBatch`, `openRelationshipGraphContext`, `renderCompanyRelationshipReview`, `openTab`.
- `scripts/ui_static_check.py` static contract.

## Blockers

- No blocker for this delivered slice.
- A first-class ownership table UI requires a later backend/UI task.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Not needed; this is UI action wiring over existing APIs.
- `SystemService` changes: None for T-506.
- Focused regression: `tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture`.
- API schema changed: No.
- Storage schema changed: No.
- UI behavior changed: relationship gap rows now have clickable backfill actions.
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
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Results:

- Passed: pending final verification in this turn.
- Failed: none known.
- Artifact boundary: no new artifact files; evidence is local test output and tracked code/docs.

Files touched:

- `app/static/index.html`: relationship gap action buttons and delegated action handler.
- `scripts/ui_static_check.py`: required function and interaction marker.
- `tasks/todo.md`: T-506 roadmap record.

## Next Recommended Action

Add a first-class browser workflow for ownership table import and manifest template generation so `ownership_import_guidance` can run a preview directly instead of guiding users to the maintenance area.
