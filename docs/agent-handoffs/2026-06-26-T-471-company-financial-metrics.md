# Handoff: T-471 Company Financial Metrics Fact Layer

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-471

## Status

- Status: DONE
- Owner group: Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Promote company financial snapshot fields into first-class factual records so revenue, net income, gross margin, cash and debt can be queried, audited and linked back to governed sources.

## Background

The company intelligence workbench already had `CompanyProfile.latest_financial_snapshot`, but those values were only a latest-view blob on issuer/profile records. The platform needs a company database foundation where financial facts are period-specific, evidence-linked and independently queryable.

## Problem Statement

Without a dedicated financial metrics object, a company can appear to have a financial snapshot while the system cannot answer which period, source, document, evidence or review status supports a value. That weakens company database coverage audits and makes later review or correction difficult.

## Expected Deliverables

- A first-class `FinancialMetric` data model and store collection.
- API route for querying and registering governed financial fact records.
- Automatic materialization from official/IR/regulatory profile-field extraction.
- Company intelligence and coverage audit integration.
- Focused regression coverage and updated docs/roadmap/handoff.

## Scope

- In scope: data model, in-memory/store collection registration, API route, service helpers, extraction materialization, company intelligence aggregate, deep field coverage audit, API/data-structure docs, roadmap and focused tests.
- Out of scope: external data download, broker integration, live trading, full accounting statement taxonomy, UI-specific metrics table and research-report forecast migration.

## Current Findings

- `CompanyProfileFieldAssertion` already captures field-level provenance for official/IR extracted fields.
- Financial fields were previously stored on `Issuer.fundamentals` and `CompanyProfile.latest_financial_snapshot`.
- Coverage audit could mark financial fields present, but source records often pointed to issuer/profile snapshots instead of a durable metric fact.
- Research reports already have separate forecast/viewpoint models and must not be promoted into fact records.

## Proposed Work Plan

1. Add `FinancialMetric` and register `financial_metrics` in the store.
2. Add `/api/company-financial-metrics` for query/register.
3. Materialize profile extraction financial fields into financial metrics when a period is available.
4. Feed company intelligence and deep coverage audit from financial metrics.
5. Update tests, docs, roadmap and handoff.

## Validation Plan

- Compile app, tests and scripts.
- Run focused official/IR profile extraction regression.
- Run handoff validation.
- Run whitespace diff check.

## Current State

- Completed: Added `FinancialMetric` and the `financial_metrics` store collection.
- Completed: Added `GET|POST /api/company-financial-metrics`.
- Completed: Official/IR/regulatory company profile extraction now materializes financial fields into `FinancialMetric` when a period is available.
- Completed: Company intelligence aggregation and deep field coverage audit read financial metrics as the latest financial snapshot source.
- Completed: API and data-structure docs describe the source boundary.
- Completed: Final verification passed before commit/push.
- Not started: UI-specific financial metrics table; current UI sees metrics through company intelligence sections and coverage records.
- Blocked: None.

## Dependencies

- Existing issuer/security mapping.
- Existing company profile field extraction and field assertion provenance.
- Existing source/document/evidence governance metadata.

## Blockers

- None.

## Files Touched

- `app/models.py`: added the `FinancialMetric` dataclass.
- `app/store.py`: registered the `financial_metrics` collection, datetime fields and resource dirty marker mapping.
- `app/services.py`: added financial metric registration/query helpers, extraction materialization and company intelligence integration.
- `app/api.py`: registered `/api/company-financial-metrics` and permission policy coverage.
- `tests/test_system.py`: extended official/IR extraction regression to assert financial metrics, latest financial snapshot and coverage provenance.
- `docs/api-contracts.md`: documented endpoint contract, payloads and research-report boundary.
- `docs/data-structure-design.md`: documented `FinancialMetric`.
- `tasks/todo.md`: added DONE T-471.
- `docs/agent-handoffs/2026-06-26-T-471-company-financial-metrics.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_expands_official_ir_facts_and_assertions
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile on app, tests and scripts.
- Failed: first focused unit command used an incorrect test method name.
- Passed: focused official/IR extraction regression with the correct method name.
- Passed: handoff validation.
- Passed: whitespace diff check.

## Evidence

- Compile check proves touched Python files parse.
- Focused regression is extended to assert `FinancialMetric` rows and latest financial snapshot integration.
- Coverage audit assertion checks financial fields now point to `financial_metric` source records.

## Decisions

- Financial metrics are fact-layer records, not research-report opinion records.
- Research reports, broker research, news, manual references, local references and red risk sources cannot register factual financial metrics.
- Company profile extraction can auto-materialize financial metrics only when a period is available in the same run or existing snapshot.
- Existing `Issuer.fundamentals` and `CompanyProfile.latest_financial_snapshot` stay as latest snapshot views for compatibility.

## Risks and Open Questions

- There is not yet a dedicated financial-metrics UI table; users see the values through the company intelligence aggregate and field coverage audit.
- `FinancialMetric` currently handles core snapshot metrics. Future work can add richer statement line items and period taxonomy if needed.

## Artifacts

- None. This task changes code/docs/tests only.

## Handoff Checklist

- [x] Code changes completed.
- [x] API/data structure docs updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [x] Focused unit test rerun with correct method name.
- [x] Handoff validation rerun.

## Next Steps

1. Commit and push the verified changes to GitHub.
2. Add a dedicated financial metrics table in the workbench if analysts need to inspect period-by-period values directly.
3. Expand the model beyond snapshot metrics only after statement taxonomy requirements are clear.

## Next Recommended Action

Commit and push T-471.
