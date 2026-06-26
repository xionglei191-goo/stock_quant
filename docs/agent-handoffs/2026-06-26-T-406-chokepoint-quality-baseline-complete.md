# Handoff: T-406C Chokepoint Quality Baseline Complete

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-406C

## Status

- Status: DONE
- Owner group: Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Complete the local-only chokepoint research quality baseline by moving the manual review package from seed-only rows to a versioned, repeatable human review input for the five bundled real-topic samples.

## Background

T-406C already had a repeatable quality package script and a narrow manual-review import contract. The remaining gap was that the repo did not contain a completed baseline review input that could close all bundled samples without inventing T-406D/T-406E schema.

## Problem Statement

The quality package could be rerun, but manual review metrics stayed at zero unless a caller supplied external rows. Another agent could not reproduce a completed T-406C baseline from repo state alone.

## Expected Deliverables

- Versioned local-only manual review input covering all five bundled samples.
- Script support for the four required label classes: `confirmed`, `inferred`, `speculative`, `unknown`.
- Completed manual review readiness metric.
- Tests and docs for the bundled baseline command.
- Roadmap and handoff updates.

## Scope

- In scope: local quality package script, versioned review input, tests, chokepoint docs, roadmap and handoff.
- Out of scope: T-406D structured conclusion schema, T-406E verification task writeback, production-grade external evidence.

## Current Findings

- The existing `manual_review_input` contract was sufficient; no new run schema was needed.
- `artifacts/` is ignored, so the durable input belongs under `docs/examples/`; generated package output remains local-only.
- The default seed-only script behavior should remain available for smoke tests.

## Proposed Work Plan

1. Add a versioned manual review baseline input.
2. Extend accepted manual label states and summary counts.
3. Add CLI flag for bundled baseline use.
4. Add focused regression.
5. Update docs and roadmap.
6. Run focused and default validation.

## Validation Plan

- Run focused bundled baseline test.
- Run quality package CLI with bundled baseline.
- Run Python compile, full unittest suite, UI static, security and handoff checks.

## Current State

- Completed: `docs/examples/chokepoint-manual-review-baseline.jsonl` provides completed review rows for all five bundled samples.
- Completed: script accepts `confirmed`, `inferred`, `speculative`, `unknown`, `dismissed` and `pending_manual_review` label states.
- Completed: script reports `manual_review_ready_for_local_baseline` and `manual_review_summary.label_status_counts`.
- Completed: CLI supports `--use-bundled-manual-review-baseline`.
- Blocked: none.

## Dependencies

- T-406B chokepoint research run pipeline.
- Existing `scripts/local_chokepoint_quality_package.py` sample set and manual review contract.

## Blockers

- None.

## Files Touched

- `scripts/local_chokepoint_quality_package.py`: added bundled baseline option and completed review metrics.
- `docs/examples/chokepoint-manual-review-baseline.jsonl`: local-only review baseline input.
- `tests/test_system.py`: added regression for the bundled review baseline.
- `docs/chokepoint-research-module.md`: documented completed T-406C baseline and command.
- `tasks/todo.md`: marked T-406C done.
- `docs/README.md`: updated docs index.
- `docs/agent-handoffs/2026-06-26-T-406-chokepoint-quality-baseline-complete.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_bundled_manual_review_baseline_closes_samples tests.test_system.SystemServiceTests.test_company_profile_field_assertion_query_recommends_and_batch_rejects_conflicts
python3 scripts/local_chokepoint_quality_package.py --use-bundled-manual-review-baseline --output-dir /tmp/chokepoint-quality-package-baseline
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
```

Result:

- Passed: focused tests, 2 tests.
- Passed: bundled quality package CLI, `manual_review_ready_for_local_baseline=true`, 5/5 samples reviewed, 10/10 labels closed.
- Passed: UI static check.
- Passed: Python compile.
- Passed: full unittest suite, 250 tests.
- Passed: security check, 181 files checked, no findings.
- Passed: handoff validation.

## Evidence

- `/tmp/chokepoint-quality-package-baseline/quality-package.json`: local-only generated package from bundled baseline, not versioned.
- Key metrics: `manual_review_close_rate=1.0`, `manual_review_sample_coverage_rate=1.0`, `boundary_violation_rate=0.0`.
- `scripts/check_handoffs.py`: passed after template fix.

## Decisions

- Kept T-406C at sample-label review granularity and did not add T-406D/T-406E schema fields.
- Separate partial T-406D/T-406E work is now tracked in `docs/agent-handoffs/2026-06-26-T-406-chokepoint-structured-verification-partial.md`; this handoff remains the scope record for the T-406C quality package baseline only.
- Stored the baseline input under `docs/examples/` because `artifacts/` is ignored and generated outputs remain local-only.
- Kept default script behavior as seed-only unless explicit manual review input or the bundled baseline flag is provided.

## Risks and Open Questions

- The baseline is a local review fixture, not production-grade external evidence.
- The next quality jump belongs to T-406D structured conclusion schema and T-406E verification task feedback.

## Artifacts

- `docs/examples/chokepoint-manual-review-baseline.jsonl`: versioned local-only input; no secrets; not acceptable for non-local production release gates.
- `/tmp/chokepoint-quality-package-baseline`: generated local-only output directory; not versioned and not production evidence.

## Handoff Checklist

- [x] Versioned manual review baseline added.
- [x] Script metrics and CLI flag added.
- [x] Focused regression added.
- [x] Roadmap/docs updated.
- [x] Validation run.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. Use T-406D to add machine-readable conclusion sections and evidence-backed scorecards.
2. Use T-406E to make verification task closures refresh run conclusions and confidence.

## Next Recommended Action

Start T-406D with a narrow structured conclusion schema that consumes the completed T-406C baseline but does not rewrite the quality package contract.
