# Handoff: T-559 根首页文档导览

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-559
- Handoff type: closure
- Roadmap state: DONE

## Objective

把根 `README.md` 补成一个真正可导航的文档首页，能够先指向逻辑总地图，再下钻到四条主线的正式总览。

## Scope

- In scope:
  - `README.md`
  - `docs/agent-handoffs/2026-06-29-T-559-root-doc-guide.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

虽然已经有四条主线的正式总览和总地图，但根首页还缺少一个直接说明如何阅读这些文档的导览区块。

## Problem Statement

如果根首页没有文档导览，用户看到的是能力说明和若干入口链接，但不会很快知道应该先读哪一层。

## Expected Deliverables

- 根 `README.md` 增加文档导览。
- 交接记录符合仓库标准。

## Current Findings

- 四条主线均已形成正式总览。
- 只需增加导览层，不需要改动实现。

## Proposed Work Plan

1. 更新 `README.md`。
2. 补齐交接。
3. 校验并提交推送。

## Validation Plan

- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `docs/logic-map.md`
- `docs/logic-chain-overview.md`
- `docs/latest-analysis-chain.md`
- `docs/multidimensional-relationship-closure.md`
- `docs/personal-research-loop-overview.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 根首页导览已更新
- [ ] 交接格式按模板补齐
- [ ] 校验已复验
- [ ] 提交并推送

## Evidence

- `README.md`: 新增文档导览。

## Commands Run

```bash
git status --short --branch
sed -n '1,140p' README.md
```

Result:

- Passed: 根首页导航状态核对。
- Failed: 无。
- Not run: 交接校验、提交和推送尚未执行。

## Decisions

- 将根首页作为文档导览入口，而不是继续往能力说明段落里塞更多链接。

## Risks and Open Questions

- 文档导览需要随着主线文档变化同步维护。

## Artifacts

- 无。

## Next Steps

1. 运行 handoff 校验。
2. 提交本次根首页收口改动。
3. 推送到 GitHub。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是首页导览收口。
- Focused regression protecting behavior: `scripts/check_handoffs.py` 与 `git diff --check`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成交接校验与提交。
2. 推送到 GitHub。
