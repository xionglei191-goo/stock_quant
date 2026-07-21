# Handoff: T-606 Data Health Source Of Truth

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Product and UI; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t606_data_health`
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only
- Risk level: medium

## Objective

Make `/api/data-health/summary` report backend-aware market-data counts and freshness for typed/lazy PostgreSQL storage without materializing the market table, while preserving the existing response contract.

## Scope

- In scope: data-health domain extraction, bounded market-data health projection, source/consistency metadata, focused regression, API contract, and a read-only live PostgreSQL probe.
- Out of scope: roadmap edits, `app/api.py`, daily/latest-analysis behavior, usage metrics, report reconciliation, live data mutations, broker connectivity, and automatic orders.

## Background

T-602 moved approximately 28 million market rows into typed PostgreSQL storage and intentionally stopped loading them into `store.market_data`. The existing health summary still counted the in-memory dictionary and therefore reported zero rows and no freshness date.

## Problem Statement

The health endpoint conflated an empty lazy cache with an empty authoritative backend. It also did not disclose which store a count represented or whether cross-store consistency had been checked.

## Expected Deliverables

- A backend-aware, bounded market-data snapshot.
- Backward-compatible source rows with explicit source and consistency metadata.
- Regression evidence for a lazy store and a real local PostgreSQL probe.

## Current State

- Completed: domain module, facade extraction, compatibility additions, two focused tests, the existing API regression, API documentation, compile check, and real local PostgreSQL probe.
- In progress: none in T-606.
- Not started: cross-store research-report reconciliation; owned by T-604.
- Blocked: none.

## Current Findings

- The real local PostgreSQL probe reported `status=healthy`, estimated count `28,364,673`, latest date `2026-07-20`, `storage_mode=lazy_typed_backend`, and `consistency_status=consistent`.
- PostgreSQL counts use backend statistics during normal reads and are explicitly labeled `count_accuracy=estimated`; an exact backend count is used only if statistics say zero while a latest row exists.
- Research-report health remains scoped to the application registry. A zero registry count is not replaced with filesystem or search-index inventory and is labeled `consistency_status=not_reconciled`.

## Proposed Work Plan

1. Resolve a bounded backend market-data projection and extract source-health assembly from `SystemService`.
2. Preserve all existing response fields and add source/consistency metadata.
3. Verify lazy-store behavior and the real local PostgreSQL state.

## Validation Plan

- Run focused T-606 regressions.
- Compile the changed Python files.
- Probe the mounted current code against local PostgreSQL without writing data.
- Run handoff validation; parent runs the full integrated suite after concurrent tasks settle.

## Dependencies

- T-602 typed market-data query and estimate methods.
- Existing read-only `data_health_runs_summary` and material-inbox projections.

## Blockers

- None. A transient shared-worktree API failure occurred while the parallel usage-metrics task had added `origin` at the router but had not yet added the matching service argument; after that facade landed, the original API regression passed.

## Files Touched

- `app/service_modules/data_health.py`: backend-aware market snapshot, source rows, and full data-health summary assembly.
- `app/services.py`: imports the domain module and retains a thin `data_health_summary` facade.
- `tests/test_data_health.py`: lazy typed-store and backward-compatibility regressions.
- `docs/api-contracts.md`: documents source, consistency, estimate, and registry-scope additions.
- `docs/agent-handoffs/2026-07-21-T-606-data-health-source-of-truth.md`: this handoff.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_data_health tests.test_system.SystemServiceTests.test_data_health_summary_aggregates_runs_sources_and_next_actions
.venv/bin/python -m py_compile app/service_modules/data_health.py app/services.py tests/test_data_health.py
docker compose exec -T ai-quant-org python -c '<read-only data-health probe>'
python3 scripts/check_handoffs.py
```

Result:

- Passed: 3/3 focused and existing API tests; changed-file compile; real local PostgreSQL read-only probe.
- Failed then resolved: the first combined API run failed before executing T-606 assertions because a parallel usage-metrics edit temporarily passed unsupported `origin`; rerun passed after the parallel facade landed.
- Not run: full suite, per sub-agent packet; parent integration owns it.

## Evidence

- Live command output, generated 2026-07-21 by the read-only Docker Compose probe: local-only; count/date/source metadata only; no sensitive data; not valid for non-local release. No artifact file was written.

## Decisions

- Use backend statistics for normal health reads so a dashboard request never scans or materializes approximately 28 million rows; disclose that accuracy instead of presenting it as exact.
- Query only one newest row for freshness. If statistics are zero but that row exists, use the exact counter as a guarded recovery path.
- Keep the research registry count honest and explicitly defer filesystem/PostgreSQL/OpenSearch reconciliation to T-604.
- Keep `schema_id=data-health-summary-v1`; additions are backward-compatible fields rather than a version-breaking replacement.

## Risks and Open Questions

- PostgreSQL statistics can lag recent writes, so the displayed count is approximate by design; `count_accuracy` and `count_source` make that visible.
- `consistency_status=not_reconciled` for research reports is expected until T-604 establishes a cross-store inventory.
- The running HTTP process must reload current source before a live endpoint request observes the new projection; the parent owns integrated restart/acceptance.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly recorded
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status update delegated to parent T-603 integration as instructed

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; 151 net lines of source-health assembly were removed from the facade area.
- Domain placement: market snapshot and summary assembly live in `app/service_modules/data_health.py`; `SystemService.data_health_summary` only gathers existing dependencies and delegates.
- Focused regression: `tests.test_data_health` protects lazy backend counts/freshness and the prior source-row fields; the existing `/api/data-health/summary` API regression also passed.
- Contract/boundary changes: response additions only (`source_of_truth`, `consistency_status`, `summary.consistency_counts`, evidence metadata); no storage schema, write path, UI behavior, broker, auto-order, or paper-only boundary changed.

## Next Steps

1. Parent runs full local CI after usage and daily-analysis tasks converge.
2. Parent restarts/reloads the local app and probes `/api/data-health/summary` through HTTP.
3. T-604 uses its inventory to replace `not_reconciled` only after cross-store evidence is available.

## Next Recommended Action

Run the full integrated local CI after all T-603 parallel changes settle.
