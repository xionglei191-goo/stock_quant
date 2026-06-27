# Handoff: T-487 K-line Moving Average System

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-487

## Objective

Add a practical moving-average layer to the local K-line panel so a personal user can read trend context directly inside the market data workspace.

## Scope

- In scope: K-line moving averages, MA controls, static UI contract, roadmap and handoff.
- Out of scope: real-time market data, broker integration, trading signals, drawing tools, external charting dependencies.

## Background

T-486 added a native SVG K-line panel for local OHLCV market data. The chart showed candles, volume and price metrics, but lacked the common MA references users expect when reading daily price trends.

## Problem Statement

A raw K-line chart is useful but incomplete for personal research. Users need trend overlays such as MA5, MA10, MA20 and MA60 without leaving the all-weather company intelligence system.

## Current Findings

- The existing chart already receives sorted local market data from `/api/market-data`.
- The browser can calculate daily moving averages from local `close` values without new backend API work.
- The existing SVG renderer can overlay MA polylines with no extra dependency.

## Expected Deliverables

- MA5, MA10, MA20 and MA60 calculations from local close prices.
- Colored MA overlays in the existing K-line SVG.
- Checkbox controls to show or hide each MA without reloading data.
- Latest MA value display for each MA window.
- Static UI contract updated.

## Proposed Work Plan

1. Add MA controls and latest-value slots under the K-line header.
2. Add MA calculation helpers and draw MA polylines in `renderKlineChart`.
3. Cache current chart data so checkbox changes can redraw the SVG locally.
4. Update `scripts/ui_static_check.py`.
5. Validate in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation against local `/ui` data-center market-data section.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: Added MA controls, latest-value display and CSS.
- Completed: Added moving-average calculation and SVG overlays.
- Completed: Added cached chart re-rendering for checkbox changes.
- Completed: Updated roadmap and static UI contract.
- Completed: Browser validation against `sec_000818`.
- Blocked: None.

## Dependencies

- Existing T-486 K-line panel.
- Existing `/api/market-data` endpoint.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: MA controls, MA helpers, SVG overlays, cached chart redraw and market-data wiring.
- `scripts/ui_static_check.py`: required MA IDs/functions.
- `tasks/todo.md`: added T-487.
- `docs/agent-handoffs/2026-06-26-T-487-kline-moving-average-system.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: UI static check with `required_ids=343`, `required_functions=122`, `node_check=passed`.
- Passed: Python compile check.
- Passed: Final handoff validation checked 58 markdown files.
- Passed: Browser validation against `sec_000818`.
- Passed: Initial `git diff --check`.

## Evidence

- Browser validation with `sec_000818`:
- Chart title: `sec 000818 K线`.
- Subtitle: `100 根 · 2026-01-23 至 2026-06-26 · A`.
- MA5: `13.44`.
- MA10: `13.04`.
- MA20: `13.31`.
- MA60: `15.36`.
- Polyline count with all MAs enabled: 5.
- Polyline count after disabling MA20: 4.
- Candle count: 100.
- SVG display: `block`; empty state display: `none`.
- Console error count: 0.

## Decisions

- Use MA5, MA10, MA20 and MA60 because they are common daily K-line review windows.
- Compute from local `close` values already returned by `/api/market-data`; no external data source is introduced.
- Keep the implementation in native SVG to match the existing no-extra-dependency K-line panel.

## Risks and Open Questions

- Sparse local market data will only show MA values after enough points exist for the selected window.
- This is a visual analysis aid only. It is not a trading signal engine.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Browser validation completed.
- [x] Final handoff validation passed.
- [x] Initial diff check passed.

## Next Steps

1. Keep the chart display-only unless a future task explicitly asks for drawing tools or signal alerts.
2. If users need more technical indicators, add them as optional overlays with the same local-only data boundary.
3. Consider mirroring this chart into the company intelligence page after selecting a company.

## Next Recommended Action

Open `/ui`, enter `sec_000818` in the data-center market-data panel, and use MA5/MA10/MA20/MA60 toggles to inspect trend overlays.
