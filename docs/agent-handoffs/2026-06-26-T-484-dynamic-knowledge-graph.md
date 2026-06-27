# Handoff: T-484 Dynamic Knowledge Graph

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-484

## Objective

Make the Obsidian-style knowledge graph dynamic instead of a one-time static layout. Users should see a live force-directed graph, pause it, resume it, drag nodes to fixed positions, and release fixed nodes.

## Scope

- In scope: `app/static/index.html`, `scripts/ui_static_check.py`, `tasks/todo.md`, this handoff.
- Out of scope: backend graph API changes, external graph databases, broker integration, automatic trading.

## Background

T-483 added a relationship graph explorer. It rendered nodes and edges from `/api/graph/query`, but node positions were computed synchronously and then stayed still.

## Problem Statement

The user clarified that the graph should be dynamic. A static layout does not match the expected Obsidian-like graph behavior.

## Current Findings

- Existing graph rendering is native SVG, so dynamic behavior can be added with `requestAnimationFrame`.
- Current graph sizes are small enough for local client-side simulation with 90 visible nodes and 140 visible links.
- The static UI contract needed new IDs/functions for dynamic controls.

## Expected Deliverables

- Continuous force-directed graph motion.
- Pause/resume dynamic simulation.
- Drag nodes to fixed positions.
- Release fixed nodes back into the simulation.
- Motion status visible in the graph stats row.
- Static contract and validation evidence updated.

## Proposed Work Plan

1. Add dynamic state for alpha, frame id, cached positions and fixed node ids.
2. Replace one-time layout with seeded layout plus per-frame force ticks.
3. Update SVG positions per frame without rebuilding DOM.
4. Add pause/resume and release controls.
5. Validate in browser that node positions change over time and pause stops movement.

## Validation Plan

- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- Browser validation against local `/ui` knowledge graph tab.

## Current State

- Completed: dynamic simulation code added.
- Completed: pause/resume and release controls added.
- Completed: drag-to-fix behavior added.
- Completed: browser validation and final status update.
- Blocked: None.

## Dependencies

- Running local app at `http://127.0.0.1:8000`.
- Existing T-483 graph explorer.
- Existing `/api/graph/query` response shape.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: dynamic graph state, force simulation, SVG frame updates, pause/resume, drag-to-fix, release fixed nodes.
- `scripts/ui_static_check.py`: static contract for dynamic graph controls and functions.
- `tasks/todo.md`: added T-484.
- `docs/agent-handoffs/2026-06-26-T-484-dynamic-knowledge-graph.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "dynamic force directed knowledge graph fintech dashboard interaction" --design-system -p "Dynamic Knowledge Graph"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
docker compose restart ai-quant-org
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: design-system query completed.
- Passed: UI static check with `required_ids=327`, `required_functions=118`, `node_check=passed`.
- Passed: Python compile check.
- Passed: local Compose app restarted.
- Passed: handoff validation checked 55 markdown files.
- Passed: `git diff --check`.
- Passed: browser validation against `/ui` knowledge graph tab.

## Evidence

- Browser validation loaded `AAPL` graph with 90 visible nodes and 130 visible links.
- Dynamic evidence: first sampled node moved from `translate(443.0 338.5)` to `translate(443.1 339.0)` while dynamic mode was running.
- Pause evidence: after clicking pause, the same node remained at `translate(443.1 339.0)` across two samples.
- Resume evidence: after clicking continue, the node moved again to `translate(442.8 339.0)`.
- Console error count during validation: 0.

## Decisions

- Keep the implementation dependency-free and native SVG.
- Update SVG attributes per frame rather than rebuilding DOM on every animation tick.
- Keep a pause button because constant motion can distract during reading.
- Preserve user-dragged node positions until reset or release.

## Risks and Open Questions

- Very dense future graphs may need a dedicated graph library or web worker simulation.
- Continuous animation should be checked on lower-end machines if the visible node cap is raised.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation drafted.
- [x] UI static contract updated.
- [x] Browser validation completed.
- [x] Handoff validation passed.
- [x] Handoff marked DONE.

## Next Steps

1. Watch graph performance if the visible node/link caps are increased.
2. Consider adding a reduced-motion preference toggle if users find continuous motion distracting.
3. Consider persisting manual node positions per issuer after users settle on saved graph views.

## Next Recommended Action

Commit and push the dynamic graph changes after final diff review.
