# Handoff: T-617 Segment Quiescence Integration

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Governance, Security, and Compliance; Data and Evidence; Research and AI Workflows; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only
- Related tasks: T-617

## Objective

Make persistent-clone execution refuse to start without a fresh, hash-bound scheduler quiescence proof and bind each checkpoint to its exact plan, manifest, batch, and run artifacts.

## Scope

- In scope: quiescence proof schema/validator/generator, executor pre-API gate, checkpoint artifact binding, tests and documentation.
- Out of scope: stopping services automatically, PostgreSQL writes, Docker lifecycle, batch 0006 execution, primary promotion, and scheduler deployment.

## Background

Earlier batch windows showed that `ai-quant-daily-update.service` can write the primary concurrently with clone measurements. The clone executor already proved primary reachability isolation, but it had no machine-enforced scheduler gate.

## Problem Statement

An operator could run an isolated clone while a known primary scheduler was active and incorrectly claim a clean measurement window. A checkpoint could also be assembled from artifacts belonging to a different plan or batch.

## Expected Deliverables

- Quiescence proof builder and validator with freshness, hash, writer-session, scheduler, and primary reachability gates.
- Clone executor refusal before API access when the proof is absent or invalid.
- Checkpoint refusal unless both run artifacts bind segment plan/manifest and batch identity and run 2 passes idempotence.

## Current State

- Completed: quiescence proof contract, direct read-only observation command, and executor integration.
- Completed: checkpoint plan/manifest/batch binding.
- Blocked: batch 0006 remains unauthorized; service stopping and observation collection remain operator-controlled.

## Current Findings

- Proof freshness is limited to 30 minutes with a two-minute future-skew allowance.
- Required proof values: `primary_service_reachable=false`, all known scheduler units stopped, known writer containers observed stopped, `active_writer_sessions=0`, and the exact operator boundary string.
- `--quiescence-proof` is required by the real executor CLI and validated before any clone API request.
- `observe-proof` reads systemd state, Docker container state, primary health reachability, and PostgreSQL sessions without stopping or mutating anything.

## Proposed Work Plan

1. Keep the proof and state contracts local-only and hash-bound.
2. Collect proof observations by an operator-controlled stop/inspect procedure before any future batch.
3. Request a fresh batch approval only after a direct observation proof and full CI pass.

## Validation Plan

- `python3 -m py_compile` for modified scripts/tests.
- Focused clone executor, runtime probe, segment state, and quiescence tests.
- `scripts/security_check.py .`, `scripts/check_handoffs.py`, and `git diff --check`.
- `PATH=.venv/bin:$PATH make local-ci`.

## Dependencies

- T-617 segment state contract.
- A restore-verified clone backup and fresh operator observations of known scheduler units.
- `PyYAML` dependency availability for the unrelated full-suite dynamic allocation tests.

## Blockers

- No batch 0006 approval exists.
- The proof builder intentionally refuses to manufacture evidence while schedulers or writer sessions are active.

## Files Touched

- `scripts/manage_research_report_clone_segment.py`: proof schema, validator, builder, and CLI.
- `scripts/execute_research_report_clone_batch.py`: required pre-API quiescence gate and proof path.
- `tests/test_manage_research_report_clone_segment.py`: proof acceptance/rejection and checkpoint binding coverage.
- `tasks/todo.md`: T-617 progress and handoff references.

## Commands Run

```bash
python3 -m py_compile scripts/manage_research_report_clone_segment.py scripts/execute_research_report_clone_batch.py tests/test_manage_research_report_clone_segment.py
python3 -m unittest tests.test_manage_research_report_clone_segment tests.test_execute_research_report_clone_batch tests.test_probe_research_report_clone_runtime
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
make local-ci
```

Result:

- Passed: 11 focused tests, security scan (550 files), handoff validation, compile, diff check.
- Passed: full CI with the declared `.venv` dependency set; 541 tests plus UI, security, links, handoffs, and metadata checks.
- Not run: any real clone execution or database mutation.

## Evidence

- Focused test output: local-only, generated 2026-07-21, no sensitive data, not a non-local release gate.
- No runtime/database artifact produced; batch 0006 remains blocked.

## Decisions

- Require the proof on the actual executor CLI rather than relying only on preflight documentation.
- Do not automatically stop the primary scheduler from this tool; operator-controlled service lifecycle remains auditable and reversible.

## Risks and Open Questions

- The direct observer still requires operator-supplied unit/container names; it does not stop services automatically. Unknown systemd states and missing writer-container identities are rejected.

## Handoff Checklist

- [x] Code changes completed
- [x] Focused tests run
- [x] Docs/contracts updated
- [x] Roadmap status updated

## Next Steps

1. Run `observe-proof` during a controlled quiescent window with the actual scheduler and writer container names.
2. Prepare a new batch 0006 preflight only after a fresh quiescence proof and human approval.
3. Keep the primary baseline and no-broker boundary unchanged.

## Next Recommended Action

Generate a direct quiescence proof in a controlled window before preparing any batch 0006 approval.
