# Handoff: T-485 Knowledge Graph Readability

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-485

## Objective

Fix the dynamic knowledge graph readability issues reported by the user: nodes sticking to the outer edge, overlapping nodes, and unreadable/raw node names.

## Scope

- In scope: client-side graph layout, label policy, semantic node naming and validation evidence in `app/static/index.html`.
- Out of scope: backend graph API changes, new graph database integration, real trading or broker functionality.

## Background

T-483/T-484 added an Obsidian-style dynamic graph. In the AAPL graph, star-shaped relationships pushed many nodes to the canvas boundary, repeated viewpoint/event nodes overlapped, and raw IDs such as `vp_rr_*` made the graph hard to read.

## Problem Statement

The graph was technically dynamic but not yet product-quality: it behaved like a raw database visualization rather than a readable relationship map.

## Current Findings

- The initial force layout used strong repulsion and hard boundary clamping, causing nodes to stick to the outer edge.
- AAPL returns many same-type viewpoint/event nodes; rendering all of them as first-class labeled nodes creates visual noise.
- Some nodes are inferred only from edges, so type inference is required to avoid rendering companies/securities as generic evidence.

## Expected Deliverables

- No default edge sticking in the AAPL graph.
- No visible node overlap in the default AAPL graph.
- Fewer, more meaningful labels.
- Raw graph IDs converted into business labels where possible.
- Existing graph search/filter/depth/dynamic behavior preserved.

## Proposed Work Plan

1. Add semantic node/edge labeling helpers.
2. Infer node type from ID prefixes when nodes are only discovered through edges.
3. Limit visible nodes by type so repeated low-value nodes do not dominate.
4. Replace boundary-heavy force behavior with cluster centers, collision avoidance and soft boundaries.
5. Hide noisy labels by default and reveal details via selection/inspector.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation against local `/ui` knowledge graph tab using `AAPL`.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: graph semantic labels and edge labels added.
- Completed: inferred node type upgrades added.
- Completed: visible node caps by type added.
- Completed: cluster layout, collision avoidance and soft edge boundaries tuned.
- Completed: browser validation for AAPL layout.
- Blocked: None.

## Dependencies

- Existing T-483/T-484 graph explorer.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: label sanitization, type inference, node caps, force layout tuning and label visibility policy.
- `tasks/todo.md`: added T-485.
- `docs/agent-handoffs/2026-06-26-T-485-knowledge-graph-readability.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "knowledge graph force layout label collision dashboard" --design-system -p "Knowledge Graph Readability"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
docker compose restart ai-quant-org
```

Result:

- Passed: design-system query completed.
- Passed: UI static check with `required_ids=327`, `required_functions=118`, `node_check=passed`.
- Passed: Python compile check.
- Passed: local Compose app restarted.
- Pending: final handoff validation and diff check after this file is added.

## Evidence

- Browser validation for AAPL graph after 2.2 seconds of layout:
- Visible nodes: 29.
- Visible links: 85.
- Node overlap count: 0.
- Edge-sticking count using 100px margin: 0.
- Always-visible label count: 2, both `AAPL`.
- Motion remained active: `动态运行 · α 0.12`.

## Decisions

- Default graph should prioritize readability over showing every raw record.
- Repeated evidence/event/viewpoint nodes remain available as selectable nodes and table details, but no longer all carry always-visible labels.
- Type caps are client-side only and do not discard backend data.

## Risks and Open Questions

- If users need exhaustive graph inspection, a separate "show all raw nodes" mode may be useful.
- Future graph improvements could add aggregation nodes such as "20 research viewpoints" instead of individual dots.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Browser validation completed.
- [ ] Final handoff validation passed.
- [ ] Final diff check passed.

## Next Steps

1. Run final `python3 scripts/check_handoffs.py`.
2. Run final `git diff --check`.
3. Commit and push when the full worktree is ready.

## Next Recommended Action

Review the graph visually in `/ui` and decide whether to add an explicit "show all raw nodes" toggle later.
