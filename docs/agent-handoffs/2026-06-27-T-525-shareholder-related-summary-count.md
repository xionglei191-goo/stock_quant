# Handoff: T-525 Shareholder Related Summary Count

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Fix the company intelligence relationship summary count so `股东关联` reflects both approved fact shareholder networks and 13F/institutional holding same-holder networks.

## Scope

- In scope: relationship summary count rendering, UI static contract, browser acceptance assertion, API contract note, roadmap entry, handoff.
- Out of scope: backend relationship context schema changes, relationship graph query behavior, ownership import behavior.

## Background

The relationship table now distinguishes `事实股东关联` from 13F/holding-derived `股东关联公司`. The top `股东关联` metric still used only `summary.shareholder_related_companies`, which represents the 13F/holding-derived network.

## Problem Statement

When approved fact shareholder related companies exist but no 13F same-holder records exist, the detail table can show `事实股东关联` while the top summary still displays zero. That makes the relationship chain look incomplete even when fact shareholder expansion is available.

## Expected Deliverables

- Display a combined shareholder related count in the top relationship summary.
- Show fact and holding-derived subcounts explicitly as `事实 N / 持仓 M`.
- Protect the expression with static UI contract.
- Extend browser acceptance to assert `事实 1` in the same-holder fixture.

## Current Findings

- Backend summary already exposes both `approved_shareholder_related_companies` and `shareholder_related_companies`.
- Only the UI top metric was using the narrower 13F/holding count.
- Existing browser acceptance same-holder fixture can prove the fact subcount.

## Proposed Work Plan

- Completed: update `companyIntelShareholderRelatedCount` rendering to show combined and split counts.
- Completed: add a static contract marker for the `事实 / 持仓` expression.
- Completed: extend `company_ownership_approved_same_holder_network_context` browser assertion to require `事实 1`.
- Completed: update `docs/api-contracts.md` and `tasks/todo.md`.

## Validation Plan

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t525 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- The summary text is denser than before. It is intentional because the two shareholder-network sources have different provenance and should not be collapsed silently.
- This is UI-only; API consumers should continue reading the two separate summary fields for exact source-specific counts.

## Dependencies

- Existing `relationship_context.summary.approved_shareholder_related_companies`.
- Existing `relationship_context.summary.shareholder_related_companies`.
- Existing browser acceptance fixture for approved Alpha Capital same-holder relationships.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated where applicable.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py` passed.
- `python3 scripts/ui_static_check.py` passed with `interaction_markers=17`, `required_functions=162`, `required_ids=379`, and `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t525 --timeout 60` passed with 36/36 checks; evidence URI `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t525`.
- `python3 scripts/check_handoffs.py` passed before browser run; rerun after final evidence update.
- `git diff --check` passed before browser run; rerun after final evidence update.
- Browser server was launched with explicit local SQLite/object-store overrides because `.env` contains PostgreSQL settings and this environment lacks `psycopg`.

## Next Recommended Action

Consider exposing a tooltip or compact legend for `事实 / 持仓` if analysts need a clearer explanation of the source split.
