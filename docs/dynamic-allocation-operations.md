# Dynamic Allocation Longitudinal Paper Operations

- Status: active
- Owner group: Research and AI Workflows
- Last updated: 2026-07-18
- Related tasks: T-588, T-589, T-590, T-591, T-598
- Scope: Local-only daily evidence retention, monthly operational aggregation, forward paper NAV, and 3/6/12 month review gates
- Non-goals: Broker connectivity, order execution, investment advice, fabricated elapsed evidence, or non-local release evidence

## Purpose

Turn the required 6-12 month paper observation period into a measurable operating process. The process records whether governed decisions ran, whether strict data gates passed, and whether the append-only ledger remains valid. It does not infer investment performance from operational health.

## Facts

- `scripts/dynamic_allocation_daily_run.py` remains read-only unless `--execute`, `--ledger`, and `--output` are all supplied.
- Optional `--history-dir` archives one report per UTC as-of timestamp. A strict failure writes a boundary-labelled failure report with missing series, failing source names, insert-conflict count, and decision readiness; raw provider error messages are not copied.
- `scripts/dynamic_allocation_operations_report.py` replays and validates the JSONL hash chain, reads archived daily reports, and aggregates monthly run and data-health status.
- Every report is `local-only`, is unacceptable for a non-local release gate, and fixes `paper_only=true`, `live_execution_allowed=false`, `broker_connected=false`, and `order_execution_allowed=false`.

## Review Gates

The report exposes 3, 6, and 12 calendar-month gates. Each gate requires both elapsed calendar time and at least the same number of distinct observed calendar months.

- `awaiting_elapsed_time`: the calendar threshold has not elapsed.
- `insufficient_monthly_coverage`: time elapsed but operational evidence does not cover enough distinct months.
- `operational_review_due`: time and operational coverage permit a review.

Without governed performance input, all gate records keep `efficacy_proven=false`. A gate progresses through elapsed time, operational month coverage, performance coverage, and human review. `human_review_required` means the automated evidence package is ready for a person; it is not an efficacy conclusion. Only a completed, non-premature review with outcome `effective` can set that gate to `efficacy_proven=true`. `not_effective` and `inconclusive` remain false. TLT/GLD expansion remains outside this calculation.

## Paper NAV And Performance Contract

The input schema is `dynamic-allocation-paper-performance/v1`; the calculation methodology is `paper-nav-next-session-adjusted-close/v1`. `app/dynamic_allocation/performance.py` validates and calculates the package. This is forward-observed paper evidence only, not a historical backtest.

Required top-level fields:

- All local paper boundary fields must match the daily report: `classification=local-only`, `acceptable_for_non_local_release_gate=false`, `paper_only=true`, and all broker/live/order flags false.
- `collection_started_at` must be timezone-aware, must not be in the future, and must be within seven days before the first paper decision. No session availability may predate it.
- `initial_nav`, `transaction_cost_bps`, and `annual_advisory_fee_bps` are explicit finite assumptions. The default methodology uses NAV 1.0, 5 bps turnover cost, and zero advisory fee.
- `calendar` requires a calendar ID, version, source ID/URI, and availability timestamp.
- `sessions` must be unique and ascending. Every weekday in the declared range must appear as `open` or `closed`; a closed holiday is explicit rather than inferred.
- Every open session needs a timezone-aware close/availability time and adjusted-close evidence for `SPY`, `QQQ`, and `SGOV`. Each price needs an observation ID, source ID/URI, and rights with `automated_use_allowed=true` and `paper_performance_eligible=true`.

Calculation rules:

- A decision can earn a return only when it was available by the prior complete common session. A decision made later cannot earn any part of that already-started interval.
- SPY, QQQ, and SGOV adjusted-close returns include distributions and embedded ETF expenses. SGOV is the cash return; missing cash is never replaced with zero.
- Rebalance turnover is `0.5 * sum(abs(new_weight - old_weight))`, starting from 100% SGOV. Transaction cost is turnover times configured bps. Advisory fees, if nonzero, accrue at annual bps divided by 252. ETF expenses are not deducted twice.
- Benchmarks are aligned to the same evaluated intervals: SPY buy-and-hold and 60% SPY / 40% SGOV.
- Missing weekdays, incomplete open sessions, unavailable/future sessions, or intervals without a prior eligible signal block `performance_evidence_ready`. No return crosses an incomplete open session.
- Every NAV point carries signal run ID, allocation, gross/net return, turnover, fees, drawdown, aligned benchmark returns, and both endpoint price observation IDs.

Human review records are keyed to the 3, 6, or 12 month gate. `status` is `not_started`, `pending`, or `completed`. Completed records require `outcome` (`effective`, `not_effective`, or `inconclusive`), reviewer, reviewed timestamp, and rationale. A completed review before its gate date is rejected.

## Commands

Read-only current status:

```bash
python3 scripts/dynamic_allocation_operations_report.py \
  --ledger data/local/dynamic-allocation-paper.jsonl \
  --daily-report artifacts/dynamic-allocation/daily-run-latest.json \
  --daily-reports artifacts/dynamic-allocation/daily-history \
  --performance-input /absolute/path/to/forward-paper-performance.json
```

Explicit local-only report write:

```bash
python3 scripts/dynamic_allocation_operations_report.py \
  --ledger data/local/dynamic-allocation-paper.jsonl \
  --daily-report artifacts/dynamic-allocation/daily-run-latest.json \
  --daily-reports artifacts/dynamic-allocation/daily-history \
  --as-of 2026-07-18T00:00:00+08:00 \
  --execute \
  --output artifacts/dynamic-allocation/operations-latest.json
```

Render, but do not install, the scheduler units:

```bash
python3 scripts/dynamic_allocation_scheduler_template.py \
  --project-root /absolute/path/to/sotck_quant \
  --python /absolute/path/to/python \
  --state-dir /absolute/path/to/sotck_quant/data/local \
  --artifact-dir /absolute/path/to/sotck_quant/artifacts/dynamic-allocation
```

The scheduler renderer requires absolute paths. Its default action only prints a user-level service and timer. `--execute --install-dir /absolute/path` writes the two unit files but deliberately does not call `systemctl`, enable the timer, or start it. The generated service uses `NoNewPrivileges=true`, `PrivateTmp=true`, and `UMask=0077`.

## Decisions

- Daily success and daily failure artifacts share the same boundary contract so missing runs are visible instead of silently omitted.
- Calendar gates measure readiness to review, not outcome quality.
- Performance calculation uses only explicit forward paper session evidence and next-session signal timing; current-vintage factor history is not accepted as historical walk-forward efficacy.
- Scheduler enablement remains a manual operator action because scheduling changes external user-session state.

## Assumptions

- The operator chooses a schedule after the required public data sources are expected to be available.
- The ledger and archived reports remain on a trusted local filesystem; neither is production-grade evidence.

## Open Questions

- Choose and govern the actual market-calendar and adjusted-close collectors before operational performance accumulation begins.
- Decide the minimum expected weekday-run coverage and an alert destination only after observing local scheduler reliability.

## Artifacts

- `data/local/dynamic-allocation-paper.jsonl`: produced by the explicit daily execute command; append-only local paper ledger; sensitive data is not expected; not acceptable for non-local production release gates.
- `artifacts/dynamic-allocation/daily-history/*.json`: produced by `--history-dir`; local-only daily success/failure evidence; sensitive data is not expected; not acceptable for non-local production release gates.
- `artifacts/dynamic-allocation/operations-latest.json`: optionally produced by the explicit operations report write command; local-only aggregation; sensitive data is not expected; not acceptable for non-local production release gates.
- `/absolute/path/to/forward-paper-performance.json`: operator-provided, versioned forward-session evidence input; local-only; source URIs and rights must be reviewed for sensitivity; not acceptable for non-local production release gates.
