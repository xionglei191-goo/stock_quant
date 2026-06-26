# Handoff: T-472 Company Database Bootstrap

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-472

## Status

- Status: DONE
- Owner group: Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Let an analyst start a local company database from a previously unknown symbol by creating a minimal issuer/security/profile stub and receiving the next material-ingestion template.

## Background

The company intelligence workbench could show unknown symbols, but the build pipeline depended on existing issuer/security records. This left users with empty tables and no direct way to establish the first company database object for a new watchlist name.

## Problem Statement

`GET /api/company-intelligence/{symbol}` returned `not_found`, while `POST /api/company-database/build` could only operate after a local issuer/security existed. The missing first-run bootstrap blocked material inbox ingestion, coverage audit and later company database build steps.

## Expected Deliverables

- A local-only bootstrap API that defaults to dry-run.
- Idempotent issuer/security/profile stub creation when `execute=true`.
- Manifest template for official/IR material inbox.
- Company intelligence next action updated from research-run-first to bootstrap-first.
- Minimal UI action to preview bootstrap from the workbench.
- Focused tests and updated docs/roadmap/handoff.

## Scope

- In scope: API route, service method, next action semantics, minimal UI guidance action, API docs, roadmap, handoff and focused backend/UI static checks.
- Out of scope: external company search, automatic data download, real broker integration, full watchlist CSV import, and dedicated bootstrap form fields beyond current symbol input.

## Current Findings

- `_company_database_target_issuers` intentionally falls back to all issuers when no symbol matches, so bootstrap needs exact symbol resolution without fallback.
- `company-database/build` already materializes profiles and binds reports, but only after issuer/security records exist.
- `company_material_inbox_ingest` requires explicit issuer/security/source/document manifest fields.
- Unknown company intelligence currently returns `not_found` and next actions; this is the right place to point the user to bootstrap.

## Proposed Work Plan

1. Add exact symbol-to-existing-issuer helper for bootstrap.
2. Add `bootstrap_company_database` with dry-run and execute modes.
3. Register `POST /api/company-database/bootstrap`.
4. Update next actions and minimal UI action routing.
5. Add focused tests, docs, roadmap and handoff.

## Validation Plan

- Compile app, tests and scripts.
- Run bootstrap focused unit tests.
- Run UI static check.
- Run handoff validation.
- Run whitespace diff check.

## Current State

- Completed: `POST /api/company-database/bootstrap` is registered.
- Completed: dry-run returns planned issuer/security IDs, coverage preview and material inbox manifest template without writing.
- Completed: execute creates local issuer/security/company profile stubs and is idempotent on rerun.
- Completed: bootstrap writes `cik`/`lei` to `Issuer` and `figi`/`isin` to `Security` when provided.
- Completed: explicit unknown symbols no longer fall back to all companies in build/coverage audit.
- Completed: unknown symbol company intelligence next action points to `/api/company-database/bootstrap`.
- Completed: workbench guidance button can preview bootstrap and render the returned plan.
- Completed: API docs and `tasks/todo.md` list T-472.
- Completed: final validation passed before commit/push.
- Not started: dedicated UI form for exchange/currency/company name overrides and watchlist CSV import.
- Blocked: None.

## Dependencies

- Existing `Issuer`, `Security` and `CompanyProfile` models.
- Existing company intelligence symbol token matching.
- Existing material inbox manifest contract.
- Existing coverage audit.

## Blockers

- None.

## Files Touched

- `app/api.py`: added bootstrap route and handler.
- `app/services.py`: added bootstrap service, exact symbol resolution helper, market defaults, manifest template and next action update.
- `app/static/index.html`: routed company intelligence guidance to bootstrap dry-run preview.
- `tests/test_system.py`: added bootstrap regression and updated unknown-symbol next action expectation.
- `docs/api-contracts.md`: documented bootstrap payload, response and boundaries.
- `tasks/todo.md`: added DONE T-472.
- `docs/agent-handoffs/2026-06-26-T-472-company-database-bootstrap.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_bootstrap_creates_local_stub_for_unknown_symbol tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_company_database_unknown_symbol_does_not_fallback_to_all_companies
python3 scripts/ui_static_check.py
```

Result:

- Passed: Python compile on app, tests and scripts.
- Passed: focused bootstrap, SPCX unknown->available flow and unknown-symbol no-fallback regressions.
- Passed: UI static check.
- Passed: handoff validation.
- Passed: whitespace diff check.

## Evidence

- Focused bootstrap test proves dry-run does not write, execute creates issuer/security/profile, identifiers are persisted and rerun is idempotent.
- Unknown-symbol no-fallback test proves `company-database/build` and coverage audit return zero targets instead of falling back to all companies.
- UI static check proves the modified workbench script still satisfies the static contract.

## Decisions

- Bootstrap creates only local stubs; it does not download external data or run research.
- Bootstrap returns a material inbox manifest template so the next source of facts is official/IR/public company material, not research reports.
- Unknown symbol guidance now points to bootstrap first because company database creation should precede research workflow feedback.
- The UI starts with dry-run preview only; execute can be added after the user-facing form and confirmation are clearer.

## Risks and Open Questions

- Market/exchange/currency inference is intentionally simple and should be overridden by explicit payload fields for edge cases.
- The UI has no dedicated bootstrap form yet; it uses the current company symbol input.
- Watchlist/CSV bootstrap remains future work.

## Artifacts

- None. This task changes code/docs/tests only.

## Handoff Checklist

- [x] Code changes completed.
- [x] API docs updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [x] Focused tests and UI static check completed.
- [x] Handoff validation and diff check completed.

## Next Steps

1. Commit and push T-472.
2. Continue with material inbox real end-to-end acceptance or sample company package.
3. Add a dedicated bootstrap form if analysts need exchange/currency/company-name overrides from the UI.

## Next Recommended Action

Commit and push T-472.
