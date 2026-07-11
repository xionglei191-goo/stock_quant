# Handoff: T-570 Workflow scheduling helper extraction

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-07-10
- Last agent: Kiro (Claude Opus 4.8)
- Branch/worktree: main

## Objective

Reduce `SystemService` monolith size by extracting pure workflow scheduling / DAG
planning helpers into a domain module, following the SystemService Modularization
ADR, with no API, storage schema, UI, or paper-only boundary change.

## Scope

- In scope: `app/services.py` workflow scheduling pure helpers; new
  `app/service_modules/workflow_planning.py`.
- Out of scope: workflow methods that read `self.store` (e.g.
  `_workflow_last_run`, `_workflow_lineage_summary`,
  `_workflow_latest_logical_run_date`, `_workflow_dependency_graph_row`,
  `_execute_workflow_task`); API routes; DB schema; UI; other domains.

## Background

`app/services.py` still held ~34k lines in a single `SystemService` class
(995 methods). The ADR (`docs/systemservice-modularization-adr.md`) mandates
incremental, facade-preserving extraction into `app/service_modules/`. Workflow
orchestration (ADR domain boundary #6) had not yet been extracted.

## Problem Statement

Deterministic workflow scheduling logic (cron mapping, topological sort,
schedule/backfill date math, queue routing, scheduler recommendation) lived
inline in `SystemService`, inflating the monolith and mixing pure computation
with stateful orchestration.

## Expected Deliverables

- New `app/service_modules/workflow_planning.py` with the pure functions.
- `SystemService` facade methods delegating to the module, signatures unchanged.
- Green regression per ADR checklist.

## Current Findings

- AST analysis found 311 pure leaf helpers in `SystemService` (no `self`
  data-attribute access and no `self` method calls).
- 14 workflow-scheduling leaves were fully pure and mutually consistent,
  depending only on `re`, `json`, `hashlib`, `datetime`, and module-level
  `to_plain` / `parse_datetime` from `app.utils` (no import cycle).

## Proposed Work Plan

Completed in this turn:

1. Create `workflow_planning.py` with 14 pure functions.
2. Import it in `app/services.py` and replace the 14 method bodies with
   one-line delegations, keeping identical signatures.
3. Run the full regression checklist.

## Validation Plan

Run the ADR regression checklist (clean-env pattern from AGENTS.md §9).

## Risks

- Low. Behavior-preserving move of pure functions; internal callers
  (`self._workflow_*`) and public method signatures are unchanged. Full suite
  count is unchanged (332) and passes.

## Dependencies

- None. `app.utils` and `app.models` do not import `app.services`, so no cycle.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable (ADR-aligned; no contract change)
- [x] `tasks/todo.md` status updated if roadmap state changed

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
# clean-env full suite (AGENTS.md §9 pattern)
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
git diff --check
```

Result:

- Passed: py_compile OK; `Ran 332 tests ... OK` (baseline was also 332 OK);
  `ui_static_check.py` exit 0; `security_check.py .` exit 0 with 0 findings
  across 362 files; `git diff --check` clean.
- Failed: none.
- Not run: none.

Metrics:

- `app/services.py`: 33921 -> 33776 lines (-145).
- `app/service_modules/workflow_planning.py`: 248 lines (new, local source, not
  an artifact deliverable).

## SystemService Growth Freeze Review

- New `SystemService` business logic added? No. This is a refactor-only change;
  no new behavior was introduced.
- Why a domain module was/was not used: 14 pure scheduling helpers were moved
  out of `SystemService` into `app/service_modules/workflow_planning.py`.
  `SystemService` retains the same method names as thin facades that delegate to
  the module, per the ADR facade rule. No stateful (store/audit/permission)
  logic was moved.
- Focused regression protecting the facade: the full `tests/test_system.py`
  suite (332 tests, including orchestration/workflow endpoints and the
  `test_golden_api_behavior_baseline_for_backend_domain_refactor` baseline)
  passes unchanged.
- Did API schema, storage schema, UI behavior, or paper-only/no-broker
  boundaries change? No. Method signatures, payloads, and boundaries are
  identical.

## Next Recommended Action

1. Continue extraction with the next coherent pure-leaf cluster (candidates from
   AST scan: `source_review_escalation_*` -> governance module,
   `llm_*escalation` -> research/AI module, `portfolio_*` pure helpers ->
   portfolio module).
2. Consider extracting the stateful workflow orchestration into a `workflow`
   service that receives the store, once a second pure batch lands.
3. Track cumulative `SystemService` line reduction in the ADR.
