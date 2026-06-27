# Handoff: T-493 Data Health and Source Health Center

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI, PM / Release Coordination
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-493

## Objective

Add a read-only data/source health center that answers whether the personal company intelligence system is fresh, failed, pending, or missing across market data, research reports, official disclosures, company materials, company database builds, and paper-only workflow feedback.

## Scope

- In scope: read-only backend health APIs, API contract docs, focused tests, dashboard/data-center UI panels, UI static contract, browser smoke.
- Out of scope: destructive schema migration, route grouping, `SystemService` domain extraction, external downloads, real broker integration, live trading, automatic order execution.

## Background

T-502 chose an aggregation-first run summary/read-model strategy. T-501 added a pre-refactor API behavior baseline. T-493 now consumes those decisions to expose source health without introducing a new persistent run table.

## Problem Statement

The system had many local run histories and artifacts, but users could not easily tell whether data was stale, missing, failed, or waiting for manual action. This made the product look scattered and non-automatic even when local pipelines had partial evidence.

## Expected Deliverables

- `GET|POST /api/data-health/runs/summary` for unified run summaries.
- `GET|POST /api/data-health/summary` for user-facing source health rows.
- UI panels: dashboard `今日数据状态` and data-center `来源健康中心`.
- Focused tests and API docs.

## Current Findings

- Existing run families are enough for a first read-model: ingestion jobs/schedules, company database build runs, company package import runs, company intelligence cycle runs, material inbox pending signals, daily update artifacts, and personal intelligence artifacts.
- `app.server` loads `.env` by default; for browser smoke on this machine, a clean local environment is needed to avoid missing `psycopg` when `.env` points at PostgreSQL.

## Proposed Work Plan

1. Add facade methods in `SystemService` for run summary and source health summary.
2. Register `/api/data-health/runs/summary` and `/api/data-health/summary` in `ApiRouter` with existing analyst/data roles.
3. Add focused regression in `tests/test_system.py`.
4. Add dashboard/data-center UI panels and static contract coverage.
5. Run validation and browser smoke.

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_data_health_summary_aggregates_runs_sources_and_next_actions`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/ui_static_check.py`
- `git diff --check`
- browser smoke against clean-env local server on `http://127.0.0.1:8010/ui?verify=t493b`
- final standard checks/full tests before commit

## Risks

- The read model reads local artifacts if present. These artifacts remain `local_only` and `acceptable_for_non_local_release=false`.
- The UI source health rows are intentionally concise. Raw run/source details are available only through advanced trace folds.
- The first implementation keeps logic in `SystemService` facade for compatibility; T-500 should later extract it behind a domain module.

## Dependencies

- T-501 golden API baseline.
- T-502 data health run summary ADR.
- Existing run histories and material inbox read methods.
- Existing UI summary-first helpers and static contract check.

## Blockers

- None for local T-493 completion.

## Handoff Checklist

- [x] Backend read-only health APIs added.
- [x] Focused tests added and passed.
- [x] API docs updated.
- [x] Dashboard and data-center UI panels added.
- [x] Browser smoke passed with console error count 0.
- [x] `tasks/todo.md` marked T-493 DONE.

## Evidence

- `app/services.py`: `data_health_runs_summary` and `data_health_summary` read models.
- `app/api.py`: `/api/data-health/runs/summary` and `/api/data-health/summary` routes.
- `tests/test_system.py`: `test_data_health_summary_aggregates_runs_sources_and_next_actions`.
- `app/static/index.html`: `今日数据状态` and `来源健康中心` panels.
- Playwright smoke result: title `公司情报与市场综合分析平台`, console errors `[]`, dashboard rows `6`, source health rows `6`.

## Next Recommended Action

Proceed to T-494: split the default `/ui` into personal research workspace and backend maintenance reachability while preserving existing tab IDs and DOM contracts.
