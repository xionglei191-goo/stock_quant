# Handoff: T-560 文档首页导览压缩

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-560
- Handoff type: closure
- Roadmap state: DONE

## Objective

把 `docs/README.md` 压成更清晰的文档首页，让主线入口和文档入口分层呈现，减少重复与目录堆叠感。

## Scope

- In scope:
  - `docs/README.md`
  - `docs/agent-handoffs/2026-06-29-T-560-doc-homepage-guide.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

虽然仓库已有四条主线的总地图和总览，但 `docs/README.md` 仍然层次偏多，需要压缩成更像首页的结构。

## Problem Statement

如果文档首页依旧有多组相似的链路列表，用户会把它当成目录，而不是导览页。

## Expected Deliverables

- `docs/README.md` 结构压缩为更清晰的首页。
- 交接记录符合仓库标准。

## Current Findings

- 入口和总览都已经具备。
- 本次仅做文档首页整理，不涉及新功能。

## Proposed Work Plan

1. 调整 `docs/README.md` 结构。
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
- [x] 首页结构已调整
- [ ] 交接格式按模板补齐
- [ ] 校验已复验
- [ ] 提交并推送

## Evidence

- `docs/README.md`: 文档首页结构调整。

## Commands Run

```bash
sed -n '1,90p' docs/README.md
```

Result:

- Passed: 首页结构确认。
- Failed: 无。
- Not run: 交接校验、提交和推送尚未执行。

## Decisions

- 保留两层结构：主线入口 + 文档入口。

## Risks and Open Questions

- 文档首页后续仍需随着主线新增维持简洁。

## Artifacts

- 无。

## Next Steps

1. 运行 handoff 校验。
2. 提交本次首页压缩改动。
3. 推送到 GitHub。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是首页结构整理。
- Focused regression protecting behavior: `scripts/check_handoffs.py` 与 `git diff --check`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成交接校验与提交。
2. 推送到 GitHub。
