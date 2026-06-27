# Handoff: T-488 K-line Cross-section Guard

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-488

## Objective

Prevent the K-line panel from rendering multi-security same-day market snapshots as a single-security time series.

## Scope

- In scope: public market-data UI, K-line render guards, default security loading, static UI contract, roadmap and handoff.
- Out of scope: backend market-data API behavior, data-source ingestion, corporate-action adjustment logic, broker or real-time market feeds.

## Background

The `/api/market-data` endpoint supports both filtered single-security history and unfiltered latest market-data browsing. When `security_id` is empty, the endpoint returns a multi-security latest-day cross-section. That is valid for a table, but invalid for a K-line time series.

## Problem Statement

The K-line panel could receive the empty-security response and draw different securities from the same date as if they were one security across time. This produced repeated x-axis dates and unrealistic price spikes such as `60.58 / 1.54`.

## Current Findings

- `/api/market-data?security_id=&limit=120` returns many securities for one date.
- `/api/market-data?security_id=sec_000670&limit=120` returns one security across 100 dates with a normal price range.
- The frontend needed a stronger guard between table data and chartable time-series data.

## Expected Deliverables

- Empty security input defaults to a sample single security before requesting data.
- K-line rendering rejects multi-security cross-sections.
- K-line rendering rejects single-day multi-row inputs.
- Static UI check covers the new guard behavior.
- Browser validation confirms normal x-axis dates and sane price range.

## Proposed Work Plan

1. Change the public market-data security input default to a real sample security.
2. Make `loadMarketData` normalize empty input to the same sample security.
3. Add chart guards for single-security and multi-date requirements.
4. Update static UI contract.
5. Validate in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation for empty security input and `sec_000670`.
- Browser direct render guard validation for multi-security cross-section rows.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: Default security input and load normalization updated.
- Completed: `renderKlineChart` now rejects multi-security and single-day multi-row data.
- Completed: Static UI contract updated.
- Completed: Browser validation for default single-security flow and cross-section rejection.
- Blocked: None.

## Dependencies

- Existing `/api/market-data` endpoint.
- Existing K-line panel from T-486 and MA system from T-487.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: K-line default security, `loadMarketData` normalization, render guards and empty-state messages.
- `scripts/ui_static_check.py`: static text snippets for K-line guard behavior.
- `tasks/todo.md`: added T-488.
- `docs/agent-handoffs/2026-06-26-T-488-kline-cross-section-guard.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: UI static check with `required_ids=343`, `required_functions=122`, `text_snippets=3`, `node_check=passed`.
- Passed: Python compile check.
- Passed: Browser validation for blank input fallback and cross-section guard.
- Passed: Final handoff validation checked 59 markdown files.
- Passed: Final diff check.

## Evidence

- Browser validation after service restart:
- Blank security input was normalized to `sec_000670`.
- Rendered chart title: `sec 000670 K线`.
- Subtitle: `100 根 · 2026-01-23 至 2026-06-26 · A`.
- Latest close: `7.60`.
- Range return: `-21.57%`.
- High/low: `11.23 / 7.02`.
- Date labels: `2026-01-23`, `2026-04-14`, `2026-06-26`.
- Candle count: 100.
- Cross-section guard test: 20 securities and 1 date produced empty state with subtitle `请选择单一证券后查看时间序列，当前结果是多证券横截面`.
- Console error count: 0.

## Decisions

- Keep the backend endpoint flexible because the table can still use broad market-data browsing.
- Enforce chartability in the UI renderer because a K-line chart has a stricter data shape than a market-data table.
- Use `sec_000670` as the default A-share sample because it reproduced the user-visible issue and has current local history.

## Risks and Open Questions

- The chart still depends on the local market-data store having enough rows for the selected security.
- If future UI adds a broad market heatmap, it should use a separate visualization rather than the K-line panel.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Browser validation completed.
- [x] Final handoff validation passed.
- [x] Final diff check passed.

## Next Steps

1. Keep broad market snapshots in table or future heatmap views, not the K-line panel.
2. If another chart is added for market breadth, require a different data-shape contract.
3. Continue using browser validation for visible chart changes.

## Next Recommended Action

Open `/ui`, clear the market-data security input, click load, and confirm it resolves to `sec_000670` with non-repeated date labels and sane price range.
