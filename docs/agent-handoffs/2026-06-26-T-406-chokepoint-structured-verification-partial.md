# Handoff: T-406D/E Chokepoint Structured Conclusion and Verification Partial

## Metadata

- Status: DOING
- Owner group: Research and AI Workflows
- Reviewer groups: Data and Evidence, Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-406D, T-406E

## Status

- Status: DOING
- Owner group: Research and AI Workflows
- Reviewer groups: Data and Evidence, Product and UI, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Move chokepoint research from a one-shot readable report toward a machine-readable research file with structured facts, inference layers, evidence gaps, verification task closure and review state. This handoff records partial T-406D/T-406E progress; it does not mark either task done.

## Background

T-406C closed the local quality package baseline. While reviewing that line, the implementation also added structured conclusion fields and verification task closure support that belongs to T-406D/T-406E, so the roadmap must now distinguish completed partial work from the still-open scorecard and replay requirements.

## Problem Statement

The previous roadmap still listed all T-406D/T-406E work as TODO even though the code already returned structured conclusion fields and the UI could close verification tasks. Without this handoff, future agents could either duplicate the work or incorrectly mark the tasks done.

## Expected Deliverables

- Structured conclusion payload that separates facts, inferences, speculation, unknowns, gaps, market context and verification tasks.
- UI controls for verification task closure and conclusion refresh.
- Focused backend and UI static coverage.
- Roadmap and API contract alignment that leaves scorecard and replay work open.

## Scope

- In scope: chokepoint `conclusion` structured fields, verification task status summary, UI closure controls, API contract documentation and focused regression coverage.
- Out of scope: 7-dimension evidence-backed chokepoint scorecard, strict core-fact eligibility gate, backend automatic run refresh on every task status update, simulation feedback/replay integration.

## Current Findings

- T-406D is partially implemented for machine-readable conclusion fields, but the 7-dimension scorecard and hard core-fact gate are still missing.
- T-406E is partially implemented through UI-driven task closure followed by run finalization, but direct API task updates do not yet auto-refresh owning chokepoint runs.
- `market_pricing_context` is available as validation context only and must remain separate from trading signals.

## Proposed Work Plan

1. Record the partial T-406D/T-406E implementation in roadmap, docs and handoff.
2. Preserve T-406D/T-406E as `TODO` until scorecard, fact gate and replay work are implemented, because project completion audits expect no lingering `DOING` roadmap items.
3. Next implement T-406D-1 evidence-backed scorecard and core-fact gate.

## Validation Plan

- Run focused chokepoint structured conclusion regression.
- Run UI static check and handoff validation.
- Before commit, run full unit tests and security check.

## Current State

- Completed: `conclusion` includes `core_facts`, `inferences`, `speculations`, `unknowns`, `evidence_gaps`, `market_pricing_context`, `falsification_status` and `next_verification_tasks`.
- Completed: verification tasks are summarized by status, open/closed counts and completion rate in the conclusion.
- Completed: UI displays verification tasks, closed count and falsification status, and can mark tasks `done` or `dismissed` before refinalizing the run.
- In progress: T-406D/T-406E keep `TODO` status in `tasks/todo.md`, with partial completed bullets recorded under each task.
- Not started: 7-dimension scorecard with evidence refs, confidence and gap per dimension.
- Not started: direct backend writeback from task status update into the owning chokepoint run without relying on UI refinalize.
- Blocked: none.

## Files Touched

- `app/services.py`: added structured conclusion fields, verification task status aggregation and falsification status derivation.
- `app/static/index.html`: added verification task table, closed task count, falsification status and task close actions in the chokepoint workbench.
- `scripts/ui_static_check.py`: added required IDs, JS function and interaction markers for the new UI controls.
- `scripts/ui_interaction_acceptance.py`: added synthetic browser check for the structured conclusion and verification panel.
- `tests/test_system.py`: added regression for structured conclusion refresh after verification task closure.
- `docs/api-contracts.md`: documented the expanded `conclusion` contract.
- `docs/chokepoint-research-module.md`: clarified T-406C quality package boundaries versus partial T-406D/T-406E work.
- `tasks/todo.md`: kept T-406D/T-406E as `TODO` and recorded completed partial work plus remaining gaps.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_bundled_manual_review_baseline_closes_samples tests.test_system.SystemServiceTests.test_company_profile_field_assertion_query_recommends_and_batch_rejects_conflicts tests.test_system.SystemServiceTests.test_chokepoint_structured_conclusion_reflects_verification_closure
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_profile_field_assertion_batch_approve_supersedes_old_values tests.test_system.SystemServiceTests.test_company_profile_field_assertion_query_recommends_and_batch_rejects_conflicts tests.test_system.SystemServiceTests.test_chokepoint_structured_conclusion_reflects_verification_closure tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_bundled_manual_review_baseline_closes_samples
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
python3 scripts/local_chokepoint_quality_package.py --use-bundled-manual-review-baseline --output-dir /tmp/chokepoint-quality-package-baseline
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8768 --output-dir artifacts/ui-interaction-acceptance-t465
```

Result:

- Passed: focused regressions, then focused regressions including batch approve, 4 tests.
- Passed: UI static check.
- Failed then fixed: handoff validation initially failed on this file name/template; final rerun passed.
- Passed: Python compile.
- Passed: full unittest suite, 250 tests.
- Passed: security check, 181 files checked, no findings.
- Passed: bundled chokepoint quality package CLI, `manual_review_ready_for_local_baseline=true`.
- Passed: browser interaction acceptance on current-code temporary service, 20/20 checks.

## Dependencies

- Existing chokepoint run/finalize workflow.
- Existing `ResearchTask` status endpoint.
- T-406C local quality package baseline.

## Blockers

- None.

## Evidence

- Focused regression covers structured conclusion refresh after verification task closure.
- UI static check covers the new verification task table, closure action marker and status fields.
- Browser interaction acceptance covers the synthetic structured conclusion and verification panel.
- Handoff validation passed after the template and filename fix.

## Decisions

- Keep T-406D/T-406E as `TODO` because scorecard, hard source gate and simulation feedback/replay integration remain incomplete.
- Treat UI-driven task closure plus refinalize as a partial T-406E bridge, not the final backend writeback contract.
- Keep market data in `market_pricing_context` as validation-only context, not a trading signal.

## Risks and Open Questions

- `core_facts` still needs a stricter eligibility gate for URL, source type, published date and primary-source status.
- `thesis_strength_score` still uses an aggregate count model; it should be derived from a transparent scorecard.
- API callers must still call chokepoint `finalize` after direct `ResearchTask` status updates to refresh the run conclusion.

## Artifacts

- No new versioned runtime artifacts. Browser and quality package outputs remain local-only when generated.

## Handoff Checklist

- [x] Partial T-406D/T-406E state documented.
- [x] Roadmap retains `TODO` status with partial progress bullets.
- [x] API contract updated for structured conclusion fields.
- [x] Focused tests and UI static check run.
- [x] Full unittest/security/browser acceptance run before final commit.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Implement T-406D-1: 7-dimension evidence-backed chokepoint scorecard and strict core-fact gate.
2. Implement T-406E-1: backend verification result writeback contract that refreshes related run conclusions when tasks close.
3. Connect chokepoint run review snapshots to company intelligence analysis conclusions and paper-only simulation feedback.

## Next Recommended Action

Start T-406D-1 by adding a scorecard helper and core-fact eligibility gate in `app/services.py`, then add tests proving each score dimension has evidence refs and missing-source facts are excluded from `core_facts`.
