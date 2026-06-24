# Handoff: T-457 Company Profile Official/IR Field Extraction

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-457

## Objective

Add a local, dry-run-first extraction path that fills company profile facts from already-ingested official disclosure, company IR, company official and exchange/regulatory records.

## Scope

- In scope: profile field extraction API, source-boundary filtering, evidence-linked candidates, optional execute/write behavior, regression tests, API/data-structure docs, todo and handoff.
- Out of scope: external downloads, paid data vendors, UI exposure, event/relationship deduplication, entity merge, LLM extraction, live trading or broker integration.

## Background

T-456 identifies which deep company profile fields are missing and which source classes should fill them. The next gap is actual field extraction from local governed records so the company database can become more complete without relying on research reports as facts.

## Problem Statement

The company database can now audit missing deep fields, but without an extraction path it still requires manual edits to fill business summaries, products and financial snapshots from official/IR documents. Research reports must remain opinion signals and cannot be promoted into facts.

## Expected Deliverables

- A dry-run-first profile field extraction endpoint.
- A company-database scoped compatibility route.
- Evidence-linked candidates for business and financial profile fields.
- Optional execute behavior that persists `Issuer` and `CompanyProfile` updates.
- Regression tests for official/IR extraction, research-source exclusion and refresh semantics.
- Updated API, data-structure, roadmap and handoff docs.

## Current Findings

- `CompanyProfile` can be rebuilt from `Issuer`, `Security`, market data and overlay fields.
- `Issuer.company_details` and `Issuer.fundamentals` are the current durable place for extracted business and financial facts.
- `_company_profile_document_is_fact_source` and `_evidence_is_official_public` already encode the correct source boundary.
- T-456 coverage audit can verify whether extracted fields become visible after execution.

## Proposed Work Plan

1. Add profile field extraction routes.
2. Implement local governed-document/evidence extraction helpers.
3. Persist extracted fields only when `execute=true`.
4. Add focused tests around official evidence, research exclusion and overwrite behavior.
5. Update docs, roadmap and handoff.

## Validation Plan

- Compile app/tests/scripts.
- Run focused T-457 tests.
- Run full clean-env unit discovery.
- Run UI static check, security check, handoff validation and diff whitespace check.

## Current State

- Completed: added `POST /api/company-profiles/fields/extract`.
- Completed: added compatible alias `POST /api/company-database/profile-fields/extract`.
- Completed: extraction supports `issuer_ids`, `symbols`, `document_ids`, `fields`, `document_limit`, `evidence_limit`, `min_confidence`, `require_evidence`, `refresh_existing` and `execute`.
- Completed: default mode is dry-run and returns evidence-linked candidates.
- Completed: `execute=true` writes supported facts into `Issuer.company_details`, `Issuer.fundamentals`, `Issuer.data_sources` and materializes `CompanyProfile`.
- Completed: research reports, broker research, local/manual references, news and unclear sources are excluded from fact extraction.
- Blocked: none.

## Files Touched

- `app/api.py`: added profile field extraction routes and handler.
- `app/services.py`: added `extract_company_profile_fields` and helper methods for governed document filtering, rule-based field extraction, candidate scoring and profile persistence.
- `tests/test_system.py`: added focused regressions for official/IR extraction, research-report exclusion and refresh semantics.
- `docs/api-contracts.md`: documented extraction endpoint request/response, dry-run/execute behavior and source boundaries.
- `docs/data-structure-design.md`: documented `CompanyProfileFieldExtractionResult` and persistence mapping.
- `tasks/todo.md`: added T-457 as done and kept T-458/T-459 as follow-ups.
- `docs/README.md`: updated document index for profile field extraction.
- `docs/agent-handoffs/README.md`: added T-457.
- `docs/agent-handoffs/2026-06-24-T-457-company-profile-official-ir-field-extraction.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence tests.test_system.SystemServiceTests.test_company_profile_field_extraction_keeps_research_reports_opinion_only tests.test_system.SystemServiceTests.test_company_profile_field_extraction_does_not_overwrite_without_refresh
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused T-457 tests, 3 tests.
- Passed: full clean-env unit discovery, 237 tests.
- Passed: UI static check.
- Passed: security check.
- Passed: handoff validation.
- Passed: diff whitespace check.

## Decisions

- Kept the primary extraction API under `company-profiles` and added a `company-database` alias for补库 orchestration.
- Reused `_company_profile_document_is_fact_source` and `_evidence_is_official_public`; no parallel source-governance path was introduced.
- Kept v1 extraction rule-based and evidence-linked. Results are candidates and operational facts, not an assertion that analyst review is complete.
- Did not add a persistent extraction-run model; the durable state is the updated `Issuer` and `CompanyProfile`.

## Dependencies

- T-456 company profile deep-field coverage audit and source plan.
- Existing source governance and evidence boundary helpers.
- Existing `Issuer`, `Document`, `Evidence` and `CompanyProfile` models.

## Blockers

- None.

## Risks and Open Questions

- Rule extraction is intentionally conservative and will miss many filing phrasings until T-457 is expanded with richer parsers.
- `require_evidence=true` will ignore whole-document body text unless explicit evidence records exist.
- UI visibility is not included; T-459 should surface extraction actions, candidates and coverage changes in the workbench.
- T-458 still needs deduplication, entity merge and source quality scoring for events/relationships.

## Artifacts

- None committed. No external downloads or generated production evidence.

## Handoff Checklist

- [x] Endpoint and alias added.
- [x] Governed source boundary reused.
- [x] Dry-run and execute behavior tested.
- [x] Research report fact-exclusion tested.
- [x] API/data-structure docs updated.
- [x] Todo and docs index updated.
- [x] Handoff validation rerun after required-section fix.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence tests.test_system.SystemServiceTests.test_company_profile_field_extraction_keeps_research_reports_opinion_only tests.test_system.SystemServiceTests.test_company_profile_field_extraction_does_not_overwrite_without_refresh
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: compile, focused T-457 tests, full 237-test suite, UI static check, security check, handoff validation and diff whitespace check.

## Next Steps

1. T-458: implement event/relationship deduplication, entity merge and source quality scoring.
2. T-459: expose deep-field coverage and extraction in the company intelligence workbench.

## Next Recommended Action

Proceed to T-458 event/relationship deduplication, entity merge and source quality scoring.
