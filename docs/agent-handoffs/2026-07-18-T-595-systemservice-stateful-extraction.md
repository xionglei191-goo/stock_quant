# Handoff: T-595 Graph traceability stateful extraction

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex (T-595 delegated agent)
- Branch/worktree: current shared worktree

## Objective

Extract the next bounded, read-only, store-backed domain from
`SystemService` while preserving the facade signature, API behavior, storage
behavior, and project governance boundaries.

## Scope

- In scope: graph traceability report construction, thesis/decision/answer
  traceability rows, issuer decision filtering, facade/domain parity, and the
  modularization ADR.
- Out of scope: graph query construction, edge quality, readiness mutation and
  audit, API URLs/payloads, storage schema, UI, dynamic allocation, roadmap, and
  risk register edits.
- Risk level: low; this is a read-only extraction with exact method equivalence
  and focused facade coverage.

## Background

T-577 established explicit store injection for workflow reporting. After T-593
created a focused graph regression module, graph traceability was the safest
remaining stateful slice: it reads six store collections, has no audit or
permission side effects, and is protected by existing API-level regressions.

## Problem Statement

`graph_traceability_report` and its four private store traversal helpers still
lived in the central facade. That kept read-only graph domain logic coupled to a
32,282-line service class and increased ownership and review cost.

## Expected Deliverables

- Add a graph traceability domain object receiving only `store`.
- Keep `SystemService.graph_traceability_report()` as a compatibility facade.
- Remove the duplicated private traversal helpers from the facade.
- Prove domain/facade parity and preserve existing API behavior.
- Run focused, golden, aggregate, compilation, security, UI static, whitespace,
  and handoff checks.

## Current Findings

- Completed: `GraphTraceabilityReporting` owns the original report and four
  private helper implementations behind explicit store injection.
- Completed: the facade retains the existing optional-filter signature and
  delegates directly to the domain object.
- Completed: a representative focused fixture covers a traceable
  thesis-to-signal-to-decision chain, a traceable research answer, an
  untraceable cross-issuer thesis, filtering, detail suppression, and limits.
- Completed: five moved method ASTs match the original `HEAD` implementations.
- In progress: none.
- Not started: subsequent stateful reporting extractions.
- Blocked: none for T-595.

## Proposed Work Plan

Completed in this turn:

1. Compare read-only candidates and reject slices needing facade callback
   injection or mutation dependencies.
2. Move graph traceability reporting and helpers to a store-injected module.
3. Add facade/domain parity coverage to the focused graph module.
4. Run targeted, golden, aggregate, security, and documentation gates.

## Validation Plan

Compare normalized ASTs for the five extracted methods, run the full focused
graph module, run the existing graph traceability API regression and golden API
baseline, compile all Python entry points, run full discovery, security and UI
static checks, then validate whitespace and handoff structure.

## Files Touched

- `app/service_modules/graph_traceability.py`: new 175-line / 8,955-byte
  store-injected read-only graph reporting domain.
- `app/services.py`: replaced graph traceability business logic with a facade
  delegate and removed four private helpers; 32,282 lines before and 32,137
  lines after, a net reduction of 145 lines.
- `tests/test_graph_quality.py`: added one facade/domain parity test and required
  model imports; 1,334 lines before and 1,426 lines after.
- `docs/systemservice-modularization-adr.md`: recorded T-595's boundary,
  dependency injection decision, dated size metric, and compatibility gates.
- `docs/agent-handoffs/2026-07-18-T-595-systemservice-stateful-extraction.md`:
  records implementation and acceptance evidence.

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_graph_quality
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_query_links_evidence_portfolio_market_data_and_13f tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor
python3 <AST equivalence script comparing HEAD app/services.py with app/service_modules/graph_traceability.py>
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py tests/dynamic_allocation/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
python3 scripts/ui_static_check.py
git diff --check -- app/services.py app/service_modules/graph_traceability.py tests/test_graph_quality.py docs/systemservice-modularization-adr.md docs/agent-handoffs/2026-07-18-T-595-systemservice-stateful-extraction.md
python3 scripts/check_handoffs.py
```

Result:

- Passed: focused graph module, 40 tests in 2.110 seconds.
- Passed: existing traceability API regression and golden API baseline, 2 tests.
- Passed: normalized AST equivalence for the report and all four moved helpers.
- Passed: compilation, security scan (381 files, zero findings), UI static check,
  and whitespace check.
- Passed count gate: full discovery finds 432 tests, up from 423 at task intake.
  T-595 adds one test; eight additional tests arrived from concurrent work.
- Failed, pre-existing and unrelated: full discovery reports the same 6 failures
  and 14 errors seen at intake. Fourteen errors and three failures are in
  concurrent dynamic allocation work; three failures are PM roadmap/completion
  audits. No graph traceability test fails.
- Not run: `make local-ci`; its component discovery is already known to fail on
  the unchanged concurrent failure set. All task-relevant component gates were
  run separately.

## Decisions

- Chose graph traceability over edge quality because traceability needs only the
  store. Edge quality would require injecting `query_graph` or the facade,
  weakening the stateful module boundary.
- Moved all four private traversal helpers with the public report to avoid a
  domain module that calls back into `SystemService`.
- Repeated the established local `_truthy` and `_bounded_limit` utilities inside
  the domain object exactly, matching the T-577 store-backed module pattern and
  preserving coercion behavior.
- Did not export the class from `app/service_modules/__init__.py`; consumers use
  the explicit domain module path, consistent with `WorkflowReporting`.

## Risks

- `app/services.py` remains 32,137 lines; this extraction reduces but does not
  close the modularization maintenance risk.
- `GraphTraceabilityReporting` intentionally accepts `Any` for the heterogeneous
  local/SQLite/PostgreSQL-compatible store interface, matching the established
  workflow reporting pattern. A store protocol can be introduced later if
  multiple extracted modules benefit from it.
- The shared worktree contains concurrent production, UI, dynamic allocation,
  roadmap, and handoff changes. T-595 preserved and did not revert them.

## Dependencies

- Store collections: `theses`, `signals`, `decisions`, `research_answers`,
  `evidence`, and `documents`.
- Existing facade route: `GET|POST /api/graph/traceability-report`.
- Existing T-593 focused module and the golden API regression.

## Blockers

- None for T-595. A green aggregate `make local-ci` depends on concurrent owners
  reconciling the known dynamic allocation and PM task-status failures.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no. The facade lost business logic
  and now contains a one-line compatibility delegate.
- Domain module decision: used `app/service_modules/graph_traceability.py`
  because the behavior is a coherent read-only store-backed graph domain.
- Focused regression: 40 graph tests pass, including direct facade/domain parity;
  the existing API traceability regression and golden API baseline also pass.
- Contract impact: no API schema, storage schema, UI behavior, audit behavior,
  permission behavior, paper-only boundary, or no-broker boundary changed.

## Artifacts

- None. `/tmp/t595-discovery.log` is ephemeral `local-only` diagnostic output,
  produced by unittest discovery on 2026-07-18, contains no sensitive data, and
  is not acceptable for non-local release gates.

## Handoff Checklist

- [x] Code and focused test changes completed
- [x] Required checks run or aggregate failure explicitly recorded
- [x] Modularization ADR updated; API/storage/UI contracts unchanged
- [x] `tasks/todo.md` intentionally left to the parent PM agent

## Next Recommended Action

1. PM / Release Coordination records T-595 in `tasks/todo.md` and integrates the
   concurrent handoffs.
2. Reconcile the dynamic allocation and task-status failures, then run
   `make local-ci` on the combined worktree.
3. For the next extraction, evaluate another bounded read-only store report;
   avoid candidates that require injecting the whole facade or mutation hooks.
