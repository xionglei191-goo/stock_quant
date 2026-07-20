# Handoff: T-577 Workflow Reporting Extraction

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-07-17
- Last agent: Codex with delegated implementation
- Branch/worktree: main

## Objective

Establish the first bounded stateful domain extraction by moving read-only workflow reporting behind an explicit store-injected module while retaining the existing compatibility facade.

## Scope

- In scope: workflow runs, SLA, schedule, dependency graph, definitions, lineage, queue plan, logical-date and backfill-preview read behavior.
- Out of scope: workflow execution/retry, incident mutation, audit, OpenLineage export, scheduler handoff mutation, API/schema/UI changes.

## Background

T-570/T-571 completed pure-helper extraction, but store-backed reporting still lived in the central service. T-576 first separated the workflow regression surface.

## Problem Statement

Read-only workflow ownership remained mixed with cross-domain mutation and audit behavior, keeping a large stateful slice in the facade and leaving no established dependency-injection pattern for later extractions.

## Expected Deliverables

- A store-injected workflow reporting domain module.
- Thin compatibility facade methods with unchanged signatures and payloads.
- Direct module/facade parity and golden API regression.
- ADR record and growth-freeze review.

## Current Findings

- The coherent read-only slice could receive only the shared store and existing stateless planning helpers.
- Mutation and audit methods remain outside the extracted module.
- `app/services.py` decreased from 33,499 to 32,282 lines; the new module is 420 lines.

## Proposed Work Plan

1. Completed the read-only call-graph extraction.
2. Completed thin facade delegation and direct parity regression.
3. Completed ADR and handoff documentation.
4. Defer the next stateful domain until this pattern has passed the complete integration gate.

## Validation Plan

Run the focused workflow suite, golden API baseline, compilation, full unit discovery, UI static check, security scan, documentation gates, and whitespace validation.

## Risks

- Later source-governance and portfolio slices have additional audit/mutation coupling and must not be copied mechanically from this read-only pattern.
- File line reduction is secondary to ownership and compatibility; it is recorded only as a dated maintenance metric.

## Dependencies

- T-570 workflow planning helpers.
- T-576 workflow regression module.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated by PM integration

## Evidence

Commands run:

```bash
python3 -m py_compile app/services.py app/service_modules/workflow_reporting.py tests/test_workflow_service.py
python3 -m unittest tests.test_workflow_service
python3 -m unittest tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor
git diff --check -- app/services.py app/service_modules/workflow_reporting.py tests/test_workflow_service.py
```

Result:

- Passed: compilation; 5 focused workflow tests; golden API baseline; whitespace validation.
- Failed: none.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.
- Artifacts: none; refactor-only source and regression evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module decision: read-only store-backed workflow behavior moved to `app/service_modules/workflow_reporting.py`; the facade retains compatibility and mutation/audit orchestration.
- Focused regression: direct facade/module equality, the workflow service suite, and the golden API behavior baseline.
- API schema, storage schema, UI behavior, paper-only/no-broker boundaries changed: no.

## Next Recommended Action

1. Complete the full integration quality gate.
2. Measure facade thickness and suite duration before selecting another stateful domain.
3. Keep mutation/audit dependencies explicit in any later extraction.
