# Handoff: T-617 Persistent Clone Segment State Contract

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Data and Evidence; Research and AI Workflows; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only
- Related tasks: T-617

## Objective

Add a machine-checkable local state contract for persistent research clone segments. The contract binds clone identity, plan/manifest hashes, successful double-run artifacts, and the latest checkpoint without authorizing database execution.

## Scope

- In scope: state initialization, append-only batch checkpoints, idempotence gating, abort/resume state transitions, CLI and focused tests.
- Out of scope: PostgreSQL access, Docker lifecycle, primary writes/deletes, batch 0006 execution, promotion, and scheduler control.

## Background

Batch 0005 proved single-batch clone idempotence, but the project had no durable contract for accumulated segment state or an explicit terminal abort boundary.

## Problem Statement

Without a hash-bound state file, a later resume could use the wrong clone identity, prior batch, or run artifact while still appearing operationally successful.

## Expected Deliverables

- A local-only state schema and CLI for initialization, checkpoint append, and abort.
- Focused tests covering successful checkpointing, idempotence rejection, and terminal abort.

## Current State

- Completed: `scripts/manage_research_report_clone_segment.py`, focused unit tests, and executor state integration.
- In progress: real persistent segment execution remains gated by approval and quiescence evidence.
- Blocked: batch 0006 execution remains unauthorized.

## Current Findings

- A checkpoint is rejected unless run 2 contains `idempotency_comparison.passed=true`.
- A checkpoint stores SHA-256 hashes for both run artifacts, exact `prior_run_sha256`, restore-verified backup/dump SHA, post-backup vacuum evidence SHA/timestamp, all nine cumulative counts (`records`, `audit_log`, `market_data_bars`, and six research collections), and its own canonical checkpoint hash.
- A segment can transition `active -> aborted -> active` only when resume names the latest existing checkpoint; an aborted segment cannot accept checkpoints until resumed.
- The state explicitly records `primary_writes_allowed=false`, an empty delete list, `accumulated_counts`, and `local-only` classification.

## Proposed Work Plan

1. Implement the standalone state contract and refuse unsafe transitions. [done]
2. Add focused regression tests and document the integration boundary. [done]
3. Integrate with the future executor only after restore and scheduler evidence are available. [next]

## Validation Plan

- Compile the new script and tests.
- Run the focused state tests and existing clone executor/runtime tests.
- Run handoff validation, diff whitespace checks, and repository security scan.

## Dependencies

- Existing T-617 batch execution artifacts and clone attestation contract.
- A future restore-verified segment backup and scheduler-quiescence proof.

## Blockers

- No batch 0006 approval exists.
- The executor accepts `--segment-state` for pre-execution state validation. Checkpoint finalization is a separate `checkpoint` command and requires a restore-verified backup manifest, so the segment-end backup precedes the state write.

## Files Touched

- `scripts/manage_research_report_clone_segment.py`: local-only state machine and CLI.
- `tests/test_manage_research_report_clone_segment.py`: checkpoint, idempotence rejection, abort/resume, and terminal-state coverage.
- `tasks/todo.md`: T-617 progress reference.

## Evidence

- `tests/test_manage_research_report_clone_segment.py`: focused local regression evidence; local-only; no sensitive data; not a release gate.
- No runtime or database artifact was produced by this change.

## Commands Run

```bash
python3 -m py_compile scripts/manage_research_report_clone_segment.py tests/test_manage_research_report_clone_segment.py
python3 -m unittest tests.test_manage_research_report_clone_segment
git diff --check
```

Result:

- Passed: compilation and 12 focused tests; full CI is rerun in the current T-617 integration handoff.
- Not run: full local CI; no application or database behavior changed.

## Decisions

- Keep segment state as a standalone JSON contract before wiring it into the long-running executor.
- Refuse duplicate batch checkpoints and failed idempotence comparisons to prevent ambiguous resume state.
- Treat abort as a stop boundary; recovery must explicitly name the latest verified checkpoint before resuming.

## Risks and Open Questions

- The checkpoint command validates cumulative counts, backup restore equality, and post-backup vacuum ordering but does not query PostgreSQL itself; backup/vacuum producers supply the evidence before the state write.
- Scheduler quiescence evidence is still a separate required gate and is not inferred from this state file.
- No batch 0006 approval exists; this change does not authorize execution.

## Handoff Checklist

- [x] Code changes completed
- [x] Focused tests run
- [x] Contract boundaries documented
- [x] Roadmap reference updated

## Next Steps

1. Bind this state contract to the persistent clone executor and restore-verified segment backup flow.
2. Add a fresh scheduler-quiescence/attributable-write proof gate for each execution window.
3. Run focused and full CI before requesting any batch 0006 approval.

## Next Recommended Action

Implement the executor integration that creates a checkpoint only after backup restore equality and scheduler evidence pass.
