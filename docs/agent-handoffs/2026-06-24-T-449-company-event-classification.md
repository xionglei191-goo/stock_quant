# Handoff: T-449 Company Event Classification

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows, Platform and Quality, Product and UI
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-449

## Objective

Strengthen the company event layer so official disclosures can produce finer `CompanyEvent` categories, not only coarse `official_disclosure` rows. This moves the system closer to a company intelligence database that can track financial results, management changes, litigation/regulatory matters, major orders/contracts, capacity/supply/demand changes and policy impacts.

## Scope

- In scope: `POST /api/company-database/events/build`, deterministic local rules over existing disclosure summaries, evidence text and non-research documents, tests, API contract, roadmap and handoff updates.
- Out of scope: external news crawling, commercial data feeds, LLM extraction, entity resolution, UI event filters, real broker integration and live trading.

## Background

Multi-agent review found that T-438 and T-441 already build market, research coverage and official disclosure events, but the event layer remained too coarse for the user's target company database. The highest-value next step is to classify existing official disclosure text into finer event types while preserving source and evidence backlinks.

## Problem Statement

The company database can show that a filing happened, but it does not yet expose what kind of investable or research-relevant company event the filing contains. Without finer event types, analysts still have to read raw disclosure text to identify earnings changes, management changes, litigation/regulatory issues, major contracts, supply-demand shifts or policy impacts.

## Expected Deliverables

- Add structured disclosure event extraction to `POST /api/company-database/events/build`.
- Preserve source/document/evidence backlinks and review boundaries on every generated detailed event.
- Keep research reports out of the fact classifier and retain them as opinion/attention events only.
- Add regression tests and update roadmap/API/handoff documentation.

## Current State

- Completed: `build_company_events` accepts `include_structured_disclosures`, defaulting to `true`.
- Completed: official disclosure summaries, disclosure evidence text and non-research document bodies can generate detailed event candidates.
- Completed: supported detailed event types are `earnings_result`, `management_change`, `litigation_regulatory`, `major_order_contract`, `capacity_supply_demand` and `policy_impact`.
- Completed: detailed events carry `source_layer=official_disclosure_text_classification`, `matched_terms`, `classification_rule`, document/evidence/source backlinks and `review_status=needs_review`.
- Completed: full local CI and handoff validation.
- Blocked: none.

## Current Findings

- `CompanyEvent` already has enough fields for this slice: `event_type`, source/document/evidence backlinks, confidence, fact status, review status and metadata.
- Disclosure events and evidence records already carry the public/official source context needed for deterministic local classification.
- The current company workbench can already display company events through the company intelligence aggregate; this backend slice does not require UI contract changes.

## Proposed Work Plan

1. Extend the existing event builder rather than adding a separate endpoint.
2. Keep the classifier deterministic, local and conservative.
3. Document that classification requires review even when source facts come from official disclosure.

## Validation Plan

- Run focused event builder tests.
- Compile changed Python files.
- Run handoff validation after documentation updates.
- Run full `make local-ci` before closeout if feasible.

## Files Touched

- `app/services.py`: added structured official disclosure event extraction and response counters.
- `tests/test_system.py`: added regression coverage for dry-run and execute paths.
- `docs/api-contracts.md`: documented `include_structured_disclosures`, supported event types and review boundary.
- `tasks/todo.md`: added T-449 roadmap entry.
- `docs/README.md`: updated company intelligence task range through T-449.
- `docs/agent-handoffs/README.md`: added T-449 to related tasks.
- `docs/agent-handoffs/2026-06-24-T-449-company-event-classification.md`: this handoff.

## Commands Run

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_event_builder_extracts_structured_disclosure_events
python3 -m py_compile app/services.py tests/test_system.py
python3 scripts/check_handoffs.py
make local-ci
```

Result:

- Passed: focused company event builder tests.
- Passed: compile for changed service and test files.
- Passed: handoff validation.
- Passed: full `make local-ci`, including compile, 224 tests, UI static check, security check and handoff validation.

## Decisions

- Detailed disclosure events use `fact_status=verified` because the source layer is official disclosure/evidence, but `review_status=needs_review` because the rule-based classification still needs analyst review.
- Research reports are excluded from the structured disclosure classifier. They continue to create only `research_coverage` events with `fact_status=opinion_signal`.
- Rules are deterministic and local; no external crawler or LLM call is introduced in this slice.

## Dependencies

- Existing `DisclosureEvent`, `Evidence`, `Document` and `CompanyEvent` data models.
- Existing `/api/company-database/events/build` route and company intelligence aggregate.
- Existing local/public data boundary: official disclosures are fact sources; research reports are opinion sources.

## Blockers

- None for this slice.

## Risks and Open Questions

- Keyword rules can over-classify broad disclosure text; event review UI filters and quality scoring are still pending.
- Duplicate control is deterministic per disclosure/event type, but richer event deduplication across filings remains future work.
- News, policy webpages and official company websites still need separate source-governed ingestion before they can become event sources.

## Artifacts

- None produced.

## Handoff Checklist

- [x] Structured disclosure extraction implemented.
- [x] Focused regression tests added.
- [x] API contract updated.
- [x] Todo and document indexes updated.
- [x] Full local validation completed.

## Evidence

Commands run:

```bash
python3 -m unittest tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_event_builder_extracts_structured_disclosure_events
python3 -m py_compile app/services.py tests/test_system.py
python3 scripts/check_handoffs.py
make local-ci
```

Result:

- Passed: focused event builder tests.
- Passed: Python compile for changed service and test files.
- Passed: handoff validation.
- Passed: full `make local-ci`, including compile, 224 tests, UI static check, security check and handoff validation.

## Next Steps

1. Follow up with UI empty-state guidance and company event filters.
2. Add run history and resumability for company database batch builds.
3. Extend official/non-research sources beyond filings after source governance is in place.

## Next Recommended Action

Continue with the UI empty-state guidance identified by the Product/UI explorer so unknown symbols and sparse companies show explicit next actions instead of empty tables.
