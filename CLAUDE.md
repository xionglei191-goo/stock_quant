# CLAUDE.md — 项目工作约定（给 AI agent 的记忆）

本文件是给在本仓库工作的 AI agent 的长期记忆，减少会话间的重复犯错。

## 执行节奏

- **不要在工具结果之间无必要地停顿。** 连续执行到任务完成，或直到遇到真正需要用户拍板的决策点 / 破坏性操作确认。查文件、跑脚本、导入数据这类操作之间通常没有决策点，不要每步都停下等待——那样只会拖慢用户。

## 结论纪律

- **先隔离验证，再下因果结论。** 不要基于单次观察就急着断定根因。本会话曾把"导入报错没跑成功"误判为"缺 commit 的 bug"，并把这个不存在的 bug 写进了权威路线图 `tasks/todo.md`。正确做法：在全新/隔离环境里复现，用事实确认，再动代码或改文档。

## Git 状态纪律

- **git 状态以 `git log` / `git status` 的实时输出为准，不以记忆或自己之前的汇报为准。** 本会话曾多次误报提交已落库/已合并（如报告了实际不存在的提交 hash）。每次提交/合并后，用 `git show HEAD:<file>` 或 `git log --oneline` 从已提交版本复核，再向用户汇报。
- 工作区文件（尤其 `tasks/todo.md`）的 bash 写入在后台隔离下，若不在同一次调用里提交，可能在工具调用之间被还原。改法：**"变换 + 校验 + 提交" 放进同一次 bash 调用原子完成**。
- 只在明确延续用户已授权的工作时才提交/推送；不确定时只读分析、跑测试，把提交决定留给用户。

## 质量门（每次改动后）

```bash
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
git diff --check
```

或直接 `make local-ci`。

## 边界（产品红线，不可越）

- 纸面 / 模拟 only：不接真实券商、不自动下单、不做实时交易。
- 研报只进观点层 / 参考层，不作为事实真相源、训练源或真实交易触发源。
- 事实层（公告/财报/行情）优先于观点层（研报），观点先于模拟反馈。

## SystemService 模块化

- `app/services.py` 是 facade，按 `docs/systemservice-modularization-adr.md` 逐步把**纯 helper** 抽到 `app/service_modules/`，保持 facade 方法签名和 API/schema/UI 边界不变。
- 有状态方法（读 `self.store` / audit / 网络 I/O）**有意保留在 SystemService**，不强抽。纯 helper 的低垂果实已基本摘完，不为重构而重构。
