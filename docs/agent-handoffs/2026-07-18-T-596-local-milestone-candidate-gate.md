# Handoff: T-596 Local Milestone Candidate Gate

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex `/root` after independent `/root/t591_paper_ops` Platform/Governance review
- Branch/worktree: `main`, shared dirty worktree
- Artifact classification: local-only

## Objective

Provide one non-destructive command that inventories the current Git worktree and runs the local CI, completion-audit, and artifact-retention gates required for a reviewable local milestone candidate.

## Scope

- In scope: local command orchestration, temporary audit outputs, structured gate summaries, dirty-worktree inventory, focused tests, and a Make target.
- Out of scope: commit, push, deletion, service enablement, external evidence, or non-local release approval.

## Background

The PM audit found a large green but uncommitted change set and stale completion evidence. Existing gates were individually available but did not produce one candidate-level status and inventory.

## Problem Statement

Task completion could be recorded before the exact shared worktree passed current checks. Reviewers needed a repeatable entry point that never mutates Git or deletes artifacts.

## Expected Deliverables

- `scripts/local_milestone_candidate.py` and `make milestone-candidate`.
- Structured local-only report with Git inventory and exact gate failures.
- Focused regressions proving dirty trees are inventoried and failed gates prevent readiness.

## Current State

- Completed: implementation, independent safety/correctness review, structured timeout/audit failures, strict dry-run semantics, shell action hardening, focused tests, and final real candidate execution.
- In progress: none.
- Not started: none.
- Blocked: none.

## Current Findings

- A dirty tree is expected input for candidate review and is not itself a failed gate.
- Completion and artifact audits can safely write only to a temporary directory.
- The retention script's authoritative dry-run field is `mode="dry-run"`; the original implementation incorrectly expected a nonexistent `execute=false` field and would reject a real safe audit.
- The candidate requires completion `achieved=true`, `local_production_ready=true`, well-typed non-negative counts, retention `mode="dry-run"`, and `deleted_count=0` in addition to command return codes.
- `status` invokes only `docker compose ps`; `stop` invokes only `docker compose stop`, preserving volumes. Unknown or extra actions fail before Docker is called.

## Proposed Work Plan

1. Unit-test command orchestration, timeout behavior, audit parsing, and mutation boundaries.
2. Wait for active shared-worktree edits to settle.
3. Execute the real candidate command and reconcile any failures.

## Validation Plan

- Focused unit tests and Python compilation.
- Final `make milestone-candidate PYTHON=.venv/bin/python` after all active tasks settle.
- Handoff, Markdown, security, and diff checks through the nested local CI gate.

## Dependencies

- `make local-ci`, `scripts/project_completion_audit.py`, and `scripts/local_artifact_retention.py`.
- T-591 through T-595, T-598, and T-599 must settle before final execution.

## Blockers

- None.

## Files Touched

- `scripts/local_milestone_candidate.py`: non-destructive candidate orchestrator.
- `tests/test_local_milestone_candidate.py`: command, timeout, malformed/missing audit, Git failure, and stack action regressions.
- `Makefile`: `milestone-candidate` entry point.
- `scripts/local_production_stack.sh`: strict single-action parsing with read-only status and volume-preserving stop.
- `docs/agent-handoffs/2026-07-18-T-596-local-milestone-candidate-gate.md`: current integration record.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_local_milestone_candidate -v
.venv/bin/python -m py_compile scripts/local_milestone_candidate.py tests/test_local_milestone_candidate.py
bash -n scripts/local_production_stack.sh
make -n milestone-candidate PYTHON=.venv/bin/python
make milestone-candidate PYTHON=.venv/bin/python
```

Result:

- Passed: 8 focused tests; Python compilation; Bash syntax; final candidate 3/3 gates; nested 450-test local CI; completion achieved/local ready; retention dry-run with zero deletion; Git inventory.
- Failed then fixed: the first real run resolved `.venv/bin/python` to the Homebrew base interpreter and lost optional ML packages; the launcher is now preserved verbatim.
- Not run: commit and push by design.

## Evidence

- Final stdout report: `status=passed`, `ready_for_commit_review=true`, 32 modified and 58 untracked paths; local-only and not acceptable for non-local release.

## Decisions

- Treat a dirty tree as inventory, not automatic failure; exact changed paths remain visible for human commit review.
- Run subordinate audit outputs in a temporary directory so the candidate command does not churn tracked artifacts.
- Capture only output tails to keep the report bounded while preserving failure diagnosis.
- Apply a finite 30-minute default timeout to every real subprocess; timeout/start failures become structured failed gates rather than uncaught exceptions.
- Preserve the caller-provided Python launcher (for example `.venv/bin/python`) instead of resolving its symlink to a base interpreter that lacks virtual-environment packages.
- Treat missing, malformed, non-object, symlinked, or semantically invalid audit output as a failure of its named gate even when the command exits zero.

## Risks and Open Questions

- Full local CI output is intentionally summarized; reviewers may rerun the recorded command for complete logs.
- The command can take roughly the duration of the full test suite and fails after the configurable timeout; exceptionally slow machines may need an explicit larger `--timeout-seconds`.

## Handoff Checklist

- [x] Code and tests added
- [x] Focused checks passed
- [x] Real current-code candidate gate passed
- [x] Roadmap status reconciled by PM

## Next Steps

1. Review candidate inventory into intentional commit groups.
2. Commit/push only with explicit user authorization.
3. Continue to reject local-only evidence at non-local release gates.

## Next Recommended Action

Use the passing candidate inventory for commit review; rerun after any subsequent workspace edit.
