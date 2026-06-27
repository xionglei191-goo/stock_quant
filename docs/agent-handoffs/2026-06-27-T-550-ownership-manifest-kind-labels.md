# Handoff: T-550 股权 manifest 默认类型显示中文且保留 raw 追溯

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-550
- Handoff type: implementation
- Roadmap state: DONE

## Objective

股权 manifest 预览表的“默认类型”列显示“事实股东 / 实控候选”等中文关系类型，避免用户在补股权关系时看到 `shareholder` 等 raw 枚举；同时 manifest payload 和高级 trace 继续保留 raw `default_kind`。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - Ownership manifest schema
  - Relationship import normalization rules
  - Database schema or relationship enum changes

## Background

The relationship UI now localizes relationship types across graph chips, relationship tables, graph edges, graph inspector, and review queues. The ownership manifest preview still displayed `default_kind=shareholder` in its main “默认类型” column.

## Problem Statement

The manifest preview is part of the user-facing ownership import workflow. The main table should show the business meaning, while raw `default_kind` stays available for import behavior, trace, and scripts.

## Expected Deliverables

- Ownership manifest preview table displays Chinese default relationship type.
- Raw `default_kind` stays in advanced trace and payload.
- Browser acceptance covers visible Chinese display and raw trace preservation.
- API contract and task ledger updated.

## Current Findings

- `renderCompanyOwnershipManifest()` used `statusLabel(item.default_kind || "")`.
- Existing browser acceptance checked manifest rows contained symbols but did not check the default-kind display.

## Proposed Work Plan

1. Render manifest default kind through `relationshipTypeDisplayLabel(item.default_kind)`.
2. Extend `company_ownership_manifest_preview_real_api` acceptance to assert visible “事实股东” and raw `shareholder` in trace.
3. Update static contract, API contract, task ledger, and handoff.

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t550 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `relationshipTypeDisplayLabel()`.
- Existing ownership manifest browser acceptance fixture.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance planned
- [x] Handoff validation planned

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=37`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- First `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t550 --timeout 60`
  - Result: failed, 45/47 checks passed.
  - Cause: the manifest advanced trace was in the first column, so the first three visible decision columns still included raw `shareholder`.
  - Follow-up fix: moved `renderAdvancedTrace("股权 Manifest 追溯", item)` to the final source column.
- Final `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t550 --timeout 60`
  - Result: passed, 47/47 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t550`, local-only evidence.

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t550 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: corrected py_compile, UI static check, final browser acceptance.
- Failed: first browser acceptance run failed before trace placement was corrected.
- Not run: full unit suite, because this was a focused UI display-label change and browser/static checks cover the touched path.

## Decisions

- Treat `default_kind` as a relationship type for display purposes.
- Preserve raw `default_kind` in trace and manifest payload.
- Place manifest trace in the final source column so file/symbol/default-type columns stay user-readable.
- Reuse the shared relationship display helper instead of adding a separate ownership-kind mapping.

## Risks and Open Questions

- Unknown future manifest default kinds still fall back to raw display until added to `relationshipTypeDisplayLabel()`.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t550`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`, not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_ownership_manifest_preview_real_api`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible labels changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

Continue scanning ownership import result rows and maintenance previews for raw enum leakage outside trace JSON.

## Next Steps

1. Continue relationship-chain UI readability audit.
2. Check ownership import result rows for candidate/default type raw leakage.
3. Keep raw `default_kind` and `relationship_type` values in trace/payload while localizing visible labels.
