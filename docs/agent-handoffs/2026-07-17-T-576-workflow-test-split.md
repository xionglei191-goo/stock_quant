# Handoff: T-576 Workflow test split

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-07-17
- Last agent: Codex (T-576 delegated agent)
- Branch/worktree: current shared worktree

## Objective

Mechanically move a coherent workflow/orchestration test slice out of the
monolithic `tests/test_system.py` without changing production behavior, test
method names, setup order, or assertions.

## Scope

- In scope: four contiguous orchestration tests covering workflow lineage,
  readiness, the built-in executor, and queue-isolated backfill.
- Out of scope: production code, API/storage/UI contracts, the golden API test,
  value-case work, canonical documentation, and roadmap edits.

## Background

`tests/test_system.py` held 319 test methods and exceeded 1.1 MB. The workflow
planning behavior extracted under T-570 still had its orchestration regression
slice embedded in that single file.

## Problem Statement

The oversized test module increases ownership ambiguity and makes focused
workflow regression slower to locate and review.

## Expected Deliverables

- Add `tests/test_workflow_service.py` using `SystemServiceTestBase`.
- Move the four contiguous workflow/orchestration methods without assertion
  changes.
- Preserve aggregate test count and keep the golden API regression covered.

## Current Findings

- The four moved method ASTs are identical to their versions in `HEAD`.
- `tests/test_system.py`: 22,783 lines / 1,134,157 bytes before; 21,929 lines /
  1,091,090 bytes after.
- `tests/test_workflow_service.py`: 860 lines / 43,204 bytes after formatting.
- Aggregate touched test sources: 22,789 lines / 1,134,294 bytes.
- Test method count is unchanged: 319 total, split as 315 plus 4.
- Full discovery currently finds 344 tests because another agent added eight
  value-case tests while this task was running.

## Proposed Work Plan

Completed in this turn:

1. Identify a contiguous workflow/orchestration slice.
2. Move the four methods into a focused module with shared setup.
3. Verify AST equivalence, focused behavior, compilation, golden API behavior,
   and full discovery.

## Validation Plan

Run the focused module, golden API baseline, full unittest discovery,
`py_compile`, handoff validation, and whitespace checks.

## Risks

- Full discovery has three unrelated task-status audit failures while concurrent
  PM work leaves three roadmap entries in `DOING`; no moved workflow test fails.
- The shared worktree contains concurrent changes outside T-576. They were not
  modified or reverted by this task.

## Dependencies

- `tests/support.py` provides the unchanged `SystemServiceTestBase` fixture.
- T-570 defines the workflow planning domain boundary exercised by this slice.

## Blockers

- None for the mechanical split. Parent PM reconciliation is required before a
  completely green full suite because roadmap edits are still in progress.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly recorded with failures
- [x] Docs/contracts updated if applicable (no contract change)
- [x] `tasks/todo.md` intentionally left to the parent PM agent

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_workflow_service
python3 -m unittest tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: moved workflow module, 4 tests; golden API baseline, 1 test;
  compilation; AST equivalence for all four moved methods.
- Failed: full discovery ran 344 tests with 3 failures in project completion and
  production task closure audits. Each failure observes concurrent
  `tasks/todo.md` state (`doing_task_count` is 3); they are outside T-576.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.
  and the parent wave owns the final combined validation.

Artifacts:

- None. This task creates test source and a handoff only.

## Next Recommended Action

1. Parent PM agent reviews the moved slice and reconciles `tasks/todo.md` status.
2. Rerun full discovery after concurrent roadmap tasks reach their intended
   terminal status.
3. Keep future workflow tests in `tests/test_workflow_service.py` when they use
   the same service-level fixture and domain boundary.
