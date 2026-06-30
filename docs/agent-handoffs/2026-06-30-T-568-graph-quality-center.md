# Handoff: T-568 Graph Quality Center

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-30
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
- Click-expansion acceptance distinguishes true expansion targets from sparse/leaf nodes: nodes with hidden neighbors must reveal growth, while nodes without hidden neighbors are accepted when click focus, selection, and at least one existing visible neighbor remain stable.

### SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module used: yes, `app/service_modules/graph_quality_center.py`.
- Facade behavior protected by: focused tests for API gap/action output, enrichment dry-run no-write behavior, and CLI artifact writing.
- API/storage/UI/paper-only impact: one new API endpoint; no storage schema change; no direct UI change; no broker or live-trading behavior.

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

## Next Recommended Action

Run the quality center against the local long-running service and use the highest-count missing layers to prioritize document, event, relationship, holding, and research backfills:

```bash
python3 scripts/graph_quality_center.py http://127.0.0.1:8000 --market A,U --limit 50 --output artifacts/graph-quality-center/latest.json
```
