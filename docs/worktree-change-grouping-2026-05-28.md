# Worktree Change Grouping (2026-05-28)

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-05-28
- Related tasks: T-425, T-426, T-427, T-428, T-429, T-406B
- Scope: classify current local worktree changes for handoff clarity and provide safe commit sequence
- Non-goals: this file is not a permanent release manifest

## Grouping Rules

- `functional_change`: affects runtime behavior or tests.
- `documentation_change`: ADR, checklist, handoff, README/index updates.
- `evidence_or_audit_support`: scripts that produce or validate evidence.
- `temporary_or_out_of_scope`: local files not required by current task chain.

## Current Grouping Summary

### task_chain_t425_to_t429

#### functional_change

- `app/server.py`: `.env` import side-effect removed; lazy router; non-local auth mode startup gate.
- `app/utils.py`: adds `env_text` / `env_int` / `env_float`.
- `app/llm_gateway.py`: unified env parsing, request timeout handling, hard timeout, payload timeout field stripping.
- `app/document_parser.py`: unified env parsing for timeout/poll/max poll.
- `scripts/staging_acceptance.py`: env float parsing for capacity thresholds.
- `scripts/ui_static_check.py`: adds required IDs/functions for current UI contract.
- `tests/test_system.py`: env isolation fixture; dotenv import isolation tests; env empty-string parse tests; UI contract dynamic assertions; non-local auth gate test.

#### dependency_and_runtime_alignment

- `pyproject.toml`: adds build-system and `test`/`ui-acceptance` extras.
- `Dockerfile`: uses project extras install instead of manually pinned ad hoc runtime deps.

#### evidence_or_audit_support

- `Makefile`: adds `local-ci` chain and `check-handoffs`.
- `scripts/check_handoffs.py`: handoff schema validator.

#### documentation_change

- `README.md`: install/test matrix and `make local-ci` usage.
- `AGENTS.md`: team workflow and mandatory handoff standards.
- `docs/README.md`: adds links for new governance/ADR/handoff docs.
- `docs/pr-checklist.md`: merge checklist with multi-agent handoff gate.
- `docs/artifact-governance.md`: artifact class and commit policy.
- `docs/agent-handoffs/README.md`: handoff folder usage.
- `docs/agent-handoffs/TEMPLATE.md`: handoff template.
- `docs/agent-handoffs/2026-05-28-T-424-test-isolation.md`: completed handoff with verification evidence.
- `docs/systemservice-modularization-adr.md`: T-427 ADR.
- `docs/security-boundary-modes-adr.md`: T-428 ADR.
- `tasks/todo.md`: PM section updates for T-424~T-429 `DONE`.

### task_t406b_chokepoint_feature

#### functional_change

- `app/models.py`: adds `ChokepointResearchRun`.
- `app/store.py`: adds chokepoint collection and dirty-collection commit optimization support.
- `app/api.py`: adds chokepoint run/readiness/finalize/review/task endpoints.
- `app/services.py`: adds chokepoint templates, run pipeline, finalize, review, verification tasks, readiness report wiring.
- `app/static/index.html`: adds chokepoint workbench UI and pipeline interaction.
- `tests/test_system.py`: chokepoint run/pipeline/fallback verification tests.
- `app/service_modules/__init__.py`: service module exports.
- `app/service_modules/common.py`: extracted `safe_identifier()`.

#### documentation_change

- `docs/chokepoint-research-module.md`: feature direction and boundary notes.
- `docs/api-contracts.md`: chokepoint API contract sections.
- `tasks/todo.md`: adds T-406B `DONE`.

### temporary_or_out_of_scope (requires owner decision before commit)

- `aleabitoreddit_articles.html`
- Any local-only generated artifacts not explicitly referenced by task acceptance

## Commit Sequence Recommendation

### Option A (preferred): isolate task chain first, chokepoint second

1. Commit T-425 + T-428 (config isolation + security startup gate)
   - files:
     - `app/server.py`
     - `app/utils.py`
     - `app/llm_gateway.py`
     - `app/document_parser.py`
     - `scripts/staging_acceptance.py`
     - `tests/test_system.py` (only non-chokepoint hunks)
     - `docs/agent-handoffs/2026-05-28-T-424-test-isolation.md`
2. Commit T-424 (UI static contract test convergence)
   - files:
     - `scripts/ui_static_check.py`
     - `tests/test_system.py` (UI contract dynamic assertion hunks)
3. Commit T-426 (dependency/runtime alignment)
   - files:
     - `pyproject.toml`
     - `Dockerfile`
     - `README.md`
4. Commit T-427 (service modularization phase 1 + ADR)
   - files:
     - `app/service_modules/__init__.py`
     - `app/service_modules/common.py`
     - `app/services.py` (safe_identifier/env helper hunks only)
     - `docs/systemservice-modularization-adr.md`
5. Commit T-429 (governance/checklist/local-ci/handoff policy)
   - files:
     - `Makefile`
     - `scripts/check_handoffs.py`
     - `AGENTS.md`
     - `docs/agent-handoffs/README.md`
     - `docs/agent-handoffs/TEMPLATE.md`
     - `docs/pr-checklist.md`
     - `docs/artifact-governance.md`
     - `docs/worktree-change-grouping-2026-05-28.md`
     - `docs/README.md`
     - `tasks/todo.md`
6. Commit T-406B (feature)
   - files:
     - `app/models.py`
     - `app/store.py`
     - `app/api.py`
     - `app/services.py` (chokepoint feature hunks)
     - `app/static/index.html`
     - `tests/test_system.py` (chokepoint test hunks)
     - `docs/chokepoint-research-module.md`
     - `docs/api-contracts.md`
     - `tasks/todo.md` (T-406B section)

### Option B (single integrated commit)

Only acceptable if reviewer explicitly agrees to merge mixed-scope changes in one PR. Not recommended due to cross-group review complexity.

## Notes For Mixed Files

- `tests/test_system.py`, `app/services.py`, and `tasks/todo.md` contain mixed hunks across multiple tasks.
- Use `git add -p` for these files if splitting by task.
- Do not include `aleabitoreddit_articles.html` in functional/doc commits.
