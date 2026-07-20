# Handoff: T-588 Dynamic Allocation Integration Closure

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence; Research and AI Workflows; Platform and Quality; Product and UI; Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: `/root`
- Branch/worktree: shared root worktree
- Artifact classification: local-only

## Objective

Integrate and validate T-581 through T-588 as one paper-only dynamic asset allocation workflow, including PIT data, explainable factors, model comparison, risk sizing, backtests, HTTP API, Streamlit dashboard, and replayable decision snapshots.

## Scope

- In scope: domain integration, YAML parameters, application API, append-only decision/backtest records, paper snapshot linkage, permissions, dashboard discovery, docs, roadmap closure, and local acceptance.
- Out of scope: real broker connectivity, order generation, paid or ungoverned data, fabricated production evidence, and claiming that a 6-12 month observation period has elapsed.

## Background

T-581 established the architecture and T-582 through T-588 were implemented by the repository owner groups in parallel. PM integration was required to reconcile contracts, preserve the growth freeze, expose a usable API, and test the end-to-end research flow.

## Problem Statement

Individually tested modules were not sufficient: the final product needed one point-in-time evaluation path, stable persistence identities, source-backed dashboard contracts, conservative missing-data behavior, and an immutable paper audit object with no execution capability.

## Expected Deliverables

- `app/dynamic_allocation/`: PIT repositories, factors, rules/ML, allocation, risk, backtest, application API boundary, dashboard, and paper ledger.
- `config/dynamic_allocation.yaml`: governed series, factor parameters, allocation weights, Kelly and risk settings.
- `app/api.py` and `app/api_routes.py`: thin dynamic-allocation HTTP handlers and role policy.
- `scripts/dynamic_allocation_paper_run.py` and `scripts/dynamic_allocation_dashboard_acceptance.py`: local paper and browser acceptance entrypoints.
- Updated README, API contract, PostgreSQL schema, task statuses, tests, and per-phase handoffs.

## Current Findings

- Critical missing, stale, future, or quality-blocked inputs never become a neutral factor or target allocation.
- Complete controlled PIT input produces eight explained factors, a five-state regime, a five-bucket requested allocation, conservative Kelly/risk clipping, SPY/QQQ/SGOV weights, and a deterministic paper snapshot.
- Rule baseline remains the default unless a complex candidate passes every chronological Sharpe/drawdown stability gate.
- Backtest signals become effective on the next observation and disclose cash proxies before SGOV availability.
- The dashboard consumes HTTP only, discovers the latest backtest, and renders both complete and data-insufficient states.
- Local smoke data and screenshots are acceptance fixtures, not investment data or non-local release evidence.

## Proposed Work Plan

1. Operate scheduled paper evaluation at a documented cadence with governed PIT inputs.
2. Review data quality, factor attribution, risk clips, and model comparison results monthly.
3. Evaluate TLT/GLD only after 6-12 months of real paper evidence; retain SQQQ as tactical research only.

## Validation Plan

- Run `make local-ci PYTHON=.venv/bin/python`.
- Run the 58-test dynamic-allocation suite and focused API/dashboard tests.
- Run desktop/mobile Chrome acceptance against the real local API and Streamlit process.
- Validate packaging metadata, handoffs, Markdown, security, and diffs.

## Risks

- PostgreSQL behavior has contract/schema coverage but was not exercised against a live PostgreSQL instance in this closure.
- Current end-to-end populated data is a controlled local smoke fixture, not a production market-data refresh.
- XGBoost/LightGBM remain optional; LightGBM emits a harmless feature-name warning under the current Python 3.14 test environment.
- The 6-12 month longitudinal paper record is necessarily future operational evidence.

## Dependencies

- Governed public/local data providers with release and vintage timestamps.
- Python 3.11+ and declared optional analysis/ML/dashboard extras.
- Local API and Streamlit processes, or equivalent reverse-proxied deployment.

## Blockers

- None for code, tests, local paper operation, or dashboard use.
- TLT/GLD expansion remains gated by the future longitudinal observation window.

## Handoff Checklist

- [x] T-581 through T-588 code and docs integrated
- [x] Paper-only/no-broker/no-order boundary tested
- [x] API, persistence, dashboard, and paper snapshot connected
- [x] Focused and browser tests passed
- [x] Roadmap statuses updated
- [x] Local-only evidence classification recorded

## Evidence

- `make local-ci PYTHON=.venv/bin/python`: 411 tests passed, followed by UI static, security (381 files, zero findings), Markdown link, handoff (164 files), and canonical document metadata checks; local environment; 2026-07-17; no intended sensitive output; not a non-local release artifact.
- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation`: 58 tests passed; local-only.
- `.venv/bin/python scripts/dynamic_allocation_dashboard_acceptance.py http://127.0.0.1:8502 --output-dir /tmp/dynamic-dashboard-final --timeout 45`: desktop/mobile passed with 4 Plotly charts, 21 tables, zero exceptions, and zero horizontal overflow; local-only temporary screenshots.
- `http://127.0.0.1:55539`: current-code local API, backed by ignored local SQLite smoke state; paper-only.
- `http://127.0.0.1:8502`: current-code Streamlit dashboard connected to that API; paper-only.

## SystemService Growth Freeze Review

- New business logic added directly to `app/services.py`: no.
- Domain placement: all new behavior lives under `app/dynamic_allocation/`; `ApiRouter` owns only thin lazy construction, authorization, and HTTP mapping.
- Focused regression: `tests/dynamic_allocation/test_application.py` covers API envelopes, permissions, persistence, PIT decisions, and backtest retrieval.
- Contract/boundary changes: new dynamic-allocation API and SQLite/PostgreSQL observation schema were documented; existing APIs and storage collections were not changed; paper-only/no-broker constraints were strengthened.

## Next Recommended Action

Replace the controlled smoke observations with governed provider ingestion, schedule paper evaluations, and review the first monthly attribution/quality report without changing the rule baseline or adding assets prematurely.
