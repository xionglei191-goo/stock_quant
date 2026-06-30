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

## Next Recommended Action

Run the quality center against the local long-running service and use the highest-count missing layers to prioritize document, event, relationship, holding, and research backfills:

```bash
python3 scripts/graph_quality_center.py http://127.0.0.1:8000 --market A,U --limit 50 --output artifacts/graph-quality-center/latest.json
```
