# Handoff: T-450 Company Intelligence Empty-State Guidance

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-450

## Objective

Make the company intelligence workbench visibly actionable when a symbol has no local company database record or has sparse data. Unknown or incomplete companies should show the reason, missing layers and next steps instead of empty tables plus raw JSON.

## Scope

- In scope: static UI layout, JavaScript rendering/actions, UI static contract, browser interaction acceptance, roadmap and handoff updates.
- Out of scope: new backend endpoints, external crawling, data import execution, real broker integration and live trading.

## Background

The Product/UI explorer found that `/api/company-intelligence/{symbol}` already returns `status=not_found`, `data_quality.missing_sections` and `next_actions`, but the UI was not making these fields visible enough. This made the platform look like it was not running when the real issue was that a symbol had not been locally built or had missing data layers.

## Problem Statement

Users need to know whether a blank company page means the service failed, the symbol is unknown, or a specific company database layer is missing. The workbench also needs a direct action from that diagnosis so users can begin building the local company database.

## Expected Deliverables

- Add a visible gap diagnosis panel to the company intelligence overview.
- Render missing sections and next actions from the existing company intelligence response.
- Wire next-action buttons to existing local workbench flows.
- Avoid stale issuer scope when the user changes the company intelligence symbol.
- Add static and browser acceptance checks.

## Current State

- Completed: company intelligence overview now shows diagnosis status, missing count and next action count.
- Completed: missing sections render with impact and suggested action.
- Completed: next actions render with buttons for single-name research, research structure preview and coverage audit.
- Completed: batch/audit payload helpers now only use the issuer resolved by the current company intelligence result.
- Completed: UI static contract includes the new IDs and functions.
- Completed: browser acceptance and full local validation.
- Blocked: none.

## Current Findings

- The backend already has enough state for useful empty-state guidance; no API change is needed.
- Existing UI is a dense workbench, so the fix stays as compact system boxes and tables instead of a decorative empty-state illustration.
- Guidance actions must remain local research/paper-only operations and should not imply live trading.

## Proposed Work Plan

1. Surface the backend's diagnosis fields directly in the existing company intelligence panel.
2. Keep actions small and use existing functions instead of adding new routes.
3. Lock the unknown-symbol behavior with browser acceptance.

## Validation Plan

- Run `python3 scripts/ui_static_check.py`.
- Compile changed UI scripts.
- Run browser interaction acceptance.
- Run full `make local-ci` before closeout if feasible.

## Files Touched

- `app/static/index.html`: added diagnosis UI, rendering helpers, current-symbol issuer scoping and guidance actions.
- `scripts/ui_static_check.py`: added required IDs and functions.
- `scripts/ui_interaction_acceptance.py`: added unknown ticker empty-state guidance check.
- `tasks/todo.md`: added T-450 roadmap entry.
- `docs/README.md`: updated task range through T-450.
- `docs/agent-handoffs/README.md`: added T-450 to related tasks.
- `docs/agent-handoffs/2026-06-24-T-450-company-intelligence-empty-state-guidance.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
docker compose restart ai-quant-org
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --timeout 60
make local-ci
```

Result:

- Passed: UI static check and Node syntax check.
- Passed: Python compile for UI check scripts.
- Passed: browser interaction acceptance with 13/13 checks, including `company_intelligence_empty_state_guidance`.
- Passed: full `make local-ci`, including compile, 224 tests, UI static check, security check and handoff validation.

## Decisions

- Reused the existing `next_actions` contract rather than adding a new API.
- Unknown or changed ticker input uses the ticker scope instead of stale `activeEntityIssuerId`.
- Empty-state actions call existing local workbench functions and preserve no-broker/no-live-trading boundaries.

## Dependencies

- Existing `GET /api/company-intelligence/{symbol}` response fields: `status`, `data_quality.missing_sections` and `next_actions`.
- Existing UI functions: `runSecSingleName`, `structureCompanyReports`, `auditCompanyCoverage` and `buildCompanyDatabaseBatch`.
- Existing browser acceptance harness.

## Blockers

- None for this slice.

## Risks and Open Questions

- The next-action labels are backend driven; future backend action types need a UI mapping.
- Coverage and batch-build results still rely on a raw JSON box; a richer run summary remains pending.
- Running single-name research from a guidance action can take longer than simple preview paths.

## Artifacts

- None produced.

## Handoff Checklist

- [x] Gap diagnosis panel added.
- [x] Missing sections and next actions rendered.
- [x] Guidance buttons wired.
- [x] Static UI contract updated.
- [x] Browser acceptance check added.
- [x] Browser/full validation completed.

## Evidence

Commands run:

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
docker compose restart ai-quant-org
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --timeout 60
make local-ci
```

Result:

- Passed: UI static check and script compile.
- Passed: browser interaction acceptance with 13 checks and 0 failures.
- Passed: full local CI with 224 unit tests.

## Next Steps

1. Continue with richer operation summaries for coverage audit, batch build and report realization.
2. Add persistent run history and resumability for company database batch builds.
3. Add UI event filters for structured disclosure event types.

## Next Recommended Action

Continue with company database batch run history and richer operation summaries so long-running补库 work can be audited from the workbench.
