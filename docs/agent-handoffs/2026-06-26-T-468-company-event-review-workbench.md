# Handoff: T-468 Company Event Review Workbench

## Metadata

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-468

## Status

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Add first-class review endpoints and workbench controls for `CompanyEvent` candidates so structured disclosure events can be approved, rejected, merged or reclassified before becoming trusted timeline inputs.

## Background

T-449 generated fine-grained `CompanyEvent` candidates from official disclosure text and marked them `review_status=needs_review`. Backend exploration found there was no equivalent to relationship or field assertion review for events, leaving the fact timeline without a complete human review loop.

## Problem Statement

The company intelligence database can generate event candidates, but users need a local review workflow to confirm, reject, merge or reclassify those candidates while preserving evidence and review history.

## Expected Deliverables

- Event list payloads enriched with source quality and review recommendation.
- Single and batch event review endpoints.
- Company intelligence UI event review panel with candidate count, recommendation status, selection, batch approve/reject, merge and reclassify controls.
- Static UI, synthetic browser acceptance and backend regression coverage.
- API contract, roadmap and handoff updates.

## Scope

- In scope: `CompanyEvent` list/review API, company intelligence workbench, UI acceptance/static checks, tests, API docs, roadmap and handoff.
- Out of scope: automatic event approval, external source download, material inbox UI, real broker/live trading integrations.

## Current Findings

- `CompanyEvent` already has `review_status`, `fact_status`, `metadata`, source/document/evidence back-links and merge metadata from quality reconciliation.
- Existing source-quality scoring can be reused for event review recommendations.
- `CompanyEvent` registration validates issuer existence, so direct smoke tests need to seed an issuer first.

## Proposed Work Plan

1. Enrich `company_events_payload` with fact/review status counts, candidate count, source quality and recommendation data.
2. Add single and batch event review service methods for approve/reject/merge/reclassify.
3. Add API routes under `/api/company-events/...` and `/api/company-database/events/review`.
4. Add company intelligence workbench event review panel.
5. Extend static UI and synthetic browser acceptance contracts.
6. Extend backend regression coverage.
7. Update API contracts, roadmap and handoff.

## Validation Plan

- Run Python compile on touched Python files.
- Run UI static check.
- Run a direct service/API smoke for batch event review.
- Attempt focused unittest; document environment blockers if test extras are missing.
- Run handoff validation.

## Current State

- Completed: `GET|POST /api/company-events` now returns enriched event rows and review/candidate counts.
- Completed: `POST /api/company-events/{event_id}/review`, `POST /api/company-events/review` and `POST /api/company-database/events/review` support event candidate review.
- Completed: company intelligence workbench has an event candidate review panel with batch approve/reject, merge and reclassification inputs.
- Completed: tests and UI contracts were updated for the new event review path.
- Blocked: focused unittest import is blocked by missing `PIL` in the current `.venv`.

## Dependencies

- Existing `CompanyEvent` model and company event builder.
- Existing company database quality reconciliation source-quality helper.
- T-449 structured disclosure event extraction.

## Blockers

- The current `.venv` lacks `PIL`, so importing `tests/test_system.py` fails before focused unit tests run. `pyproject.toml` already declares `Pillow>=10.0` under `test` and `ui-acceptance` extras.

## Files Touched

- `app/services.py`: added event row enrichment, source-quality-based review recommendation and single/batch event review.
- `app/api.py`: added `/api/company-events/{event_id}/review`, `/api/company-events/review` and `/api/company-database/events/review`.
- `app/static/index.html`: added event review counts, recommendation status, selection checkboxes, batch approve/reject, merge and reclassify controls.
- `scripts/ui_static_check.py`: added new DOM/function/interaction contract markers.
- `scripts/ui_interaction_acceptance.py`: added synthetic browser check for event review queue rendering.
- `tests/test_system.py`: added event review regression for approve, reject, merge, reclassify and batch review note persistence.
- `docs/api-contracts.md`: documented event review endpoints and recommendation semantics.
- `tasks/todo.md`: added T-467 TODO and T-468 DONE.
- `docs/agent-handoffs/2026-06-26-T-468-company-event-review-workbench.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/api.py app/services.py tests/test_system.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
python3 - <<'PY'
from app.api import ApiRouter
from app.models import Issuer
from app.services import SystemService

svc = SystemService()
svc.store.issuers['issuer_001'] = Issuer(issuer_id='issuer_001', legal_name='Demo Inc')
router = ApiRouter(svc)
for eid in ['ce_smoke_a', 'ce_smoke_b']:
    svc.register_company_event({
        'event_id': eid,
        'issuer_id': 'issuer_001',
        'security_id': 'sec_001',
        'event_type': 'earnings_result',
        'title': 'Smoke event',
        'summary': 'Revenue increased.',
        'source_ids': ['src_sec'],
        'document_ids': ['doc_smoke'],
        'evidence_ids': ['ev_smoke'],
        'confidence': 0.78,
        'fact_status': 'verified',
        'review_status': 'needs_review',
        'metadata': {'classification_status': 'candidate_needs_review', 'source_layer': 'official_disclosure_text_classification'},
    })
listed = router.dispatch('GET', '/api/company-events', {'issuer_id': 'issuer_001', 'review_status': 'needs_review'}, role='analyst')
assert listed.success, listed.error
assert listed.data['candidate_count'] == 2, listed.data
assert 'review_recommendation' in listed.data['events'][0]
reviewed = router.dispatch('POST', '/api/company-database/events/review', {'event_ids': ['ce_smoke_a', 'ce_smoke_b'], 'action': 'reject', 'reason': 'smoke'}, role='analyst')
assert reviewed.success, reviewed.error
assert reviewed.data['reviewed_count'] == 2, reviewed.data
assert svc.store.company_events['ce_smoke_a'].review_status == 'rejected'
print('event batch review smoke passed')
PY
./.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_company_event_review_approves_reclassifies_merges_and_batches_candidates
```

Result:

- Passed: Python compile on touched Python files.
- Passed: UI static check, `required_ids=252`, `required_functions=87`, `interaction_markers=13`.
- Passed: direct event batch review smoke.
- Failed: targeted unittest did not reach the test because `PIL` is missing from the current `.venv`.

## Evidence

- Direct smoke proves event list enrichment, recommendation presence and batch reject behavior through `ApiRouter`.
- UI static check proves new controls, functions and interaction markers are present.
- `tests/test_system.py` contains focused regression coverage for event recommendation output, approve, reject, merge, reclassification and batch note persistence, but the local test environment must install `Pillow` test extra before the unittest command can execute.

## Decisions

- Event recommendations are review assist only; no event is auto-approved by score.
- `approve` does not rewrite `fact_status` unless the caller explicitly provides a new `fact_status`.
- `reclassify` records `metadata.event_type_history` and defaults to `review_status=approved`.
- Batch review uses a collection endpoint and applies one action/note to selected events.

## Risks and Open Questions

- Recommendation scoring is intentionally simple and should be calibrated with real event review outcomes.
- Material inbox UI remains the next data-source workflow gap.
- A broader company intelligence cycle runner is still needed to combine event review, report realization, workflow rebuild and paper-only feedback updates.

## Artifacts

- None. This task did not generate persistent runtime artifacts.

## Handoff Checklist

- [x] Event review API added.
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
2. T-469: Add retry/resume buttons for failed or partial company database build runs.
3. Add a company intelligence cycle runner that updates report realization, simulation feedback and workflow state after new data arrives.

## Next Recommended Action

Implement the material inbox UI next because it is the remaining visible data-source gap for getting official/IR/company materials into profile field assertions.
