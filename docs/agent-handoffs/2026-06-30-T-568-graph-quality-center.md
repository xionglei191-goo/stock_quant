# Handoff: T-568 Graph Quality Center

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows, Platform and Quality
- Last updated: 2026-07-01
- Last agent: Codex
- Branch/worktree: main
- Related tasks: T-568

## Scope

- In scope:
  - Graph quality and gap audit over the current production universe sample.
  - Real event and relationship enrichment orchestration through existing builders.
  - Optional browser matrix handoff through existing UI graph acceptance script.
  - Roadmap cleanup for stale T-566 status.
- Out of scope:
  - New storage schema.
  - `/api/graph/query` schema changes.
  - New external paid data sources.
  - Promoting research-report opinions to facts.
  - Broker integration or live trading.

## Objective

Close the three requested follow-up directions after full graph backfill: graph data quality gaps, real event/relationship enrichment entry points, and productized graph exploration acceptance.

## Background

T-566 made the graph exploration UI more Obsidian-like. T-567 gave all current A/U in-scope stocks a baseline graph scaffold. The next gap is operational: users need to know why a stock graph is shallow, whether the UI still passes exploration quality gates, and which local data builders should be run next.

## Problem Statement

Without a single quality center, graph work splits across separate readiness checks, batch backfill artifacts, event builders, relationship builders, and browser acceptance scripts. That makes it easy to miss shallow graphs, raw label leakage, duplicate labels, or missing event/relationship layers after new data runs.

## Expected Deliverables

- Add `app/service_modules/graph_quality_center.py`.
- Add `GET|POST /api/graph/quality-center`.
- Add `scripts/graph_quality_center.py`.
- Add focused tests for API output, enrichment dry-run safety, and CLI artifact writing.
- Update `README.md` with usage examples.
- Update `tasks/todo.md` with T-568 and correct stale T-566 DOING status.

## Current Findings

- The quality center samples the same production universe selector used by T-567.
- For each target it calls `query_graph` and `graph_knowledge_network_readiness`, then summarizes missing/thin layers, cross-links, seed dependency, duplicate labels, raw label leakage, edge density, and community count.
- Empty target universes now return `status=no_targets`, `needs_attention_count=1`, and a `target_universe` global failure instead of passing.
- Enrichment actions reuse `build_company_events` and `build_company_relationships`; default behavior is dry-run.
- Writes require `run_enrichment=true` and `execute=true`.
- Candidate event/relationship records remain review-gated and local-only.
- Optional `--browser-matrix` delegates to `scripts/ui_graph_multi_symbol_acceptance.py`.
- The quality gate now applies the same readable label cleanup used by the UI for issuer/security/market-data identifiers.
- `market_data` graph nodes are treated as first-class display nodes in the SVG explorer and render as `行情 <security> <date>` instead of raw `md_public_eod...` IDs.
- The SVG explorer now aggregates per-day `market_data` rows into one `行情走势` node per security and deduplicates repeated edges after node redirection. This keeps detailed K-line/table data intact outside the graph while reducing graph clutter.
- Focus status now uses the visible node semantic label instead of `graphRef(focusId)`, and generic `vp_rr_*` / `rr_*` IDs are normalized to `研究观点` / `研报主题`.
- Browser layout acceptance now checks visible graph text from SVG labels, inspector, path/trail panels, focus label, and motion status for raw identifiers such as `md_`, `market_data_summary:`, Obsidian seed IDs, and long hash-based viewpoint IDs.
- Graph inspector node traces now sanitize graph node metadata before rendering, so market-data summary nodes do not expose `market_data_summary:*` or raw `md_*` source point IDs in the default details text.
- Backend graph quality raw-label evaluation now shares the generic research ID cleanup for `vp_rr_*`, `rr_*`, and `srr_*`, keeping the quality-center gate aligned with the visible graph.
- Backend graph quality now separates `structure` from `raw_structure`. `structure` follows the UI display model by collapsing daily `market_data` rows into one market-data summary node per security before computing hub dominance, leaf ratio, fragmentation, effective edge count, duplicate display edges, and edge-type distribution. `raw_structure` keeps the uncollapsed backend graph for data diagnostics.
- Click-expansion acceptance distinguishes true expansion targets from sparse/leaf nodes: nodes with hidden neighbors must reveal growth, while nodes without hidden neighbors are accepted when click focus, selection, and at least one existing visible neighbor remain stable.
- Backend graph quality now shares the UI relationship-type display vocabulary for common graph relationship enums. `listed_security`, `customer_candidate`, `supplier_candidate`, industry direction edges, ownership candidates, 13F holder edges, and evidence links are evaluated as readable labels such as `上市证券` and `客户候选`, so machine relationship enums do not slip through display-quality gates.
- Backend graph quality now defaults to zero tolerance for duplicate display labels and raw label leaks. `max_duplicate_labels` / `max_raw_label_leaks` remain explicit override knobs for diagnosis, but the normal quality gate no longer lets known display ambiguity pass by default.
- API contracts now document `GET|POST /api/graph/quality-center`, including strict display-label thresholds, `quality_gate.structure/raw_structure`, enrichment dry-run/execute behavior, and the fixed no-broker/paper-only boundary.
- Frontend graph model now builds direct display edges for `company_relationships` from canonical `subject_id` and `object_id` when source/target issuer aliases are absent. This keeps customer/supplier/ownership/listing relationships visible as semantic graph edges instead of forcing users through the raw relationship record node.
- Backend display-structure quality mirrors that frontend projection by folding the raw `HAS_COMPANY_RELATIONSHIP` / `RELATIONSHIP_SUBJECT` / `RELATIONSHIP_OBJECT` relationship-record chain into one display edge for structure checks. Raw structure is still preserved separately for diagnostics.
- Frontend graph model and backend quality labels now disambiguate 13F holding nodes as `13F 持仓 · <holder> / <security-or-issuer> · <period>`. This prevents same-holder portfolios from showing several indistinguishable `Vanguard Group Inc.` / `Berkshire Hathaway Inc.` nodes and keeps duplicate-label gates focused on real ambiguity.
- Frontend graph model and backend quality labels now also disambiguate issuer/security nodes that share the same ticker. Issuer labels can fall back through `aliases`, readable `issuer_id`, and `legal_name`, while securities keep ticker plus market/exchange. This removes the local AAPL duplicate naked-label case where both company and security could render as `AAPL`.
- The display relationship derivation algorithms for `industry_peer`, `upstream_of`, `downstream_of`, 13F same-holder expansion, and ownership-holder fact networks are now isolated in `app/service_modules/graph_derived_relationships.py`. `SystemService.query_graph` still owns compatibility node/edge assembly, but the reusable relationship planning logic no longer grows inside the large facade method.
- The extracted industry and 13F holder planner outputs now use frozen dataclass contracts instead of bare dicts. This makes future graph display optimization less dependent on implicit string keys while preserving `/api/graph/query` output.
- Graph source-layer actions are now isolated in `app/service_modules/graph_source_actions.py`. The quality center `enhancement_actions` and graph enrichment runner `layer_action_plan` share the same action, endpoint, required source field, and usage-boundary definitions for event, relationship, document, evidence, holding, research report, and viewpoint layers.
- The knowledge graph UI now exposes a separate display-quality gate through the “检查展示质量” button. It dry-runs `/api/graph/quality-center` for the current issuer/symbol and renders duplicate display labels, raw ID leaks, duplicate display edges, and structural gate failures in `knowledgeGraphQualityGateRows`, separate from the data-density readiness and source-input queue tables.
- `quality_gate.remediation_actions` now routes display-quality failures to concrete dry-run next steps. Density/layer/structure failures point to `/api/graph/enrichment-runner` source queues, duplicate labels/display edges point to `/api/company-database/quality/reconcile` preview, and raw label leaks point back to a read-only quality-center label-model inspection.
- The browser graph layout acceptance now checks focus switching through a coordinate-based `PointerEvent('pointerdown')` + `pointerup` + click path and fails with `focus_switch_pointer_chain` if the target element cannot be exercised through the pointer chain. This keeps the Obsidian-style graph interaction gate aligned with real pointer behavior instead of a synthetic click-only shortcut.
- Graph quality thresholds are now centralized in the frozen `GraphQualityThresholds` domain contract. `query_graph` filters and `quality_gate.thresholds` share the same parsed values, and explicit query-string `0` values are preserved instead of being replaced by defaults.
- Local browser acceptance fixture securities are now registered with `company_universe_scope=out_of_scope`. Quality-center and full-graph production universe sampling therefore skip `AAPL-P/AAPL-U/AAPL-D` fixture-only securities by default, while browser relationship-filter acceptance can still use them through explicit query context.
- Relationship-filter browser acceptance now marks institution-coverage and Alpha shareholder cases as fixture-only. When `--skip-industry-fixture` is used, those cases are reported under `skipped_cases` instead of being executed against missing setup data and producing misleading failures.
- Display duplicate edges are now a first-class quality gate. `max_display_duplicate_edges` defaults to `0` for the UI display model, while `max_duplicate_edges` remains a raw-structure diagnostic threshold defaulting to `4`.
- The graph acceptance fixture now reuses the Obsidian seed listing relationship IDs for AAPL, NVDA, and 600519. This keeps repeated seed+fixture setup idempotent and avoids duplicate `listed_security` display edges in acceptance-only data.
- Display duplicate-edge counting now follows the actual rendered edge set after market-data aggregation. Repeated raw `HAS_MARKET_DATA` edges redirected into one `market_data_summary:<security>` node are no longer counted as duplicate display edges, while repeated first-class `company_relationships` display edges still fail the zero-tolerance gate.
- Quality-center `enhancement_actions` now follow each target's actual missing/thin layers instead of returning a fixed event/relationship builder list. This keeps post-event samples pointed at the real remaining layers: 13F/holdings, documents, evidence, structured research reports, and viewpoints.
- Display structure now canonicalizes industry chain nodes to `chain_id:node_id`, matching the UI graph model and backend edge endpoints. This prevents one chain node from being counted as both bare `node_id` and scoped `chain_id:node_id`.
- Frontend graph display now consumes `structured_research_reports` from `/api/graph/query` and connects `report_viewpoints` through `research_report_id`. This closes the gap where structured report data existed in the API response but could be missing or disconnected in the visible graph.
- Browser graph layout acceptance now records `raw_structured_reports` and fails when structured reports exist but no visible `research` node type is rendered.
- Backend quality-center structure now records `community_counts` and `max_community_node_share`, with `max_community_node_share` defaulting to `0.72`. The new `community_balance` failure catches graphs where the nominal community count passes but one community still dominates the display model.
- `scripts/graph_quality_center.py --browser-matrix` can now pass `--min-browser-visible-communities` and `--min-browser-community-spread-ratio` into the browser layout matrix, so one quality-center run can pair backend community balance with pixel-level community spread acceptance.
- The knowledge graph display-quality panel now renders `community_balance` as `社区节点失衡`, displays the actual/max community share as percentages, and includes a readable `community_counts` summary such as company/evidence/industry node counts.
- Browser layout acceptance now writes `/api/graph/knowledge-network/readiness` into `knowledge_network_readiness`, including `seed_dependency`, missing/thin layers, cross-links, and paper-only boundaries. The optional `--require-non-seed-readiness` gate fails production-style visual acceptance when the graph is still seed dependent or readiness is not `ready`.
- `renderKnowledgeGraphExplorer()` now maintains shared `knowledgeGraphState.nodeById`, `communitySummaries`, and `communityNodesByKey` structures for the visible layout. Edge markup, focus-label lookup, community-label updates/click representative selection, path/trail/history pruning, inspector neighbor rendering, label updates, SVG position sync, centering, drag interactions, and the animation tick reuse prebuilt indexes instead of repeatedly scanning `knowledgeGraphState.nodes`, rebuilding per-frame node objects, or recomputing community summaries; the node `<g>` transform update uses the same Map so dynamic layout and dragging keep nodes, edges, and edge labels aligned, while community labels refresh their centroid coordinates from the cached community node groups so cached summaries do not leave labels behind during animation or drag.
- Path-panel next hops now use `graphPathNextHops()` instead of taking the first three adjacent links. The helper keeps candidates inside the visible node map, deduplicates by node, and sorts by graph node priority, knowledge/research/event/evidence value, link weight, and the current path node's community context so the side branches in a highlighted path remain useful exploration entry points. Highlight class decisions now flow through `knowledgeGraphNodeHighlightState()` / `knowledgeGraphLinkHighlightState()`, and path nodes/links stay readable even when a separate node is selected. Neighbor rows, path next-hop buttons, focus history, and trail buttons now use `activateKnowledgeGraphSideNode()` so side-panel exploration actions share one focus/select/path activation contract. Focus changes now use `updateKnowledgeGraphFocusPathAnchor()` to keep a readable path from the new focus back to the previous focus instead of clearing the path context.
- Browser focus-switch acceptance now records `path_after_focus` and `path_after_back_focus`. The gate requires the forward focus switch to preserve a highlighted path from the new focus back to the previous focus, and the back-focus switch to preserve the reverse path, so this graph-first context behavior is covered by a rendered browser check. It also clicks a rendered `.graph-neighbor[data-node-id]` row and requires the neighbor to become both focus and selection, covering side-panel graph exploration with real DOM interaction. Neighbor rows, path next-hop buttons, focus history, and trail entries are explicit `button type="button"` controls with action-specific `aria-label` text; neighbor rows also keep a `:focus-visible` style so side-panel exploration is keyboard-focusable, not just a clickable block.
- Main SVG graph nodes and community labels are now keyboard-focusable controls: their `<g>` elements include `role="button"`, `tabindex="0"`, and action-specific `aria-label` text, and Enter/Space trigger the same node selection or community representative focus change as pointer interaction. Nodes and community labels also expose visible `:focus-visible` styles so graph-first exploration has a visible keyboard cursor instead of only mouse/pointer or side-panel affordances.
- Browser focus-switch acceptance now exercises those main SVG keyboard paths directly: it focuses a `.graph-node-svg`, dispatches Enter, and requires both `focusId` and `selectedId` to become that node while semantic and `:focus-visible` evidence is recorded in `focus_switch.keyboard_node`; it also focuses a `.graph-community-label`, dispatches Space, and requires focus to move to that community representative while evidence is recorded in `community_click.keyboard_community`.
- The focus-switch path gate now also protects against a real pointer/click race: `selectKnowledgeGraphNode()` ignores the suppressed click after a pointerup focus switch so the second click cannot clear `pathEndId`, and `filteredGraphModel()` keeps `pathStartId`/`pathEndId` as pinned path anchors before local depth cropping. Current-code isolated acceptance on port `55701` passed with `artifacts/ui-graph-layout-keyboard-focus-55701.json`, including `focus_switch.keyboard_node.focus_visible_before_key=true`, `community_click.keyboard_community.focus_visible_before_key=true`, and `path_after_focus` preserving `pos_obsidian_aapl_edge_device -> issuer_aapl`.
- Mobile graph layout now has a first-class browser gate. At `max-width:900px`, `.graph-explorer` becomes a single column, the graph stage/SVG use a 480px minimum height, and the inspector drops below the graph with a lower minimum height. `scripts/ui_graph_layout_acceptance.py` accepts `--viewport-width`, `--viewport-height`, and `--expect-mobile-layout`, records `responsive_layout` and interaction-stable `initial_graph`, and fails on mobile horizontal overflow, missing single-column order, or collapsed graph height. Current-code isolated acceptance on port `55702` passed for AAPL at `430x900` with `artifacts/ui-graph-layout-mobile-55702.json`; desktop focus-switch regression also passed with `artifacts/ui-graph-layout-desktop-after-mobile-55702.json`.
- Reduced-motion graph layout now has a browser gate. The UI checks `prefers-reduced-motion: reduce`, keeps the graph in static layout until the user explicitly clicks “继续动态”, synchronously settles node positions without leaving an active `requestAnimationFrame`, and labels status as `减少动态 · 静态布局`. `scripts/ui_graph_layout_acceptance.py` accepts `--emulate-reduced-motion` and `--expect-reduced-motion`, records `reduced_motion`, and fails if reduced-motion media state is not reflected in graph state, dynamic motion stays active, an RAF remains scheduled, or the opt-in button/status is missing. Current-code isolated acceptance on port `55703` passed with `artifacts/ui-graph-layout-reduced-motion-55703.json`: 28 nodes / 79 links, 4 community labels, `reduced_motion.matches=true`, `dynamic=false`, `frame_id=0`, and status `减少动态 · 静态布局`.
- Node type encoding is now redundant instead of color-only. Each visible SVG node carries a centered `.graph-node-type-code` and `data-type-code`, the legend repeats the same code beside the color swatch, and node `aria-label` names the semantic type. `scripts/ui_graph_layout_acceptance.py` accepts `--expect-redundant-node-encoding`, records `encoded_node_types`, `legend_encoded_types`, and `legend_encodings`, and fails when any visible node type lacks a node code or matching legend code. Current-code isolated acceptance on port `55704` passed with `artifacts/ui-graph-layout-redundant-encoding-55704.json`: 28 nodes / 79 links, 4 community labels, encoded node types and legend encoded types both covered issuer, event, research, industry, evidence, and security, with no missing type codes.
- Graph markup now escapes SVG edge ids/endpoints, edge labels, node ids/labels, community keys/labels/quality text, path-step labels, inspector neighbor labels/ids, legend labels, and node meta badges before writing `innerHTML`, keeping special characters or raw source text from breaking visible graph labels and interaction attributes.
- Browser layout acceptance now supports `--max-visible-nodes`, `--max-visible-links`, and `--max-link-label-dom-count`. Large-graph runs can pair those with `--expect-performance-mode large` to prove the SVG explorer is still rendering a bounded visible subgraph instead of dumping the full backend graph into the DOM. In large mode the front end only creates edge-label DOM for focus/selected/path-related links, path refresh triggers a redraw so newly highlighted path links still get readable labels, `renderStats.linkLabelDomCount` is the shared runtime/artifact metric, and the high-performance status text exposes visible/full nodes, visible/full links, and label DOM count.

### SystemService Growth Freeze Review

- New `SystemService` business logic added: no; this pass moved existing industry relationship, 13F same-holder, ownership-holder derivation planning, graph source-layer action definitions, and quality-center community-balance checks into domain modules, and later exposed the existing quality-center facade in the UI without touching `SystemService`.
- Domain module used: yes, `app/service_modules/graph_quality_center.py`, `app/service_modules/graph_derived_relationships.py`, and `app/service_modules/graph_source_actions.py`.
- Facade behavior protected by: focused tests for API gap/action output, enrichment dry-run no-write behavior, CLI artifact writing, shared graph source actions, industry relationship graph-query regressions, chain-node canonical structure metrics, community-balance structure metrics, 13F holder-key graph-query regressions, and ownership holder-key browser regression.
- API/storage/UI/paper-only impact: one new quality-center API endpoint from the original T-568 work; no storage schema change; UI display contract now explicitly includes structured research report/viewpoint linkage from existing `/api/graph/query` fields, a read-only graph display-quality gate, dry-run remediation routing for failed display gates, community-balance structure fields in `quality_gate.structure`, a front-end display row for community balance, large-graph edge-label DOM reduction, and browser acceptance artifacts that surface seed dependency and bounded visible-DOM budgets; no broker or live-trading behavior.

## Proposed Work Plan

1. Add a domain module for graph quality center orchestration.
2. Add a `SystemService` facade and API route.
3. Add a CLI that writes local artifacts and optionally runs browser matrix acceptance.
4. Add focused regressions.
5. Update README, roadmap, and handoff.
6. Run validation.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_enrichment_dry_run_does_not_write tests.test_system.SystemServiceTests.test_graph_quality_center_script_writes_artifact
python3 -m unittest tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_dry_run_does_not_write tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_execute_is_idempotent
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_graph_model_consumes_structured_research_reports tests.test_system.SystemServiceTests.test_graph_quality_center_structure_links_structured_report_viewpoints
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Dependencies

- Existing `SystemService.query_graph`.
- Existing `SystemService.graph_knowledge_network_readiness`.
- Existing `SystemService.build_company_events`.
- Existing `SystemService.build_company_relationships`.
- Existing `scripts/ui_graph_multi_symbol_acceptance.py` for optional browser matrix.

## Blockers

- None.

## Risks

- Quality thresholds are conservative defaults and should be tuned after larger local A/U runs.
- Browser matrix depends on an active service and local browser tooling, so it remains optional for quick audit runs.
- HK remains a documented universe gap until real HK/H in-scope securities exist.

## Handoff Checklist

- [x] Code changes completed.
- [x] API route added.
- [x] CLI added.
- [x] Focused tests added.
- [x] README updated.
- [x] Roadmap updated.
- [x] Handoff created.

## Evidence

- `app/service_modules/graph_quality_center.py`: graph quality center module.
- `scripts/graph_quality_center.py`: local CLI.
- `tests/test_system.py`: focused regression coverage.
- Focused unit validation passed:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_enrichment_dry_run_does_not_write tests.test_system.SystemServiceTests.test_graph_quality_center_script_writes_artifact tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_dry_run_does_not_write tests.test_system.SystemServiceTests.test_full_knowledge_graph_bulk_execute_is_idempotent
```

- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`: passed.
- `python3 scripts/ui_static_check.py`: passed.
- `git diff --check`: passed.
- `python3 scripts/check_handoffs.py`: rerun required after this template correction.
- Current-code isolated service no-target smoke passed on port `55611`: `scripts/graph_quality_center.py` returned `status=no_targets` and exited with code `1`, which prevents empty graphs from being treated as quality-passed.
- Current-code PostgreSQL sample smoke passed on port `55612`:
  - Existing long-running `http://127.0.0.1:8000` returned `404` for the new graph endpoints because it was an older process, so validation used a restarted current-code service on `55612` pointed at the same PostgreSQL DSN.
  - `python3 scripts/graph_quality_center.py http://127.0.0.1:55612 --market A,U --limit 5 --output artifacts/graph-quality-center/postgres-current-code-sample-after-labels.json --timeout 60`
  - Result: `status=needs_attention`, `processed_count=5`, `raw_label_leaks=0` for sampled items. Remaining failures are data-layer gaps such as `layer_count`, not raw display labels.
- Browser graph acceptance passed against the same current-code PostgreSQL service:
  - `python3 scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55612 --symbols 000001,AAPL --output artifacts/ui-graph-multi-symbol-label-cleanup-acceptance-pass.json --timeout 60`
  - Result: `status=passed`, `case_count=2`, both symbols had `42` nodes, `110` links, `near_edge_nodes=0`, and saved subgraph restore count `3`.
  - `scripts/ui_graph_layout_acceptance.py` now treats rAF FPS as a scheduling signal and pairs it with average frame time; low FPS only fails when frame work is also high, while `graph_avg_frame_ms` remains a hard gate.
- Browser graph acceptance after market-data aggregation passed:
  - `python3 scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55612 --symbols 000001,AAPL --output artifacts/ui-graph-multi-symbol-market-summary-dedup-acceptance.json --timeout 60`
  - Result: `status=passed`, `000001` measured `35` nodes, `97` links, `overlap_pairs=1`, `near_edge_nodes=0`; `AAPL` measured `35` nodes, `98` links, `overlap_pairs=0`, `near_edge_nodes=0`.
- Browser visible-text raw-leak acceptance passed:
  - `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55612 --symbol AAPL --min-nodes 8 --min-links 6 --max-overlap-pairs 8 --max-near-edge-nodes 2 --min-community-labels 1 --min-visible-neighbors-after-click 1 --min-expansion-neighbor-delta 0 --output artifacts/ui-graph-visible-raw-text-seeded-layout-pass.json --timeout 60`
  - Result: `status=passed`, focus label `局部图 · 焦点 研究观点`, `raw_label_text_leaks=[]`, `visible_text_count=36`.
- Browser sparse-node click acceptance passed:
  - `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55612 --symbol AAPL --min-nodes 8 --min-links 6 --max-overlap-pairs 8 --max-near-edge-nodes 2 --min-community-labels 1 --min-visible-neighbors-after-click 1 --output artifacts/ui-graph-click-semantics-seeded-layout-pass.json --timeout 60`
  - Result: `status=passed`; clicked research node had `hidden_neighbors_before=0`, `focus_after` matched the clicked node, `visible_neighbors_after=1`, and `raw_label_text_leaks=[]`.
- Browser market-node raw-trace probe passed:
  - `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55612 --symbol AAPL --min-nodes 8 --min-links 6 --max-overlap-pairs 8 --max-near-edge-nodes 2 --min-community-labels 1 --min-visible-neighbors-after-click 1 --output artifacts/ui-graph-market-node-raw-trace-pass.json --timeout 60`
  - Result: `raw_text_probe.checked=true`, probed `market_data_summary:security_aapl_us`, and both `raw_text_probe.raw_label_text_leaks=[]` and `raw_label_text_leaks=[]`.
- Backend quality-center research-ID cleanup regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_does_not_flag_market_data_ids_as_raw_labels tests.test_system.SystemServiceTests.test_graph_quality_center_cleans_generic_research_ids tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions`
  - Result: passed; `vp_rr_...` and `srr_...` no longer appear as raw label leaks in quality snapshots.
- Backend display-structure quality regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_flags_star_shaped_graphs tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_graph_quality_center_cleans_generic_research_ids tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions`
  - Result: passed; true star-shaped graphs are flagged by `hub_dominance` / `leaf_ratio`, while multi-day market data fan-out is evaluated with the UI display aggregation model.
- Backend relationship-display label regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_uses_relationship_display_labels tests.test_system.SystemServiceTests.test_graph_quality_center_cleans_generic_research_ids tests.test_system.SystemServiceTests.test_graph_quality_center_flags_star_shaped_graphs tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model`
  - Result: passed; relationship rows with `listed_security` and `customer_candidate` quality labels render as `上市证券` and `客户候选`, with no raw label leaks.
- Backend/frontend relationship display projection regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_uses_relationship_display_labels tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_graph_quality_center_flags_star_shaped_graphs`
  - Result: passed; display structure counts one `customer_candidate` direct relationship edge while raw structure retains three relationship-record edges.
  - `python3 scripts/ui_static_check.py`
  - Result: passed; static contract now checks that frontend `company_relationships` rendering includes `subject_id` and `object_id` fallbacks.
- Current-code relationship direct-display runtime acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55640.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55640 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55640 --timeout 60`
  - Result: `created_count=49`, `status=seeded`, local-only Obsidian graph sample.
  - Browser matrix: `python3 scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55640 --symbols AAPL,NVDA,600519 --output artifacts/ui-graph-multi-symbol-direct-relationship-display-acceptance.json --timeout 90`
  - Result: `status=passed`, AAPL `36` nodes / `88` links, NVDA `33` / `75`, 600519 `24` / `53`; all cases had `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore passed.
  - AAPL layout: `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55640 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --check-focus-switch --output artifacts/ui-graph-layout-direct-relationship-display-acceptance.json --timeout 90`
  - Result: `status=passed`, `36` nodes / `88` links, `4` visible communities, `0` overlaps, `0` near-edge nodes, `raw_label_text_leaks=[]`, performance about `60 FPS / 1.5ms`, focus switch/trail/view controls/saved subgraph passed.
  - Quality center: `python3 scripts/graph_quality_center.py http://127.0.0.1:55640 --market A,U --limit 4 --output artifacts/graph-quality-center/direct-relationship-display-quality.json --timeout 60`
  - Result: `status=needs_attention` overall because thin samples still lack layers; AAPL `quality_gate.status=passed`. Display structure for thin listed-security samples folded raw relationship-record edges into `listed_security` display edges while `raw_structure` retained `HAS_COMPANY_RELATIONSHIP` / `RELATIONSHIP_SUBJECT` / `RELATIONSHIP_OBJECT`.
- Backend 13F holding label disambiguation regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_same_holder_labels tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_uses_relationship_display_labels`
  - Result: passed; same holder across AAPL/NVDA produces distinct labels and no duplicate-label finding.
  - `python3 scripts/ui_static_check.py`
  - Result: passed; static contract now requires `graphHoldingLabel` and the `13F 持仓 · ${holder}` label path.
- Backend/frontend issuer-security label disambiguation regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_uses_relationship_display_labels tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_same_holder_labels tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_issuer_and_security_labels`
  - Result: passed; issuer with `aliases=["AAPL"]`, security ticker `AAPL`, and multiple collection rows resolving to the same issuer identity produce one company node label and one security label, with no duplicate-label finding.
  - `python3 scripts/ui_static_check.py`
  - Result: passed; static contract now requires the frontend issuer alias fallback and `item.ticker || item.symbol || alias || item.name` path.
  - `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
  - Result: passed.
  - `python3 scripts/security_check.py .`
  - Result: passed; `ok=true`, `findings=[]`, `checked_files=360`.
  - `python3 scripts/check_handoffs.py`
  - Result: passed; checked `146` markdown handoff files.
  - `git diff --check`
  - Result: passed.
- Knowledge graph UI display-quality gate validation passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_ui_exposes_graph_source_input_queue tests.test_system.SystemServiceTests.test_ui_exposes_knowledge_graph_display_quality_gate`
  - Result: passed; UI static contract exposes the source queue and display-quality gate.
  - `python3 scripts/ui_static_check.py`
  - Result: passed; static check requires the graph quality-center UI hook, strict display thresholds, and DOM ids.
  - `python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`
  - Result: passed.
  - Browser smoke against isolated SQLite service on `55682` passed. The smoke monkey-patched `/api/graph/quality-center`, clicked `#checkKnowledgeGraphDisplayQuality`, captured a POST with `issuer_ids=["issuer_aapl"]`, `max_duplicate_labels=0`, `max_raw_label_leaks=0`, and `max_display_duplicate_edges=0`, and confirmed `重复展示标签` / `重复展示边` / `中心节点过载` rendered in `knowledgeGraphQualityGateRows`.
  - Artifact: `artifacts/ui-knowledge-graph-quality-gate-smoke.json`, local-only, ignored; valid for this machine/browser smoke only and not a production release artifact.
  - Result: passed.
- Knowledge graph UI remediation-action validation passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_gate_remediation_routes_duplicate_edges_to_reconcile tests.test_system.SystemServiceTests.test_graph_quality_center_api_contract_documents_strict_display_gate tests.test_system.SystemServiceTests.test_ui_exposes_knowledge_graph_display_quality_gate tests.test_system.SystemServiceTests.test_graph_source_actions_are_shared_by_quality_center_and_runner`
  - Result: passed; quality gate failures now expose dry-run remediation actions and the UI contract checks remediation rendering.
  - Browser smoke against isolated SQLite service on `55683` passed. The smoke monkey-patched `/api/graph/quality-center`, clicked `#checkKnowledgeGraphDisplayQuality`, and confirmed failed rows render `处理动作` for `/api/company-database/quality/reconcile`, `/api/graph/quality-center`, and `/api/graph/enrichment-runner`.
  - Artifact: `artifacts/ui-knowledge-graph-quality-remediation-smoke.json`, local-only, ignored; valid for this machine/browser smoke only and not a production release artifact.
- Derived relationship refactor regression passed:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_derived_relationships_plans_display_edges tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_graph_acceptance_fixture_supports_industry_relationship_filters tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network`
  - Result: passed; the extracted planner returns peer/upstream/downstream, 13F same-holder, and ownership-holder plans, and `/api/graph/query` still exposes `INDUSTRY_PEER`, `INDUSTRY_UPSTREAM_OF`, `INDUSTRY_DOWNSTREAM_OF`, `SAME_HOLDER_RELATED_COMPANY`, and active `shareholder` graph edges for existing graph acceptance fixtures.
  - `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
  - Result: passed after the refactor.
- Current-code relationship-filter browser matrix after derivation refactor:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55644.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55644 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55644 python3 -m app.server`
  - Command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55644 --output artifacts/ui-graph-relationship-filter-derived-refactor-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=10`, `failure_count=0`.
  - Covered: AAPL `listed_security`, `institution_coverage`, `industry_peer`, `upstream_of`, `downstream_of`, and `institutional_holder_key=0000102909`; NVDA `listed_security` and `institution_coverage`; 600519 `listed_security` and `institution_coverage`.
  - Acceptance-script adjustment: `scripts/ui_graph_layout_acceptance.py` now treats strong relationship-filter clicks as valid when focus switches, the clicked node enters `expandedIds`, and the required visible-neighbor count remains satisfied, even if the filtered visible subgraph shrinks instead of growing.
- Current-code relationship-filter browser matrix after 13F holder planner extraction:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55645.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55645 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55645 python3 -m app.server`
  - Command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55645 --output artifacts/ui-graph-relationship-filter-derived-holder-refactor-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=10`, `failure_count=0`.
  - The AAPL `institutional_holder_vanguard` case measured `39` nodes / `95` links and retained `SAME_HOLDER_RELATED_COMPANY` in the raw edge types through the layout acceptance gate.
- Current-code relationship-filter browser matrix after ownership-holder planner extraction:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55646.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55646 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55646 python3 -m app.server`
  - Command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55646 --output artifacts/ui-graph-relationship-filter-derived-ownership-refactor-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=11`, `failure_count=0`.
  - New covered case: AAPL `relationship_type=shareholder` with `ownership_holder_key=external_graph_acceptance_alpha_capital`; measured `36` nodes / `64` links, `raw_relationship_types=["shareholder"]`, `raw_edge_relationship_types=["shareholder"]`, and filter chip `股东: external_graph_acceptance_alpha_capital`.
- Current-code relationship-filter browser matrix after dataclass planner contract tightening:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55647.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55647 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55647 python3 -m app.server`
  - Command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55647 --output artifacts/ui-graph-relationship-filter-derived-dataclass-refactor-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=11`, `failure_count=0`.
  - Covered: AAPL `listed_security`, `institution_coverage`, `industry_peer`, `upstream_of`, `downstream_of`, `shareholder + ownership_holder_key=external_graph_acceptance_alpha_capital`, and `institutional_holder_key=0000102909`; NVDA `listed_security` and `institution_coverage`; 600519 `listed_security` and `institution_coverage`.
- Current-code dataclass planner focused gates:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_derived_relationships_plans_display_edges tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_graph_acceptance_fixture_supports_industry_relationship_filters tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_issuer_and_security_labels`
  - Result: passed.
  - `python3 -m py_compile app/*.py tests/*.py scripts/*.py`: passed.
  - `python3 scripts/ui_static_check.py`: passed.
  - `python3 scripts/check_handoffs.py`: passed; checked `146` markdown files.
  - `python3 scripts/security_check.py .`: passed; `ok=true`, `findings=[]`, `checked_files=360`.
  - `git diff --check`: passed.
- Current-code pointer-chain graph interaction acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55648.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55648 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55648 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55648 --timeout 60`
  - AAPL layout command: `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55648 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --check-focus-switch --output artifacts/ui-graph-layout-pointer-focus-acceptance.json --timeout 90`
  - AAPL layout result: `status=passed`, `36` nodes / `88` links, `3` community labels, `0` overlap pairs, `0` near-edge nodes, `raw_label_text_leaks=[]`, and `focus_switch.pointer_checked=true`.
  - Relationship matrix command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55648 --output artifacts/ui-graph-relationship-filter-pointer-focus-acceptance.json --timeout 90`
  - Relationship matrix result: `status=passed`, `case_count=11`, `failure_count=0`, covering AAPL listed/security/institution/industry/shareholder/13F holder filters plus NVDA and 600519 listing/institution filters.
  - Service was stopped after validation and port `55648` returned `ConnectionRefusedError`.
- Current-code strict display-label quality gate acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55649.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55649 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55649 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55649 --timeout 60`
  - Command: `python3 scripts/graph_quality_center.py http://127.0.0.1:55649 --market A,U --limit 4 --output artifacts/graph-quality-center/strict-display-label-quality.json --timeout 60`
  - Result: overall `status=needs_attention` because thin symbols still fail data-layer `layer_count`; AAPL `quality_gate.status=passed` with `thresholds.max_duplicate_labels=0`, `thresholds.max_raw_label_leaks=0`, `duplicate_labels=[]`, and `raw_label_leaks=[]`. 600519, 600809, and ASML had no duplicate/raw-label failures; their failures were `layer_count`.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_any_duplicate_or_raw_label tests.test_system.SystemServiceTests.test_graph_quality_center_does_not_flag_market_data_ids_as_raw_labels tests.test_system.SystemServiceTests.test_graph_quality_center_cleans_generic_research_ids tests.test_system.SystemServiceTests.test_graph_quality_center_uses_relationship_display_labels tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_same_holder_labels tests.test_system.SystemServiceTests.test_graph_quality_center_disambiguates_issuer_and_security_labels tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions`
  - Result: passed.
  - Service was stopped after validation and port `55649` returned `ConnectionRefusedError`.
- Current-code graph-quality diagnostic threshold override smoke:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55650.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55650 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55650 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55650 --timeout 60`
  - Command: `python3 scripts/graph_quality_center.py http://127.0.0.1:55650 --market A,U --limit 2 --max-duplicate-labels 2 --max-raw-label-leaks 3 --output artifacts/graph-quality-center/threshold-override-quality.json --timeout 60`
  - Result: artifact thresholds reflected the CLI payload: sampled rows had `quality_gate.thresholds.max_duplicate_labels=2` and `quality_gate.thresholds.max_raw_label_leaks=3`.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_script_writes_artifact tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_any_duplicate_or_raw_label tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions`
  - Result: passed; the script test captures the POST body and asserts `max_duplicate_labels=2`, `max_raw_label_leaks=3`.
  - Service was stopped after validation and port `55650` returned `ConnectionRefusedError`.
- Current-code quality-center API contract regression:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_get_route_uses_query_thresholds tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_api_contract_documents_strict_display_gate tests.test_system.SystemServiceTests.test_graph_quality_center_script_writes_artifact tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_any_duplicate_or_raw_label`
  - Result: passed; `docs/api-contracts.md` now includes `GET|POST /api/graph/quality-center`, `graph-quality-center-v1`, `max_duplicate_labels`, `max_raw_label_leaks`, `quality_gate`, `structure`, `raw_structure`, `automation_allowed=false`, `live_execution_allowed=false`, and `usage_boundary`. The GET route regression confirms query-string threshold overrides reach `quality_gate.thresholds`.
- Current-code graph-quality threshold contract regression:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_get_route_uses_query_thresholds tests.test_system.SystemServiceTests.test_graph_quality_center_thresholds_preserve_explicit_zero_values tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_any_duplicate_or_raw_label tests.test_system.SystemServiceTests.test_graph_quality_center_flags_star_shaped_graphs tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model`
  - Result: passed; threshold parsing now preserves explicit string `0` overrides and keeps graph-query filters plus `quality_gate.thresholds` on the same `GraphQualityThresholds` contract.
- Current-code fixture-boundary and browser matrix acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55652.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55652 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55652 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55652 --timeout 60`
  - Fixture: `python3 scripts/graph_acceptance_fixture.py http://127.0.0.1:55652 --output artifacts/graph-acceptance-fixture-current-code-55652.json --timeout 60`
  - Quality center: `python3 scripts/graph_quality_center.py http://127.0.0.1:55652 --market A,U --limit 8 --output artifacts/graph-quality-center/current-code-55652-fixture-scoped-quality.json --timeout 60`
  - Result: quality center stayed `needs_attention` for real data-layer gaps, but display gates held: sampled quality rows had `duplicate_labels=[]` and `raw_label_leaks=[]`; AAPL/NVDA/MSFT `quality_gate.status=passed`; `universe.skipped_by_market.U=3`, proving local fixture-only securities `AAPL-P/AAPL-U/AAPL-D` were excluded from default production-universe sampling.
  - Browser matrix: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55652 --output artifacts/ui-graph-relationship-filter-current-code-55652-full.json --timeout 90`
  - Result: passed, `case_count=11`, `failure_count=0`, covering listed security, institution coverage, industry peer/upstream/downstream, shareholder holder, and 13F same-holder filters.
  - Note: an earlier diagnostic run with `--skip-industry-fixture` failed the institution/shareholder cases because the fixture relationships were intentionally absent; do not use that artifact as final browser acceptance evidence.
  - Service was stopped after validation and port `55652` returned `KeyboardInterrupt`.
- Current-code skip-fixture relationship-filter acceptance contract:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55653.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55653 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55653 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55653 --timeout 60`
  - Command: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55653 --output artifacts/ui-graph-relationship-filter-current-code-55653-skip-fixture.json --timeout 90 --skip-industry-fixture`
  - Result: passed with `case_count=7`, `skipped_case_count=4`, and `failure_count=0`. Skipped cases were the fixture-only `institution_coverage` cases for AAPL/NVDA/600519 and the AAPL Alpha shareholder holder case.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_filter_matrix_skips_fixture_only_cases_when_fixture_disabled tests.test_system.SystemServiceTests.test_graph_acceptance_fixture_supports_industry_relationship_filters`
  - Result: passed. The script also now supports package import from tests while retaining direct CLI sibling-import fallback.
  - Service was stopped after validation and port `55653` returned `KeyboardInterrupt`.
- Current-code duplicate display-edge gate acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55655.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55655 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55655 python3 -m app.server`
  - Seed + fixture + quality center: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55655 --timeout 60`; `python3 scripts/graph_acceptance_fixture.py http://127.0.0.1:55655 --output artifacts/graph-acceptance-fixture-current-code-55655.json --timeout 60`; `python3 scripts/graph_quality_center.py http://127.0.0.1:55655 --market A,U --limit 8 --output artifacts/graph-quality-center/current-code-55655-display-duplicate-quality.json --timeout 60`
  - Result: overall `status=needs_attention` for real `layer_count` gaps, but `display_duplicate_failures=0`; AAPL, MSFT, and NVDA had `quality_gate.status=passed`; `universe.skipped_by_market.U=3`.
  - Relationship matrix: `python3 scripts/ui_graph_relationship_filter_acceptance.py http://127.0.0.1:55655 --output artifacts/ui-graph-relationship-filter-current-code-55655-full.json --timeout 90`
  - Result: passed with `case_count=11`, `failure_count=0`, `skipped_case_count=0`.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_display_duplicate_edges tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_graph_quality_center_thresholds_preserve_explicit_zero_values tests.test_system.SystemServiceTests.test_graph_quality_center_get_route_uses_query_thresholds`
  - Result: passed.
  - Final local checks after roadmap/handoff update: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_display_duplicate_edges tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_graph_quality_center_api_contract_documents_strict_display_gate tests.test_system.SystemServiceTests.test_graph_acceptance_fixture_supports_industry_relationship_filters tests.test_system.SystemServiceTests.test_relationship_filter_matrix_skips_fixture_only_cases_when_fixture_disabled`; `python3 -m py_compile app/*.py tests/*.py scripts/*.py`; `python3 scripts/check_handoffs.py`; `python3 scripts/ui_static_check.py`; `python3 scripts/security_check.py .`; `git diff --check`.
  - Final local check result: all passed; port `55655` returned `ConnectionRefusedError` after service shutdown.
- Current-code display market-data edge deduplication acceptance on PostgreSQL service:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55656 .venv/bin/python -m app.server`
  - Quality center: `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55656 --market A,U --limit 20 --output artifacts/graph-quality-center/display-quality-after-event-execute-50-display-dedup-fixed.json --timeout 120`
  - Result: `status=needs_attention`, `processed_count=20`, all 20 sampled rows had `company_event=1`; `display_duplicate_edges` failures dropped to `0`, and remaining quality failures were only `layer_count`.
  - Browser matrix: `.venv/bin/python scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55656 --symbols 000001,000002,000004 --output artifacts/ui-graph-multi-symbol-display-dedup-event-layer-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=3`, `failure_count=0`; 000001 measured `22` nodes / `38` links, 000002 and 000004 measured `21` nodes / `35` links, all with `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore count `4`.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_graph_quality_center_default_gate_rejects_display_duplicate_edges tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_direct_relationship_display_edges tests.test_system.SystemServiceTests.test_graph_quality_center_flags_star_shaped_graphs`
  - Result: passed; the market-data display-model regression now asserts `structure.duplicate_edge_count == 0`, while the duplicate company-relationship regression still asserts duplicate fact edges fail the gate.
- Current-code layer-specific action acceptance on PostgreSQL service:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55657 .venv/bin/python -m app.server`
  - Quality center: `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55657 --market A,U --limit 20 --output artifacts/graph-quality-center/display-quality-layer-specific-actions-55657.json --timeout 120`
  - Result: `status=needs_attention`, `processed_count=20`, quality failures were only `layer_count`. All 20 sampled rows had missing `shareholder_holding`, `document`, `evidence`, `research_report`, and `viewpoint`, and all 20 received matching actions: `import_13f_holdings`, `ingest_source_documents`, `extract_and_link_evidence`, `structure_research_reports`, and `structure_or_register_viewpoints`. `build_company_events` and `build_company_relationships` were not recommended for this post-event/post-relationship sample.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions tests.test_system.SystemServiceTests.test_graph_quality_center_actions_follow_remaining_missing_layers tests.test_system.SystemServiceTests.test_graph_quality_center_get_route_uses_query_thresholds tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model`
  - Result: passed; the new regression verifies that after event and relationship layers are present, enhancement actions no longer point back to those builders and instead cover holdings, documents, evidence, research reports, and viewpoints.
- Current-code chain-node canonical display acceptance on PostgreSQL service:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55662 .venv/bin/python -m app.server`
  - Browser graph acceptance: `.venv/bin/python scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55662 --symbol AAPL --scope global --min-nodes 20 --min-links 30 --min-community-labels 2 --max-overlap-pairs 80 --max-near-edge-nodes 2 --expect-performance-mode standard --max-chain-node-splits 0 --output artifacts/ui-graph-layout-canonical-chain-nodes-55662.json --timeout 60`
  - Result: passed with `chain_node_splits=[]`, 21 visible nodes, 44 visible links, 29 full nodes, 52 full links, 4 community labels, 0 overlap pairs, 0 near-edge nodes, and about 60 FPS.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_canonical_chain_node_ids tests.test_system.SystemServiceTests.test_graph_quality_center_structure_uses_display_market_data_model tests.test_system.SystemServiceTests.test_query_graph_scopes_company_positions_to_focus_issuer tests.test_system.SystemServiceTests.test_graph_quality_center_reports_gaps_and_actions`
  - Result: passed; `test_graph_quality_center_structure_uses_canonical_chain_node_ids` proves display/raw structure use the scoped chain-node identity instead of splitting a chain node into two nodes.
- Current-code structured research display acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_research_55664.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_research_objects_55664 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55664 .venv/bin/python -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55664 --output artifacts/obsidian-knowledge-graph-seed-research-layer-55664.json --timeout 30`
  - API probe: `/api/graph/query?issuer_id=issuer_aapl&security_id=security_aapl_us&market_data_limit=20` returned `structured_research_reports=1`, `report_viewpoints=1`, and research edges `COVERED_BY_REPORT`, `REPORT_HAS_VIEWPOINT`, and `VIEWPOINT_ON_COMPANY`.
  - Browser graph acceptance: `.venv/bin/python scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55664 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-raw-structured-reports 1 --min-visible-knowledge-types 2 --max-overlap-pairs 14 --max-near-edge-nodes 2 --forbid-filter-chip "证券:" --max-chain-node-splits 0 --output artifacts/ui-graph-layout-structured-research-55664.json --timeout 60`
  - Result: passed with `raw_structured_reports=1`, visible node type `research`, 28 visible nodes, 83 visible links, 4 community labels, 5 industry nodes, 0 overlap pairs, 0 near-edge nodes, and `chain_node_splits=[]`.
  - Focused regression: `python3 -m unittest tests.test_system.SystemServiceTests.test_ui_graph_model_consumes_structured_research_reports tests.test_system.SystemServiceTests.test_graph_quality_center_structure_links_structured_report_viewpoints tests.test_system.SystemServiceTests.test_graph_quality_center_cleans_generic_research_ids tests.test_system.SystemServiceTests.test_obsidian_knowledge_graph_seed_creates_multi_dimension_network`
  - Result: passed; this verifies UI consumption of `structured_research_reports`, the `research_report_id` join, and quality-center structure handling for `REPORT_HAS_VIEWPOINT`.
- Current-code issuer/security label disambiguation runtime acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55643.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55643 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55643 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55643 --timeout 60`
  - Result: `created_count=49`, `status=seeded`, local-only Obsidian graph sample.
  - Quality center: `python3 scripts/graph_quality_center.py http://127.0.0.1:55643 --market A,U --limit 4 --output artifacts/graph-quality-center/issuer-security-label-disambiguation-quality.json --timeout 60`
  - Result: AAPL `quality_gate.status=passed`, `duplicate_labels=[]`, `raw_label_leaks=[]`. This specifically confirms the prior duplicate naked `AAPL` finding is removed.
  - AAPL layout: `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55643 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --check-focus-switch --output artifacts/ui-graph-layout-issuer-security-label-disambiguation-acceptance.json --timeout 90`
  - Result: `status=passed`, `36` nodes / `88` links, `4` visible communities, `0` overlaps, `0` near-edge nodes, `raw_label_text_leaks=[]`, performance about `60 FPS / 1.2ms`, focus switch/trail/view controls/saved subgraph passed.
- Current-code 13F holding label runtime acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_55641.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_objects_55641 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55641 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55641 --timeout 60`
  - Result: `created_count=49`, `status=seeded`, local-only Obsidian graph sample.
  - Quality center: `python3 scripts/graph_quality_center.py http://127.0.0.1:55641 --market A,U --limit 4 --output artifacts/graph-quality-center/holding-label-disambiguation-quality.json --timeout 60`
  - Result: AAPL `quality_gate.status=passed`; duplicate labels no longer include naked `Vanguard Group Inc.` or `Berkshire Hathaway Inc.` holding nodes. Remaining duplicate label was `AAPL`, caused by issuer/security same ticker disambiguation policy rather than same-holder ambiguity.
  - AAPL layout: `python3 scripts/ui_graph_layout_acceptance.py http://127.0.0.1:55641 --symbol AAPL --scope local --min-nodes 26 --min-links 60 --min-community-labels 3 --min-visible-communities 3 --min-industry-nodes 5 --min-raw-knowledge-nodes 5 --min-visible-knowledge-types 2 --max-overlap-pairs 12 --max-near-edge-nodes 2 --check-focus-switch --output artifacts/ui-graph-layout-holding-label-disambiguation-acceptance.json --timeout 90`
  - Result: `status=passed`, `36` nodes / `88` links, `4` visible communities, `0` overlaps, `0` near-edge nodes, `raw_label_text_leaks=[]`, performance about `60 FPS / 1.4ms`.
- Current-code PostgreSQL quality sample after display-structure gate:
  - `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55630 --market A,U --limit 8 --output artifacts/graph-quality-center/latest.json --timeout 60`
  - Result: `status=needs_attention`, `processed_count=8`. AAPL display structure measured `node_count=11`, `valid_edge_count=11`, `hub_edge_share=0.6364`, `leaf_ratio=0.6364`; raw structure still shows `HAS_MARKET_DATA=20`. 600519 display structure measured `node_count=6`, `valid_edge_count=6`, `hub_edge_share=0.5`, `leaf_ratio=0.3333`. Remaining failures are `community_count`, `layer_count`, and sparse `edge_density` for very thin issuers, not raw market-data fan-out.
- Current PostgreSQL data-state correction for display-quality samples:
  - Direct database check showed the current `ai_quant.records` store had `company_positions=0` and no `company_relationships`, contradicting older T-567 artifact expectations for this local DB state.
  - `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant .venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:55630 --execute --market A,U --limit 100 --batch-size 50 --resume-state artifacts/full-knowledge-graph/state-display-quality.json --output artifacts/full-knowledge-graph/display-quality-batch-100.json`
  - Result: `status=executed`, `processed_count=50`, `failed_count=0`, `layer_coverage.industry_position=50`, `layer_coverage.listed_security=50`.
  - Targeted service-layer backfill for `600519` and `AAPL` created their `listed_security` relationships and `CompanyPosition` rows.
- Current-code targeted quality sample after sample data correction:
  - Wrote `artifacts/graph-quality-center/display-quality-targeted-symbols.json`.
  - Result: `processed_count=2`, both `600519` and `AAPL` have `company_profile=1`, `industry_position=1`, `company_relationship=1`; both only fail `layer_count` because holding/document/evidence/event/research layers remain missing. 600519 display structure: `node_count=11`, `valid_edge_count=14`, `hub_edge_share=0.3571`, `leaf_ratio=0.1818`. AAPL display structure: `node_count=16`, `valid_edge_count=19`, `hub_edge_share=0.3684`, `leaf_ratio=0.4375`.
- Browser matrix after sample data correction passed:
  - `.venv/bin/python scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55630 --symbols AAPL,600519 --output artifacts/ui-graph-multi-symbol-display-structure-acceptance.json --timeout 60`
  - Result: `status=passed`, `case_count=2`, AAPL measured `28` nodes / `38` links, 600519 measured `23` nodes / `35` links, both `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore passed.
- Current PostgreSQL A/U base graph correction completed:
  - `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant .venv/bin/python scripts/backfill_full_knowledge_graph.py http://127.0.0.1:55630 --execute --market A,U --batch-size 500 --resume --resume-state artifacts/full-knowledge-graph/state-display-quality.json --output artifacts/full-knowledge-graph/display-quality-full-run.json`
  - Repeated resumable batches completed `5207/5207` current A/U universe targets with `failed_count=0`.
  - Direct DB confirmation: `company_positions=5207`, `company_relationships=5207`, `industry_chains=4`, `issuers=5208`, `securities=5208`; all generated positions are `needs_review`.
  - State/artifacts: `artifacts/full-knowledge-graph/state-display-quality.json`, `artifacts/full-knowledge-graph/display-quality-full-run.json`.
- Current-code quality center after full base correction:
  - `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55630 --market A,U --limit 50 --output artifacts/graph-quality-center/latest.json --timeout 90`
  - Result: `status=needs_attention`, `processed_count=50`, `ready_count=0`, `passed_quality_count=0`. For the first sample rows, each now has `company_profile=1`, `industry_position=1`, `company_relationship=1`; quality failures are `layer_count` only. Top missing layers remain `shareholder_holding`, `document`, `evidence`, `company_event`, `research_report`, and `viewpoint`.
- Browser matrix after full base correction passed:
  - `.venv/bin/python scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55630 --symbols 000001,000002,600519,AAPL --output artifacts/ui-graph-multi-symbol-display-quality-full-backfill-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=4`; 000001 and 000002 measured `20` nodes / `31` links, 600519 measured `23` nodes / `35` links, AAPL measured `28` nodes / `38` links; all had `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore passed.
- Current-code community-balance quality-center acceptance on isolated SQLite service:
  - Service: `AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=/tmp/ai_quant_graph_quality_balance_55686.sqlite AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_graph_quality_balance_objects_55686 AI_QUANT_SEARCH_BACKEND=local AI_QUANT_PORT=55686 python3 -m app.server`
  - Seed: `python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:55686 --output artifacts/obsidian-knowledge-graph-seed-community-balance-55686.json --timeout 30`
  - Result: `created_count=49`, `status=seeded`, local-only Obsidian graph sample.
  - Quality center + browser matrix: `python3 scripts/graph_quality_center.py http://127.0.0.1:55686 --market A,U --limit 4 --browser-matrix --symbols AAPL,NVDA,MSFT,600519 --min-browser-visible-communities 3 --min-browser-community-spread-ratio 0.12 --output artifacts/graph-quality-center/community-balance-browser-55686.json --timeout 120`
  - Result: quality-center `status=needs_attention` because non-AAPL sampled rows still fail `layer_count`, but backend community-balance metrics passed. AAPL `quality_gate.status=passed`, `structure.max_community_node_share=0.3784`, and `community_counts=[company 14, evidence 11, industry 5, portfolio 5, research 2]`.
  - Browser matrix result: `status=passed`, `case_count=4`, `failure_count=0`. AAPL measured `28` nodes / `83` links / `community_spread_ratio=0.5686`; NVDA `27` / `74` / `0.4736`; MSFT `23` / `62` / `0.475`; 600519 `17` / `47` / `0.6597`. All four had `overlap_pairs=0`, `near_edge_nodes=0`, and at least three visible communities.
  - Service was stopped after validation and port `55686` returned `KeyboardInterrupt`.

## Next Recommended Action

The current DB base graph is no longer empty. Next, prioritize real source-backed enrichment layers: holding imports, document ingestion, evidence extraction, company events, structured reports, and viewpoints. Re-run quality center after each data run:

```bash
.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55630 --market A,U --limit 50 --output artifacts/graph-quality-center/latest.json
```
