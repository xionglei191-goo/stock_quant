# Handoff: T-477 Company Intelligence Completion

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Reviewer groups: Platform and Quality, Data and Evidence, Product and UI, Research and AI Workflows
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related tasks: T-477, T-478, T-479, T-406D, T-406E

## Objective

Close the PM follow-up gaps after T-476: persist company intelligence cycle runs, reduce manual material manifest URL entry, expose a pending material queue, and finish remaining chokepoint research quality gaps.

## Scope

- In scope: backend models/store/API/service, workbench UI, focused tests, UI static contract, API/data docs, roadmap and handoff.
- Out of scope: external website downloads, broker integration, live trading, model training, production release evidence URI collection.

## Background

T-476 bridged package import runs to material inbox sidecar generation, but the overall user flow still had three gaps: cycle refresh results were not durable, generated manifests used example URLs unless the user filled templates manually, and imported companies lacked a visible material-preparation queue. T-406D/T-406E also still listed scorecard/source-gate/replay-feedback work as TODO.

## Problem Statement

Analysts needed fewer manual steps between importing a company package, preparing official/IR materials, refreshing company intelligence, and reviewing whether research conclusions improved. The roadmap also needed to reflect that chokepoint conclusions now have structured scoring, source gates and feedback summaries.

## Expected Deliverables

- Persisted company intelligence cycle run history with query API and workbench table.
- Material manifest export that uses known local IR/official URLs when available.
- Material inbox pending queue API and workbench table.
- Chokepoint conclusion `source_gate`, 7-dimension `chokepoint_scorecard`, and `review_feedback`.
- Focused regressions and docs/roadmap updates.

## Current Findings

- `CompanyPackageImportRun.items` already contains issuer/security/symbol data needed to derive material queues.
- `Issuer.company_details` already stores `ir_url` and `website_url` from prior profile field extraction work.
- The company intelligence cycle runner already returns before/after completeness and step summaries, so persisting a slim history record is enough.
- Chokepoint `finalize` already builds structured conclusions and can be extended without changing the run pipeline.

## Proposed Work Plan

1. Add `CompanyIntelligenceCycleRun` and register it in all stores.
2. Record execute cycle runs by default and add history query API/UI.
3. Add official URL selection for material manifest export.
4. Add material inbox pending queue API/UI.
5. Add chokepoint source gate, scorecard and review feedback summary.
6. Update tests, UI static contract, API/data docs, roadmap and handoff.

## Validation Plan

- Compile app/tests/scripts.
- Run focused regressions for cycle history, material manifest/pending queue, and chokepoint structured conclusion.
- Run UI static contract.
- Run handoff validation and whitespace diff check.
- Run browser interaction acceptance if local service is available.

## Current State

- Completed: `CompanyIntelligenceCycleRun` model, store registration, recording and query route.
- Completed: workbench cycle history controls and table.
- Completed: manifest export prefers local IR/website/source provenance.
- Completed: pending material queue route and workbench table.
- Completed: chokepoint source gate, 7-dimension scorecard and paper-only feedback summary.
- Blocked: None.

## Dependencies

- T-470 company intelligence cycle runner.
- T-474/T-475 package import run history.
- T-476 material manifest export.
- Existing chokepoint structured conclusion/finalize path.

## Blockers

- None.

## Files Touched

- `app/models.py`: added `CompanyIntelligenceCycleRun`.
- `app/store.py`: registered `company_intelligence_cycle_runs`.
- `app/api.py`: added cycle run history and material pending routes.
- `app/services.py`: added cycle history persistence/query, material pending queue, source URI selection, chokepoint scorecard/source gate/review feedback.
- `app/static/index.html`: added workbench controls and tables for cycle history and pending materials.
- `tests/test_system.py`: added focused regressions.
- `scripts/ui_static_check.py`: added new UI contract IDs/functions.
- `docs/api-contracts.md`: documented new/changed endpoints.
- `docs/data-structure-design.md`: documented `CompanyIntelligenceCycleRun`.
- `docs/README.md`: updated task range summary to T-479.
- `docs/chokepoint-research-module.md`: updated T-406D/T-406E completion note.
- `tasks/todo.md`: added T-477/T-478/T-479 DONE and marked T-406D/T-406E DONE.

## Commands Run

```bash
python3 -m py_compile app/models.py app/store.py app/api.py app/services.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_cycle_runs_local_workflow_feedback_loop tests.test_system.SystemServiceTests.test_company_package_import_run_exports_material_manifest_templates tests.test_system.SystemServiceTests.test_chokepoint_structured_conclusion_reflects_verification_closure
python3 scripts/ui_static_check.py
```

Result:

- Passed: Python compile.
- Passed: focused backend regressions.
- Passed: UI static contract.
- Failed: first handoff validation failed due filename/template; fixed in this handoff.

## Evidence

- Focused cycle test proves execute runs are recorded and queryable by symbol.
- Focused manifest test proves IR URL auto-fill, manifest write, pending missing-material state and ready-to-ingest state.
- Focused chokepoint test proves `source_gate`, 7-dimension scorecard and review feedback are present.
- UI static check proves new controls/functions are present.

## Decisions

- Cycle history records execute runs by default; dry-run history requires explicit `record_run=true`.
- Pending material queue is derived from package import history and local file existence; no separate queue object yet.
- Chokepoint scorecard is rule-derived and evidence-backed for human review, not an investment signal.

## Risks and Open Questions

- Pending material queue assumes default manifest/material naming unless users generated sidecars through the workbench.
- Chokepoint scorecard quality depends on available fact evidence and run text; low-evidence runs should remain `needs_evidence`.
- Browser acceptance still needs a final run after all docs/handoff edits.

## Artifacts

- No new persistent runtime artifacts are required. Browser acceptance output, if generated, is local-only and not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests updated.
- [x] UI static contract updated.
- [x] API/data docs updated.
- [x] `tasks/todo.md` updated.
- [x] Handoff created.
- [ ] Final validation after handoff format fix.

## Next Steps

1. Run final verification: focused tests, UI static, handoff check and diff check.
2. Run browser interaction acceptance if local service is available.
3. Commit and push when the worktree is ready.

## Next Recommended Action

Run final verification commands and then commit this task group.
