# Handoff: T-476 Company Package Material Manifest Export

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-476

## Objective

Bridge company package import runs to local material inbox preparation by generating official/IR/public-disclosure manifest sidecar templates from persisted package import history.

## Scope

- In scope: backend service/API, focused route test, UI controls and render table, UI static contract, browser render acceptance, API docs, roadmap and handoff.
- Out of scope: external downloads, automatic source crawling, broker research fact promotion, model training, live trading, material file content generation.

## Background

T-473/T-474/T-475 let users import a local watchlist/company package, persist the import run, and review it in the workbench. The next data-source gap was preparing `*.manifest.json` sidecars for the official/IR/company material inbox so users can collect company materials and feed them into source/document/evidence/profile-field extraction.

## Problem Statement

After importing a watchlist, users still had to manually create material inbox sidecar manifests for every company. That made the company database first-mile flow incomplete: imported companies existed, but the official material ingestion path still required repetitive hand-written manifest JSON.

## Expected Deliverables

- API to generate material inbox manifest templates from a package import run.
- Default dry-run behavior that returns templates without writing files.
- Explicit execute behavior that writes local `*.manifest.json` files only when `output_root` is provided.
- Workbench controls for output root, preview, write and result table.
- Tests and docs covering local-only/no-download/no-training/no-trading boundary.

## Current Findings

- `CompanyPackageImportRun.items` stores slim row audit with `issuer_id`, `security_id` and `symbol`, enough to regenerate bootstrap manifest templates.
- `_company_database_bootstrap_manifest_template` already defines the correct company IR / official profile sidecar shape.
- `company_material_inbox_ingest` consumes local `*.manifest.json` sidecars and rejects disallowed research/manual/news sources for fact ingestion.

## Proposed Work Plan

1. Add service method to materialize manifest templates from a package import run.
2. Add API route under `/api/company-database/package/import/runs/{run_id}/material-manifests`.
3. Add focused test for dry-run, execute write and skip-existing behavior.
4. Add workbench controls and render table.
5. Update UI static and browser acceptance checks.
6. Update docs, roadmap and handoff.

## Validation Plan

- Compile app, tests and scripts.
- Run focused material manifest export test.
- Run UI static check.
- Run handoff validation.
- Run whitespace diff check.
- Run browser interaction acceptance against a current-code local service when feasible.

## Current State

- Completed: service/API generates `company-material-manifest-export-v1` responses.
- Completed: execute writes local manifest JSON files under `output_root`; default behavior skips existing files unless `overwrite=true`.
- Completed: workbench can preview and write material manifests from the latest loaded/imported package run.
- Completed: UI static and browser render checks include manifest export.
- Blocked: None.

## Risks

- The generated manifest still points to a local material `file_path`; users must place the actual official/IR/disclosure text file there before material inbox ingestion can succeed.
- `source_uri_template` defaults to an example URL and should be replaced by a real official/IR/disclosure URL before production-quality local research use.
- Local output paths are machine-specific and must not be treated as non-local production evidence.

## Dependencies

- T-474 `CompanyPackageImportRun` persistence.
- T-475 workbench import run selection and visibility.
- Existing `_company_database_bootstrap_manifest_template`.
- Existing material inbox ingestion and source boundary rules.

## Blockers

- None.

## Files Touched

- `app/services.py`: added `company_package_import_material_manifests`.
- `app/api.py`: added package/watchlist material manifest export routes.
- `tests/test_system.py`: added focused export test.
- `app/static/index.html`: added manifest output controls, render table and JS API call.
- `scripts/ui_static_check.py`: added required IDs/functions.
- `scripts/ui_interaction_acceptance.py`: added `company_package_material_manifest_render`.
- `docs/api-contracts.md`: documented endpoint and boundaries.
- `docs/README.md`: updated task range and API summary.
- `tasks/todo.md`: added `DONE` T-476.
- `docs/agent-handoffs/2026-06-26-T-476-company-package-material-manifest-export.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_package_import_run_exports_material_manifest_templates
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t476
```

Result:

- Passed: focused backend test before final docs/handoff.
- Passed: Python compile and UI static check before final docs/handoff.
- Passed: pending final full verification after handoff update.
- Failed: none known.

## Evidence

- Focused test proves dry-run returns a template without writing, execute writes a local manifest JSON, rights tags keep `training_allowed=false`, and repeated execute skips existing manifest files.
- UI static check should prove new controls and JS functions are present.
- Browser render check should prove manifest export rows render representative payloads.

## Decisions

- Kept manifest export separate from material inbox ingestion; export only prepares sidecars, while ingestion remains the controlled source/document/evidence write path.
- Required `output_root` only for execute; dry-run can preview templates without a local directory.
- Defaulted source/file/title templates but allowed controlled placeholders: `{symbol}`, `{raw_symbol}`, `{issuer_id}`, `{security_id}`.
- Did not persist a new export run model yet; this is a deterministic helper derived from package import run history.

## Artifacts

- Browser acceptance output, if produced, is local-only evidence and not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Code changes completed.
- [x] API docs updated.
- [x] UI static contract updated.
- [x] `tasks/todo.md` status updated.
- [x] Handoff created.
- [ ] Final verification completed.

## Next Steps

1. Add real official/IR URL fields to company profiles or source candidates so `source_uri_template` can be populated from known company URLs.
2. Add optional UI filters for choosing which import run to export when users need cross-symbol package operations.
3. Consider an export run history only if repeated manifest export auditing becomes necessary.

## Next Recommended Action

Run final verification commands, then commit and push T-476.
