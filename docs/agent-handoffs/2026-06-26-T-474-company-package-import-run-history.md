# Handoff: T-474 Company Package Import Run History

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-474

## Objective

Persist local watchlist / company package import runs so company database intake can be audited after the immediate API response is gone.

## Scope

- In scope: package import run model/store registration, service persistence, run history query API, focused tests, API docs, roadmap update.
- Out of scope: UI history controls, retry/resume for package imports, external company package download, real trading.

## Background

T-473 added local watchlist / company package import, but import results only lived in the immediate API response and audit log. Long-term local research use needs a durable record of each package import run, including invalid rows, duplicate rows, created/existing issuers, and enough row-level detail for failure review.

## Problem Statement

Without a persisted import run history, analysts cannot reliably answer which watchlist package was imported, whether it was dry-run or executed, which companies were created, which rows failed, or what should feed the next material inbox step.

## Expected Deliverables

- Dedicated `CompanyPackageImportRun` model and store collection.
- Package import service writes run history for execute imports by default.
- Dry-run imports write run history only when `record_run=true`.
- Query API supports run, issuer, symbol, status, limit, and optional slim item details.
- API docs, roadmap and handoff updated.
- Focused tests for execute recording, dry-run recording, filtering, slim item behavior, and no build-run pollution.

## Current Findings

- `import_company_watchlist` already produces full per-company results, including coverage and material inbox templates.
- `CompanyDatabaseBuildRun` has batch/retry/resume semantics that should not be reused for package import history.
- The store collection mechanism can persist a new dataclass by registering it in `COLLECTIONS`, dirty resource mapping, datetime fields, and `InMemoryStore`.

## Proposed Work Plan

1. Add `CompanyPackageImportRun` and register it in the store.
2. Wire `import_company_watchlist` to create run history with slim row items.
3. Add `company_package_import_runs_payload` and API routes.
4. Add focused unit tests.
5. Update docs, roadmap and handoff.
6. Run compile, focused tests, handoff validation and diff checks.

## Validation Plan

- Compile app, tests and scripts.
- Run focused package import run history tests.
- Run handoff validation because this task adds a handoff.
- Run whitespace diff check.
- Skip UI static check because this task does not change UI.

## Current State

- Completed: `CompanyPackageImportRun` persists in `company_package_import_runs`.
- Completed: `POST /api/company-database/package/import` records runs by default for `execute=true`; dry-run records only with `record_run=true`.
- Completed: `GET|POST /api/company-database/package/import/runs` and watchlist alias query run history.
- Completed: default history listing omits row items; `include_items=true` returns slim row details.
- Not started: UI table for viewing import run history.
- Blocked: None.

## Risks

- UI does not yet expose import run history; users must query the API directly.
- `root_path` is local machine metadata and should not be treated as non-local production evidence.
- Full retry/resume for package import is intentionally not implemented; repeated import should call the import endpoint again.

## Dependencies

- Existing `bootstrap_company_database`.
- Existing package/watchlist import parser from T-473.
- Existing store dataclass serialization and dirty resource tracking.
- Existing API router role/permission handling for company database endpoints.

## Blockers

- None.

## Files Touched

- `app/models.py`: added `CompanyPackageImportRun`.
- `app/store.py`: registered `company_package_import_runs`, resource dirty mapping, and datetime fields.
- `app/services.py`: records package import runs and exposes run history payloads.
- `app/api.py`: added package import run history routes and handler.
- `tests/test_system.py`: added focused route/service tests.
- `docs/api-contracts.md`: documented run recording semantics and query contract.
- `docs/README.md`: updated docs index to include T-474 and package import run history.
- `tasks/todo.md`: added `DONE` T-474.
- `docs/agent-handoffs/2026-06-26-T-474-company-package-import-run-history.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_database_package_import_bootstraps_watchlist_companies tests.test_system.SystemServiceTests.test_company_database_package_import_dry_run_history_is_explicit tests.test_system.SystemServiceTests.test_company_database_package_import_does_not_fallback_to_all_issuers
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile on app, tests and scripts.
- Passed: 3 focused package import tests.
- Passed: handoff validation after aligning this file to the strict `scripts/check_handoffs.py` headings.
- Passed: whitespace diff check.
- Not run: `python3 scripts/ui_static_check.py`; no UI files changed.

## Evidence

- Focused execute test proves package import records a run by default, stores slim items, filters by symbol/issuer/status, and does not pollute `company_database_build_runs`.
- Focused dry-run test proves `record_run=true` persists dry-run history without creating local issuers.
- Focused no-fallback test proves missing-symbol package rows do not fallback to all issuers.
- `python3 scripts/check_handoffs.py` and `git diff --check` passed.

## Decisions

- Keep `CompanyPackageImportRun` separate from `CompanyDatabaseBuildRun` because import history has no batch build retry/resume semantics.
- Persist only slim row items in run history to avoid storing full coverage, material inbox templates, and next actions for every row.
- Default execute imports to run recording; dry-run history requires `record_run=true` to avoid noisy previews.
- Add `/watchlist/import/runs` alias for API consistency with the import alias.

## Artifacts

- No generated artifact committed. Runtime records are local store state with boundary `company_package_import_run_is_local_watchlist_history_no_external_download_no_live_trading`.

## Handoff Checklist

- [x] Code changes completed.
- [x] API docs updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [x] Focused tests completed.
- [x] UI static check intentionally skipped because no UI changed.

## Next Steps

1. Add a UI import history panel if the workbench needs visible audit browsing.
2. Consider optional failed-row re-import helpers only after real usage shows repeated manual retry friction.
3. Keep package import runs out of non-local release evidence unless paths and local metadata are sanitized.

## Next Recommended Action

Commit and push T-474, then continue with a UI import history panel if analysts need to browse package import runs from the workbench.
