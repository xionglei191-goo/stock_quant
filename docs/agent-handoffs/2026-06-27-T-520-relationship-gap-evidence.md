# Handoff: T-520 Relationship Gap Evidence

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Make relationship coverage gaps show the evidence/source basis used for each diagnostic layer, so analysts can tell whether a gap comes from IndustryChain, CompanyPosition, InstitutionalHolding, CompanyRelationship, or graph edges.

## Scope

- In scope: company intelligence relationship gap rendering, static UI contract, API contract note, roadmap entry, handoff.
- Out of scope: backend schema changes, graph query behavior, ownership import behavior, diagnostic scoring changes.

## Background

T-519 split same-holder diagnostics into 13F/institutional holdings and approved fact shareholder networks. The response already includes `diagnostics[].evidence`, but the UI gap rows did not surface that source boundary.

## Problem Statement

Users need to understand not only which relationship chain layer is missing, but also what source type the system checked before marking it missing. Without the evidence/source label, 13F gaps, approved fact shareholder gaps, and industry-chain gaps are easy to confuse.

## Expected Deliverables

- Show `diagnostics[].evidence` in company intelligence relationship gap rows.
- Preserve the same backfill actions and required/optional labels.
- Add a structured `data-evidence` attribute to the gap action button for traceability and static checks.
- Update API contracts, roadmap, and handoff.

## Current Findings

- `renderCompanyRelationshipContext()` maps missing diagnostics into `relationshipRows`.
- Each diagnostic item already includes `evidence` from `_relationship_diagnostic()`.
- `renderInsightTable()` displays the `finding` text and allows custom `actionHtml`, so no new table component is needed.

## Proposed Work Plan

- Completed: append `来源: ${item.evidence}` to relationship gap `finding`.
- Completed: add `data-evidence` to the relationship gap action button with existing `escapeHtml()`.
- Completed: add the new marker to `scripts/ui_static_check.py`.
- Completed: document the UI trace behavior in `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- Evidence text is currently source-oriented English such as `same-holder InstitutionalHolding records`; later UI polish may translate or map it to shorter analyst-facing Chinese labels.
- This exposes only the diagnostic source type, not the specific source record IDs. Full record trace remains in the row's advanced trace object.

## Dependencies

- Existing `diagnostics[].evidence` response field from relationship coverage diagnostics.
- Existing `renderInsightTable()` and relationship gap action handling.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m py_compile scripts/ui_static_check.py` passed.
- `python3 scripts/ui_static_check.py` passed with `interaction_markers=16`, `required_functions=161`, `required_ids=379`, and `node_check=passed`.
- `python3 scripts/check_handoffs.py` passed, checking 94 markdown files.
- `git diff --check` passed.
- Browser acceptance skipped because this is a static rendering/trace attribute change covered by `scripts/ui_static_check.py`; no interaction flow or API behavior changed.

## Next Recommended Action

Consider adding analyst-facing Chinese labels for diagnostic evidence sources if the relationship gap list becomes too technical for routine use.
