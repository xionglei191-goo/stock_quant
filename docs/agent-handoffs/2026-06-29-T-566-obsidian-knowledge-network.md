# Handoff: T-566 Obsidian Knowledge Network

## Metadata

- Task ID: T-566
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-30
- Branch/worktree: main

## Status

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-06-30
- Last agent: Codex
- Branch/worktree: main

## Objective

Upgrade the knowledge graph from a company-centered visualization into an Obsidian-style explorable knowledge network. The target behavior is community-aware layout, progressive node expansion, readable labels, and local/global graph exploration without losing the existing audit-oriented graph data.

## Scope

- In scope: `/ui` knowledge graph rendering, client-side graph model, layout, progressive expansion, labels, roadmap and handoff state.
- Out of scope: broker/trading integration, backend graph schema migration, replacing `/api/graph/query`, production release evidence.

## Background

T-483 introduced the first graph view, T-484 made it dynamic, and T-485 improved readability. User review on 2026-06-29 showed the result still did not meet Obsidian Graph View expectations because the graph remained visually centered on one issuer and lacked progressive exploration.

## Problem Statement

The graph currently exposes relationship data, but users need a navigable knowledge network: meaningful clusters, visible expansion paths, readable labels, and local exploration without losing the larger graph context.

## Expected Deliverables

- Community-aware graph model.
- Weighted force layout with reduced starburst behavior.
- Click-to-expand hidden neighbors.
- Better label density and hidden-neighbor hinting.
- Path-based next-hop neighborhood walking.
- Explicit graph viewport controls for zoom, fit, and focus centering.
- Pinned exploration trail controls for preserving the current walk.
- Runtime performance status and acceptance thresholds for SVG graph viability.
- Saved subgraph restore flow for continuing prior exploration.
- Multi-symbol browser acceptance proving the graph is not AAPL-only.
- Relationship-filter browser acceptance for filtered network exploration.
- Repeatable validation evidence for AAPL graph rendering.

## Current State

- Completed:
  - `app/static/index.html` graph nodes now carry `community`, `hiddenNeighborCount`, and edge `weight`.
  - Default graph filtering keeps a readable high-value summary instead of rendering every candidate node.
  - Clicking a node records it in `expandedIds` and re-renders its neighbors into the visible model.
  - Nodes with hidden neighbors render a subtle outer halo.
  - Layout now uses community centers, weighted edge distances, stable hash-based initial spread, stronger collision avoidance, label overlap avoidance, and a 640px graph canvas.
  - Knowledge graph now has explicit local/global graph modes; local graph is the readable default, global graph allows a denser overview.
  - Visible community labels summarize relationship clusters such as company/security and event/evidence.
  - Community labels now include density, relationship strength, and strong-edge ratio.
  - `scripts/ui_graph_layout_acceptance.py` measures graph layout quality through headless Chrome and supports local/global scopes.
  - Manual node placement is persisted in `localStorage` by focus, mode, depth, and enabled relation groups.
  - A "clear layout" control resets persisted manual placement for the current graph context.
  - Path exploration panel can set the selected node as path start/end, compute the shortest visible path, and highlight path nodes/links.
  - Path steps expose next-hop neighbor buttons so users can continue walking from the highlighted path without losing context.
  - View controls now expose zoom out, zoom in, fit visible graph, and center focus actions; the graph status line includes the current zoom ratio.
  - Path panel now includes pin current, save path, clear trail, and a clickable exploration trail list.
  - Graph animation now samples FPS, average frame time, and worst frame time; the status line includes FPS and frame duration.
  - `scripts/ui_graph_layout_acceptance.py` now enforces `min_fps` and `max_frame_ms` thresholds.
  - Subgraph save/restore persists trail, fixed nodes, expanded nodes, path endpoints, scope, depth, and transform under `ai_quant_graph_subgraph:{focus}`.
  - `scripts/ui_graph_multi_symbol_acceptance.py` runs AAPL local, NVDA local, 600519 local, and AAPL global browser cases.
  - The layout acceptance now uses the current graph `focusId` instead of hard-coded `issuer_aapl`, so path/trail checks work for non-AAPL symbols.
  - `scripts/ui_graph_relationship_filter_acceptance.py` runs relationship-filtered browser cases for listed-security and institution-coverage networks across AAPL, NVDA, and 600519.
  - `/api/graph/query` now derives industry semantic graph edges from existing `CompanyPosition + IndustryChain.edges` records without adding schema or persisted fact relationships.
  - Graph query returns `INDUSTRY_PEER`, `INDUSTRY_UPSTREAM_OF`, and `INDUSTRY_DOWNSTREAM_OF` edges with raw `relationship_type` values `industry_peer`, `upstream_of`, and `downstream_of` when local chain-position data exists.
  - Direction-level `chain_node_id` filtering now matches peer shared nodes, upstream source nodes, or downstream target nodes so recommended graph entries do not accidentally filter out the intended direction network.
  - `scripts/ui_graph_layout_acceptance.py` relationship-filter checks now count both persisted `company_relationships[].relationship_type` and derived `edges[].relationship_type`, so future browser cases can verify industry semantic edges.
  - `query_graph` industry semantic edges now work when the UI also sends `security_id`; only the focus company position is scoped to the selected security, while peer/upstream/downstream related company positions remain eligible.
  - `scripts/ui_graph_relationship_filter_acceptance.py` now prepares a controlled industry fixture through public APIs and runs 9 browser cases, including AAPL `industry_peer`, `upstream_of`, and `downstream_of`.
  - `scripts/graph_acceptance_fixture.py` now owns the public-API fixture preparation so the browser matrix and manual default-service preparation can reuse the same data setup.
  - Local graph default depth is now three hops, and the first render seeds cross-community expansions before layout so the default view is less issuer-star centered.
  - Local graph cropping now prioritizes pinned focus, community minimums, industry nodes, and hidden-neighbor hubs before filling remaining type budgets.
  - `scripts/ui_graph_layout_acceptance.py` now measures visible communities and industry-node coverage, so the Obsidian-style default is gated on multi-community shape rather than only total node/link count.
  - Plain symbol graph loading now defaults to issuer-level company knowledge neighborhoods instead of automatically carrying the resolved primary `security_id`; explicit security scoping remains available from security/company-position/relationship entry points.
  - `scripts/ui_graph_layout_acceptance.py` can now assert expected or forbidden filter chips, which locks the default AAPL graph against accidental return to a security-filtered first screen.
  - The Obsidian seed now adds a local seed source, company note documents, company events, structured research reports, and report viewpoints, so the graph contains document/event/opinion nodes in addition to industry and holder relationships.
  - `scripts/ui_graph_layout_acceptance.py` now measures raw knowledge nodes and visible knowledge node types, proving the rendered graph includes Obsidian-like note/event/viewpoint material instead of only relationship edges.
  - Node inspector actions now include `graphFocusSelected`, which turns the selected visible node into the local graph focus, adds it to the exploration trail, expands it, and rerenders the neighborhood.
  - `scripts/ui_graph_layout_acceptance.py` now supports `--check-focus-switch` to prove a visible knowledge node can become the local graph center in the browser.
  - Focus history and `graphBackFocus` now make focus switching reversible. The path panel renders recent focus nodes, and the browser acceptance verifies that a user can switch from the company to a knowledge node and then return to the prior company focus.
  - `/api/graph/knowledge-network/readiness` and `scripts/graph_knowledge_network_readiness.py` now audit whether the current local graph has enough real data density for Obsidian-style exploration, including layer coverage, community sources, cross-layer links, edge count, seed dependency, and concrete next backfill actions.
  - `scripts/backfill_knowledge_network_evidence.py` now provides an API-only evidence backfill path for a knowledge-network issuer. It defaults to dry-run and, with `--execute`, extracts Evidence from graph documents that do not yet have evidence rows, then records readiness before/after.
  - `/api/graph/knowledge-network/evidence-links/backfill` and `scripts/backfill_knowledge_network_evidence_links.py` now backfill existing document Evidence ids onto `CompanyEvent`, `CompanyRelationship`, and `ReportViewpoint` provenance links. This turns document evidence into event/viewpoint evidence graph edges without promoting opinions to facts.
  - 2026-06-30 natural-layout correction: local pruning now preserves focus, expanded-neighborhood nodes, community skeleton nodes, cross-community bridges, and key knowledge nodes before filling type budgets.
  - 2026-06-30 natural-layout correction: issuer/security priority was lowered while event/evidence/research/portfolio priority was raised, so the first screen is less likely to collapse into a company starburst.
  - 2026-06-30 natural-layout correction: layout now uses weaker global centering, wider community centers, and local anchors for expanded nodes; clicked-node neighbors gather around the clicked node instead of being pulled into AAPL spokes.
  - 2026-06-30 natural-layout correction: single click only selects and expands; focus switching remains explicit through double-click or `graphFocusSelected`.
  - 2026-06-30 natural-layout correction: `scripts/ui_graph_layout_acceptance.py` now measures visible-neighbor growth after node click, so expansion must increase the clicked node's visible neighborhood or grow the graph.
  - 2026-06-30 second correction: single click now directly switches the graph focus to the clicked node, expands it, and rebuilds the radial layout around that node.
  - 2026-06-30 second correction: layout seeding now uses focus-centered radial distance rings rather than rectangular community targets; non-fixed stale positions are cleared on focus change so old localStorage coordinates do not preserve the previous rectangle.
  - 2026-06-30 second correction: `scripts/ui_graph_layout_acceptance.py` now fails if clicked-node focus switching does not happen.
  - 2026-06-30 third correction: real mouse clicks were being swallowed because node `pointerdown` always set `suppressNextNodeClick=true` before the real `click` event. The fix only suppresses click after movement exceeds a drag threshold.
  - 2026-06-30 third correction: browser acceptance now dispatches `pointerdown`, `pointerup`, then `click`, so it covers the real press/release path instead of bypassing pointer handlers with a synthetic click only.
  - 2026-06-30 fourth correction: community labels are now clickable exploration entries. Clicking a label picks a representative node in that community and switches focus to it.
  - 2026-06-30 fourth correction: community label text no longer uses `pointer-events: none`; the previous setting let real clicks pass through to the SVG background, which made the graph appear to light up during press and then return to AAPL.
  - 2026-06-30 fourth correction: acceptance now includes a `community_click` assertion, and an additional CDP-native `Input.dispatchMouseEvent` probe verified the real browser input path.
  - 2026-06-30 fifth correction: node click focus switching no longer depends on node-level `pointerup`; SVG-level `pointerup` now handles `pendingNodePointer` and `elementFromPoint` as a fallback because pointer capture is set on the SVG.
  - 2026-06-30 fifth correction: all focus switching now goes through `switchKnowledgeGraphFocusNode()`, which synchronizes `focusId`, `selectedId`, path start, expansion, trail, and layout reset.
  - 2026-06-30 sixth correction: graph labels now disambiguate same-ticker issuer and security nodes. Issuers render as `<ticker> · 公司`; securities render as `<ticker> · <exchange/market>`.
  - 2026-06-30 seventh correction: default graph labels now translate local seed/internal IDs (`doc_/hold_/pos_/srr_/vp_/event_/rel_...obsidian`) and raw relationship enums (`RELATIONSHIP_*`, `VIEWPOINT_ON_COMPANY`, `HOLDS_SECURITY`, `POSITIONED_AS`, etc.) before they reach the canvas, inspector, and graph relationship table. Folded trace JSON still preserves raw provenance.
  - 2026-06-30 seventh correction: `graphRef()`, `userEntityLabel()`, `relationshipTypeDisplayLabel()`, and inspector neighbor rows now share the graph-readable label path; chain node IDs with colon suffixes use the suffix node (`equipment`, `foundry`, etc.) instead of being collapsed into the broader `ai_device` label.
- In progress:
  - 2026-06-30 AAPL natural-expansion browser acceptance passes on current-code port 55551 with 35 measured DOM nodes before click, 88 links, 4 visible communities, 12 industry nodes, visible event/research/evidence node types, 5 overlap pairs, 0 near-edge nodes, and performance around 60 FPS / 1.1ms average frame time. Clicking `pos_obsidian_asml_equipment` increased visible neighbors from 1 to 3, nodes from 35 to 36, and links from 87 to 88.
  - 2026-06-30 AAPL click-focus browser acceptance passes on current-code port 55552. Clicking `pos_obsidian_asml_equipment` changed `focusId` from `issuer_aapl` to `pos_obsidian_asml_equipment`, increased visible neighbors from 1 to 3, kept near-edge nodes at 0, reduced overlap pairs to 0, and ran around 60 FPS / 1.3ms average frame time.
  - 2026-06-30 real-pointer click-focus browser acceptance passes after restarting 55552 with the pointer-threshold fix. The test now uses the real event chain and still changes `focusId` from `issuer_aapl` to `pos_obsidian_asml_equipment`, with near-edge nodes 0, overlap pairs 0, and around 60 FPS / 1.5ms average frame time.
  - 2026-06-30 native community-label click proof passes on current-code port 55552. A CDP `Input.dispatchMouseEvent` click on the `industry` community label changed focus from `issuer_aapl` to `chain_obsidian_ai_device_network`, and the inspector title became `AI 端侧设备与算力产业链`.
  - 2026-06-30 updated layout acceptance passes with `community_click`: after the scripted graph walk, clicking the industry community label changes focus from `pos_obsidian_asml_equipment` to `chain_obsidian_ai_device_network:accelerator`.
  - 2026-06-30 SVG pointerup fallback proof passes on current-code port 55552. CDP-native click on `event_obsidian_aapl_on_device_ai` changes focus from `issuer_aapl` to the event node; a subsequent freshly located click on the `industry` community label changes focus to `chain_obsidian_ai_device_network:edge_device`, with `selectedId` matching `focusId`.
  - 2026-06-30 label-disambiguation proof passes on current-code port 55552. Browser state shows `issuer_aapl` as `AAPL · 公司` and `security_aapl_us` as `AAPL · NASDAQ`.
  - 2026-06-30 default-label cleanup proof passes on current-code port 55552. A headless Chromium DOM probe found no default-visible `doc/hold/pos/srr/vp/event/rel ... obsidian`, `RELATIONSHIP`, `VIEWPOINT_ON_COMPANY`, or `product strategy` text in graph node labels, edge labels, community labels, inspector text, or graph relationship rows.
  - 2026-06-30 label-cleanup layout acceptance passes on current-code port 55552 after reseeding 49 local Obsidian records. It measured 35 DOM nodes, 88 links, 4 visible communities, 12 industry nodes, 0 overlap pairs, 0 near-edge nodes, click focus/expansion from `issuer_aapl` to `pos_obsidian_asml_equipment`, and community-label focus to `chain_obsidian_ai_device_network:foundry`.
  - Relationship-filter matrix passes with 10/10 cases across AAPL, NVDA, and 600519, including listed-security, institution-coverage, industry-peer, upstream-of, downstream-of, and Vanguard holder cases.
- Not started:
  - Canvas/WebGL or virtualization for larger graphs.
- Blocked:
  - Not blocked.

## Current Findings

- AAPL graph can contain more raw relations than a single SVG viewport can readably show.
- Rendering 88 nodes increased coverage but caused many overlaps.
- A local 36-39 node default summary with progressive expansion is currently a better tradeoff for readability.
- The repeatable layout gates now pass for local readable exploration and global overview.
- Path next-hop controls now provide a concrete neighborhood walking route from highlighted paths.
- Explicit viewport controls make the graph browsable without relying on hidden wheel/drag gestures.
- Exploration trail controls preserve the user's current walk, which makes iterative graph exploration less transient.
- Current AAPL local/global scopes are still within the SVG performance threshold; Canvas/WebGL is a measured fallback, not an immediate requirement.
- Saved subgraphs make a graph walk resumable across local UI state resets without changing backend graph contracts.
- Matrix acceptance exposed and fixed an AAPL-specific test assumption; graph exploration checks now follow the loaded focus node.
- The graph query code exposes industry peer/upstream/downstream networks when `CompanyPosition + IndustryChain` data exists, including UI-driven queries that carry both `issuer_id` and `security_id`.
  - A controlled browser fixture now proves industry peer/upstream/downstream filters end to end; long-lived local production sample data for AAPL/NVDA/600519 still needs to be backfilled outside the fixture.
- The latest user screenshot still looked short of Obsidian because the default view was visually centered on AAPL, only showed a few relationship communities, and compressed most business meaning into a starburst. The remaining gap is driven by three layers: default query scope still carries company/security focus filters, seed/production graph data is thinner than an Obsidian vault-scale graph, and the SVG local view must crop aggressively to stay readable.
- After default cross-community expansion, current-code AAPL local seed evidence improved to 22 visible nodes, 54 visible links, 3 visible communities, 5 industry nodes, 0 overlaps, and around 60 FPS. This is a measurable step toward Obsidian-like exploration, but not final product parity.
- After switching default symbol loading to issuer-level scope, current-code AAPL local seed evidence improved again to 37 visible nodes, 88 visible links, 3 visible communities, 13 industry nodes, 2 overlap pairs, 0 near-edge nodes, and around 60 FPS. The filter chip is now only `主体: issuer_aapl`, proving the default graph is no longer a single-security graph.
- After adding document/event/viewpoint seed nodes, current-code AAPL local evidence shows 40 visible nodes, 88 visible links, 4 visible communities, 13 industry nodes, 5 raw knowledge nodes, and visible `event`, `research`, and `evidence` node types. This moves the graph closer to an Obsidian vault model where company, industry, events, notes, and viewpoints are explored together.
- After adding the explicit focus-switch action, current-code browser evidence confirms a user can select a visible knowledge node and make it the local center: `focusId` changed from `issuer_aapl` to `event_obsidian_aapl_on_device_ai`, the event entered `expandedIds` and the exploration trail, and the saved-subgraph key moved to the event focus.
- After adding focus history and `graphBackFocus`, current-code browser evidence confirms the exploration jump is reversible: `focusId` changed from `issuer_aapl` to `event_obsidian_aapl_on_device_ai`, the focus-history list held 2 nodes, and `graphBackFocus` returned the graph to `issuer_aapl`.
- After adding knowledge-network readiness, current-code AAPL seed evidence is explicitly classified as `needs_data`: it has 90 graph edges, 7 community sources, and 8 present layers, but the `evidence` layer is missing and `seed_dependency.seed_dependent=true`. This prevents treating a fixture-rich graph as proof that the real local production vault is complete.
- After adding knowledge-network evidence backfill, current-code AAPL seed evidence can close the missing Evidence layer without hiding seed dependency: 2 graph documents produced 3 Evidence rows, readiness moved `evidence` from missing to sufficient, graph edges increased from 90 to 93 with `HAS_EVIDENCE`, and `seed_dependency.seed_dependent=true` remained true because the evidence came from seed documents.
- After adding evidence-link backfill, current-code AAPL seed evidence now has cross-layer event/viewpoint evidence links: 1 company event and 1 report viewpoint received evidence ids, readiness reports `event_evidence_links=1` and `viewpoint_evidence_links=1`, graph edges rose to 98, and browser raw edge types include `EVENT_EVIDENCE` and `VIEWPOINT_EVIDENCE`.
- After the 2026-06-30 natural-layout correction, the screenshot issue was traced to two concrete causes: the cropper could still evict clicked-node neighbors, and the force model had too much company/focus centering. The new code hard-preserves expanded neighborhoods and adds local anchor clustering, so click expansion changes visible graph structure rather than only `expandedIds`.
- A follow-up user review on 2026-06-30 showed the previous correction was still insufficient because main-node switching was too indirect and the layout still read as a rectangle. The second correction made click-to-focus the primary graph interaction and moved the layout toward focus-centered radial rings.
- Another 2026-06-30 user review exposed a test bug: the previous automation dispatched only `MouseEvent('click')`, while real clicks run through `pointerdown` first. Because node `pointerdown` always enabled click suppression, real clicks only highlighted during press and then reverted. This is now fixed and covered by pointer-chain acceptance.
- A later 2026-06-30 browser-level check exposed a second gap: the user was clicking the community label, not a regular `.graph-node-svg` node. That label was a summary overlay, not an exploration target, and its text had pointer-events disabled. Community labels now route to representative graph nodes.
- A later native-input probe exposed the remaining node-click issue: the node `pointerdown` set pointer capture on the SVG, so node-level `pointerup` was not reliable. The fix moved click finalization to the SVG `pointerup` fallback.
- Port warning: `http://127.0.0.1:8000` is currently a long-running Postgres/S3-backed service started at 2026-06-30T01:32:13Z, while the current-code browser proof was run on `http://127.0.0.1:55552`. If a browser is pointed at 8000, it may not show this work until that service is restarted with the current code.

## Proposed Work Plan

1. Consider Canvas/WebGL or virtualization if graph size grows beyond current AAPL scale.
2. Add visual controls for layout save status only if user testing shows ambiguity.
3. Consider pin/favorite or saved subgraph collections after the exploratory interaction stabilizes.

## Validation Plan

- Run `python3 scripts/ui_static_check.py`.
- Run `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Run `python3 scripts/check_handoffs.py`.
- Run `git diff --check`.
- Run `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope local --check-persistence --check-path --output artifacts/ui-graph-layout-acceptance.json`.
- Run `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope global --check-path --output artifacts/ui-graph-layout-acceptance-global.json --min-nodes 70 --min-links 150 --max-overlap-pairs 80 --max-near-edge-nodes 8`.
- Run `python3 scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:8000 --output artifacts/ui-graph-multi-symbol-acceptance.json`.
- Run `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:8000 --output artifacts/ui-graph-relationship-filter-acceptance.json`.
- Browser-load `/ui`, open the knowledge graph page, load AAPL, and verify node count, relation count, expansion, near-edge count, overlap count, label density, and performance status.

## Dependencies

- Existing `/api/graph/query` contract.
- Running local service at `http://127.0.0.1:8000/ui`.
- Playwright or equivalent browser automation for visual/DOM checks.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: upgraded graph model, layout, expansion interaction, label visibility, and graph stage size.
- `app/server.py`: added `AI_QUANT_PORT` parsing and range validation for direct current-code startup on non-8000 ports.
- `app/service_modules/graph_seed.py`: added local Obsidian-style graph seed definition and registration orchestration for multi-community graph samples.
- `app/services.py`: added derived industry semantic graph edges from existing chain-position records and a thin graph-seed facade.
- `app/api.py`, `app/api_routes.py`: added `POST /api/graph/seed/obsidian`.
- `tests/test_system.py`: added graph query assertions for industry peer, upstream, downstream, direction-level chain-node filtering, `AI_QUANT_PORT`, and Obsidian graph seed multi-dimension coverage.
- `scripts/seed_obsidian_knowledge_graph.py`: added CLI entry for preparing the local multi-community graph seed through the public API.
- `scripts/ui_graph_layout_acceptance.py`: added repeatable headless Chrome layout acceptance for the knowledge graph, including institutional holder edge checks.
- `scripts/ui_graph_multi_symbol_acceptance.py`: added multi-symbol browser matrix around the graph acceptance.
- `scripts/graph_acceptance_fixture.py`: added reusable public-API fixture setup for graph acceptance data.
- `scripts/ui_graph_relationship_filter_acceptance.py`: added relationship-filter browser matrix around graph acceptance, reports derived edge relationship types, reuses the graph acceptance fixture, runs the Obsidian graph seed, and covers institutional holder-key graph cases.
- `README.md`: documented `AI_QUANT_HOST` / `AI_QUANT_PORT` overrides and the Obsidian graph seed script.
- `tasks/todo.md`: added T-566 as the active follow-up task after T-485.
- `docs/agent-handoffs/2026-06-29-T-566-obsidian-knowledge-network.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope local --check-persistence --check-path --output artifacts/ui-graph-layout-acceptance.json
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope global --check-path --output artifacts/ui-graph-layout-acceptance-global.json --min-nodes 70 --min-links 150 --max-overlap-pairs 80 --max-near-edge-nodes 8
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers
python3 -m py_compile app/services.py tests/test_system.py scripts/ui_graph_layout_acceptance.py scripts/ui_graph_relationship_filter_acceptance.py scripts/ui_graph_multi_symbol_acceptance.py
python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:8000 --output artifacts/ui-graph-relationship-filter-acceptance.json --timeout 45
python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55537 --output artifacts/ui-graph-relationship-filter-acceptance-current.json --timeout 45
python3 scripts/graph_acceptance_fixture.py http://127.0.0.1:55537 --output artifacts/graph-acceptance-fixture-current.json --timeout 10
python3 -m py_compile app/server.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_server_port_reads_environment_and_validates_range
python3 scripts/check_handoffs.py
git diff --check
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_port_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55538 python3 -m app.server
curl -sS --max-time 10 http://127.0.0.1:55538/api/health
curl -sS --max-time 10 http://127.0.0.1:55538/ui | rg -n "<title>|关系图谱|知识图谱"
python3 -m py_compile app/service_modules/graph_seed.py app/services.py app/api.py app/api_routes.py scripts/seed_obsidian_knowledge_graph.py scripts/ui_graph_layout_acceptance.py scripts/ui_graph_relationship_filter_acceptance.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_obsidian_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55539 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55539 --output artifacts/obsidian-knowledge-graph-seed-current.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55539 --symbol AAPL --scope local --institutional-holder-key 0000102909 --min-nodes 8 --min-links 8 --min-community-labels 1 --max-overlap-pairs 12 --output artifacts/ui-graph-layout-acceptance-holder-current.json --timeout 45
python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55539 --output artifacts/ui-graph-relationship-filter-acceptance-current.json --timeout 60
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
git diff --check
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_natural_expand_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55551 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55551 --output artifacts/obsidian-knowledge-graph-seed-natural-expand.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55551 --symbol AAPL --scope local --min-nodes 32 --min-links 70 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --min-expansion-neighbor-delta 1 --min-visible-neighbors-after-click 3 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-natural-expand.json --timeout 60
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
git diff --check
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_click_focus_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55552 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-click-focus.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 30 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 0 --min-expansion-neighbor-delta 0 --min-visible-neighbors-after-click 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-click-focus.json --timeout 60
ss -ltnp | rg ':8000|:55552' || true
curl -sS --max-time 5 http://127.0.0.1:8000/api/health
curl -sS --max-time 5 http://127.0.0.1:55552/api/health
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
git diff --check
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-real-pointer.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 30 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 0 --min-expansion-neighbor-delta 0 --min-visible-neighbors-after-click 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-real-pointer.json --timeout 60
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-community-native-fixed.json --timeout 10
python3 - <<'PY'
# Used Chrome DevTools Protocol Input.dispatchMouseEvent against the industry community label center.
# Result: focus changed from issuer_aapl to chain_obsidian_ai_device_network; inspector title became AI 端侧设备与算力产业链.
PY
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 30 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 0 --min-expansion-neighbor-delta 0 --min-visible-neighbors-after-click 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-community-click.json --timeout 60
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-element-from-point.json --timeout 10
python3 - <<'PY'
# Used Chrome DevTools Protocol Input.dispatchMouseEvent twice:
# 1. clicked event_obsidian_aapl_on_device_ai -> focus changed from issuer_aapl to event_obsidian_aapl_on_device_ai
# 2. re-read current industry community label coordinates, clicked it -> focus changed to chain_obsidian_ai_device_network:edge_device
PY
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-label-disambiguation.json --timeout 10
python3 - <<'PY'
# Browser probe confirmed issuer_aapl label=AAPL · 公司 and security_aapl_us label=AAPL · NASDAQ.
PY
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_label_cleanup_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55552 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-label-cleanup.json --timeout 10
python3 - <<'PY'
# Headless Chromium DOM probe checked default-visible graph node labels, edge labels, community labels, inspector text, and graph relationship rows.
# Result: no visible doc/hold/pos/srr/vp/event/rel ... obsidian, RELATIONSHIP, VIEWPOINT_ON_COMPANY, or product strategy text.
PY
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-label-cleanup.json --timeout 45
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_multicommunity_objects2 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55541 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55541 --output artifacts/obsidian-knowledge-graph-seed-multicommunity.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55541 --symbol AAPL --scope local --min-nodes 20 --min-links 40 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --max-overlap-pairs 10 --max-near-edge-nodes 2 --output artifacts/ui-graph-layout-acceptance-multicommunity-current.json --timeout 45
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_company_scope_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55542 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55542 --output artifacts/obsidian-knowledge-graph-seed-company-scope.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55542 --symbol AAPL --scope local --min-nodes 24 --min-links 55 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --max-overlap-pairs 10 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --output artifacts/ui-graph-layout-acceptance-company-scope-current.json --timeout 45
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_knowledge_nodes_objects2 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55544 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55544 --output artifacts/obsidian-knowledge-graph-seed-knowledge-nodes.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55544 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --output artifacts/ui-graph-layout-acceptance-knowledge-nodes-current.json --timeout 45
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_focus_switch_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55545 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55545 --output artifacts/obsidian-knowledge-graph-seed-focus-switch.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55545 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-focus-switch-current.json --timeout 45
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_focus_history_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55546 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55546 --output artifacts/obsidian-knowledge-graph-seed-focus-history.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55546 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-focus-history.json --timeout 45
python3 -m py_compile app/service_modules/graph_intelligence.py app/services.py app/api.py app/api_routes.py scripts/graph_knowledge_network_readiness.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_knowledge_network_readiness_flags_real_data_gaps_and_seed_dependency
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_readiness_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55547 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55547 --output artifacts/obsidian-knowledge-graph-seed-readiness.json --timeout 10
python3 scripts/graph_knowledge_network_readiness.py http://127.0.0.1:55547 --issuer-id issuer_aapl --output artifacts/graph-knowledge-network-readiness-aapl-current.json --timeout 10
python3 -m py_compile scripts/backfill_knowledge_network_evidence.py app/service_modules/graph_intelligence.py app/services.py app/api.py tests/test_system.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_evidence_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55548 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55548 --output artifacts/obsidian-knowledge-graph-seed-evidence-backfill.json --timeout 10
python3 scripts/backfill_knowledge_network_evidence.py http://127.0.0.1:55548 --issuer-id issuer_aapl --limit 5 --output artifacts/knowledge-network-evidence-backfill-dry-run.json --timeout 10
python3 scripts/backfill_knowledge_network_evidence.py http://127.0.0.1:55548 --issuer-id issuer_aapl --limit 5 --execute --output artifacts/knowledge-network-evidence-backfill-executed.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55548 --symbol AAPL --scope local --min-nodes 28 --min-links 62 --min-community-labels 3 --min-visible-communities 4 --min-industry-nodes 5 --min-raw-knowledge-nodes 8 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-evidence-backfill.json --timeout 45
python3 -m py_compile app/service_modules/knowledge_network_backfill.py app/services.py app/api.py app/api_routes.py scripts/backfill_knowledge_network_evidence_links.py tests/test_system.py
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_t566_evidence_links_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55549 python3 -m app.server
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55549 --output artifacts/obsidian-knowledge-graph-seed-evidence-links.json --timeout 10
python3 scripts/backfill_knowledge_network_evidence.py http://127.0.0.1:55549 --issuer-id issuer_aapl --limit 5 --execute --output artifacts/knowledge-network-evidence-backfill-for-links.json --timeout 10
python3 scripts/backfill_knowledge_network_evidence_links.py http://127.0.0.1:55549 --issuer-id issuer_aapl --limit 10 --execute --output artifacts/knowledge-network-evidence-link-backfill-executed.json --timeout 10
python3 scripts/graph_knowledge_network_readiness.py http://127.0.0.1:55549 --issuer-id issuer_aapl --output artifacts/graph-knowledge-network-readiness-evidence-links.json --timeout 10
python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55549 --symbol AAPL --scope local --min-nodes 28 --min-links 64 --min-community-labels 3 --min-visible-communities 4 --min-industry-nodes 5 --min-raw-knowledge-nodes 8 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-evidence-links.json --timeout 45
```

Result:

- Passed: `python3 scripts/ui_static_check.py`, `python3 -m py_compile app/*.py tests/*.py scripts/*.py`, `python3 scripts/check_handoffs.py`, the focused unit subset, seed CLI, local graph acceptance, and relationship-filter matrix all passed on the current code path.
- Failed: none.
- Not run: full unit suite.

Browser validation:

- Headless Chrome loaded `http://127.0.0.1:8000/ui`.
- Loaded AAPL in the knowledge graph page.
- Acceptance measured local graph: `节点 39/132`, `关系 60/320`, measured DOM nodes 36, links 60, community labels 2, community quality labels 2, overlap pairs 2, near-edge nodes 0, click expansion 3, persisted layout restored with `dx=0`, `dy≈0.04`, path highlighted 2 nodes and 1 link, 6 path next-hops, path highlight retained after next-hop, 4 view controls passed, 2 exploration trail nodes passed, saved-subgraph restore produced 2 trail nodes, and performance measured around 60 FPS / 1.8ms average frame time.
- Acceptance measured global graph: `节点 88/132`, `关系 182/320`, measured DOM nodes 88, links 182, community labels 2, community quality labels 2, overlap pairs 66, near-edge nodes 0, click expansion 3, 6 path next-hops, path highlight retained after next-hop, 4 view controls passed, 2 exploration trail nodes passed, saved-subgraph restore produced 2 trail nodes, and performance measured around 60 FPS / 4.2ms average frame time.
- Multi-symbol matrix measured AAPL local 36 nodes/60 links, NVDA local 36 nodes/73 links, 600519 local 33 nodes/88 links, and AAPL global 88 nodes/182 links; all passed near-edge and performance gates.
- Relationship-filter matrix measured listed-security and institution-coverage filters for AAPL, NVDA, and 600519; all cases returned only the requested relationship type and passed browser rendering gates.
- Current-code Obsidian seed created 38 local graph records on `http://127.0.0.1:55539`, including AAPL/NVDA/MSFT/TSM/ASML/AVGO/600519/600809 issuers and securities, one AI device industry chain, 8 company positions, 8 listing relationships, and 5 13F holdings.
- API probes on 55539 confirmed AAPL `industry_peer`, `upstream_of`, `downstream_of`, and `institutional_holder_key=0000102909` all returned expected semantic graph edges.
- Holder-key browser acceptance on 55539 passed with 18 nodes, 43 links, 3 community labels, 0 overlap pairs, visible `13F持有人: 0000102909` chip, and `SAME_HOLDER_RELATED_COMPANY` in raw graph edges.
- Relationship-filter browser matrix on 55539 expanded to 10/10 cases. The new AAPL Vanguard holder case measured 28 nodes, 65 links, visible holder chip, and `SAME_HOLDER_RELATED_COMPANY`.
- Multi-community default browser acceptance on 55541 passed after the default depth/cross-community changes with 22 nodes, 54 links, 3 visible communities, 5 industry nodes, 0 overlap pairs, 0 near-edge nodes, saved-subgraph/trail/view-control checks, and about 60 FPS / 1.35ms average frame time.
- Company-scope default browser acceptance on 55542 passed after removing implicit security scoping from plain symbol graph loads: 37 nodes, 88 links, 3 visible communities, 13 industry nodes, 2 overlap pairs, 0 near-edge nodes, saved-subgraph/trail/view-control checks, and about 60 FPS / 1.69ms average frame time. The filter chip check forbids `证券:` and passed.
- Knowledge-node browser acceptance on 55544 passed after adding documents/events/structured reports/viewpoints to the Obsidian seed: 40 nodes, 88 links, 4 visible communities, 13 industry nodes, 5 raw knowledge nodes, visible knowledge types `event`, `research`, and `evidence`, 3 overlap pairs, 0 near-edge nodes, and about 60 FPS / 1.59ms average frame time. The filter chip check still forbids `证券:` and passed.
- Focus-switch browser acceptance on 55545 passed: selecting a visible knowledge node and pressing `graphFocusSelected` changed focus from `issuer_aapl` to `event_obsidian_aapl_on_device_ai`, kept the node expanded, wrote it to the exploration trail, and kept the graph within 40 visible nodes / 78 visible links / about 60 FPS.
- Focus-history browser acceptance on 55546 passed: AAPL default local graph measured 40 nodes, 78 links, 4 visible communities, 13 industry nodes, 5 raw knowledge nodes, and visible `event/research/evidence` node types. Selecting a visible knowledge node and pressing `graphFocusSelected` changed focus from `issuer_aapl` to `event_obsidian_aapl_on_device_ai`; the focus-history list contained 2 nodes, and `graphBackFocus` returned focus to `issuer_aapl`.
- Knowledge-network readiness CLI on 55547 passed and wrote `artifacts/graph-knowledge-network-readiness-aapl-current.json`: AAPL seed graph reported 90 edges, 7 community sources, 8 present layers, `missing_layers=["evidence"]`, `seed_dependency.seed_dependent=true`, and `ready_for_obsidian_exploration=false`.
- Knowledge-network evidence backfill on 55548 passed and wrote `artifacts/knowledge-network-evidence-backfill-executed.json`: AAPL had 2 candidate documents, created 3 Evidence rows, moved readiness `evidence` layer to sufficient, increased edges to 93 with `HAS_EVIDENCE`, and kept `seed_dependency.seed_dependent=true`.
- Evidence-backfill browser acceptance on 55548 passed and wrote `artifacts/ui-graph-layout-acceptance-evidence-backfill.json`: AAPL default graph measured 41 nodes, 82 visible links, 4 visible communities, 13 industry nodes, 8 raw knowledge nodes, visible `evidence/research/event`, and focus switch/back focus remained functional.
- Evidence-link backfill on 55549 passed and wrote `artifacts/knowledge-network-evidence-link-backfill-executed.json`: planned and updated 2 resources, including `event_obsidian_aapl_on_device_ai` and `vp_obsidian_aapl_device_cloud`.
- Evidence-link readiness on 55549 passed and wrote `artifacts/graph-knowledge-network-readiness-evidence-links.json`: `document_evidence_links=3`, `event_evidence_links=1`, `viewpoint_evidence_links=1`, `graph_summary.edges=98`, `status=needs_data`, and `seed_dependency.seed_dependent=true`.
- Evidence-link browser acceptance on 55549 passed and wrote `artifacts/ui-graph-layout-acceptance-evidence-links.json`: AAPL default graph measured 42 nodes, 88 visible links, 4 visible communities, 8 raw knowledge nodes, visible `event/research/evidence`, and raw edge types include `EVENT_EVIDENCE` and `VIEWPOINT_EVIDENCE`.

## Decisions

- Keep the existing SVG implementation for this slice because it integrates with current UI contracts and static checks.
- Do not replace `/api/graph/query`; this slice extends the existing graph response with derived industry edges while preserving the current backend contract and storage schema.
- Use progressive local expansion rather than showing all 132 nodes by default, because the current SVG viewport becomes unreadable when rendering 80+ nodes.
- Add explicit local/global graph modes so the UI can expose both readable exploration and broader overview.
- Keep audit-oriented relationship records, but visually prioritize business-readable nodes and weighted relations.
- Use explicit viewport controls in addition to wheel and drag gestures so the graph remains discoverable in dense views.
- Store exploration trails in client state for now; persist only manual layout positions until saved subgraphs have a clearer product contract.
- Keep SVG for the current AAPL-scale local/global graph because the measured frame-time threshold passes; revisit Canvas/WebGL only when larger graphs fail the acceptance threshold.
- Persist saved subgraphs only in localStorage for now, because this is a local exploration affordance and does not need a backend API until users need named/shared subgraphs.
- Use per-case thresholds in the multi-symbol matrix because graph richness differs by local data coverage; the generic interaction checks remain enabled.
- Keep relationship-filter thresholds data-aware; add industry peer/upstream/downstream browser cases after local sample data contains the required `CompanyPosition + IndustryChain` records.
- Let `python3 -m app.server` read `AI_QUANT_PORT` so current-code graph validation can use an explicit temporary port when the long-running 8000 service is stale or owned by another process.
- Keep graph seed data in `app/service_modules/graph_seed.py` and expose only a thin `SystemService` facade, so the seed can be reused by API, CLI, tests, and browser acceptance without expanding core service business logic.
- Keep the default local view at three hops with cross-community seed expansion. This better matches Obsidian's exploratory first impression without forcing a dense global graph that becomes unreadable in SVG.
- Treat plain ticker/symbol graph loading as a company-level knowledge-network entry point. Security-level scoping should be explicit, because implicit `security_id` made the first screen feel like a stock instrument graph instead of an explorable company network.
- Represent Obsidian-style note material with existing `Document`, `CompanyEvent`, `ResearchReport`, and `ReportViewpoint` objects. Do not add a separate graph-note schema until real local production imports show a gap that existing company-intelligence objects cannot cover.
- Make focus switching explicit rather than relying only on neighbor rows. The visible `设为焦点` action is easier to discover and better matches Obsidian's local-neighborhood exploration behavior.
- Keep focus history local and lightweight for now. A recent-focus stack plus `返回焦点` solves the immediate Obsidian-like navigation problem without adding backend state or named workspace semantics before real usage proves the need.
- Use a readiness report, not visual acceptance alone, as the bridge from seed fixture to real local production knowledge network. Visual graph checks prove interaction and layout; `/api/graph/knowledge-network/readiness` proves whether real data layers and cross-links are dense enough to claim Obsidian-style exploration.
- Treat evidence extracted from seed documents as seed-dependent evidence. It closes the technical Evidence layer but does not prove real production graph density until the source documents are real local imports.
- Evidence-link backfill should update provenance links only. It must not approve events or relationships, infer new facts, or treat report viewpoints as fact sources.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: yes, earlier scoped graph-query derivation was added inside `query_graph`; this continuation added thin facades for `graph_knowledge_network_readiness` and `backfill_knowledge_network_evidence_links`. The Obsidian graph seed lives in `app/service_modules/graph_seed.py`; readiness scoring lives in `app/service_modules/graph_intelligence.py`; evidence-link mutation lives in `app/service_modules/knowledge_network_backfill.py`.
- Domain module decision: reusable relationship context remains in `app/service_modules/company_intelligence.py`, seed orchestration remains in `graph_seed.py`, knowledge-network readiness lives in `graph_intelligence.py`, and provenance-link backfill lives in `knowledge_network_backfill.py`. `/api/graph/query` still owns node/edge assembly to preserve the public graph contract and avoid a partial extraction risk.
- Focused regression: graph industry-edge and Obsidian seed tests passed, including the `issuer_id + security_id + relationship_type=industry_peer` case and `institutional_holder_key=0000102909` same-holder graph case; readiness regression now also proves sparse graphs expose missing layers, seed-rich graphs remain `needs_data` when evidence is missing or seed-dependent, evidence extracted from seed documents does not erase seed dependency, and event/viewpoint evidence links produce graph edges.
- Contract/schema/boundary impact: API response gains derived edge types when source data exists; `POST /api/graph/seed/obsidian` adds local seed data only; `GET|POST /api/graph/knowledge-network/readiness` adds a read-only local density audit; `POST /api/graph/knowledge-network/evidence-links/backfill` updates local provenance links only; storage schema unchanged; UI behavior compatible; paper-only/no-broker boundary unchanged.

## Risks and Open Questions

- The graph is closer to Obsidian behavior but not complete: larger-than-current graph performance still needs threshold-driven evaluation.
- Current overlap check is approximate but now repeatable via `scripts/ui_graph_layout_acceptance.py`.
- The graph remains SVG-based; if graph size grows materially and the FPS/frame thresholds fail, performance may require Canvas/WebGL.
- Matrix currently covers three symbols plus one global overview plus one institutional holder network; broader sector-scale graphs still need future evidence.
- Industry-chain relationship filtering and institutional holder network are now supported by graph query code and browser-proven through controlled API fixtures and local Obsidian seed; real local production data import/update remains a follow-up.
- Current default graph is now issuer-level, but it can still look sparse compared with Obsidian when real local data lacks enough industry positions, holder facts, events, viewpoints, documents, and cross-company links.
- The existing `http://127.0.0.1:8000` service is a root-owned old process from before the graph-query change, so current-code browser evidence was gathered on `http://127.0.0.1:55537`; `AI_QUANT_PORT` now supports starting current code on a temporary port without an inline Python launcher.
- `app/static/index.html` remains large; future work should consider moving graph code into a UI module after preserving existing contract checks.

## Artifacts

- `artifacts/ui-graph-layout-acceptance.json`: local-only headless Chrome graph layout measurement, produced by `scripts/ui_graph_layout_acceptance.py`, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-global.json`: local-only headless Chrome global graph measurement, produced by `scripts/ui_graph_layout_acceptance.py`, not production-grade evidence.
- `artifacts/ui-graph-multi-symbol-acceptance.json`: local-only multi-symbol graph acceptance summary, not production-grade evidence.
- `artifacts/ui-graph-relationship-filter-acceptance.json`: local-only relationship-filter graph acceptance summary, not production-grade evidence.
- `artifacts/graph-acceptance-fixture-current.json`: local-only graph fixture preparation evidence from `scripts/graph_acceptance_fixture.py`, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-current.json`: local-only Obsidian graph seed result, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-holder-current.json`: local-only holder-key graph browser acceptance, not production-grade evidence.
- `artifacts/ui-graph-relationship-filter-acceptance-current.json`: local-only 10-case relationship/holder filter matrix, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-multicommunity.json`: local-only current-code Obsidian seed result on temporary port 55541, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-multicommunity-current.json`: local-only current-code browser acceptance for the default multi-community AAPL graph, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-company-scope.json`: local-only current-code Obsidian seed result on temporary port 55542, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-company-scope-current.json`: local-only current-code browser acceptance for issuer-level default AAPL graph, including forbidden `证券:` chip check, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-knowledge-nodes.json`: local-only current-code Obsidian seed result including document/event/viewpoint seed records, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-knowledge-nodes-current.json`: local-only current-code browser acceptance proving raw knowledge nodes and visible event/research/evidence node types, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-focus-switch.json`: local-only current-code Obsidian seed result used for focus-switch browser acceptance, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-focus-switch-current.json`: local-only current-code browser acceptance proving knowledge-node focus switching, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-focus-history.json`: local-only current-code Obsidian seed result used for focus-history browser acceptance, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-focus-history.json`: local-only current-code browser acceptance proving reversible focus switching through `graphBackFocus`, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-readiness.json`: local-only current-code Obsidian seed result used for knowledge-network readiness CLI evidence, not production-grade evidence.
- `artifacts/graph-knowledge-network-readiness-aapl-current.json`: local-only current-code readiness report showing AAPL seed graph still needs real evidence and lower seed dependency before claiming product-level Obsidian completeness, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-evidence-backfill.json`: local-only current-code Obsidian seed result used for evidence-backfill acceptance, not production-grade evidence.
- `artifacts/knowledge-network-evidence-backfill-dry-run.json`: local-only dry-run candidate list for AAPL document evidence backfill, not production-grade evidence.
- `artifacts/knowledge-network-evidence-backfill-executed.json`: local-only evidence backfill execution result showing 3 Evidence rows created from 2 AAPL seed documents, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-evidence-backfill.json`: local-only browser acceptance after evidence backfill, not production-grade evidence.
- `artifacts/obsidian-knowledge-graph-seed-evidence-links.json`: local-only current-code Obsidian seed result used for evidence-link acceptance, not production-grade evidence.
- `artifacts/knowledge-network-evidence-backfill-for-links.json`: local-only evidence extraction prerequisite for evidence-link acceptance, not production-grade evidence.
- `artifacts/knowledge-network-evidence-link-backfill-executed.json`: local-only evidence-link backfill execution result, not production-grade evidence.
- `artifacts/graph-knowledge-network-readiness-evidence-links.json`: local-only readiness report after evidence-link backfill, not production-grade evidence.
- `artifacts/ui-graph-layout-acceptance-evidence-links.json`: local-only browser acceptance after evidence-link backfill, not production-grade evidence.

## Handoff Checklist

- [x] Current task and scope recorded.
- [x] Files touched listed.
- [x] Commands and current browser evidence recorded.
- [x] Known remaining gaps listed.
- [x] Local graph layout acceptance completed.
- [x] Global graph overview acceptance completed.
- [x] Multi-dimensional graph seed and holder network acceptance completed.
- [x] Default local graph multi-community acceptance completed.
- [x] Default symbol graph no longer implicitly uses security-level scope.
- [x] Document/event/viewpoint knowledge nodes included in seed and browser acceptance.
- [x] Visible knowledge node can be promoted to local graph focus in browser acceptance.
- [x] Focus history and return-to-prior-focus behavior verified in browser acceptance.
- [x] Knowledge-network readiness report distinguishes seed/fixture graph coverage from real-data completeness.
- [x] Knowledge-network evidence backfill can close missing Evidence layer while preserving seed-dependency classification.
- [x] Knowledge-network evidence-link backfill connects event/viewpoint provenance to Evidence edges without changing fact/opinion boundaries.
- [ ] Full Obsidian-like product target completed.

## Evidence

- `python3 scripts/ui_static_check.py`: passed.
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`: passed.
- `python3 scripts/check_handoffs.py`: passed.
- `git diff --check`: passed.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope local --check-persistence --check-path --output artifacts/ui-graph-layout-acceptance.json`: passed.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:8000 --scope global --check-path --output artifacts/ui-graph-layout-acceptance-global.json --min-nodes 70 --min-links 150 --max-overlap-pairs 80 --max-near-edge-nodes 8`: passed.
- AAPL local graph after this slice: `节点 39/132`, `关系 60/320`, measured DOM nodes 36, links 60, community labels 2, community quality labels 2, overlap pairs 2, near-edge nodes 0, click expansion produced 3 expanded nodes, persisted layout restored with `dx=0`, `dy≈0.04`, path highlighted 2 nodes and 1 link, 6 path next-hops, next-hop click retained 2 path nodes and 1 path link, view controls passed with zoom status visible, trail controls pinned the selected node and produced 2 trail nodes, saved-subgraph restore produced 2 trail nodes, performance measured around 60 FPS / 1.8ms.
- AAPL global graph after this slice: `节点 88/132`, `关系 182/320`, measured DOM nodes 88, links 182, community labels 2, community quality labels 2, overlap pairs 66, near-edge nodes 0, click expansion produced 3 expanded nodes, 6 path next-hops, next-hop click retained 2 path nodes and 1 path link, view controls passed with zoom status visible, trail controls pinned the selected node and produced 2 trail nodes, saved-subgraph restore produced 2 trail nodes, performance measured around 60 FPS / 4.2ms.
- Multi-symbol matrix after this slice: AAPL local 36 nodes/60 links, NVDA local 36 nodes/73 links, 600519 local 33 nodes/88 links, AAPL global 88 nodes/182 links, all passed.
- Relationship-filter matrix after this slice: AAPL/NVDA/600519 listed-security and institution-coverage filters all passed with visible filter chips and correct raw relationship types.
- Focused backend regression after the industry-edge slice: `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers` passed.
- Focused compile after the industry-edge slice: `python3 -m py_compile app/services.py tests/test_system.py scripts/ui_graph_layout_acceptance.py scripts/ui_graph_relationship_filter_acceptance.py scripts/ui_graph_multi_symbol_acceptance.py` passed.
- Relationship-filter browser matrix rerun after acceptance-stat update: AAPL/NVDA/600519 listed-security and institution-coverage filters passed and reported matching `raw_edge_relationship_types`.
- Direct graph-query probe with an in-memory chain fixture returned one semantic edge for each of `industry_peer`, `upstream_of`, and `downstream_of`.
- Current-code browser matrix on `http://127.0.0.1:55537` passed 9/9 cases after controlled fixture preparation. AAPL industry filters measured `industry_peer` 11 nodes/19 links, `upstream_of` 12 nodes/19 links, and `downstream_of` 12 nodes/19 links, each with the expected raw edge relationship type and no persisted `company_relationships`.
- `python3 scripts/graph_acceptance_fixture.py http://127.0.0.1:55537 --output artifacts/graph-acceptance-fixture-current.json --timeout 10`: passed and prepared 32 public-API fixture operations.
- `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_acceptance_fixture_supports_industry_relationship_filters tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers`: passed.
- `python3 -m unittest tests.test_system.SystemServiceTests.test_server_port_reads_environment_and_validates_range`: passed.
- `AI_QUANT_PORT=55538 python3 -m app.server` with clean local storage overrides started current code; `/api/health` returned `status=ok`, `store=InMemoryStore`, and `/ui` returned the knowledge graph section.
- `python3 -m unittest tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network`: passed.
- `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55539 --output artifacts/obsidian-knowledge-graph-seed-current.json --timeout 10`: passed and created 38 local graph seed records.
- Direct graph-query probes on `http://127.0.0.1:55539` returned `INDUSTRY_PEER`, `INDUSTRY_UPSTREAM_OF`, `INDUSTRY_DOWNSTREAM_OF`, and `SAME_HOLDER_RELATED_COMPANY` for AAPL.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55539 --symbol AAPL --scope local --institutional-holder-key 0000102909 --min-nodes 8 --min-links 8 --min-community-labels 1 --max-overlap-pairs 12 --output artifacts/ui-graph-layout-acceptance-holder-current.json --timeout 45`: passed with 18 nodes, 43 links, 3 community labels, 0 overlap pairs, and visible same-holder edge.
- `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55539 --output artifacts/ui-graph-relationship-filter-acceptance-current.json --timeout 60`: passed 10/10 cases; AAPL Vanguard holder case measured 28 nodes and 65 links.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55541 --symbol AAPL --scope local --min-nodes 20 --min-links 40 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --max-overlap-pairs 10 --max-near-edge-nodes 2 --output artifacts/ui-graph-layout-acceptance-multicommunity-current.json --timeout 45`: passed with 22 nodes, 54 links, 3 visible communities, 5 industry nodes, 0 overlap pairs, 0 near-edge nodes, and about 60 FPS.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55542 --symbol AAPL --scope local --min-nodes 24 --min-links 55 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --max-overlap-pairs 10 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --output artifacts/ui-graph-layout-acceptance-company-scope-current.json --timeout 45`: passed with 37 nodes, 88 links, 3 visible communities, 13 industry nodes, 2 overlap pairs, 0 near-edge nodes, `filter_chips="主体: issuer_aapl"`, and about 60 FPS.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55544 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --output artifacts/ui-graph-layout-acceptance-knowledge-nodes-current.json --timeout 45`: passed with 40 nodes, 88 links, 4 visible communities, 13 industry nodes, 5 raw knowledge nodes, visible `event/research/evidence` node types, 3 overlap pairs, 0 near-edge nodes, `filter_chips="主体: issuer_aapl"`, and about 60 FPS.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55545 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-focus-switch-current.json --timeout 45`: passed. `focus_switch.after_focus_id=event_obsidian_aapl_on_device_ai`, `expanded=true`, `trail_nodes=1`, and `button_present=true`.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55546 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-focus-history.json --timeout 45`: passed. It measured 40 nodes, 78 links, 4 visible communities, 13 industry nodes, 5 raw knowledge nodes, visible `event/research/evidence`, `focus_switch.after_focus_id=event_obsidian_aapl_on_device_ai`, `history_nodes_after_focus=2`, and `after_back_focus_id=issuer_aapl`.
- `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_knowledge_network_readiness_flags_real_data_gaps_and_seed_dependency`: passed.
- `python3 scripts/graph_knowledge_network_readiness.py http://127.0.0.1:55547 --issuer-id issuer_aapl --output artifacts/graph-knowledge-network-readiness-aapl-current.json --timeout 10`: passed. The report shows `status=needs_data`, 90 edges, 7 communities, 8 present layers, missing `evidence`, `seed_dependency.seed_dependent=true`, `automation_allowed=false`, and `live_execution_allowed=false`.
- `python3 scripts/backfill_knowledge_network_evidence.py http://127.0.0.1:55548 --issuer-id issuer_aapl --limit 5 --execute --output artifacts/knowledge-network-evidence-backfill-executed.json --timeout 10`: passed. It created 3 Evidence rows from 2 AAPL graph documents, readiness moved `evidence` from missing to sufficient, graph edges rose from 90 to 93, and seed dependency stayed true.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55548 --symbol AAPL --scope local --min-nodes 28 --min-links 62 --min-community-labels 3 --min-visible-communities 4 --min-industry-nodes 5 --min-raw-knowledge-nodes 8 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-evidence-backfill.json --timeout 45`: passed. It measured 41 visible nodes, 82 visible links, 4 visible communities, 8 raw knowledge nodes, `HAS_EVIDENCE`, `evidence/research/event` visible knowledge types, and reversible focus switching.
- `python3 scripts/backfill_knowledge_network_evidence_links.py http://127.0.0.1:55549 --issuer-id issuer_aapl --limit 10 --execute --output artifacts/knowledge-network-evidence-link-backfill-executed.json --timeout 10`: passed. It updated 2 resources: 1 company event and 1 report viewpoint.
- `python3 scripts/graph_knowledge_network_readiness.py http://127.0.0.1:55549 --issuer-id issuer_aapl --output artifacts/graph-knowledge-network-readiness-evidence-links.json --timeout 10`: passed. It reported `event_evidence_links=1`, `viewpoint_evidence_links=1`, 98 graph edges, `status=needs_data`, and seed dependency still true.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55549 --symbol AAPL --scope local --min-nodes 28 --min-links 64 --min-community-labels 3 --min-visible-communities 4 --min-industry-nodes 5 --min-raw-knowledge-nodes 8 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-evidence-links.json --timeout 45`: passed. It measured 42 visible nodes, 88 visible links, 4 visible communities, `EVENT_EVIDENCE`, `VIEWPOINT_EVIDENCE`, 8 raw knowledge nodes, and reversible focus switching.
- `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55552 --output artifacts/obsidian-knowledge-graph-seed-label-cleanup.json --timeout 10`: passed and created 49 local Obsidian seed records on current-code port 55552.
- Headless Chromium default-visible label probe on `http://127.0.0.1:55552/ui`: passed. It checked graph node labels, edge labels, community labels, inspector text, and graph relationship rows; no default-visible `doc/hold/pos/srr/vp/event/rel ... obsidian`, `RELATIONSHIP`, `VIEWPOINT_ON_COMPANY`, or `product strategy` remained. Folded trace JSON still contains raw provenance by design.
- `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55552 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --check-focus-switch --output artifacts/ui-graph-layout-acceptance-label-cleanup.json --timeout 45`: passed. It measured 35 DOM nodes, 88 links, 4 visible communities, 12 industry nodes, 0 overlap pairs, 0 near-edge nodes, click focus/expansion from `issuer_aapl` to `pos_obsidian_asml_equipment`, and community-label focus to `chain_obsidian_ai_device_network:foundry`.

## Next Recommended Action

Use `scripts/seed_obsidian_knowledge_graph.py` on the long-lived local service, then continue replacing local seed samples with real local production imports for industry positions, shareholder facts, events, viewpoints, documents, evidence, and holder networks.

## Next Steps

1. Run `scripts/seed_obsidian_knowledge_graph.py` against the long-lived local service once it is running current code.
2. Restart or replace the old root-owned 8000 service with current code before using it as visual evidence.
3. Run `scripts/graph_knowledge_network_readiness.py` against real long-lived local companies and use `next_actions` to drive the next backfill batch.
4. Run `scripts/backfill_knowledge_network_evidence.py --execute` on real imported issuer documents where readiness reports missing evidence.
5. Run `scripts/backfill_knowledge_network_evidence_links.py --execute` after evidence extraction to attach event/relationship/viewpoint provenance links.
6. Replace seed samples with real local production imports for company positions, shareholder facts, and 13F holder networks.
7. Add richer real event/viewpoint/document/evidence cross-links to make the graph feel more like an Obsidian vault rather than only a seeded industry/shareholder network.
8. Add richer focus-history collections or saved named graph workspaces only if user testing shows the lightweight recent-focus row is not enough.
9. Evaluate Canvas/WebGL only if larger graphs fail measured FPS/frame thresholds.
