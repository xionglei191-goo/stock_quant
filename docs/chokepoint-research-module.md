# 瓶颈研究模块方向文档

- Status: active
- Owner group: Research and AI Workflows
- Last updated: 2026-05-28
- Related tasks: T-406B, T-406C, T-406D, T-406E
- Scope: 瓶颈研究模块的方法论、边界、自动化流水线和本地质量基线
- Non-goals: 不定义真实交易策略，不替代人工研究复核

## 1. 模块定位

「瓶颈研究」模块面向没有系统分析训练的普通投资者。它的目标不是替用户直接荐股、承诺收益或自动下单，而是用 AI 把专业研究流程拆成可执行步骤，帮助用户从“听概念、追热点”升级为“画价值链、找瓶颈、验事实、等催化、控风险”。

模块采用 @aleabitoreddit / Serenity 式研究方法作为方法论参考：从终端需求出发，自底向上逆向拆解供应链、价值链和商业模式，寻找集中度高、切换成本高、供给扩张慢、但市场尚未充分定价的 chokepoint。该方法可以提高发现不对称机会的概率，但不能被描述为稳定收益机器。

## 2. 用户与核心问题

目标用户包括：

- 没有分析基础、但希望系统学习投研方法的个人投资者。
- 能理解行业机会、但缺少供应链拆解和证据验证能力的研究新手。
- 希望用 AI 扩展研究范围、减少盲区、提升复盘质量的模拟组合使用者。

这些用户的核心问题通常不是“没有信息”，而是：

- 不知道一个公司到底赚什么钱，谁给它付钱。
- 不知道热点背后的产业链节点和利润池在哪里。
- 容易把 AI 的流畅输出、社交媒体叙事或研报观点误认为事实。
- 容易只寻找支持自己观点的信息，缺少反方验证和退出条件。
- 无法把研究结论和 K 线、估值、研报、公告、财报、知识图谱等真实资源连起来验证。

## 3. 方法论原则

瓶颈研究模块的指导思想是 Serenity-style chokepoint research，但必须做跨行业泛化，不默认套用 AI、半导体或任何单一赛道。

核心流程：

1. 从终端需求和付费方开始，确认真实需求是否存在。
2. 逆向拆解价值链：终端产品或服务 -> 系统/组件 -> 材料/资源 -> 设备/工艺 -> 渠道/监管/许可。
3. 标出每一层的关键玩家、集中度、切换成本、供给扩张周期和客户依赖。
4. 识别 chokepoint：如果该节点受限，整个需求扩张是否会被卡住。
5. 量化不对称性：当前市值、收入、利润池、TAM、潜在订单和市场关注度之间是否存在错配。
6. 跟踪催化剂：认证、量产、合同、政策、并购、指数纳入、财报验证和机构轮动。
7. 明确证伪条件：什么事实出现后，thesis 必须降权、暂停或退出。

模块应把每个结论分为四层：

- `confirmed`：有一手或可靠公开来源支持。
- `inferred`：基于已确认事实的合理推断。
- `speculative`：早期假设、想象空间或低置信推演。
- `unknown`：无法确认，必须保留为待验证问题。

## 4. AI 脚手架与流水线

AI 在本模块中的角色是研究脚手架，而不是最终裁判。流水线负责约束用户和模型不要偏离方法论，并在每一步展示当前状态：

- 当前正在进行哪一步。
- 本步骤的输入是什么。
- 本步骤产出的阶段结论是什么。
- 形成了哪些可复用成果，例如来源台账、价值链地图、瓶颈列表、催化剂时间线、证伪条件。
- 存在哪些问题，例如缺来源、事实冲突、推断过强、市场份额未知、客户关系无法确认。
- 哪些地方需要用户调优，例如缩小研究对象、换行业模板、降低输出长度、增加事实审计、重跑某一步。

建议的自动化流水线包括：

1. 来源台账：只收集来源、链接、日期、来源类型、置信度和待验证事实。
2. 事实审计：识别幻觉、过期事实、无链接事实、把推断写成 confirmed 的问题。
3. 问题窄化：把宽泛主题拆成 2-4 个可执行 chokepoint 子问题。
4. 价值链映射：建立上下游、替代品、渠道、监管和关键玩家地图。
5. Chokepoint 排名：比较集中度、切换成本、供给弹性和客户依赖。
6. Thesis 草稿：形成研究假设、催化剂、风险和证伪条件。
7. 验证与复盘：用真实数据和后续事件持续校验，而不是一次性生成报告。

## 5. 项目资源的验证角色

本项目已有的 K 线、研报、基础资料、公告/财报、知识图谱和研究任务队列，是瓶颈研究成果的验证层。

这些资源的角色应明确区分：

- K 线和成交量：验证市场是否已经开始定价、是否存在拥挤或趋势失效。
- 研报：作为机构观点、产业链线索和预期差观察，不作为核心事实源。
- 公告、财报和监管文件：作为客户、收入、订单、产能、认证、资本开支和风险披露的核心事实源。
- 基础资料和公开网页：用于建立行业地图、术语解释、上下游关系和候选池。
- 知识图谱：连接公司、证券、文件、证据、观点、事件、thesis 和模拟组合反馈。

验证层的原则是：AI 可以提出假设，但真实资源负责验收。任何缺少来源、无法回链、无法复核的结论，都只能进入 `unknown` 或 `needs_verification`，不能进入可执行研究结论。

## 6. 风险边界

模块输出固定为研究辅助和模拟组合输入，不构成投资建议，不触发真实交易，不连接真实券商。

必须内置以下边界：

- 不把 @aleabitoreddit / Serenity 方法描述为确定收益路径。
- 不允许 AI 直接输出“买入/卖出/目标价”作为最终建议。
- 不允许社交媒体、Substack 或二手摘要作为核心事实源，只能作为研究线索。
- 不允许研报观点替代公司公告、财报、监管文件等事实来源。
- 不允许没有 URL、日期、来源类型和置信度的关键事实进入 `confirmed`。
- 每个 thesis 必须包含反方论点、证伪条件和需要手动验证的关键事实。

## 7. 后续建设方向

### 7.1 本地质量包基线

`T-406C` 当前已提供本地可重复执行的质量包脚本：

- 脚本：`scripts/local_chokepoint_quality_package.py`
- 默认产物目录：`artifacts/chokepoint-quality-package/`
- 本地 smoke 命令：`python3 scripts/local_chokepoint_quality_package.py --output-dir /tmp/chokepoint-quality-package-smoke`

当前脚本会使用 5 个真实主题模板样本，批量创建并执行现有 7 步 chokepoint 流水线，并导出以下本地 `local-only` 产物：

- `sample-manifest.json`：样本清单、主题、ticker、playbook 和 run 状态
- `run-results.json`：每个 run 的 step 摘要、结论状态、verification task 统计和边界检查
- `manual-review-seed.json`：人工标注骨架，供后续补充 `confirmed` / `inferred` / `speculative` / `unknown` 复核结果
- `quality-summary.json`：本机基线指标汇总
- `quality-package.json`：质量包入口清单

当前本地基线只解决“可重跑、可归档、可对比”的第一步，不等同于 `T-406C` 最终完成。仍需后续补齐：

- 人工标注闭环和 review 关闭率
- 样本级错分、无 URL、无日期、边界违规和 fallback 的人工判定
- 与 `T-406D/T-406E` 新结构化结论/回写闭环保持口径一致

`T-406C` 当前已实现最窄人工复核导入 contract，继续沿用 `manual-review-seed.json` 的样本和 label 粒度，不提前发明 `T-406D/T-406E` 的新 schema。

当前脚本支持三种输入：

- `manual_review_input=<python dict>`
- `--manual-review-input /path/to/manual-review.json`
- `--manual-review-input /path/to/manual-review.jsonl`

当前已实现 contract：

- 顶层或每行都必须能提供 `sample_id`
- `.json` 可使用：
  - 顶层 `{"rows": [...]}`
  - 或直接传 `[{...}, {...}]`
- `.jsonl` 每行一个 review row
- 每个 review row 当前支持：
  - `sample_id`: 必填；必须能匹配 `sample-manifest.json`
  - `review_status`: 可选；常见值为 `completed_manual_review`、`partial_manual_review`
  - `reviewer`: 可选
  - `reviewed_at`: 可选
  - `review_notes`: 可选
  - `expected_labels` 或 `labels`: 可选；按 `label_id` 覆盖 seed 中对应 label
  - `manual_issues`: 可选；问题数组，按 `issue_type` 聚合
- 每个 label override 当前支持：
  - `label_id`: 必填；必须匹配 seed 中的 `label_id`
  - `manual_status`: 当前脚本接受 `pending_manual_review`、`confirmed`、`dismissed`
  - `notes`: 可选

当前聚合输出：

- `manual_review_close_rate`
- `manual_review_sample_coverage_rate`
- `manual_review_issue_count`
- `manual_review_summary.review_row_count`
- `manual_review_summary.sample_coverage_count`
- `manual_review_summary.label_count`
- `manual_review_summary.closed_label_count`
- `manual_review_summary.review_status_counts`
- `manual_review_summary.issue_counts`

明确 out of scope：

- 不新增 `core_facts`、`market_pricing_context`、`falsification_status` 等 `T-406D/T-406E` 字段
- 不把人工复核结果直接回写 chokepoint run、`ResearchTask` 或 `conclusion`
- 不引入新的 7 维 scorecard 或 verification task 生命周期状态机
- 不要求逐证据对象 schema；本轮只复核样本级 label 和问题标记

短期方向：

- 把现有前端内存流水线升级为可持久化的 ResearchTask / ResearchRun。
- 保存每一步的输入、AI 输出、阶段结论、证据质量、问题清单和调优记录。
- 将来源台账、事实审计、反方审计、证伪条件做成强制步骤。
- 在 UI 中持续展示当前步骤、阶段成果、问题和下一步建议。

中期方向：

- 接入 K 线、研报、公告/财报、基础资料和知识图谱作为验证面板。
- 为每个 thesis 形成可复盘档案，记录当时价格、估值、证据、催化剂、证伪条件和后续结果。
- 建立研究质量指标，例如来源覆盖率、confirmed 占比、unknown 数量、反方覆盖率、催化剂兑现率和复盘命中率。

长期方向：

- 从单次 AI 研究升级为自动化研究系统：可定期刷新来源、监控催化剂、提示证伪风险和复盘偏差。
- 让普通投资者通过持续使用模块，逐步学会 Serenity 式底层思考，而不是只消费 AI 生成的结论。
