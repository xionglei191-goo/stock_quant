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

#### `POST /api/llm/task-templates/seed`

写入默认生产 LLM 任务模板和对应 baseline prompt 审批记录，覆盖研究摘要、filing 问答、challenger 和事故 RCA。

#### `POST /api/llm/task-templates`

登记生产 LLM 任务模板。`status=approved` 时必须提供已审批的 `approved_prompt_change_id`，否则不能进入生产运行。

请求字段：

- `template_id`
- `task_type`
- `prompt_name`
- `prompt_version`
- `content`
- `provider`
- `model`
- `status`
- `approved_prompt_change_id`
- `fallback_chain`
- `data_domains`
- `allowed_roles`
- `risk_level`

#### `GET /api/llm/task-templates`

按 `task_type`、`status`、`limit` 查询 LLM 任务模板。

#### `GET /api/prompts/changes`

按 `status`、`prompt_name`、`limit` 查询 prompt 变更审批记录，供 Agent 协作 UI 展示 pending/approved prompt。`POST /api/prompts/changes` 创建变更，`POST /api/prompts/changes/{request_id}/approve` 完成审批。

#### `POST /api/llm/tasks/run`

运行已审批 LLM 任务模板。接口会渲染模板变量、调用配置的 OpenAI/Anthropic 上游，并记录模型、prompt 版本、延迟、成本估算、回退路径和人工复核标记。上游不可用时按模板 `fallback_chain` 使用规则摘要、上一稳定输出或人工复核降级。

请求字段：

- `run_id`
- `template_id`
- `role`
- `variables`
- `provider`
- `model`
- `llm_payload`
- `previous_output`

#### `GET /api/llm/tasks/runs`

按 `task_type`、`status`、`limit` 查询 LLM 任务运行记录。

#### `GET /api/llm/tasks/metrics`

返回 LLM 任务模板数、已审批模板数、运行数、失败数、错误率、回退数、人工复核数、平均延迟、成本估算、成本预算和预算使用率。默认告警 `alert_llm_cost_budget` 和 `alert_llm_error_rate` 消费该指标。

#### `POST /api/orchestration/dags`

登记轻量 DAG / 工作流定义，作为 Airflow、Dagster 或 Cron 接入前的生产契约层。

请求字段：

- `dag_id`
- `name`
- `tasks`
- `cadence`
- `owner_role`
- `status`
- `idempotency_key_fields`

#### `POST /api/orchestration/dags/{dag_id}/run`

登记一次工作流运行。默认根据 DAG 的 `idempotency_key_fields` 生成幂等键；同一 DAG 和幂等键再次运行会返回已有运行，除非 `force=true`。

请求字段：

- `run_id`
- `inputs`
- `idempotency_key`
- `output_refs`
- `task_statuses`
- `status`
- `error`
- `force`

#### `POST /api/orchestration/runs/{run_id}/retry`

用失败或待复核 run 的冻结输入创建一次强制重放，返回新 `WorkflowRun`，并在 `inputs.retry_of` / `inputs.retry_error` 中保留原 run 和错误。默认告警 `alert_workflow_failed_runs` 使用 `workflow_failed_runs` 指标提示失败 run 需要重放。

请求字段：

- `run_id`
- `inputs`
- `task_statuses`
- `status`
- `output_refs`
- `force`

#### `GET /api/orchestration/runs`

按 `dag_id`、`status`、`limit` 查询工作流运行记录。

#### `POST /api/lineage/events`

记录数据血缘事件，将任务运行、输入、输出、代码版本、模型版本和 prompt 版本关联起来。

请求字段：

- `lineage_id`
- `job_run_id`
- `dataset`
- `input_refs`
- `output_refs`
- `code_version`
- `model_versions`
- `prompt_versions`

#### `POST /api/model-versions`

登记模型或规则版本，供回放、审计和上线闸门引用。

请求字段：

- `model_version_id`
- `model_name`
- `version`
- `model_type`
- `artifact_uri`
- `training_dataset_ids`
- `prompt_versions`
- `metrics`
- `status`

#### `POST /api/search/semantic`

使用本地语义检索 adapter 对已入库 SearchRecord 执行轻量向量化排序。当前实现为 term-frequency cosine，用于固定 Qdrant/reranker 替换前的 API 契约，并继承原始记录的权限边界。默认过滤 restricted 结果；可用 `include_restricted=true` 显式纳入本地参考/受限结果，返回项会标记 `source_boundary`、`rights_tag` 和 `risk_level`。

请求字段：

- `q`
- `issuer_id`
- `resource_types`
- `include_restricted`
- `limit`

#### `POST /api/search/semantic/benchmark`

对语义检索样本计算 `recall_at_k`。每个样本包含 `q`、`issuer_id`、`resource_types`、`include_restricted` 和 `expected_resource_ids`，用于回归检索质量和权限过滤行为。

#### `GET /api/readiness/vision-gate`

返回项目愿景上线闸门报告，按证据覆盖率、研究结论原文回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、source governance 覆盖率、审计完整性、实体映射准确率、benchmark 指标、季度事故演练覆盖率和 readiness checklist 覆盖率计算 `ready` / `not_ready`，并列出仍需人工验收的真实数据 smoke、UI、容量、备份恢复、权限红队、合规复核和上线 checklist 清单。

#### `GET /api/readiness/checklist`

查询上线验收台账。每个必填项包含 `check_id`、owner、状态、证据 URI、测量时间和指标；未写入记录时状态为 `pending`。可用 `status`、`owner_role` 过滤。过期的 `passed` 记录会在 `effective_status` 中标记为 `expired`，不会计入闸门通过。

#### `POST /api/readiness/checklist/{check_id}`

写入或更新真实上线验收记录，并进入审计日志。支持的 `check_id` 包括 `real_data_smoke_test`、`production_ui_screenshot_acceptance`、`cross_browser_acceptance`、`capacity_latency_report`、`backup_restore_drill`、`permission_red_team_test`、`compliance_review_record` 和 `launch_checklist`。

请求字段：

- `status`
- `owner`
- `evidence_uri`
- `notes`
- `metrics`
- `measured_at`
- `expires_at`

#### `POST /api/governance/sources/{source_id}`

更新公开来源治理字段，包括字段白名单、缓存期限、来源/provenance 引用、用途范围、复核频率和 TOS URI。该接口不修改实际 `rights_tag`，只补齐来源治理台账。

请求字段：

- `field_whitelist`
- `retention_policy`
- `cache_ttl_days`
- `provenance_ref`
- `usage_scope`
- `collection_method`
- `robots_policy`
- `last_reviewed_at`
- `review_cadence`
- `review_owner`
- `review_owner_role`
- `source_tos_uri`
- `risk_level`

#### `GET /api/governance/sources/report`

返回公开来源治理覆盖报告，按 source 汇总 rights tag、字段白名单、缓存期限、provenance 引用、TOS URI、用途范围、复核 owner、缺口项、最新复核记录和 `automation_ready` 白名单状态。可用 `source_type`、`risk_level` 过滤。

#### `POST /api/governance/sources/{source_id}/reviews`

写入一次来源复核记录，并同步更新该来源的 `last_reviewed_at`。复核记录用于季度来源检查，不替代 rights tag；`rejected`、公开性不清、TOS/robots 未复核或用途被阻断会在治理报告中进入 `blocked_reasons`。

请求字段：

- `review_id`
- `reviewed_at`
- `review_period`
- `status`
- `publicness_status`
- `tos_status`
- `robots_status`
- `usage_scope_status`
- `findings`
- `next_review_due_at`
- `notes`

#### `GET /api/governance/source-reviews`

查询来源复核记录。可用 `source_id`、`status`、`due_before`、`limit` 过滤；历史 `authorized_*` source id 会映射到当前 canonical public/local/manual source id。

#### `GET /api/governance/source-review-reminders`

返回季度来源复核提醒和 owner 看板，覆盖从未复核、已逾期和未来窗口内到期的来源，并保留阻断原因供治理看板展示。可用 `as_of`、`due_before`、`due_within_days`、`owner`、`owner_role`、`source_type`、`risk_level`、`include_blocked`、`limit` 过滤。系统治理 UI 消费该接口；默认告警规则 `alert_source_review_overdue` 使用 `source_review_overdue` 指标触发，可通过 `/api/alerts/notify` 写入来源复核通知 outbox。

#### `GET /api/governance/audit-report`

返回审计日志字段完整性报告，检查关键动作是否具备 `event_id`、`actor`、`action`、`resource_type`、`resource_id`、`source` 和 `timestamp`。可用 `action_prefix` 过滤。

#### `GET /api/governance/data-security-report`

扫描已入湖 document、evidence 和 research answer 中的邮箱、手机号、身份证样式和 secret/API key 字面量，返回脱敏 snippet、按类型/来源/严重级别聚合的统计，并用于 `sensitive_findings` 默认告警。可用 `resource_type`、`finding_type`、`issuer_id`、`source_id`、`scan_char_limit`、`limit` 过滤。越权 API 访问会被拦截并以 `permission_denied` 审计事件留痕，默认告警 `alert_permission_denied_events` 使用 `permission_denied_events` 指标触发。

#### `POST /api/connectors/astock/seed`

写入 A 股补充接口候选注册表，包括东财研报发现、巨潮公告补充、腾讯估值快照、同花顺热点、百度概念/资金流、龙虎榜、解禁日历和可选 iwencai。所有候选默认 restricted rights，不进入事实真相层或训练层。

#### `POST /api/connectors/astock`

登记单个 A 股补充接口候选，要求已有 `source_id`，并显式声明 rights tag、限速、字段映射和允许用途。

请求字段：

- `connector_id`
- `provider`
- `endpoint_type`
- `source_id`
- `rights_tag`
- `priority`
- `requires_key`
- `rate_limit_per_minute`
- `field_mapping`
- `allowed_use`

#### `POST /api/connectors/astock/verify`

登记接口验证结果，不直接把第三方数据升级为事实层。`passed` 会把 connector 标为 `verified`；`blocked` 会阻断后续自动化使用。

请求字段：

- `connector_id`
- `status`
- `error`

#### `POST /api/connectors/astock/fetch`

对 A 股补充 connector 的本地样本行执行字段归一化、source URI 脱敏和权限边界评估。当前入口用于公开接口接入前的可重复样本验证；默认只返回 `manual_reference_or_supplemental_research_only` 结果，不写入事实真相层。`blocked` connector 或红区来源会被合规闸门拦截。

请求字段：

- `connector_id`
- `sample_rows`
- `limit`

#### `GET /api/connectors/astock`

按 `provider`、`status`、`requires_key`、`limit` 查询 A 股补充接口注册表。

#### `POST /api/document-parsing/paddleocr`

调用配置的 PaddleOCR-VL 文档解析备用接口。请求必须配置 `AI_QUANT_PADDLEOCR_TOKEN`；服务端只记录 provider、job id 和模型审计，不记录 token。

请求字段：

- `document_id` 可选；解析已入湖文档的 `object_uri`，如无本地对象且 `source_uri` 是 HTTP(S)，则提交 URL
- `file_url` 可选；直接提交远程文件 URL
- `optional_payload` 可选；覆盖 PaddleOCR 可选参数，例如 `useChartRecognition`

返回字段：

- `provider`
- `model`
- `job_id`
- `state`
- `result_url`
- `page_count`
- `pages`
- `text`

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
- `field_mapping`
- `field_whitelist`
- `retention_policy`
- `cache_ttl_days`
- `provenance_ref`
- `usage_scope`
- `collection_method`
- `robots_policy`
- `last_reviewed_at`
- `review_cadence`
- `source_tos_uri`

#### `POST /api/ingestion/documents`

提交原始文档入湖。`source_uri` 会在入库前移除 fragment，并对 `token`、`api_key`、`access_token`、`signature`、`secret` 等敏感查询参数做 `REDACTED` 脱敏，保留可审计 provenance 但不保留密钥样值。

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

写入公开/已提供 EOD 或延时行情点。接口会校验 `security_id`、`source_id`、市场一致性、`rights_tag` 是否超过 source 权限，并阻断实时行情或红区来源。
若 source definition 配置了 `field_whitelist`，请求字段必须落在白名单或运行所需元数据字段内，避免未声明实时/non-display 字段进入自动化链路。

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

批量写入公开/已提供 EOD 或延时行情点，逐条返回创建结果和错误，不因单条失败回滚整个批次。

#### `POST /api/market-data/tdx/preview`

从本地通达信 DuckDB 日线库或 `vipdoc/*.day` 本地文件只读预览行情，不写入状态库。DuckDB 默认路径由 `AI_QUANT_TDX_DUCKDB_PATH` 指定；`vipdoc` 默认路径由 `AI_QUANT_TDX_VIPDOC_PATH` 指定。

请求字段：

- `source_format`：`duckdb|vipdoc`
- `symbols`
- `start_date`
- `end_date`
- `limit`
- `include_summary`

#### `POST /api/market-data/tdx/import`

从本地通达信 DuckDB 日线库或 `vipdoc/*.day` 文件读取行情，并写入公开/已提供 EOD/延时行情层。导入时会复用 `/api/market-data/points` 的 source rights、security、market 和 data_type 校验。

请求字段：

- `source_format`：`duckdb|vipdoc`
- `symbols`
- `security_map`
- `start_date`
- `end_date`
- `limit`
- `source_id`
- `data_type`
- `skip_existing`

#### `GET|POST /api/market-data/quality-report`

返回已入库公开/已提供行情的数据质量报告，覆盖 OHLC 区间一致性、source rights/红区拦截遗留检查、公开来源治理字段缺口、按证券/来源/类型的时间序列覆盖和日期断档。

请求字段：

- `security_id`
- `market`
- `source_id`
- `data_type`
- `max_gap_days`

#### `GET /api/market-data/adjusted`

返回公开/已提供行情的复权可消费视图，不改写原始 MarketDataPoint。支持 `raw`、`backward`、`forward` 三种口径；拆股、反向拆股和送股进入价格因子，现金分红只作为公司行动事件返回，不在未声明总回报方法时混入价格因子。

请求字段：

- `security_id`
- `source_id`
- `data_type`
- `adjustment_mode`
- `start_date`
- `end_date`
- `limit`

#### `GET /api/market-data/returns`

基于 `/api/market-data/adjusted` 的价格口径生成收益序列，供回测、估值和风险模块消费。返回逐期收益、累计收益、波动和最大回撤，并透传复权策略说明。默认 `total_return_method=price_only`；显式传 `cash_dividend_reinvested` 时，ex-date 现金分红按当前价格口径计入当期收益。

请求字段：

- `security_id`
- `source_id`
- `data_type`
- `adjustment_mode`
- `price_field`
- `start_date`
- `end_date`
- `limit`

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

从文档生成证据切片。若当前规则/PDF 文本流解析器无法得到文本，且 `AI_QUANT_PADDLEOCR_TOKEN` 已配置，会先调用 PaddleOCR-VL 备用解析并把 markdown 结果切成 evidence；备用解析未配置、失败或仍无文本时，会创建 `ManualReviewItem` 并返回 `422`。

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

#### `POST /api/research-reports/scan`

扫描本地研报目录，生成 manifest。研报默认作为本地参考观点层，不作为事实真相源，也不默认用于训练。默认根目录可由 `AI_QUANT_RESEARCH_REPORT_ROOT` 指定。

请求字段：

- `root_path`
- `extensions`
- `limit`
- `hash_files`
- `per_broker_sources`

#### `GET /api/research-reports`

按 broker、source、status 或关键词查询研报 manifest。

#### `POST /api/research-reports/{report_id}/ingest`

将单份研报按需登记为 `Document`，保留本地 `object_uri` 和 restricted rights tag，供 OCR、证据抽取和人工引用使用。

请求字段：

- `issuer_id`
- `security_id`
- `document_id`
- `language`

#### `POST /api/research-reports/{report_id}/extract`

对已登记研报执行本地文本抽取和引用片段索引。`.txt` 研报或请求中的 `text` 会生成 `research_report_citation` evidence，并按 `citation_char_limit` 截断；无文本的 PDF/扫描件会创建 `research_report_text_extraction_required` 人工复核项。研报 evidence 只作为本地参考引用，不升级为事实真相源。

请求字段：

- `text`
- `citation_char_limit`
- `parser_version`

#### `POST /api/research/manual-references`

登记私会、路演、expert note 或边界不清转录稿的 metadata-only 人工参考记录，并自动创建 `manual_reference_boundary_review` 人工复核项。该接口拒绝 `body`、`text` 或 `content`，不会把非公开文本写入事实层、证据层、训练层或可执行建议层。

请求字段：

- `document_id`
- `issuer_id`
- `security_id`
- `source_id`
- `document_type`
- `title`
- `source_uri`
- `notes`
- `severity`

#### `POST /api/research/answers`

创建英文 evidence 优先的研究问答与中文摘要审计记录。接口会保留英文原文 evidence、中文摘要、summary 版本、prompt 版本、模型版本、来源公开性和人工覆核状态，并写入审计日志。对非公开或本地参考来源，`english_source_text` 会按 `citation_char_limit` 截断并标记 `citation_truncated`，避免长片段外泄。

请求字段：

- `answer_id`
- `issuer_id`
- `question`
- `evidence_ids`
- `summary_version`
- `prompt_version`
- `model_version`
- `human_review_status`
- `citation_char_limit`
- `reviewer`

#### `GET /api/research/answers/{answer_id}`

返回研究问答与摘要审计记录。

#### `GET /api/research/answers/quality-report`

返回答案级质量和人工复核队列报告，检查 evidence/document 回链、英文原文保留、受限来源引用截断、人工复核状态、summary/prompt/model 版本，并输出 `source_link_rate`、`review_coverage`、`pending_review` 和逐答案 `issues`。可用 `issuer_id`、`human_review_status`、`limit` 过滤；默认告警 `alert_research_answer_pending_review` 使用 `research_answer_pending_reviews` 指标触发。

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

#### `GET /api/operating-reports/red-flag-reminders`

查询月报红灯项 owner、due_date 和逾期状态。可用 `as_of_date`、`owner`、`status` 过滤，供提醒和经营看板使用。

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

#### `POST /api/portfolio/returns`

基于公开行情复权收益序列计算组合级收益、累计收益、波动、最大回撤和分组归因。输入 holdings/weights 后按共同收益日期对齐，权重自动归一；当前 MVP 路径只支持 long-only 权重，不生成交易指令。

请求字段：

- `holdings` 或 `weights`
- `groups`
- `source_id`
- `data_type`
- `adjustment_mode`
- `total_return_method`
- `start_date`
- `end_date`
- `limit`

返回中的 `attribution` 会按 `market`、`currency`、`industry`、`style` 汇总权重和期间贡献；`industry` / `style` 可通过 `groups[security_id]` 显式传入。

#### `POST /api/portfolio/valuation`

基于公开/已提供行情做组合持仓估值。输入持仓股数和现金后，按 `as_of_date` 前最近行情价格计算市值、权重、现金权重和缺失价格清单。该接口只用于研究、回测、估值和风险展示，不代表可交易价格。

请求字段：

- `as_of_date`
- `holdings`
- `cash`
- `currency`
- `source_id`
- `data_type`
- `price_field`

#### `POST /api/portfolio/transactions`

登记真实或回测交易流水，作为持仓、月报绩效和归因的输入层。当前仅支持 long-only buy/sell，写入时校验证券、日期、数量、价格、费用和来源边界。

请求字段：

- `transaction_id`
- `security_id`
- `trade_date`
- `side`
- `quantity`
- `price`
- `fees`
- `source_id`
- `account_id`
- `strategy_id`

#### `GET /api/portfolio/transactions`

按 `security_id`、`account_id`、`strategy_id` 查询交易流水。

#### `GET /api/portfolio/positions`

按交易流水派生 as-of 持仓，返回证券持仓股数、净成本、参与交易数和过滤条件。支持 `as_of_date`、`account_id`、`strategy_id`。

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

#### `POST /api/alerts/incidents/create`

把当前开放告警按其 `playbook_id` 自动生成 IncidentReport，并把 `incident_report_id` 回写到 SystemAlert。可用 `alert_ids` 限定范围；`include_without_playbook=true` 时会使用通用告警分诊剧本。

请求字段：

- `alert_ids`
- `include_without_playbook`
- `root_cause`
- `impact`
- `action_items`
- `owner`

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

#### `POST /api/playbooks/seed`

写入默认事故剧本和季度演练计划，覆盖文档解析失败、数据采集失败、检索降级、LLM 网关失败和权限/敏感数据泄漏五类事故。返回 `playbooks` 与 `schedules`。

请求字段：

- `create_schedules`
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

- 边界不清或禁止自动化的数据尝试进入事实层
- 未通过 Reg FD 审查的来源尝试进入可执行建议
- non-display 数据试图绕过许可边界
- 未审批 prompt 变更试图进入生产
