# Handoff: T-481 Company Intelligence Visual Polish

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-481

## Objective

Improve the company intelligence page from a personal user's PM perspective. The page should feel less like an engineering console and more like a readable research workbench, while preserving all existing controls and contracts.

## Scope

- In scope: visual hierarchy, spacing, card/table treatment, advanced-section presentation, roadmap and handoff updates.
- Out of scope: backend APIs, data contracts, broker integration, automated trading, route redesign, removal of existing controls.

## Background

T-480 simplified the default company intelligence view by adding a personal research summary and folding advanced maintenance controls. The user then reported that the UI still looked rough, so this task focuses on PM-level visual polish rather than new functionality.

## Problem Statement

The page still carried too much visual weight from the original operations console. Metric boxes, tables, personal cards and folded maintenance sections needed clearer hierarchy, more consistent spacing and calmer surfaces.

## Expected Deliverables

- Improved visual hierarchy for the company intelligence first screen.
- More readable personal summary cards and system metric boxes.
- Cleaner table treatment with better spacing and scanability.
- Advanced maintenance sections that remain accessible but visually quieter.
- Static and browser acceptance evidence.

## Current Findings

- Existing DOM IDs and JavaScript functions are sufficient for the visual pass.
- The safest change surface is CSS plus one class on the company intelligence summary panel.
- The previous interaction acceptance suite can validate that advanced controls remain reachable.

## Proposed Work Plan

1. Apply a quiet light design system to shared primitives.
2. Improve company intelligence summary card, metric boxes, tables and advanced details styling.
3. Preserve all current DOM IDs and control locations.
4. Run static, handoff and browser validation.
5. Update roadmap and handoff status after validation.

## Validation Plan

- Run `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Run `python3 scripts/ui_static_check.py`.
- Run `python3 scripts/check_handoffs.py`.
- Run `git diff --check`.
- Start a current-code temporary service.
- Run `python3 scripts/ui_interaction_acceptance.py <base-url> --output-dir artifacts/ui-interaction-acceptance-personal-ui-polish`.
- Capture or inspect the page after the visual pass.

## Current State

- Completed: refreshed global light theme tokens, button hover/focus states, navigation active states and base panel spacing.
- Completed: restyled personal summary cards, system metric boxes, advanced `details` sections and tables for clearer scanability.
- Completed: static, handoff, browser acceptance and screenshot review.
- Not started: separate route/tab split for advanced maintenance.
- Blocked: None.

## Dependencies

- Existing company intelligence UI from T-480.
- Existing UI static and interaction acceptance scripts.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: CSS visual polish for company intelligence and shared workbench primitives.
- `tasks/todo.md`: added T-481 as the visual polish follow-up to T-480.
- `docs/agent-handoffs/2026-06-26-T-481-company-intelligence-visual-polish.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "personal investment research company intelligence dashboard professional quiet" --design-system -p "Company Intelligence"
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= python3 -c 'from app.server import serve; serve(port=8770)'
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8770 --output-dir artifacts/ui-interaction-acceptance-personal-ui-polish
```

Result:

- Passed: design-system reference query completed.
- Passed: `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Passed: `python3 scripts/ui_static_check.py`.
- Passed: `python3 scripts/check_handoffs.py`.
- Passed: `git diff --check`.
- Passed: browser interaction acceptance, 28/28 checks.
- Failed then fixed: first handoff validation, because this file lacked required template sections.

## Evidence

- UI static result so far: `status_labels=9`, `required_ids=300`, `required_functions=109`, `node_check=passed`.
- Browser acceptance result: `status=passed`, `failure_count=0`, `check_count=28`, output under `artifacts/ui-interaction-acceptance-personal-ui-polish`.
- Screenshot review: desktop and mobile viewport captures showed no obvious overlap, clipping or text overflow in the company intelligence first screen.

## Decisions

- Keep the UI quiet and utilitarian: white surfaces, restrained borders, blue as the primary action accent, and green/amber/slate only for semantic accents.
- Do not rename DOM IDs or remove advanced controls; this is a visual polish pass on top of T-480 simplification.
- Use stronger hierarchy in the personal cards and metric blocks instead of adding another explanatory text layer.

## Risks and Open Questions

- This remains a dense single-page app. If the page still feels busy after visual polish, the next PM-level improvement is a route split between personal research and maintenance operations.
- CSS changes touch shared primitives, so browser acceptance should cover the main UI flow before commit.

## Artifacts

- `artifacts/ui-interaction-acceptance-personal-ui-polish`: local-only browser acceptance evidence, not acceptable for non-local production release gates.
- `artifacts/ui-screenshots/company-intelligence-ui-polish-desktop-top.png`: local-only desktop screenshot review evidence.
- `artifacts/ui-screenshots/company-intelligence-ui-polish-mobile.png`: local-only mobile screenshot review evidence.

## Handoff Checklist

- [x] Visual polish implemented.
- [x] `tasks/todo.md` updated.
- [x] Static and handoff checks pass.
- [x] Browser acceptance passes.
- [x] T-481 marked DONE.

## Next Steps

1. Commit and push T-480/T-481 when ready.
2. If the page still feels dense after use, split advanced maintenance into a separate route or tab.

## Next Recommended Action

Commit and push the completed UI simplification and visual polish changes when ready.
