# SystemService Modularization ADR

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-05-28
- Related tasks: T-427
- Scope: `app/services.py` modularization strategy and first extraction batch
- Non-goals: Big-bang rewrite, API contract changes

## Context

`SystemService` currently aggregates ingestion, evidence, research, portfolio, governance, workflow, and readiness logic in one class. This slows code review, increases regression surface, and raises handoff cost.

## Decision

Keep `SystemService` as a facade during migration. Extract low-risk helpers and domain logic in phases, with facade-level compatibility tests kept green.

## Target Module Boundaries

1. `ingestion`: source registration, ingestion schedules/jobs, connector orchestration.
2. `evidence`: document parse, evidence extraction, benchmark inputs.
3. `research`: thesis/signal/answer/challenger workflows.
4. `portfolio`: proposals, simulated execution, attribution, replay.
5. `governance`: permissions, source review, secret metadata, retention.
6. `workflow`: DAG/scheduler/backfill/readiness orchestration.
7. `readiness`: readiness reports, checklist/package gates.

## Migration Phases

1. Phase 1: Extract stateless helpers and shared normalizers.
2. Phase 2: Extract domain services with no API shape change.
3. Phase 3: Route facade methods to extracted services.
4. Phase 4: Freeze direct growth in `SystemService`; new behavior goes to extracted modules only.

## First Low-Risk Extraction (Completed)

- Extracted `safe_identifier()` helper to `app/service_modules/common.py`.
- `SystemService._safe_identifier()` now delegates to the shared helper.
- Behavior unchanged; API and data model unchanged.

## Regression Checklist

Run after each extraction batch:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
```

## Guardrails

- Do not change public API payloads during extraction phases.
- No direct DB schema churn as part of refactor-only PRs.
- Keep audit events, rights boundaries, and simulation-only constraints intact.
