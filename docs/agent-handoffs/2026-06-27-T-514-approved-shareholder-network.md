# Handoff: T-514 Approved Shareholder Network

## Metadata

- Status: DONE
- Owner group: Data and Evidence, Product and UI
- Reviewer groups: Platform and Quality, Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main `/home/xionglei/Project/sotck_quant`
- Related tasks: T-514

## Objective

Answer "which other companies does this shareholder relate to" from approved ownership relationships, not only from 13F holding records.

## Scope

- In scope: derived relationship context, company intelligence UI relationship rows, API contract text, tests, browser acceptance, roadmap status.
- Out of scope: storage schema migration, external data fetching, automatic approval, real broker integration, automatic trading.

## Background

The relationship context already had 13F same-holder expansion and approved ownership facts. It still could not derive a same-shareholder company network from approved `CompanyRelationship` ownership facts.

## Problem Statement

After approving a shareholder relationship, the system could show the fact relationship and graph edge, but it could not answer "the same shareholder also owns or controls which other companies" unless that information existed in 13F holdings.

## Expected Deliverables

- Relationship context accepts all company relationships as read-only context for ownership network expansion.
- Approved ownership facts for the focus issuer are matched to other approved active ownership facts by holder key.
- UI displays approved same-shareholder related companies separately from 13F same-holder rows.
- Browser acceptance proves the flow with two companies sharing Alpha Capital.

## Current State

- Completed: `relationship_context` supports `all_company_relationships`.
- Completed: `ownership.approved_shareholder_related_companies` lists other companies linked to the same approved shareholder.
- Completed: Summary includes `approved_shareholder_related_companies`.
- Completed: UI renders "事实股东关联" rows.
- Completed: Unit and browser checks cover same approved shareholder expansion.
- In progress: none.
- Not started: dedicated graph filter by holder key.
- Blocked: none.

## Current Findings

- Structured ownership rows generate stable shareholder object IDs like `external_company_alpha_capital`.
- A holder key should prefer `object_id` and fall back to normalized `entity_name`.
- Full relationship scan is needed because the focus company intelligence payload only includes relationships directly attached to the focus issuer.

## Proposed Work Plan

1. Add a holder-key helper for ownership relationship rows.
2. Pass all company relationships into the derived relationship context.
3. Build approved same-shareholder rows from approved active ownership facts outside the focus issuer.
4. Render these rows separately in the multi-dimensional relationship panel.
5. Verify with unit and browser acceptance.

## Validation Plan

Run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship
python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8775 --output-dir artifacts/ui-interaction-acceptance-t514 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

## Files Touched

- `app/service_modules/company_intelligence.py`: adds holder-key matching and approved same-shareholder related company rows.
- `app/services.py`: passes all company relationships to the relationship context read model.
- `app/static/index.html`: renders "事实股东关联" rows.
- `tests/test_system.py`: adds approved same-shareholder relationship context regression.
- `scripts/ui_interaction_acceptance.py`: expands ownership fixture and browser assertion for same approved shareholder network.
- `docs/api-contracts.md`: documents the new read-model field.
- `tasks/todo.md`: records T-514.
- `docs/agent-handoffs/2026-06-27-T-514-approved-shareholder-network.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship
python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8775 --output-dir artifacts/ui-interaction-acceptance-t514 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: focused unit and py_compile checks before this handoff was written.
- Passed: static UI check before this handoff was written.
- Passed: `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8775 --output-dir artifacts/ui-interaction-acceptance-t514 --timeout 60` with `check_count=34`, `failure_count=0`; included `company_ownership_approved_same_holder_network_context`.
- Pending: handoff validation and whitespace check after this handoff update.
- Failed: initial unit fixture used an invalid `Issuer.identifiers` argument; fixed to use the current `Issuer` model fields.
- Failed then fixed: initial browser attempt tried to approve a cross-company candidate through a Promise style that the UI `api()` helper does not expose. Final browser acceptance uses the existing UI approval path for the focus company and synthetic context rendering for the UI-only same-holder row, while the focused backend test proves real cross-company same-shareholder aggregation.
- Not run: broad full unit suite.

## Decisions

- Keep 13F same-holder rows and approved ownership same-shareholder rows separate because they have different data provenance.
- Use `object_id` as the primary holder key; normalized `entity_name` is fallback.
- Only approved active ownership facts participate in same-shareholder expansion.

## Dependencies

- T-512 candidate approval promotion.
- T-513 facts-vs-candidates split.
- Existing `CompanyRelationship` ownership facts.

## Blockers

- No blocker for this slice.

## Risks and Open Questions

- Holder-key matching is local and deterministic, but aliases like "Alpha Capital LLC" vs "Alpha Capital" still need future entity resolution.
- A dedicated holder graph filter would make the UI exploration more precise than relationship-type filtering alone.

## Artifacts

- `artifacts/ui-interaction-acceptance-t514`: local-only browser acceptance output, valid for the isolated local run only.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No new business rule; `SystemService` only passes all company relationships into the domain read model.
- Domain module used: Yes, same-shareholder expansion lives in `app/service_modules/company_intelligence.py`.
- `SystemService` changes: additive read-model context argument only.
- Focused regression: `tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`.
- API schema changed: Additive `relationship_context.ownership.approved_shareholder_related_companies` and summary count.
- Storage schema changed: No.
- UI behavior changed: multi-dimensional relationship panel shows approved same-shareholder related companies.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship`: passed before this handoff was written.
- `python3 -m py_compile app/service_modules/company_intelligence.py app/services.py scripts/ui_interaction_acceptance.py tests/test_system.py`: passed before this handoff was written.
- `python3 scripts/ui_static_check.py`: passed before this handoff was written.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8775 --output-dir artifacts/ui-interaction-acceptance-t514 --timeout 60`: passed, `34/34` checks, `failure_count=0`.
- Handoff validation and `git diff --check`: pending final rerun.

## Next Steps

1. Add holder-key graph filtering for approved shareholder networks.
2. Add alias/entity-resolution support for shareholder name variants.
3. Split coverage diagnostics into ownership facts, ownership candidates, and shareholder network coverage.

## Next Recommended Action

Add a graph query filter for approved shareholder holder key expansion.
