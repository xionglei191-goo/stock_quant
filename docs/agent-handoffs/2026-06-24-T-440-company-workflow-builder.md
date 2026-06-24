# Handoff: T-440 Company Workflow Builder

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-440

## Objective

Add the first automatic workflow builder for the company intelligence platform so a company page can show observation tasks, baseline analysis conclusions and paper-only simulation feedback after the profile, event, relationship and research viewpoint layers exist.

## Scope

- In scope: workflow builder API, CLI integration, focused regression test, API/README/todo documentation.
- Out of scope: real trading, broker integration, automated buy/sell advice, realized performance scoring, analyst reliability recomputation, official-disclosure relationship extraction.

## Background

T-437 created the company database build entry point. T-438 added minimum event timelines. T-439 added first-class listing and institution coverage relationships. The next visible gap was the feedback layer: `ObservationItem`, `AnalysisConclusion` and `SimulationFeedback` existed as models and manual APIs, but there was no builder to populate them from an existing company database.

## Problem Statement

Company pages could show profiles, events, relationships and research viewpoints, but the observation/conclusion/feedback layer still needed manual API writes. This made the platform feel incomplete for the user's intended loop: record analysis, track whether it was valid, and use simulated feedback only as a research validation tool.

## Expected Deliverables

- `POST /api/company-database/workflow/build` defaults to dry-run and requires `execute=true` for persistence.
- The builder reuses the company target resolution from the database builders.
- The builder creates `ObservationItem`, `AnalysisConclusion` and `SimulationFeedback`.
- The builder refreshes existing baseline records by default when new event, relationship or viewpoint links appear.
- Generated feedback remains paper-only and cannot connect to brokers.
- The CLI supports `--build-workflow`.
- Focused tests verify dry-run, execute and company-intelligence aggregation.

## Current Findings

- Added `POST /api/company-database/workflow/build`.
- Added `SystemService.build_company_workflow`.
- Extended `scripts/build_company_database_minimum.py --build-workflow`.
- Added a focused regression test covering dry-run, execute and `/api/company-intelligence/{symbol}` aggregation.
- Added default refresh of existing baseline records so later structured report batches can update prior conclusions and feedback links.
- Updated `README.md`, `docs/README.md`, `docs/api-contracts.md`, `tasks/todo.md` and this handoff index.

## Proposed Work Plan

1. Treat this slice as the minimum analysis-feedback population layer.
2. Continue with realized performance updates using market data and review dates.
3. Continue with viewpoint realization and analyst reliability scoring after more forecasts have actuals.
4. Keep all generated conclusions as research baselines rather than investment advice.

## Validation Plan

- Compile changed API, service, script and test files.
- Run the focused workflow builder regression.
- Run adjacent company database, event and relationship builder regressions.
- Run handoff validation.

## Decisions

- The generated conclusion uses `conclusion_type=company_intelligence_baseline` and `status=draft`.
- The generated feedback is always `feedback_type=watch_only`, `paper_only=true`, `live_execution_allowed=false` and `broker_connected=false`.
- The builder links recent company events, company relationships, report viewpoints and evidence IDs where available.
- Missing events, relationships or structured viewpoints are recorded as `evidence_gap` rather than silently treated as complete data.
- Existing baseline records are refreshed by default instead of requiring delete/recreate.

## Risks and Open Questions

- The workflow builder creates a baseline research skeleton, not a real investment conclusion.
- Simulation performance remains pending until later runs compare against market data and review outcomes.
- Analyst reliability scoring still depends on forecast realization review and is not recomputed by this builder.

## Dependencies

- T-437 company database builder.
- T-438 company event builder.
- T-439 company relationship builder.
- Existing `ObservationItem`, `AnalysisConclusion`, `SimulationFeedback`, `CompanyEvent`, `CompanyRelationship`, `ReportViewpoint` and market-data models.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Workflow build API added.
- [x] CLI supports `--build-workflow`.
- [x] Generated feedback remains paper-only.
- [x] Existing workflow records can be refreshed.
- [x] Focused tests passed.
- [x] README, API contracts and todo updated.
- [x] Local sample execute completed for `AAPL,NVDA,600519`.
- [x] Handoff validation passed after format correction.

## Evidence

Files changed:

- `app/api.py`: route and handler for `/api/company-database/workflow/build`.
- `app/services.py`: workflow builder implementation and dirty resource marking.
- `scripts/build_company_database_minimum.py`: added `--build-workflow` and `--workflow-link-limit`.
- `tests/test_system.py`: added focused workflow builder regression.
- `README.md`: documented end-to-end builder command.
- `docs/api-contracts.md`: documented workflow builder contract.
- `tasks/todo.md`: added T-440 completion entry.
- `docs/agent-handoffs/README.md`: added T-440 to related tasks.
- `docs/README.md`: updated roadmap index range through T-440.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_workflow_builder_creates_observation_conclusion_and_paper_feedback
python3 -m unittest tests.test_system.SystemServiceTests.test_company_workflow_builder_creates_observation_conclusion_and_paper_feedback tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports
docker compose restart ai-quant-org
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519 --limit 3 --report-match-limit 10 --build-events --build-relationships --structure-reports --build-workflow --execute --output artifacts/company-database-build.json
curl -sS --max-time 120 -X POST 'http://127.0.0.1:8000/api/research-reports/structure' -H 'Content-Type: application/json' -H 'X-Role: analyst' -H 'X-Actor: company_database_builder' -d '{"issuer_id":"issuer_600519","limit":10,"execute":true}'
curl -sS --max-time 60 -X POST 'http://127.0.0.1:8000/api/company-database/workflow/build' -H 'Content-Type: application/json' -H 'X-Role: data_engineer' -H 'X-Actor: company_database_builder' -d '{"symbols":["600519"],"limit":1,"link_limit":5,"execute":true}'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/AAPL?limit=20'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/NVDA?limit=20'
curl -sS --max-time 10 'http://127.0.0.1:8000/api/company-intelligence/600519?limit=20'
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile.
- Passed: focused workflow builder test.
- Passed: focused workflow, relationship, event and company database builder test group.
- Passed: local sample execute; AAPL and NVDA each show 10 structured reports, 10 viewpoints, one observation, one conclusion and one feedback record.
- Passed: 600519 follow-up structure/refresh; 600519 shows 6 structured reports, 6 viewpoints, one observation, one conclusion and one feedback record.
- Passed after format correction: handoff validation.
- Not run: full `make local-ci`; this is a focused builder slice and the worktree already contains broad unrelated changes.

Artifacts:

- `artifacts/company-database-build.json`: existing local-only builder output can now include `workflow_result` when `--build-workflow` is used.

## Next Recommended Action

1. Run a local sample execute with `--structure-reports --build-events --build-relationships --build-workflow`.
2. Query `/api/company-intelligence/{symbol}` for the sample companies and confirm workflow counts are visible.
3. Add realized performance and viewpoint realization update jobs after more event/market data is available.
