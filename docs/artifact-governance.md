# Artifact Governance

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-05-28
- Related tasks: T-429
- Scope: local artifact submission rules, handoff evidence hygiene
- Non-goals: non-local production evidence approval policy

## Classification

Use one of four classes for generated files:

1. `functional_change`: source code and tests required for behavior.
2. `documentation_change`: docs, ADRs, handoffs, checklists.
3. `evidence_artifact`: reproducible readiness/acceptance outputs required by a task gate.
4. `temporary_output`: local debug/log/intermediate files, never required for commit.

## Commit Policy

1. Always commit `functional_change` and `documentation_change` tied to task scope.
2. Commit `evidence_artifact` only when the task explicitly requires archived evidence.
3. Do not commit `temporary_output`; add to `.gitignore` when recurring.
4. Every committed artifact must include owner, generation command, and freshness date in task notes or handoff.

## Local CI Gate

Run:

```bash
make local-ci
```

This chains compile, unit tests, UI static contract, security scan, and handoff validation.
