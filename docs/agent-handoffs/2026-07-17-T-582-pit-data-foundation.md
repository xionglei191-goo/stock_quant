# Handoff: T-582 Point-in-Time Data Foundation

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality; Research and AI Workflows; Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: /root/t582_pit_data
- Branch/worktree: shared current worktree
- Related tasks: T-581, T-582, T-583
- Evidence classification: local-only

## Objective

Implement the Phase 1 point-in-time data foundation for dynamic asset allocation without calculating factors, training models, generating allocations, or adding execution capability.

## Scope

- In scope: immutable observation contracts, YAML config/hash, SQLite and PostgreSQL repository contracts, local fixture ingestion, existing market-data adapter, data-health output, typed PostgreSQL schema, focused tests.
- Out of scope: factors, regimes, allocation, Kelly sizing, backtests, APIs, dashboard, broker connectivity, and automated execution.

## Background

T-581 selected `app/dynamic_allocation/` as the domain boundary and requires all historical decisions to use only observations whose `available_at` was known at that time. High-volume observations use typed SQL tables; existing market bars remain in place and are read through an adapter.

## Problem Statement

Current market data did not provide an immutable macro/valuation observation vintage store. Dynamic allocation therefore needed explicit `release_date`, `available_at`, vintage, revision, source, rights, quality, and payload-hash semantics before any factor or backtest work could safely proceed.

## Expected Deliverables

- Point-in-time observation/provider/repository contracts with timezone and temporal validation.
- SQLite implementation proving idempotency, immutable revisions, historical vintage selection, and future exclusion.
- PostgreSQL implementation and typed `ai_quant.economic_observations` schema/indexes.
- Local CSV/JSON fixture provider and existing `market_data` read adapter.
- Data-health report exposing coverage, freshness, missing/stale series, source/grain, and paper-only boundary.
- Focused regressions and current handoff.

## Current Findings

- SQLite stores each `(series_id, observation_date, vintage_date, revision_seq)` once and never overwrites changed content under the same natural key; changed content is reported as a conflict.
- `history_available` filters `available_at <= as_of`, then selects the latest then-known vintage per observation date. `latest_available` selects the latest observation date per series from that snapshot.
- Existing daily market bars are not copied; the adapter applies exchange close time plus configured delay and excludes same-day data before availability.
- Missing critical series and stale critical series make `ready_for_factor_calculation=false`; they are never converted to neutral scores.
- The local Python environment is externally managed. Verification used `/tmp/sotck-quant-t582-venv` with PyYAML and Pillow installed. `pip install -e .` also exposed a pre-existing setuptools flat-layout package discovery issue, so dependencies were installed directly in the temporary environment.

## Proposed Work Plan

1. T-583 consumes `history_available`/`latest_available` and preserves their as-of semantics in factor normalization.
2. A later API integration task adds ingest preview/execute and audit plumbing through a thin domain service; T-582 intentionally does not modify shared service/API files.
3. Run a real PostgreSQL contract test when the integration environment provides a database; the schema and psycopg-compatible implementation are present now.

## Validation Plan

- Compile all application, dynamic-allocation, dynamic test, and script Python files.
- Run all tests under `tests/dynamic_allocation`.
- Run the full unit suite and compare its failures to the PM baseline.
- Run security and handoff checks.

## Risks

- PostgreSQL behavior is contract-tested through SQL/schema assertions but was not executed against a live PostgreSQL server in this task.
- The series registry currently contains only representative critical Phase 1 sources. Each future source requires governance review before automated ingestion.
- Existing market bars do not carry vendor release timestamps, so the adapter derives availability from configured exchange close plus delay; downstream backtests must still execute on the next tradable point.

## Dependencies

- Runtime: Python 3.11+, PyYAML 6.0+.
- Optional PostgreSQL runtime: psycopg 3.1+.
- T-583 depends on the observation and repository contracts delivered here.

## Blockers

- None for SQLite/local fixture use.
- Live PostgreSQL integration proof awaits an available test database but does not block the documented repository contract.

## Handoff Checklist

- [x] Code changes completed.
- [x] Focused tests passed.
- [x] Full suite run and baseline-only failures recorded.
- [x] PostgreSQL schema updated.
- [x] Paper-only/no-broker boundary preserved.
- [x] No unrelated user or agent changes reverted.
- [ ] `tasks/todo.md` status update is delegated to the parent PM agent because this task packet explicitly excluded that file.

## Evidence

- `python3 -m py_compile app/*.py app/dynamic_allocation/*.py app/dynamic_allocation/**/*.py tests/dynamic_allocation/*.py scripts/*.py`: passed, local-only, 2026-07-17.
- `python3 -m unittest discover -s tests/dynamic_allocation`: passed, 28 tests, local-only, 2026-07-17.
- `python3 -m unittest discover -s tests`: ran 381 tests; 3 known PM-baseline completion/roadmap-state failures, no T-582 functional failures, local-only, 2026-07-17.
- `python3 scripts/security_check.py .`: passed with 0 findings across 381 checked files, local-only, 2026-07-17.
- `docs/postgresql-schema.sql`: typed PostgreSQL contract; no live database execution evidence, local-only and not valid for non-local release gates.
- Sensitive data: none. Non-local production release acceptable: no.

## SystemService Growth Freeze Review

- New business logic added to `app/services.py`: no.
- Domain placement: all T-582 logic lives under `app/dynamic_allocation/`; no facade was needed because API integration is out of scope.
- Focused regression: repository, provider, market adapter, config, and health tests under `tests/dynamic_allocation/`.
- Contract/boundary changes: adds a typed storage schema and domain contracts; no existing API schema, existing storage schema behavior, UI behavior, or paper-only/no-broker boundary changed.

## Next Recommended Action

The parent PM should review the diff, mark T-582 DONE in `tasks/todo.md`, and let T-583 consume the repository snapshots without bypassing `available_at` or substituting missing observations with neutral values.
