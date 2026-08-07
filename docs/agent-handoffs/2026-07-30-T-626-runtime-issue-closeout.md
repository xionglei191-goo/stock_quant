# Handoff: T-626 Runtime Issue Closeout

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows; Data and Evidence; Product and UI; PM / Release Coordination
- Last updated: 2026-07-30
- Last agent: Codex
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Keep the dynamic-allocation domain current through the scheduled local pipeline and ensure the default daily research mainline always preserves time for queue generation while producing useful LLM diligence.

## Scope

- In scope: daily-mainline timeout allocation and defaults, dynamic public-source refresh atomicity and immutable revisions, daily scheduler wiring, persistent cache placement, focused tests, live runtime and browser evidence, contracts, roadmap, and this handoff.
- Out of scope: factor formulas, asset universe or allocation policy, data-rights expansion, broker connectivity, automatic orders, external release evidence, and unrelated blocked organizational-release tasks.

## Background

T-620 delivered the daily research mainline and T-625 made the Streamlit dashboard persistently reachable. Live follow-up exposed two governed-data problems: the latest daily mainline could exhaust its total budget before queue generation, and the dynamic decision remained stale at 4/8 factors because the scheduled daily pipeline did not refresh that domain.

## Problem Statement

The mainline reserved non-LLM time only for candidates selected for model diligence even though all candidates require context reads, leaving no final queue budget in a 20-candidate run. Dynamic refresh was absent from the scheduler, depended on a missing container `curl`, used FRED request variants that hung on the current route, wrote partial source results before a strict failure, treated same-vintage upstream revisions as permanent conflicts, and stored its response cache outside the durable Compose volume.

## Expected Deliverables

- Default 20-candidate daily runs complete queue generation inside 600 seconds and receive successful model diligence.
- Scheduled strict dynamic refresh produces 38/38 fresh series and an 8/8-factor paper decision without partial-batch poisoning.
- Same-vintage upstream changes append immutable revisions.
- Runtime UI and APIs remain healthy, paper-only, broker-disconnected, and browser-accessible.
- Focused and complete repository gates pass with current documentation.

## Current State

- Completed: daily-mainline reserve calculation now accounts for context work on all remaining candidates.
- Completed: default automatic diligence was revised from 8 to 4 while preserving all 20 queue candidates.
- Completed: strict dynamic collection, FRED compatibility, immutable revision append, scheduled execution, durable cache path, and focused tests.
- Completed: strict source/conflict gates run before decision evaluation, so a failed refresh cannot persist a new decision from stale data or append the paper ledger.
- Completed: live strict dynamic refresh reached 38/38 fresh series and 8/8 ready factors.
- Completed: live default mainline `dmrun_3c05122968a7` completed in 439.9932 seconds with 4/4 LLM successes and 20/20 queue items.
- Completed: desktop/mobile dynamic Dashboard acceptance and manual screenshot inspection.
- Completed: final complete local CI, runtime health/API/redirect/timer checks, handoff validation, and diff check.
- In progress: none.
- Not started: none.
- Blocked: none.

## Current Findings

- The old mainline run `dmrun_320cf95baebd` selected 20 candidates but skipped `build_daily_queue` with `timeout_budget_exceeded`.
- An intermediate 8-diligence regression run proved queue preservation but all eight calls received only about 36-46 seconds and fell back on timeout.
- The revised default gives four calls enough useful time; all four succeeded in the live run while the final queue stage passed.
- The strict dynamic run completed 38/38 configured and fresh series, 8/8 ready factors, 4,068 inserted observations, 12,442 idempotent duplicates, zero conflicts, and a ready paper decision.
- `partial` remains the expected mainline aggregate status when candidates beyond the configured diligence limit are explicitly retained with `diligence_budget_exhausted`; it is not a stage failure.

## Proposed Work Plan

1. Preserve the production-validated defaults and strict scheduled refresh behavior.
2. Track the unrelated stateful full-UI acceptance isolation gap separately from T-626.

## Validation Plan

- Run daily-mainline configuration, facade, property, dynamic provider/repository/pipeline/runtime, scheduler wiring, static UI, and security regressions.
- Run strict public refresh and a real default daily-mainline request against the Compose stack.
- Inspect dynamic current/data-health APIs, queue/runs APIs, redirect, container health, and desktop/mobile screenshots.
- Run `make PYTHON=.venv/bin/python local-ci`, handoff validation, shell syntax, Compose parsing, and diff checks.

## Dependencies

- Existing local Compose PostgreSQL/S3/OpenSearch stack and dynamic-allocation SQLite domain repository.
- Public FRED, Cboe, FINRA, and governed Yahoo EOD endpoints.
- Configured local LLM gateway.

## Blockers

- None.

## Files Touched

- `app/service_modules/daily_mainline.py`: reserve context cost for all candidates and set the production-validated default diligence limit.
- `app/services.py`: pass the remaining candidate count into the domain timeout allocator; no new business logic.
- `app/dynamic_allocation/data/public_sources.py`: support container urllib fallback and route-compatible FRED requests.
- `app/dynamic_allocation/data/public_pipeline.py`: collect and validate strict source batches before persistence.
- `app/dynamic_allocation/data/repository.py`: append immutable same-vintage revisions without changing schema.
- `scripts/dynamic_allocation_daily_run.py`: use strict ingestion for the governed daily run.
- `tests/dynamic_allocation/test_daily_run.py`: prove a failed strict source batch never reaches decision evaluation.
- `scripts/daily_data_update_pipeline.py`, `scripts/run_daily_data_update.sh`: schedule strict dynamic refresh and summarize its result.
- `docker-compose.yml`, `.env.example`: use a durable cache path and document scheduler/mainline configuration.
- `tests/test_daily_mainline.py`, `tests/dynamic_allocation/test_providers.py`, `tests/dynamic_allocation/test_public_data_pipeline.py`, `tests/test_system.py`: protect the corrected behaviors.
- `README.md`, `docs/api-contracts.md`, `docs/production-runbook.md`, `docs/user-manual.md`, `.kiro/specs/project-usability-improvement/`, `tasks/todo.md`: reconcile implementation, operations, defaults, and roadmap.

## Commands Run

```bash
.venv/bin/python -m unittest \
  tests.test_daily_mainline.ResolveConfigTests \
  tests.test_daily_mainline.DailyMainlineFacadeIntegrationTests \
  tests.test_daily_mainline_properties -v
.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v
docker compose up -d --force-recreate ai-quant-org
curl -X POST http://127.0.0.1:8000/api/daily-mainline/run \
  -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":600,"candidate_limit":20,"market_quota":10}'
docker compose exec -T ai-quant-org python \
  scripts/dynamic_allocation_daily_run.py \
  --as-of 2026-07-30T04:52:41+00:00 \
  --market-start 2000-01-01 \
  --execute \
  --ledger /data/local/dynamic-allocation-paper.jsonl \
  --output artifacts/dynamic-allocation/daily-run-latest.json \
  --history-dir artifacts/dynamic-allocation/daily-history
.venv/bin/python scripts/dynamic_allocation_dashboard_acceptance.py \
  http://127.0.0.1:8501 \
  --output-dir artifacts/t626-runtime-closeout \
  --timeout 45
.venv/bin/python scripts/ui_interaction_acceptance.py \
  http://127.0.0.1:8000 \
  --output-dir artifacts/t626-runtime-closeout/ui-interaction \
  --timeout 30
make PYTHON=.venv/bin/python local-ci
```

Result:

- Passed: 91 daily-mainline tests/properties and 90 dynamic-allocation tests.
- Passed: scheduler/runbook focused regressions, shell syntax, Compose parsing, static UI/module checks, handoff validation, and diff check.
- Passed: live default run `dmrun_3c05122968a7`, 439.9932 seconds, 4/4 LLM successes, 20/20 queue items, final queue stage passed.
- Passed: final live strict dynamic refresh in 12.862 seconds, 38/38 fresh series, 8/8 ready factors, 16,510 idempotent duplicates, zero conflicts, ready paper decision, and ledger append.
- Passed: dynamic Dashboard desktop 1440x1000 and mobile 390x844, 19 tables, 2 Plotly charts, allocation and paper-only boundary visible, no browser exception or horizontal overflow; screenshots were manually inspected.
- Passed: final `make PYTHON=.venv/bin/python local-ci`; all 787 tests, static UI, security scan over 559 files, 264-document Markdown link validation, 205-document handoff validation, and canonical document metadata validation.
- Passed: API reports 8/8 ready factors, 100% data coverage, no missing/stale series, 30% target equity, and fixed paper-only/no-broker boundaries; both containers are healthy, redirect is correct, the previous daily service result is success, and the timer is active.
- Failed then fixed: missing `curl`, hanging FRED request variants, partial strict writes, same-vintage conflicts, and the ineffective 8-call default.
- Failed outside T-626 scope: the 55-check stateful full-UI interaction suite passed the T-626-relevant daily-mainline failure-stage/reason check but failed 28 unrelated company-intelligence/graph/market assertions against the reused production-like database. An isolated SQLite/local-adapter rerun passed 53/55, proving the production run mostly failed because persistent acceptance records violated clean-state assumptions and timed-out async requests then serialized behind the main dispatch lock. The two repeatable unrelated failures are `company_ownership_approved_same_holder_network_context` and `company_graph_inspector_neighbor_shows_relationship_label`.
- Not run: none for the T-626 acceptance surface.

## Decisions

- Preserve a 20-item research queue but default model diligence to the first four candidates. This balances breadth with the measured local gateway latency rather than silently reducing the queue.
- Include non-LLM context cost for every remaining candidate in the fair-share timeout calculation because context assembly is performed for all candidates.
- Make scheduled dynamic refresh strict by default. A source outage must not leave a partially written same-day vintage that blocks a later complete retry.
- Run source and conflict gates before decision evaluation so a failed refresh cannot create a stale decision record.
- Append changed same-vintage values as immutable revisions. Exact repeats remain idempotent and existing observations are never overwritten.

## Risks and Open Questions

- External public sources and the LLM gateway can still be slow or unavailable. Failures remain explicit and retryable; the scheduler does not fabricate data.
- Dynamic immutable-revision support is implemented on the SQLite domain repository used by `DynamicAllocationApplication`; it does not change generic state-store behavior.
- A normal 20-candidate run is intentionally `partial` when only four candidates receive automatic diligence; UI and operators should judge the stage list and queue count rather than treating every `partial` as failure.
- The broad `ui_interaction_acceptance.py` suite is not isolated from persistent production-like fixture state and can cascade timeouts after its first slow unrelated request. An isolated rerun reached 53/55; the remaining same-holder context and shareholder-label graph assertions need a separate Product and UI task. T-626's relevant DOM assertion and dynamic browser acceptance passed.

## Evidence

- `artifacts/dynamic-allocation/daily-run-latest.json`: produced by strict `dynamic_allocation_daily_run.py --execute`; local Compose; 2026-07-30; Platform and Quality; no secrets; local-only; not eligible for non-local release.
- `artifacts/dynamic-allocation/daily-history/`: immutable local history from the same producer and boundary.
- `data/local/dynamic-allocation-paper.jsonl`: hash-chained paper ledger; local Compose; contains no broker execution; local-only.
- `artifacts/daily-mainline/`: per-run local-only mainline artifacts including `dmrun_3c05122968a7`; may contain derived research summaries but no credentials or complete upstream model responses; not eligible for non-local release.
- `artifacts/t626-runtime-closeout/dashboard-desktop.png`: generated by `dynamic_allocation_dashboard_acceptance.py`; local Compose; 2026-07-30; 1440x1000 rendered state; no secrets; local-only; not eligible for non-local release.
- `artifacts/t626-runtime-closeout/dashboard-mobile.png`: same producer and classification; 390x844 rendered state.
- `artifacts/t626-runtime-closeout/ui-interaction/ui-interaction-acceptance.json`: stateful full-UI diagnostic; local-only; relevant daily-mainline DOM check passed but overall status failed on unrelated persistent-state assertions; not release evidence.
- `artifacts/t626-runtime-closeout/ui-interaction-isolated/ui-interaction-acceptance.json`: isolated SQLite/local-adapter diagnostic; local-only; 53/55 passed, with two unrelated shareholder-graph failures; not release evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no. `app/services.py` only forwards the number of remaining candidates to a domain budget function.
- Domain placement: budget arithmetic remains in `app/service_modules/daily_mainline.py`; public-source ingestion and revision rules remain in `app/dynamic_allocation/data/`.
- Focused regression: `DailyMainlineFacadeIntegrationTests.test_run_reserves_total_budget_for_queue_stage` covers 20 candidates, eight simulated diligence attempts, bounded timeout allocation, and a passed final queue.
- Contract/boundary changes: no API response schema, generic storage schema, or UI action change. The default diligence value and dynamic revision persistence behavior changed; paper-only, no-broker, and no-automatic-order boundaries are unchanged.

## Handoff Checklist

- [x] Code changes completed
- [x] Focused tests and live workflows passed
- [x] Docs and contracts updated
- [x] T-626 browser acceptance passed
- [x] Complete local CI passed
- [x] `tasks/todo.md` status updated to DONE
- [x] No unrelated dirty-worktree changes reverted

## Next Steps

1. Let the active user timer run the strict dynamic refresh during normal daily operations.
2. Treat `partial` plus `build_daily_queue=passed` and a full queue as the normal default-mainline outcome when the four-item diligence cap is reached.
3. Create a separate Product and UI task for full-suite state isolation and the two repeatable shareholder-graph assertions before using it as a repeatable full-product release gate.

## Next Recommended Action

Continue normal operation from `/ui` and `/dynamic-allocation`; both T-626 runtime paths are healthy and current.
