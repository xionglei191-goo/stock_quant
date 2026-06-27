# Handoff: T-402-T-421 Production Evidence Owner Packets

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Data and Evidence, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421

## Objective

Convert the remaining external-evidence-blocked production tasks into owner-specific evidence collection packets so PM can route the work by group instead of leaving a flat blocked list. After owner-agent review, refine the packets so each task includes collection procedure, minimum artifact contents, reviewer routing, and API-aligned artifact fields.

## Scope

- In scope: owner packet generator, generated owner-readable document, tests, doc index, task notes, and handoff.
- Out of scope: fabricating evidence, changing blocked task status to DONE, real staging/production artifact upload, broker integration, and automatic trading.

## Background

The code layer is complete for the remaining productionization tasks, but non-local release still requires real external artifacts. T-499 created the readiness package; this follow-up makes the evidence collection plan directly assignable to owner groups.

## Problem Statement

`production_task_closure_audit.py --output-plan` creates a machine-readable plan, but PM still needs a human-readable work packet grouped by owner role, with each task's endpoint, blockers, artifact fields, and URI templates.

## Expected Deliverables

- `scripts/production_evidence_owner_packets.py` generates JSON and Markdown owner packets.
- `docs/production-evidence-owner-packets.md` lists 6 owner groups, 17 external evidence tasks, and 81 required artifact fields.
- `docs/production-evidence-task-packets/` contains one agent/issue packet per external evidence task.
- Each task packet states collection procedure, minimum artifact contents, reviewer routing, and source/boundary rules.
- Tests validate owner grouping and output files.
- Docs and todo notes point future agents to the packet.

## Current Findings

- `production_task_closure_audit.py` reports `needs_code_work_count=0`.
- The remaining 17 audit entries are all `blocked_external_evidence`.
- The `tasks/todo.md` visible task list has 16 `BLOCKED` parent tasks; the audit expands `T-406A` as an additional evidence subtask.
- Owner-agent review found that T-406A's prior `research_task_queue_uri` was not a direct readiness endpoint gate; the plan now requires `company_position_review_uri` and `chain_taxonomy_review_uri`.
- T-414 now uses `citation_policy_uri`, matching the citation-boundary readiness API input alias and test payload.
- Generated task packets now map role labels to AGENTS.md owner groups instead of showing every task as PM owned.

## Proposed Work Plan

1. Add owner packet generator.
2. Generate Markdown packet from the current evidence collection plan.
3. Add collection-procedure and minimum-content requirements for each blocked evidence task.
4. Add focused test coverage.
5. Link the packet from docs and todo.
6. Run validation and push.

## Validation Plan

- `python3 scripts/production_evidence_owner_packets.py artifacts/production-evidence-collection-plan-current.json --output-json artifacts/production-evidence-owner-packets-current.json --output-md docs/production-evidence-owner-packets.md --output-dir docs/production-evidence-task-packets`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_production_evidence_owner_packets_group_external_evidence_by_owner tests.test_system.SystemServiceTests.test_production_task_closure_audit_separates_external_evidence_blockers`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `python3 scripts/security_check.py .`
- `git diff --check`

## Risks

- The packet is not release evidence and must not be used to mark blocked tasks DONE.
- The generated Markdown includes template URIs with placeholders; real release still requires filled external URIs, artifact inventory, readiness evidence package, and release gate.
- Owner names are role labels mapped to owner groups from AGENTS.md, not confirmed human assignees.

## Dependencies

- `scripts/production_task_closure_audit.py`
- `scripts/production_evidence_plan_check.py`
- `docs/non-local-production-readiness-package.md`
- `docs/production-runbook.md`

## Blockers

- Real non-local staging/production artifacts are still external blockers.

## Handoff Checklist

- [x] Owner packet generator added.
- [x] Owner-readable Markdown packet generated.
- [x] One task packet per external evidence task generated.
- [x] Test coverage added.
- [x] Docs index updated.
- [x] Todo notes updated without changing external-evidence-blocked tasks to DONE.

## Evidence

- `docs/production-evidence-owner-packets.md`: owner-readable collection instructions.
- `docs/production-evidence-task-packets/`: task-level agent/issue packets.
- `scripts/production_evidence_owner_packets.py`: packet generator and validator.
- `artifacts/production-evidence-collection-plan.example.json`: versioned placeholder plan aligned with readiness endpoint artifact fields.
- `tests/test_system.py`: focused owner-packet regression.

## Next Recommended Action

Send each owner packet to the matching group. Once real external artifact URIs exist, fill `artifacts/production-evidence-collection-plan.json`, validate with `--require-filled-uris`, build artifact inventory, and run the strict release gate.
