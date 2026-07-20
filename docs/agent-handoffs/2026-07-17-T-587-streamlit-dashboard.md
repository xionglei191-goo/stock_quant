# Handoff: T-587 Streamlit Dynamic Allocation Dashboard

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: /root/t587_dashboard
- Branch/worktree: shared working tree
- Boundary: local-only research dashboard; paper simulation only

## Objective

Deliver a Streamlit research page that consumes only the dynamic-allocation HTTP API and answers the current regime, target allocation, explanation, history, backtest, data freshness, and risk questions without presenting unavailable data as current fact.

## Scope

- In scope: read-only API client, version-tolerant presentation models, Streamlit rendering, `/ui` navigation entry, dashboard dependency declaration, focused tests, browser acceptance, and this handoff.
- Out of scope: model/factor/backtest calculations, persistence, broker connectivity, order actions, data ingestion controls, and unrelated `/ui` workflows.

## Background

T-581 specifies a summary-first Streamlit page backed by `GET /api/dynamic-allocation/current`, `/history`, `/data-health`, and `/backtests/{run_id}`. T-587 depends on the rule allocation and risk-cap work while preserving the repository's local-only and simulated-only boundary.

## Problem Statement

The dashboard must remain useful across both a complete decision and a governed data-insufficient response. It also needs to tolerate the API's nested persisted backtest `result`, show source timing and freshness, recover visibly from connection errors, and avoid direct database access or fabricated fallback values.

## Expected Deliverables

- Thin Streamlit entrypoint with summary, factors, allocation caps, warnings, history, backtest, drawdown, stress periods, and data-health views.
- HTTP client for unified `success/data/error/trace_id` envelopes and identity headers.
- Stable presentation normalization for current, history, health, and persisted backtest shapes.
- Existing `/ui` navigation entry to `http://127.0.0.1:8501`.
- Desktop/mobile and error/empty-state evidence.

## Current Findings

- Final source-backed rendering shows 4 Plotly charts and 21 bounded tables with no exception or horizontal overflow at 1440x1000 and 390x844.
- A real local API with an empty SQLite database correctly returns eight unavailable factors and blocks allocation. The dashboard renders this as data-insufficient, retains the factor warnings and health table, and does not substitute a neutral score or allocation.
- Persisted backtests may place metrics, benchmark metrics, points, and stress periods inside `result`; the presentation layer reconstructs strategy NAV/drawdown from points and renders benchmark metrics as a comparison table.
- All API-derived strings passed to `unsafe_allow_html` are escaped. Other API values use native Streamlit or Plotly renderers.
- The sidebar is collapsed initially so narrow screens open on decision content; connection controls remain available through the standard Streamlit sidebar control.

## Proposed Work Plan

1. Parent PM reviews the shared-tree integration and marks T-587 complete in `tasks/todo.md`.
2. Run the page against the retained local API process with `AI_QUANT_API_BASE_URL=http://127.0.0.1:8001` or the normal service on port 8000.
3. Use the paper-run workflow to accumulate real local decision history; do not create dashboard sample fallback data.

## Validation Plan

- Compile the dashboard, test, and browser acceptance modules.
- Run focused dashboard tests and full `tests/dynamic_allocation` discovery.
- Exercise a real local API data-insufficient state with Streamlit AppTest.
- Exercise a source-backed controlled decision through Chrome at desktop/mobile viewports.
- Run existing UI static, security, handoff, and diff checks.

## Risks

- The `/ui` entry uses the local default `http://127.0.0.1:8501`; non-local deployment needs an environment-specific route or reverse proxy before release.
- The live local database currently has no governed observations, so it intentionally cannot render a current allocation chart. Controlled API evidence proves the chart/table path, while real API evidence proves the conservative empty state.
- Streamlit and Plotly are optional dependencies; the dashboard process must install the `dynamic-allocation-dashboard` extra.

## Dependencies

- `plotly>=5.24` and `streamlit>=1.40` are declared under the `dynamic-allocation-dashboard` optional extra.
- Dynamic-allocation API endpoints and the unified response envelope are required.
- Browser acceptance reuses the repository's Chrome DevTools acceptance helper and a local Chrome/Chromium binary.

## Blockers

- No code blocker remains in T-587 scope.
- Non-local URL routing and authentication deployment are intentionally outside this local-first task.

## Handoff Checklist

- [x] API-only dashboard boundary implemented
- [x] Current allocation, factor, cap, history, backtest, drawdown, stress, health, and warning views implemented
- [x] Loading, empty, error, and recovery states implemented
- [x] Real API empty-state smoke passed
- [x] Controlled chart/table browser render passed at desktop and mobile sizes
- [x] `/ui` entry and optional dependencies added
- [x] Focused and dynamic-allocation tests passed
- [x] Security and UI static checks passed
- [ ] Parent PM updates `tasks/todo.md`

## Evidence

- `.venv/bin/python -m unittest tests.dynamic_allocation.test_dashboard -v`: 11 passed; local-only, 2026-07-17, Product and UI, no sensitive data, not acceptable for non-local production release.
- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation`: 58 passed; local-only, 2026-07-17, Product and UI / Platform and Quality, no sensitive data, not acceptable for non-local production release.
- `.venv/bin/python scripts/dynamic_allocation_dashboard_acceptance.py http://127.0.0.1:8502 --output-dir /tmp/dynamic-dashboard-final --timeout 45`: desktop/mobile passed, 4 charts, 21 tables, 0 exceptions, 0 horizontal overflow; screenshots `/tmp/dynamic-dashboard-final/dashboard-desktop.png` and `/tmp/dynamic-dashboard-final/dashboard-mobile.png`; producer is the acceptance script, local environment, generated 2026-07-17, no sensitive data, local-only and not acceptable for non-local production release.
- `AI_QUANT_API_BASE_URL=http://127.0.0.1:8001 .venv/bin/python -c '<Streamlit AppTest>'`: real local API data-insufficient state passed with 1 title, 7 metrics, 9 tables, 0 exceptions; local-only, 2026-07-17, no sensitive data, not acceptable for non-local production release.
- `AI_QUANT_API_BASE_URL=http://127.0.0.1:9 .venv/bin/python -c '<Streamlit AppTest>'`: connection error state passed with one error, one recovery message, and zero exceptions; local-only, 2026-07-17, no sensitive data, not acceptable for non-local production release.
- `.venv/bin/python scripts/ui_static_check.py`: passed; local-only, 2026-07-17.
- `.venv/bin/python scripts/security_check.py .`: passed with zero findings across 381 checked files; local-only, 2026-07-17.

## Next Recommended Action

Parent PM should rerun the integrated quality gate, update T-587 roadmap status, and start the Streamlit process against the final local API URL before handing the working URL to the user.
