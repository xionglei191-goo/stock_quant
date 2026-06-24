# Handoff: T-439 Company Relationship Builder

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-439

## Objective

Add the first automatic company-relationship builder so company pages have first-class relationship records in addition to profiles and events. This slice intentionally limits relationships to listings and institution coverage, avoiding customer/supplier/competitor claims without stronger fact evidence.

## Scope

- In scope: relationship builder API, listed-security relationships, institution-coverage relationships from bound research reports, script integration, tests, API/README/task documentation, local sample execution.
- Out of scope: customer, supplier, competitor, equity, product, management/person and industry-chain relationship extraction; external crawling; real trading.

## Background

T-437 materialized company profiles and report bindings. T-438 added the first event timeline. The company relationship layer was still empty, which meant the platform had no first-class company relationship objects for graph and profile completeness.

## Problem Statement

The system could show graph edges from legacy or derived sources, but first-class `CompanyRelationship` records were absent. A company database needs explicit, reviewable relationships with sources, confidence and status.

## Expected Deliverables

- `POST /api/company-database/relationships/build` defaults to dry-run and requires `execute=true` for persistence.
- The endpoint reuses company target resolution from the company database builder.
- The endpoint creates `listed_security` relationships between company and security.
- The endpoint creates `institution_coverage` relationships between company and research institutions based on bound report assets.
- Research institution coverage is marked `review_status=needs_review` and `rights_boundary=opinion_coverage_relationship_not_company_fact`.
- `scripts/build_company_database_minimum.py` supports `--build-relationships`.
- Focused tests verify dry-run, execute and company-intelligence aggregation.

## Current Findings

- Added `SystemService.build_company_relationships`.
- Added `/api/company-database/relationships/build`.
- Extended `scripts/build_company_database_minimum.py --build-relationships`.
- Executed the builder locally for `AAPL,NVDA,600519`.
- Current PostgreSQL sample state: `company_profiles=3`, `company_events=29`, `company_relationships=12`, `research_reports=11702`.
- AAPL company intelligence now shows `company_relationships=4`, profile coverage `0.8` and relationship backlink rate `0.75`.
- Structured viewpoints, analyst reliability scores, first-class analysis conclusions and first-class simulation feedback remain mostly unpopulated for the samples.

## Proposed Work Plan

1. Keep listing and institution coverage as the minimum relationship layer.
2. Add official-disclosure relationship extraction next for customers, suppliers, subsidiaries, major shareholders and partnerships.
3. Add human review and confidence scoring before treating extracted relationships as high-trust facts.
4. Surface `review_status` and `rights_boundary` clearly in the UI for coverage relationships.

## Validation Plan

- Compile changed API, service, script and test files.
- Run focused tests for relationship builder, event builder, company database builder and aggregation.
- Restart local Compose app.
- Execute relationship builder for sample companies.
- Query company-intelligence API for relationship counts and quality.
- Run handoff validation.

## Risks

- Institution coverage relationships are not business relationships and must not be confused with customers, suppliers or owners.
- Broker names can be sparse or localized; relationship IDs use hashed parts for non-ASCII names to avoid collisions.
- Source IDs in the current report inventory include `local_research_unknown`; governance should improve source normalization later.
- Existing relation completeness is still far from a Palantir-like company graph.

## Dependencies

- T-437 report binding.
- Existing `CompanyRelationship` model and `/api/company-relationships`.
- Existing local research report asset inventory.
- Existing local Compose stack at `http://127.0.0.1:8000`.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Relationship build API added.
- [x] Script supports `--build-relationships`.
- [x] Listed-security relationships generated.
- [x] Institution-coverage relationships generated as review-needed opinion coverage relationships.
- [x] Focused tests passed.
- [x] README, API contracts and todo updated.
- [x] Local sample execution completed for `AAPL,NVDA,600519`.
- [x] Running API verified after container restart.

## Evidence

Files changed:

- `app/services.py`: added `build_company_relationships` and non-ASCII-safe relationship ID helper.
- `app/api.py`: added `/api/company-database/relationships/build` route.
- `scripts/build_company_database_minimum.py`: added `--build-relationships`.
- `tests/test_system.py`: added company relationship builder regression.
- `README.md`: documented `--build-relationships`.
- `docs/api-contracts.md`: documented relationship builder endpoint.
- `tasks/todo.md`: added T-439.
- `artifacts/company-database-build.json`: local-only execute artifact now includes relationship builder result.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
docker compose restart ai-quant-org
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519 --limit 3 --report-match-limit 10 --build-events --build-relationships --event-limit 20 --relationship-limit 20 --execute --output artifacts/company-database-build.json
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/AAPL?limit=20'
docker compose exec -T postgres psql -U ai_quant -d ai_quant -Atc "select collection, count(*) from ai_quant.records group by collection order by collection;"
python3 scripts/check_handoffs.py
```

Results:

- Passed: Python compile.
- Passed: focused unit tests.
- Passed: local sample execute, creating 12 relationships.
- Passed: company-intelligence API shows AAPL `company_relationships=4`, profile coverage `0.8`.
- Not run: full `make local-ci`; this was a focused relationship-builder slice and the worktree already contains many unrelated changes.

Artifacts:

- `artifacts/company-database-build.json`: local-only relationship-builder execute artifact.
- Running local URL: `http://127.0.0.1:8000/ui`.

## Next Recommended Action

Implement structured report batches and analysis workflow population for the sample companies, or begin official-disclosure relationship extraction. The database now has profiles, events and basic relationships, but still lacks structured viewpoints, analyst reliability, first-class conclusions and reviewed simulation feedback for most companies.
