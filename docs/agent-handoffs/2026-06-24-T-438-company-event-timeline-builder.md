# Handoff: T-438 Company Event Timeline Builder

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-438

## Objective

Add the first automatic company-event timeline builder so company pages are not limited to static profiles and research report lists. This slice must use only existing local/public records and must keep research report coverage as an opinion/attention signal rather than a fact source.

## Scope

- In scope: event builder API, market-data events, research-coverage events, script integration, tests, API/README/task documentation, local sample execution.
- Out of scope: external news collection, announcement scraping, order/litigation/policy extraction, relationship extraction, trading signals, real broker workflows.

## Background

T-437 added company profile materialization and research report binding. The company intelligence API then showed profile, market data and research coverage for sample companies, but `company_events` remained empty. A complete company database needs at least a timeline surface before deeper event extraction can be layered in.

## Problem Statement

The platform could identify relevant reports and market data, but it did not convert those records into timeline events. This kept company pages from acting like a durable research database and made the event layer appear unbuilt.

## Expected Deliverables

- `POST /api/company-database/events/build` defaults to dry-run and requires `execute=true` for persistence.
- The endpoint reuses company target resolution from the company database builder.
- The endpoint creates latest public market-data events with `fact_status=verified`.
- The endpoint creates research-coverage events with `fact_status=opinion_signal` and `review_status=needs_review`.
- The builder does not treat research report content as fact truth.
- `scripts/build_company_database_minimum.py` supports `--build-events`.
- Focused tests verify dry-run, execute and company-intelligence aggregation.

## Current Findings

- Added `SystemService.build_company_events`.
- Added `/api/company-database/events/build`.
- Extended `scripts/build_company_database_minimum.py --build-events`.
- Executed the builder locally for `AAPL,NVDA,600519`.
- Current PostgreSQL sample state: `company_profiles=3`, `company_events=29`, `research_reports=11702`.
- AAPL company intelligence now shows `company_events=11` and `event_timeline_available=true`.
- 600519 company intelligence now shows `company_events=7` and `event_timeline_available=true`.
- At T-438 completion time, `company_relationships`, structured viewpoints and first-class analysis feedback were not populated for these samples. T-439 later populated first-class listing and institution-coverage relationships.

## Proposed Work Plan

1. Treat market-data and research-coverage events as the minimum timeline foundation.
2. Add official disclosure and filing event extraction next.
3. Add relationship extraction after events, because relationship evidence often depends on event/document context.
4. Keep all research report derived items clearly marked as opinion/attention signals.

## Validation Plan

- Compile changed API, service, script and test files.
- Run focused unit tests for company event builder, company database builder and company-intelligence aggregation.
- Restart the local Compose app.
- Execute event builder for sample companies.
- Query company-intelligence API for event counts and event data-quality flags.
- Run handoff validation.

## Risks

- Research coverage events can be mistaken for company facts if UI wording is too terse; downstream UI should surface `opinion_signal`.
- Market-data events are useful for timeline completeness but not enough to explain business changes.
- Existing relationship graph availability may still be driven by legacy graph edges rather than first-class `CompanyRelationship`.
- This slice can produce many research coverage events if `event_limit` is high; keep reviewed batches small.

## Dependencies

- T-437 company database builder and report binding.
- Existing `CompanyEvent` model and `/api/company-events` aggregation.
- Existing PostgreSQLStore.
- Existing local Compose stack at `http://127.0.0.1:8000`.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Event build API added.
- [x] Script supports `--build-events`.
- [x] Market-data events generated with verified fact status.
- [x] Research coverage events generated as opinion signals.
- [x] Focused tests passed.
- [x] README, API contracts and todo updated.
- [x] Local sample execution completed for `AAPL,NVDA,600519`.
- [x] Running API verified after container restart.

## Evidence

Files changed:

- `app/services.py`: added `build_company_events` and latest-market helper.
- `app/api.py`: added `/api/company-database/events/build` route and authorization coverage.
- `scripts/build_company_database_minimum.py`: added `--build-events` and event builder call.
- `tests/test_system.py`: added company event builder regression.
- `README.md`: documented `--build-events`.
- `docs/api-contracts.md`: documented event builder endpoint.
- `tasks/todo.md`: added T-438.
- `artifacts/company-database-build.json`: local-only execute artifact now includes event builder result.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
docker compose restart ai-quant-org
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519 --limit 3 --report-match-limit 10 --build-events --event-limit 20 --execute --output artifacts/company-database-build.json
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/AAPL?limit=20'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/600519?limit=20'
docker compose exec -T postgres psql -U ai_quant -d ai_quant -Atc "select collection, count(*) from ai_quant.records where collection in ('company_profiles','company_events','company_relationships','research_reports','structured_research_reports','report_viewpoints','report_forecasts') group by collection order by collection;"
python3 scripts/check_handoffs.py
```

Results:

- Passed: Python compile.
- Passed: focused unit tests.
- Passed: local sample execute, creating 29 events.
- Passed: company-intelligence API shows AAPL `company_events=11` and 600519 `company_events=7`.
- Passed: event data-quality availability is true for sample companies.
- Not run: full `make local-ci`; this was a focused event-builder slice and the worktree already contains many unrelated changes.

Artifacts:

- `artifacts/company-database-build.json`: local-only event-builder execute artifact.
- Running local URL: `http://127.0.0.1:8000/ui`.

## Next Recommended Action

Implement T-439 first-class company relationship extraction. The database now has profiles, research bindings and timeline events for sample companies, but it still lacks `CompanyRelationship` records for customers, suppliers, competitors, institutions, analysts and industry-chain links.
