# Handoff: T-607 Usage Origin Metrics

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/persistence_review`
- Branch/worktree: `main`, shared T-603 integration worktree
- Artifact classification: local-only
- Risk level: medium

## Objective

Separate real UI use from scheduled and acceptance traffic while preserving the existing local feature counters and storage/API compatibility.

## Scope

- In scope: origin header propagation, aggregate origin counts, trusted product-use count, legacy-record treatment, API contract, focused tests and primary local clients.
- Out of scope: user-level analytics, external telemetry, request-body capture, cookies/device fingerprints, non-local analytics services, broker or execution behavior.

## Background

The prior telemetry stored only one aggregate row per feature. Most of the 934 observed hits came from scripts and acceptance workflows, so the total could not answer whether the personal research product was actually being used.

## Problem Statement

Automation and UI requests were indistinguishable, and historical counts had no trustworthy origin. Reporting all hits as product use would overstate adoption.

## Expected Deliverables

- `ui|scheduled|acceptance|api` origin counters per feature.
- A product KPI that counts only explicit UI traffic.
- Backward-compatible hydration and API fields.
- Explicit headers on UI, daily/scheduled, and principal acceptance clients.

## Current State

- Completed: domain module, model additions, router/server propagation, UI/Streamlit and principal script headers, API contract, SQLite reopen regression, 12 focused tests, real local HTTP origin/performance probe, 516-test full local CI, schedule evidence review, and handoff validation.
- In progress: none.
- Not started: none required for T-607. More specific origin tags for low-frequency auxiliary clients remain an optional monitoring refinement.
- Blocked: none.

## Current Findings

- Existing persisted rows have no origin breakdown and therefore remain `unclassified`; they are not counted as product use.
- Browser automation is detected through `navigator.webdriver` and labeled `acceptance`, while normal `/ui` requests are labeled `ui`.
- Missing or invalid origin values normalize to `api`, which is visible but excluded from the trusted `product_hits` count.
- The real local origin gate passed: five acceptance-origin company-intelligence GETs increased `company_intelligence.hit_count` by 5, `origin_counts.acceptance` by 5 and `automation_hits` by 5 while `product_hit_delta` remained 0. The traffic changed automation telemetry only and did not change the product KPI.
- The same local app returned HTTP 200 for all 20 `/api/analysis/latest` samples; observed latency was median `44.5ms`, p95 `47.4ms` and maximum `48.3ms`.
- The local daily schedule audit reports `passed: true`, zero failures, latest pipeline execution status `passed`, and latest pipeline content status `ready`. This is local operational evidence only and makes no company-readiness-count claim.

## Proposed Work Plan

Status: completed.

1. Keep feature/path mapping and origin aggregation in `app/service_modules/usage_metrics.py`.
2. Keep `SystemService` as a best-effort compatibility facade.
3. Preserve the passed persistence and real HTTP gates and validate them through the full local CI and handoff gates.

## Validation Plan

Status: completed.

- `python -m unittest tests.test_usage_metrics`.
- SQLite reopen regression for additive model fields.
- Real local HTTP calls with each origin and response inspection.
- `make local-ci` and handoff validation under parent T-603.

## Dependencies

- Existing local `usage_metrics` record collection and HTTP request headers.

## Blockers

- None.

## Files Touched

- `app/models.py`: additive `origin_counts` and `last_origin` fields.
- `app/service_modules/usage_metrics.py`: feature mapping, origin normalization, aggregation and product KPI.
- `app/services.py`: thin compatibility facade.
- `app/api.py` / `app/server.py`: optional origin propagation.
- `app/static/index.html` / `app/dynamic_allocation/dashboard/api_client.py`: UI origin markers.
- `scripts/daily_data_update_pipeline.py`, `scripts/latest_analysis_run.py`, `scripts/personal_intelligence_refresh.py`: scheduled markers.
- `scripts/staging_acceptance.py`, `scripts/smoke_test.py`, `scripts/local_business_acceptance.py`, `scripts/local_backup_restore_drill.py`: acceptance markers.
- `tests/test_usage_metrics.py`: focused origin and legacy-count regressions.
- `docs/api-contracts.md`: additive request/response contract.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_usage_metrics
.venv/bin/python -m py_compile app/api.py app/models.py app/server.py app/services.py app/service_modules/usage_metrics.py
make local-ci PYTHON=.venv/bin/python
python3 scripts/check_handoffs.py
# Real local HTTP probe against http://127.0.0.1:8000:
# usage snapshot -> five acceptance-origin company GETs -> usage snapshot
# 20 timed GET samples for /api/analysis/latest
```

Result:

- Passed: 12/12 focused tests, including SQLite reopen and request-boundary persistence regressions; changed-file compilation passed.
- Passed: real HTTP origin gate. Five acceptance company GETs produced `company_intelligence.hit_count +5`, `acceptance +5`, `automation_hits +5` and `product_hit_delta 0`.
- Passed: `/api/analysis/latest` returned HTTP 200 for 20/20 samples; median `44.5ms`, p95 `47.4ms`, maximum `48.3ms`.
- Passed: full local CI, including 516/516 unit tests, and final handoff validation.
- Failed: none.
- Not run: no required T-607 checks. External staging and non-local production validation remain outside this local-only task.

## Evidence

- `artifacts/t612-post-promotion/usage-before-company-probes.json`: produced by the 2026-07-21 real HTTP probe against the local Compose app before the five acceptance requests; local-only, ignored, Product and UI owned, aggregate telemetry only, no request bodies or PII, not acceptable for non-local production release gates.
- `artifacts/t612-post-promotion/usage-after-company-probes.json`: produced by the same local probe after the five requests; local-only, ignored, Product and UI owned, aggregate telemetry only, no request bodies or PII, not acceptable for non-local production release gates.
- Before/after evidence records `company_intelligence` changing from 95 to 100 total hits and from 5 to 10 acceptance hits, while its product hit count remains 0; global product hits remain 1.
- `artifacts/daily-update-local/daily-update-schedule-audit-post-promotion.json`: generated at `2026-07-21T00:32:15.667412+00:00`; local-only daily scheduler evidence, Platform and Quality reviewed, no secrets, latest execution `passed` and content status `ready`, not acceptable for non-local production release gates.
- Focused test and latency command output is local-only session evidence, contains no secrets, and is not acceptable for non-local production release gates.

## Decisions

- `product_hits` counts only explicit UI traffic; generic API and historical unclassified hits remain visible but are not claimed as adoption.
- Store only aggregate counters and last route metadata. Do not collect bodies, identities, cookies or external analytics identifiers.
- Add fields to the JSON record payload; no relational schema migration is required.

## Risks and Open Questions

- Auxiliary scripts not yet tagged remain `api`, so automation totals are conservative rather than exhaustive.
- `navigator.webdriver` correctly handles the current browser acceptance path but is not a security boundary; this metric is operational, not billing or authorization evidence.
- The origin acceptance probe intentionally persists five telemetry events. They are classified as `acceptance`, excluded from product use, and must not be interpreted as natural user activity.
- Evidence under `artifacts/t612-post-promotion/` is ignored and local-only. It supports this machine's runtime gate but not external staging or production release claims.
- All portfolio and execution behavior remains paper-only, with no broker integration or automatic order execution.
- No unresolved blocker remains. Residual origin-distribution review is routine monitoring rather than incomplete implementation.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks completed: 12/12 focused tests, 516/516 full local CI tests, real HTTP origin/latency probes, and handoff validation passed
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated if roadmap state changed

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain placement: mapping, normalization, mutation and aggregation live in `app/service_modules/usage_metrics.py`; facade only bounds limits and suppresses telemetry failures.
- Focused regression: all 12 `tests.test_usage_metrics` tests pass and cover feature mapping, self-exclusion, failure exclusion, origin aggregation, legacy counts, SQLite reopen, request-boundary business persistence, telemetry failure isolation and commit-failure retry behavior; the full local CI also passes 516/516 tests.
- Contract/boundary changes: additive JSON fields and optional request header only; no relational schema, URL, UI workflow, paper-only or no-broker behavior changed.

## Next Steps

1. Monitor explicit `ui` product hits and automation-origin distribution during normal local use.
2. Review low-frequency generic `api` clients only if monitoring shows that more specific operational attribution would improve decisions.
3. Retain or expire ignored local evidence according to the local artifact retention policy; no further T-607 implementation is required.

## Next Recommended Action

Continue residual monitoring using only explicit `ui` hits as the PM product-use signal; keep scheduled and acceptance traffic excluded from product adoption.
