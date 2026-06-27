# Handoff: T-498 Modularization and Route Registry

## Metadata

- Status: DONE
- Owner group: Product and UI, Platform and Quality
- Reviewer groups: PM / Release Coordination, Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex with Product/UI worker
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-498

## Objective

Reduce long-term maintenance risk from `app/static/index.html` and `app/api.py` growth while preserving the current `/ui` route, DOM contract, API URLs, request methods, payloads, dispatch behavior, trace IDs, permission checks, and error envelopes.

## Scope

- In scope: API route registry extraction, frontend module scaffold, static contracts, focused tests, task status, and handoff.
- Out of scope: moving active UI runtime code out of `index.html`, changing static serving, changing API schemas, route renames, authorization policy changes, database migrations.

## Background

The UI file is roughly 9.6k lines and `app/api.py` had a large route table inside `_resolve`. T-498 is the first modularization step, so compatibility matters more than aggressive extraction.

## Problem Statement

The project needs a path to split dashboard/company/graph/market/admin/helpers UI code and API route groups without breaking the single-page local workbench or hundreds of existing API tests and scripts.

## Expected Deliverables

- `ApiRouter._resolve` delegates route registration to a separate route table module.
- A static frontend module scaffold exists for dashboard/company/graph/market/admin/helpers.
- Static checks enforce the scaffold and prevent accidental runtime loading before browser acceptance is ready.
- Focused regression proves core API URLs still resolve and `_resolve` no longer owns the giant inline list.

## Current Findings

- `app/server.py` currently serves `/ui` as `index.html` and does not expose a JS module import path contract. Loading modules at runtime would add unnecessary UI risk.
- `scripts/ui_static_check.py` is the right guard for the first frontend split because it already protects the DOM and helper contract.
- The route table can be moved mechanically because handlers are bound methods on `ApiRouter`.

## Proposed Work Plan

1. Extract the route list into `app/api_routes.py::build_route_table(owner)`.
2. Keep `ApiRouter._resolve` as the matching loop and keep dispatch/authorize/error handling in `app/api.py`.
3. Add inert `.mjs` scaffold files and manifest under `app/static/ui_modules/`.
4. Extend `scripts/ui_static_check.py` to verify manifest domains, `runtime_loaded=false`, and module syntax.
5. Add focused tests and run browser matrix.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 -m unittest tests.test_system.SystemServiceTests.test_api_route_table_is_registered_outside_router_resolve tests.test_system.SystemServiceTests.test_golden_api_behavior_baseline_for_backend_domain_refactor tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture tests.test_system.SystemServiceTests.test_ui_research_workbench_matrix_validator_requires_t495_scenarios_and_local_boundary`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- `python3 scripts/security_check.py .`
- `python3 scripts/ui_research_workbench_matrix.py http://127.0.0.1:<port> --output-dir artifacts/t498-ui-research-workbench-matrix --timeout 60`

## Risks

- Frontend modules are scaffold-only. Actual extraction still belongs to later, smaller slices with browser acceptance after each moved section.
- The route registry still contains a large list; it is outside `_resolve`, but not yet grouped by domain files.
- Because route handler names remain bound methods, any future handler rename still needs route registry updates.

## Dependencies

- T-495 browser matrix.
- T-501 golden API behavior baseline.
- Existing `/ui` static contract.
- Existing permission and dispatch behavior in `ApiRouter`.

## Blockers

- None for local T-498 completion.

## Handoff Checklist

- [x] API route table extracted from `_resolve`.
- [x] API behavior focused baseline passed.
- [x] UI module scaffold added.
- [x] Static check enforces scaffold and no runtime loading.
- [x] Browser matrix passed.
- [x] `tasks/todo.md` marked T-498 DONE.

## Evidence

- `app/api_routes.py`: `build_route_table(owner)` route registry.
- `app/api.py`: `_resolve` delegates to `build_route_table(self)`.
- `app/static/ui_modules/manifest.json`: scaffold split map, `runtime_loaded=false`.
- `scripts/ui_static_check.py`: validates scaffold and `.mjs` syntax.
- Focused regression result: four T-498/API/UI tests passed.
- `artifacts/t498-ui-research-workbench-matrix/ui-research-workbench-matrix.json`: local-only browser evidence; 8 required scenarios passed across desktop/mobile, 16 checks total, failure count 0, console error 0.

## Next Recommended Action

Proceed to T-499 non-local production readiness package. Keep any future UI extraction behind the T-495 browser matrix and any future route regrouping behind the T-501 golden API baseline.
