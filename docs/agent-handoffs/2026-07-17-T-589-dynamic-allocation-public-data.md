# Handoff: T-589 Dynamic Allocation Public Data Integration

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Research and AI Workflows; Platform and Quality; Governance, Security, and Compliance
- Last updated: 2026-07-17
- Last agent: Codex `/root`
- Branch/worktree: shared current worktree
- Artifact classification: local-only

## Objective

Connect governed public data, derive all 38 configured series with explicit lineage and proxy disclosures, and produce a current paper-only decision visible through the API and Streamlit dashboard.

## Scope

- In scope: public clients, derivations, PIT metadata, quality gates, idempotent backfill CLI, tests, runtime evidence, and documentation.
- Out of scope: brokers, live execution, paid/unauthorized sources, and representing current-vintage backfills as historical PIT evidence.

## Background

T-581 through T-588 delivered the domain, models, API, dashboard, and paper ledger, but the controlled smoke observations were removed after acceptance. The live page therefore correctly showed 0/8 factors and no target allocation until governed inputs were connected.

## Problem Statement

The 38 internal series span market, macro, credit, liquidity, volatility, leverage, valuation, and breadth data. No commercial credentials are configured, and free sources do not provide historical Forward PE, proprietary ISM, or survivorship-safe breadth. The system needed a strict current-decision path without fabricating vintage history or silently neutral-filling missing fields.

## Expected Deliverables

- No-key FRED, Cboe, FINRA XLSX, and governed Yahoo EOD acquisition.
- All 38 internal series with formulas, upstream lineage, proxy flags, and current-vintage classification.
- Strict CLI, immutable same-day reruns, critical data-health decision gate, tests, docs, and a working local API/dashboard.

## Current Findings

- The strict run produced 11,902 observations across 38/38 series, 100% coverage, no missing/stale/source errors, and one current decision.
- Current paper state at 2026-07-17 15:30 UTC: `Late Cycle`, 50% equity, allocated SPY 35%, QQQ 15%, SGOV 50%.
- Same-day rerun produced 11,902 duplicates, zero inserts, and zero conflicts.
- Eight factor scores are valuation 5.84, trend 71.66, volatility 57.38, credit 74.33, leverage 5.51, macro 43.33, liquidity 52.48, and breadth 87.67.
- Kelly is explicitly unavailable because governed expected-return/volatility inputs were not supplied; the rule/regime cap binds at 50%.

## Proposed Work Plan

1. Run the strict CLI after US EOD and investigate any source/data-health failure instead of bypassing it.
2. Accumulate real paper decisions at the configured cadence.
3. Replace proxies only after a licensed historical-vintage source is governed and regression-tested.

## Validation Plan

- Run focused source/pipeline/application tests and the complete dynamic-allocation suite.
- Verify strict backfill and same-day idempotence against the local SQLite state.
- Verify current/data-health API payloads and desktop/mobile Streamlit rendering.
- Run `make local-ci PYTHON=.venv/bin/python` and handoff/security/document gates.

## Risks

- Forward PE, FCF Yield, proprietary ISM, literal DXY, and constituent breadth remain transparent proxies.
- Current-vintage FRED history is revised data and is not eligible for historical walk-forward evidence.
- Public endpoints can rate-limit. Same-day raw caching stabilizes reruns, and failures remain blocking and inspectable.
- FRED uses `curl` in this runtime because its Python HTTP/1.1 path timed out while libcurl/HTTP2 was reliable.

## Dependencies

- Python 3.11+, PyYAML, and the existing optional dashboard/analysis environment.
- Public FRED, Cboe, FINRA, and Yahoo endpoints; `curl` for FRED in this runtime.
- Local ignored paths `data/local/dynamic_allocation.sqlite` and `data/local/dynamic-allocation-cache/`.

## Blockers

- None for current local paper operation.
- Genuine historical-vintage backtests remain intentionally blocked until vintage-qualified data is available.

## Handoff Checklist

- [x] 38/38 series connected or explicitly proxied
- [x] Critical Data Health gates final allocation
- [x] PIT/rights/proxy lineage retained in decision snapshots
- [x] Same-day backfill idempotent with zero conflicts
- [x] API and desktop/mobile dashboard verified
- [x] Docs and roadmap updated
- [x] Paper-only/no-broker boundary preserved

## Evidence

- `.venv/bin/python scripts/backfill_dynamic_allocation_public_data.py --as-of 2026-07-17T15:30:00+00:00 --market-start 2000-01-01 --persist-decision --output /tmp/t589-public-data-run.json`: ready, 38 series, 11,902 inserts, no errors; local-only.
- Same command repeated: 11,902 duplicates, zero inserts/conflicts, decision `dap_0a04b364be01c927a6a65f3c`; local-only.
- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v`: 62 passed.
- `.venv/bin/python scripts/dynamic_allocation_dashboard_acceptance.py http://127.0.0.1:8502 --output-dir /tmp/t589-dashboard-acceptance --timeout 45`: desktop/mobile passed, 2 charts, 18 tables, zero exceptions/overflow; local-only.
- `.venv/bin/python scripts/security_check.py .`: 381 files, zero findings.
- First `make local-ci PYTHON=.venv/bin/python`: 412 tests passed and three completion audits failed only because T-589 was still DOING. Final rerun: 415 tests passed, followed by UI static, security, Markdown, 165-file handoff, and document metadata gates.
- `data/local/dynamic_allocation.sqlite`: 11,902 observations, 38 series, one decision; ignored local-only state, no secrets, not valid for non-local release or historical PIT proof.

## Next Recommended Action

Keep the local API at `http://127.0.0.1:55539` and Streamlit at `http://127.0.0.1:8502` for review, then schedule the strict backfill after market close when an operational scheduler is in scope.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain placement: all behavior is under `app/dynamic_allocation/` plus a thin CLI.
- Focused regression: source, pipeline, readiness, application/API, and dashboard tests protect the behavior.
- Contract/boundary changes: decision snapshots retain source URI/rights lineage; no storage schema, UI contract, broker, execution, or paper-only boundary changed.
