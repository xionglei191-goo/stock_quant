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
- Render the verdict in the company intelligence workbench outside raw JSON.
- Distinguish blocking fact-layer gaps from non-blocking viewpoint/feedback gaps.
- Keep research reports as opinion and attention records, not fact sources.
- Keep simulation feedback paper-only.
- Cover the verdict with focused service tests, UI static checks, browser interaction acceptance and a handoff.

## Scope

- In scope: `SystemService.company_intelligence`, company intelligence UI verdict display, focused tests, UI acceptance scripts, roadmap entry and handoff.
- Out of scope: external crawling, real broker integration, live trading, new storage collections and scoring model calibration from large samples.

## Current Findings

- Existing `section_counts` and `data_quality` already exposed most ingredients for a verdict.
- Existing company database coverage and profile deep-field coverage helpers can be reused for score context.
- SPCX single-name research creates relationship coverage, but not an event timeline, so the expected blocking gap is `events`.
- DEMO first-class object coverage can still be incomplete if market data is absent.
- The company intelligence workbench already had `system-strip`, `system-box` and `badge` styles suitable for compact verdict display.
- Browser acceptance can validate the verdict without relying only on raw JSON by checking `companyIntelVerdictStatus` and `companyIntelVerdictRows`.

## Proposed Work Plan

1. Add verdict helper methods to `SystemService`.
2. Wire the verdict into `company_intelligence` responses.
3. Assert not-found and incomplete verdict behavior in existing company intelligence tests.
4. Render verdict status, score, readiness and per-layer rows in the company intelligence workbench.
5. Update static and browser UI acceptance.
6. Update roadmap and handoff records.
7. Run focused validation and handoff validation.

## Validation Plan

- Run Python compile for changed service and test files.
- Run focused company intelligence tests.
- Run UI static check.
- Run browser interaction acceptance against a current-code temporary service.
- Run handoff validation.
- Run `git diff --check`.

## Current State

- Completed: `/api/company-intelligence/{symbol}` now returns `completeness_verdict`.
- Completed: verdict covers company profile, market data, events, relationships, research viewpoints and simulation feedback.
- Completed: verdict includes blocking gaps, warning gaps, score, readiness booleans, required layers, missing layers and recommended next action.
- Completed: verdict pulls company database coverage and profile deep-field coverage scores when an issuer is resolved.
- Completed: source policy states research reports are opinion/attention records and cannot complete fact fields.
- Completed: company intelligence workbench renders verdict status, score, fact/analysis/feedback readiness, missing fact fields and per-layer verdict rows.
- Completed: raw JSON summary includes `completeness_verdict` for cross-checking UI output.
- Completed: UI static contract and browser interaction acceptance require verdict DOM to be present and populated.
- In progress: none.
- Not started: large-sample weight calibration and conflict-aware field assertion scoring.
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
- `app/static/index.html`: added verdict DOM, rendering function, status labels and raw JSON inclusion.
- `scripts/ui_static_check.py`: added verdict DOM IDs and render function to static contract.
- `scripts/ui_interaction_acceptance.py`: added verdict diagnostics and browser assertions for SPCX and unknown-company flows.
- `tests/test_system.py`: added assertions for not-found and incomplete company intelligence verdicts.
- `tasks/todo.md`: updated T-462 completion record with UI and browser acceptance.
- `docs/agent-handoffs/README.md`: added T-462 to the handoff index.
- `docs/agent-handoffs/2026-06-25-T-462-company-intelligence-completeness-verdict.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/services.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8767 --output-dir artifacts/ui-interaction-acceptance-verdict --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused company intelligence tests after correcting the SPCX expected missing layer from relationships to events.
- Passed: UI static check with `required_ids=224`, `required_functions=74`, `node_check=passed`.
- Passed: browser interaction acceptance against current-code temporary service, 18/18 checks.
- Failed then fixed: first handoff validation run reported missing standard sections in this file.
- Passed: `git diff --check`.

## Evidence

Commands run:

```bash
python3 -m py_compile app/services.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 scripts/ui_static_check.py
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8767 --output-dir artifacts/ui-interaction-acceptance-verdict --timeout 60
git diff --check
```

Result:

- Passed: Python compile.
- Passed: focused company intelligence tests.
- Passed: UI static check.
- Passed: browser interaction acceptance, 18/18 checks.
- Passed: diff whitespace check.

## Decisions

- Kept the service/API verdict as the source of truth, and rendered a compact UI projection rather than duplicating scoring logic in the browser.
- Treated company profile, market data, events and relationships as blocking fact-layer requirements.
- Treated research viewpoints and simulation feedback as non-blocking but important analysis and review layers.
- Reused existing coverage and deep-field audit helpers rather than creating a second coverage model.
- Used existing `system-strip`, `system-box` and `badge` UI patterns to keep the company intelligence workbench dense and operational.
- Preserved the boundary that research reports are not fact sources and simulation feedback is paper-only.

## Risks and Open Questions

- The scoring weights are pragmatic defaults and should be revisited after real company coverage samples.
- Deep field missing facts are currently surfaced as `missing_fact_fields`; they do not yet independently block the verdict unless the profile layer is missing.
- Browser acceptance used a temporary in-memory service on port 8767 for current-code validation; it proves UI behavior, not production-like PostgreSQL data coverage.

## Artifacts

- `artifacts/ui-interaction-acceptance-verdict/ui-interaction-acceptance.json`: local-only browser acceptance evidence, generated against `http://127.0.0.1:8767`, not committed and not valid as non-local production evidence.

## Handoff Checklist

- [x] API verdict added.
- [x] UI verdict strip and rows added.
- [x] Source boundary documented in verdict.
- [x] Focused tests updated.
- [x] UI static contract updated.
- [x] Browser interaction acceptance updated and run.
- [x] Roadmap updated.
- [x] Handoff created.

## Next Steps

1. Continue T-463 for conflicting or replacement field assertions.
2. Calibrate verdict weights after real company coverage samples.
3. Consider making deep missing fact fields influence blocking readiness after enough field assertion coverage data exists.

## Next Recommended Action

Continue T-463 for conflicting or replacement field assertions so field-level evidence can handle multiple sources, revised values and manual review outcomes.
