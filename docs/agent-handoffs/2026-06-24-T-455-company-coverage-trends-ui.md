# Handoff: T-455 Company Coverage Trends UI

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-455

## Objective

Expose company database coverage trends and retry/partial run status in the company intelligence workbench so users can see whether补库 is improving the company database without opening raw JSON.

## Scope

- In scope: static UI, trend loading/rendering, run-history metadata display, UI static contract, interaction acceptance, docs index, todo and handoff.
- Out of scope: changing coverage-trend math, executing补库 from trend loading, new external data sources, charting library adoption, real broker integration, real trading.

## Background

T-453 added `/api/company-database/coverage/trends`, and T-454 added retry/resume and partial-run metadata. The backend could now explain coverage change over time, but the workbench still lacked a visible trend view.

## Problem Statement

The user sees many empty or raw JSON states unless the workbench surfaces the database operations history. A company intelligence platform needs visible feedback on whether repeated补库 is reducing missing sections and whether failed/partial runs are recoverable.

## Expected Deliverables

- Add a read-only coverage trend control in the company database panel.
- Render trend summary metrics and trend rows.
- Show retry/partial metadata in run-history rows.
- Use human labels for local-only boundaries.
- Extend UI static and browser interaction acceptance checks.

## Current Findings

- The existing company database panel already has run-history controls and enough room for a compact trend table.
- The trend endpoint can be filtered by `issuer_id` and does not execute补库.
- `statusLabel` already maps `partial` to a human label.
- Existing run-history rows can show retry metadata without adding a new panel.

## Proposed Work Plan

1. Add DOM controls and metric boxes for coverage trends.
2. Add trend payload/render/load helpers.
3. Refresh trends after company load and batch execution.
4. Add local-only boundary labels.
5. Update UI static and interaction acceptance.

## Validation Plan

- Compile Python modules and scripts.
- Run UI static contract check.
- Run focused company database tests affected by T-454/T-455.
- Run browser interaction acceptance if local Chrome/server startup is available.
- Run handoff validation and diff whitespace check.

## Current State

- Completed: added `loadCompanyCoverageTrends`, trend status, cumulative coverage delta, missing delta and trend rows.
- Completed: trend loading uses `POST /api/company-database/coverage/trends` as analyst with current issuer filter only.
- Completed: run-history rows display retry source, resume mode, completed/skipped counts and human local-only boundary labels.
- Completed: executing a batch build and loading company intelligence refresh both run history and trend rows.
- Completed: UI static and interaction acceptance scripts include the new controls, status labels, stable demo-state reset and failure diagnostics.
- Blocked: none.

## Files Touched

- `app/static/index.html`: added trend UI, render/load helpers, boundary labels, `executed`/`dry_run` status labels and run-history retry metadata display.
- `scripts/ui_static_check.py`: added required trend DOM IDs and JS functions.
- `scripts/ui_interaction_acceptance.py`: added browser acceptance for coverage trend loading and human boundary labels; reset demo inputs before dependent checks and capture concise DOM diagnostics on failure.
- `tasks/todo.md`: added T-455.
- `docs/README.md`: updated task range.
- `docs/agent-handoffs/README.md`: added T-455.
- `docs/agent-handoffs/2026-06-24-T-455-company-coverage-trends-ui.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_resume_run_id_retries_remaining_issuers tests.test_system.SystemServiceTests.test_company_database_batch_retry_replays_source_run tests.test_system.SystemServiceTests.test_company_database_coverage_trends_report_and_artifact
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
bash -lc 'export AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB= AI_QUANT_OBJECT_STORE_BACKEND=local AI_QUANT_OBJECT_STORE=/tmp/ai_quant_ui_acceptance_objects_8014 AI_QUANT_SEARCH_BACKEND=local; python3 -c "from app.server import get_router, serve; get_router(); serve(port=8014)"'
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8014 --timeout 60
```

Result:

- Passed: Python compile.
- Passed: UI static check.
- Passed: focused company database tests, 3 tests.
- Passed: full clean-env unit test discovery, 231 tests.
- Passed: security check.
- Passed: handoff validation.
- Passed: diff whitespace check.
- Passed: browser interaction acceptance on fresh local server, 15 checks.
- Failed: none.

## Decisions

- The trend UI is read-only and does not send `write_artifact`, build options or external data-source requests.
- The interface stays data-dense and table-first; no new charting dependency was added.
- Internal usage-boundary constants are mapped to human labels in the UI.
- Retry preview buttons were left out of this slice; the UI now makes retry/partial state visible first.

## Dependencies

- T-453 coverage trends API.
- T-454 retry/resume metadata and slim run-history rows.
- Existing company intelligence workbench static UI.

## Blockers

- None.

## Risks and Open Questions

- Trend rows are textual tables, not a chart; a later slice can add a small line chart if the data density remains readable.
- Browser interaction acceptance depends on local Chrome availability and current-code server startup.
- Retry actions are still API-only; a later UI slice can add safe dry-run retry preview buttons.

## Artifacts

- None committed. Browser acceptance, if run, may create local-only screenshots/logs under `artifacts/ui-interaction-acceptance/`.

## Handoff Checklist

- [x] DOM controls added.
- [x] Trend render/load helpers added.
- [x] Run-history metadata display added.
- [x] UI static contract updated.
- [x] UI interaction acceptance updated.
- [x] Todo and docs index updated.
- [x] Final validation completed after this handoff.

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_batch_resume_run_id_retries_remaining_issuers tests.test_system.SystemServiceTests.test_company_database_batch_retry_replays_source_run tests.test_system.SystemServiceTests.test_company_database_coverage_trends_report_and_artifact
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8014 --timeout 60
```

Result:

- Passed: compile, UI static check, focused company database tests, full 231-test suite, security check, handoff validation, diff whitespace check and browser interaction acceptance on a fresh current-code server.

## Next Steps

1. T-456: audit deep company-profile field coverage and source plan.
2. T-457: enrich company profiles from already-ingested official disclosures and company IR documents.
3. Add safe retry/resume preview actions to the UI after the API-only workflow settles.

## Next Recommended Action

Implement T-456 company profile deep-field coverage audit and source plan, then use it to prioritize the next data-source or filing-extraction work.
