# Handoff: T-492 PM Execution Coordination

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Product and UI, Data and Evidence, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-492

## Objective

Coordinate the T-492 through T-503 queue as a PM-led multi-group execution plan. Close the T-492 release gate first, then sequence the remaining work so product improvements and backend refactoring move together without breaking the current personal company intelligence system.

## Scope

- In scope: T-492 worktree closure planning, grouped agent findings, validation, handoff, roadmap status update, and the small daily pipeline compatibility fix needed to restore tests.
- Out of scope: implementing T-493 through T-503, changing API schemas, changing database schemas, connecting real brokers, automatic order execution, or marking external-evidence `BLOCKED` tasks as done.

## Background

T-492 through T-503 were added as the long-term completion route after T-491 UI denoise. The user then asked to act as PM and call agent groups to complete all `todo.md` tasks. The current queue contains feasible local tasks T-492 through T-503 plus older `BLOCKED` non-local/organization-level evidence gaps.

## Problem Statement

The project should not continue adding large UI/backend changes on top of an uncommitted T-480 through T-491 worktree. It also should not treat external production evidence gaps as locally completable. A PM coordination pass was needed to separate the immediate T-492 release closure from staged execution of T-493 through T-503.

## Expected Deliverables

- Call grouped agents for Data/Evidence, Product/UI, Platform/Quality, Research/Workflow, and Governance/Security planning.
- Record a staged execution sequence for T-493 through T-503.
- Fix any immediate validation blocker needed for T-492 release closure.
- Run validation checks.
- Mark T-492 done in `tasks/todo.md` after validation and before commit/push.

## Current Findings

- Data and Evidence recommends T-502 first, choosing run-summary aggregation/read model before implementing T-493 source health or T-497 trust enhancements.
- Product and UI recommends T-494 first as a mode split without module extraction, preserving tab IDs and selector contracts; T-498 frontend modularization should follow only after compatibility is proven.
- Platform and Quality recommends T-501 golden API baselines before route grouping or `SystemService` extraction.
- Research and AI Workflows recommends T-496 with pure scoring/realization modules behind current service/API flows, preserving paper-only behavior.
- Governance/Security recommends T-499 as a non-local production readiness preparation package, not a local readiness reclassification.
- The first full unit run failed because `scripts/daily_data_update_pipeline.py` assumed new personal-intelligence args existed on older test-built `Namespace` objects. This was fixed with `getattr` defaults.

## Proposed Work Plan

1. Complete T-492 validation, commit, and push.
2. Start T-502 ADR and T-501 golden API behavior baselines before implementation-heavy tasks.
3. Implement T-493 source health center on top of the run-summary decision.
4. Implement T-494 personal workspace versus backend maintenance split, preserving DOM contracts.
5. Implement T-496 realization/scoring, T-497 trust/dedupe, T-498 modularization, T-500 service extraction, T-503 growth rules, and T-499 production readiness package as separate tasks with handoffs.

## Validation Plan

- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/security_check.py .`
- Clean-env `python3 -m unittest discover -s tests`

## Risks

- T-493 through T-500 are large and should each get focused handoffs and tests. Marking them done from this coordination pass would be inaccurate.
- Existing UI acceptance scripts use direct DOM selectors; hiding or renaming nodes during T-494/T-498 can break tests even if the visible UI works.
- Golden payloads must normalize timestamps and trace IDs but still catch business payload drift.
- The daily pipeline now invokes personal intelligence refresh unless skipped; defaults are backwards-compatible, but runtime operators should decide whether daily refresh should be default-on or default-skipped in production-like schedules.

## Dependencies

- Existing T-492 through T-503 roadmap entries in `tasks/todo.md`.
- Existing T-490/T-491 UI denoise work and handoffs.
- Existing `SystemService` facade and API router behavior.
- Existing local-only/paper-only/no-broker/no-auto-trading project boundaries.

## Blockers

- No blocker remains for T-492 local closure.
- Historical operations appendix tasks remain blocked on external staging/production artifacts or large-sample evidence and must not be closed from local-only validation.

## Handoff Checklist

- [x] Grouped agent planning collected.
- [x] Immediate validation blocker fixed.
- [x] Validation commands run.
- [x] `tasks/todo.md` updated for T-492.
- [x] Next task ordering recorded.

## Evidence

- `scripts/daily_data_update_pipeline.py`: backwards-compatible defaults for personal intelligence refresh arguments.
- Validation passed after the fix:
  - `python3 scripts/ui_static_check.py`
  - `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
  - `python3 scripts/security_check.py .`
  - Clean-env `python3 -m unittest discover -s tests` ran 259 tests and passed.
- `tasks/todo.md`: T-492 marked `DONE`; T-493 through T-503 remain TODO.

## Next Recommended Action

Commit and push the T-480 through T-492 worktree. Then start T-502 ADR and T-501 golden API baselines before implementing T-493 or backend route/service extraction.
