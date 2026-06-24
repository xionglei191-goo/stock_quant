# Handoff: T-437 Company Database Builder

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-437

## Objective

Create the first implementation slice for rebuilding the system around a persistent company database. The slice turns existing issuer, security, market data and research report asset records into materialized company profiles and reviewed report bindings while preserving the project boundary: no broker connections, no automatic orders, no research reports as fact sources.

## Scope

- In scope: company database build API, local builder script, company profile materialization, research report asset binding, optional report structuring hook, focused tests, API/README/task documentation, local sample execution.
- Out of scope: automatic company event extraction, automatic relationship extraction, full analyst reliability population, non-local production release, real trading, external data downloads.

## Background

The user clarified that the project should start from a complete company database rather than a virtual fund-company workflow. Inspection showed the running stack had raw records such as `issuers`, `securities` and `research_reports`, but the company intelligence core objects were empty or sparse. Pages appeared empty because the UI expected company profiles, events, relationships and structured viewpoints that had not been built from the raw layer.

## Problem Statement

The system had many one-off object APIs, but no central builder that starts from a company and materializes the minimum usable company database. This made the platform look non-operational even though raw records existed in PostgreSQL.

## Expected Deliverables

- `POST /api/company-database/build` defaults to dry-run and explicitly requires `execute=true` for persistence.
- The builder resolves target companies by `symbols`, `symbol`, `ticker`, `q` or `issuer_ids`.
- The builder can persist `CompanyProfile` from existing issuer, security, market data and research coverage.
- The builder can bind unassigned `ResearchReportAsset` records to companies and securities using ticker/company-token matching.
- Bound research reports are marked `asset_binding.review_status=needs_review`.
- The builder can optionally invoke the existing report-structure flow for matched reports.
- A CLI wrapper produces local artifacts for dry-run and execute.
- Focused tests verify dry-run, execute, profile persistence, report binding and optional structure.

## Current Findings

- Added `/api/company-database/build`.
- Added `scripts/build_company_database_minimum.py`.
- Fixed `CompanyProfile` generation so PostgreSQL lazy-loaded market data contributes to `latest_market_snapshot`.
- Executed a local sample build for `AAPL,NVDA,600519`.
- Current PostgreSQL sample state immediately after T-437 execution: `company_profiles=3`, `research_reports=11702`; company events, relationships and structured viewpoints were not populated by this slice. T-438 later populated the first company events for the same sample companies.
- `AAPL` company intelligence now shows persisted profile coverage `0.6`, 20 market data rows and 26 research report matches in the aggregate view.
- `NVDA` company intelligence now shows persisted profile coverage `0.6`, 20 market data rows and 17 research report matches in the aggregate view.

## Proposed Work Plan

1. Treat this slice as the company database materialization entry point, not the full company graph solution.
2. Continue with automatic event extraction from public disclosures, filings and local documents.
3. Continue with relationship extraction and review workflow for customers, suppliers, competitors, institutions, analysts and industry chains.
4. Run reviewed report-structure batches after report bindings are manually accepted or sampled.

## Validation Plan

- Compile changed API, service, script and test files.
- Run focused unit tests around the new builder and existing company-intelligence/structure flows.
- Restart the local Compose app service.
- Run builder dry-run against the live local service.
- Run a small sample execute against the live local service.
- Query company-intelligence API for sample companies.
- Run handoff validation.

## Risks

- Ticker/name matching is heuristic and can create false positives. This is mitigated by `asset_binding.review_status=needs_review`.
- Sparse issuer names and identifiers limit profile quality.
- The sample execute intentionally did not structure reports, so `structured_research_reports`, `report_viewpoints` and `report_forecasts` remain empty.
- Company events and relationships remain empty; this is the largest remaining database completeness gap.

## Dependencies

- Existing PostgreSQLStore and `ai_quant.records`.
- Existing `Issuer`, `Security`, `MarketDataPoint`, `ResearchReportAsset`, `CompanyProfile` and report-structure models.
- Existing local Compose stack at `http://127.0.0.1:8000`.
- Existing research report asset inventory under the configured local research report root.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Company database build API added.
- [x] Local builder script added.
- [x] Company profile market-data lazy-load issue fixed.
- [x] Focused tests passed.
- [x] API contract and README updated.
- [x] `tasks/todo.md` updated with T-437.
- [x] Local dry-run executed.
- [x] Local sample execute completed for `AAPL,NVDA,600519`.
- [x] Running API verified after container restart.

## Evidence

Files changed:

- `app/services.py`: added builder, target resolution, report binding helpers and direct market-data support in company profile generation.
- `app/api.py`: added `/api/company-database/build` route and policy coverage.
- `scripts/build_company_database_minimum.py`: added CLI wrapper for dry-run/execute.
- `tests/test_system.py`: added builder regression.
- `README.md`: documented builder script usage.
- `docs/api-contracts.md`: documented builder endpoint contract.
- `tasks/todo.md`: added T-437.
- `artifacts/company-database-build.json`: local-only execute artifact.
- `artifacts/company-database-build-dry-run.json`: local-only dry-run artifact.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_research_report_structure_endpoint_writes_viewpoints_and_forecasts
docker compose restart ai-quant-org
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519 --limit 3 --report-match-limit 10 --output artifacts/company-database-build-dry-run.json
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519 --limit 3 --report-match-limit 10 --execute --output artifacts/company-database-build.json
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/AAPL?limit=20'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/NVDA?limit=20'
docker compose exec -T postgres psql -U ai_quant -d ai_quant -Atc "select collection, count(*) from ai_quant.records where collection in ('company_profiles','company_events','company_relationships','research_reports','structured_research_reports','report_viewpoints','report_forecasts') group by collection order by collection;"
python3 scripts/check_handoffs.py
```

Results:

- Passed: Python compile.
- Passed: focused unit tests.
- Passed: Compose app health after restart.
- Passed: dry-run, with 3 planned profiles and 26 matched reports.
- Passed: execute, with 3 saved profiles and 26 bound reports.
- Passed: AAPL/NVDA company-intelligence API shows persisted profile coverage and report coverage.
- Not run: full `make local-ci`; this was a focused database-builder slice and the worktree already contains many unrelated changes.

Artifacts:

- `artifacts/company-database-build.json`: local-only, produced by builder execute, records 3 saved profiles and 26 bound report assets.
- `artifacts/company-database-build-dry-run.json`: local-only, produced by builder dry-run, records planned profiles and matches.
- Running local URL: `http://127.0.0.1:8000/ui`.

## Next Recommended Action

Implement T-438 automatic company event extraction and T-439 company relationship extraction. The database now has a company-profile and report-binding entry point, but it is still not a complete company database until events, relationships, structured viewpoints and analysis feedback are populated.
