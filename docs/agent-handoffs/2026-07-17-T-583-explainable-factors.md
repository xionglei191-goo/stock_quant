# Handoff: T-583 Explainable Dynamic Allocation Factors

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Data and Evidence; Platform and Quality
- Last updated: 2026-07-17
- Last agent: /root/t583_factors
- Branch/worktree: shared working tree
- Boundary: local-only research calculation; no broker or order execution

## Objective

Implement the valuation, trend, volatility, credit, leverage, macro, liquidity, and breadth factor families with a shared explainable result contract. Every valid score uses a consistent `0-100` direction where a higher value supports more equity risk.

## Scope

- In scope: pure factor-domain calculators, mapping input adapter, PIT historical percentile, component contributions, coverage/freshness gates, serializable factor rows, focused tests.
- Out of scope: providers and repositories, model/regime logic, allocation, backtesting, API/UI, dependency changes, model training, and live execution.

## Background

T-581 defines eight factor families and requires each result to retain raw values, contributions, coverage, data cutoff, source observation IDs, warnings, factor version, and config hash. T-583 consumes plain mappings so the T-582 repository layer can integrate without coupling factor logic to a database or dataframe library.

## Problem Statement

A numeric factor score is unsafe when future history, stale observations, insufficient history, or critical missing inputs can silently look complete. The implementation must make these conditions explicit and prevent unavailable critical evidence from becoming a neutral score.

## Expected Deliverables

- Shared dataclasses and calculator protocol in `app/dynamic_allocation/factors/base.py`.
- Eight transparent factor-family specifications.
- JSON-serializable dataframe-like output with factor and component explanations.
- Tests for every family, PIT filtering, score direction, critical missing data, freshness, history sufficiency, quality flags, and provenance.

## Current Findings

- All eight factor families produce complete high scores for deliberately supportive fixture inputs and reverse risk-adverse measures such as VIX and credit spreads.
- Macro inflation components use distance from a configured 2% target instead of assuming that indefinitely lower inflation is always better.
- Only history entries with `available_at <= as_of` enter a percentile. Current observations with future availability are rejected.
- Critical missing, stale, insufficient-history, future, or quality-blocked inputs set the result to unavailable; they are never replaced with 50.
- Current and actually used historical observation IDs are retained for audit.

## Proposed Work Plan

1. Integrate T-582 repository snapshots by converting them to the documented mapping or `SeriesSnapshot` contract.
2. Move component weights, freshness limits, minimum history, and inflation targets into the validated YAML configuration when the application orchestration is added.
3. Pass factor rows to T-584 rule models only when `ready=true`.

## Validation Plan

- Compile all factor modules and their focused test.
- Run `tests.dynamic_allocation.test_factors`.
- Run dynamic-allocation discovery to identify integration failures from concurrent work.
- Run the handoff validator after this record is added.

## Risks

- Family weights and freshness thresholds are transparent first-version defaults; production use requires source-specific calibration and a versioned YAML snapshot.
- Percentiles require sufficient governed PIT history. A present-day value alone intentionally cannot produce a score.
- Aggregate market breadth must use PIT constituents or a governed aggregate series to avoid survivorship bias.

## Dependencies

- T-582 supplies governed point-in-time observations and configuration loading.
- T-584 consumes `FactorResult` and must respect `ready`, coverage, and warnings.
- No third-party Python package is required by the factor calculation core.

## Blockers

- No blocker in T-583 scope.
- Concurrent dynamic-allocation discovery currently reports two T-582 configuration-test errors because PyYAML is not installed in the active environment. Focused T-583 tests pass, and T-583 did not modify dependency declarations.

## Handoff Checklist

- [x] Code changes completed
- [x] Focused tests passed
- [x] All eight families tested
- [x] PIT and missing-data gates tested
- [x] Provenance/config/version retained
- [x] Paper-only and no-broker boundary preserved
- [ ] Roadmap status update by parent PM agent

## Evidence

- `python3 -m py_compile app/dynamic_allocation/factors/*.py tests/dynamic_allocation/test_factors.py`: passed; local-only verification on 2026-07-17; no sensitive data; not non-local release evidence.
- `python3 -m unittest tests.dynamic_allocation.test_factors -v`: 7 passed; local-only verification on 2026-07-17; no sensitive data; not non-local release evidence.
- `python3 -m unittest discover -s tests/dynamic_allocation -v`: 15 run, 13 passed and 2 T-582 PyYAML environment errors; local-only integration diagnostic on 2026-07-17; no sensitive data; not non-local release evidence.

## Next Recommended Action

The PM agent should review the shared-tree integration after T-582 finishes dependency/config work, rerun dynamic-allocation discovery, then mark T-583 done and hand `FactorResult` to T-584 without bypassing readiness gates.
