# Handoff: T-500 SystemService Company Mainline Modularization

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-500

## Objective

Extract the first company-intelligence mainline domain helpers from `SystemService` while preserving the facade, API schema, UI behavior, storage schema, audit context, and paper-only boundaries.

## Scope

- In scope: deterministic helper extraction for company intelligence, market data, research report rows, graph export shaping, tests, ADR, task status, and handoff.
- Out of scope: moving full workflows, database migrations, API route changes, UI changes, broker integration, and automatic trading.

## Background

T-501 established a golden API baseline. T-496 already extracted feedback scoring and T-497 extracted company quality. T-500 continues the same gradual approach rather than rewriting `SystemService`.

## Problem Statement

`app/services.py` is too large for long-term safe feature growth. Company intelligence is a central path that combines company profile, market data, research opinions, graph edges, and paper feedback, so it needs domain modules without breaking existing `/api` behavior.

## Expected Deliverables

- Company-intelligence helper module.
- Market-data helper module.
- Research-report helper module.
- Graph-intelligence helper module.
- Existing feedback-scoring module included in the T-500 boundary.
- Facade helper methods still available on `SystemService`.
- Focused tests and golden API baseline passing.

## Current Findings

- `SystemService` still owns store access and orchestration; this is intentional for compatibility.
- Extracted code is deterministic and does not perform external IO.
- The next safe step is extracting larger company database builders in smaller slices, guarded by the same golden API baseline.

## Proposed Work Plan

1. Add the new service modules.
2. Delegate existing `SystemService` helper methods to modules.
3. Add focused regression for helper delegation.
4. Run focused golden API and domain tests.
5. Update ADR, task status, and handoff.

## Validation Plan

- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_systemservice_company_intelligence_helpers_delegate_to_domain_modules tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_simulation_feedback_realization_scoring_links_conclusion_market_window_and_review tests.test_system.SystemServiceTests.test_company_database_quality_reconcile_merges_duplicate_events`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/security_check.py .`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Risks

- This is a first slice, not a full `SystemService` split.
- Larger workflow methods still need future extraction in smaller batches.
- Protocol-based helper modules assume the current model attribute names remain stable.

## Dependencies

- T-501 golden API baseline.
- T-496 feedback scoring module.
- T-497 company quality module.
- `docs/systemservice-modularization-adr.md`.

## Blockers

- None for local T-500 completion.

## Handoff Checklist

- [x] `SystemService` facade preserved.
- [x] No API schema or route changes.
- [x] No database migration.
- [x] No UI behavior changes.
- [x] Paper-only/no-broker/no-auto-trading boundary preserved.
- [x] Focused regression added.

## Evidence

- `app/service_modules/company_intelligence.py`: company-intelligence symbol, verdict, and next-action rules.
- `app/service_modules/market_data.py`: corporate-action and adjustment factor rules.
- `app/service_modules/research_reports.py`: research-report mapping and viewpoint rows.
- `app/service_modules/graph_intelligence.py`: graph identity and Neo4j export helper rules.
- `tests/test_system.py`: focused facade delegation regression.

## Next Recommended Action

Proceed to T-503 service-layer growth freeze rules so future features default to domain modules and handoffs must justify any new `SystemService` logic.
