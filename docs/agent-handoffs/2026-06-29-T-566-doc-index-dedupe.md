# Handoff: T-566 文档索引去重

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-566
- Handoff type: closure
- Roadmap state: DONE

## Objective

移除 `docs/README.md` 中已经在主线入口出现的重复多维关系链链接，让文档首页保持“主线入口 + 文档入口”的清晰结构。

## Scope

- In scope:
  - `docs/README.md`
  - `docs/agent-handoffs/2026-06-29-T-566-doc-index-dedupe.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

最终审计发现 `multidimensional-relationship-closure.md` 同时出现在主线入口和文档入口中。

## Problem Statement

重复入口会让文档首页再次变得像目录堆叠，而不是清晰的阅读路径。

## Expected Deliverables

- 从普通文档入口移除重复的多维关系链条目。
- 保留主线入口中的多维关系链入口。
- 交接记录符合仓库标准。

## Current Findings

- 主线入口已经包含 `multidimensional-relationship-closure.md`。
- 文档入口中的第二处链接可以安全删除。

## Proposed Work Plan

1. 更新 `docs/README.md`。
2. 运行 Markdown 链接、handoff 和 diff 校验。
3. 提交并推送。

## Validation Plan

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `docs/README.md`
- `docs/multidimensional-relationship-closure.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 重复入口已删除
- [x] Markdown 链接检查已通过
- [x] handoff 校验已通过
- [x] diff 检查已通过
- [ ] 提交并推送

## Evidence

- `docs/README.md`: 删除文档入口中的重复多维关系链链接，主线入口保留。

## Commands Run

```bash
git status --short --branch
nl -ba docs/README.md | sed -n '1,45p'
python3 scripts/check_markdown_links.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: 确认重复入口位置；Markdown 链接检查、handoff 校验和 diff 检查通过。
- Failed: 无。
- Not run: 提交和推送尚未执行。

## Decisions

- 保留主线入口中的多维关系链文档，删除普通文档入口中的重复项。

## Risks and Open Questions

- 无。

## Artifacts

- 无。

## Next Steps

1. 运行最终校验。
2. 提交并推送。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是文档索引去重。
- Focused regression protecting behavior: Markdown 链接检查、handoff 校验和 diff 检查。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成校验、提交并推送。
