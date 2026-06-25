# Handoff: T-461 Company Material Inbox

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-461

## Status

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Platform and Quality, Product and UI, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main

## Objective

Add a local-first company official/IR material inbox so already downloaded or manually saved company materials can feed the existing company database fact pipeline: source governance, document ingestion, evidence extraction, profile field extraction and field-level assertions.

## Background

T-456 to T-460 made deep profile coverage, official/IR field extraction and field-level assertions available, but users still needed a practical way to load local company materials without manually calling four APIs for every file.

## Problem Statement

The company database could identify missing fields and extract from already-ingested official records, but it lacked a governed local inbox for official company/IR materials. Without that path, the system still appeared empty unless source, document, evidence and profile extraction APIs were called by hand.

## Expected Deliverables

- Local script for manifest-backed company official/IR material ingestion.
- Dry-run planning mode that does not mutate the store.
- Execute mode that registers source/document, extracts evidence and backfills profile fields.
- Strict source/document boundary so research reports, news and manual references cannot enter the fact layer.
- Focused tests and docs/handoff updates.

## Scope

- In scope: local text/Markdown/HTML company material files, sidecar manifest, existing API composition, field-level assertion backfill, tests, docs and roadmap.
- Out of scope: external crawling, PDF/OCR automation, new backend routes, broker integration, live trading, UI completeness verdict.

## Current Findings

- Existing APIs were sufficient for T-461; no backend route was needed.
- `/api/evidence/extract` does not authorize the data engineer role, while `platform` can compose ingestion, evidence and company-database APIs.
- Website URL extraction could incorrectly prefer an Investor Relations URL when using the generic URL fallback.
- Manifest metadata must be explicit because filename inference would be too weak for source and company boundaries.

## Proposed Work Plan

1. Add manifest-backed local inbox script.
2. Validate source/document/rights boundaries before API calls.
3. Compose source registration, document ingestion, evidence extraction and profile field extraction.
4. Add dry-run, execute and boundary tests.
5. Update docs, todo and handoff.

## Validation Plan

- Run Python compile for changed code and tests.
- Run focused T-461 tests.
- Run T-460 official evidence extraction regression.
- Run handoff validation.
- Run broader checks before commit.

## Current State

- Completed: added `scripts/company_material_inbox_ingest.py`.
- Completed: script scans `*.manifest.json` sidecars and defaults to dry-run.
- Completed: execute mode registers source, ingests document, extracts evidence and calls profile field backfill.
- Completed: manifest source/document boundaries reject research reports, broker research, news, manual references and training-allowed inputs.
- Completed: tests cover dry-run, execute and boundary rejection.
- Completed: fixed website URL fallback so Investor Relations URLs are not written as `website_url`.
- In progress: none.
- Not started: T-462 company intelligence completeness verdict UI.
- Blocked: none.

## Dependencies

- T-456 company profile deep coverage audit.
- T-457 official/IR profile field extraction API.
- T-460 `CompanyProfileFieldAssertion`.
- Existing ingestion source/document and evidence extraction APIs.

## Blockers

- None.

## Files Touched

- `scripts/company_material_inbox_ingest.py`: new local manifest-backed inbox/backfill script.
- `app/services.py`: tightened website URL extraction fallback around Investor Relations text.
- `tests/test_system.py`: added company material inbox script tests and regression coverage.
- `docs/api-contracts.md`: documented script command, manifest shape, execute chain and boundaries.
- `docs/data-structure-design.md`: documented `CompanyMaterialInboxManifest` and run summary artifact.
- `docs/README.md`: updated docs index for T-461.
- `docs/agent-handoffs/README.md`: added T-461 to related tasks.
- `tasks/todo.md`: added T-461 DONE roadmap entry.

## Commands Run

```bash
python3 -m py_compile scripts/company_material_inbox_ingest.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_material_inbox_script_dry_run_plans_without_mutation tests.test_system.SystemServiceTests.test_company_material_inbox_script_executes_profile_backfill tests.test_system.SystemServiceTests.test_company_material_inbox_script_rejects_research_and_manual_sources
python3 -m py_compile app/services.py scripts/company_material_inbox_ingest.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_material_inbox_script_dry_run_plans_without_mutation tests.test_system.SystemServiceTests.test_company_material_inbox_script_executes_profile_backfill tests.test_system.SystemServiceTests.test_company_material_inbox_script_rejects_research_and_manual_sources tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence
```

Result:

- Passed: Python compile.
- Passed: three T-461 script tests after role and URL extraction fixes.
- Passed: T-460 official evidence extraction regression.
- Failed then fixed: first execute test used `data_engineer` role for `/api/evidence/extract`; script now uses `platform` role because it must compose ingestion, evidence and company-database APIs.
- Failed then fixed: `website_url` fallback preferred a longer Investor Relations URL; fallback now skips IR/investor text for website fields.

## Evidence

Commands run:

```bash
python3 -m py_compile app/services.py scripts/company_material_inbox_ingest.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_material_inbox_script_dry_run_plans_without_mutation tests.test_system.SystemServiceTests.test_company_material_inbox_script_executes_profile_backfill tests.test_system.SystemServiceTests.test_company_material_inbox_script_rejects_research_and_manual_sources tests.test_system.SystemServiceTests.test_company_profile_field_extraction_updates_from_official_evidence
python3 scripts/check_handoffs.py
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
```

Result:

- Passed: Python compile.
- Passed: focused T-461 script tests.
- Passed: T-460 extraction regression.
- Passed: handoff validation.
- Passed: UI static check.
- Passed: full unit discovery, 244 tests.
- Passed: security check.

## Decisions

- Implemented T-461 as a local script rather than a new backend ingestion subsystem.
- Required manifest metadata instead of filename inference so company/source/document boundaries remain explicit.
- Kept the script local-only and no-download; it only reads local files and calls existing APIs.
- Used existing `CompanyProfileFieldAssertion` as the downstream provenance target.
- Kept rejected research/news/manual records out of source registration and document ingestion.

## Risks and Open Questions

- Current script reads text/Markdown/HTML only; PDF/OCR material should be converted first or routed through a later OCR-specific slice.
- Re-running execute can extract duplicate evidence for an existing document because there is no narrow evidence-by-document query endpoint.
- Source governance reviews are not automatically created; users should still review source TOS/robots/publicness for long-running use.
- T-462 should expose a company intelligence completeness verdict in UI so users can see whether inbox backfill materially improved a company.

## Artifacts

- `artifacts/company-material-inbox-ingest.json`: produced by script runs; local-only, generated only when the script is executed, not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Script added.
- [x] Manifest boundary documented.
- [x] Dry-run and execute paths tested.
- [x] Research/news/manual boundary tested.
- [x] Docs and todo updated.

## Next Steps

1. Implement T-462 company intelligence completeness verdict UI.
2. Add optional evidence-by-document idempotency support before large repeated inbox runs.
3. Add an OCR/PDF handoff path if official PDFs become the dominant company material input.

## Next Recommended Action

Continue with T-462 company intelligence completeness verdict UI so users can see whether company material inbox backfill made the company database usable.
