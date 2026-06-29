# Handoff: T-564 Markdown 链接质量门

## Status

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI, PM / Release Coordination
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-564
- Handoff type: closure
- Roadmap state: DONE

## Objective

把 `scripts/check_markdown_links.py` 接入本地质量门和 PR/产物治理说明，避免文档链路检查只停留在手工命令。

## Scope

- In scope:
  - `Makefile`
  - `docs/artifact-governance.md`
  - `docs/pr-checklist.md`
  - `docs/agent-handoffs/2026-06-29-T-564-markdown-link-gate.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 外部链接可达性检查
  - Markdown 锚点校验

## Background

T-563 新增了 Markdown 相对链接检查脚本，但还没有纳入常规质量门和 PR 检查说明。

## Problem Statement

如果脚本没有接入 `make local-ci` 或文档流程，后续维护者可能不知道需要运行它。

## Expected Deliverables

- `make local-ci` 执行 Markdown 链接检查。
- 文档治理说明 documentation-only 变更的最小检查命令。
- PR checklist 提醒文档变更运行链接检查。

## Current Findings

- `Makefile` 的 `local-ci` 已包含 compile、unit、UI static、安全和 handoff 校验。
- `docs/artifact-governance.md` 和 `docs/pr-checklist.md` 尚未提及 Markdown 链接检查。

## Proposed Work Plan

1. 更新 `Makefile`。
2. 更新 `docs/artifact-governance.md`。
3. 更新 `docs/pr-checklist.md`。
4. 运行链接检查、handoff 校验和 diff 检查。

## Validation Plan

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `scripts/check_markdown_links.py`
- `Makefile`
- `docs/artifact-governance.md`
- `docs/pr-checklist.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] `make local-ci` 已接入链接检查
- [x] 产物治理说明已更新
- [x] PR checklist 已更新
- [x] 链接检查已通过
- [x] handoff 校验已通过
- [x] diff 检查已通过
- [ ] 提交并推送

## Evidence

- `Makefile`: `local-ci` 新增 `python3 scripts/check_markdown_links.py`。
- `docs/artifact-governance.md`: 说明 Markdown link validation 和 documentation-only 最小检查命令。
- `docs/pr-checklist.md`: 文档变更 checklist 新增链接检查。

## Commands Run

```bash
git status --short --branch
sed -n '1,220p' docs/artifact-governance.md
sed -n '1,160p' docs/pr-checklist.md
sed -n '1,160p' Makefile
python3 scripts/check_markdown_links.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: 确认链接检查尚未接入质量门和 PR/治理说明；更新后 Markdown 链接检查通过，检查 195 个 Markdown 文件；handoff 校验和 diff 检查通过。
- Failed: 无。
- Not run: 提交和推送尚未执行。

## Decisions

- 将链接检查纳入 `make local-ci`，让文档链路成为常规本地质量门。
- 对 documentation-only 变更记录更轻量的最小检查命令。

## Risks and Open Questions

- `make local-ci` 会比之前多一次 Markdown 扫描，但当前检查 194 个 Markdown 文件耗时很低。

## Artifacts

- 无。

## Next Steps

1. 运行最终校验。
2. 提交并推送。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是质量门接入。
- Focused regression protecting behavior: `python3 scripts/check_markdown_links.py`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成校验、提交并推送。
