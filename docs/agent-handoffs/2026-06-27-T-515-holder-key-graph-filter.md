# Handoff: T-515 Holder-Key Graph Filter

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows, Product and UI
- Reviewer groups: Platform and Quality, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree, branch not assumed

## Objective

Enable the dynamic relationship graph to expand an approved same-shareholder network by holder key, so a row in `relationship_context.ownership.approved_shareholder_related_companies` can open all approved active ownership facts for that same holder.

## Scope

- In scope: `relationship_context` holder key output, `/api/graph/query` holder-key filtering, UI graph action parameters, focused unit coverage, API contract docs, roadmap status.
- Out of scope: database rebuild, external graph database sync, real broker integration, non-local production release evidence, broad browser fixture for persisted multi-company holder networks.

## Background

T-514 added `approved_shareholder_related_companies`, which answers "this approved shareholder also appears on which other companies". The remaining gap was that clicking those rows still opened only a relationship-type graph rather than a same-holder network.

## Problem Statement

The relationship graph needed a stable filter that could cross issuer boundaries by an approved holder key while preserving the boundary between facts and candidates. Candidate ownership rows must remain visible for review workflows but must not enter the approved same-shareholder fact graph.

## Expected Deliverables

- `/api/graph/query` supports `ownership_holder_key`.
- Company-intelligence relationship rows expose a reusable `holder_key`.
- The UI passes `ownership_holder_key` when opening graph context from "事实股东关联".
- Tests verify cross-company expansion and candidate/unrelated exclusion.
- API contract, roadmap, and handoff are updated.

## Current Findings

- `CompanyRelationship.relationship_status` only supports `active`, `inactive`, `historical`, and `unknown`; candidate state is expressed through `relationship_type=*_candidate` plus `review_status=needs_review`.
- Existing graph construction lives in `SystemService.query_graph()`, so holder-key graph assembly remains there while normalization is delegated to `company_intelligence.ownership_holder_key()`.
- The UI already had a generic `openRelationshipGraphContext()` path that could carry one more pending filter without changing tab navigation.

## Proposed Work Plan

- Completed: expose `ownership_holder_key()` in `app/service_modules/company_intelligence.py`.
- Completed: add `holder_key` to `approved_shareholder_related_companies`.
- Completed: add `ownership_holder_key` parsing and approved ownership filtering in `SystemService.query_graph()`.
- Completed: anchor cross-company relationship graph edges to each relationship's issuer.
- Completed: pass `ownership_holder_key` through `app/static/index.html`.
- Completed: update focused regression, API contract, and roadmap.

## Validation Plan

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies
python3 -m py_compile app/services.py app/service_modules/company_intelligence.py scripts/ui_interaction_acceptance.py tests/test_system.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

## Risks

- Future graph UI could make active holder-key filters more visible with a chip or subtitle.

## Dependencies

- Existing `CompanyRelationship` storage and review workflow.
- Existing company-intelligence `relationship_context`.
- Existing static UI graph loader and `/api/graph/query` endpoint.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed.
- [x] Tests/checks run or explicitly skipped with reason.
- [x] Docs/contracts updated.
- [x] `tasks/todo.md` status updated.
- [x] No real broker or automated trading behavior introduced.

## Evidence

- Focused unit test passed after correcting the candidate fixture to a legal `relationship_status`.
- `python3 -m py_compile ...` passed.
- `python3 scripts/ui_static_check.py` passed.
- `git diff --check` passed.
- `python3 scripts/check_handoffs.py` passed after the template correction.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t516 --timeout 60` passed with 35/35 checks, including `company_ownership_holder_key_graph_click_loads_same_holder_network`.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: narrowly scoped graph-query filtering in the existing `query_graph()` facade.
- Domain module use: holder-key normalization lives in `app/service_modules/company_intelligence.py`; graph assembly remains in `SystemService.query_graph()` because that method owns graph edge/node construction.
- Focused regression: `test_relationship_context_links_approved_same_shareholder_companies` covers relationship-context holder key output, cross-company graph expansion, and candidate/unrelated exclusion.
- API schema changed: `/api/graph/query` accepts optional `ownership_holder_key`.
- Storage schema changed: no.
- UI behavior changed: "事实股东关联" graph action sends holder key.
- Paper-only/no-broker boundary changed: no.

## Next Recommended Action

Add a visible graph filter chip or subtitle for active `ownership_holder_key` filters so users can see why the rendered graph is scoped to one shareholder network.
