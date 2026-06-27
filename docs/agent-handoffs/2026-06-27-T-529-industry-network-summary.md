# Handoff: T-529 Industry Network Summary

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Add a unified industry-network summary for peer, upstream, and downstream company coverage in `relationship_context`.

## Scope

- In scope: relationship context summary field, coverage diagnostics summary, focused regressions, API contract note, roadmap entry, handoff.
- Out of scope: UI rendering changes, graph query behavior, storage schema, company position derivation logic.

## Background

The relationship context already exposes source-specific industry relationship counts: peer companies, upstream companies, and downstream companies. Consumers had to add them manually to answer whether the industry relationship network is covered overall.

## Problem Statement

The project goal is a multi-dimensional relationship graph. Like shareholder networks, industry networks need both source-specific counts and a single aggregate coverage summary to keep API, UI, and agent reasoning aligned.

## Expected Deliverables

- Add `summary.industry_related_companies_total`.
- Add `coverage_diagnostics.industry_network_summary`.
- Preserve existing peer/upstream/downstream diagnostics and counts.
- Add tests for complete and sparse chain scenarios.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `relationship_context()` already builds `peer_rows`, `upstream_rows`, `downstream_rows`, and `chain_node_rows`.
- Complete company intelligence sample has one peer, one upstream, one downstream, and one chain node.
- Sparse chain sample has a chain node but no peer/upstream/downstream companies.

## Proposed Work Plan

- Completed: add `industry_related_companies_total` to `summary`.
- Completed: add `industry_network_summary` to `coverage_diagnostics`.
- Completed: assert summary and diagnostic values in complete and sparse samples.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers
python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The total counts rows across peer/upstream/downstream categories and does not deduplicate a company that may appear in more than one category.
- This is additive API metadata; consumers with exact-key snapshots should accept the new fields.

## Dependencies

- Existing `CompanyPosition` and `IndustryChain` relationship context derivation.
- Existing coverage diagnostics for peer, upstream, and downstream layers.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers` passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py` passed.
- `python3 scripts/check_handoffs.py` passed, checking 103 markdown files.
- `git diff --check` passed.

## Next Recommended Action

Consider adding UI trace attributes for industry-network summary if analysts need the top peer/upstream/downstream counts inspected as one aggregate.
