# Handoff: T-563 Markdown 链接检查脚本

## Status

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-563
- Handoff type: closure
- Roadmap state: DONE

## Objective

把临时 Markdown 相对链接扫描固化为可复跑脚本，作为文档总入口整理后的质量门。

## Scope

- In scope:
  - `scripts/check_markdown_links.py`
  - `docs/agent-handoffs/2026-06-29-T-563-markdown-link-check.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 外部链接可达性检查
  - Markdown 锚点校验

## Background

T-562 通过一次性脚本发现并修正了两个历史底稿断链。后续需要一个正式脚本来复跑同类检查。

## Problem Statement

如果 Markdown 链接检查只停留在一次性命令里，后续文档整理容易再次引入断链而没有固定质量门。

## Expected Deliverables

- 新增标准库实现的 Markdown 相对链接检查脚本。
- 默认检查 `README.md` 和 `docs/**/*.md`。
- 交接记录符合仓库标准。

## Current Findings

- 仓库已有 `scripts/check_handoffs.py`，但没有通用 Markdown 相对链接检查器。
- 当前检查范围只需要本地相对文件存在性，不检查外部链接或锚点。

## Proposed Work Plan

1. 新增 `scripts/check_markdown_links.py`。
2. 跑脚本确认当前文档无相对断链。
3. 跑 handoff 和 diff 校验。
4. 提交并推送改动。

## Validation Plan

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `README.md`
- `docs/**/*.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 链接检查脚本已新增
- [x] 链接检查已通过
- [x] handoff 校验已通过
- [x] diff 检查已通过
- [ ] 提交并推送

## Evidence

- `scripts/check_markdown_links.py`: Markdown 相对链接检查脚本。

## Commands Run

```bash
ls scripts | rg 'check|link|handoff|doc'
sed -n '1,220p' scripts/check_handoffs.py
git status --short --branch
python3 scripts/check_markdown_links.py
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: 确认仓库已有 handoff 校验但无 Markdown 链接检查脚本；新增脚本后 `python3 scripts/check_markdown_links.py` 通过，检查 194 个 Markdown 文件；handoff 校验和 diff 检查通过。
- Failed: 无。
- Not run: 提交和推送尚未执行。

## Decisions

- 使用 Python 标准库实现，避免新增依赖。
- 默认跳过外部链接、`mailto:`、纯锚点和 URI。
- 支持显式传入文件或目录作为检查范围。

## Risks and Open Questions

- 当前不校验标题锚点是否存在。
- 当前不检测外部链接可达性。

## Artifacts

- 无。

## Next Steps

1. 运行 `python3 scripts/check_markdown_links.py`。
2. 运行 handoff 和 diff 校验。
3. 提交并推送。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是文档质量脚本。
- Focused regression protecting behavior: `python3 scripts/check_markdown_links.py`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成脚本校验、提交并推送。
