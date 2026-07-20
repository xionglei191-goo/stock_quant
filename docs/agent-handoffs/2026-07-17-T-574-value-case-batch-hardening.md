# Handoff: T-574 Value-Case Batch Hardening

## Metadata

- Status: active
- Owner group: Research and AI Workflows
- Last updated: 2026-07-17
- Related tasks: T-573, T-574
- Scope: Local-only value-case batch execution and its focused regression tests.
- Non-goals: API, storage schema, UI, broker integration, or non-local release evidence changes.

## Status

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality
- Last updated: 2026-07-17
- Last agent: Codex `/root/t574_impl`
- Branch/worktree: shared current worktree

## Objective

Harden the uncommitted T-573 batch mode with a strict symbol contract, collision-safe identifiers, deterministic aggregate status, sanitized failures, artifact metadata, and focused regression coverage while preserving single-symbol behavior.

## Scope

- In scope: `scripts/value_case_analysis_feedback_loop.py`, focused tests, this handoff.
- Out of scope: roadmap edits, production APIs, schemas, UI behavior, existing artifact deletion, live trading, and broker connectivity.

## Background

T-573 introduced an uncommitted single-store batch mode for the local value-case analysis feedback loop. T-574 closes validation, identifier, rerun, aggregation, failure-reporting, and artifact-classification gaps in that work.

## Problem Statement

The initial batch implementation accepted unchecked symbols, collided on identical six-digit codes across exchanges, reported partial success as passed, leaked exception messages, and could not rerun against a persistent store because fixed IDs already existed.

## Expected Deliverables

- A strict and shared CLI/programmatic symbol contract.
- Exchange-aware stable IDs and persistent rerun support.
- Accurate batch aggregation, sanitized failure records, and local-only metadata.
- Focused tests and a validated handoff.

## Current State

- Completed: Batch inputs normalize to lowercase, validate `^(sh|sz)\d{6}$`, reject explicit empty values/segments, and deduplicate in first-seen order.
- Completed: Exchange prefixes are included in issuer/security IDs; persistent reruns reuse existing conclusion, observation, and feedback entities.
- Completed: Aggregate status is `passed`, `partial`, or `failed`; failures expose only a stable reason and exception type, never exception text.
- Completed: Results carry UTC generation time, producer, `local-only` classification, non-local gate rejection, and explicit paper-only/no-broker boundaries.
- Blocked: None.

## Current Findings

- The completed implementation satisfies all expected deliverables in the three-file task boundary.
- No API, schema, UI, live execution, or broker behavior changed.

## Proposed Work Plan

1. Normalize and validate symbols at both entry points.
2. Derive exchange-aware IDs and make fixed entity creation idempotent.
3. Aggregate cases, attach metadata, and sanitize exceptions.
4. Prove the contract with focused tests and repository handoff validation.

## Files Touched

- `scripts/value_case_analysis_feedback_loop.py`: Added strict parsing, resilient batch execution, exchange-aware IDs, idempotent entity creation, aggregate metadata, and CLI batch routing.
- `tests/test_value_case_analysis_feedback_loop.py`: Added nine focused tests for validation, order/deduplication, status/returns, sanitization, IDs, reruns, CLI output, and paper-only boundaries.
- `docs/agent-handoffs/2026-07-17-T-574-value-case-batch-hardening.md`: Records implementation and verification.

## Commands Run

```bash
python3 -m unittest tests.test_value_case_analysis_feedback_loop
python3 -m py_compile scripts/value_case_analysis_feedback_loop.py tests/test_value_case_analysis_feedback_loop.py
git diff --check
python3 scripts/check_handoffs.py
```

Result:

- Passed: 9 focused unit tests; Python compilation; whitespace validation.
- Failed: None.
- PM integration: `make local-ci` passed on 2026-07-17 with 353 tests plus UI static, security, Markdown, handoff, and canonical metadata gates.

## Validation Plan

- Run the nine focused unit tests and Python compilation.
- Run `git diff --check` and the repository handoff validator.
- Leave the full suite to PM integration after concurrent work settles.

## Decisions

- `--symbols` defaults to `None`, so omitted batch mode preserves the original single-symbol path while an explicitly empty value is an argument error.
- Programmatic batch calls enforce the same parser contract as CLI calls.
- Existing fixed-ID records are reused on rerun, while performance scoring still runs again against current local market data.
- Arbitrary exception messages are excluded from artifacts; `reason=value_case_execution_error` plus the exception class provides stable diagnostics.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Domain module decision: No production service extraction was needed; this task only orchestrates existing public service methods in a local script.
- Focused facade regression: The persistent-store test proves entity reuse and repeated performance updates through the existing facade contract.
- Contract/boundary changes: No API schema, storage schema, or UI behavior changed. Paper-only remains true; live execution and broker connectivity remain false.

## Risks and Open Questions

- Exception class names are retained for local diagnostics; exception text is deliberately removed.
- Full integration with the machine's TDX dataset was not run in this focused task.

## Dependencies

- Uses existing `SystemService` market import, conclusion, observation, simulation feedback, and performance update contracts.
- Depends on local TDX data only when executing a real value-case artifact, not for focused tests.

## Blockers

- None.

## Handoff Checklist

- [x] Implementation is limited to the assigned script, focused test, and handoff.
- [x] Focused verification passes.
- [x] Paper-only and no-broker boundaries are explicit.
- [x] PM retains ownership of `tasks/todo.md` updates and wave-wide verification.

## Artifacts

- Runtime `--output` JSON: Produced by `python3 scripts/value_case_analysis_feedback_loop.py`; generated at execution time; local environment; owner Research and AI Workflows; may contain local market-derived data; `local-only`; not acceptable for non-local production release gates.

## Evidence

- `tests/test_value_case_analysis_feedback_loop.py`: Executable evidence for the strict contract and persistent rerun behavior.
- Focused test result: 9 tests passed on 2026-07-17 in the local worktree.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated by PM integration

## Next Steps

1. Platform and Quality reviews the parser, idempotency, and focused tests.
2. PM updates `tasks/todo.md` as part of the coordinated wave closeout.
3. PM runs the complete repository verification suite after parallel changes settle.

## Next Recommended Action

Platform and Quality should review the focused diff, then PM should integrate the roadmap status and run wave-wide checks.
