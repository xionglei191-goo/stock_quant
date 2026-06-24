# Handoff: T-443 Disclosure Relationship Candidates

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-443

## Objective

Start populating the company relationship layer from public disclosure evidence so company pages can move beyond listing and research-coverage relationships.

## Scope

- In scope: relationship candidate extraction from existing `DisclosureEvent`, `Evidence` and non-research `Document` text; focused tests; API/todo/handoff documentation.
- Out of scope: external crawling, LLM extraction, entity resolution, automatic high-confidence fact promotion, relationship review UI.

## Background

T-439 created listed-security and institution-coverage relationships. That made the relationship layer visible, but it still lacked customers, suppliers, partners and subsidiaries from public disclosure evidence. The user wants a company database with relationship and unstructured data, so this slice adds a conservative candidate extractor.

## Problem Statement

The platform needs relationship graph growth from facts and evidence, not from research report opinions. Public disclosures can mention customers, suppliers, partners and subsidiaries, but these mentions should enter as review-needed candidates until entity normalization and human review are stronger.

## Expected Deliverables

- `POST /api/company-database/relationships/build` supports `include_disclosure_candidates`.
- Extracts `customer_candidate`, `supplier_candidate`, `partner_candidate` and `subsidiary_candidate`.
- Candidate relationships keep disclosure, document, evidence and source backlinks.
- Candidate relationships use `relationship_status=unknown`, `review_status=needs_review` and `metadata.candidate_status=candidate`.
- Research report coverage remains opinion/attention only.
- Focused tests cover dry-run and execute.

## Current Findings

- Added disclosure candidate extraction to `SystemService.build_company_relationships`.
- Added simple Chinese/English keyword extraction helpers.
- Added focused regression coverage for customer and supplier candidates.
- Updated API contracts, todo and docs index.

## Proposed Work Plan

1. Treat these relationships as candidate graph edges only.
2. Add stronger entity extraction, normalization and deduplication later.
3. Add manual review and promotion from candidate to verified relationship.

## Validation Plan

- Compile changed service and test files.
- Run focused company relationship builder regression.
- Run adjacent builder regressions.
- Run handoff validation.

## Decisions

- Candidate object IDs use stable external-company IDs based on extracted names.
- Candidate confidence is fixed at `0.55` until better source scoring exists.
- Research reports are explicitly excluded from this extraction path.
- Candidate relationships preserve extraction rule names in metadata for review.

## Risks and Open Questions

- Regex extraction can over-capture or miss entities; review status is therefore required.
- Entity identity is not yet normalized against issuer/security/entity mapping tables.
- Chinese relationship extraction is intentionally minimal and should be improved with structured NLP later.

## Dependencies

- Existing `CompanyRelationship`, `DisclosureEvent`, `Evidence` and `Document` models.
- Existing company relationship builder endpoint and company target resolution.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Disclosure candidate extraction added.
- [x] Research reports excluded from candidate extraction.
- [x] Candidate relationships require review.
- [x] Focused tests passed.
- [x] API contracts, todo and docs index updated.
- [x] Handoff validation passed.

## Evidence

Files changed:

- `app/services.py`: added disclosure candidate extraction path and helpers.
- `tests/test_system.py`: updated relationship builder regression.
- `docs/api-contracts.md`: documented `include_disclosure_candidates`.
- `tasks/todo.md`: added T-443 completion entry.
- `docs/README.md`: updated task range through T-443.
- `docs/agent-handoffs/README.md`: added T-443 to related tasks.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile.
- Passed: focused company relationship builder test.
- Passed: focused relationship, event and company database builder test group.
- Passed: handoff validation.
- Not run: full `make local-ci`; this is a focused relationship slice and the worktree already contains broad unrelated changes.

Artifacts:

- None required.

## Next Recommended Action

Add relationship candidate review APIs and promotion rules so users can approve, reject or merge extracted customer/supplier/partner/subsidiary relationships.
