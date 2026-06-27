# Handoff: T-495 Real Browser Acceptance Matrix

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI, PM / Release Coordination
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-495

## Objective

Upgrade UI acceptance from static checks to a local real-browser matrix for the personal company intelligence workbench. The matrix must cover the key user paths that T-490 through T-494 made visible: personal default navigation, source health, K-line interactions, company intelligence, graph details, empty states, and advanced trace escaping.

## Scope

- In scope: new local-only browser matrix script, validator regression, task status, and handoff evidence.
- Out of scope: production cross-browser evidence, new backend API schemas, database migrations, broker integration, live trading, automatic order execution.

## Background

T-493 added source health summaries and T-494 split the UI into personal and maintenance workspaces. Static checks were no longer enough because the default personal workbench depends on rendered DOM state, button interactions, K-line SVG output, graph node clicks, and HTML escaping behavior.

## Problem Statement

The project needed a repeatable browser gate that proves the main research workbench works end to end on this machine and fails with scenario-level diagnostics when a visible path breaks. The artifact must remain explicitly local-only so it cannot be confused with non-local production release evidence.

## Expected Deliverables

- A browser acceptance script covering:
  - personal workspace default navigation
  - source health center
  - A-share sample K-line path
  - real K-line API load with period switch, zoom, and pan
  - AAPL company intelligence readable summary
  - unknown ticker actionable empty state
  - knowledge graph node detail
  - advanced trace HTML escaping
- Matrix output with desktop and mobile viewports, console error count, scenario diagnostics, and local-only boundary flags.
- Focused regression that locks required T-495 scenarios and the local-only artifact boundary.

## Current Findings

- The existing `scripts/ui_browser_acceptance.py` verifies basic rendered text and screenshots, but not scenario-level interactions.
- The existing `scripts/ui_interaction_acceptance.py` provides useful DevTools helpers that can be reused without adding Playwright as a new dependency.
- The existing `scripts/ui_cross_browser_matrix_check.py` is still the right checker for production-style matrix shape; T-495 uses it with `--required-browser-family-count 1` because this artifact is local-only Chromium evidence.
- A-share local data may be absent, so the T-495 A-share scenario verifies the `sec_000670` path does not crash and reaches either a K-line state or clear no-data state. The real OHLCV load, period switch, zoom, and pan are verified through seeded `security_demo_us` public EOD data.

## Proposed Work Plan

1. Add a focused `scripts/ui_research_workbench_matrix.py` script that launches headless Chromium through the existing DevTools helper layer.
2. Seed demo data from the UI, then run all required scenarios on desktop and mobile viewports.
3. Persist a JSON matrix artifact under `artifacts/t495-ui-research-workbench-matrix/`.
4. Add a validator regression in `tests/test_system.py`.
5. Mark T-495 as DONE only after the real-browser matrix and local matrix checker pass.

## Validation Plan

- `python3 scripts/ui_research_workbench_matrix.py http://127.0.0.1:8012 --output-dir artifacts/t495-ui-research-workbench-matrix --timeout 60`
- `python3 scripts/ui_cross_browser_matrix_check.py artifacts/t495-ui-research-workbench-matrix/ui-research-workbench-matrix.json --required-browser-family-count 1`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_ui_research_workbench_matrix_validator_requires_t495_scenarios_and_local_boundary tests.test_system.SystemServiceTests.test_ui_cross_browser_matrix_validator_requires_families_viewports_and_text`
- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/security_check.py .`

## Risks

- This is Chromium-only local evidence. It does not replace the production cross-browser release gate.
- The matrix seeds local demo state and writes local market data points; repeated runs tolerate deterministic conflicts.
- A-share path coverage is a no-crash/no-data-state check unless local A-share EOD rows are present.

## Dependencies

- T-493 data/source health UI and APIs.
- T-494 personal/maintenance workspace mode.
- Existing DevTools utilities in `scripts/ui_interaction_acceptance.py`.
- Existing matrix shape checker in `scripts/ui_cross_browser_matrix_check.py`.

## Blockers

- None for local T-495 completion.

## Handoff Checklist

- [x] Real-browser matrix script added.
- [x] Required T-495 scenarios locked in script-level contract.
- [x] Desktop and mobile viewports covered.
- [x] Local-only artifact boundary recorded.
- [x] Focused regression added.
- [x] Existing cross-browser matrix checker accepts the local matrix with a one-family gate.
- [x] `tasks/todo.md` marked T-495 DONE.

## Evidence

- `scripts/ui_research_workbench_matrix.py`: local-only Chromium scenario matrix.
- `tests/test_system.py`: `test_ui_research_workbench_matrix_validator_requires_t495_scenarios_and_local_boundary`.
- `artifacts/t495-ui-research-workbench-matrix/ui-research-workbench-matrix.json`: generated local-only evidence, not acceptable for non-local release gates.
- Browser matrix result: 16 checks passed across desktop and mobile; failure count 0; console error count 0 for each scenario.
- Local matrix checker result: passed with one browser family, desktop/mobile viewports, and required UI text.

## Next Recommended Action

Proceed to T-496 conclusion realization and paper-only feedback scoring, using the T-495 matrix as the UI regression gate for visible research workbench paths.
