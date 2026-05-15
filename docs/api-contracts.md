# 接口契约

## 1. 目标

定义工程实现的最小接口边界，保证前后端、数据、研究和治理模块能够并行开发。

## 2. 约定

- 所有接口返回统一 `success/error` 结构
- 所有写操作必须支持幂等键
- 所有关键接口必须记录审计日志
- 所有可执行动作必须有审批状态
- HTTP 调用可用 `X-Actor` 和 `X-Role` 请求头传入操作者与角色；`X-Role` 推荐使用 ASCII 别名：`ceo`、`cio`、`pm`、`risk_compliance`、`platform`、`analyst`、`data_engineer`、`nlp_ml`、`overseas_research`
- GET 接口支持 query string 参数，例如 `/api/graph/query?issuer_id=issuer_001`

## 3. 基础响应格式

```json
{
  "success": true,
  "data": {},
  "error": null,
  "trace_id": "string"
}
```

## 4. 核心接口

### 4.1 数据接入

#### `POST /api/demo/full-flow`

生成一套可展示的端到端 demo 数据，覆盖 source、issuer、security、document、evidence、thesis、signal、decision、execution intent、review、exception、playbook 和 dashboard。

请求字段：

- 无必填字段

#### `GET /api/health`

返回服务健康状态、启动时间、运行时长、状态库类型、对象存储 adapter 和检索 adapter。

#### `GET /api/metrics`

返回核心对象计数、审计事件数量、未处理例外、pending prompt 变更数量、对象存储 adapter 和检索 adapter。

#### `POST /api/llm/openai/chat/completions`

调用配置的 OpenAI 兼容上游 `/v1/chat/completions`。默认上游由 `AI_QUANT_LLM_BASE_URL` 指定，默认模型由 `AI_QUANT_LLM_DEFAULT_MODEL` 指定。请求必须配置 `AI_QUANT_LLM_API_KEY`；服务端只记录模型和 endpoint 审计，不记录请求正文。

请求字段：

- `model` 可选；默认 `qwen3.6-plus`
- `messages`
- 其他字段会原样转发给上游

#### `POST /api/llm/anthropic/messages`

调用配置的 Anthropic 兼容上游 `/v1/messages`。服务端会同时发送 `Authorization: Bearer ...`、`x-api-key` 和 `anthropic-version`，以兼容常见中转服务。

请求字段：

- `model` 可选；默认 `qwen3.6-plus`
- `messages`
- `max_tokens`
- 其他字段会原样转发给上游

#### `POST /api/ingestion/sources`

创建或更新数据源定义。

请求字段：

- `source_id`
- `source_type`
- `license_class`
- `training_allowed`
- `redistribution_allowed`
- `display_use`
- `non_display_use`

#### `POST /api/ingestion/documents`

提交原始文档入湖。

请求字段：

- `document_id`
- `issuer_id`
- `security_id`
- `source_uri`
- `document_type`
- `language`

#### `GET /api/ingestion/documents/{document_id}`

返回原始文档元数据和权限标签。

#### `POST /api/market-data/points`

写入授权 EOD 或延时行情点。接口会校验 `security_id`、`source_id`、市场一致性、`rights_tag` 是否超过 source 权限，并阻断实时行情或红区来源。

请求字段：

- `data_id`
- `security_id`
- `source_id`
- `as_of_date`
- `data_type`
- `close`
- `adjusted_close`
- `volume`
- `rights_tag`

#### `POST /api/market-data/batch`

批量写入授权 EOD 或延时行情点，逐条返回创建结果和错误，不因单条失败回滚整个批次。

#### `POST /api/corporate-actions`

写入公司行动，用于后续复权和估值链路。支持 `split`、`reverse_split`、`cash_dividend`、`stock_dividend`、`symbol_change`。

#### `GET /api/corporate-actions`

按 `security_id`、`action_type` 查询公司行动。

#### `POST /api/entity-mappings`

写入 A/H/U 主体映射。

#### `POST /api/entity-mappings/batch`

批量写入 A/H/U 主体映射，逐条返回创建结果和错误。

#### `GET /api/entity-mappings/quality-report`

根据人工标签样本计算主体映射覆盖率、市场分布、准确率和不匹配样例。

#### `GET /api/market-data`

按 `security_id`、`market`、`source_id`、`data_type` 过滤查询已入库行情点。

请求字段：

- `security_id`
- `market`
- `source_id`
- `data_type`
- `limit`

#### `POST /api/13f/holdings`

写入 SEC 13F 扁平持仓记录，用于中低频拥挤度和反身性风控，不直接触发交易。

请求字段：

- `holding_id`
- `issuer_id`
- `security_id`
- `source_id`
- `filer_cik`
- `filer_name`
- `report_period`
- `shares`
- `value_usd`

#### `GET /api/13f/holdings`

按主体、证券或报告期查询 13F 持仓记录。

请求字段：

- `issuer_id`
- `security_id`
- `report_period`
- `limit`

#### `POST /api/13f/crowding/update`

根据指定主体和报告期的 13F 持仓生成 `CrowdingSnapshot`。

请求字段：

- `issuer_id`
- `report_period`
- `snapshot_id`

#### `POST /api/disclosure-events/classify`

从 8-K、6-K、20-F 等披露文件生成事件标签、严重性、摘要和证据链接。

请求字段：

- `document_id`
- `event_id`
- `event_type`
- `severity`

#### `POST /api/disclosure-events`

手工登记披露事件。

#### `GET /api/disclosure-events`

按 `issuer_id`、`security_id`、`event_type`、`severity` 查询披露事件墙。

#### `POST /api/connectors/sec/recent`

从 SEC EDGAR submissions API 获取指定 CIK 的最近 filings 元数据，不写入系统。

请求字段：

- `cik`
- `document_types`
- `limit`
- `user_agent`

#### `POST /api/connectors/ashare/recent`

从 A 股交易所公告查询接口获取指定证券代码的最近公告元数据，不写入系统。`exchange=auto` 会按证券代码选择上交所或深交所。

请求字段：

- `security_code`
- `exchange`
- `begin_date`
- `end_date`
- `report_type`
- `security_type`
- `limit`
- `user_agent`

#### `POST /api/connectors/hkex/recent`

从 HKEXnews 获取指定检索词的最近公告元数据，不写入系统。

请求字段：

- `query`
- `file_type`
- `limit`
- `language`
- `user_agent`

#### `POST /api/ingestion/sec/recent`

从 SEC EDGAR 获取最近 filings 并写入文档入湖流程。`include_body=true` 时下载主文档正文，`include_attachment=true` 时保存主文档附件。

请求字段：

- `issuer_id`
- `security_id`
- `cik`
- `document_types`
- `limit`
- `include_body`
- `include_attachment`
- `max_attachment_bytes`
- `user_agent`

#### `POST /api/ingestion/ashare/recent`

从 A 股交易所公告查询接口获取最近公告并写入文档入湖流程。`exchange=auto` 会按证券代码选择上交所或深交所，`include_attachment=true` 时保存公告附件。

请求字段：

- `issuer_id`
- `security_id`
- `security_code`
- `exchange`
- `begin_date`
- `end_date`
- `report_type`
- `security_type`
- `limit`
- `include_attachment`
- `max_attachment_bytes`
- `user_agent`

#### `POST /api/ingestion/hkex/recent`

从 HKEXnews 获取最近公告并写入文档入湖流程。`include_attachment=true` 时保存公告附件。

请求字段：

- `issuer_id`
- `security_id`
- `query`
- `file_type`
- `limit`
- `language`
- `include_attachment`
- `max_attachment_bytes`
- `user_agent`

#### `POST /api/ingestion/jobs`

运行批量采集任务。每个 item 会执行 connector normalize、source rights 校验、去重和文档入湖。任务会记录 created/skipped/failed 和逐项错误。

请求字段：

- `job_id`
- `items`
- `include_body`
- `max_body_bytes`
- `user_agent`

#### `GET /api/ingestion/jobs/{job_id}`

返回采集任务状态和错误明细。

#### `POST /api/ingestion/schedules`

创建采集调度配置，保存批量 ingestion payload、cadence 和 retry 策略。

请求字段：

- `schedule_id`
- `name`
- `payload`
- `cadence`
- `retry_limit`
- `next_run_at`

#### `POST /api/ingestion/schedules/run`

执行到期采集调度，失败时按 `retry_limit` 更新 `retrying/failed` 状态。

请求字段：

- `schedule_ids`
- `due_only`

#### `GET /api/ingestion/schedules/{schedule_id}`

返回采集调度、最近任务、重试次数和最近错误。

### 4.2 证据与研究

#### `POST /api/evidence/extract`

从文档生成证据切片。若当前规则/PDF 文本流解析器无法得到文本，会创建 `ManualReviewItem` 并返回 `422`，供 OCR fallback 或人工复核队列处理。

请求字段：

- `document_id`
- `parser_version`
- `model_version`

#### `GET /api/evidence/manual-reviews`

查询解析失败、扫描件或低置信度定位形成的人工复核队列。

请求字段：

- `document_id`
- `status`
- `severity`
- `limit`

#### `GET /api/evidence/quality-report`

返回 evidence 定位覆盖率、平均置信度、人工复核数量和解析失败率。

请求字段：

- `issuer_id`

#### `POST /api/benchmarks`

登记抽取/定位/表格 benchmark 配置与阈值。

#### `POST /api/benchmarks/{benchmark_id}/samples`

登记中英文金标样本，字段包括 `document_id`、`language`、`expected_terms`、`expected_numbers`、`expected_periods`、`expected_tables`、`expected_pages`。

#### `GET /api/benchmarks/{benchmark_id}/samples`

按 `language`、`status` 查询 benchmark 样本集。

#### `POST /api/benchmarks/{benchmark_id}/run`

运行 benchmark suite。系统复用真实 evidence extraction 与结构化抽取规则，输出 `term_f1`、`number_recall`、`period_recall`、`table_recall`、`page_hit_rate`、`evidence_locator_rate`、`avg_confidence`、按语言拆分指标、失败样本和回归样例；低置信度样本会进入失败报告。

#### `POST /api/benchmarks/{benchmark_id}/evaluate`

对外部传入的聚合指标按 benchmark 阈值做一次轻量评估。

#### `POST /api/extractions/run`

对单条 evidence 运行规则基线抽取，生成术语、数值、期间、规则表格和定位指标；如传入 `benchmark_id`，会按阈值计算通过状态。

请求字段：

- `evidence_id`
- `benchmark_id`
- `expected_terms`
- `expected_numbers`
- `expected_periods`
- `expected_tables`
- `parser_version`

#### `GET /api/extractions/{extraction_id}`

返回结构化抽取结果、质量指标和 benchmark 通过状态。

#### `POST /api/thesis/create`

创建 Thesis Card。

请求字段：

- `issuer_id`
- `hypothesis`
- `evidence_ids`
- `falsifiers`
- `owner`

#### `GET /api/thesis/{thesis_id}`

返回研究结论及其证据链。

#### `POST /api/research/answers`

创建英文 evidence 优先的研究问答与中文摘要审计记录。接口会保留英文原文 evidence、中文摘要、summary 版本、prompt 版本、模型版本、来源公开性和人工覆核状态，并写入审计日志。

请求字段：

- `answer_id`
- `issuer_id`
- `question`
- `evidence_ids`
- `summary_version`
- `prompt_version`
- `model_version`
- `human_review_status`
- `reviewer`

#### `GET /api/research/answers/{answer_id}`

返回研究问答与摘要审计记录。

#### `POST /api/research/answers/{answer_id}/review`

人工覆核研究问答摘要，更新 `human_review_status`、`reviewer` 和审计日志。

请求字段：

- `status`
- `reviewer`

### 4.3 评分与信号

#### `POST /api/scoring/run`

运行长线/短线评分。

请求字段：

- `thesis_id`
- `strategy_type`
- `score_profile`

#### `GET /api/signals/{signal_id}`

返回信号得分与来源。

### 4.4 决策治理

#### `POST /api/decision-packs/build`

生成投委会 Pack。

请求字段：

- `signal_ids`
- `risk_checks`
- `red_team_note`

#### `POST /api/approvals/{decision_id}/sign`

人工签字。

请求字段：

- `role`
- `user`
- `comment`

#### `POST /api/execution-intents`

从已审批的投委会决策生成执行意图。未审批决策必须返回 `423`。

请求字段：

- `decision_id`
- `security_id`
- `action`
- `target_weight`
- `rationale`

#### `GET /api/execution-intents/{intent_id}`

返回执行意图。

#### `POST /api/exceptions`

创建例外事项。

请求字段：

- `decision_id`
- `reason`
- `severity`

### 4.5 复盘与图谱

#### `POST /api/reviews/create`

创建复盘记录。

#### `GET /api/reviews/{review_id}`

返回复盘记录。

#### `POST /api/operating-reports`

生成月度经营报告，包含治理指标、研究质量指标、真实收益/持仓绩效指标和红灯项。可传入 `portfolio_returns` / `portfolio_values`、`benchmark_returns` / `benchmark_values`、`turnover` 或持仓权重变化、`attribution`，服务端会计算 `twr`、`total_return`、`max_drawdown`、`benchmark_return`、`active_return`、`information_ratio`、`turnover`。

请求字段：

- `period`
- `report_id`
- `owner`
- `portfolio_returns`
- `benchmark_returns`
- `turnover`
- `attribution`

#### `POST /api/operating-reports/{report_id}/publish`

发布月度经营报告。只有 CEO、CIO 或风险/合规审批角色可发布；发布会写入 `approvals`、`status=published`、`published_at` 和审计事件。

请求字段：

- `approver_role`
- `user`
- `comment`

#### `POST /api/operating-reports/{report_id}/red-flags/{red_flag_id}/resolve`

逐条关闭月报红灯项，写入处理结论、责任人、时间戳和审计事件。

#### `GET /api/operating-reports/{report_id}`

返回月度经营报告。

#### `GET /api/strategy-replays`

按 `decision_id`、`version`、`actual_outcome`、`created_from`、`created_to` 筛选策略回放。

#### `POST /api/strategy-replays`

创建策略回放记录。

请求字段：

- `decision_id`
- `expected_outcome`
- `actual_outcome`
- `version`
- `variance_reason`
- `next_action`

#### `GET /api/strategy-replays/{replay_id}`

返回策略回放记录。

#### `POST /api/portfolio/optimize`

生成纸面组合候选方案。当前实现为可解释的对角 Black-Litterman 原型：由市场权重和波动率得到均衡先验，由 research view 的 `confidence` 绑定 `Omega`，再应用禁投清单、单证券上限、市场预算、行业预算，输出候选权重、风险贡献、换手、压力测试和 walk-forward 诊断。该接口不会创建 execution intent。

请求字段：

- `proposal_id`
- `securities`
- `views`
- `risk_aversion`
- `tau`
- `constraints`
- `risk_budget`
- `stress_scenarios`
- `return_history`

#### `GET /api/portfolio/proposals`

按 `status`、`created_by` 查询纸面组合候选方案。

#### `GET /api/portfolio/proposals/{proposal_id}`

返回纸面组合候选方案。

#### `GET /api/graph/query`

按主体、证据、观点、持仓关系查询图谱。

请求字段：

- `issuer_id`
- `security_id`
- `evidence_id`
- `thesis_id`
- `decision_id`

返回字段包含 `issuers`、`securities`、`market_data`、`corporate_actions`、`documents`、`evidence`、`manual_reviews`、`theses`、`signals`、`decisions`、`execution_intents`、`reviews`、`strategy_replays`、`exceptions`、`entity_mappings`、`research_cards`、`crowding`、`institutional_holdings`、`disclosure_events`、`challengers`、`portfolio_proposals`、`portfolio_positions` 和 `edges`。其中 `portfolio_positions` 由已审批或待审批的 execution intent 派生，`portfolio_proposals` 是纸面组合候选方案，二者都不代表自动交易。

#### `GET /api/search`

内置全文检索 fallback，按 query 命中和字段权重返回结果。

请求字段：

- `q`
- `issuer_id`
- `limit`

#### `POST /api/search`

同 `GET /api/search`，用于复杂查询体。

### 4.6 Dashboard

#### `GET /api/dashboard/ceo`

返回 CEO Dashboard 所需聚合数据。

#### `GET /api/dashboard/risk`

返回风险热图与例外事项。

### 4.7 告警与监控

#### `POST /api/alerts/rules`

注册指标告警规则。

请求字段：

- `rule_id`
- `metric`
- `operator`
- `threshold`
- `severity`
- `owner`
- `description`
- `enabled`
- `playbook_id`

#### `POST /api/alerts/rules/seed`

写入默认告警规则，覆盖人工复核队列、开放例外、待审批 prompt 和待处理决策。

#### `POST /api/alerts/evaluate`

按当前 `/api/metrics` 和 dashboard 计数评估告警规则，返回本次触发、恢复和当前开放告警。

请求字段：

- `seed_defaults`

#### `POST /api/alerts/notify`

把当前开放告警写入通知记录，可指定 `channel`、`target`、`alert_ids`。当前为内部/外部通道适配前的可靠 outbox，不直接调用第三方服务。

#### `GET /api/alerts/notifications`

按 `alert_id`、`channel`、`status` 查询告警通知记录。

#### `GET /api/alerts`

查询告警规则和系统告警。

请求字段：

- `status`
- `severity`
- `owner`
- `limit`

## 5. 接口权限

| 接口 | CEO | CIO | PM | 风险/合规 | 平台负责人 | 分析师 |
|---|---|---|---|---|---|---|
| 数据入湖 | I | I | I | A/R | R | C |
| 证据抽取 | I | C | I | I | A/R | R |
| Thesis 创建 | I | A | I | I | C | R |
| 评分运行 | I | A | R | I | C | C |
| 决策包生成 | A | R | C | C | C | I |
| 签字 | A | R | C | R | I | I |
| 例外事项 | A | C | I | R | C | I |
| 图谱查询 | A | A | R | C | A/R | R |

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `401` | 未认证 |
| `403` | 无权限 |
| `409` | 幂等冲突 |
| `422` | 数据校验失败 |
| `423` | 合规闸门拦截 |
| `429` | 请求过频 |
| `500` | 系统错误 |

## 7. 合规拦截

以下场景必须返回 `423`：

- 未授权数据尝试进入事实层
- 未通过 Reg FD 审查的来源尝试进入可执行建议
- non-display 数据试图绕过许可边界
- 未审批 prompt 变更试图进入生产
