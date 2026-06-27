# Handoff: T-527 Shareholder Network Diagnostic Summary

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Add a unified shareholder-network summary to relationship coverage diagnostics while preserving source-specific diagnostics for 13F/holding and approved fact shareholder networks.

## Scope

- In scope: `coverage_diagnostics.shareholder_network_summary`, focused regressions, API contract note, roadmap entry, handoff.
- Out of scope: required coverage scoring changes, UI rendering changes, storage schema, graph query behavior.

## Background

T-526 added `summary.shareholder_related_companies_total`. Coverage diagnostics still exposed only the two source-specific optional layers: `shareholder_network` and `approved_shareholder_network`. That preserves provenance, but it does not give consumers a unified answer to whether any shareholder-related network exists.

## Problem Statement

Analysts and downstream automation need both views: source-specific diagnostics for provenance, and a total shareholder-network coverage summary for the overall relationship-chain completeness question.

## Expected Deliverables

- Add `coverage_diagnostics.shareholder_network_summary`.
- Include `total`, `fact_network`, `holding_network`, `available`, and `source_layers`.
- Preserve existing `shareholder_network` and `approved_shareholder_network` diagnostic rows unchanged.
- Add focused assertions for 13F-only and fact-network-only scenarios.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `_relationship_coverage_diagnostics()` receives the complete relationship summary, including `shareholder_related_companies_total`.
- Existing tests already cover one holding-derived network and one approved fact shareholder network.
- Optional diagnostics should remain optional and should not affect required `coverage_score`.

## Proposed Work Plan

- Completed: add `shareholder_network_summary` in `_relationship_coverage_diagnostics()`.
- Completed: keep the two existing source-specific diagnostics unchanged.
- Completed: add regression assertions in the complete aggregated sample and approved same-shareholder sample.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- This is an additive diagnostics field. Consumers that snapshot exact coverage diagnostic keys should accept the new field.
- The summary indicates coverage availability, not source freshness or holder identity quality.

## Dependencies

- T-526 `summary.shareholder_related_companies_total`.
- Existing source-specific shareholder network diagnostics.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated` passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py` passed.
- `python3 scripts/check_handoffs.py` passed, checking 101 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Consider adding freshness/confidence fields to the shareholder network summary if this summary starts driving automated prioritization.
