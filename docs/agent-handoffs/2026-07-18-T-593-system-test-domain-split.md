# Handoff: T-593 Graph quality test domain split

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex (T-593 delegated agent)
- Branch/worktree: current shared worktree

## Objective

Mechanically move the full-knowledge-graph, graph quality center, and graph
enrichment runner regression slice out of `tests/test_system.py` into a focused
module without changing production behavior, test names, method bodies, or test
discovery count.

## Scope

- In scope: 39 graph-domain test methods and their private
  `_add_graph_enrichment_fixture` helper, focused and aggregate verification,
  and this handoff.
- Out of scope: production code, shared fixture behavior, roadmap and risk
  register status, UI, dynamic allocation, and API/storage contracts.
- Risk level: low; the change is a mechanical test-source move, but it occurs in
  a heavily modified shared worktree.

## Background

MR-2 identifies `tests/test_system.py` as a high maintenance and parallel-edit
risk. T-576 moved the first workflow slice, but the file still held 315 tests
and exceeded 1.09 MB at T-593 intake.

## Problem Statement

The graph quality and enrichment regression surface remained embedded at the
tail of the central system test class, increasing ownership ambiguity and
conflict risk for graph-domain changes.

## Expected Deliverables

- A focused graph test module using the established shared fixture.
- Mechanical proof that method names, bodies, assertions, and aggregate counts
  did not drift.
- Focused, compilation, and full-discovery evidence with existing failures
  separated from task regressions.

## Current Findings

- Completed: moved the coherent graph regression slice to
  `tests/test_graph_quality.py` using the existing `SystemServiceTestBase`.
- Completed: proved AST equivalence for all 39 test methods and the one private
  fixture helper; no moved test name remains duplicated in `test_system.py`.
- Completed: preserved aggregate discovery at 423 tests and preserved the exact
  pre-existing full-suite failure set.
- In progress: none.
- Not started: further domain splits from the remaining monolith.
- Blocked: none for T-593.

## Proposed Work Plan

Completed in this turn:

1. Freeze current source and test-discovery baselines.
2. Move the contiguous graph slice with only required module imports.
3. Compare normalized ASTs and run focused plus aggregate verification.
4. Record exact counts and shared-worktree risks for PM integration.

## Validation Plan

Run the focused module, compile all Python entry points, compare moved ASTs,
rerun full discovery, compare its before/after failure set, validate handoffs,
and check whitespace.

## Files Touched

- `tests/test_system.py`: removed 39 graph-domain tests and their private helper;
  21,929 lines / 1,091,090 bytes before, 20,613 lines / 1,027,771 bytes after.
- `tests/test_graph_quality.py`: added the mechanically moved graph slice with
  only its required module imports; 1,334 lines / 63,954 bytes after.
- `docs/agent-handoffs/2026-07-18-T-593-system-test-domain-split.md`: records
  scope, equivalence evidence, checks, and follow-up ownership.

Aggregate touched test source changed from 21,929 lines / 1,091,090 bytes to
21,947 lines / 1,091,725 bytes. Test method counts are unchanged: the source
module changed from 315 to 276 methods and the new module owns the other 39.

## Evidence

```bash
python3 -m unittest discover -s tests
python3 -m unittest tests.test_graph_quality
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py tests/dynamic_allocation/*.py scripts/*.py
python3 <AST equivalence script comparing /tmp/t593-test-system-before.py with the two post-split modules>
git diff --check -- tests/test_system.py tests/test_graph_quality.py
python3 scripts/check_handoffs.py
```

Result:

- Passed: focused graph module, 39 tests in 2.108 seconds.
- Passed: compilation across application, service modules, tests, dynamic
  allocation tests, and scripts.
- Passed: 39 test ASTs plus one helper AST are byte-for-byte equivalent after
  normalization with `ast.dump(..., include_attributes=False)`.
- Passed: aggregate method count for this slice remains 315 (276 plus 39), with
  zero duplicate moved names.
- Passed: full discovery still runs exactly 423 tests.
- Failed, pre-existing and unchanged: full discovery reports 6 failures and 14
  errors both before and after the split. The exact ordered failure/error set is
  identical. Fourteen errors and three failures are in concurrent dynamic
  allocation work; three failures are roadmap/completion audits observing
  concurrent task status. No `tests.test_graph_quality` test fails.
- Not run: `make local-ci`; the narrower full discovery already reproduces the
  shared worktree's unchanged known failures, so downstream gates cannot make
  the aggregate command green until concurrent owners reconcile them.

## Decisions

- Selected the contiguous tail slice covering bulk graph construction, graph
  quality gates, source action planning, and enrichment execution because it is
  a coherent ownership boundary and removes 39 high-value tests in one
  mechanical change.
- Kept test methods, ordering, assertions, local handler classes, and the private
  fixture unchanged. Only module-level imports and the class name were added.
- Reused `tests/support.py`; no new fixture abstraction was necessary.
- Left now-potentially-unused imports in `tests/test_system.py` untouched to keep
  this task mechanical and avoid mixing cleanup with source movement.
- Added no production changes. Production files visible in `git status` belong
  to concurrent tasks and were neither modified nor reverted by T-593.

## Risks

- `tests/test_system.py` remains 20,613 lines and 276 test methods, so MR-2 is
  reduced but not closed.
- The shared worktree was dirty before this task and gained additional dynamic
  allocation scripts while verification ran. PM integration must reconcile all
  concurrent handoffs before claiming a green release baseline.
- The baseline copy and full-suite logs under `/tmp` are ephemeral diagnostic
  evidence only and are not release artifacts.

## Dependencies

- `tests/support.py` supplies unchanged environment isolation and the baseline
  `SystemService`/router fixture.
- T-576 establishes the prior mechanical split pattern and count gate.
- Concurrent dynamic allocation and PM tasks own the unchanged aggregate test
  failures; T-593 does not alter their files.

## Blockers

- None for the graph test split. A green `make local-ci` remains dependent on
  concurrent owners resolving their existing dynamic allocation and roadmap
  audit failures.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; production code was not changed.
- Domain module decision: not applicable because this task only relocates test
  source and reuses the existing facade fixture.
- Focused regression: `python3 -m unittest tests.test_graph_quality` passed all
  39 moved facade/domain regressions, with AST equivalence to their originals.
- Contract impact: no API schema, storage schema, UI behavior, or paper-only /
  no-broker boundary changed.

## Artifacts

- None. T-593 creates source and handoff documentation only. `/tmp/t593-*.log`
  and `/tmp/t593-test-system-before.py` are local ephemeral diagnostics,
  classified `local-only`, contain no sensitive data, and are not acceptable
  for non-local production release gates.

## Handoff Checklist

- [x] Test source changes completed
- [x] Focused, compilation, equivalence, and aggregate checks recorded
- [x] No production/API/storage/UI contract change
- [x] `tasks/todo.md` intentionally left to the parent PM agent

## Next Recommended Action

1. PM / Release Coordination records T-593 in `tasks/todo.md` and reviews the
   unchanged aggregate failure baseline with concurrent task owners.
2. Continue MR-2 with another coherent slice, preferably production release
   evidence tests or daily data pipeline tests, using the same AST/count gate.
3. Run `make local-ci` after the shared worktree's dynamic allocation and roadmap
   status failures are reconciled.
