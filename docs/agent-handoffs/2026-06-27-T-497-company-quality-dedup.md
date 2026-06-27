# Handoff: T-497 Company Quality Deduplication

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows, Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-27
- Last agent: Codex with Data/Evidence worker
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-497

## Objective

Reduce company event and relationship graph noise by strengthening credibility scoring, duplicate detection, entity alias merge support, and human review recommendations. Preserve the boundary that research reports are opinion sources and cannot automatically become fact relationships.

## Scope

- In scope: company quality domain module, existing quality reconciliation facade, event/relationship review recommendation payloads, company intelligence maintenance UI summaries, focused regression, task status, and handoff.
- Out of scope: database migrations, new API URLs, destructive deletion of duplicate records, broker integration, live trading, automatic order execution.

## Background

Before T-497, duplicate groups, source quality scoring, entity alias normalization, and candidate recommendation logic were implemented directly in `SystemService`. UI rows still leaned toward internal score/detail display instead of telling the reviewer why the item matters, what evidence exists, and what action to take.

## Problem Statement

The knowledge graph and company event layer become hard to trust when duplicate events, alias relationships, and low-quality opinion-derived records look equivalent to official evidence. A personal research user needs a clear review queue that separates fact candidates from opinion signals and preserves traceability.

## Expected Deliverables

- Extract company quality scoring and recommendation helpers into `app/service_modules/company_quality.py`.
- Keep `SystemService` as compatibility facade for all existing API URLs and payloads.
- Add structured `explanation`, `evidence_summary`, and `next_action` fields to review recommendations and source quality rows.
- Update quality, event review, and relationship review UI rows to default to "why important / evidence source / next action".
- Add tests proving duplicate merge, alias merge, recommendation explanation, and research-opinion downgrade behavior.

## Current Findings

- Existing data model already supports non-destructive merge by marking duplicate events as `merged` and relationships as `inactive/merged`; no schema migration was needed.
- Existing `source_ids`, `document_ids`, and `evidence_ids` are enough to produce evidence summaries.
- Research and broker source IDs were already detectable; T-497 keeps them lower quality and records `research_opinion_source` rather than upgrading them to facts.

## Proposed Work Plan

1. Move source quality scoring, normalized keys, entity keys, review candidate checks, and review recommendation builders into `app/service_modules/company_quality.py`.
2. Preserve `SystemService` method names and route behavior while delegating to the module.
3. Enhance UI rows in the company intelligence maintenance area.
4. Strengthen focused tests for explanation fields and opinion-source downgrade.
5. Run standard validation and browser smoke where feasible.

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_event_review_approves_reclassifies_merges_and_batches_candidates tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_duplicate_events tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_relationship_entity_aliases tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_scores_source_boundaries tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor`
- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/security_check.py .`

## Risks

- This is still a heuristic local provenance score, not investment advice or objective truth.
- Duplicate merge remains non-destructive; records are marked merged/inactive rather than deleted.
- The UI now exposes clearer recommendations, but human review is still required before candidate relationships are treated as trusted facts.

## Dependencies

- Existing company event and company relationship models.
- Existing `/api/company-database/quality/reconcile`, `/api/company-events`, and `/api/company-relationships` routes.
- Existing T-490/T-491 advanced trace helpers.
- Existing T-498/T-500 direction to keep service growth in domain modules.

## Blockers

- None for local T-497 completion.

## Handoff Checklist

- [x] Company quality domain module added.
- [x] `SystemService` compatibility facade preserved.
- [x] Research/opinion source downgrade retained.
- [x] UI review rows show why, evidence, and next action.
- [x] Focused regression added and passed.
- [x] `tasks/todo.md` marked T-497 DONE.

## Evidence

- `app/service_modules/company_quality.py`: source quality, normalized/entity keys, candidate checks, review scores and recommendations.
- `app/services.py`: delegates quality methods to `company_quality`.
- `app/static/index.html`: quality/review rows show reviewer-oriented summaries.
- `tests/test_system.py`: recommendation explanation and research-opinion downgrade assertions.
- Focused regression result: six T-497/company-quality tests passed.
- `python3 scripts/ui_research_workbench_matrix.py http://127.0.0.1:8014 --output-dir artifacts/t497-ui-research-workbench-matrix --timeout 60`: passed 16 desktop/mobile browser checks; failure count 0; console error count 0; artifact is local-only and not acceptable for non-local release gates.

## Next Recommended Action

Proceed to T-498 front-end modularization and API route grouping. Use the T-495 browser matrix and T-501 golden API baseline to prove no UI/API behavior changed during the split.
