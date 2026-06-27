# Handoff: T-552 13F 股东/持有人来源状态显示可读化

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-552
- Handoff type: implementation
- Roadmap state: DONE

## Objective

公司情报“多维关系”里的“股东/持有人”行在缺少报告期时不直接显示 `sec_edgar` 等 raw 来源 id，而显示治理后的来源标签，并在行级追溯属性中保留 raw 来源。

## Scope

- In scope:
  - `app/static/index.html`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 13F ingestion schema
  - InstitutionalHolding storage model
  - `/api/graph/query` filtering behavior

## Background

股东/持有人网络是用户提出的“看到公司时知道股东有哪些、该股东还有哪些公司”的关键链路。此前“股东/持有人”行在没有 `report_period` 时会把 `source_id` 原文作为状态显示，容易把 `sec_edgar` 这类机器字段暴露到主视图。

## Problem Statement

主视图应展示用户能理解的报告期或来源名称；raw `source_id` 仍应保留在行级追溯属性中，供来源治理、审计和脚本验收使用。

## Expected Deliverables

- “股东/持有人”行状态列优先显示报告期。
- 缺少报告期时显示 `sourceLabel(source_id)`。
- 浏览器验收覆盖主列不显示 raw `sec_edgar`，行级 `data-source-id` 仍保留 raw。
- API contract、任务台账和 handoff 同步更新。

## Current Findings

- `renderCompanyRelationshipContext()` 的 `ownership.shareholders` 行使用 `item.report_period || item.source_id` 作为状态。
- `sourceLabel()` 已有 `sec_edgar -> SEC 官方披露` 映射，可直接复用。
- 该问题仅影响 UI 主显示，不需要改 API 或数据结构。

## Proposed Work Plan

1. 在 `renderCompanyRelationshipContext()` 内增加 `holdingStatusLabel()`。
2. 将 “股东/持有人” 行状态改为 `report_period` 优先、来源标签兜底，并写入 `data-source-id`。
3. 增加真实 DOM 浏览器验收，确认主列可读且 raw trace 保留。
4. 更新静态契约、API contract、任务台账和 handoff。

## Validation Plan

- `python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t552 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing `sourceLabel()` helper.
- Existing `renderCompanyRelationshipContext()` relationship context renderer.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Current State

- Completed:
  - `holdingStatusLabel()` added.
  - Browser acceptance check added.
  - 13F holder rows now preserve raw source through `data-source-id`.
  - Static contract, API contract, task ledger, and handoff updated.
- In progress:
  - None.
- Not started:
  - None.
- Blocked:
  - None.

## Files Touched

- `app/static/index.html`: 用可读来源标签替代 13F 持有人状态列 raw source fallback，并保留 `data-source-id`。
- `scripts/ui_interaction_acceptance.py`: 增加股东/持有人来源显示浏览器验收。
- `scripts/ui_static_check.py`: 增加 `holdingStatusLabel` 静态契约片段。
- `docs/api-contracts.md`: 记录 13F 持有人主显示与 raw trace 分工。
- `tasks/todo.md`: 新增并关闭 T-552。
- `docs/agent-handoffs/2026-06-27-T-552-shareholder-source-label.md`: 本交接记录。

## Commands Run

```bash
python3 -m py_compile scripts/ui_interaction_acceptance.py scripts/ui_static_check.py
python3 scripts/ui_static_check.py
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t552 --timeout 60
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: py_compile, UI static check, final browser interaction acceptance, handoff validation, diff whitespace check.
- Failed: earlier browser runs failed while the fixture asserted raw `source_id` in prettified trace text and while failed runs polluted the service state; final clean run passed after moving raw source verification to `data-source-id`.
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
  - Result: passed, `text_snippets=39`, `required_ids=379`, `required_functions=162`, `node_check=passed`.
- Final `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t552 --timeout 60`
  - Result: passed, 48/48 checks.
- `python3 scripts/check_handoffs.py`
  - Result: passed, 126 handoffs checked.
- `git diff --check`
  - Result: passed.

## Decisions

- Prefer report period over source label because report period is more useful for holdings.
- Use `sourceLabel()` fallback instead of adding a separate 13F-specific map.
- Keep raw `source_id` in row-level `data-source-id` while trace may display a humanized source label.

## Risks and Open Questions

- Unknown future `source_id` values still fall back to raw until added to `sourceLabel()`.

## Artifacts

- `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t552`: local-only browser acceptance artifact produced by `scripts/ui_interaction_acceptance.py`; not production evidence.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No.
- Why a domain module was or was not used: Not applicable; this was a UI display and contract update.
- Focused regression protecting behavior: `company_shareholder_holding_source_label_is_readable`.
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: UI visible fallback label changed; API schema, storage schema, and paper-only/no-broker boundaries did not change.

## Next Recommended Action

1. Run focused validation.
2. Update this handoff evidence with actual results.
3. Continue scanning relationship context rows for any remaining raw source/status fallback in primary columns.
