# Handoff: T-458 Event/Relationship Dedup, Entity Merge, Source Quality

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-458

## Objective

Add a local quality reconciliation path for the company intelligence database: event deduplication, relationship deduplication, entity alias merge metadata and source quality scoring.

## Scope

- In scope: dry-run-first quality reconciliation API, duplicate group detection, non-destructive merge application, entity canonical key/aliases, source quality metadata, focused tests, API/data-structure docs, todo and handoff.
- Out of scope: UI exposure, external downloads, paid data vendors, live trading, investment ratings, production graph database writes and destructive deletes.

## Background

T-456/T-457 moved the system from missing-field audit to profile field extraction. The next database-quality gap is repeated event/relationship records created by filings, evidence snippets, research coverage and repeated补库 runs. These need local reconciliation while preserving provenance and review state.

## Problem Statement

Duplicate events and relationships make the company timeline and relationship graph noisy. Entity aliases such as `Mega Cloud` and `Mega Cloud Inc.` should be surfaced as merge candidates, and each event/relationship needs a local source quality score so later review and UI work can prioritize low-confidence records.

## Expected Deliverables

- A reconciliation endpoint under company database.
- Event duplicate keys and non-destructive merge behavior.
- Relationship duplicate keys, entity canonical keys and alias preservation.
- Source quality score stored in metadata during execute and returned during dry-run.
- Regression tests for event dedup, relationship/entity alias merge and source quality boundary.
- Updated API, data-structure, roadmap and handoff docs.

## Current Findings

- `CompanyEvent` and `CompanyRelationship` already support flexible `metadata`, confidence, review status and evidence/document/source backlinks.
- Existing relationship review merge semantics already use `review_status=merged` and `relationship_status=inactive`; T-458 extends the same style to automated duplicate reconciliation.
- Source definitions and source IDs can support a local provenance score without introducing investment-rating semantics.
- T-459 should expose these results in UI; this slice stays backend/data-quality only.

## Proposed Work Plan

1. Add `POST /api/company-database/quality/reconcile`.
2. Implement event duplicate grouping and merge application.
3. Implement relationship duplicate grouping, entity canonical key and alias metadata.
4. Implement source quality scoring.
5. Add focused tests and update docs/handoff.

## Validation Plan

- Compile app/tests/scripts.
- Run focused T-458 tests.
- Run full clean-env unit discovery.
- Run UI static check, security check, handoff validation and diff whitespace check.

## Current State

- Completed: added `POST /api/company-database/quality/reconcile`.
- Completed: dry-run returns duplicate groups, entity merge candidates and source quality scores.
- Completed: execute marks duplicate events as `review_status=merged` and merges evidence/document/source backlinks into the canonical event.
- Completed: execute marks duplicate relationships as `review_status=merged`, `relationship_status=inactive` and merges backlinks/aliases into the canonical relationship.
- Completed: `metadata.source_quality` scores official/evidence-backed records above research/manual/reference/opinion records.
- Blocked: none.

## Files Touched

- `app/api.py`: added quality reconciliation route and handler.
- `app/services.py`: added `reconcile_company_database_quality` plus event/relationship dedup, entity canonicalization and source-quality helpers.
- `tests/test_system.py`: added focused T-458 regressions.
- `docs/api-contracts.md`: documented reconciliation request/response, merge behavior and source quality boundary.
- `docs/data-structure-design.md`: documented `CompanyGraphQualityReconciliation`.
- `tasks/todo.md`: added T-458 as done and kept T-459 as the next follow-up.
- `docs/README.md`: updated index for event/relationship quality reconciliation.
- `docs/agent-handoffs/README.md`: added T-458.
- `docs/agent-handoffs/2026-06-24-T-458-event-relationship-dedup-entity-source-quality.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_duplicate_events tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_relationship_entity_aliases tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_scores_source_boundaries
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused T-458 tests, 3 tests.
- Passed: full clean-env unit discovery, 240 tests.
- Passed: UI static check.
- Passed: security check.
- Passed: handoff validation.
- Passed: diff whitespace check.

## Decisions

- Added a unified reconcile endpoint instead of expanding event/relationship builders with more flags; T-458 crosses events, relationships, entity aliases and source quality.
- Kept merges non-destructive: canonical records keep backlinks and duplicates are marked merged/inactive rather than deleted.
- Stored source quality in `metadata.source_quality` because no new persistent model is needed for this local scoring view.
- Defined source quality as provenance/review quality only, not company quality, investment rating or trading signal.

## Dependencies

- Existing `CompanyEvent`, `CompanyRelationship`, `Document`, `Evidence`, `SourceDefinition` and source review records.
- T-443/T-449 candidate extraction and T-457 profile field extraction.
- Existing company database target issuer resolution.

## Blockers

- None.

## Risks and Open Questions

- Dedup keys are deterministic and conservative; they may miss semantically equivalent events across different documents.
- Entity alias canonicalization is string-based and should be augmented later with curated `EntityMapping` review.
- Source quality scores prioritize provenance completeness; they should not be displayed as investment recommendations.

## Artifacts

- None committed. No external downloads or generated production evidence.

## Handoff Checklist

- [x] Endpoint and route added.
- [x] Event duplicate merge tested.
- [x] Relationship entity alias merge tested.
- [x] Source quality boundary tested.
- [x] API/data-structure docs updated.
- [x] Todo and docs index updated.
- [x] Full validation rerun.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_duplicate_events tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_relationship_entity_aliases tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_scores_source_boundaries
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: compile, focused T-458 tests, full 240-test suite, UI static check, security check, handoff validation and diff whitespace check.

## Next Steps

1. T-459: expose deep-field coverage, extraction and quality reconciliation results in the company intelligence workbench.

## Next Recommended Action

Proceed to T-459 UI integration after full validation passes.
