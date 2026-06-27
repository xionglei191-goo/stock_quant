# Handoff: T-402 Production Evidence Status Board

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Data and Evidence, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421

## Objective

Add a PM tracking board that shows external evidence URI readiness by owner, task, and artifact field so remaining production blockers can be managed without confusing collection instructions with release evidence.

## Scope

- In scope: status board generator, generated Markdown board, tests, docs index, todo notes, and handoff.
- Out of scope: uploading real external artifacts, approving release, changing BLOCKED tasks to DONE, broker integration, and automatic trading.

## Background

The owner and task packets make the remaining external evidence work assignable. PM still needs a single status view showing whether URIs are placeholders, filled, invalid, or ready for inventory.

## Problem Statement

Without a status board, the next agent has to inspect a large evidence plan manually to know which owner is waiting on which artifact URI and whether the plan can enter artifact inventory and release gate.

## Expected Deliverables

- `scripts/production_evidence_status_board.py`.
- `docs/production-evidence-status-board.md`.
- Focused regression for placeholder and filled URI states.
- Docs and todo notes updated.

## Current Findings

- Current plan has 6 owner groups, 17 evidence tasks, and 80 artifact fields.
- All 80 current URIs are placeholders.
- Board status is `waiting_for_external_evidence`.
- A filled production/staging prefix moves the board to `ready_for_release_gate`, but release still requires artifact inventory and strict gate.

## Proposed Work Plan

1. Add status board generator and validator.
2. Generate Markdown board from the current plan.
3. Add tests for current placeholder state and filled URI state.
4. Update docs and todo.
5. Run validation and push.

## Validation Plan

- `python3 scripts/production_evidence_status_board.py artifacts/production-evidence-collection-plan-current.json --output-json artifacts/production-evidence-status-board-current.json --output-md docs/production-evidence-status-board.md`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_production_evidence_status_board_tracks_uri_readiness_by_owner tests.test_system.SystemServiceTests.test_production_evidence_owner_packets_group_external_evidence_by_owner`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `python3 scripts/security_check.py .`
- `python3 scripts/ui_static_check.py`
- `git diff --check`

## Risks

- The board is not release evidence.
- A `ready_for_release_gate` board only means URIs are filled; it does not replace artifact inventory, readiness package, or release gate.
- Current task statuses must remain BLOCKED until real external evidence is present and strict release gate passes.

## Dependencies

- `scripts/production_task_closure_audit.py`
- `scripts/production_evidence_plan_check.py`
- `scripts/production_evidence_plan_fill.py`
- `scripts/production_artifact_inventory_check.py`
- `scripts/production_release_gate.py`

## Blockers

- Real external staging/production artifacts are still required before production tasks can be marked DONE.

## Handoff Checklist

- [x] Status board generator added.
- [x] Markdown status board generated.
- [x] Placeholder and filled URI states covered by tests.
- [x] Docs index updated.
- [x] Todo notes updated without changing BLOCKED tasks to DONE.

## Evidence

- `docs/production-evidence-status-board.md`: PM status board.
- `scripts/production_evidence_status_board.py`: status board generator and validator.
- `tests/test_system.py`: focused status board regression.

## Next Recommended Action

When real external artifact URIs are available, fill the production evidence plan, regenerate the status board, build artifact inventory, and run the strict release gate. Only then should corresponding BLOCKED tasks move to DONE.
