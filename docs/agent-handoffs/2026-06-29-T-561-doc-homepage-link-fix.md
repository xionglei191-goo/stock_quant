# Handoff: T-561 文档首页链接修正

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-561
- Handoff type: closure
- Roadmap state: DONE

## Objective

修正 `docs/README.md` 压缩后的链接文本和段落格式问题，保持文档首页可读、可维护。

## Scope

- In scope:
  - `docs/README.md`
  - `docs/agent-handoffs/2026-06-29-T-561-doc-homepage-link-fix.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

T-560 将 `docs/README.md` 压缩为主线入口和文档入口两层，后续审计发现 PRD 链接文本拼写不一致，且主线入口与下一节之间缺少空行。

## Problem Statement

链接目标正确但显示文本错误，会降低文档首页可信度；缺少空行会让 Markdown 渲染结构不够清晰。

## Expected Deliverables

- 修正 PRD 链接文本。
- 补齐主线入口和文档入口之间的空行。
- 交接记录符合仓库标准。

## Current Findings

- `project-requirements-document.md` 文本应为 `product-requirements-document.md`。
- 目标链接本身已经指向 `./product-requirements-document.md`。

## Proposed Work Plan

1. 更新 `docs/README.md`。
2. 补齐交接。
3. 校验并提交推送。

## Validation Plan

- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `docs/README.md`
- `docs/product-requirements-document.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 链接文本已修正
- [x] 空行格式已修正
- [ ] 交接格式按模板补齐
- [ ] 校验已复验
- [ ] 提交并推送

## Evidence

- `docs/README.md`: 修正文档首页链接文本和空行。

## Commands Run

```bash
git status --short --branch
sed -n '1,120p' docs/README.md
ls docs | rg 'product|project|requirements|logic|personal|latest|relationship'
```

Result:

- Passed: 发现并修正链接文本和段落格式问题。
- Failed: 无。
- Not run: 交接校验、提交和推送尚未执行。

## Decisions

- 只修明确错误，不继续重排文档首页结构。

## Risks and Open Questions

- 无。

## Artifacts

- 无。

## Next Steps

1. 运行 handoff 校验。
2. 提交本次修正。
3. 推送到 GitHub。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是文档修正。
- Focused regression protecting behavior: `scripts/check_handoffs.py` 与 `git diff --check`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 完成交接校验与提交。
2. 推送到 GitHub。
