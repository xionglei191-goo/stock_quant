# Handoff: T-491 UI Denoise Completion

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-491

## Objective

Complete the second-pass UI information denoise work across the remaining workbench pages so the default interface reads as a personal company intelligence and market research workspace.

## Scope

- In scope: `app/static/index.html`, `scripts/ui_static_check.py`, `tasks/todo.md`, and this handoff.
- Out of scope: backend API schema changes, new endpoints, real broker integration, live trading, deletion of traceability data.

## Background

T-490 converted the highest-visibility company intelligence, dashboard, graph, and market-data paths. The remaining pages still contained backend-style output: raw objects, `pre` JSON, run IDs, evidence IDs, replay IDs, source IDs, and manifest paths as primary UI content.

## Problem Statement

Personal users need conclusions, state, impact, evidence and next actions. Engineering identifiers and raw payloads should remain available for audit, but should not be the main reading surface.

## Current Findings

- `app/static/index.html` remains the main UI surface for these pages.
- Existing payloads already contain enough title, status, summary, count, date, and action fields to derive readable front-end summaries without backend changes.
- Several page sections were still writing raw objects directly into `pre` elements or using compact IDs as table primary text.

## Expected Deliverables

- Shared helper functions for readable object summaries, folded raw details, and actionable rows.
- Chokepoint, agent collaboration, approval, replay, data center, governance, and company maintenance pages use summary-first rendering.
- Raw JSON, run IDs, trace IDs, manifest paths, assertion IDs and relationship IDs are available in folded advanced trace sections.
- Static UI contract checks include the new helpers and core text snippets.
- Roadmap and handoff records updated.

## Proposed Work Plan

1. Add `renderReadableObjectSummary`, `renderAdvancedPre`, and `renderActionableRows`.
2. Replace raw `pre` writes on chokepoint, committee, replay, data center, governance and company maintenance paths.
3. Convert remaining major default tables from internal IDs to business labels, status, evidence counts and next actions.
4. Update `scripts/ui_static_check.py`.
5. Update `tasks/todo.md` and this handoff.
6. Validate statically and in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- Browser smoke at `http://127.0.0.1:8000/ui?ts=491`

## Current State

- Completed: Shared readable summary helpers added.
- Completed: Raw object and `pre` sections converted to summary plus folded trace on the remaining major pages.
- Completed: Several remaining visible ID-first tables were converted to business labels and traces.
- Completed: Static contract and roadmap updated.
- Completed: Browser smoke completed with console error check after refresh.
- Blocked: None.

## Dependencies

- Existing static UI.
- Existing API payloads.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: readable summary helpers, advanced trace rendering, actionable row helper, and second-pass UI denoise across remaining pages.
- `scripts/ui_static_check.py`: required helper and text-snippet checks for the T-491 UI contract.
- `tasks/todo.md`: added and marked T-491 as done.
- `docs/agent-handoffs/2026-06-26-T-491-ui-denoise-completion.md`: current handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
Browser smoke at http://127.0.0.1:8000/ui?ts=491
```

Result:

- Passed: `python3 scripts/ui_static_check.py` (`required_functions=142`, `required_ids=351`, `text_snippets=13`, `node_check=passed`).
- Passed: `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Passed: browser helper smoke and page refresh console check.
- Passed: final `python3 scripts/check_handoffs.py` and `git diff --check` in the closeout pass.

## Evidence

- Browser verified helper availability for `renderReadableObjectSummary`, `renderAdvancedPre`, `renderActionableRows`, and `renderAdvancedTrace`.
- Injected representative summaries into chokepoint conclusion, decision package, portfolio feedback, data schedule, company material inbox, and source review rows; each rendered a folded `.advanced-trace`.
- Verified raw HTML in trace data was escaped and did not create image elements.
- Verified K line SVG renders when `renderKlineChart(items)` receives typed OHLCV rows; period controls are present. The currently running local service did not expose a populated default K line dataset in the visible data-center tab, so API-backed K line data was not revalidated beyond empty-state behavior.
- Refreshed the page and confirmed browser console errors were `0`.

## Decisions

- Keep traceability data in folded advanced sections instead of deleting it, preserving auditability while improving personal-user readability.
- Do not modify backend payloads or API contracts; all readable labels are derived in the front end.
- Use business labels, counts, status labels, and next actions as default table content; use internal IDs only as button data attributes or folded trace payloads.

## Risks

- Some transient status messages still include trace IDs after user-triggered operations. They are not table primary content, but a future polish pass could hide them behind a global trace drawer.
- K line controls were smoke-tested with direct function injection because the current local service did not expose a populated default K line dataset in the visible data-center tab.
- The worktree contains unrelated pre-existing changes and handoff files from T-480 through T-490; they were not reverted.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Roadmap updated.
- [x] Browser smoke completed.
- [x] Final handoff validation passed.
- [x] Final diff check passed.

## Next Recommended Action

Continue with T-492 through T-503, starting with documentation/worktree release closure before adding the data-health and backend modularization work.
