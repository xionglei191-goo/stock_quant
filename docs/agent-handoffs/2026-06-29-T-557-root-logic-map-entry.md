# Handoff: T-557 根入口逻辑总地图

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Data and Evidence, Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-557
- Handoff type: closure
- Roadmap state: DONE

## Objective

把 `docs/logic-map.md` 提升到仓库根入口层，让用户从 `README.md` 就能先进入四条主线的总地图。

## Scope

- In scope:
  - `README.md`
  - `docs/agent-handoffs/2026-06-29-T-557-root-logic-map-entry.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

当前已经有四条主线的独立总览和总地图，但仓库根入口还没有直接把总地图作为第一跳转点。

## Problem Statement

如果根入口只指向逻辑链条总览而不指向总地图，用户仍需多跳一次才能看见四条主线的整体关系。

## Expected Deliverables

- `README.md` 增加总地图入口。
- 交接记录符合仓库标准。

## Current Findings

- 逻辑总地图已经存在。
- 只需把它挂到根入口，不需要新增业务实现。

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

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 根入口已更新
- [ ] 交接格式按模板补齐
- [ ] 校验已复验
- [ ] 提交并推送

## Evidence

- `README.md`: 新增逻辑总地图入口。

## Commands Run

```bash
git status --short --branch
sed -n '1,140p' README.md
```

Result:

- Passed: 根入口状态核对。
- Failed: 无。
- Not run: 交接校验、提交与推送尚未执行。

## Decisions

- 根入口只挂总地图，不再直接罗列所有主线，避免首页再膨胀。

## Risks and Open Questions

- 需要持续维护总地图与各主线总览之间的关系。

## Artifacts

- 无。

## Next Steps

1. 运行 handoff 校验。
2. 提交本次根入口收口改动。
3. 推送到 GitHub。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是入口导航收口。
- Focused regression protecting behavior: `scripts/check_handoffs.py` 与 `git diff --check`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成交接校验与提交。
2. 推送到 GitHub。
