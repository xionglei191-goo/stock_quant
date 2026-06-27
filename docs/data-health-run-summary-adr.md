# Data Health Run Summary ADR

- Status: active
- Owner group: Data and Evidence, Platform and Quality
- Last updated: 2026-06-27
- Related tasks: T-493, T-501, T-502
- Scope: run history/read-model strategy for data health and source health
- Non-goals: database schema migration, destructive run table unification, changing existing API payloads, changing paper-only/no-live-trading boundaries

## Context

The company intelligence system now has multiple run-producing flows:

- ingestion jobs and ingestion schedules
- company database batch build runs
- company package/watchlist import runs
- company intelligence cycle runs
- material inbox and pending material preparation
- daily data update pipeline artifacts
- personal watchlist intelligence refresh artifacts

These flows answer related operator questions but currently use different records, artifacts, and field names. T-493 needs a data/source health center that can tell a personal user whether market data, reports, disclosures, IR materials, imports, and scheduled refreshes are fresh, failed, pending, or ready for the next action.

## Problem Statement

Unifying every run producer into one persistent model before the data-health product surface exists would create migration risk and delay the user-facing health center. At the same time, implementing data health directly against scattered payloads would make future refactors fragile.

## Decision

Use an aggregation-first run summary read model for the first implementation.

Do not migrate existing run schemas in T-493/T-502. Instead, create a read-model contract that normalizes existing run sources into common summary rows. `SystemService` remains the facade and can later delegate the aggregation to a `data_health` or `source_health` domain module.

## Run Families

The read model must be able to aggregate these run families:

| Run family | Existing source | Purpose in health center |
| --- | --- | --- |
| `ingestion_job` | ingestion job records and schedule execution payloads | source connector execution, failures, retries, next scheduled action |
| `company_database_build` | `CompanyDatabaseBuildRun` / batch build run history | company profile/event/relation/workflow build status and coverage deltas |
| `company_package_import` | company package or watchlist import run history | imported company package freshness, material manifest sidecars, failed imports |
| `company_intelligence_cycle` | company intelligence cycle run history | end-to-end company refresh, realization, workflow, and paper feedback update status |
| `material_inbox` | company material inbox ingest/pending payloads | IR/official material preparation status and pending manual actions |
| `daily_update_pipeline` | `artifacts/daily-update-local/latest-run.json` and pipeline summaries | daily automation freshness and step failures |
| `personal_intelligence_refresh` | `artifacts/personal-intelligence/latest.json` | watchlist company readiness, needs-attention counts, and local-only refresh status |

## Normalized Fields

Every run summary row should use these fields where data is available:

- `run_key`: stable read-model key, not necessarily a persisted ID.
- `run_family`: one of the families above.
- `domain`: market data, research reports, disclosures, company materials, company database, workflow, or governance.
- `status`: user-facing status such as `healthy`, `stale`, `failed`, `partial`, `pending`, or `unknown`.
- `latest_success_at`: most recent successful completion timestamp.
- `latest_failure_at`: most recent failed completion timestamp.
- `failure_count`: recent failure count.
- `pending_count`: unresolved work count.
- `target_count`: number of companies, symbols, files, or jobs targeted.
- `completed_count`: number completed successfully.
- `artifact_uri`: local artifact path or external URI when present.
- `next_action`: one concise operator action.
- `usage_boundary`: local-only/public-data/paper-only boundary statement.
- `source_payload_ref`: advanced trace pointer to the original run family and ID/artifact.

## Source Health Mapping

T-493 should derive source health rows from the run summary plus direct coverage signals:

- market data: latest market rows, schema coverage, backfill coverage, daily import artifacts.
- research reports: report inbox schedule, parsed/indexed counts, structure runs, local report boundaries.
- disclosures: ingestion schedules, disclosure events, official source governance.
- company IR/materials: material inbox manifests, pending queues, profile field extraction status.
- company database: build run history, coverage audit, quality reconcile status.
- workflow/feedback: company intelligence cycle runs, simulation feedback performance update status.

## API Guidance

Preferred first routes:

- `GET|POST /api/data-health/runs/summary`
- `GET|POST /api/data-health/summary`

Both routes should be read-only aggregation by default. If a future execute action is needed, it should call existing run producers rather than mutate the read model directly.

## Testing Guidance

T-501 should add golden behavior baselines before T-493 implementation. T-493 should then add focused tests for:

- run summary aggregation across at least company build, package import/cycle, ingestion, and local artifact families.
- source health rows for market data, research reports, materials, company database, and workflow.
- missing data state with executable next actions.
- local-only and no-live-trading boundaries.
- no destructive schema migration.

## Migration Criteria

A unified persistent model should only be reconsidered if the read model cannot answer these questions without repeated expensive scans:

1. Which sources failed most recently?
2. Which company or source needs the next manual action?
3. Which run family produced the latest health signal?
4. Which artifacts prove the result and what are their boundary labels?

If a persistent model becomes necessary, it should be introduced as a new read-store projection first. Existing run records should remain authoritative until compatibility is proven.

## Consequences

- T-493 can ship a useful health center without blocking on schema migration.
- T-498/T-500 can later move aggregation behind domain modules without changing the user-facing contract.
- The system keeps existing run histories intact and auditable.
- The read model must clearly label local-only artifacts so T-499 cannot accidentally treat them as production evidence.

