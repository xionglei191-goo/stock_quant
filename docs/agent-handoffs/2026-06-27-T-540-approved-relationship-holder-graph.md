# Handoff: T-540 事实股权关系行直达同一事实股东网络

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Research and AI Workflows
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-540
- Handoff type: implementation
- Roadmap state: DONE

## Objective

当用户看到已批准的“事实股权关系”时，可以从该事实关系行直接展开“同一事实股东还关联哪些公司”，不必先找到二跳“事实股东关联”行。

## Scope

- In scope:
  - `app/service_modules/company_intelligence.py`
  - `app/static/index.html`
  - `tests/test_system.py`
  - `scripts/ui_interaction_acceptance.py`
  - `scripts/ui_static_check.py`
  - `docs/api-contracts.md`
  - `tasks/todo.md`
- Out of scope:
  - 新增事实股权关系类型
  - 改变候选关系审核规则
  - 数据库重建或外部数据接入

## Background

事实股东网络已经能从“事实股东关联”二跳行进入，也能通过推荐图谱入口进入。但“事实股权关系”行本身只按 `relationship_type` 打开图谱，缺少 `ownership_holder_key`，不能直接回答“这个事实股东还关联哪些公司”。

## Problem Statement

用户看到某条已批准股权事实时，仍需要从其他二跳行或推荐入口绕行才能展开同一事实股东网络。该入口和原始问题中的“该股东还有哪些公司”不够直接。

## Expected Deliverables

- `approved_relationships[]` 输出 `holder_key` / `holder_name`。
- “事实股权关系”行写入 `data-ownership-holder-key` / `data-ownership-holder-label`。
- 浏览器验收覆盖从事实股权关系行点击进入同一事实股东网络。
- API 合同和任务台账记录该入口。

## Current Findings

- `ownership_holder_key(row)` 已能从 `object_id` 或 `metadata.entity_name` 生成稳定 key。
- `/api/graph/query` 已支持 `ownership_holder_key`。
- 图谱 chip 已支持 ownership holder label。

## Proposed Work Plan

1. 给 `approved_ownership_relationship_rows` 增加 holder key/name。
2. 更新 UI 行属性和文案。
3. 补单测、浏览器验收、静态契约和文档。

## Validation Plan

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t540 --timeout 60`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- Existing approved ownership relationship context.
- Existing `/api/graph/query` ownership holder filtering.
- Local UI service for browser acceptance.

## Blockers

- Current: none.

## Handoff Checklist

- [x] Task scope and objective recorded
- [x] Code changes completed
- [x] `tasks/todo.md` updated
- [x] API contract updated
- [x] Browser acceptance rerun
- [x] Handoff validation rerun

## Evidence

- `python3 -m unittest tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies`
  - Result: passed.
- `python3 -m py_compile app/service_modules/company_intelligence.py tests/test_system.py scripts/ui_interaction_acceptance.py scripts/ui_static_check.py app/services.py`
  - Result: passed.
- `python3 scripts/ui_static_check.py`
  - Result: passed.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t540-clean --timeout 60`
  - Result: passed, 43/43 checks.
  - Artifact: `artifact://ui-interaction-acceptance/ui-interaction-acceptance-t540-clean`, local-only evidence.
  - Note: a prior rerun against reused `/tmp/ai_quant_t540_state.db` failed three unrelated setup checks because the browser acceptance script had already inserted duplicate relationship rows and consumed import fixture state. The clean DB rerun above passed and is the accepted evidence.
- `python3 scripts/check_handoffs.py`
  - Result: passed.
- `git diff --check`
  - Result: passed.

## SystemService Growth Freeze Review

- New SystemService business logic added: no.
- Why a domain module was or was not used: the backend addition is in `app/service_modules/company_intelligence.py`, where relationship context rows are already assembled. `app/services.py` was not changed for new business behavior.
- What focused regression protects the facade behavior: `test_relationship_context_links_approved_same_shareholder_companies` checks holder-key output, and browser acceptance checks the UI click path.
- Whether API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: API/UI response shape changed by adding holder key/name to approved relationship rows; storage and no-broker boundaries did not change.

## Decisions

- Use `object_id` as the primary fact holder key, matching existing `ownership_holder_key` behavior.
- Keep relationship type filter when opening the graph so the network stays focused on the fact relationship type.

## Risks and Open Questions

- No known open blocker. The accepted browser evidence uses a clean local SQLite DB/object store to avoid acceptance-state reuse side effects.

## Next Recommended Action

1. Continue the next visible relationship-chain gap.
