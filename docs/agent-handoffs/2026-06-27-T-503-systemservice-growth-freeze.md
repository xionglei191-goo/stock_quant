# Handoff: T-503 SystemService Growth Freeze

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination, Platform and Quality
- Reviewer groups: Data and Evidence, Research and AI Workflows, Product and UI
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-503

## Objective

Prevent new features from continuing to accumulate directly in `app/services.py` by documenting a service-layer growth freeze and enforcing a handoff review whenever `SystemService` is touched.

## Scope

- In scope: development rules, PR checklist, handoff validation, task status, and handoff.
- Out of scope: additional runtime refactoring, API schema changes, database migrations, and UI changes.

## Background

T-500 extracted the first company-intelligence domain helpers while preserving `SystemService` as a facade. T-503 turns that migration direction into a durable rule for future tasks.

## Problem Statement

Without a written and validated freeze rule, future tasks can keep adding domain behavior directly to the already large service facade, undoing the modularization work and increasing regression risk.

## Expected Deliverables

- `AGENTS.md` records the growth freeze rule.
- PR checklist includes the service-layer review gate.
- Handoff validation requires a `SystemService Growth Freeze Review` section when relevant.
- `tasks/todo.md` marks T-503 done.

## Current Findings

- `docs/agent-handoffs/` already has a central checker.
- Existing future-facing handoffs that mention `SystemService` should be explicit about facade vs domain-module logic.
- The freeze rule should not block compatibility shims or orchestration in `SystemService`; it should force justification and regression evidence.

## Proposed Work Plan

1. Add the freeze rule to `AGENTS.md`.
2. Add PR checklist items.
3. Extend `scripts/check_handoffs.py`.
4. Add the required review section to T-500 and T-503 handoffs.
5. Mark T-503 done and run validation.

## Validation Plan

- `python3 scripts/check_handoffs.py`
- `python3 -m py_compile scripts/check_handoffs.py`
- `python3 scripts/security_check.py .`
- `git diff --check`

## Risks

- The rule is intentionally lightweight; it does not parse code diffs.
- Existing handoffs that mention `SystemService` may need the review section when they are next touched.
- `SystemService` remains a facade, so some orchestration will continue to live there with explicit justification.

## Dependencies

- T-500 modularization.
- `docs/agent-handoffs/` validation convention.
- `AGENTS.md` as the repository operating manual.

## Blockers

- None.

## Handoff Checklist

- [x] Growth freeze rule documented.
- [x] PR checklist updated.
- [x] Handoff checker updated.
- [x] Relevant handoffs include growth-freeze review.
- [x] `tasks/todo.md` marked T-503 DONE.

## Evidence

- `AGENTS.md`: SystemService Growth Freeze section.
- `docs/pr-checklist.md`: merge gate additions.
- `scripts/check_handoffs.py`: conditional handoff section check.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no.
- Domain module usage: not applicable; this is governance/checking work.
- Focused regression: `python3 scripts/check_handoffs.py` and `python3 -m py_compile scripts/check_handoffs.py`.
- API schema, storage schema, UI behavior, and paper-only/no-broker boundary changes: none.

## Next Recommended Action

Use T-503 as the default rule for all future backend tasks: new domain behavior belongs in modules, while `SystemService` remains the compatibility facade and orchestration layer.
