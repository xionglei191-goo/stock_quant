# Handoff: T-569 Graph Enrichment Runner

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-30
- Last agent: Codex
- Branch/worktree: main
- Related tasks: T-569

## Scope

- In scope:
  - Batch planning and execution for graph event/relationship enrichment.
  - Priority-layer selection from graph quality gaps.
  - Local artifact and resumable state output.
  - Review-gated candidate event/relationship production.
- Out of scope:
  - Automatic candidate approval.
  - New database schema.
  - External paid data connectors.
  - Research-report opinion promotion to fact.
  - Broker integration or live trading.

## Objective

Turn T-568 graph quality gaps into a dry-run-first, resumable enrichment runner that can plan and optionally execute local event/relationship candidate generation for shallow company graphs.

## Background

T-567 created baseline graph scaffolding for A/U in-scope stocks. T-568 added a quality center that reports missing graph layers and enhancement actions. T-569 creates the batch runner needed to apply those actions safely across a universe slice.

## Problem Statement

Graph quality gaps were visible but not operationalized into a recoverable batch process. Running event and relationship builders manually per symbol is not enough for thousands of stocks, and execute paths must remain explicit and review-gated.

## Expected Deliverables

- Add `app/service_modules/graph_enrichment_runner.py`.
- Add `GET|POST /api/graph/enrichment-runner`.
- Add `scripts/graph_enrichment_runner.py`.
- Extend full graph universe selection with `issuer_ids`, `security_ids`, and `symbols` filters.
- Add focused tests for dry-run planning, execute review-gated writes, and CLI artifact/state writing.
- Update `README.md` and `tasks/todo.md`.

## Current Findings

- The runner reuses `graph_quality_center`, `build_company_events`, and `build_company_relationships`.
- Default mode is dry-run.
- `execute=true` writes local event/relationship candidate data only.
- Company relationship candidates remain `review_status=needs_review` and `relationship_status=unknown`.
- Structured disclosure events remain `review_status=needs_review`.
- The CLI writes both a report artifact and a resumable state file.
- Dry-run CLI state does not mark issuer IDs as completed; only successful execute rows are added to `completed_issuer_ids`.
- Resume behavior now passes completed issuer IDs to the service, and the service honors `skip_issuer_ids` with `resume_skipped_count`.
- Empty target universes now return `status=no_targets` and a `target_universe` global failure; the CLI exits non-zero for that state.
- Each processed row now includes `candidate_activity` for planned/created event and relationship candidates.
- If a row has no planned, created, or review-candidate activity, its status is `no_candidate_sources`; CLI state does not add that issuer to `completed_issuer_ids` even in an execute report, so future runs can pick it up after new local materials arrive.
- Default planning now uses `quality_mode=fast`, which checks cheap layer counts instead of running full `graph_quality_center` before/after every row. Full quality before/after is still available through `--quality-mode full` for small diagnostic runs.
- The runner now calls builders only for actual missing/thin layers. If `company_relationship` is already present, the relationship builder is skipped unless `--force-build` is passed. This prevents current large local stores from timing out on unnecessary relationship dry-runs after T-568/T-567 base graph correction.
- The runner now emits `layer_action_plan` and `manual_input_required_layers` for source-backed layers that cannot be safely fabricated by a builder: `document`, `evidence`, `shareholder_holding`, `research_report`, and `viewpoint`.
- Rows that only need source inputs are marked `waiting_for_source_inputs`, not `executed` or `no_candidate_sources`; CLI resume state must not treat them as completed.
- The runner now emits a top-level `source_input_queue` (`graph-source-input-queue-v1`) that groups source-backed work by layer. Each queue layer carries endpoint/fallback/secondary endpoint, `required_source_fields`, `target_count`, and bounded target samples, so operators do not need to scrape every row's `layer_action_plan` to collect missing documents, holdings, evidence, research reports, or viewpoints.

### SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module used: yes, `app/service_modules/graph_enrichment_runner.py`.
- Facade behavior protected by: focused tests for dry-run, execute review-gated writes, and CLI artifact/state writing.
- API/storage/UI/paper-only impact: one new API endpoint; no storage schema change; no direct UI change; response contract now includes `source_input_queue` for local/public/provided source collection; no broker or live-trading behavior.

## Proposed Work Plan

1. Add enrichment runner domain module.
2. Add facade and API route.
3. Add CLI with artifact and state output.
4. Add focused regressions.
5. Update README, roadmap, and handoff.
6. Run validation.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_dry_run_plans_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_execute_writes_review_gated_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_marks_completed_state
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_plans_manual_input_layers
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Dependencies

- `app/service_modules/graph_quality_center.py`.
- Existing company event builder.
- Existing company relationship builder.
- Existing production universe selector.

## Blockers

- None.

## Risks

- Large universe execute runs can create many `needs_review` candidates; use small `--batch-size` and inspect artifacts first.
- Candidate quality still depends on available local disclosure/evidence text and builder heuristics.
- Candidate approval remains a separate review workflow.

## Handoff Checklist

- [x] Code changes completed.
- [x] API route added.
- [x] CLI added.
- [x] Focused tests added.
- [x] README updated.
- [x] Roadmap updated.
- [x] Handoff created.

## Evidence

- `app/service_modules/graph_enrichment_runner.py`: batch enrichment module.
- `scripts/graph_enrichment_runner.py`: CLI runner.
- `tests/test_system.py`: focused regressions.
- `app/service_modules/knowledge_graph_bulk.py`: precise `issuer_ids`/`security_ids`/`symbols` universe filters.
- Focused unit validation passed:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_dry_run_plans_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_execute_writes_review_gated_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_marks_completed_state
```

- Resume regression passed:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_respects_skip_issuer_ids tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_marks_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_dry_run_plans_candidates
```

- Fast-mode and relationship-skip regression passed:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_graph_enrichment_runner_dry_run_plans_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_execute_writes_review_gated_candidates tests.test_system.SystemServiceTests.test_graph_enrichment_runner_respects_skip_issuer_ids tests.test_system.SystemServiceTests.test_graph_enrichment_runner_no_targets_is_not_success tests.test_system.SystemServiceTests.test_graph_enrichment_runner_marks_no_candidate_sources tests.test_system.SystemServiceTests.test_graph_enrichment_runner_skips_relationship_builder_when_layer_present tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_dry_run_does_not_mark_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_marks_completed_state tests.test_system.SystemServiceTests.test_graph_enrichment_runner_script_execute_does_not_complete_no_candidate_sources
```

- Current-code isolated service smoke passed on port `55610`:
  - `python3 scripts/graph_quality_center.py http://127.0.0.1:55610 --market A,U --limit 1 --output artifacts/graph-quality-center/current-code-smoke.json --timeout 20`
  - `python3 scripts/graph_enrichment_runner.py http://127.0.0.1:55610 --market A,U --limit 1 --batch-size 1 --output artifacts/graph-enrichment-runner/current-code-smoke.json --resume-state artifacts/graph-enrichment-runner/current-code-smoke-state.json --timeout 20`
  - Both returned valid schema/status. The isolated SQLite smoke had no universe rows, so `processed_count=0` is expected.
- Current-code no-target smoke passed on port `55611`: `scripts/graph_enrichment_runner.py` returned `status=no_targets` and exited with code `1`.
- Current-code PostgreSQL sample smoke passed on port `55612`:
  - Existing long-running `http://127.0.0.1:8000` returned `404` for the new graph endpoints because it was an older process, so validation used a restarted current-code service on `55612` pointed at the same PostgreSQL DSN.
  - `python3 scripts/graph_enrichment_runner.py http://127.0.0.1:55612 --market A,U --limit 5 --batch-size 2 --output artifacts/graph-enrichment-runner/postgres-current-code-sample-after-labels.json --resume-state artifacts/graph-enrichment-runner/postgres-current-code-sample-after-labels-state.json --timeout 60`
  - Result: `status=dry_run`, `processed_count=2`, `failed_count=0`, event planned `6`, relationship planned `5`, review candidates `3`, and state `completed_issuer_ids=[]`, `dry_run_items_not_completed=2`.
- Current-code PostgreSQL fast-mode relationship skip passed on port `55630` after base graph correction:
  - `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55630 --market A,U --limit 50 --batch-size 20 --priority-layers company_event,company_relationship --quality-mode fast --no-events --output artifacts/graph-enrichment-runner/display-quality-relationship-skip-dry-run.json --timeout 30`
  - Result: `status=dry_run`, `processed_count=20`; all sampled rows had `relationship_result.status=skipped_no_company_relationship_gap`, confirming the runner no longer calls the relationship builder when the base relationship layer is already present.
- Current-code PostgreSQL event small-batch execution passed:
  - Dry-run: `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55630 --market A,U --limit 10 --batch-size 5 --priority-layers company_event --quality-mode fast --no-relationships --output artifacts/graph-enrichment-runner/display-quality-event-dry-run.json --timeout 60`
  - Result: `processed_count=5`, `event_totals.planned=5`.
  - Execute: `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55630 --market A,U --limit 10 --batch-size 5 --priority-layers company_event --quality-mode fast --no-relationships --execute --output artifacts/graph-enrichment-runner/display-quality-event-execute-5.json --timeout 60`
  - Result: `processed_count=5`, `event_totals.created=5`; events remain local/review-gated.
- Current-code quality and browser checks after event execution passed:
  - `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55630 --market A,U --limit 10 --output artifacts/graph-quality-center/display-quality-after-event-execute-5.json --timeout 90`
  - Result: the first five samples now have `company_event=1`; remaining missing layers are holding, document, evidence, research report, and viewpoint.
  - `.venv/bin/python scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55630 --symbols 000001,000002,000004 --output artifacts/ui-graph-multi-symbol-display-quality-event-execute-acceptance.json --timeout 90`
  - Result: `status=passed`; 000001 measured `22` nodes / `37` links, 000002 and 000004 measured `21` nodes / `34` links, all with `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore passed.
- Current-code PostgreSQL event-layer expansion probe on port `55656`:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55656 .venv/bin/python -m app.server`
  - Attempted command: `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55656 --market A,U --limit 100 --batch-size 50 --priority-layers company_event --quality-mode fast --no-relationships --execute --output artifacts/graph-enrichment-runner/display-quality-event-execute-50.json --resume-state artifacts/graph-enrichment-runner/display-quality-event-execute-50-state.json --timeout 120`
  - Result: client timed out before receiving the API response, so no runner report/state artifact was written for this attempt. The service stayed healthy but logged a `BrokenPipeError` when writing to the closed client socket.
  - Follow-up quality center: `.venv/bin/python scripts/graph_quality_center.py http://127.0.0.1:55656 --market A,U --limit 20 --output artifacts/graph-quality-center/display-quality-after-event-execute-50-display-dedup-fixed.json --timeout 120`
  - Result: 20/20 sampled rows now have `company_event=1`; remaining missing layers are `shareholder_holding`, `document`, `evidence`, `research_report`, and `viewpoint`.
  - Browser matrix: `.venv/bin/python scripts/ui_graph_multi_symbol_acceptance.py http://127.0.0.1:55656 --symbols 000001,000002,000004 --output artifacts/ui-graph-multi-symbol-display-dedup-event-layer-acceptance.json --timeout 90`
  - Result: `status=passed`, `case_count=3`, `failure_count=0`; 000001 measured `22` nodes / `38` links, 000002 and 000004 measured `21` nodes / `35` links, all with `overlap_pairs=0`, `near_edge_nodes=0`, and saved subgraph restore count `4`.
  - Operational note: keep event enrichment in smaller resumable batches (`--batch-size 5` to `20`) or raise timeout before attempting larger synchronous execute runs.
- Current-code PostgreSQL manual-layer planning dry-run on port `55658`:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55658 .venv/bin/python -m app.server`
  - Command: `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55658 --market A,U --limit 20 --batch-size 20 --priority-layers document,evidence,shareholder_holding,research_report,viewpoint --quality-mode fast --no-events --no-relationships --output artifacts/graph-enrichment-runner/display-quality-manual-layer-plan-55658.json --resume-state artifacts/graph-enrichment-runner/display-quality-manual-layer-plan-55658-state.json --timeout 90`
  - Result: `status=dry_run`, `processed_count=20`, `manual_input_required_count=20`, `failed_count=0`; all rows were `waiting_for_source_inputs`.
  - Planned actions covered all remaining source-backed layers: `ingest_source_documents`, `extract_and_link_evidence`, `import_13f_holdings`, `structure_research_reports`, and `structure_or_register_viewpoints`.
  - Artifact: `artifacts/graph-enrichment-runner/display-quality-manual-layer-plan-55658.json` is local-only planning evidence. It does not prove production/staging release readiness.
  - Operational note: this path intentionally does not fake-write document/evidence/holding/report/viewpoint data. Use the emitted source endpoints to ingest real local/public/provided material, then rerun quality center and browser acceptance.
- Current-code PostgreSQL source-input queue dry-run on port `55665`:
  - Service: `AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant AI_QUANT_PORT=55665 .venv/bin/python -m app.server`
  - Command: `.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55665 --market A,U --limit 8 --batch-size 8 --priority-layers document,evidence,shareholder_holding,research_report,viewpoint --quality-mode fast --no-events --no-relationships --output artifacts/graph-enrichment-runner/source-input-queue-55665.json --resume-state artifacts/graph-enrichment-runner/source-input-queue-55665-state.json --timeout 90`
  - Result: `status=dry_run`, `processed_count=8`, `manual_input_required_count=8`, `source_input_queue.status=needs_source_inputs`, `layer_count=5`, `target_count=40`, `unique_target_count=8`.
  - Queue layers: `document` -> `/api/ingestion/documents`; `evidence` -> `/api/evidence/extract` plus `/api/graph/knowledge-network/evidence-links/backfill`; `shareholder_holding` -> `/api/13f/filings/parse` plus `/api/13f/holdings`; `research_report` -> `/api/research-reports/structure`; `viewpoint` -> `/api/research-reports/structure` plus `/api/research-report-viewpoints`.
  - Artifact: `artifacts/graph-enrichment-runner/source-input-queue-55665.json` is local-only queue evidence. It proves queue generation, not that source materials have been collected or ingested.

## Next Recommended Action

Run event enrichment in small resumable batches, then route candidates through review. After the 20-sample event layer is present, the next graph-quality bottleneck is source-backed holding/document/evidence/research-report/viewpoint layers. Use the manual-layer planning mode to produce source-input queues, ingest real local/public/provided source material, then rerun quality center and browser acceptance. Only use `--force-build` when deliberately re-running a builder for an already-present layer:

```bash
.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55630 \
  --market A,U --limit 100 --batch-size 20 \
  --priority-layers company_event \
  --quality-mode fast \
  --no-relationships \
  --output artifacts/graph-enrichment-runner/latest.json
```

For remaining source-backed layers:

```bash
.venv/bin/python scripts/graph_enrichment_runner.py http://127.0.0.1:55658 \
  --market A,U --limit 20 --batch-size 20 \
  --priority-layers document,evidence,shareholder_holding,research_report,viewpoint \
  --quality-mode fast \
  --no-events \
  --no-relationships \
  --output artifacts/graph-enrichment-runner/latest-manual-layer-plan.json
```
