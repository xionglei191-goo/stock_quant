# Handoff: T-432 Company Intelligence Core Completion

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-432, T-433, T-434, T-435, T-436

## Objective

Complete the company intelligence implementation route after the T-431 product redirection. The goal is to make company profiles, events, relationships, research report viewpoints, observations, analysis conclusions, and simulation feedback first-class API and UI concepts instead of only roadmap documents.

## Scope

- Add API routes and handlers for first-class company intelligence objects.
- Aggregate those objects in `/api/company-intelligence/{symbol}`.
- Add graph-query backlinks for events, relationships, viewpoints, conclusions, and simulation feedback.
- Reframe `/ui` navigation and the company intelligence workbench around the new product direction.
- Update roadmap and API documentation.

## Background

The project was repositioned from an organization/execution workflow to a company intelligence and market analysis platform. The user asked to complete all of T-431 through T-436, not just document the route.

## Problem Statement

Before this completion pass, `CompanyProfile`, `CompanyEvent`, `CompanyRelationship`, `ReportViewpoint`, `ObservationItem`, `AnalysisConclusion`, and `SimulationFeedback` existed in models/services, but not all were exposed as stable APIs, included in the symbol-level workbench aggregation, or reflected in the UI and roadmap status.

## Expected Deliverables

- `GET|POST /api/company-profiles` and `GET /api/company-profiles/schema`.
- `GET|POST /api/company-events` and `/api/company-relationships`.
- Structured report, viewpoint, forecast, analyst, and reliability score APIs.
- Observation, analysis conclusion, and paper-only simulation feedback APIs.
- Company intelligence aggregation returns first-class object sections and data quality metrics.
- Graph query returns company event, relationship, report viewpoint, conclusion, and feedback nodes/edges.
- UI main navigation is company intelligence centered, with old approval/execution views marked as compatibility.
- `tasks/todo.md` marks T-432 through T-436 done.

## Current Findings

- First-class object service methods were already partly present in `app/services.py`.
- Missing pieces were API exposure, aggregation use, graph backlinks, UI information architecture, roadmap status, and tests.
- `SimulationFeedback` now remains model-enforced paper-only and rejects live execution flags.

## Proposed Work Plan

1. Treat T-431 as the completed documentation redirection baseline.
2. Treat this handoff as the completion record for T-432 through T-436.
3. Use future tasks for deeper scoring algorithms, richer UI pages, and external graph/vector stores; those are enhancements, not blockers for the current route.

## Validation Plan

- Run Python compile checks.
- Run focused company intelligence API tests.
- Run UI static check after navigation changes.
- Run handoff validation after documentation changes.
- Full `make local-ci` is not required for this Markdown-plus-focused-code pass, but focused tests must pass.

## Risks

- The work keeps legacy decision/execution objects as compatibility data in aggregation responses.
- UI still contains the old approval page as a compatibility tab, so product language must keep distinguishing it from the main path.
- Deeper automated event/price validation scoring remains an enhancement after T-435, not part of this completion pass.

## Dependencies

- Existing `Issuer`, `Security`, `MarketDataPoint`, `Document`, `Evidence`, `ResearchReportAsset`, graph, and paper ledger stores.
- Existing local store serialization in `app/store.py`.
- Existing static UI and UI acceptance scripts.

## Blockers

- None for T-432 through T-436 completion.

## Handoff Checklist

- [x] First-class APIs added.
- [x] Aggregation updated.
- [x] Graph backlinks updated.
- [x] UI main path reframed.
- [x] Roadmap updated.
- [x] API docs updated.
- [x] Focused tests added.
- [x] Final validation commands recorded below.

## Evidence

- `app/api.py`: routes and handlers for company profiles, events, relationships, structured reports, report viewpoints, forecasts, analysts, observations, conclusions, and simulation feedback.
- `app/services.py`: symbol aggregation and graph query now include first-class company intelligence objects.
- `app/static/index.html`: navigation and company intelligence panel prioritize the company intelligence route.
- `scripts/ui_static_check.py`: required navigation labels updated.
- `tests/test_system.py`: focused API, aggregation, paper-only, and graph backlink coverage.
- `docs/api-contracts.md`: first-class API contracts documented.
- `tasks/todo.md`: T-432 through T-436 marked done.

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
```

Results:

- Passed: py_compile.
- Passed: focused company intelligence tests, 2 tests.
- Passed: full unit suite, 211 tests.
- Passed: UI static check, `node_check=passed`.
- Passed: security check, `ok=true`, `findings=[]`.
- Passed: handoff validation, 8 markdown files.
- Failed: none.

Artifacts:

- No new external artifacts.
- Handoff is local-only project coordination evidence.

## Next Recommended Action

Continue with implementation enhancements under new task IDs rather than reopening T-432 through T-436.
