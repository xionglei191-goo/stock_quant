# Handoff: T-591 Dynamic Allocation Longitudinal Operations

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality; Governance, Security, and Compliance; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex `/root/t591_paper_ops`
- Branch/worktree: shared current worktree

## Objective

Convert the unelapsed 6-12 month paper observation requirement into an auditable workflow with daily and monthly operational health, explicit 3/6/12 month review gates, and a safe local scheduler handoff without fabricating performance evidence.

## Scope

- In scope: read-only ledger/report aggregation, daily failure retention, monthly health summaries, review-gate semantics, local systemd template rendering, focused tests, and operator documentation.
- Out of scope: roadmap edits owned by the parent PM agent, broker connectivity, order execution, historical performance fabrication, TLT/GLD expansion, systemd enable/start actions, and non-local evidence.

## Background

T-588 delivered an immutable paper ledger and T-590 joined strict public-data refresh, decision persistence, and a current local report. The roadmap correctly retained a 6-12 month real observation requirement, but there was no durable success/failure history, monthly aggregation, explicit review dates, or safe scheduler handoff.

## Problem Statement

A single successful report cannot demonstrate sustained operation, and stderr-only failures create survivorship bias in later reviews. The project needed to retain governed failure evidence, validate the ledger before aggregation, and make elapsed-time gates measurable without presenting operational continuity as investment efficacy.

## Expected Deliverables

- A read-only longitudinal report over the validated ledger and daily success/failure artifacts.
- Monthly run and data-health status plus explicit 3/6/12 month gate states.
- Execute-gated daily history retention that preserves nonzero exits on strict failure.
- A print-only-by-default systemd user timer template with explicit paths and no automatic enable/start action.
- Focused regressions, operating documentation, and a complete handoff.

## Current Findings

- The real ledger contains one valid hash-chain record and the current report contains one completed strict daily run with 38/38 fresh series.
- The observation window began at `2026-07-17T16:15:00Z`; the 3/6/12 month due dates are 2026-10-17, 2027-01-17, and 2027-07-17 at the same UTC time.
- All current gates are `awaiting_elapsed_time`; no return, benchmark, drawdown, or turnover evidence exists in this operational layer.

## Proposed Work Plan

1. Archive explicit daily execute results, including governed strict failures.
2. Review the read-only aggregation regularly and investigate failed/data-health runs.
3. At each elapsed gate, require monthly coverage and separately governed performance evidence before making an efficacy or asset-universe decision.

## Validation Plan

- Exercise boundary validation, monthly aggregation, failure visibility, review gates, and default read-only behavior in unit tests.
- Run the complete dynamic-allocation suite and touched-file compilation.
- Replay the current ledger and latest report without writing, render the timer, parse its calendar, and run security/handoff gates.

## Current State

- Completed: longitudinal operations module, read-only/report-write CLI, daily success/failure archive support, safe scheduler renderer, focused tests, security scan, documentation, and real read-only replay.
- In progress: none in implementation scope.
- Not started: elapsed observation evidence and governed paper performance/NAV contract; these require future real time and a follow-up task.
- Blocked: none for local operation. Efficacy assessment is intentionally unavailable until real longitudinal performance evidence exists.

## Files Touched

- `app/dynamic_allocation/operations.py`: validates daily report boundaries and aggregates ledger, monthly health, and 3/6/12 month gates.
- `scripts/dynamic_allocation_daily_run.py`: optionally archives each daily report and preserves structured strict-failure evidence without provider error messages.
- `scripts/dynamic_allocation_operations_report.py`: read-only-by-default longitudinal report CLI with execute-gated output.
- `scripts/dynamic_allocation_scheduler_template.py`: absolute-path user systemd service/timer renderer; default print-only, explicit write-only, never enables or starts units.
- `tests/dynamic_allocation/test_operations.py`: aggregation, boundary, CLI dry-run, and scheduler regressions.
- `tests/dynamic_allocation/test_daily_run.py`: strict failure detail and failure archive regressions.
- `README.md`: daily archive, longitudinal reporting, and scheduler template operator commands.
- `docs/dynamic-allocation-operations.md`: active operational contract, decisions, gates, assumptions, artifacts, and open questions.

## Commands Run

```bash
.venv/bin/python -m unittest tests.dynamic_allocation.test_operations tests.dynamic_allocation.test_daily_run tests.dynamic_allocation.test_paper_run -v
.venv/bin/python -m py_compile app/dynamic_allocation/operations.py scripts/dynamic_allocation_daily_run.py scripts/dynamic_allocation_operations_report.py scripts/dynamic_allocation_scheduler_template.py tests/dynamic_allocation/test_operations.py tests/dynamic_allocation/test_daily_run.py
.venv/bin/python scripts/check_doc_metadata.py
.venv/bin/python scripts/security_check.py .
.venv/bin/python scripts/dynamic_allocation_operations_report.py --ledger data/local/dynamic-allocation-paper.jsonl --daily-report artifacts/dynamic-allocation/daily-run-latest.json --as-of 2026-07-18T12:00:00+08:00
.venv/bin/python scripts/dynamic_allocation_scheduler_template.py --project-root /home/xionglei/Project/sotck_quant --python /home/xionglei/Project/sotck_quant/.venv/bin/python --state-dir /home/xionglei/Project/sotck_quant/data/local --artifact-dir /home/xionglei/Project/sotck_quant/artifacts/dynamic-allocation
systemd-analyze calendar 'Mon..Fri *-*-* 07:30:00 Asia/Shanghai'
```

Result:

- Passed: 16 focused paper/operations tests, 76 complete dynamic-allocation tests, touched-file compilation, canonical document metadata, security scan over 381 files, real ledger replay, scheduler rendering, and systemd calendar parsing.
- Passed: real read-only status reports one valid ledger record, one completed daily report, 38/38 fresh series, zero recorded failures, and all gates `awaiting_elapsed_time`.
- Failed: the first scheduler rendering attempt rejected `.venv/bin/python` because it is a normal virtualenv symlink; the validator was corrected to allow an absolute Python symlink while still rejecting a symlinked daily runner, then the exact command passed.
- Not run: full `make local-ci`; the parent PM agent is coordinating repository-wide integration in the shared dirty worktree.

## Decisions

- Gate states distinguish elapsed time, monthly coverage, and review readiness. Every gate fixes `efficacy_proven=false`; operational readiness cannot substitute for return/drawdown evidence.
- Daily failures are archived when the operator already authorized `--execute` and an output path. Only missing series, source names, insert conflicts, and decision readiness are retained; raw provider errors are excluded.
- The scheduler renderer defaults to stdout and requires absolute paths. Explicit execute writes units only and deliberately does not mutate systemd enablement or runtime state.
- Individual `--daily-report` and directory `--daily-reports` inputs are both supported so the existing latest report is visible before the new archive accumulates.

## Risks

- The ledger currently has only one record and archived history has not started; no elapsed efficacy claim is possible.
- Operational evidence does not yet define paper NAV, benchmark return, drawdown, or turnover. That contract must be governed before the first 3-month review.
- Expected weekday coverage and an alert destination remain policy decisions after local scheduler reliability is observed.
- The rendered timer has not been installed or enabled; doing so is an explicit operator action outside this task.

## Dependencies

- Existing T-588 JSONL paper repository and T-590 daily report contract.
- A trusted local filesystem for ledger and report history.
- Python 3.11+ and optional user-level systemd for scheduling; the reporting module itself has no new third-party dependency.

## Blockers

- None for implementing and operating the local workflow.
- Financial efficacy remains time- and evidence-dependent, and cannot be closed by software implementation alone.

## Handoff Checklist

- [x] Ledger integrity validated before aggregation
- [x] Daily success and strict failure reports retained only after explicit execute authorization
- [x] Strict failures preserve nonzero exit status
- [x] Monthly health and 3/6/12 month gates covered by tests
- [x] Default report and scheduler commands remain read-only/print-only
- [x] Paper-only/no-broker/no-order boundary preserved
- [x] Focused and domain test suites passed

## Evidence

- `.venv/bin/python -m unittest discover -s tests/dynamic_allocation -v`: 76 tests passed; one existing optional ML `ResourceWarning` and one LightGBM feature-name warning did not fail the suite.
- `.venv/bin/python scripts/dynamic_allocation_operations_report.py --ledger data/local/dynamic-allocation-paper.jsonl --daily-report artifacts/dynamic-allocation/daily-run-latest.json --as-of 2026-07-18T12:00:00+08:00`: one valid ledger record, one completed report, 38/38 fresh, and all gates awaiting elapsed time; stdout only, local-only.
- `.venv/bin/python scripts/security_check.py .`: 381 files checked, zero findings.
- `systemd-analyze calendar 'Mon..Fri *-*-* 07:30:00 Asia/Shanghai'`: calendar parsed and normalized successfully.
- Unit regression `test_execute_failure_is_archived_for_longitudinal_visibility`: explicit execute failure writes latest/history governed reports, returns exit code 1, and does not append the paper ledger.

## Artifacts

- `data/local/dynamic-allocation-paper.jsonl`: existing input produced by the T-590 explicit daily command; local-only append-only evidence; not sensitive by design; not acceptable for non-local production gates.
- `artifacts/dynamic-allocation/daily-run-latest.json`: existing input produced by the T-590 daily command; local-only current status; not sensitive by design; not acceptable for non-local production gates.
- `artifacts/dynamic-allocation/daily-history/*.json`: future output from explicit `--history-dir`; local-only operational evidence; not sensitive by design; not acceptable for non-local production gates.
- `artifacts/dynamic-allocation/operations-latest.json`: optional future output from the explicit report write command; local-only aggregation; not sensitive by design; not acceptable for non-local production gates.

## Acceptance Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [ ] `tasks/todo.md` status updated by the parent PM agent, which owns roadmap coordination and explicitly excluded it from this subtask

## Next Steps

1. Parent PM agent adds/reconciles T-591 in `tasks/todo.md` and includes this handoff in repository-wide validation.
2. Operator reviews the printed unit paths and schedule before explicitly installing/enabling the timer; the first execute run begins `daily-history` accumulation.
3. Define governed paper NAV, benchmark, turnover, drawdown, and review decision fields before the 3-month gate due at `2026-10-17T16:15:00Z` for the current ledger.

## Next Recommended Action

Parent PM should register T-591 in the roadmap, then have the local operator review the rendered service and timer before any explicit installation or enablement. After the first scheduled execute run, verify that `daily-history` contains either a governed success or governed failure artifact and that the process exit status remains observable by systemd.
