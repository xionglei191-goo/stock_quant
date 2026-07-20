# 风险与依赖登记册

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-07-18
- Related tasks: T-402-T-421, T-424, T-503, T-570-T-601
- Scope: 当前本机产品路线维护风险、兼容模块风险和非本机发布依赖
- Non-goals: 替代 `tasks/todo.md` 的任务状态，或将协调材料视为发布证据

## 使用说明

本登记册按生命周期维护风险。`open` 表示已识别且仍需缓解，`monitoring` 表示已有控制但需持续复核，`accepted` 表示当前边界内接受，`closed` 表示触发条件已消失并有验证记录。PM 每个里程碑复核一次；高风险触发后 24 小时内升级。

事实、决定与假设分开记录：表内状态和证据路径是当前事实；是否接受或关闭是 PM/责任组决定；未来外部环境是否可用不得作为完成假设。

## 活动维护风险

| 编号 | 风险 | 级别 | 状态 | 触发信号 | 当前控制与证据 | Owner group | 关联任务 | 下次复核 |
|---|---|---|---|---|---|---|---|---|
| MR-1 | `SystemService` 单体继续增长，扩大评审和回归面 | 高 | monitoring | 新业务逻辑直接加入 facade，或缺少 facade 回归 | Growth Freeze；T-570/T-571 已提取 34 个纯助手，T-595 提取 graph traceability；[模块化 ADR](./systemservice-modularization-adr.md) | Platform and Quality | T-503, T-570, T-571, T-595 | 2026-08-01 |
| MR-2 | 超大 `tests/test_system.py` 增加定位和并行修改成本 | 高 | open | 测试继续集中、拆分时数量或断言漂移 | T-576 已完成首批机械拆分；T-593 继续按领域迁移并锁定发现数量，生产逻辑不得混入同一变更 | Platform and Quality | T-576, T-593 | 2026-07-31 |
| MR-3 | 本机验收产物和浏览器 profile 无界增长 | 中 | monitoring | `artifacts/` 持续增长、profile 被长期保留 | T-578/T-580 已加入 dry-run 保留审计并清理 547 个临时目录；tracked/example/被引用证据和持久数据继续受保护 | Platform and Quality | T-578, T-580 | 2026-08-01 |
| MR-4 | 权威文档元数据和时点数据漂移 | 中 | monitoring | 缺少 owner/date/task，或把旧 artifact 数量写成实时事实 | T-575 补齐核心文档元数据和日期；后续门禁只校验结构，不改写历史正文 | PM / Release Coordination | T-575, T-579 | 2026-08-01 |
| MR-5 | 端到端价值案例缺少稳定输入契约或可复跑证据 | 高 | closed | 临时进程结果丢失、非法 symbol 被接受、批量状态含糊 | T-573/T-574 已固化严格 symbol、确定性批量状态、SQLite 重开和 local-only artifact 回归；2026-07-18 `make local-ci` 复验通过 | Research and AI Workflows | T-573, T-574 | 2026-08-01 |
| MR-6 | TDX 导入未提交导致重启后行情缺失 | 高 | closed | 导入成功但新进程读不到，反馈变为 `skipped_no_market_data` | T-572 已显式注入 SQLite store 并增加进程重开读回与价值案例回归；2026-07-18 `make local-ci` 复验通过 | Platform and Quality | T-572 | 2026-08-01 |
| MR-7 | 边界不清来源进入事实、训练或执行层 | 高 | monitoring | 缺 provenance/rights tag；研报观点被提升为事实 | 来源治理、rights tag、人工复核；研报仅观点/参考层；无真实交易 | Governance, Security, and Compliance | T-414, T-417, T-418 | 2026-08-01 |
| MR-8 | 动态配置能力完成后缺少真实纵向纸面证据 | 高 | open | 每日运行中断、账本跨度不足、只凭回测宣称有效、6-12 个月要求从路线图消失 | T-591 建立每日/月度汇总和 3/6/12 月阶段门；在真实观察期完成前仅允许 `accumulating`，不得宣称财务收益 | Research and AI Workflows; PM / Release Coordination | T-588, T-590, T-591 | 2026-08-18 |
| MR-9 | 大批已验收变更仍停留在共享 dirty worktree | 高 | open | 任务标为 DONE 但代码、测试和 handoff 未进入可追溯 Git 基线 | T-594 负责分组审查、完整门禁、handoff 和可提交里程碑收口；不得覆盖用户或其他 agent 变更 | PM / Release Coordination; Platform and Quality | T-594 | 2026-07-19 |
| MR-10 | 本机 42GB 行情库使全量备份恢复和批量图同步超出旧小数据基线 | 中 | monitoring | backup/restore 接近配置超时、可用磁盘不足两倍数据库、批处理被误判为交互回归 | T-601 已把 graph sync 从 58-78 秒优化到 2.24 秒，并完成 1,371.6 秒全量恢复；备份单步默认 1,800 秒且容器内外终止、失败清理，交互/批处理阈值分离 | Platform and Quality | T-601 | 2026-08-01 |

## 兼容模块风险

投委会、签批、执行意图和组织级发布能力是历史兼容/运维模块，不是当前本机公司情报产品主线。保留这些能力不得改变以下边界：所有组合和执行反馈仅为模拟；`live_execution_allowed=false`；不连接真实券商；兼容审批状态不得被表述为真实交易授权。

| 编号 | 风险 | 状态 | 控制 | Owner group | 下次复核 |
|---|---|---|---|---|---|
| CR-1 | 兼容审批/签批被误解为当前主流程或真实执行授权 | accepted | README 明确兼容定位；API 和 UI 保持 paper-only/no-broker 声明 | Product and UI; Governance, Security, and Compliance | 2026-08-01 |
| CR-2 | 兼容模块修改破坏当前公司情报主链 | monitoring | 修改必须运行 golden API/facade 回归，禁止与领域重构混杂 | Platform and Quality | 2026-08-01 |

## 非本机发布外部依赖

截至 2026-07-17，`tasks/todo.md` 记录 17 个开放项均归类为 `blocked_external_evidence`，覆盖 T-402、T-404-T-421 中的真实 staging/production artifact URI 与外部环境证明。这些是非本机组织级发布依赖，不是本机产品代码缺口，也不阻塞本机个人使用目标。

协调包、placeholder URI、`local-only` 或 `staging-local` artifact 均不可替代发布证据。权威执行入口为 [owner packets](./production-evidence-owner-packets.md)、[execution plan](./production-evidence-execution-plan.md) 和 [status board](./production-evidence-status-board.md)。只有真实 URI、artifact inventory 和 strict release gate 全部通过后，PM 才能在 `tasks/todo.md` 更新对应状态。

## 关键依赖与升级规则

| 依赖 | 适用范围 | 未满足影响 | Owner group |
|---|---|---|---|
| 公开来源 provenance、rights tag 与用途边界 | 本机及非本机 | 数据不得进入自动事实/训练层 | Governance, Security, and Compliance |
| evidence id 与原文回链 | 研究主链 | 结论不得视为可复核 | Data and Evidence |
| facade/golden API 回归 | 模块化维护 | 不得合并 `SystemService` 提取 | Platform and Quality |
| 真实外部 URI、inventory、strict gate | 非本机发布 | 组织级发布保持阻塞 | PM / Release Coordination |

- 高风险触发后 24 小时内进入例外事项池，由 owner group 给出止血动作和复核日期。
- 影响来源边界、paper-only/no-broker 边界或非本机发布真实性的风险必须升级到 PM 与 Governance。
- 风险关闭必须记录验证命令或 artifact、关闭日期和责任组；只有叙述性判断不得关闭风险。
