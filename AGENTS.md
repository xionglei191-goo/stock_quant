# AGENTS.md

## 1. Purpose

This document is the operating manual for all human developers, Codex agents, and delegated sub-agents working in this repository.

The project is a local-first AI native investment research system. It supports public/local data ingestion, evidence tracking, research workflows, governance, simulated portfolio feedback, audits, and readiness evidence. It does not connect to real brokers, does not place orders, and does not provide automated live trading.

The main coordination goal is to reduce memory loss between agent sessions. Every non-trivial task must leave a written handoff that allows another agent to continue without guessing.

## 2. Repository Scope

This `AGENTS.md` applies to the whole repository.

Primary project references:

- `README.md`: run, deployment, and local production entry points.
- `tasks/todo.md`: authoritative roadmap, task status, blockers, and PM priorities.
- `docs/README.md`: document index.
- `docs/api-contracts.md`: API and workflow contracts.
- `docs/system-architecture.md`: architecture principles and target topology.
- `docs/production-runbook.md`: deployment, backup, rollback, and operations.
- `artifacts/`: local evidence, readiness reports, and generated acceptance outputs.

## 3. Project Boundaries

All agents must preserve these boundaries:

- Research and evidence come before portfolio simulation.
- Public, local, or explicitly provided data comes before automation.
- All portfolio and execution flows are paper/simulated only.
- No real broker integration.
- No automatic order execution.
- No training on restricted research reports, transcripts, or unclear third-party content.
- Boundary-unclear data may enter manual reference only, not automated fact or training layers.
- Production closure for non-local organizational release requires real staging/production artifact URI, artifact inventory, and release gate validation.

## 4. Development Groups

Use these groups when assigning tasks to sub-agents. Each task has one owner group and may have reviewer groups.

### 4.1 PM / Release Coordination

Owns roadmap, task status, milestones, release evidence, cross-group dependency tracking, and handoff quality.

Typical files:

- `tasks/todo.md`
- `docs/README.md`
- readiness and closure scripts under `scripts/`
- release artifacts under `artifacts/`

### 4.2 Platform and Quality

Owns configuration, test isolation, CI commands, dependency declarations, storage adapters, deployment scripts, Docker/Compose, and service health.

Typical files:

- `pyproject.toml`
- `Dockerfile`
- `docker-compose.yml`
- `app/server.py`
- `app/store.py`
- `app/object_store.py`
- `app/search.py`
- `scripts/security_check.py`
- test and CI support scripts

### 4.3 Data and Evidence

Owns A/H/U source ingestion, market data, research report assets, source governance, rights tags, document parsing boundaries, evidence extraction, and benchmark inputs.

Typical files:

- `app/connectors.py`
- `app/document_parser.py`
- `app/research_reports.py`
- `app/tdx_market_data.py`
- ingestion and backfill scripts under `scripts/`
- benchmark and data artifacts under `artifacts/`

### 4.4 Research and AI Workflows

Owns LLM task templates, prompt governance, research answers, hotspot expansion, chokepoint research, workflow orchestration, reranking, model/version lineage, and manual review loops.

Typical files:

- `app/llm_gateway.py`
- research, LLM, graph, workflow, and extraction sections of `app/services.py`
- `docs/chokepoint-research-module.md`
- LLM, benchmark, graph, and orchestration scripts

### 4.5 Product and UI

Owns `/ui`, static UI contract, dashboards, research workbench, graph views, investment committee views, cross-browser acceptance, and interaction acceptance.

Typical files:

- `app/static/index.html`
- `scripts/ui_static_check.py`
- `scripts/ui_browser_acceptance.py`
- `scripts/ui_interaction_acceptance.py`
- `scripts/ui_cross_browser_matrix_check.py`

### 4.6 Governance, Security, and Compliance

Owns permissions, role policy, audit completeness, source review, secret rotation metadata, red/yellow/green data boundaries, cache retention, and non-local release security gates.

Typical files:

- authorization and governance sections of `app/api.py`
- governance, security, readiness, and alerting sections of `app/services.py`
- `docs/us-compliance-open-questions.md`
- security and staging governance scripts

## 5. Task Intake Standard

Before starting any non-trivial task, the owner agent must create or restate a task brief in the conversation or in the handoff record.

Task brief fields:

- `task_id`: Use an existing `T-###` from `tasks/todo.md` when available.
- `owner_group`: One group from section 4.
- `reviewer_groups`: Groups that must review the result.
- `objective`: One or two concrete sentences.
- `scope`: Files, modules, APIs, scripts, or docs expected to change.
- `out_of_scope`: Explicitly list what must not change.
- `acceptance`: Commands, checks, artifacts, or review gates required.
- `risk_level`: low, medium, high, or critical.
- `handoff_path`: Planned handoff document path if the task is not completed in one turn.

Default handoff path:

```text
docs/agent-handoffs/YYYY-MM-DD-TASKID-short-slug.md
```

The handoff directory and template are available at:

- `docs/agent-handoffs/README.md`
- `docs/agent-handoffs/TEMPLATE.md`

## 6. Mandatory Handoff Record

A written handoff is mandatory when any of the following is true:

- The task spans more than one agent turn or more than one sub-agent.
- The task changes code, tests, deployment scripts, data pipelines, API contracts, UI contracts, or readiness gates.
- The task leaves failing tests, known gaps, blocked dependencies, or follow-up work.
- The task produces or consumes artifacts that future agents must understand.
- The task makes a design decision not obvious from the code.
- The task crosses agent or owner-group boundaries.

Before merge, any cross-agent or cross-group task must leave a current handoff record under `docs/agent-handoffs/`.

Handoff records must be concise but complete. Do not write stream-of-consciousness notes. Write what the next agent needs.

Required handoff template:

````markdown
# Handoff: <TASKID> <Short Title>

## Status

- Status: TODO | DOING | DONE | BLOCKED
- Owner group:
- Last updated:
- Last agent:
- Branch/worktree:

## Objective

<What this task is trying to achieve.>

## Current State

- Completed:
- In progress:
- Not started:
- Blocked:

## Files Touched

- `path`: <what changed and why>

## Commands Run

```bash
<command>
```

Result:

- Passed:
- Failed:
- Not run:

## Decisions

- <Decision, reason, alternatives rejected if important.>

## Risks and Open Questions

- <Risk or question>

## Artifacts

- `artifact path or URI`: <producer, purpose, freshness, whether it is local-only or production-grade>

## Next Steps

1. <Concrete next action>
2. <Concrete next action>
3. <Concrete next action>
````

## 7. Documentation Standards

Every project document added or materially updated by an agent must follow these standards:

- Start with a clear title and purpose.
- State status: draft, active, superseded, or local-only evidence.
- State owner group and last updated date.
- Link to related task IDs from `tasks/todo.md`.
- Separate facts, decisions, assumptions, and open questions.
- Record commands and artifact paths for reproducibility.
- Never include secrets, API keys, private tokens, signed result URLs, or complete model responses.
- Mark local-only evidence clearly. Local evidence must not be presented as non-local production release evidence.
- Prefer references to exact files, scripts, artifact IDs, and API paths over narrative summaries.

Recommended document header:

```markdown
# <Document Title>

- Status:
- Owner group:
- Last updated:
- Related tasks:
- Scope:
- Non-goals:
```

## 8. Code and Change Standards

All agents must follow these standards:

- Read existing code and docs before editing.
- Keep changes scoped to the task.
- Do not revert user or other-agent changes unless explicitly instructed.
- Preserve the local-only, simulated-only project boundary.
- Use existing patterns before introducing new abstractions.
- Add tests when behavior changes.
- Update docs when contracts, scripts, environment variables, APIs, or readiness gates change.
- Keep artifact churn out of commits unless the artifact is an intended evidence deliverable.
- When splitting `app/services.py`, preserve `SystemService` as a facade until API compatibility is proven.

### 8.1 SystemService Growth Freeze

New business behavior must not be added directly to `app/services.py` by default. The default destination is a domain module under `app/service_modules/` or another established domain file.

Allowed `SystemService` changes:

- facade methods that preserve existing API compatibility
- cross-module orchestration that cannot live inside one domain module
- compatibility shims during gradual extraction
- audit/permission/store plumbing needed by existing public methods

Every handoff that touches `app/services.py` or `SystemService` must include a `SystemService Growth Freeze Review` section stating:

- whether new `SystemService` business logic was added
- why a domain module was or was not used
- what focused regression protects the facade behavior
- whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed

Do not mark the task done until this review is present and the relevant facade or golden API regression has passed.

## 9. Verification Standards

Default checks for code changes:

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
```

Equivalent single command:

```bash
make local-ci
```

Current caveat: until the configuration isolation task is completed, direct unit tests may be polluted by local `.env` values. If the machine has a production-like `.env`, use a clean local test environment and record the exact command in the handoff.

Suggested clean test pattern:

```bash
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
```

Verification notes:

- If a check is not run, explain why.
- If a check fails, record the first failing test, root cause if known, and whether it is related to the task.
- Do not hide failures caused by environment drift.
- UI work must include `scripts/ui_static_check.py`; browser-level work should include the relevant UI acceptance script when feasible.
- Security/governance work must include `scripts/security_check.py .`.

## 9.1 Handoff Validation

Run `python3 scripts/check_handoffs.py` before merge when `docs/agent-handoffs/` changes or when a task crosses agents/groups.

## 10. Artifact Standards

Artifacts must be named, scoped, and classified.

Artifact classification:

- `local-only`: valid for this machine or local Compose stack only.
- `staging-local`: local staging simulation; not valid for non-local release.
- `external-staging`: real external staging evidence.
- `production`: real production evidence.
- `example`: template or sample, not a release gate input.

Every artifact referenced in a handoff must state:

- producer command or API
- generated timestamp if available
- environment
- owner group
- whether it contains sensitive data
- whether it is acceptable for non-local production release gates

Do not commit large or machine-specific artifacts unless the task explicitly requires evidence files to be versioned.

## 11. Sub-Agent Delegation Protocol

When calling a sub-agent, provide a compact packet:

```markdown
## Sub-agent Task Packet

- Task ID:
- Owner group:
- Objective:
- Must read:
- Files likely touched:
- Do not touch:
- Acceptance checks:
- Expected handoff path:
- Known risks:
```

Sub-agent output must include:

- summary of work
- files changed
- tests run and results
- unresolved risks
- exact next step if not complete

The parent agent remains responsible for integrating sub-agent output, resolving conflicts, and updating the final handoff.

## 12. Memory Recovery Procedure

When an agent starts with limited context or after compaction, do this before editing:

1. Read `AGENTS.md`.
2. Read the relevant section of `tasks/todo.md`.
3. Read the latest handoff for the task if one exists.
4. Run `git status --short`.
5. Inspect relevant diffs before touching files.
6. Reconstruct current objective, blockers, and acceptance checks.
7. Continue from current state instead of restarting from scratch.

If the task cannot be reconstructed confidently, ask for a narrow clarification or create a status-only handoff describing the ambiguity.

## 13. Completion Criteria

A task is complete only when:

- Required code or doc changes are made.
- Relevant tests or checks are run, or skipped with a documented reason.
- `tasks/todo.md` status is updated when the task changes roadmap state.
- API, environment, artifact, or UI contract changes are documented.
- A handoff exists if the task meets the mandatory handoff criteria.
- No known unrelated user changes were reverted.

Do not mark a task `DONE` just because the current agent session is ending.
