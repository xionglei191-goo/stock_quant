# Handoff: T-456 Company Profile Deep Field Coverage

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-456

## Objective

Add a read-only company profile deep-field coverage audit so the company intelligence database can identify missing profile fields and source priorities beyond section-level coverage.

## Scope

- In scope: profile deep-field audit API, source plan, field source/evidence status, tests, API/data-structure docs, todo and handoff.
- Out of scope: external downloads, paid/commercial data, official disclosure extraction, UI panel, persistence model, live trading or broker integration.

## Background

T-445 added section-level company database coverage audit, T-453/T-455 added coverage trend reporting and UI, and T-454 added retry/resume run history. The next product gap was field-level clarity: section coverage could say a company had a profile or document, but not whether important fields such as business summary, products, financial metrics, source evidence or analyst coverage were actually supported by governed records.

## Problem Statement

The user wants a complete company database. Without deep-field coverage, future agents cannot prioritize whether to extract official disclosures, company IR, exchange filings, public financial summaries, or opinion-layer research reports. The system also needs to keep research reports as opinion and attention signals, not fact sources.

## Expected Deliverables

- A read-only profile field coverage endpoint.
- A compatibility route under company database.
- Field groups and missing field counts.
- Source/evidence records per field.
- Source plan and boundaries for official/public/local/manual/research sources.
- Focused regression tests and docs.

## Current Findings

- `CompanyProfile` is a compact aggregate and does not itself prove deep-field completeness.
- Existing `Issuer`, `Security`, `MarketDataPoint`, `Document`, `Evidence`, `ResearchReportAsset`, `CompanyEvent`, `CompanyRelationship`, `ObservationItem` and `AnalysisConclusion` records can be used as coverage evidence.
- `_company_database_target_issuers`, `_company_profile_from_existing_records`, `_latest_market_point_for_security` and `_evidence_is_official_public` provide the existing routing and source-boundary logic.
- Research reports must stay opinion-only and only count toward coverage/opinion fields.

## Proposed Work Plan

1. Add profile coverage routes.
2. Implement source-plan and field-level coverage helpers.
3. Add sparse/official/research-boundary tests.
4. Update API/data-structure docs and roadmap.
5. Run focused and full validation.

## Validation Plan

- Compile app/tests/scripts.
- Run focused T-456 tests.
- Run full clean-env unit discovery.
- Run UI static check, security check, handoff validation and diff whitespace check.

## Current State

- Completed: added `GET|POST /api/company-profiles/coverage/audit`.
- Completed: added compatible alias `GET|POST /api/company-database/profile-field-coverage/audit`.
- Completed: audit returns field-level `present`, `source_records`, `evidence_ids`, `missing_reason`, `source_policy`, missing counts and source plans.
- Completed: research reports only satisfy coverage/opinion slots and do not satisfy fact fields.
- Completed: official/regulatory/company IR evidence can satisfy source/evidence fields; manual/local/research references stay non-fact.
- Blocked: none.

## Files Touched

- `app/api.py`: added profile deep-field coverage routes and handler.
- `app/services.py`: added `company_profile_coverage_audit` and helper methods for field grouping, source plans, source policy and field-level coverage rows.
- `tests/test_system.py`: added focused regressions for sparse fields, official evidence, and research report opinion-only boundaries.
- `docs/api-contracts.md`: documented request/response schema, field groups, alias endpoint and source boundaries.
- `docs/data-structure-design.md`: documented `CompanyProfileDeepCoverageAudit`.
- `tasks/todo.md`: added T-456 and shifted follow-ups to T-457/T-458/T-459.
- `docs/README.md`: updated index for deep-field coverage audit.
- `docs/agent-handoffs/README.md`: added T-456.
- `docs/agent-handoffs/2026-06-24-T-456-company-profile-deep-field-coverage.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_reports_deep_missing_fields tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_counts_official_sources_and_evidence tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_keeps_research_reports_opinion_only
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused T-456 tests, 3 tests.
- Passed: full clean-env unit discovery, 234 tests.
- Passed: UI static check.
- Passed: security check.
- Passed: handoff validation.
- Passed: diff whitespace check.

## Decisions

- Kept the primary endpoint under `company-profiles` because the resource is a company profile audit.
- Added the `company-database/profile-field-coverage/audit` alias because future补库 agents may expect a company-database scoped route.
- Did not add a persisted model; this is an audit view over existing records.
- Research reports remain opinion/attention sources only.

## Dependencies

- T-432 `CompanyProfile` and company-intelligence aggregation.
- T-445 company database section-level coverage audit.
- T-453/T-455 coverage trend and run-history visibility.
- Existing source governance and evidence boundary helpers.

## Blockers

- None.

## Risks and Open Questions

- The audit proves coverage status, not extraction quality. T-457 must still implement actual official disclosure/company IR field extraction.
- `require_evidence=true` is stricter than the default and may mark issuer/security master fields missing until evidence backlinks are imported.
- UI visibility is not included in this slice; T-459 should add a compact deep-field coverage panel if needed.

## Artifacts

- None committed. No external downloads or generated production evidence.

## Handoff Checklist

- [x] Endpoint and alias added.
- [x] Field groups/source plan implemented.
- [x] Research report opinion-only boundary tested.
- [x] API/data-structure docs updated.
- [x] Todo and docs index updated.
- [x] Handoff validation rerun after template fix.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_reports_deep_missing_fields tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_counts_official_sources_and_evidence tests.test_system.SystemServiceTests.test_company_profile_coverage_audit_keeps_research_reports_opinion_only
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: compile, focused T-456 tests, full 234-test suite, UI static check, security check, handoff validation and diff whitespace check.

## Next Steps

1. T-457: extract company profile fields from already-ingested official disclosures and company IR documents.
2. T-458: add event/relationship deduplication, entity merge and source quality scoring.
3. T-459: expose deep-field coverage and source plan in the company intelligence workbench.

## Next Recommended Action

Implement T-457 official disclosure/company IR profile field extraction using the missing fields and source plan emitted by T-456.
