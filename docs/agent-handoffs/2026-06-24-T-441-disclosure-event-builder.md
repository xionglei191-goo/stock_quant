# Handoff: T-441 Disclosure Event Builder

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI, Governance / Security / Compliance
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-441

## Objective

Strengthen the company database fact layer by turning existing public disclosure events into first-class `CompanyEvent` timeline records.

## Scope

- In scope: extend company event builder, preserve document/evidence/source backlinks, focused test, API/todo/handoff documentation.
- Out of scope: external crawling, PDF/OCR extraction, fine-grained announcement parsing, relationship extraction, real trading.

## Background

T-438 created the first company event builder, but it only generated public market-data events and research-coverage attention events. The platform already had `DisclosureEvent` records, yet they were not materialized into the primary `CompanyEvent` timeline. That left the fact event layer thinner than the user's intended company database direction.

## Problem Statement

Company pages need a fact-first timeline. Research coverage can signal attention, but it cannot be the core event source. Existing official disclosure records must be promoted into the company event layer with evidence backlinks and verified fact status.

## Expected Deliverables

- `POST /api/company-database/events/build` supports `include_disclosures`.
- Existing `DisclosureEvent` records create `CompanyEvent(event_type=official_disclosure)`.
- Official disclosure events carry document, evidence and source backlinks.
- Research-coverage events remain `fact_status=opinion_signal`.
- Focused tests cover market, research and disclosure events together.

## Current Findings

- Added `include_disclosures` to `SystemService.build_company_events`, defaulting to true.
- Official disclosure events are created with `fact_status=verified`, `review_status=auto_generated`, confidence `0.95` and metadata back to the source disclosure event.
- Event builder rows now include `official_disclosure_event_count`.
- Updated API docs, todo and handoff index.

## Proposed Work Plan

1. Treat `DisclosureEvent` to `CompanyEvent` materialization as the minimum fact-event layer.
2. Add finer event extraction from filing sections and announcements in a later task.
3. Add human review and event taxonomy normalization before expanding to lawsuits, orders, product launches or policy impacts.

## Validation Plan

- Compile changed service and test files.
- Run the focused company event builder regression.
- Run adjacent company builder regressions.
- Restart local app and run event builder on sample companies if local disclosure data exists.
- Run handoff validation.

## Decisions

- Disclosure-derived events use `event_type=official_disclosure` instead of copying all filing-specific event types into the top-level taxonomy.
- The original disclosure `event_type`, `item_code`, `severity` and `disclosure_event_id` are preserved in tags/metadata.
- Research report coverage remains an opinion/attention signal and is not changed by this fact-layer enhancement.

## Risks and Open Questions

- The current event is one row per existing `DisclosureEvent`; it does not yet split filings into fine-grained business events.
- Some existing disclosure records may have sparse summaries, so UI display quality depends on upstream extraction.
- Local sample companies may have no new disclosure events to create if previous runs already generated or no disclosure records exist.

## Dependencies

- Existing `DisclosureEvent` model and store collection.
- Existing `CompanyEvent` model and company event builder endpoint.
- Existing company target resolution from T-437.

## Blockers

- None for this slice.

## Handoff Checklist

- [x] Disclosure event builder path added.
- [x] Official disclosure events use verified fact status.
- [x] Research coverage remains opinion signal.
- [x] Focused tests passed.
- [x] API contracts, todo and docs index updated.
- [x] Handoff validation passed.

## Evidence

Files changed:

- `app/services.py`: extended `build_company_events` with disclosure event materialization.
- `tests/test_system.py`: updated company event builder regression to cover official disclosure events.
- `docs/api-contracts.md`: documented `include_disclosures` and official disclosure event counts.
- `tasks/todo.md`: added T-441 completion entry.
- `docs/README.md`: updated task range through T-441.
- `docs/agent-handoffs/README.md`: added T-441 to related tasks.

Commands run:

```bash
python3 -m py_compile app/api.py app/services.py scripts/build_company_database_minimum.py tests/test_system.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events
python3 -m unittest tests.test_system.SystemServiceTests.test_company_workflow_builder_creates_observation_conclusion_and_paper_feedback tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_event_builder_creates_market_and_research_attention_events tests.test_system.SystemServiceTests.test_company_database_builder_materializes_profiles_and_binds_reports
python3 scripts/check_handoffs.py
```

Result:

- Passed: Python compile.
- Passed: focused company event builder test.
- Passed: focused workflow, relationship, event and company database builder test group.
- Passed: handoff validation.
- Not run: full `make local-ci`; this is a focused event-layer slice and the worktree already contains broad unrelated changes.

Artifacts:

- None required.

## Next Recommended Action

Implement fine-grained official disclosure event extraction from document/evidence text, then relationship extraction for customers, suppliers, subsidiaries, partnerships and major shareholders with review status and evidence confidence.
