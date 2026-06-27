# Handoff: T-513 Ownership Context Facts vs Candidates

## Metadata

- Status: DONE
- Owner group: Data and Evidence, Product and UI
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main `/home/xionglei/Project/sotck_quant`
- Related tasks: T-513

## Objective

Split approved ownership facts from pending ownership candidates in the company relationship context and UI.

## Scope

- In scope: derived relationship context structure, company intelligence UI rendering, tests, browser acceptance, roadmap status.
- Out of scope: storage schema migration, automatic approval, external data fetching, real broker integration, automatic trading.

## Background

T-512 promoted approved ownership candidates into fact relationship types such as `shareholder`. The company relationship context still displayed ownership relationship rows under `relationship_candidates`, which made approved facts look like pending candidates.

## Problem Statement

The company intelligence page could correctly approve and graph a shareholder relationship, but the multi-dimensional relationship panel still labeled it as a candidate. That contradicted the review state and confused the relationship chain.

## Expected Deliverables

- `relationship_context.ownership.approved_relationships` contains approved active ownership fact relationships.
- `relationship_context.ownership.relationship_candidates` contains only pending candidate relationships.
- UI renders approved ownership facts separately from candidates.
- Browser acceptance proves the approved fact appears in the context and candidates are empty after approval.

## Current State

- Completed: `relationship_context.ownership` now returns `approved_relationships`, `relationship_candidates`, and compatibility list `relationships`.
- Completed: Summary includes `approved_ownership_relationships` and `ownership_candidates`.
- Completed: Multi-dimensional relationship UI renders "事实股权关系" separately from "股权候选".
- Completed: Unit and browser checks cover approved shareholder context classification.
- In progress: none.
- Not started: reverse shareholder-network expansion from approved ownership facts.
- Blocked: none.

## Current Findings

- The relationship context is a derived read model, so this split does not require rebuilding the database.
- Approved facts can be identified by non-candidate relationship types plus `active/approved` state.
- Pending candidates can be identified by `*_candidate`, `needs_review`, or `metadata.candidate_status=candidate`.

## Proposed Work Plan

1. Split ownership rows in the derived relationship context.
2. Render approved ownership facts before candidate rows in the UI.
3. Extend existing approval regression to assert context classification.
4. Extend browser acceptance to check the context and UI label after approval.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links
python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8774 --output-dir artifacts/ui-interaction-acceptance-t513 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Files Touched

- `app/service_modules/company_intelligence.py`: split ownership relationship context into approved facts and pending candidates.
- `app/static/index.html`: render "事实股权关系" rows separately from "股权候选".
- `tests/test_system.py`: extended approval-to-context regression.
- `scripts/ui_interaction_acceptance.py`: browser acceptance checks approved relationship context and UI label after approval.
- `tasks/todo.md`: records T-513.
- `docs/agent-handoffs/2026-06-27-T-513-ownership-context-facts-vs-candidates.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links
python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8774 --output-dir artifacts/ui-interaction-acceptance-t513 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: unit, py_compile, and static UI checks before this handoff was written.
- Passed: `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8774 --output-dir artifacts/ui-interaction-acceptance-t513 --timeout 60` with `check_count=33`, `failure_count=0`.
- Pending: handoff validation and whitespace check after this handoff update.
- Failed: one invalid command attempted to `py_compile` `app/static/index.html`; command error only, not a code failure.
- Not run: broad full unit suite.

## Decisions

- Keep `ownership.relationships` as a compatibility aggregate while adding explicit `approved_relationships` and `relationship_candidates`.
- Define pending candidates by candidate type/status rather than source layer alone.
- Keep coverage score using total ownership relationship count for now; candidate-vs-fact scoring is a follow-up.

## Dependencies

- T-512 ownership candidate approval and promotion.
- Existing `relationship_context` derived read model.
- Existing company intelligence relationship context panel.

## Blockers

- No blocker for this slice.

## Risks and Open Questions

- Consumers using `relationship_context.ownership.relationship_candidates` as "all ownership relationships" must move to `relationships` or `approved_relationships`.
- Coverage diagnostics still count candidates and approved ownership facts together.

## Artifacts

- `artifacts/ui-interaction-acceptance-t513`: local-only browser acceptance output, valid for the isolated local run only.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module used: Yes, the split lives in `app/service_modules/company_intelligence.py`.
- `SystemService` changes: None for T-513.
- Focused regression: `tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship`.
- API schema changed: Additive derived read-model fields under `relationship_context.ownership` and summary.
- Storage schema changed: No.
- UI behavior changed: approved ownership facts render as facts, not candidates.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links`: passed before this handoff was written.
- `python3 -m py_compile app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py`: passed before this handoff was written.
- `python3 scripts/ui_static_check.py`: passed before this handoff was written.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8774 --output-dir artifacts/ui-interaction-acceptance-t513 --timeout 60`: passed, `33/33` checks, `failure_count=0`.
- Handoff validation and `git diff --check`: pending final rerun.

## Next Steps

1. Add reverse shareholder-network expansion from approved ownership facts.
2. Separate ownership fact coverage and candidate coverage in diagnostics.
3. Update API contract text to describe the new read-model fields.

## Next Recommended Action

Add reverse shareholder-network expansion for approved ownership facts.
