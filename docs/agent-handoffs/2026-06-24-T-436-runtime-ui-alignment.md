# Handoff: T-436 Runtime UI Alignment

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-436

## Objective

Make the running `/ui` and health surface visibly reflect the company intelligence platform direction. This fixes the gap where roadmap and documentation said the UI had moved, while the first screen and runtime metadata still looked like the old AI-native quant organization.

## Scope

- In scope: visible `/ui` title, first-screen headings, navigation labels, workflow labels, compatibility wording, UI acceptance strings, health service metadata, default public-source user-agent strings, local Compose app-container reload.
- Out of scope: renaming legacy API paths such as `/api/execution-intents`, removing compatibility approval pages, changing database schema, changing real data ingestion behavior.

## Background

T-431 through T-436 had been marked complete, and the API/data model work for company intelligence had been implemented. The user then reported that running the project still had little visible effect. Inspection showed the static page still exposed old top-level wording in key places, and the running container still returned the old health `service` name until restarted.

## Problem Statement

The implementation was functionally present but not obvious at runtime. The top page title, H1, role labels, browser/smoke acceptance strings, and health metadata were still partially anchored to the old organization/execution narrative, so a user opening `http://127.0.0.1:8000/ui` could reasonably conclude nothing meaningful changed.

## Expected Deliverables

- `/ui` browser title and H1 show `公司情报与市场综合分析平台`.
- First-screen flow shows `公司情报主流程` with data lake, company profile, event timeline, relationship graph, multi-source viewpoints, and simulation feedback.
- Company intelligence navigation is primary; old approval/execution wording is constrained to compatibility semantics.
- Knowledge graph input accepts ticker symbols by resolving them through `/api/company-intelligence/{symbol}` before querying `/api/graph/query`.
- `/api/health` returns `service=company-intelligence-platform` after app-container reload.
- UI, smoke, staging, and browser acceptance required-text checks use the new product name.
- Favicon request no longer produces a browser console 404.

## Current Findings

- `http://127.0.0.1:8000/ui` now returns the new title, H1, and company intelligence headings.
- `http://127.0.0.1:8000/api/health` now returns `service=company-intelligence-platform`.
- In the knowledge graph tab, entering `SPCX` now resolves to `issuer_spcx` and loads local graph data; entering non-existent `SPAX` now shows an explicit local-missing message instead of a silent empty table.
- The running stack is Docker Compose, with the app still using the legacy Compose service name `ai-quant-org`; this was not renamed to avoid a broader deployment/service-name migration.
- The browser console no longer reports the previous favicon 404 after the app container is recreated.

## Proposed Work Plan

1. Treat the visible runtime mismatch as a T-436 follow-up fix, not a reopening of the company intelligence core model work.
2. Keep compatibility APIs and pages in place while replacing default user-facing wording.
3. Defer any deeper service/container renaming to a separate infrastructure task because it can affect Compose service dependencies, docs, and operational scripts.

## Validation Plan

- Run Python compile checks for modified app, script, and test files.
- Run UI static contract check.
- Run focused unit tests for health, UI readiness, cross-browser text validation, and company intelligence SPCX aggregation.
- Run handoff validation.
- Verify the running Compose app at `http://127.0.0.1:8000/ui`, `/api/health`, and `/favicon.ico`.
- Open `/ui` with Playwright to confirm the browser title and console state.

## Risks

- The Compose service and image are still named `ai-quant-org`; this is operational naming debt, not a user-facing product flow blocker.
- Some legacy documents and APIs still describe paper decision/execution compatibility. They should remain until a separate compatibility-migration task removes or renames them safely.
- Existing browser sessions may need a hard refresh if they cached the old HTML before this fix.

## Dependencies

- Existing Docker Compose stack and mounted `./app` volume.
- Existing company intelligence API and UI work from T-432 through T-436.
- Existing static UI validation and unit test infrastructure.

## Blockers

- None for the runtime UI alignment fix.

## Handoff Checklist

- [x] Runtime title and H1 updated.
- [x] First-screen workflow and dynamic UI labels updated.
- [x] Acceptance scripts and test required text updated.
- [x] Health service name updated.
- [x] Favicon 404 eliminated with a 204 response.
- [x] App container recreated to load Python changes.
- [x] Checks and running endpoint verification completed.

## Evidence

Files changed:

- `app/static/index.html`: product title, H1, first-screen flow, role labels, graph section wording, compatibility-page labels, dynamic result labels.
- `app/static/index.html`: knowledge graph input now resolves ticker symbols and displays an explicit not-found state for unknown local symbols.
- `app/server.py`: health/root service name and `/favicon.ico` 204 response.
- `app/services.py`: health service name plus default SEC/HKEX user-agent and lineage namespace defaults.
- `docker-compose.yml`: default `AI_QUANT_SEC_USER_AGENT`.
- `README.md`: clarified that local bare startup must clear Postgres DSN variables or install `psycopg` when `.env` points at PostgreSQL.
- `scripts/ui_static_check.py`, `scripts/ui_browser_acceptance.py`, `scripts/smoke_test.py`, `scripts/staging_acceptance.py`, `scripts/staging_otel_acceptance.py`: required text and runtime metadata expectations.
- `tests/test_system.py`: UI required-text expectations.
- `docs/user-manual.md`: document title and version marker.

Commands run:

```bash
python3 -m py_compile app/server.py app/services.py scripts/*.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_health_and_metrics_endpoints tests.test_system.SystemServiceTests.test_ui_readiness_report_requires_browser_matrix_and_workflow_evidence tests.test_system.SystemServiceTests.test_ui_cross_browser_matrix_validator_requires_families_viewports_and_text tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research
docker compose up -d --force-recreate ai-quant-org
curl -sS http://127.0.0.1:8000/ui | rg -n "<title>|<h1>|最新公司情报分析|公司情报主流程|AI 原生|虚拟量化"
curl -sS http://127.0.0.1:8000/api/health | python3 -m json.tool | sed -n '1,18p'
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/favicon.ico
python3 scripts/check_handoffs.py
```

Results:

- Passed: Python compile.
- Passed: UI static check.
- Passed: 4 focused unit tests.
- Passed: handoff validation.
- Passed: `/ui` title/H1/headings return company intelligence wording.
- Passed: `/api/health` returns `service=company-intelligence-platform`.
- Passed: `/favicon.ico` returns `204`.
- Passed: Playwright opened `/ui?verify=company-intelligence` with page title `公司情报与市场综合分析平台` and no reported console error after the favicon fix.
- Passed: Playwright verified `SPCX` resolves to `issuer_spcx` and loads graph facts; `SPAX` displays `未找到本地主体`.

Artifacts:

- Running local URL: `http://127.0.0.1:8000/ui` (local-only).
- Running health URL: `http://127.0.0.1:8000/api/health` (local-only).

## Next Recommended Action

Open `http://127.0.0.1:8000/ui` with a hard refresh. If the user still sees the old page, check browser cache or whether they are opening another port/container; the verified local Compose stack on port 8000 now serves the company intelligence UI.
