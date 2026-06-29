# Handoff: T-562 文档链接审计

## Status

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: Platform and Quality
- Last updated: 2026-06-29
- Last agent: Codex
- Branch/worktree: /home/xionglei/Project/sotck_quant

## Metadata

- Task ID: T-562
- Handoff type: closure
- Roadmap state: DONE

## Objective

对文档首页整理后的 Markdown 相对链接做证据型检查，修正历史研究底稿的断链。

## Scope

- In scope:
  - `docs/README.md`
  - `docs/agent-handoffs/2026-06-29-T-562-doc-link-audit.md`
- Out of scope:
  - 业务逻辑改动
  - schema 迁移
  - 真实交易
  - 外部生产证据

## Background

文档首页经过多轮压缩和重排后，需要用实际扫描确认相对链接没有断开。

## Problem Statement

`docs/README.md` 中两个历史研究底稿链接使用 URL 编码形式，本地文件存在但相对路径扫描无法解析为现有文件。

## Expected Deliverables

- 修正两个历史研究底稿链接。
- 跑 Markdown 相对链接扫描，确认缺失为 0。
- 交接记录符合仓库标准。

## Current Findings

- `deep-research-report-加美股.md` 实际文件名为中文文件名，不是 URL 编码路径。
- `deep-research-report -next.md` 实际文件名包含空格，链接需要用尖括号包住。

## Proposed Work Plan

1. 修正 `docs/README.md` 的历史研究底稿链接。
2. 运行相对链接扫描。
3. 运行 handoff 和 diff 校验。
4. 提交并推送改动。

## Validation Plan

- Markdown 相对链接扫描输出 `MISSING_LINKS=0`
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Dependencies

- `docs/README.md`
- `docs/deep-research-report-加美股.md`
- `docs/deep-research-report -next.md`

## Blockers

- 无。

## Handoff Checklist

- [x] 任务范围和目标记录
- [x] 断链已修正
- [x] 相对链接扫描已通过
- [x] handoff 校验已通过
- [x] diff 检查已通过
- [ ] 提交并推送

## Evidence

- `docs/README.md`: 修正两个历史研究底稿链接。
- Markdown 相对链接扫描: `MISSING_LINKS=0`。

## Commands Run

```bash
git status --short --branch
python3 - <<'PY'
from pathlib import Path
import re
files = [Path('README.md')] + sorted(Path('docs').rglob('*.md'))
pat = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
missing=[]
for f in files:
    text=f.read_text(encoding='utf-8')
    for m in pat.finditer(text):
        raw=m.group(1).strip()
        if raw.startswith('<') and raw.endswith('>'):
            raw=raw[1:-1]
        if raw.startswith(('http://','https://','mailto:','#')) or '://' in raw:
            continue
        target=raw.split('#',1)[0]
        if not target:
            continue
        p=(f.parent/target).resolve()
        if not p.exists():
            missing.append((str(f), raw, str(p)))
for item in missing:
    print('|'.join(item))
print(f'MISSING_LINKS={len(missing)}')
PY
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: 相对链接扫描、handoff 校验、diff 检查。
- Failed: 首次扫描发现 2 个历史底稿链接断链；已修正。
- Not run: 提交和推送尚未执行。

## Decisions

- 对中文文件名使用直接相对路径。
- 对包含空格的文件名使用尖括号包裹 Markdown 链接目标。

## Risks and Open Questions

- 当前扫描只检查相对文件是否存在，不校验标题锚点。

## Artifacts

- 无。

## Next Steps

1. 提交本次链接审计修正。
2. 推送到 GitHub。

## SystemService Growth Freeze Review

- 新增 `SystemService` business logic: 否。
- Why a domain module was or was not used: 不涉及业务逻辑，只是文档链接审计。
- Focused regression protecting behavior: 相对链接扫描、`scripts/check_handoffs.py`、`git diff --check`。
- API schema, storage schema, UI behavior, or paper-only/no-broker boundaries changed: 没有。

## Next Recommended Action

1. 提交并推送链接审计修正。
