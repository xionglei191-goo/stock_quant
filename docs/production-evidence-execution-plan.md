# Production External Evidence Execution Plan

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-06-27
- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421
- Scope: PM execution plan for collecting real external evidence, validating inventory, running release gate, and finalizing task status
- Non-goals: generating evidence, accepting local-only artifacts, changing task status without strict release gate, broker integration, automatic trading

## Summary

- Execution status: `waiting_for_external_evidence`
- Owners: 6
- Tasks: 17
- Artifact fields: 81
- Ready tasks: 0
- Waiting tasks: 17
- Placeholder URIs: 81
- Boundary: execution plan only; it is not release evidence and cannot mark tasks DONE without real external artifacts and a passed release gate

## Owner Runs

### CIO

- Owner group: Research and AI Workflows / Portfolio
- Tasks: T-408, T-409
- Artifact fields: 7
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-408-production-evidence.md`
  - `docs/production-evidence-task-packets/t-409-production-evidence.md`

### NLP/ML 负责人

- Owner group: Research and AI Workflows
- Tasks: T-402, T-410, T-418
- Artifact fields: 15
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-402-production-evidence.md`
  - `docs/production-evidence-task-packets/t-410-production-evidence.md`
  - `docs/production-evidence-task-packets/t-418-production-evidence.md`

### 分析师

- Owner group: Research and AI Workflows
- Tasks: T-406A
- Artifact fields: 4
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-406a-production-evidence.md`

### 平台负责人

- Owner group: Platform and Quality
- Tasks: T-404, T-407, T-411, T-412, T-419, T-420
- Artifact fields: 35
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-404-production-evidence.md`
  - `docs/production-evidence-task-packets/t-407-production-evidence.md`
  - `docs/production-evidence-task-packets/t-411-production-evidence.md`
  - `docs/production-evidence-task-packets/t-412-production-evidence.md`
  - `docs/production-evidence-task-packets/t-419-production-evidence.md`
  - `docs/production-evidence-task-packets/t-420-production-evidence.md`

### 数据工程

- Owner group: Data and Evidence
- Tasks: T-405, T-406, T-416
- Artifact fields: 12
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-405-production-evidence.md`
  - `docs/production-evidence-task-packets/t-406-production-evidence.md`
  - `docs/production-evidence-task-packets/t-416-production-evidence.md`

### 风险/合规

- Owner group: Governance, Security, and Compliance
- Tasks: T-414, T-421
- Artifact fields: 8
- Exit criteria: All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.
- Task packets:
  - `docs/production-evidence-task-packets/t-414-production-evidence.md`
  - `docs/production-evidence-task-packets/t-421-production-evidence.md`

## Execution Phases

### P1 Owner evidence collection

- Exit criteria: Every owner replaces placeholder URIs with concrete external staging/production archive URIs.

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
```

### P2 Artifact inventory

- Exit criteria: Every evidence URI has sha256, size, environment, producer, owner, retention, and immutable/object-lock metadata.

```bash
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
```

### P3 Strict release gate

- Exit criteria: The filled plan, readiness evidence package, artifact inventory, generated manifest, and optional closure dry-run all pass.

```bash
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```

### P4 Task status finalization

- Exit criteria: Only tasks covered by a passed strict release gate are moved from BLOCKED to DONE.

```bash
python3 scripts/production_task_status_finalize.py --todo tasks/todo.md --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --manifest artifacts/production-closure-manifest.json
```

## Required Inputs

- `artifacts/production-evidence-collection-plan.json with real external URIs`
- `artifacts/readiness-evidence-package.json exported from the real staging/production system`
- `artifacts/production-artifact-inventory.json covering every evidence URI`
- `artifacts/production-evidence-bundle/ when local bundle hash verification is required`

## Completion Rule

The remaining BLOCKED tasks are complete only after the filled evidence plan, readiness evidence package, artifact inventory, generated manifest, and strict release gate all pass with real external staging/production evidence. This plan is a coordination artifact, not release evidence.
