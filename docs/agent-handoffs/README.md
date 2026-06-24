# Agent Handoffs

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-06-24
- Related tasks: T-406C, T-424, T-425, T-426, T-427, T-428, T-429, T-431, T-432, T-433, T-434, T-435, T-436, T-437, T-438, T-439, T-440, T-441, T-442, T-443, T-444, T-445, T-446, T-447, T-448, T-449, T-450, T-451, T-452, T-453, T-454, T-455, T-456, T-457, T-458
- Scope: Standard handoff records for multi-agent and cross-group development
- Non-goals: This folder does not replace `tasks/todo.md` as the roadmap authority

## Purpose

This folder stores task handoff records so another agent can continue work without relying on memory.

## Naming Rule

Use one file per active handoff:

```text
YYYY-MM-DD-TASKID-short-slug.md
```

Examples:

- `2026-05-28-T-406-chokepoint-quality-package-c.md`
- `2026-05-28-T-424-test-isolation.md`
- `2026-05-29-T-427-service-split-phase1.md`

If a roadmap item uses a lettered subtask such as `T-406C`, keep the filename compatible with `scripts/check_handoffs.py` by using the numeric parent task ID in the filename and putting the lettered subtask in the slug or document body.

Example:

- `2026-05-28-T-406-chokepoint-quality-package-c.md`

## Required Contents

Every handoff file must include:

1. Status and owner
2. Objective and scope
3. Current state and blockers
4. Files touched
5. Commands run and results
6. Decisions and rationale
7. Risks and open questions
8. Artifact references with boundary label (`local-only`, `staging-local`, `external-staging`, `production`, `example`)
9. Next actions

Use [TEMPLATE.md](./TEMPLATE.md) as the starting point.

## Lifecycle

1. Create handoff when task spans multiple turns, multiple agents, or leaves unresolved work.
2. Update in place while task remains active.
3. Keep final state accurate (`DONE` or `BLOCKED`) before closing.
4. Do not delete old handoffs unless explicitly requested.

## Sensitive Data Rule

Do not include secrets, API keys, tokens, private URLs, or full model responses in handoff files.
