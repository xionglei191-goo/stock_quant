# Handoff: T-483 Obsidian Knowledge Graph View

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-483

## Objective

Make the knowledge graph page feel like an exploratory relationship graph rather than a table dashboard. A personal user should be able to open a company graph, quickly see the surrounding network, filter relationship types, and inspect adjacent nodes.

## Scope

- In scope: `app/static/index.html`, `scripts/ui_static_check.py`, `tasks/todo.md`, this handoff.
- Out of scope: external Neo4j/Qdrant sync, broker integration, automatic trading, backend schema changes, deleting existing table details.

## Background

The backend already exposes `/api/graph/query` with issuers, securities, industry chains, evidence, events, viewpoints, decisions, portfolio records and graph edges. The UI only rendered counts and tables, so the graph page did not provide the fast spatial exploration expected from an Obsidian-style graph view.

## Problem Statement

The user asked for a best-in-class relationship graph. The current page made users read tables to infer relationships, which is too slow for personal research triage.

## Current Findings

- The existing knowledge graph page had metrics and tables but no network canvas.
- `/api/graph/query` already returns enough relationship data to build a local graph without backend schema changes.
- The existing static UI contract should be extended rather than relaxed.

## Expected Deliverables

- A first-screen interactive graph explorer on the knowledge graph tab.
- Node search, relationship type filters and depth control.
- Drag, zoom, reset view and click-to-highlight behavior.
- Inspector side panel with node summary and adjacent relationships.
- Existing table views preserved as detail layers.
- Static UI contract updated and validation evidence recorded.

## Proposed Work Plan

1. Add graph explorer markup before the existing graph tables.
2. Add scoped CSS for graph canvas, filters, legend and inspector.
3. Build a client-side graph model from existing `/api/graph/query` payload sections.
4. Render a native SVG force layout with search, filter, depth, zoom, pan and node selection.
5. Update static UI contract and run validation.

## Validation Plan

- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- Browser validation against local `/ui` knowledge graph tab.

## Current State

- Completed: native SVG graph explorer added to the knowledge graph page.
- Completed: graph model builder maps existing `/api/graph/query` payloads into company, security, industry, event, evidence, research, decision, portfolio and risk nodes.
- Completed: filters, search, depth, reset, zoom/pan, node selection and inspector added.
- Completed: browser validation and final handoff status update.
- Blocked: None.

## Dependencies

- Running local app at `http://127.0.0.1:8000`.
- Existing `/api/graph/query` response shape.
- Existing static single-page UI in `app/static/index.html`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: added graph explorer markup, styling, graph model construction, SVG force layout, interactions and inspector.
- `scripts/ui_static_check.py`: added required graph explorer IDs/functions.
- `tasks/todo.md`: added DONE task entry for T-483.
- `docs/agent-handoffs/2026-06-26-T-483-obsidian-knowledge-graph-view.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "fintech investment research knowledge graph network explorer professional dashboard" --design-system -p "Company Intelligence Knowledge Graph"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
docker compose restart ai-quant-org
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: design-system query completed.
- Passed: UI static check with `required_ids=324`, `required_functions=115`, `node_check=passed`.
- Passed: Python compile check.
- Passed: local Compose app restarted.
- Passed: browser validation against `http://127.0.0.1:8000/ui`.
- Passed: graph loaded for `AAPL` with 90 visible nodes / 130 visible links from 130 total nodes / 306 total links.
- Passed: search/depth/filter interaction updated graph to 2 visible nodes / 2 visible links with no console errors.
- Pending: final handoff validation and diff check rerun after this update.

## Evidence

- UI static result: `required_ids=324`, `required_functions=115`, `node_check=passed`.
- Browser evidence: `/ui` knowledge graph tab loaded `AAPL`; `knowledgeGraphNodeCount=节点 90/130`, `knowledgeGraphLinkCount=关系 130/306`, `knowledgeGraphFocusLabel=焦点 issuer aapl`.
- Interaction evidence: searching `research`, setting depth to `1`, and disabling evidence filter changed the rendered graph to `节点 2/130`, `关系 2/306`; console error count was 0.

## Decisions

- Use a native SVG graph instead of adding a dependency so the static single-file UI remains local-first and easy to serve.
- Keep all previous graph tables below the explorer as detail and audit surfaces.
- Limit rendered graph size to 90 nodes and 140 links to keep first-screen exploration responsive.
- Treat the graph as research visualization only; it does not add execution or broker capabilities.

## Risks and Open Questions

- Native force layout is sufficient for current local graph sizes but may need Cytoscape.js or Sigma.js if graph density grows materially.
- Search and depth filters are client-side; future work could add backend graph expansion endpoints for very large graphs.

## Artifacts

- Pending browser validation screenshot if captured; local-only evidence, not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Implementation drafted.
- [x] UI static contract updated.
- [x] Browser validation completed.
- [x] Handoff validation passed.
- [x] Handoff marked DONE.

## Next Steps

1. Consider replacing the native layout with Cytoscape.js or Sigma.js only if graph density grows beyond the current local performance envelope.
2. Add server-side graph expansion if future watchlists require thousands of visible nodes.
3. Add saved graph layouts after users settle on preferred focus views.

## Next Recommended Action

Commit and push the T-483 graph explorer once final validation is reviewed.
