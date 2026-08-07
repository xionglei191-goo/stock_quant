# Handoff: T-627 Shareholder Graph UI Closeout

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; Data and Evidence; PM / Release Coordination
- Last updated: 2026-07-30
- Last agent: Codex
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Make the company shareholder network and graph inspector semantically correct, and make the full UI interaction suite repeatable without writing acceptance fixtures into the long-lived application state.

## Scope

- In scope: approved shareholder network read-model deduplication, graph relationship labels, isolated UI acceptance startup and cleanup, focused regressions, contract docs, roadmap, and this handoff.
- Out of scope: deleting or merging stored relationship facts, changing review or rights policy, external data collection, broker connectivity, automatic orders, and non-local release evidence.

## Background

T-626 closed the dynamic-allocation and daily-mainline runtime issues. Its broad browser follow-up passed 53/55 checks on a temporary SQLite service and isolated two repeatable Product and UI failures: duplicate same-holder facts inflated the related-company count, and a generic graph edge type hid the business relationship label in the neighbor inspector.

## Problem Statement

The relationship context deduplicated approved same-holder peers by `relationship_id`, even though the UI metric counts related companies. Equivalent approved records from ownership import and explicit registration therefore counted the same company twice. The graph model retained `relationship_type` in edge metadata, but inspector, path, trace, and canvas labels read the generic edge type first and rendered only “关系”.

The browser suite also required callers to launch and clean up a temporary service manually, so running it against the default URL could write fixtures to a persistent database.

## Expected Deliverables

- Unique same-holder company counts independent of duplicate fact IDs, with all underlying facts still queryable.
- Business relationship labels in graph neighbor, path, inspector, trace, and canvas views.
- One-command isolated 55-check browser acceptance that removes temporary state and never touches the long-lived PostgreSQL/object store.
- Focused and complete repository gates plus current docs and roadmap.

## Current State

- Completed: approved shareholder related-company rows now deduplicate by `related_issuer_id + holder_key`.
- Completed: graph link labels resolve `meta.relationship_type` before generic edge types.
- Completed: `scripts/ui_interaction_acceptance.py --isolated` launches temporary SQLite/local adapters and cleans them up.
- Completed: focused backend, isolated-environment, UI static, and 55/55 browser checks.
- Completed: complete local CI, handoff validation, roadmap closeout, targeted runtime restart, and production read verification.
- In progress: none.
- Not started: none.
- Blocked: none.

## Current Findings

- Ownership manifest import and later explicit fixture registration can legitimately create distinct approved facts for the same issuer and holder. Those facts must remain auditable, while the company-network summary must count one peer.
- `makeGraphModel` already preserves the raw edge object in `link.meta`; the display bug was caused by consumers calling `graphEdgeLabel(link.type, link.label)` and prioritizing `HAS_COMPANY_RELATIONSHIP`.
- The isolated acceptance result records `production_state_touched=false` and `temporary_state_removed=true`.

## Proposed Work Plan

1. Preserve the corrected read-model and graph-label behavior with focused tests.
2. Finish full repository gates and mark T-627 done only after they pass.

## Validation Plan

- Run the approved same-holder duplicate regression and isolated environment regression.
- Run UI static validation and all 55 real browser interactions with `--isolated`.
- Run complete local CI, handoff validation, and diff checks.

## Dependencies

- Local Chrome/Chromium and the repository `.venv`.

## Blockers

- None.

## Files Touched

- `app/service_modules/company_intelligence.py`: deduplicate the derived company network by peer issuer and holder key.
- `app/static/index.html`: resolve visible graph link labels from business relationship metadata.
- `scripts/ui_interaction_acceptance.py`: add temporary SQLite/local-adapter service lifecycle and cleanup.
- `scripts/ui_static_check.py`: protect the graph link-label helper contract.
- `tests/test_system.py`: cover duplicate fact preservation, unique network count, graph UI contract, and isolated environment.
- `README.md`: make isolated UI acceptance the default documented command.
- `docs/api-contracts.md`: document derived-network deduplication versus raw fact preservation.
- `.kiro/specs/project-usability-improvement/tasks.md`: record completed runtime and full-UI follow-up verification.
- `tasks/todo.md`: track T-627 status and acceptance.

## Commands Run

```bash
.venv/bin/python -m unittest \
  tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies \
  tests.test_system.SystemServiceTests.test_ui_interaction_isolated_server_env_uses_temporary_local_adapters \
  tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture -v
.venv/bin/python scripts/ui_static_check.py
.venv/bin/python scripts/ui_interaction_acceptance.py \
  --isolated \
  --output-dir artifacts/t627-shareholder-graph-ui \
  --timeout 45
make PYTHON=.venv/bin/python local-ci
docker compose restart ai-quant-org
curl -fsS -H 'X-Role: analyst' \
  'http://127.0.0.1:8000/api/company-intelligence/SPCX?limit=50'
```

Result:

- Passed: three focused tests and UI static validation.
- Passed: 55/55 isolated real browser checks, including both former failures.
- Passed: temporary state removed; persistent production state not touched.
- Passed: complete `local-ci`; 788 tests, UI static, security scan over 559 files, 265-document Markdown link validation, 206-document handoff validation, and canonical document metadata validation.
- Passed: targeted `ai-quant-org` restart without database or external-adapter reset; main API and dynamic Dashboard are healthy.
- Passed: production SPCX read reports one approved related-company row and one unique `related_issuer_id + holder_key`, with PostgreSQL/S3/OpenSearch still active.
- Failed: one mistyped direct unittest selector referenced a nonexistent method; the three real tests in the same command passed and the product was unaffected.
- Not run: none.

## Evidence

- `artifacts/t627-shareholder-graph-ui/ui-interaction-acceptance.json`: produced by `scripts/ui_interaction_acceptance.py --isolated`; 2026-07-30; local temporary SQLite/local adapters; Product and UI; no credentials or complete model responses; local-only and not eligible for non-local release.
- `http://127.0.0.1:8000/api/company-intelligence/SPCX`: post-restart production-like local read check; 2026-07-30; PostgreSQL/S3/OpenSearch; no artifact persisted; local-only and not eligible for non-local release.

## Decisions

- Deduplicate only the derived related-company network, not stored facts or graph query results, because the former is a company count while the latter are audit records.
- Use edge `relationship_type` metadata as the display source and retain the generic edge type for graph structure.
- Make isolation opt-in at the script level but the default documented command, preserving explicit runtime-instance testing by URL.

## Risks and Open Questions

- Full browser acceptance still exercises local fixture writes by design; callers who omit `--isolated` are explicitly choosing to test and mutate the target runtime.
- Equivalent relationship facts remain visible in raw graph queries, as required for provenance and audit.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated if roadmap state changed

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; `app/services.py` was not changed by T-627.
- Domain placement: network aggregation remains in `app/service_modules/company_intelligence.py`; UI-only labeling remains in `app/static/index.html`.
- Focused regression: `test_relationship_context_links_approved_same_shareholder_companies` now proves duplicate stored facts produce one derived peer while graph queries retain every fact.
- Contract/boundary changes: the derived network count semantics and graph display changed; no API schema, storage schema, review policy, rights boundary, UI action, paper-only rule, or no-broker boundary changed.

## Next Steps

1. Use `scripts/ui_interaction_acceptance.py --isolated` for repeatable full-product browser checks.
2. Continue the roadmap with the five-company official-fact gaps and company-intelligence feedback loop.

## Next Recommended Action

Continue normal product work; the repeatable full-product browser acceptance gate is now green.
