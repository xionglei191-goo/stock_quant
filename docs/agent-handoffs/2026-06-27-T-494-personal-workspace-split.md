# Handoff: T-494 Personal Workspace Split

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-494

## Objective

Split `/ui` from a flat engineering workbench into a default personal research desktop plus a backend maintenance mode. Preserve all existing tabs, DOM IDs, actions, API URLs, and payload contracts.

## Scope

- In scope: `/ui` navigation information architecture, personal/default mode, backend maintenance reachability, UI static contract, handoff and task status.
- Out of scope: API/schema changes, route URL changes, front-end file modularization, browser matrix automation, real broker integration, live trading, automatic order execution.

## Background

T-490 and T-491 reduced raw IDs and debugging output across the UI. T-493 added a data/source health center. T-494 now addresses the remaining product issue: the default UI still looked like an operations console because personal research and maintenance controls shared the same primary navigation.

## Problem Statement

Personal users need a default workbench focused on what to read and do next: company intelligence, graph, market chart, research conclusions, and paper-only feedback. They should not need to understand run, manifest, trace, scheduling, review queue, or governance concepts on first use, while advanced maintenance must remain available.

## Expected Deliverables

- Default personal navigation: 总览, 公司情报, 知识图谱, K 线行情, 研究结论, 模拟反馈.
- Backend maintenance navigation: 数据中台, 智能体协作, 兼容审批, 风控合规, 公司高级维护.
- Existing DOM/API contracts preserved.
- Static checks updated to prevent regression to flat debug navigation.

## Current Findings

- The existing `section[data-tab]` layout is large but stable; changing tab IDs would break static and browser acceptance.
- `ingestion` is mixed-use: K-line and source health are personal-useful, while disclosures, manual reference review, 13F, extraction, and schedules are backend maintenance.
- `search` is also mixed-use: the company summary is personal, while database build/import/review panels are maintenance.
- A Product/UI explorer agent independently recommended an in-page mode switch and preserving all existing selectors.

## Proposed Work Plan

1. Add a `个人研究 / 后台维护` mode switch in the existing `<nav>`.
2. Keep all original `data-tab` values and route behavior.
3. Add mode-aware tab activation so duplicate `data-open` buttons activate the visible group.
4. Mark backend-only panels with `maintenance-only` and hide them in personal mode.
5. Extend `scripts/ui_static_check.py` with workspace mode contract checks.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- Browser smoke for `/ui`: default personal mode, hidden maintenance panels, maintenance switch, duplicate tab activation, console error count 0.

## Risks

- Personal mode still ships the full single HTML file; T-498 should handle modularization.
- K-line and data health still live under the existing `ingestion` section for compatibility.
- Browser smoke must verify duplicate `data-open="ingestion"` and `data-open="search"` activate the correct visible button for the selected workspace mode.

## Dependencies

- Existing T-490/T-491 summary-first UI helpers and static contract checks.
- Existing T-493 data/source health UI panels.
- Existing `openTab` behavior and `data-open`/`data-tab` selectors.

## Blockers

- None for local T-494 completion.

## Handoff Checklist

- [x] Personal/maintenance workspace switch added.
- [x] Default personal navigation reduced to research-facing paths.
- [x] Backend maintenance paths remain reachable.
- [x] Existing tab IDs and API schemas preserved.
- [x] Static UI contract updated.
- [x] `tasks/todo.md` marked T-494 DONE.
- [x] Browser smoke completed.

## Evidence

- `app/static/index.html`: `workspace-switch`, `data-workspace-mode`, `maintenance-only`, `setWorkspaceMode`, and mode-aware `openTab`.
- `scripts/ui_static_check.py`: required snippets/functions include workspace mode contract.
- `tasks/todo.md`: T-494 status and completion bullets.
- `python3 scripts/ui_static_check.py`: passed after preserving legacy `复盘反馈` wording in help text.
- `python3 scripts/ui_browser_acceptance.py http://127.0.0.1:8011 --output-dir artifacts/t494-ui-browser-acceptance --timeout 30`: passed; desktop/mobile screenshots nonblank; missing text `[]`.
- DevTools T-494 smoke: passed; default visible nav was `总览, 公司情报, 知识图谱, K 线行情, 研究结论, 模拟反馈`; maintenance mode visible nav was `数据中台, 智能体协作, 兼容审批, 风控合规, 公司高级维护`; personal K-line path kept `#klineChart` and source health visible while hiding maintenance panels.

## Next Recommended Action

Proceed to T-495 real browser acceptance matrix if validation remains clean.
