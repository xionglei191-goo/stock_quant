# Handoff: T-459 Deep Profile Coverage UI

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, main
- Related task: T-459

## Objective

Expose company profile deep-field coverage, official/IR profile field extraction and company database quality reconciliation in the company intelligence workbench.

## Scope

- In scope: `/ui` controls, dry-run-first UI actions, visible summary tables, UI static contract, browser interaction acceptance, roadmap and handoff docs.
- Out of scope: backend API changes, external downloads, paid data vendors, persistent extraction run table, true broker execution or live trading.

## Background

T-456 added deep profile field coverage audit, T-457 added official/IR profile field extraction and T-458 added event/relationship deduplication, entity alias merge candidates and source quality scoring. Before T-459 these capabilities were available through API only and were not visible in the company intelligence workbench.

## Problem Statement

Users could see coarse company database coverage, run history and coverage trends, but could not operate on the most important new database-quality capabilities from the workbench: which company profile fields are missing, which official/IR evidence can fill them, and whether event/relationship records need local quality reconciliation.

## Expected Deliverables

- Visible deep profile field coverage audit in the company intelligence workbench.
- Visible official/IR profile field extraction preview and explicit execute action.
- Visible event/relationship quality reconciliation preview and explicit execute action.
- UI static and browser interaction checks covering the new dry-run paths.
- Updated roadmap, docs index and handoff.

## Agent Findings

- UI explorer agent confirmed the smallest surface is the existing `公司数据库补齐` panel in `app/static/index.html`.
- Backend/API explorer agent confirmed no backend change is required if the UI calls the existing companion endpoints directly.
- Both agents noted that `/api/company-intelligence/{symbol}` is a coarse aggregate and does not currently include T-456/T-457/T-458 outputs.

## Current Findings

- The existing workbench already has company-scoped payload helpers and status tables that can be reused.
- T-456/T-457/T-458 backend unit tests already cover the API behavior, so this task is primarily UI integration.
- New browser acceptance should use dry-run calls to avoid mutating local demo state.

## Proposed Work Plan

1. Add controls, status boxes and tables to the existing company database panel.
2. Add JavaScript payload builders, renderers and API actions for the three T-459 workflows.
3. Register new event listeners and update static UI contract.
4. Add browser acceptance checks for deep-field audit, extraction preview and quality reconcile preview.
5. Update roadmap, document index and handoff.

## Validation Plan

- Run `python3 scripts/ui_static_check.py`.
- Run `python3 scripts/check_handoffs.py`.
- Run `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Run focused UI static contract unit test.
- Run browser interaction acceptance when a local server is available.

## Current State

- Completed: added workbench controls for profile field list, evidence requirement, refresh-existing toggle, deep-field audit, field extraction preview/execute and quality reconciliation preview/execute.
- Completed: deep-field audit calls `POST /api/company-database/profile-field-coverage/audit`.
- Completed: field extraction calls `POST /api/company-database/profile-fields/extract`, defaults to dry-run, and refreshes deep-field audit plus company intelligence after execute.
- Completed: quality reconciliation calls `POST /api/company-database/quality/reconcile`, defaults to dry-run, and refreshes company intelligence after execute.
- Completed: UI tables show field coverage, extraction candidates, duplicate groups, entity aliases and source quality scores.
- Completed: static UI contract and browser interaction acceptance include the new controls and dry-run paths.
- Blocked: none.

## Files Touched

- `app/static/index.html`: added T-459 controls, status boxes, tables, renderers and API actions.
- `scripts/ui_static_check.py`: added new required IDs and JS functions.
- `scripts/ui_interaction_acceptance.py`: added diagnostics and dry-run browser checks for deep-field audit, profile field extraction and quality reconciliation.
- `tasks/todo.md`: added T-459 as done.
- `docs/README.md`: updated document index to include T-459.
- `docs/agent-handoffs/README.md`: added T-459.
- `docs/agent-handoffs/2026-06-24-T-459-deep-profile-coverage-ui.md`: this handoff.

## Commands Run

```bash
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
```

Result:

- Passed: `python3 scripts/ui_static_check.py`.
- Passed: `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Passed: focused UI static contract unit test.
- Passed: browser interaction acceptance after restarting the Docker Compose `ai-quant-org` service to load current routes; 18 checks passed, including T-459 deep-field audit, field extraction preview and quality reconcile preview.
- Passed: full clean-env unit discovery, 240 tests.
- Failed then fixed: initial `python3 scripts/check_handoffs.py` because this handoff missed required repository sections; fixed and rerun.

## Decisions

- Used direct companion APIs instead of expanding `/api/company-intelligence/{symbol}` in this slice.
- Kept field extraction and reconciliation dry-run-first in the UI; execute buttons are explicit.
- Kept `require_evidence` enabled by default for profile extraction, aligning with company fact-source boundaries.
- Did not add new data sources; this slice only exposes already implemented local database operations.

## Dependencies

- Existing T-456 profile deep-field coverage API.
- Existing T-457 profile field extraction API.
- Existing T-458 company database quality reconciliation API.
- Existing company intelligence workbench payload helpers and UI acceptance infrastructure.

## Blockers

- None.

## Risks and Open Questions

- Browser acceptance execute paths can mutate local demo state; new T-459 browser checks intentionally cover dry-run paths only.
- Deep-field extraction is rule-based and conservative; UI may show zero candidates until official/IR documents and evidence are ingested.
- A future backend aggregate may add deep-field coverage and quality summaries directly to `/api/company-intelligence/{symbol}` for one-call page load.

## Artifacts

- None committed. No external downloads, non-local production evidence or generated release artifacts.

## Handoff Checklist

- [x] Deep-field audit UI added.
- [x] Profile field extraction UI added.
- [x] Quality reconciliation UI added.
- [x] UI static contract updated.
- [x] Browser acceptance dry-run checks added.
- [x] Todo and docs index updated.
- [x] Final validation completed after required-section fix.

## Evidence

Commands run:

```bash
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/check_handoffs.py
python3 -m unittest tests.test_system.SystemServiceTests.test_ui_static_contract_matches_target_information_architecture
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000
bash -lc 'while IFS= read -r key; do export "$key="; done < <(sed -n -E "s/^\s*(export\s+)?(AI_QUANT_[A-Z0-9_]+)=.*/\2/p" .env 2>/dev/null); export AI_QUANT_OBJECT_STORE_BACKEND=local; export AI_QUANT_OBJECT_STORE="/tmp/ai_quant_test_objects"; export AI_QUANT_SEARCH_BACKEND=local; export AI_QUANT_LLM_TIMEOUT_SECONDS=120; export AI_QUANT_ANTHROPIC_VERSION=2023-06-01; export AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS=60; export AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS=0.01; export AI_QUANT_PADDLEOCR_MAX_POLLS=1; python3 -m unittest discover -s tests'
```

Result:

- Passed: UI static check, Python compile, handoff validation, focused UI unit, browser interaction acceptance and full clean-env unit discovery.
- Failed then fixed: handoff validation required additional sections in this file.
- Browser evidence: `status=passed`, `failure_count=0`, `check_count=18`, `evidence_uri=artifact://ui-interaction-acceptance/ui-interaction-acceptance`.
- Unit evidence: 240 tests passed.

## Next Steps

1. Run validation and update this handoff command results if any command differs from the expected result.
2. Continue from T-406C/T-406D/T-406E or add the next company database task for richer official source ingestion, depending on PM priority.

## Next Recommended Action

Run final validation, then continue with richer company data-source ingestion or Chokepoint quality baseline depending on PM priority.
