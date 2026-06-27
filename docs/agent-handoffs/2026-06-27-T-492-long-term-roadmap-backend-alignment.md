# Handoff: T-492 Long-Term Roadmap and Backend Alignment

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Product and UI, Data and Evidence, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-492

## Objective

Record the T-492 through T-503 long-term completion queue in the repository roadmap and explicitly connect the product completion work with backend modularization.

## Scope

- In scope: `tasks/todo.md`, `docs/README.md`, T-490/T-491 handoff status cleanup, and this handoff.
- Out of scope: implementing T-493 through T-503, changing backend APIs, changing schemas, committing, or pushing to GitHub.

## Background

After T-480 through T-491, the visible company intelligence workbench became much more usable, but the next phase needs to address data health, true browser acceptance, conclusion realization, event/relationship trust, front-end maintainability, and backend service modularity together. The backend inspection showed that `SystemService` remains a large facade and should be split gradually rather than rewritten.

## Problem Statement

The previous long-term plan covered product improvements, while the backend review separately identified modularization needs. The roadmap needed one unified queue so future agents do not treat product work and backend refactoring as disconnected efforts.

## Expected Deliverables

- Add T-492 through T-503 to `tasks/todo.md` after T-491 and before the operations appendix.
- Update `docs/README.md` so the document index reflects T-431 through T-491 completion and T-492 through T-503 long-term roadmap.
- Mark the final T-490/T-491 handoff validation items as completed based on the closeout checks already run.
- Create this handoff for the roadmap update.

## Current Findings

- `tasks/todo.md` had T-490/T-491 done, then moved directly into the operations appendix.
- `docs/README.md` still described the roadmap as T-431 through T-479.
- T-490/T-491 handoffs still showed final validation checklist items as pending despite the T-491 closeout pass recording `check_handoffs` and `git diff --check` success.
- The worktree already contains broader T-480 through T-491 changes; this task only adds roadmap and documentation alignment.

## Proposed Work Plan

1. Insert the T-492 through T-503 long-term completion and backend-alignment queue into `tasks/todo.md`.
2. Update the docs index task range and summary.
3. Update T-490/T-491 handoff checklist status.
4. Add this T-492 handoff.
5. Run static/document checks.

## Validation Plan

- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`

## Risks

- T-492 includes GitHub push in its eventual acceptance criteria, but this handoff only records the roadmap update. The actual commit and push remain the next execution step.
- The inserted tasks are intentionally high-level execution queue items. Each future task still needs its own focused implementation handoff and tests.
- The worktree contains pre-existing modified and untracked files from T-480 through T-491; they were not reverted.

## Dependencies

- Existing roadmap conventions in `tasks/todo.md`.
- Existing AGENTS owner group taxonomy.
- Existing `SystemService` modularization ADR.

## Blockers

- None for the roadmap update.

## Handoff Checklist

- [x] Roadmap updated.
- [x] Docs index updated.
- [x] T-490/T-491 handoff status aligned.
- [x] Handoff created.
- [x] Validation commands run after this handoff is added.

## Evidence

- `tasks/todo.md` now contains T-492 through T-503 immediately after T-491.
- `docs/README.md` now describes T-431 through T-491 and T-492 through T-503.
- T-490/T-491 handoffs no longer show final closeout checks as pending.
- Validation passed: `python3 scripts/check_handoffs.py`, `git diff --check`, `python3 scripts/ui_static_check.py`, and `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.

## Next Recommended Action

Run the validation plan, then execute T-492's actual worktree closure step: final grouping, commit, and push when the user asks for release closure.
