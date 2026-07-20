# SystemService Modularization ADR

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-07-17
- Related tasks: T-427, T-500, T-503, T-570, T-571, T-575, T-577, T-595
- Scope: `app/services.py` modularization strategy, completed extraction batches, and stateful module direction
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

## Company Intelligence Mainline Extraction (T-500)

Status: completed for the first company-intelligence slice on 2026-06-27.

Extracted modules:

1. `app/service_modules/company_intelligence.py`: symbol matching, company intelligence completeness verdict, section counts, and next-action selection.
2. `app/service_modules/market_data.py`: corporate-action price factors and market-data adjustment factor calculation.
3. `app/service_modules/research_reports.py`: research report month normalization, mapping rows, and viewpoint topic/sentiment rows.
4. `app/service_modules/graph_intelligence.py`: graph node identity, Neo4j labels, relationship types, and property shaping.
5. `app/service_modules/feedback_scoring.py`: simulation feedback realization scoring, added before T-500 and kept as the feedback domain module.

Facade rule:

- `SystemService` keeps the existing method names and API surface.
- Extracted modules own deterministic domain calculations.
- `SystemService` still owns store access, audit, permission context, and cross-domain orchestration.
- No API URL, payload, database schema, UI behavior, or paper-only boundary changed.

## Pure Helper Extraction Batches (T-570 and T-571)

Status: completed through T-571 on 2026-07-10.

- T-570 extracted 14 deterministic workflow scheduling and DAG-planning helpers to `app/service_modules/workflow_planning.py`; stateful workflow reads remained in the facade.
- T-571 extracted 20 source-review escalation, LLM escalation, and portfolio analytics helpers to three domain modules.
- Across both batches `app/services.py` decreased from 33,921 to 33,499 lines. This is a dated refactor metric, not a live size assertion.
- Existing facade signatures and API, storage, UI, audit, permissions, paper-only, and no-broker boundaries remained unchanged; the full 332-test baseline passed at each recorded handoff.

## Stateful Workflow Reporting Extraction (T-577)

Status: first store-backed slice completed on 2026-07-17.

- `app/service_modules/workflow_reporting.py` receives the narrow `store` dependency directly and owns read-only workflow run, SLA, schedule, dependency, definition, lineage, queue, and backfill-preview reporting.
- `SystemService` keeps the existing method names as compatibility facades; execution, retry, incident creation, audit, OpenLineage export, and scheduler handoff mutations remain in the facade.
- `app/services.py` decreased from 33,499 to 32,282 lines in this batch. This is a dated refactor metric, not a target by itself.
- Focused facade/module parity and the golden API baseline protect query semantics. API, storage schema, UI, audit, permissions, paper-only, and no-broker boundaries are unchanged.

Future stateful modules must continue explicit dependency injection: receive the narrow `store` dependency and only separately justified audit or policy dependencies, never the whole facade instance.

## Stateful Graph Traceability Extraction (T-595)

Status: completed on 2026-07-18.

- `app/service_modules/graph_traceability.py` receives only the narrow `store`
  dependency and owns read-only thesis, decision, and research-answer
  traceability reporting.
- `SystemService.graph_traceability_report()` retains its public signature as a
  compatibility facade. The four private store traversal helpers moved with the
  report and are no longer duplicated in the facade.
- `app/services.py` decreased from 32,282 to 32,137 lines in this batch. This is
  a dated refactor metric, not a target by itself.
- Focused facade/module parity, the existing graph traceability integration
  regression, and the golden API baseline protect query semantics. API, storage
  schema, UI, audit, permissions, paper-only, and no-broker boundaries are
  unchanged.

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
