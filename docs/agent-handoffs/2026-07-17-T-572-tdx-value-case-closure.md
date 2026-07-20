# Handoff: T-572 and T-573 TDX Value-Case Closure

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Research and AI Workflows; PM / Release Coordination
- Last updated: 2026-07-17
- Last agent: Codex `/root`
- Branch/worktree: shared current worktree
- Artifact classification: local-only

## Objective

Verify TDX import persistence against a reopened SQLite process and rerun the analysis-to-feedback value case with real local TDX prices, then reconcile stale T-572/T-573 roadmap states.

## Scope

- In scope: focused persistence regression, real local value-case execution, artifact inspection, roadmap/docs reconciliation.
- Out of scope: broker connectivity, order execution, TDX source redistribution, model changes, and non-local release claims.

## Background

T-572 claims `import_tdx_market_data` does not commit, while T-573 requests a reproducible real-price value-case artifact. T-574 subsequently hardened the value-case script, but T-572/T-573 remained TODO.

## Problem Statement

Roadmap state and current code disagree. `_audit()` commits every registered market point and the final import audit, so adding another commit without a behavioral test would add cost rather than prove persistence. The existing value-case artifact predates the hardened exchange-aware batch path and must be regenerated.

## Expected Deliverables

- A focused SQLite reopen regression for TDX-imported market data.
- A freshly generated, paper-only real TDX value-case artifact with conclusion/observation/feedback/market-data lineage.
- Updated T-572/T-573 roadmap status supported by executable evidence.

## Current State

- Completed: corrected `_build_service()` to construct `SQLiteStore` explicitly; added direct and batch-path SQLite reopen regressions; ran the real value case twice; reconciled T-572/T-573 as DONE.
- In progress: none.
- Not started: none in scope.
- Blocked: none.

## Current Findings

- `SystemService._audit()` already commits TDX registrations; the actual loss occurred because the CLI ignored `--db` when constructing its service.
- The corrected real run persists 812 price points and the complete conclusion/observation/feedback chain.

## Proposed Work Plan

1. Keep the two SQLite reopen regressions in the full suite.
2. Use the persisted local artifact for manual hypothesis review only.

## Validation Plan

- Run the focused persistence/value-case tests and the final repository quality gate.

## Files Touched

- `scripts/value_case_analysis_feedback_loop.py`: explicitly uses `SQLiteStore` when `--db` is supplied.
- `tests/test_tdx_value_case_persistence.py`: proves both injected-service and CLI-construction persistence across store reopen.
- `tasks/todo.md`: corrects the stale root-cause description and closes T-572/T-573 with evidence.
- `docs/agent-handoffs/2026-07-17-T-572-tdx-value-case-closure.md`: records this closure.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_tdx_value_case_persistence tests.test_value_case_analysis_feedback_loop -v
.venv/bin/python scripts/value_case_analysis_feedback_loop.py --db data/local/value-case-t573.sqlite --symbols sz000001 --start-date 2023-01-01 --end-date 2099-12-31 --vipdoc-path data/local/tdx/vipdoc --output artifacts/value-case/analysis-feedback-loop.json
```

Result:

- Passed: 11 focused tests; real command passed twice; independent SQLite reopen found 812 points and the persisted feedback.
- Failed: none after the storage construction fix.
- Passed in final PM wave: `make local-ci PYTHON=.venv/bin/python` completed with 423 tests plus all UI, security, link, handoff, and document metadata gates.

## Decisions

- Did not add another commit to `import_tdx_market_data`: existing `_audit()` plumbing already commits, and a redundant full SQLite rewrite per import would add cost without addressing the actual defect.
- Treat the artifact as local-only because it depends on the user's local TDX files.

## Risks

- TDX files are local-only and cannot be treated as redistributable production artifacts.
- A single falsified thesis proves the feedback mechanism, not investment alpha.

## Dependencies

- `data/local/tdx/vipdoc` and the existing public EOD source governance.
- SQLiteStore, SystemService, and simulation-feedback scoring.

## Blockers

- None.

## Handoff Checklist

- [x] SQLite reopen regression passes
- [x] Real value-case artifact regenerated
- [x] Paper-only/no-broker boundary verified
- [x] Roadmap reconciled

## Evidence

- `artifacts/value-case/analysis-feedback-loop.json`: local-only artifact, produced by the command above on 2026-07-18 Asia/Shanghai; contains no secrets and is not acceptable for non-local production release gates.
- `data/local/value-case-t573.sqlite`: ignored local state, 812 `sz000001` points from 2023-01-03 through 2026-05-15 plus conclusion, observation, feedback, and audit lineage; contains no broker integration.
- Result: `realization_status=missed`, `event_window_return=-0.201888`, `max_drawdown=-0.40396`, `paper_only=true`, `live_execution_allowed=false`, `broker_connected=false`.

## Next Steps

1. Include these focused tests in the final full repository gate.
2. Use the persisted review result for manual hypothesis review; do not interpret one case as alpha evidence.

## Next Recommended Action

Include the focused regression in the final PM-wave `make local-ci` run.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain placement: no service change is planned because current audit plumbing already commits.
- Focused regression: new TDX SQLite reopen test plus existing value-case tests.
- Contract/boundary changes: none; paper-only/no-broker remains fixed.
