# Handoff: T-460 Company Profile Field Assertions

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-460

## Status

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main

## Objective

Extend the company profile fact layer with core official/IR fields and persist field-level provenance so each company profile field can be traced to exact source, document and evidence records.

## Background

T-456 added deep profile coverage audit, T-457 added official/IR profile field extraction, T-458 added quality reconciliation and T-459 exposed those workflows in the UI. Agents then identified that the database still lacked field-level provenance: a profile could have aggregate evidence IDs, but not durable evidence proving a specific field.

## Problem Statement

The company intelligence database could not answer which exact source supports `website_url`, `revenue`, `management` or other profile fields. It also lacked basic company facts such as official website, IR URL, headquarters, employee count, management and key customer/supplier clues.

## Expected Deliverables

- Extended company profile extraction fields for official/IR/company materials.
- Persistent `CompanyProfileFieldAssertion` model and store collection.
- Query API for field assertions.
- Field-specific evidence gating in profile coverage audit.
- Tests proving official/IR extraction, field-level evidence and research-report boundaries.
- Updated docs, todo and handoff.

## Scope

- In scope: company profile extractable fields, field-specific evidence gating, `CompanyProfileFieldAssertion` model/store/API, company intelligence aggregation, focused tests, docs and roadmap.
- Out of scope: external downloads, paid data vendors, broker integration, live trading, UI completeness verdict, company IR inbox ingestion.

## Current Findings

- `CompanyProfile` remains a snapshot model; it should not be expanded casually for every field.
- `Issuer.company_details` is already the correct compatibility location for extended company facts.
- `CompanyProfile.source_ids/evidence_ids` are too coarse for field-level provenance.
- Existing extraction already has a dry-run-first API shape that can write assertions only on execute.

## Proposed Work Plan

1. Add `CompanyProfileFieldAssertion` and store wiring.
2. Extend official/IR extraction fields and rule extractors.
3. Persist field assertions for applied candidates.
4. Make coverage audit use field-specific evidence.
5. Expose field assertions through API and company intelligence.
6. Update UI defaults, docs, todo, tests and handoff.

## Validation Plan

- Run Python compile.
- Run focused company profile extraction/coverage/research-boundary tests.
- Run UI static check.
- Run handoff validation.
- Run broader unit discovery if time allows.

## Current State

- Completed: added `CompanyProfileFieldAssertion` and `company_profile_field_assertions` collection.
- Completed: profile extraction now supports `website_url`, `ir_url`, `headquarters`, `employee_count`, `management`, `key_customers` and `key_suppliers`.
- Completed: execute extraction writes field assertions for applied fields.
- Completed: profile coverage audit uses field-specific assertion/evidence IDs when `require_evidence=true`.
- Completed: company intelligence includes profile field assertions.
- Completed: API/docs/todo updated.
- In progress: none.
- Not started: T-461 company IR/official website local inbox; T-462 UI completeness verdict.
- Blocked: none.

## Files Touched

- `app/models.py`: added `CompanyProfileFieldAssertion`.
- `app/store.py`: added collection, hydration datetime fields and dirty alias.
- `app/services.py`: added extractable fields, field-specific extraction rules, assertion persistence/querying and company intelligence aggregation.
- `app/api.py`: added field assertion routes.
- `app/static/index.html`: expanded default deep-field list.
- `tests/test_system.py`: added/extended company profile extraction, field-specific evidence and research-report boundary tests.
- `docs/data-structure-design.md`: documented field assertions and expanded profile fields.
- `docs/api-contracts.md`: documented field assertion endpoints and extraction semantics.
- `docs/README.md`: updated docs index for T-460.
- `docs/agent-handoffs/README.md`: added T-460.
- `tasks/todo.md`: added T-460.

## Dependencies

- T-456 company profile deep coverage audit.
- T-457 official/IR profile field extraction.
- T-459 workbench deep-field UI controls.
- Existing `Issuer.company_details`, `Document`, `Evidence` and source governance boundaries.

## Blockers

- None.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence tests.test_system.SystemServiceTests.test_company_profile_coverage_requires_field_specific_evidence tests.test_system.SystemServiceTests.test_company_profile_field_extraction_keeps_research_reports_opinion_only
```

Result:

- Passed: Python compile.
- Passed: focused company profile extraction/evidence/research boundary tests after tightening management-name extraction.
- Failed: first focused run captured `CEO Jane Doe. CFO John` as one name; fixed regex and reran.
- Passed: UI static check, handoff validation and full unit discovery.

## Decisions

- Kept extended profile facts in `Issuer.company_details` instead of expanding `CompanyProfile` dataclass top-level fields in this slice.
- Added field assertions as a first-class provenance layer because aggregate profile evidence cannot prove individual fields.
- Kept research reports as opinion/attention records only; they cannot create fact assertions.
- Kept extraction local-only and based on already ingested governed records.

## Risks and Open Questions

- Rule-based management/customer/supplier extraction is conservative and should be improved with reviewed official/IR samples.
- Existing UI can trigger the new fields through the default field list, but it does not yet show a single completeness verdict.
- There is still no local inbox/backfill path for company IR or official website material; agents recommended this as T-461.

## Artifacts

- None generated or committed in this slice.

## Handoff Checklist

- [x] Data model added.
- [x] Store wiring added.
- [x] API route added.
- [x] Extraction fields expanded.
- [x] Field-specific evidence gating added.
- [x] Tests added.
- [x] Docs and todo updated.
- [x] Final validation completed.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_reports_deep_missing_fields tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_counts_official_sources_and_evidence tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_keeps_research_reports_opinion_only tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence tests.test_system.SystemServiceTests.test_company_profile_coverage_requires_field_specific_evidence tests.test_system.SystemServiceTests.test_company_profile_field_extraction_keeps_research_reports_opinion_only tests.test_system.SystemServiceTests.test_company_profile_field_extraction_does_not_overwrite_without_refresh
python3 scripts/check_handoffs.py
python3 -m unittest discover -s tests
```

Result:

- Passed: Python compile.
- Passed: UI static check.
- Passed: seven focused company profile tests.
- Passed: handoff validation.
- Passed: full unit discovery, 241 tests.
- Failed then fixed: first handoff validation because required sections were missing; rerun passed.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Implement T-461 company IR/official website local inbox and backfill.
2. Implement T-462 company intelligence completeness verdict UI.
3. Add conflict/supersession handling for multiple assertions on the same field and period.

## Next Recommended Action

Continue with T-461 company IR/official website local inbox, using `CompanyProfileFieldAssertion` as the downstream provenance target.
