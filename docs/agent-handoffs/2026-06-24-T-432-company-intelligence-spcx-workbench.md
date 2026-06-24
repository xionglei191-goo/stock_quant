# Handoff: T-432 Company Intelligence SPCX Workbench

## Metadata

- Status: DONE
- Owner group: Product and UI
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-432, T-435, T-436
- Superseded by: `2026-06-24-T-432-company-intelligence-core-completion.md`

## Objective

Implement and verify the SPCX company intelligence slice: when a user enters `SPCX`, the system can aggregate local company profile data, facts, research results, and simulation feedback into the workbench.

## Scope

- Add or preserve `GET|POST /api/company-intelligence/{symbol}` as a read-only aggregation API.
- Display company intelligence in `/ui` with default symbol `SPCX`.
- Refresh the company intelligence view after the single-name research flow creates SPCX data.
- Add automated test and browser acceptance coverage for the SPCX path.
- Keep all simulation output paper-only with no broker execution.

## Background

The product direction changed from an organization/execution workflow to a company intelligence platform. The immediate acceptance target is practical: entering `SPCX` should show the stock's related local information and research outputs, not just a generic roadmap.

## Problem Statement

Before this slice, related objects existed across issuer/security, evidence, graph, research, and simulated ledger domains, but there was no single workbench contract proving that a stock-code lookup could aggregate those objects and render them in the UI.

## Expected Deliverables

- `SPCX` with no local data returns `status=not_found` plus `next_actions`.
- After running the single-name research flow, `SPCX` returns `status=available`.
- The response includes `company_profile`, `facts_and_events`, `relationships`, `research_results`, `simulation_feedback`, `data_quality`, and `section_counts`.
- UI shows profile counts, evidence/event counts, research rows, simulation rows, and raw aggregate JSON.
- Browser acceptance includes a check for the SPCX workbench flow.

## Current Findings

- `tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research` proves the API path before and after SPCX research.
- `scripts/ui_interaction_acceptance.py` now includes `company_intelligence_spcx_research_flow`.
- A clean in-memory server on `127.0.0.1:8765` passed browser click-through acceptance for this path.
- The existing service on port `8000` is a separate production-like instance and was not used as proof for current worktree behavior.

## Proposed Work Plan

1. Keep this record as the SPCX acceptance slice history.
2. Use `2026-06-24-T-432-company-intelligence-core-completion.md` as the current completion handoff for T-432 through T-436.
3. Future work should focus on deeper scoring algorithms and richer UI pages, not reopening the T-432/T-435/T-436 baseline.

## Validation Plan

- Run focused SPCX API test.
- Run full unit test suite.
- Run static UI check.
- Run browser UI interaction acceptance against a clean current-worktree server.
- Run py_compile, security check, and handoff validation.

## Risks

- The current company intelligence API still maps some legacy objects such as thesis, signal, decision intent, and simulated execution into the new workbench.
- The UI is a first working workbench slice, not the final information architecture for all company pages.
- The browser acceptance artifact is local-only and should not be treated as production release evidence.

## Dependencies

- Existing issuer/security, market data, document/evidence, research answer, thesis/signal, graph, and simulated ledger stores.
- Existing single-name research flow.
- Existing static `/ui` application.

## Blockers

- None for the SPCX acceptance slice.
- Superseded by the full T-432 through T-436 completion handoff.

## Handoff Checklist

- [x] API aggregation path verified.
- [x] UI path verified.
- [x] SPCX browser acceptance added.
- [x] Paper-only boundary verified.
- [x] Tests and checks recorded.

## Evidence

- `app/api.py`: routes `GET|POST /api/company-intelligence/{symbol}` to the service aggregation path.
- `app/services.py`: aggregates issuer/security, market data, documents/evidence, graph relationships, research results, and simulation feedback.
- `app/static/index.html`: company intelligence workbench defaults to `SPCX` and renders profile/fact/research/simulation sections.
- `tests/test_system.py`: SPCX before/after research test covers API output and paper-only boundary.
- `scripts/ui_interaction_acceptance.py`: `company_intelligence_spcx_research_flow` verifies the browser path.
- `artifacts/ui-interaction-acceptance-spcx/ui-interaction-acceptance.json`: local-only browser acceptance output, `status=passed`, `check_count=8`, `failure_count=0`.

Commands run:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_symbol_view_handles_spcx_before_and_after_research
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8765 --output-dir artifacts/ui-interaction-acceptance-spcx --timeout 60
```

Results:

- Passed: py_compile, focused SPCX test, full unit test suite (`210` tests), UI static check, security check, handoff validation, browser interaction acceptance.
- Failed: first browser acceptance attempt timed out on the new SPCX check because `_run_check` had a fixed 12 second wait; fixed by adding a per-check `wait_timeout`.
- Not run: `make local-ci` as a single command, because its component checks were run directly and browser acceptance was additionally run.

## Next Recommended Action

See `2026-06-24-T-432-company-intelligence-core-completion.md` for the full completion record. The next work should be new enhancement tasks for richer scoring, broader UI pages, and larger data-quality automation.
