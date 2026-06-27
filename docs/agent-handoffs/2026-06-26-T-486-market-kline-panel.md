# Handoff: T-486 Market Kline Panel

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-486

## Objective

Add a K-line/candlestick panel so personal users can inspect price action inside the system while reviewing company intelligence and graph relationships.

## Scope

- In scope: data-center market-data UI, native SVG candlestick rendering, static UI contract, roadmap and handoff.
- Out of scope: broker integration, live trading, real-time streaming market data, backend schema changes, external charting libraries.

## Background

The project already stores OHLCV fields in `MarketDataPoint` and exposes them via `/api/market-data`. The UI only showed a small table of close prices, which was not enough for personal research.

## Problem Statement

Users need to see the price trend without leaving the all-weather company intelligence system. A table of close prices is too limited for market context.

## Current Findings

- `/api/market-data` returns `open`, `high`, `low`, `close`, `adjusted_close`, `volume` and `as_of_date`.
- Existing `openSecurityContext` already routes clicked securities into the data-center market-data panel.
- A native SVG chart is sufficient and avoids adding a large dependency.

## Expected Deliverables

- K-line panel under the public market-data section.
- Candles, high/low wicks, close line, volume bars, grid and date labels.
- Latest close, range return, high/low and volume summary.
- `loadMarketData` updates both table and chart.
- Static contract updated.

## Proposed Work Plan

1. Add K-line chart DOM and styling.
2. Add `renderKlineChart` using local OHLCV points.
3. Wire `loadMarketData` and `addMarketData` to update the chart.
4. Update `scripts/ui_static_check.py`.
5. Validate in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation against local `/ui` data-center market-data section.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: SVG K-line chart added.
- Completed: metrics and empty state added.
- Completed: market-data loading wired to the chart.
- Completed: static UI contract updated.
- Pending: browser validation and final checks after local restart.
- Blocked: None.

## Dependencies

- Existing `/api/market-data` endpoint.
- Existing OHLCV fields in `MarketDataPoint`.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: K-line panel markup, styling, SVG renderer and market-data wiring.
- `scripts/ui_static_check.py`: required K-line IDs/function.
- `tasks/todo.md`: added T-486.
- `docs/agent-handoffs/2026-06-26-T-486-market-kline-panel.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "financial candlestick chart investment research dashboard" --design-system -p "Market Candlestick Panel"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
```

Result:

- Passed: design-system query completed.
- Passed: UI static check with `required_ids=335`, `required_functions=119`, `node_check=passed`.
- Passed: Python compile check.
- Passed: browser validation against `sec_000818`.
- Passed: handoff validation checked 57 markdown files.
- Passed: `git diff --check`.

## Evidence

- Browser validation with `sec_000818`:
- Chart title: `sec 000818 K线`.
- Subtitle: `100 根 · 2026-01-23 至 2026-06-26 · A`.
- Latest close: `13.97`.
- Range return: `-34.32%`.
- High/low: `25.90 / 11.77`.
- Latest volume: `95,878,162`.
- SVG display: `block`; empty state display: `none`.
- Candle count: 100.
- Console error count: 0.

## Decisions

- Use native SVG instead of an external charting library to keep the static UI local-first.
- Use the existing market-data endpoint with `limit=120` to provide enough candles for trend reading.
- Keep the chart in the data-center market-data section first; future work can mirror it in company intelligence if needed.

## Risks and Open Questions

- Sparse local market data will render few candles until the daily ingestion/backfill has populated more history.
- The chart is display-only; it does not provide drawing tools or technical indicators yet.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Browser validation completed.
- [x] Final handoff validation passed.
- [x] Final diff check passed.

## Next Steps

1. Consider mirroring the K-line panel into the company intelligence page after selecting a company.
2. Add optional moving averages or volume average lines if users need technical context.
3. Keep the current chart display-only unless a future task explicitly asks for drawing tools.

## Next Recommended Action

Open `/ui`, click a security or enter `security_aapl_us` in the data-center market-data panel, and confirm the K-line SVG renders candles and metrics.
