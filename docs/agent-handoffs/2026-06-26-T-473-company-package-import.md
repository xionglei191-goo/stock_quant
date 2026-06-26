# Handoff: T-473 Company Package Import

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-473

## Status

- Status: DONE
- Owner group: Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Add a local watchlist / company package import path so analysts can start a company database from multiple symbols or a local JSON/CSV package, then continue into official/IR material inbox ingestion.

## Background

T-472 let users bootstrap a single unknown symbol. Analysts still needed a local-first way to start from a watchlist, CSV, or sample company package without manually repeating bootstrap one symbol at a time.

## Problem Statement

The company database first-mile flow was single-company only. That made a realistic research workflow awkward because the user typically starts from a coverage list, watchlist, or themed package of companies.

## Expected Deliverables

- Local-only package/watchlist import API.
- Dry-run default and explicit execute behavior.
- Per-company bootstrap result and material inbox manifest template.
- Workbench controls for preview and execute.
- Material inbox API execute regression.
- Docs, roadmap and handoff updates.

## Scope

- In scope: API route, service wrapper, local JSON/CSV package parsing, UI controls, tests, API docs, task entry and handoff.
- Out of scope: external company search, external downloads, upload widgets, persistent watchlist run history and material manifest file generation.

## Current Findings

- `bootstrap_company_database` already implements idempotent issuer/security/profile stub creation and exact symbol resolution without all-company fallback.
- `company_material_inbox_ingest` already handles official/IR material execution, but route-level execute coverage was missing.
- The existing workbench has a natural location for package import in the company database completion panel before material inbox ingestion.

## Proposed Work Plan

1. Add package/watchlist import routes.
2. Add a thin service wrapper that parses local package inputs and calls bootstrap per company.
3. Add workbench inputs, counters, result rows and JS calls.
4. Add focused package import and material inbox execute tests.
5. Update docs, roadmap and handoff.

## Validation Plan

- Compile app, tests and scripts.
- Run focused package/material inbox unit tests.
- Run UI static contract check.
- Run handoff validation and whitespace diff check.
- Run browser interaction acceptance when the local service matches the current worktree.

## Current State

- Completed: `POST /api/company-database/package/import` and alias `POST /api/company-database/watchlist/import`.
- Completed: package import accepts local `root_path` package manifests, `companies/items/watchlist`, `symbols/tickers/codes`, and inline `csv_text`.
- Completed: import defaults to dry-run; `execute=true` creates local issuer/security/profile stubs by reusing `bootstrap_company_database`.
- Completed: duplicate symbols and missing symbols are reported per row; empty or invalid rows do not fallback to all issuers.
- Completed: company intelligence workbench has local watchlist / company package preview and execute controls.
- Completed: material inbox API execute now has direct route-level regression coverage.
- Not started: full watchlist history model, upload widget, and material package generation wizard.
- Blocked: None.

## Dependencies

- Existing `bootstrap_company_database`.
- Existing company intelligence symbol matching helpers.
- Existing material inbox manifest contract.
- Existing company database coverage audit.

## Blockers

- None.

## Files Touched

- `app/api.py`: added package/watchlist import routes.
- `app/services.py`: added local package/watchlist parser and import wrapper around bootstrap.
- `app/static/index.html`: added workbench controls, counters, result table, and JS functions.
- `scripts/ui_static_check.py`: added UI contract IDs and functions.
- `scripts/ui_interaction_acceptance.py`: added package import preview render check.
- `tests/test_system.py`: added package import regressions and material inbox API execute regression.
- `docs/api-contracts.md`: documented package import and material inbox execute semantics.
- `docs/README.md`: updated company intelligence task range to T-473.
- `tasks/todo.md`: added DONE T-473.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_package_import_bootstraps_watchlist_companies tests.test_system.SystemServiceTests.test_company_database_package_import_does_not_fallback_to_all_issuers tests.test_system.SystemServiceTests.test_company_material_inbox_api_execute_backfills_profile_fields
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_interaction_acceptance.py
git diff --check
curl --max-time 5 -sS http://127.0.0.1:8000/api/health
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance
python3 -c "from app.server import serve; serve(port=8768)"
curl --max-time 5 -sS http://127.0.0.1:8768/api/health
curl --max-time 120 -sS -X POST http://127.0.0.1:8768/api/company-intelligence/SPCX/cycle/run -H 'Content-Type: application/json' -d '{"execute":false,"dry_run":true}'
curl --max-time 5 -sS -X POST http://127.0.0.1:8768/api/company-database/package/import -H 'Content-Type: application/json' -d '{"symbols":["PKGSMOKE"],"dry_run":true}'
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-current
```

Result:

- Passed: Python compile on app, tests and scripts.
- Passed: 3 focused package/material-inbox tests.
- Passed: UI static check.
- Passed: `scripts/ui_interaction_acceptance.py` syntax compile.
- Passed: whitespace diff check before handoff.
- Passed: existing local service health check.
- Partial then resolved: browser interaction acceptance against the pre-existing `127.0.0.1:8000` service ran 26 checks; new `company_package_import_preview_render` passed, but the full run failed on existing `company_intelligence_cycle_preview` because that running service returned `route not found` for `POST /api/company-intelligence/SPCX/cycle/run`.
- Passed: started current worktree app on `127.0.0.1:8768`; health, cycle route smoke and package import smoke passed.
- Passed: browser interaction acceptance against `127.0.0.1:8768` passed 26/26, including `company_package_import_preview_render`.

## Evidence

- Focused package import test proves dry-run does not mutate store, execute creates three company stubs, duplicate input is reported, and rerun is idempotent.
- Focused no-fallback test proves missing-symbol package rows do not include existing issuers or trigger broad discovery.
- Focused material inbox API test proves route-level execute registers source, writes document, extracts evidence and updates profile field assertions.
- UI static check proves the new workbench controls and JS functions are present.
- Browser interaction acceptance proves the new package render check passes; rerunning against a current-code service on port 8768 passed the full 26-check UI interaction suite.

## Decisions

- The new endpoint is a thin wrapper around bootstrap rather than a separate importer stack.
- JSON/CSV package import reads local files only; no external company lookup or download is attempted.
- The response schema is `company-database-package-import-v1`; `/watchlist/import` is a compatibility alias.
- Each row returns a material inbox manifest template so official/IR/public company material remains the next fact-source step.
- Research reports stay out of fact field population; this import only creates local company database stubs.

## Risks and Open Questions

- The pre-existing local service at port 8000 was stale relative to the worktree during this task; use the current-code 8768 run or restart the normal service before presenting browser acceptance evidence.
- Package import does not persist a dedicated watchlist run history yet; audit is currently via API response and audit log.
- UI currently accepts path/glob only; a richer form for inline CSV or company-name overrides can be added later.

## Artifacts

- `artifacts/ui-interaction-acceptance`: local browser acceptance output from the stale 8000 service. Local-only diagnostic evidence.
- `artifacts/ui-interaction-acceptance-current`: passing local browser acceptance output from the current-code 8768 service. Local-only evidence; not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Code changes completed.
- [x] API docs updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [x] Focused tests and UI static check completed.
- [x] Full browser interaction acceptance passed from a current-code service.

## Next Steps

1. Commit and push T-473 when ready.
2. Add a dedicated watchlist import history model if analysts need long-running watchlist package audits.
3. Add a UI helper to generate material inbox manifest files from package import results.

## Next Recommended Action

Commit and push T-473, then continue with watchlist import history or material manifest generation.
