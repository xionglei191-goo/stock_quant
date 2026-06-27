# Handoff: T-402-T-421 Production Evidence Execution Plan

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Data and Evidence, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421

## Objective

Turn the remaining external-evidence-blocked production tasks into a PM execution plan that routes owners from evidence collection through artifact inventory, strict release gate, and final task status changes.

## Scope

- In scope: execution-plan generator, generated PM execution plan document, focused regression test, docs index, todo notes.
- Out of scope: generating external evidence, accepting local-only artifacts, changing blocked tasks to DONE, broker integration, automatic trading.

## Background

The code layer is complete for the remaining productionization tasks, but non-local release still requires real external staging/production artifact URIs. Previous work produced owner packets and a status board; PM still needed one execution plan that connects those packets to inventory, release gate, and final status update commands.

## Problem Statement

The remaining 17 blocked evidence tasks were assignable, but the final execution sequence was spread across owner packet docs, status board docs, and release scripts. PM needed a single coordination artifact that makes the route from owner work to release gate explicit without weakening the external evidence requirement.

## Expected Deliverables

- `scripts/production_evidence_execution_plan.py` generates JSON and Markdown execution plans.
- `docs/production-evidence-execution-plan.md` lists 6 owners, 17 tasks, 81 artifact fields, task packet paths, and 4 execution phases.
- `tests/test_system.py` validates owner routing, release-gate commands, and the non-release-evidence boundary.
- `docs/README.md` and `tasks/todo.md` point future agents to the execution plan.

## Current Findings

- `production_task_closure_audit.py` reports `needs_code_work_count=0`.
- The remaining 17 audit entries are all `blocked_external_evidence`.
- `docs/production-evidence-status-board.md` shows 6 owners, 17 tasks, 81 placeholder URIs, and 0 tasks ready for inventory.
- The execution plan is a coordination artifact only; it does not satisfy any release gate by itself.

## Proposed Work Plan

1. Add execution-plan generator that reuses the evidence plan, owner packets, and status board.
2. Generate Markdown/JSON execution outputs.
3. Add focused test coverage.
4. Link the execution plan from docs and todo.
5. Run validation and push.

## Validation Plan

- `python3 scripts/production_evidence_execution_plan.py artifacts/production-evidence-collection-plan-current.json --output-json artifacts/production-evidence-execution-plan-current.json --output-md docs/production-evidence-execution-plan.md`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_production_evidence_execution_plan_routes_owner_work_to_release_gate tests.test_system.SystemServiceTests.test_production_evidence_owner_packets_group_external_evidence_by_owner tests.test_system.SystemServiceTests.test_production_evidence_status_board_tracks_uri_readiness_by_owner`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/security_check.py .`
- `git diff --check`

## Risks

- The execution plan may be mistaken for release evidence; the generated document and script explicitly state it is not.
- Real owner assignment still needs named humans or external systems outside the repo.
- Strict release gate still cannot pass until all URI placeholders are replaced and inventory metadata is real.

## Dependencies

- `scripts/production_evidence_owner_packets.py`
- `scripts/production_evidence_status_board.py`
- `scripts/production_evidence_plan_check.py`
- `scripts/production_release_gate.py`
- `scripts/production_task_status_finalize.py`

## Blockers

- Real non-local staging/production artifacts are still external blockers.
- 81 artifact URI placeholders remain until evidence owners upload real artifacts and update the collection plan.

## Handoff Checklist

- [x] Execution-plan generator added.
- [x] PM Markdown execution plan generated.
- [x] Focused regression added.
- [x] Docs index updated.
- [x] Todo notes updated without changing external-evidence-blocked tasks to DONE.

## Evidence

- `docs/production-evidence-execution-plan.md`: PM coordination artifact, local repo document, not production release evidence.
- `scripts/production_evidence_execution_plan.py`: execution-plan generator and validator.
- `tests/test_system.py`: focused execution-plan regression.
- `artifacts/production-evidence-execution-plan-current.json`: local-only generated JSON from the current plan; not committed as release evidence.

## Next Recommended Action

Send the execution plan and task packets to the matching external evidence owners. Once real URIs are available, fill `artifacts/production-evidence-collection-plan.json`, build artifact inventory, run `scripts/production_release_gate.py`, then use `scripts/production_task_status_finalize.py`.
