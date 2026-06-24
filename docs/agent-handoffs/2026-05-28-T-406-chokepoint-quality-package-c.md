# Handoff: T-406C Chokepoint Quality Package

## Metadata
- Task ID: T-406C
- Title: Local chokepoint quality package and repeatable baseline
- Status: DOING
- Priority: medium
- Owner Group: PM / Release Coordination
- Current Agent: codex-gpt5
- Reviewer: Research and AI Workflows, Platform and Quality
- Created At: 2026-05-28
- Updated At: 2026-05-28T20:33:59+08:00

## Objective
为瓶颈研究模块建立首个本地可复验质量包，让现有 7 步 chokepoint 流水线可以按固定主题样本批量运行、导出质量摘要，并为后续 T-406D/T-406E 提供稳定基线。

## Scope
In scope:
- `scripts/local_chokepoint_quality_package.py`
- `tests/test_system.py`
- `docs/chokepoint-research-module.md`
- `tasks/todo.md`
- 当前 handoff

Out of scope:
- `T-406D` 结构化结论 schema
- `T-406E` verification task 完成后的 run 回写
- UI 交互改造
- 真实交易或非本机发布证据

## Background
`T-406B` 已完成 chokepoint run、7 步流水线、verification task 和 conclusion 的代码层闭环，但仓库此前没有“真实主题批跑 + 本机质量导出”层。`tasks/todo.md` 对 `T-406C` 的要求是将模块从“能生成流水线”推进到“能用真实主题复验质量”。

并行审查结论确认：
- `T-406D` 尚未提供结构化结论 contract
- `T-406E` 尚未提供 verification task 完成后的回写闭环

因此本轮应只做基于当前 schema 的本地质量包，不应提前发明 D/E 的新契约。

## Problem Statement
当前 chokepoint 模块缺少可重复执行的本地质量基线。没有统一脚本就无法稳定比较不同主题 run 的 URL 覆盖、unknown 规模、verification task 生成、fallback 命中和研究边界违规情况，也无法为后续人工标注和 schema 演进提供固定输入。

## Expected Deliverables
- 本地可执行质量包脚本
- 至少 5 个真实主题样本模板
- 可复验导出产物：
  - `sample-manifest.json`
  - `run-results.json`
  - `manual-review-seed.json`
  - `quality-summary.json`
  - `quality-package.json`
- focused unittest
- 任务状态与模块文档更新
- 可继续接力的 handoff

## Current Findings
1. 已新增 `scripts/local_chokepoint_quality_package.py`，内置 5 个真实主题模板样本。
2. 脚本会创建并运行现有 chokepoint run，然后导出样本 manifest、run 摘要、人工复核骨架和质量汇总。
3. 产物固定保留 `automation_allowed=false` / `live_execution_allowed=false` 的研究边界检查。
4. 已新增 focused test：`test_local_chokepoint_quality_package_builds_repeatable_local_artifacts`。
5. 本地 smoke 已通过，但 `manual-review-seed.json` 仍只是骨架，没有真实 review 关闭率。
6. 质量基线已将“rate”字段收敛到 `0..1` 语义；平均数量字段单独使用 `avg_*` 命名。
7. 额外发现一个非本轮主路径风险：`docs/api-contracts.md` 声明了 `/api/chokepoint/readiness-report`，但 `app/services.py` 当前未见对应实现，后续需单独处理契约漂移。

## Proposed Work Plan
1. 新增本地质量包脚本并固定样本模板。 (completed)
2. 增加脚本级 focused unittest。 (completed)
3. 修正质量指标口径，区分比例与平均数量。 (completed)
4. 更新 `tasks/todo.md` 与模块文档。 (completed)
5. 记录 handoff 并标明剩余人工标注工作。 (completed)
6. 为质量包增加人工 review 导入与汇总口径。 (completed)
7. 后续由下一轮填入真实人工 review 数据。 (pending)

## Manual Review Contract Decision

为避免 `T-406C` 提前侵入 `T-406D/T-406E`，人工复核导入 contract 保持在“样本级 label + 问题标记”层，不扩展 chokepoint run 结论 schema。

当前脚本已实现的导入 contract：

- `manual_review_input` 支持内联对象、`.json` 或 `.jsonl`
- `.json` 可使用 `{"rows": [...]}` 或直接 list
- 每行必须提供 `sample_id`
- 当前支持字段：
  - `sample_id`
  - `review_status`
  - `reviewer`
  - `reviewed_at`
  - `review_notes`
  - `expected_labels` 或 `labels`
  - `manual_issues`
- label override 当前支持：
  - `label_id`
  - `manual_status`：`pending_manual_review`、`confirmed`、`dismissed`
  - `notes`

当前聚合规则限定为质量包统计，不改变现有 run/conclusion：

- `manual_review_close_rate = closed_labels / total_labels`
- `manual_review_sample_coverage_rate = reviewed_or_partial_rows / sample_count`
- `manual_review_issue_count = sum(manual_issue_counts.values())`
- 额外输出：
  - `manual_review_summary.review_status_counts`
  - `manual_review_summary.issue_counts`
  - `manual_review_summary.closed_label_count`

明确 out of scope：

- 不新增 `core_facts`、`market_pricing_context`、`falsification_status` 或逐证据对象 schema
- 不把人工复核结果回写 chokepoint run、`ResearchTask` 或 `conclusion`
- 不引入新的评分模型、verification task 生命周期或 UI 闭环

## Validation Plan
```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_builds_repeatable_local_artifacts
python3 scripts/local_chokepoint_quality_package.py --output-dir /tmp/chokepoint-quality-package-smoke
python3 scripts/security_check.py .
python3 scripts/check_handoffs.py
```

## Risks
- `manual-review-seed.json` 当前只是人工标注入口；虽然已支持导入 review 结果，但仍不等同于真实人工基线。
- `avg_unknowns_per_run`、`avg_verification_tasks_per_run` 仍受当前半结构化 conclusion/verification heuristic 影响，后续需要与 T-406D/T-406E 对齐。
- 脚本目前使用 stubbed LLM 输出保证本机可重跑，因此它验证的是 pipeline contract 和质量包口径，不是外部真实模型质量。
- 人工复核导入 contract 目前只覆盖样本级 label 判定；如果后续直接扩展为逐证据 schema，会与 `T-406D` 结构化结论设计重叠。

## Dependencies
- `app/api.py`
- `app/services.py`
- `app/models.py`
- `tests/test_system.py`
- `tasks/todo.md`
- `docs/chokepoint-research-module.md`

## Blockers
- 无当前阻塞。
- 后续完成度取决于人工 review 数据和 T-406D/T-406E 的正式 schema/回写设计。

## Handoff Checklist
- [x] Code changes implemented
- [x] Validation commands executed
- [x] Test results captured
- [x] Artifact or log references added
- [x] `tasks/todo.md` status updated
- [ ] Reviewer assigned

## Evidence
- Validation commands:
  ```bash
  python3 -m py_compile app/*.py tests/*.py scripts/*.py
  python3 -m unittest tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_builds_repeatable_local_artifacts tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_merges_manual_review_metrics tests.test_system.SystemServiceTests.test_local_chokepoint_quality_package_cli_accepts_manual_review_jsonl
  python3 scripts/local_chokepoint_quality_package.py --output-dir /tmp/chokepoint-quality-package-smoke-2 --manual-review-input /tmp/chokepoint-manual-review.jsonl
  python3 scripts/security_check.py .
  ```
- Result summary:
  - `py_compile`: passed
  - focused unittest: passed (`Ran 3 tests`)
  - local smoke script run with manual review input: passed
  - `security_check.py`: passed (`ok=true`, `findings=[]`)
- Artifact references:
  - `/tmp/chokepoint-manual-review.jsonl`: local-only manual review import sample used for CLI validation
  - `/tmp/chokepoint-quality-package-smoke/quality-package.json`: local-only smoke package
  - `/tmp/chokepoint-quality-package-smoke/sample-manifest.json`: local-only sample manifest
  - `/tmp/chokepoint-quality-package-smoke/run-results.json`: local-only run summaries
  - `/tmp/chokepoint-quality-package-smoke/manual-review-seed.json`: local-only manual review skeleton
  - `/tmp/chokepoint-quality-package-smoke/quality-summary.json`: local-only baseline metrics
  - `/tmp/chokepoint-quality-package-smoke-2/quality-package.json`: local-only smoke package with imported manual review sample
  - `/tmp/chokepoint-quality-package-smoke-2/manual-review-seed.json`: local-only merged manual review output
  - `/tmp/chokepoint-quality-package-smoke-2/quality-summary.json`: local-only merged baseline metrics

## Next Recommended Action
继续 `T-406C` 的剩余工作：按当前脚本已实现的最窄导入 contract 生成真实人工复核结果，先形成样本级误差台账和关闭率，再推进 `T-406D` 的结构化结论 schema 与 `T-406E` 的 verification task 回写闭环。
