# Handoff: T-489 K-line Interaction and Period Switch

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-489

## Objective

Add standard K-line chart interactions for personal research: drag-to-pan, zoom in/out, reset, and day/week/month/year period switching.

## Scope

- In scope: static UI K-line controls, SVG chart windowing, local OHLCV period aggregation, static UI contract, roadmap and handoff.
- Out of scope: external charting libraries, backend aggregation APIs, live streaming, drawing tools, trading signals.

## Background

T-486 added the SVG K-line panel, T-487 added moving averages, and T-488 fixed cross-section misuse. The chart still lacked standard interaction behaviors expected by users reading market data.

## Problem Statement

A fixed K-line viewport is hard to inspect. Users need to zoom into recent candles, drag backward through history, reset the view, and switch between common periods.

## Current Findings

- Existing `/api/market-data` can return enough daily rows for local aggregation when queried with a larger limit.
- The current SVG renderer can be extended with local state instead of adding a chart dependency.
- Weekly/monthly/yearly bars can be generated from daily OHLCV with open from first row, close from last row, high/low extrema, and summed volume.

## Expected Deliverables

- Period controls: day, week, month, year.
- Zoom in, zoom out and reset controls.
- Drag-to-pan and wheel-to-zoom on the SVG chart.
- Window state display.
- Static UI contract updated.
- Browser validation of period switching and interactions.

## Proposed Work Plan

1. Add chart tool controls and styles.
2. Add `klineViewState` for period, offset, window size and dragging state.
3. Add local OHLCV normalization and period aggregation helpers.
4. Render only the visible window after aggregation.
5. Wire period buttons, zoom buttons, reset, wheel and pointer drag.
6. Validate in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation for day/week/month/year switching.
- Browser validation for zoom in/out, reset, drag-pan and wheel zoom.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: UI controls and CSS added.
- Completed: Period aggregation helpers added.
- Completed: View window, zoom, reset, drag-pan and wheel zoom wired.
- Completed: Static UI contract and roadmap updated.
- Completed: Browser validation for period switching, zoom, drag-pan and reset.
- Blocked: None.

## Dependencies

- Existing K-line chart from T-486.
- Existing moving-average overlay from T-487.
- Existing cross-section guard from T-488.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: K-line controls, styles, aggregation, windowing and interaction events.
- `scripts/ui_static_check.py`: required controls, helper functions and interaction text.
- `tasks/todo.md`: added T-489.
- `docs/agent-handoffs/2026-06-26-T-489-kline-interaction-periods.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "financial candlestick chart dashboard interaction zoom pan period switch" --design-system -p "Kline Interaction Panel"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: design-system query completed.
- Passed: UI static check with `required_ids=351`, `required_functions=133`, `text_snippets=5`, `node_check=passed`.
- Passed: Python compile check.
- Passed: Browser validation for day/week/month/year switching.
- Passed: Browser validation for zoom in/out, drag-pan and reset.
- Passed: Final handoff validation checked 60 markdown files.
- Passed: Final diff check.

## Evidence

- Browser validation with `sec_000670`:
- Day: `日线 · 80/100 根 · 2026-03-02 至 2026-06-26 · A`, 80 candles.
- Week: `周线 · 22/22 根 · 2026-01-23 至 2026-06-26 · A`, 22 candles.
- Month: `月线 · 6/6 根 · 2026-01-23 至 2026-06-26 · A`, 6 candles.
- Year: `年线 · 1/1 根 · 2026-01-23 至 2026-06-26 · A`, 1 candle.
- Zoom in on day view changed the window from 80 to 58 candles.
- Drag-pan after zoom changed offset from 0 to 7 and moved visible range from `2026-04-01 至 2026-06-26` to `2026-03-23 至 2026-06-16`.
- Reset returned offset to 0 and day window to 80 candles.
- Console error count: 0.

## Decisions

- Use native SVG interaction to avoid introducing a heavy dependency.
- Use daily local OHLCV as source of truth; weekly/monthly/yearly bars are derived locally.
- Increase market-data fetch limit to 1000 for chart history, while keeping the table display capped to 120 rows.

## Risks and Open Questions

- Aggregated period quality depends on daily data completeness.
- More advanced chart features such as crosshair, indicators and drawing tools remain future work.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Browser validation completed.
- [x] Final handoff validation passed.
- [x] Final diff check passed.

## Next Steps

1. Keep future indicators as optional overlays using the same local OHLCV boundary.
2. Add crosshair/tooltip as a separate task if detailed candle inspection is needed.
3. Preserve browser validation for every visible chart interaction change.

## Next Recommended Action

Open `/ui`, load `sec_000670`, switch periods and use zoom/drag controls to confirm the chart behaves like a normal research K-line.
