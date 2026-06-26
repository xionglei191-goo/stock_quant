# Handoff: T-470 Company Intelligence Cycle Runner

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence, Product and UI, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-470

## Status

- Status: DONE
- Owner group: Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Add an audited local-only company intelligence cycle runner that refreshes the analysis feedback loop for one company after local data, events, relationships or research report viewpoints change.

## Background

The platform already has separate capabilities for research report realization, company workflow build and paper-only simulation feedback performance updates. The missing gap was a company-level entry point that runs those steps in sequence and reports before/after completeness back to the company intelligence workbench.

## Problem Statement

After company materials, events, relationships or research report viewpoints change, analysts need a single local refresh action that rebuilds the downstream observation, conclusion and paper feedback loop. Without that runner, the workbench can show stale feedback even when underlying company database sections have improved.

## Expected Deliverables

- A default-dry-run API route for one-company cycle refresh.
- Service orchestration over report realization, workflow build and simulation feedback performance.
- Workbench controls for preview and execute.
- API contract and focused regression coverage.
- Roadmap and handoff updates.

## Scope

- In scope: API route, service runner, API contract, UI buttons/status fields, focused unit and UI acceptance coverage.
- Out of scope: external data download, broker integration, live trading, changing research report fact boundaries, or replacing the individual sub-step APIs.

## Current Findings

- Research report realization already computes forecast/viewpoint outcome fields.
- Company workflow build already creates or refreshes observations, conclusions and watch-only feedback.
- Simulation feedback performance update already uses local market data and remains paper-only.
- The workbench already has a company-scoped payload helper that can be reused for cycle preview/execute.

## Proposed Work Plan

1. Add the API route under `/api/company-intelligence/{symbol}/cycle/run`.
2. Add a service runner that resolves local issuer IDs and calls the three existing sub-steps.
3. Return compact before/after completeness and coverage deltas.
4. Add workbench preview/execute controls and status fields.
5. Update API docs, tests, UI checks, roadmap and handoff.

## Validation Plan

- Compile touched Python files.
- Run focused unit coverage for unknown symbol, dry-run and execute.
- Run UI static contract checks.
- Run UI interaction acceptance for workbench preview.
- Run handoff validation and whitespace diff check.

## Current State

- Completed: `POST /api/company-intelligence/{symbol}/cycle/run` is registered.
- Completed: `SystemService.run_company_intelligence_cycle` resolves symbol to local issuer IDs and defaults to dry-run.
- Completed: the runner calls report realization, workflow build and paper feedback performance updates only against local records.
- Completed: unknown symbols return `status=not_found` and preserve company intelligence `next_actions`.
- Completed: company intelligence workbench exposes preview/execute buttons and compact cycle metrics.
- Completed: API contracts, unit tests, UI static checks and interaction acceptance cover the runner.

## Dependencies

- Existing research report realization service.
- Existing company workflow build service.
- Existing paper-only simulation feedback performance updater.
- Existing company intelligence symbol-to-issuer resolution.

## Blockers

- None.

## Files Touched

- `app/api.py`: added the company intelligence cycle route.
- `app/services.py`: added `run_company_intelligence_cycle`.
- `app/static/index.html`: added cycle preview/execute controls, rendering and API wiring.
- `docs/api-contracts.md`: documented request, response, execution order and boundaries.
- `scripts/ui_static_check.py`: added required DOM IDs and JS functions.
- `scripts/ui_interaction_acceptance.py`: added browser acceptance for cycle preview.
- `tests/test_system.py`: added dry-run, execute and unknown-symbol coverage.
- `tasks/todo.md`: added DONE T-470 roadmap entry.
- `docs/agent-handoffs/2026-06-26-T-470-company-intelligence-cycle-runner.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/api.py app/services.py tests/test_system.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_cycle_runs_local_workflow_feedback_loop
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile on touched Python files.
- Passed: focused company intelligence cycle unit test.
- Passed: UI static check.
- Passed: UI interaction acceptance.
- Passed: handoff validation.
- Passed: whitespace diff check.

## Evidence

- Unit test proves unknown symbol returns `not_found`, dry-run does not write local workflow objects, and execute creates observation/conclusion/feedback records.
- UI static contract proves new buttons, status fields and functions are present.
- UI interaction acceptance proves workbench preview renders `company-intelligence-cycle-v1`.

## Decisions

- Default mode is dry-run; writes require `execute=true`.
- The runner does not fetch external materials. It only refreshes derived local records from existing company database state.
- Research reports remain opinion and attention signals. They are not promoted to fact sources by this runner.
- Simulation feedback remains paper-only and explicitly declares no broker execution.

## Risks and Open Questions

- The runner currently orchestrates existing local sub-steps but does not schedule or poll long-running external ingestion.
- Interaction acceptance validates preview; execute behavior is covered by the focused backend unit test.
- Future work should add a compact run history for cycle executions if analysts need audit comparison across dates.

## Artifacts

- None. This task does not add persistent runtime artifacts.

## Handoff Checklist

- [x] API route added.
- [x] Service runner added.
- [x] Workbench controls added.
- [x] API contract updated.
- [x] Focused backend test added.
- [x] UI static and interaction acceptance updated.
- [x] Roadmap updated.

## Next Steps

1. Add cycle execution history if repeated company refreshes need date-over-date comparison.
2. Add UI guidance for companies whose symbol cannot be resolved to a local issuer.
3. Expand the runner only after new local ingestion sources have stable company mapping quality.

## Next Recommended Action

Add cycle execution history if repeated company refreshes need date-over-date comparison.
