# Handoff: T-551 股权表导入结果主列与追溯分离

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-551
- Handoff type: implementation
- Roadmap state: DONE

## Objective

股权表导入预览和执行结果的主表列只显示用户决策需要的信息，把 `file_path`、`source_table`、`source_id` 等 raw 字段留在高级追溯里，保持本地股权补库链路可读且可审计。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - Ownership import schema
  - Relationship candidate generation rules
  - Database schema or review queue behavior

## Background

T-550 已经把股权 manifest 默认类型主列改为中文关系名，并把 manifest trace 放到最后一列。继续检查股权表导入结果时发现 `renderCompanyOwnershipImport()` 仍在第一列拼接完整“股权表追溯”，导致主列文本混入 `file_path` 和来源字段。

## Problem Statement

股权导入是补齐“这个公司有哪些股东、股东还关联哪些公司”的入口。主表应帮助用户判断文件、解析状态和候选数量，raw 来源字段应可追溯但不应打断主视图。

## Expected Deliverables

- 股权表导入结果前三列不再包含 raw trace JSON。
- 最后一列仍保留完整“股权表追溯”。
- 浏览器验收覆盖主列干净和 raw trace 保留。
- API contract、任务台账和 handoff 同步更新。

## Current Findings

- `renderCompanyOwnershipImport()` 原先在第一列同时渲染股权表名称和 `renderAdvancedTrace("股权表追溯", item)`。
- 浏览器 DOM 的 `textContent` 会包含关闭状态 `<details>` 中的 trace 文本，因此如果 trace 放在第一列，主列验收会看到 raw `file_path` 和来源字段。
- 该问题只影响 UI 展示分层，不需要修改导入 payload、API schema 或存储 schema。

## Proposed Work Plan

1. 将股权表导入行的高级 trace 从第一列移到最后一列。
2. 在 manifest 到导入预览的真实浏览器验收中断言前三列不含 raw 来源字段，同时整行仍保留 raw trace。
3. 更新静态契约、API contract、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t551 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `renderAdvancedTrace()` behavior.
- Existing ownership manifest browser fixture.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Current State

- Completed:
  - `renderCompanyOwnershipImport()` 将 `renderAdvancedTrace("股权表追溯", item)` 从第一列移到最后一列。
  - `company_ownership_manifest_to_import_preview_real_api` 增加前三列无 raw 来源、整行仍有 raw 来源的断言。
  - `docs/api-contracts.md` 和 `tasks/todo.md` 已更新。
- In progress:
  - None.
- Not started:
  - None.
- Blocked:
  - None.

## Files Touched

- `app/static/index.html`: 调整股权表导入结果行的 trace 位置。
- `scripts/ui_interaction_acceptance.py`: 增加导入预览主列与 trace 分离的浏览器断言。
- `scripts/ui_static_check.py`: 增加“股权表追溯”静态契约片段。
- `docs/api-contracts.md`: 记录导入结果主列和 raw trace 的显示分工。
- `tasks/todo.md`: 新增并关闭 T-551。
- `docs/agent-handoffs/2026-06-27-T-551-ownership-import-row-trace.md`: 本交接记录。

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t551 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: py_compile, UI static check, browser interaction acceptance, handoff validation, diff whitespace check.
- Failed: none.
- Not run: full unit suite, because this is a focused UI display/acceptance change.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance completed
- [x] Handoff validation completed

## Evidence

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed, `text_snippets=38`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t551 --timeout 60`
  - Result: passed, 47/47 checks.
- `python3 scripts/check_handoffs.py`
  - Result: passed, 125 handoffs checked.
- `git diff --check`
  - Result: passed.

## Decisions

- Keep the row-level raw source data in the same table row but move it to the final boundary/trace column.
- Browser acceptance checks only the first three decision columns for raw leakage, because the full row must still contain raw trace for audit.
- Reuse the existing advanced trace renderer instead of changing the import payload.

## Risks and Open Questions

- If future CSS hides closed `<details>` text from accessibility snapshots differently, browser acceptance should continue to use DOM `textContent` because the trace is intentionally present in the row.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t551`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`; not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_ownership_manifest_to_import_preview_real_api`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI trace placement changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

1. Run the focused UI validation commands listed above.
2. If validation passes, keep T-551 as DONE.
3. Continue scanning the ownership/review/graph flow for remaining raw enum or trace leakage in primary user columns.
