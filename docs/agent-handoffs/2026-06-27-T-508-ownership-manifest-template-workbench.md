# Handoff: T-508 Ownership Manifest Template Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-508

## Objective

Add a browser and API path for generating editable local ownership manifest templates from ownership table directories.

## Scope

- In scope: ownership manifest template API, company intelligence maintenance UI, focused regression, API docs, roadmap status.
- Out of scope: external data fetching, browser file upload, automatic relationship approval, database migration, real broker integration, automatic trading.

## Background

T-504 introduced a CLI manifest template path, and T-507 added browser ownership table import. The remaining gap was generating the manifest template from the browser without manually running the CLI.

## Problem Statement

Before T-508, users could import explicit ownership files in the workbench, but directory scanning and manifest template generation still required a shell command.

## Expected Deliverables

- Add `POST /api/company-database/ownership/manifest-template`.
- Keep dry-run as default; write local JSON only with `execute=true` and `output_path`.
- Reuse domain logic for glob discovery and symbol inference.
- Add company intelligence UI controls for glob, output path, preview, and write.
- Static UI contract and focused regression cover the new path.

## Current Findings

- Completed: `app/service_modules/company_intelligence.py` owns ownership file discovery, symbol inference, and template building.
- Completed: `SystemService.company_ownership_manifest_template` is a facade for validation, optional local write, and audit.
- Completed: API route and handler are registered.
- Completed: Workbench renders manifest template rows and advanced trace.
- Completed: Tests cover dry-run and execute write.

## Proposed Work Plan

1. Move CLI-equivalent template logic into the company intelligence domain module.
2. Add a narrow `SystemService` facade that does no relationship creation.
3. Add API route and regression for preview/write behavior.
4. Add UI controls next to the ownership import workbench.
5. Update docs, roadmap, and handoff.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_ownership_manifest_template_api_previews_and_writes tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Browser interaction acceptance is deferred; this slice is covered by API regression and static UI contract.

## Risks

- The API scans server-local paths; it is a local-first workstation workflow, not a remote file upload feature.
- Generated manifest entries still need user review before executing ownership import.

## Dependencies

- Existing ownership table import path from T-507.
- Existing relationship builder ownership-file support from T-504.
- `scripts/ui_static_check.py` static contract.

## Blockers

- No blocker for this delivered slice.
- Direct manifest-to-import UI flow remains future work.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: Minimal facade logic only. File discovery and template construction live in `app/service_modules/company_intelligence.py`.
- Domain module used: Yes.
- `SystemService` changes: validation, optional local JSON write, audit, and response envelope for `company_ownership_manifest_template`.
- Focused regression: `tests.test_system.SystemServiceTests.test_company_ownership_manifest_template_api_previews_and_writes`.
- API schema changed: additive route `/api/company-database/ownership/manifest-template`.
- Storage schema changed: No.
- UI behavior changed: company intelligence maintenance area can preview/write ownership manifest templates.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_ownership_manifest_template_api_previews_and_writes tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
git diff --check
```

Results:

- Passed: pending final verification in this turn.
- Failed: none known.
- Artifact boundary: no committed artifact files; execute test writes to a temporary directory only.

Files touched:

- `app/service_modules/company_intelligence.py`: ownership manifest discovery/template helpers.
- `app/services.py`: `company_ownership_manifest_template` facade.
- `app/api.py`: API handler.
- `app/api_routes.py`: API route.
- `app/static/index.html`: ownership manifest workbench controls and renderer.
- `scripts/ui_static_check.py`: required IDs/functions.
- `tests/test_system.py`: focused API regression.
- `docs/api-contracts.md`: route contract.
- `tasks/todo.md`: T-508 roadmap record.

## Next Recommended Action

Wire generated manifest output directly into the ownership import preview flow and add browser interaction acceptance for the full manifest-to-import path.
