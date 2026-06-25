# Handoff: T-462 Company Intelligence Completeness Verdict

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI, Data and Evidence, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-462

## Status

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI, Data and Evidence, PM / Release Coordination
- Last updated: 2026-06-25
- Last agent: Codex
- Branch/worktree: local workspace, main

## Objective

Expose a clear company intelligence completeness verdict so users can tell whether a company database is unbuilt, partially usable, ready for analysis, or ready for paper-only feedback review.

## Background

T-456 through T-461 added deep profile coverage, official/IR field extraction, field-level assertions and a local material inbox. The company intelligence endpoint still exposed raw sections and counts, but it did not answer the user's direct question: whether the company database is complete enough to analyze.

## Problem Statement

Users saw empty tables or partial JSON without a single readiness judgment. That made it hard to distinguish an unbuilt company, a fact-layer gap, an opinion-layer gap and a feedback-layer gap.

## Expected Deliverables

- Add a `completeness_verdict` object to company intelligence responses.
- Distinguish blocking fact-layer gaps from non-blocking viewpoint/feedback gaps.
- Keep research reports as opinion and attention records, not fact sources.
- Keep simulation feedback paper-only.
- Cover the verdict with focused service tests and a handoff.

## Scope

- In scope: `SystemService.company_intelligence`, focused tests, roadmap entry and handoff.
- Out of scope: UI rendering, external crawling, real broker integration, live trading, new storage collections and scoring model calibration from large samples.

## Current Findings

- Existing `section_counts` and `data_quality` already exposed most ingredients for a verdict.
- Existing company database coverage and profile deep-field coverage helpers can be reused for score context.
- SPCX single-name research creates relationship coverage, but not an event timeline, so the expected blocking gap is `events`.
- DEMO first-class object coverage can still be incomplete if market data is absent.

## Proposed Work Plan

1. Add verdict helper methods to `SystemService`.
2. Wire the verdict into `company_intelligence` responses.
3. Assert not-found and incomplete verdict behavior in existing company intelligence tests.
4. Update roadmap and handoff records.
5. Run focused validation and handoff validation.

## Validation Plan

- Run Python compile for changed service and test files.
- Run focused company intelligence tests.
- Run handoff validation.
- Run `git diff --check`.

## Current State

- Completed: `/api/company-intelligence/{symbol}` now returns `completeness_verdict`.
- Completed: verdict covers company profile, market data, events, relationships, research viewpoints and simulation feedback.
- Completed: verdict includes blocking gaps, warning gaps, score, readiness booleans, required layers, missing layers and recommended next action.
- Completed: verdict pulls company database coverage and profile deep-field coverage scores when an issuer is resolved.
- Completed: source policy states research reports are opinion/attention records and cannot complete fact fields.
- In progress: none.
- Not started: UI visual status strip for `completeness_verdict`.
- Blocked: none.

## Dependencies

- T-432 company intelligence aggregation.
- T-445 company database coverage audit.
- T-456 company profile deep-field coverage audit.
- T-460 field-level company profile assertions.
- T-461 local company material inbox.

## Blockers

- None.

## Files Touched

- `app/services.py`: added `completeness_verdict` generation to `company_intelligence` and helper methods for section counts and next action selection.
- `tests/test_system.py`: added assertions for not-found and incomplete company intelligence verdicts.
- `tasks/todo.md`: added T-462 completion record and next UI follow-up.
- `docs/agent-handoffs/README.md`: added T-462 to the handoff index.
- `docs/agent-handoffs/2026-06-25-T-462-company-intelligence-completeness-verdict.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/services.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused company intelligence tests after correcting the SPCX expected missing layer from relationships to events.
- Failed then fixed: first handoff validation run reported missing standard sections in this file.
- Passed: `git diff --check`.

## Evidence

Commands run:

```bash
python3 -m py_compile app/services.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused company intelligence tests.
- Passed: diff whitespace check.

## Decisions

- Kept the first slice in the service/API response instead of adding UI in the same change, because users need a stable backend contract first.
- Treated company profile, market data, events and relationships as blocking fact-layer requirements.
- Treated research viewpoints and simulation feedback as non-blocking but important analysis and review layers.
- Reused existing coverage and deep-field audit helpers rather than creating a second coverage model.
- Preserved the boundary that research reports are not fact sources and simulation feedback is paper-only.

## Risks and Open Questions

- UI still needs to render the verdict outside raw JSON.
- The scoring weights are pragmatic defaults and should be revisited after real company coverage samples.
- Deep field missing facts are currently surfaced as `missing_fact_fields`; they do not yet independently block the verdict unless the profile layer is missing.

## Artifacts

- None generated or committed in this slice.

## Handoff Checklist

- [x] API verdict added.
- [x] Source boundary documented in verdict.
- [x] Focused tests updated.
- [x] Roadmap updated.
- [x] Handoff created.

## Next Steps

1. Add a UI status strip and gap table for `completeness_verdict`.
2. Add browser acceptance for incomplete, analysis-ready and feedback-ready states.
3. Continue T-463 for conflicting or replacement field assertions.

## Next Recommended Action

Implement the UI status strip and browser acceptance for `completeness_verdict` so users do not need to inspect raw JSON to understand why a company page is still incomplete.
