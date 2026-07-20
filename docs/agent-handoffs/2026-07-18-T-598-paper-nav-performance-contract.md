# Handoff: T-598 Paper NAV And Performance Review Contract

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Data and Evidence; Governance, Security, and Compliance; Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex `/root/t591_paper_ops`
- Branch/worktree: shared current worktree
- Artifact classification: local-only contract; no new performance evidence generated

## Objective

Define and implement the auditable forward paper NAV and performance evidence contract required before the first T-591 gate, including benchmarks, drawdown, turnover, fees, signal timing, price lineage, missing-session handling, and governed review decisions.

## Scope

- In scope: versioned forward paper methodology, explicit session/price/calendar evidence validation, NAV and benchmark calculation, longitudinal gate integration, read-only CLI input, tests, and operating documentation.
- Out of scope: roadmap/risk/index edits owned by the parent PM agent, price collection automation, historical backfill, current efficacy claims, asset-universe expansion, broker connectivity, and order execution.

## Background

T-591 made daily operational continuity and 3/6/12 month elapsed gates measurable, but deliberately left performance unavailable. The current ledger has one decision and cannot support a financial conclusion. A contract was needed before future forward observations accumulate, otherwise price timing, missing days, cash treatment, and review outcomes could drift.

## Problem Statement

Operational success does not establish strategy efficacy. A credible review requires price and market-calendar lineage, strict next-period signal application, common-session handling, explicit fees and turnover, aligned benchmarks, and a human conclusion only after the relevant gate. Current-vintage factor history marked unsuitable for backtests must not be repurposed as historical efficacy evidence.

## Expected Deliverables

- A versioned `dynamic-allocation-paper-performance/v1` input and output contract.
- A deterministic `paper-nav-next-session-adjusted-close/v1` calculation.
- Per-interval NAV, drawdown, turnover, fee, benchmark, decision, and price-observation lineage.
- Gate logic requiring elapsed time, operational coverage, performance coverage, and valid human review.
- Focused/full domain tests, documentation, security check, and handoff.

## Current Findings

- Current real state remains one valid ledger record and one completed daily report; no performance input exists.
- The read-only current report returns `performance_evidence=null`, `performance_evidence_ready=false`, `status=not_proven`, and all three gates `awaiting_elapsed_time` with `efficacy_proven=false`.
- The first 3-month gate is due at `2026-10-17T16:15:00Z`; code rejects any completed review before its due date.

## Proposed Work Plan

1. Begin governed forward calendar and adjusted-close capture without historical efficacy backfill.
2. Run the read-only longitudinal report with the explicit performance input and resolve every missing weekday/open-session gap.
3. At each due gate, have a named person record `effective`, `not_effective`, or `inconclusive` with rationale.

## Validation Plan

- Verify next-session timing, common-session prices, SGOV cash, fees, turnover, NAV/drawdown, aligned benchmarks, and endpoint lineage.
- Verify future data, live boundaries, missing weekdays/open prices, premature review, and arbitrary unversioned evidence cannot satisfy gates.
- Run the complete dynamic-allocation suite, touched-file compilation, security scan, handoff validation, current real read-only replay, and diff checks.

## Risks

- There is no governed production collector for forward paper session JSON yet; this task defines and validates the contract only.
- Free adjusted-close sources can revise records. Each captured observation therefore needs a stable observation ID and availability timestamp; mutation policy still belongs to the future collector.
- `paper_performance_eligible=true` is a new governance assertion and must be assigned only after source-rights review.
- A human `effective` outcome is a paper-research conclusion, not investment advice or a guarantee of future returns.

## Dependencies

- T-588/T-590 paper decision snapshots and T-591 longitudinal operations.
- Existing dependency-light performance metrics and next-period walk-forward timing convention.
- A governed XNYS calendar source and governed adjusted-close sources for SPY, QQQ, and SGOV.

## Blockers

- None for the implemented contract and local calculation.
- Real 3/6/12 month review remains time-dependent and cannot complete before elapsed evidence exists.
- Operational price/calendar collection is intentionally not fabricated and remains a follow-up implementation.

## Handoff Checklist

- [x] Schema and methodology versions fixed
- [x] Next-period signal effectiveness enforced
- [x] Calendar and price source/rights lineage required
- [x] SPY/QQQ/SGOV common-session and SGOV cash rules enforced
- [x] Turnover, transaction costs, advisory fees, and ETF expense treatment explicit
- [x] SPY and SPY/SGOV benchmark returns aligned to strategy intervals
- [x] Missing/future data block evidence and no return crosses a gap
- [x] Session evidence cannot predate the declared near-decision collection start
- [x] Gate requires time, operational coverage, performance evidence, and valid human review
- [x] Current efficacy remains unproven
- [x] Domain tests and security checks pass

## Evidence

- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v`: 82 tests passed; existing optional ML warnings were non-failing.
- `.venv/bin/python -m py_compile app/dynamic_allocation/performance.py app/dynamic_allocation/operations.py scripts/dynamic_allocation_operations_report.py tests/dynamic_allocation/test_performance.py tests/dynamic_allocation/test_operations.py`: passed.
- `.venv/bin/python scripts/security_check.py .`: 381 files checked, zero findings.
- `.venv/bin/python scripts/dynamic_allocation_operations_report.py --ledger data/local/dynamic-allocation-paper.jsonl --daily-report artifacts/dynamic-allocation/daily-run-latest.json --as-of 2026-07-18T12:00:00+08:00`: current local state remained accumulating/not-proven with no performance series and no efficacy claim.
- `tests/dynamic_allocation/test_performance.py`: covers one-period NAV/fees/turnover/benchmarks/lineage, strict next-session timing, missing weekday/open-price gaps, future data, boundaries, premature reviews, CLI read-only integration, and human gate completion.

## Artifacts

- No performance artifact was generated because no genuine forward session evidence exists yet.
- `/absolute/path/to/forward-paper-performance.json`: future operator input; producer must be a governed calendar/price collector; local-only; may contain source URIs but no secrets; not acceptable for non-local release gates.
- `data/local/dynamic-allocation-paper.jsonl`: existing T-590 decision input; local-only; no secrets expected; not acceptable for non-local release gates.

## Next Recommended Action

Implement a governed append-only forward session collector that writes `dynamic-allocation-paper-performance/v1` observations after each XNYS close, beginning from the current paper window without backfilling historical efficacy. Reviewer groups should approve calendar and adjusted-close rights before setting `paper_performance_eligible=true`.
