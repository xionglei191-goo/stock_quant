# Handoff: T-501/T-502 Baseline and Run Summary ADR

## Metadata

- Status: DONE
- Owner group: Platform and Quality; Data and Evidence
- Reviewer groups: PM / Release Coordination, Product and UI, Research and AI Workflows, Governance, Security, and Compliance
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-501, T-502

## Objective

Create the pre-refactor behavior baseline and run-summary decision needed before implementing T-493 data health or T-498/T-500 backend modularization.

## Scope

- In scope: T-502 ADR, T-501 focused API behavior regression, docs index update, `tasks/todo.md` status update.
- Out of scope: implementing `/api/data-health/*`, changing API schemas, changing database schemas, route grouping, service extraction, UI data health center.

## Background

T-492 established that the next implementation should not jump directly into data health or service extraction. T-502 needed to decide whether run histories should be unified as schema or aggregated as a read model, and T-501 needed a behavior baseline before route/service refactors.

## Problem Statement

The repository has several run-producing flows and a large `SystemService` facade. Without a run-summary decision, T-493 could introduce premature schema churn. Without a golden API baseline, T-498/T-500 could silently change envelopes, route behavior, or paper-only boundaries during refactor.

## Expected Deliverables

- Add an ADR for data health run summary/read-model strategy.
- Add a focused API behavior baseline test through `ApiRouter.dispatch`.
- Update docs index and roadmap status.
- Run focused and standard validation.

## Current Findings

- T-502 decision: use aggregation-first read model, no destructive schema migration in the first implementation.
- Run families covered by the ADR: ingestion jobs/schedules, company database build runs, package/watchlist import runs, company intelligence cycle runs, material inbox signals, daily update pipeline artifacts, and personal intelligence refresh artifacts.
- T-501 baseline should be field-based, not snapshot-file based, to avoid brittle trace/timestamp/generated-ID diffs.

## Proposed Work Plan

1. Use `docs/data-health-run-summary-adr.md` as the T-493/T-502 contract.
2. Use `tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor` as the pre-refactor behavior baseline.
3. Start T-493 by adding read-only data/source health APIs against this ADR.
4. Start T-498/T-500 only after running the golden baseline and focused domain tests.

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/security_check.py .`
- clean-env `python3 -m unittest discover -s tests`

## Risks

- The new baseline is intentionally focused. Future T-493 source-health endpoints still need additional tests once implemented.
- The ADR does not add a persisted run model. If T-493 proves aggregation is too expensive or incomplete, a later read-store projection may be proposed with a separate ADR/update.
- Browser acceptance was not changed in this slice; T-495 remains the browser matrix owner.

## Dependencies

- Existing `ApiRouter` response envelope and role authorization behavior.
- Existing company intelligence, market data, graph, research report, simulation feedback, quality reconcile, and governance source APIs.
- Existing local-only/paper-only/no-broker/no-auto-trading boundaries.

## Blockers

- None for T-501/T-502.

## Handoff Checklist

- [x] T-502 ADR added.
- [x] T-501 focused golden API baseline added.
- [x] Docs index updated.
- [x] `tasks/todo.md` updated.
- [x] Focused test passed.

## Evidence

- `docs/data-health-run-summary-adr.md`: active ADR for aggregation-first run summary/read model.
- `tests/test_system.py`: `test_golden_api_behavior_baseline_for_backend_domain_refactor` covers envelope/trace prefix, company intelligence, market data, graph, structured reports, simulation feedback, dry-run performance update, quality reconcile, source governance, validation error, and permission denial.
- `tasks/todo.md`: T-501 and T-502 marked `DONE`.

## Next Recommended Action

Proceed to T-493: implement read-only `/api/data-health/runs/summary` and `/api/data-health/summary` against the ADR, then add the overview/data-center UI entry and browser acceptance in later T-493/T-495 slices.
