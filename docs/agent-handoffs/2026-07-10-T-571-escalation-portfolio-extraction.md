# Handoff: T-571 Escalation and portfolio pure-helper extraction

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Governance, Security, and Compliance; Research and AI Workflows
- Last updated: 2026-07-10
- Last agent: Kiro (Claude Opus 4.8)
- Branch/worktree: main

## Objective

Continue the SystemService Modularization ADR by extracting three coherent
clusters of pure helpers (governance source-review escalation, LLM task
escalation, portfolio risk math) from `SystemService` into domain modules, with
no API, storage schema, UI, or paper-only boundary change.

## Scope

- In scope: pure helpers in `app/services.py`; three new modules under
  `app/service_modules/`.
- Out of scope: methods that read `self.store`/audit/permissions or call other
  `self` methods (e.g. `_llm_metric_escalation_row`, `_llm_run_escalation_row`,
  `_portfolio_walk_forward`, `_portfolio_covariance_diagnostics` — left in
  `SystemService`); API routes; DB schema; UI.

## Background

Follows T-570 (workflow scheduling extraction). `SystemService` still holds
~34k lines. An AST scan (`/tmp/analyze_leaves.py`) identified pure leaf helpers
(no `self` data access, no `self` calls) grouped by domain prefix. Governance
`_source_review_escalation_*`, research `_llm_*escalation`, and `_portfolio_*`
math were the next clean coherent clusters.

## Problem Statement

Deterministic escalation policy/severity/routing logic and portfolio risk math
lived inline in `SystemService`, inflating the monolith and mixing pure
computation with stateful orchestration.

## Expected Deliverables

- `app/service_modules/source_review_escalation.py` (governance, 7 functions).
- `app/service_modules/llm_escalation.py` (research/AI, 7 functions).
- `app/service_modules/portfolio_analytics.py` (portfolio, 6 functions).
- `SystemService` facade methods delegating to the modules, signatures unchanged.

## Current Findings

- 20 pure helpers moved (7 + 7 + 6). Dependencies were limited to `app.utils`
  (`env_float`) and `app.errors` (`ValidationError`); model types
  (`LLMTaskRun`, `LLMTaskTemplate`, `PortfolioProposal`) are used only in
  annotations (guarded by `TYPE_CHECKING`), so no import cycle.
- Non-pure neighbors that call these helpers via `self._...` continue to work
  because the facade method names/signatures are unchanged.

## Proposed Work Plan

Completed in this turn:

1. Create the three modules with the pure functions (verbatim behavior).
2. Import them in `app/services.py`; replace the 20 method bodies with one-line
   delegations.
3. Run the full regression checklist.

## Validation Plan

ADR regression checklist with the AGENTS.md §9 clean-env pattern.

## Risks

- Low. Behavior-preserving moves of pure functions; full suite count unchanged
  (332) and passing. `_portfolio_valuation_risk_decomposition` kept its
  pre-existing unused local `sorted_positions` verbatim to avoid any behavior
  change.

## Dependencies

- None. `app.utils`, `app.errors`, `app.models` do not import `app.services`.

## Blockers

- None.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable (ADR-aligned; no contract change)
- [x] `tasks/todo.md` status updated if roadmap state changed

## Evidence

Commands run:

```bash
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests   # AGENTS.md clean-env pattern
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
git diff --check
```

Result:

- Passed: py_compile OK; `Ran 332 tests ... OK`; `ui_static_check.py` ok;
  `security_check.py .` 0 findings; `git diff --check` clean.
- Failed: none.
- Not run: none.

Metrics:

- `app/services.py`: 33776 -> 33499 lines this batch (-277); cumulative with
  T-570 this session 33921 -> 33499 (-422).
- New modules: source_review_escalation.py (152), llm_escalation.py (112),
  portfolio_analytics.py (188). Local source, not artifact deliverables.

## SystemService Growth Freeze Review

- New `SystemService` business logic added? No. Refactor-only; no new behavior.
- Why domain modules were used: 20 pure helpers moved to
  `source_review_escalation.py`, `llm_escalation.py`, and
  `portfolio_analytics.py` per the ADR facade rule. `SystemService` retains
  identical method names as thin delegating facades. No stateful
  (store/audit/permission) logic moved.
- Focused regression protecting the facade: full `tests/test_system.py` suite
  (332 tests, including source review reminders/escalation, LLM task review
  queue/metrics, portfolio optimizer compare/forward/attribution, and the
  `test_golden_api_behavior_baseline_for_backend_domain_refactor` baseline)
  passes unchanged.
- Did API schema, storage schema, UI behavior, or paper-only/no-broker
  boundaries change? No.

## Next Recommended Action

1. Continue with the next pure-leaf clusters from the AST scan: `_normalize_*`
   (shared normalizers), `_chokepoint_*`, `_hotspot_*`, and remaining
   `_company_*`/`_industry_chain_*` pure helpers.
2. After a few more pure batches, evaluate extracting stateful orchestration
   (methods reading `self.store`) into domain services that receive the store.
3. Keep updating the ADR with cumulative `SystemService` line reduction.
