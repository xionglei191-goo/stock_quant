# Handoff: T-512 Ownership Approval Graph Edge

## Metadata

- Status: DONE
- Owner group: Data and Evidence, Product and UI
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main `/home/xionglei/Project/sotck_quant`
- Related tasks: T-512

## Objective

Complete the ownership relationship chain from imported review candidate to approved fact relationship visible in the company graph.

## Scope

- In scope: company relationship approval semantics, graph filtering evidence, browser acceptance, roadmap status.
- Out of scope: schema migration, automatic approval, external ownership data download, real broker integration, automatic trading.

## Background

T-511 made imported ownership candidates visible in the review queue. The remaining logic gap was what happens after an analyst approves a candidate: the system should no longer treat it as a candidate-only relationship.

## Problem Statement

Approved relationships were marked `approved/active`, but the relationship type could remain `shareholder_candidate`. That made graph filtering and relationship context still read as candidate semantics after manual approval.

## Expected Deliverables

- Approved candidate relationships are promoted to fact relationship types.
- Original candidate type is preserved in metadata for auditability.
- Graph query with the promoted type returns the approved relationship.
- Browser acceptance proves the approve-to-graph path.

## Current State

- Completed: `review_company_relationship(... approve)` promotes `*_candidate` to its base relationship type.
- Completed: Promotion stores `metadata.candidate_relationship_type` and `metadata.promoted_relationship_type`.
- Completed: Unit regression covers imported shareholder candidate approval and graph filtering.
- Completed: Browser acceptance approves the imported ownership candidate and opens a shareholder-filtered relationship graph.
- In progress: none.
- Not started: visual distinction between approved ownership facts and pending ownership candidates in the relationship context panel.
- Blocked: none.

## Current Findings

- Graph query already supports `relationship_type`; the main missing piece was semantic promotion on approval.
- The existing relationship object can carry the promoted type without a storage migration.
- Browser acceptance must run against isolated local storage because it writes and approves a candidate relationship.

## Proposed Work Plan

1. Add a small promotion helper inside `SystemService` review logic.
2. Cover the approval-to-graph behavior with a focused backend test.
3. Extend the browser acceptance flow after ownership import execution.
4. Update roadmap and handoff evidence.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates
python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8773 --output-dir artifacts/ui-interaction-acceptance-t512 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Files Touched

- `app/services.py`: candidate relationships are promoted to fact relationship types when approved.
- `tests/test_system.py`: added approval-to-active-graph regression.
- `scripts/ui_interaction_acceptance.py`: browser flow now approves the imported ownership candidate and opens a shareholder-filtered graph.
- `tasks/todo.md`: records T-512 status and validation.
- `docs/agent-handoffs/2026-06-27-T-512-ownership-approval-graph-edge.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates
python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8773 --output-dir artifacts/ui-interaction-acceptance-t512 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: unit, py_compile, and static UI checks before this handoff was written.
- Passed: `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8773 --output-dir artifacts/ui-interaction-acceptance-t512 --timeout 60` with `check_count=33`, `failure_count=0`; included `company_ownership_candidate_approve_promotes_graph_edge` and `company_ownership_approved_graph_filter_loads_shareholder_edge`.
- Pending: handoff validation and whitespace check after this handoff update.
- Failed: none known.
- Not run: broad full unit suite.

## Decisions

- Promotion happens only on explicit approve, not during import or dry-run.
- Keep the same relationship ID during promotion so audit history, evidence IDs, and review history remain attached.
- Preserve the original candidate type in metadata rather than duplicating the relationship record.

## Dependencies

- T-511 execution-to-review queue.
- Existing company relationship review API.
- Existing graph query `relationship_type` filter.

## Blockers

- No blocker for the completed approval-to-graph slice.

## Risks and Open Questions

- Existing consumers that expect approved relationships to retain `*_candidate` may need to switch to metadata fields for audit lineage.
- The relationship context panel still names `ownership.relationship_candidates`; it now contains ownership bucket rows and should be split into facts vs candidates in a follow-up.

## Artifacts

- `artifacts/ui-interaction-acceptance-t512`: local-only browser acceptance output generated by `scripts/ui_interaction_acceptance.py`; valid for this isolated local run only.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: Yes, but narrowly scoped to existing review semantics.
- Domain module used: Not used; this behavior belongs in the existing `review_company_relationship` state transition.
- `SystemService` changes: `_promote_company_relationship_candidate` promotes approved `*_candidate` relationship types to base fact types.
- Focused regression: `tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship`.
- API schema changed: No new endpoint; existing review response now reflects promoted relationship type after approval.
- Storage schema changed: No.
- UI behavior changed: Browser flow can approve an ownership candidate and load the promoted shareholder graph edge.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_company_relationship_review_approves_rejects_and_merges_candidates`: passed before this handoff was written.
- `python3 -m py_compile app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py`: passed before this handoff was written.
- `python3 scripts/ui_static_check.py`: passed before this handoff was written.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8773 --output-dir artifacts/ui-interaction-acceptance-t512 --timeout 60`: passed, `33/33` checks, `failure_count=0`.
- Handoff validation and `git diff --check`: pending final rerun.

## Next Steps

1. Split relationship context ownership rows into approved facts and pending candidates.
2. Add reverse shareholder-network expansion for approved ownership facts.
3. Consider a small UI badge for promoted relationships showing original candidate source.

## Next Recommended Action

Separate approved ownership facts from pending ownership candidates in the company relationship context panel.
