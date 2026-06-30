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

### SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module used: yes, `app/service_modules/graph_enrichment_runner.py`.
- Facade behavior protected by: focused tests for dry-run, execute review-gated writes, and CLI artifact/state writing.
- API/storage/UI/paper-only impact: one new API endpoint; no storage schema change; no direct UI change; no broker or live-trading behavior.

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

- Current-code isolated service smoke passed on port `55610`:
  - `python3 scripts/graph_quality_center.py http://127.0.0.1:55610 --market A,U --limit 1 --output artifacts/graph-quality-center/current-code-smoke.json --timeout 20`
  - `python3 scripts/graph_enrichment_runner.py http://127.0.0.1:55610 --market A,U --limit 1 --batch-size 1 --output artifacts/graph-enrichment-runner/current-code-smoke.json --resume-state artifacts/graph-enrichment-runner/current-code-smoke-state.json --timeout 20`
  - Both returned valid schema/status. The isolated SQLite smoke had no universe rows, so `processed_count=0` is expected.
- Current-code no-target smoke passed on port `55611`: `scripts/graph_enrichment_runner.py` returned `status=no_targets` and exited with code `1`.

## Next Recommended Action

Run a local dry-run over a small A/U sample, inspect candidate counts, then execute only a small batch and route candidates through review:

```bash
python3 scripts/graph_enrichment_runner.py http://127.0.0.1:8000 --market A,U --limit 100 --batch-size 20 --output artifacts/graph-enrichment-runner/latest.json
```
