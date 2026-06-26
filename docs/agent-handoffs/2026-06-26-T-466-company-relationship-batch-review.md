# Handoff: T-466 Company Relationship Batch Review

## Metadata

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-466

## Status

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Add batch review and recommendation support for first-class `CompanyRelationship` candidates so analysts can process customer, supplier, partner and subsidiary relationship candidates as part of the company intelligence database workflow.

## Background

T-443/T-444/T-448 added first-class relationship candidates from public disclosures and made single-row review available in the company intelligence workbench. The relationship layer still lacked the batch handling and review recommendation workflow already added for profile field assertions in T-465.

## Problem Statement

Company relationship candidates are a core part of the company database, but reviewing them one by one slows down local backfill and leaves the graph quality workflow weaker than the profile-field workflow.

## Expected Deliverables

- Relationship list payloads enriched with source quality and review recommendation.
- Batch relationship review endpoint for approve/reject/merge.
- Company intelligence UI controls for selecting multiple relationship candidates and writing review notes.
- Static UI, synthetic browser acceptance and backend regression coverage.
- API contract, roadmap and handoff updates.

## Scope

- In scope: `CompanyRelationship` list/review API, company intelligence workbench, UI acceptance/static checks, tests, API docs, roadmap and handoff.
- Out of scope: automatic relationship approval, external source download, event review, material inbox UI, real broker/live trading integrations.

## Current Findings

- `CompanyRelationship` already has `review_status`, `relationship_status`, metadata and source/document/evidence back-links, so no new model was needed.
- Existing source quality scoring for event/relationship reconciliation could be reused for review recommendations.
- Backend explorer identified event candidate review as the next core data-quality gap.
- UI/data-source explorer identified local official/IR material inbox UI as the next data source workflow gap.

## Proposed Work Plan

1. Enrich `company_relationships_payload` with review status counts, candidate count, source quality and recommendation data.
2. Add a batch review service and API route while preserving the existing single-row review path.
3. Add relationship review status, candidate count, recommendation status, checkboxes, batch approve/reject and review note controls to the company intelligence workbench.
4. Extend static UI and synthetic browser acceptance contracts.
5. Extend backend regression coverage.
6. Update API contracts, roadmap and handoff.

## Validation Plan

- Run Python compile on touched Python files.
- Run UI static check.
- Run a direct service/API smoke for batch relationship review.
- Attempt focused unittest; document environment blockers if test extras are missing.
- Run handoff validation.

## Current State

- Completed: `GET|POST /api/company-relationships` now returns enriched relationship rows and review/candidate counts.
- Completed: `POST /api/company-relationships/review` and `POST /api/company-database/relationships/review` support `relationship_ids` batch review.
- Completed: company intelligence workbench supports relationship candidate selection, batch approve/reject and review notes.
- Completed: tests and UI contracts were updated for the new relationship review path.
- Blocked: full targeted unittest import is blocked by missing `PIL` in the current `.venv`.

## Dependencies

- Existing `CompanyRelationship` model and `/api/company-relationships/{relationship_id}/review`.
- Existing company database relationship builder and quality reconciliation source-quality helper.
- T-448 company intelligence workbench operations.

## Blockers

- The current `.venv` lacks `PIL`, so importing `tests/test_system.py` fails before focused unit tests run. `pyproject.toml` already declares `Pillow>=10.0` under `test` and `ui-acceptance` extras.

## Files Touched

- `app/services.py`: added relationship row enrichment, source-quality-based review recommendation and `review_company_relationships`.
- `app/api.py`: added `/api/company-relationships/review` and `/api/company-database/relationships/review`.
- `app/static/index.html`: added relationship review counts, recommendation status, selection checkboxes, batch approve/reject and review note UI.
- `scripts/ui_static_check.py`: added new DOM/function/interaction contract markers.
- `scripts/ui_interaction_acceptance.py`: added synthetic browser check for relationship review queue rendering.
- `tests/test_system.py`: extended relationship review test to cover recommendation output and batch review note persistence.
- `docs/api-contracts.md`: documented batch review endpoints and relationship recommendation semantics.
- `tasks/todo.md`: added T-466 DONE and recorded follow-up gaps.
- `docs/agent-handoffs/2026-06-26-T-466-company-relationship-batch-review.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/api.py app/services.py tests/test_system.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
python3 - <<'PY'
from app.api import ApiRouter
from app.services import SystemService

svc = SystemService()
router = ApiRouter(svc)
for rid, conf, source_layer in [
    ('rel_smoke_a', 0.72, 'official_disclosure_candidate'),
    ('rel_smoke_b', 0.38, ''),
]:
    svc.register_company_relationship({
        'relationship_id': rid,
        'issuer_id': 'issuer_001',
        'security_id': 'sec_001',
        'subject_type': 'company',
        'subject_id': 'issuer_001',
        'object_type': 'company',
        'object_id': f'external_{rid}',
        'relationship_type': 'customer_candidate',
        'relationship_status': 'unknown',
        'review_status': 'needs_review',
        'confidence': conf,
        'source_ids': ['src_sec'] if source_layer else [],
        'document_ids': ['doc_smoke'] if source_layer else [],
        'evidence_ids': ['ev_smoke'] if source_layer else [],
        'metadata': {'candidate_status': 'candidate', 'source_layer': source_layer},
    })
listed = router.dispatch('GET', '/api/company-relationships', {'issuer_id': 'issuer_001', 'review_status': 'needs_review'}, role='analyst')
assert listed.success, listed.error
assert listed.data['candidate_count'] == 2, listed.data
assert listed.data['relationships'][0]['review_recommendation']['recommended_action'] in {'prefer_approve_after_review', 'manual_review_required'}
reviewed = router.dispatch('POST', '/api/company-database/relationships/review', {'relationship_ids': ['rel_smoke_a', 'rel_smoke_b'], 'action': 'reject', 'reason': 'smoke'}, role='analyst')
assert reviewed.success, reviewed.error
assert reviewed.data['reviewed_count'] == 2, reviewed.data
assert svc.store.company_relationships['rel_smoke_a'].review_status == 'rejected'
assert svc.store.company_relationships['rel_smoke_b'].relationship_status == 'inactive'
print('relationship batch review smoke passed')
PY
./.venv/bin/python -m unittest tests.test_system.SystemServiceTest.test_company_relationship_review_approves_rejects_and_merges_candidates
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile on touched Python files.
- Passed: UI static check, `required_ids=243`, `required_functions=83`, `interaction_markers=11`.
- Passed: direct relationship batch review smoke.
- Failed: targeted unittest did not reach the test because `PIL` is missing from the current `.venv`.
- Passed: handoff validation.

## Evidence

- Direct smoke proves list enrichment, recommendation presence and batch reject behavior through `ApiRouter`.
- UI static check proves new controls, functions and interaction markers are present.
- `tests/test_system.py` contains focused regression coverage for recommendation output and batch review note persistence, but the local test environment must install `Pillow` test extra before the unittest command can execute.

## Decisions

- Batch relationship review uses a new collection endpoint instead of overloading the existing single-relationship URL.
- Recommendations are advisory only and remain tied to human review. They do not auto-approve relationships and do not generate investment advice.
- Source quality is recalculated when `metadata.source_quality` is absent or malformed, preventing old relationship rows from breaking list queries.

## Risks and Open Questions

- Recommendation scoring is intentionally simple and should be calibrated with real relationship review outcomes.
- Event review remains a core gap because structured `CompanyEvent` candidates can be generated but not yet approved/rejected/reclassified through a first-class review API.
- Material inbox UI remains a data-source workflow gap even though the CLI script exists.

## Artifacts

- None. This task did not generate persistent runtime artifacts.

## Handoff Checklist

- [x] Batch review API added.
- [x] Recommendation payload added.
- [x] UI controls added.
- [x] Static and smoke coverage run.
- [x] Roadmap/docs updated.
- [x] Handoff created.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## Next Steps

1. T-467: Add company material inbox UI for local official/IR manifest ingestion.
2. T-468: Add `CompanyEvent` candidate review API and workbench.
3. T-469: Add retry/resume buttons for failed or partial company database build runs.

## Next Recommended Action

Implement the `CompanyEvent` review API or material inbox UI next; both are stronger blockers for a complete all-weather company database than further relationship review polish.
