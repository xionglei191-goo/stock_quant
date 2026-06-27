# Handoff: T-499 Non-Local Production Readiness

## Metadata

- Status: DONE
- Owner group: Governance, Security, and Compliance
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-499

## Objective

Clarify the gap between local personal operation and non-local organizational release, and provide a durable readiness package that prevents local-only evidence from being treated as production evidence.

## Scope

- In scope: non-local production readiness package, evidence template, local/staging/production boundary matrix, validation script, task status, and handoff.
- Out of scope: real deployment integration, API schema changes, broker integration, automatic trading, database migration, and runtime behavior changes.

## Background

The repository already includes staging and production evidence scripts, local production stack scripts, artifact validation, and a security boundary ADR. T-499 consolidates those pieces into a PM/governance package for future non-local release.

## Problem Statement

The system is usable locally, but a non-local organizational release requires explicit proof for auth, secrets, backup, source authorization, immutable artifact inventory, monitoring, and release gates. Without a single package, future work could accidentally cite local-only artifacts as production evidence.

## Expected Deliverables

- A readiness document with local/staging/production differences.
- A required evidence template for non-local release.
- A checklist connecting API permissions, trace/audit, secret, object store, and search backend requirements.
- A validation script that enforces the document contract.
- `tasks/todo.md` updated to mark T-499 complete.

## Current Findings

- `docs/security-boundary-modes-adr.md` already requires non-local deployments to reject header-only auth.
- `docs/production-runbook.md` already documents strict filled URI and release gate commands.
- `app/readiness_artifacts.py` already rejects local/staging-local/demo artifact prefixes for production closure.
- T-499 can complete without runtime changes by making the readiness package explicit and checkable.

## Proposed Work Plan

1. Add `docs/non-local-production-readiness-package.md`.
2. Add `scripts/non_local_production_readiness_check.py`.
3. Link the document from `docs/README.md`.
4. Mark T-499 DONE in `tasks/todo.md`.
5. Run static, security, and handoff checks.

## Validation Plan

- `python3 scripts/non_local_production_readiness_check.py`
- `python3 -m py_compile app/*.py app/service_modules/*.py tests/test_system.py scripts/*.py`
- `python3 scripts/security_check.py .`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Risks

- The package is a preparation artifact, not actual external staging evidence.
- Future non-local release still needs real external artifact URIs, immutable inventory, and organizational sign-off.
- The local personal workflow must remain low-friction and should not inherit production auth complexity.

## Dependencies

- `docs/security-boundary-modes-adr.md`
- `docs/production-runbook.md`
- `scripts/production_release_gate.py`
- `scripts/production_evidence_plan_check.py`
- `scripts/production_artifact_inventory_check.py`
- `app/readiness_artifacts.py`

## Blockers

- None for T-499 local completion.

## Handoff Checklist

- [x] Non-local readiness package created.
- [x] Evidence template covers auth, permission, secrets, backup, source audit, inventory, monitoring, release gate, and paper-only boundary.
- [x] Local-only evidence rejection is explicit.
- [x] Validation script added.
- [x] `tasks/todo.md` marked T-499 DONE.

## Evidence

- `docs/non-local-production-readiness-package.md`: active readiness package and evidence template.
- `scripts/non_local_production_readiness_check.py`: document contract validator.

## Next Recommended Action

Proceed to T-500 SystemService company-intelligence modularization. Treat T-499 as a non-local release preparation package, not a production approval record.
