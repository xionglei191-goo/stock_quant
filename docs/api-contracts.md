# 接口契约

## 1. 目标

定义工程实现的最小接口边界，保证前后端、数据、研究和治理模块能够并行开发。

## 2. 约定

- 所有接口返回统一 `success/error` 结构
- 所有写操作必须支持幂等键
- 所有关键接口必须记录审计日志
- 系统定位为投资分析、证据研究、模拟组合和复盘反馈；不连接真实券商，不做自动下单
- 系统必须支持宏观视野和产业链发散分析：从热点、主题、技术、产品或政策出发，沿上游材料、设备、制造、封装、零部件、模组、品牌、渠道和下游应用扩展，并把每家公司放到明确产业链位置
- 所有“执行意图”均为纸面/模拟语义，只用于把研究决策转成模拟持仓和反馈分析输入
- 所有可执行动作必须有审批状态；当前可执行动作只允许模拟成交、通知 outbox、缓存治理 handoff 等非交易动作
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

生成一套可展示的端到端 demo 数据，覆盖 source、issuer、security、document、evidence、thesis、signal、decision、纸面执行意图、模拟持仓反馈、review、exception、playbook 和 dashboard。该 demo 不代表真实交易链路。

请求字段：

- 无必填字段

#### `GET /api/health`

返回服务健康状态、启动时间、运行时长、状态库类型、对象存储 adapter 和检索 adapter。

#### `GET /api/metrics`

返回核心对象计数、审计事件数量、未处理例外、pending prompt 变更数量、对象存储 adapter 和检索 adapter。

#### `GET|POST /api/observability/logs/export`

导出结构化 JSON 日志 payload，覆盖 audit、alerts、workflow 和 notifications 来源。接口只返回 payload，不写外部日志系统；可用 `sources`、`level`、`action_prefix`、`resource_type`、`status`、`trace_id` 和 `limit` 过滤。传 `record_export=true` 时会写审计事件 `export_structured_logs`。

#### `GET|POST /api/observability/otel/export`

把结构化日志转换为 OpenTelemetry OTLP logs JSON payload，包含 `resourceLogs`、`scopeLogs`、`logRecords`、service/resource attributes、severity、body、attributes 和 hash 化 traceId。支持同结构化日志过滤字段，以及 `service_name`、`service_namespace`、`environment`、`schema_url`；接口不直接连接 collector。传 `record_export=true` 时会写审计事件 `export_opentelemetry_logs`。

#### `POST /api/observability/otel/submit`

把 OTLP logs JSON payload 写入 `AlertNotification` outbox，默认 `channel=opentelemetry_logs_outbox`、`target=otel://collector/v1/logs`。可覆盖 `target`、`channel`、`provider`、`notification_id`、`force`、`mark_sent`、`max_delivery_attempts` 和 `delivery_backoff`，后续由 `/api/alerts/notifications/deliver` dry-run、HTTP(S) webhook 或 state-only sender 推进发送状态。

#### `GET|POST /api/observability/readiness-report`

汇总生产监控验收缺口，检查结构化日志、OTLP payload、非本机 OpenTelemetry logs/metrics/traces collector 参数、collector 后端存储/查询证据、日志保留策略、真实外部告警发送记录、外部告警交付 evidence URI、事故剧本 owner/SLA/止血/回滚覆盖率和季度演练覆盖率。接口只生成验收报告，不连接生产 collector 或外部告警系统；外部告警 gate 需要发送记录和 evidence URI 同时存在。返回 `ready_for_production_observability`、`gates`、`missing_requirements`、`collector`、`retention_policy`、`notifications`、`playbooks` 和 `drill_summary`。传 `record_readiness=true` 时写审计事件 `observability_readiness_report`。

请求字段：

- `collector` / `collector_endpoint` / `logs_endpoint` / `metrics_endpoint` / `traces_endpoint`
- `retention_policy` / `retention_days` / `retention_owner` / `retention_policy_uri`
- `artifact_uris`
- `playbook_evidence`
- `drill_results`
- `record_readiness`

#### `POST /api/llm/openai/chat/completions`

调用配置的 OpenAI 兼容上游 `/v1/chat/completions`。默认上游由 `AI_QUANT_LLM_BASE_URL` 指定，默认模型由 `AI_QUANT_LLM_DEFAULT_MODEL` 指定。请求必须配置 `AI_QUANT_LLM_API_KEY`；服务端只记录模型和 endpoint 审计，不记录请求正文。

请求字段：

- `model` 可选；默认 `qwen3.6-plus`
- `messages`
- 其他字段会原样转发给上游

本机长期使用时，可用 `.venv/bin/python scripts/local_ai_capability_acceptance.py --base-url http://127.0.0.1:8000 --output artifacts/local-ai-capability-acceptance.json` 同时验收 LLM gateway 和 PaddleOCR-VL。该脚本走真实 API 调用，但输出会脱敏，不包含 API key、PaddleOCR 结果下载 URL 或完整模型响应。

#### `POST /api/llm/anthropic/messages`

调用配置的 Anthropic 兼容上游 `/v1/messages`。服务端会同时发送 `Authorization: Bearer ...`、`x-api-key` 和 `anthropic-version`，以兼容常见中转服务。

请求字段：

- `model` 可选；默认 `qwen3.6-plus`
- `messages`
- `max_tokens`
- 其他字段会原样转发给上游

#### `POST /api/llm/task-templates/seed`

写入默认生产 LLM 任务模板和对应 baseline prompt 审批记录，覆盖研究摘要、研报摘要、filing 问答、challenger、red team 和事故 RCA。模板在 `input_schema` / `output_schema.acceptance_thresholds` 中记录来源边界、必填输出和人工复核阈值。

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

#### `GET /api/llm/tasks/review-queue`

返回 LLM 任务结果人工复核队列。队列由 `LLMTaskRun` 派生，覆盖高风险模板、失败/待复核状态、fallback、上游错误、延迟 SLA breach 和成本阈值 breach。支持 `task_type`、`status`、`reason`、`min_severity`、`limit` 过滤，返回 `review_severity`、`reasons`、`reviewer_role` 和 reason 聚合计数。

#### `GET /api/llm/tasks/metrics`

返回 LLM 任务模板数、已审批模板数、运行数、失败数、错误率、回退数、人工复核数、平均延迟、成本估算、成本预算和预算使用率。`cost_budget` 使用环境配置预算与已批准、未过期的 `/api/llm/budget-approvals` 预算上限中的较大值，并额外返回 `configured_cost_budget`、`approved_cost_budget`、`approved_budget_active`。默认告警 `alert_llm_cost_budget` 和 `alert_llm_error_rate` 消费该指标。

#### `GET /api/llm/tasks/escalations`

返回 LLM SLA / 预算升级报告。报告基于成本预算使用率、错误率、fallback 率、人工复核 backlog 和逐 run 复核原因生成升级项；每条包含 severity、owner_role、channel、target、recommended_action 和外部 sender 接入边界。支持 `budget_warning_threshold`、`budget_critical_threshold`、`error_rate_threshold`、`fallback_rate_threshold`、`review_backlog_threshold`、`channels`、`targets`、`limit`。

#### `POST /api/llm/tasks/escalations/notify`

把 LLM SLA / 预算升级项写入 `AlertNotification` outbox，默认状态为 `pending`，供 `/api/alerts/notifications/deliver` dry-run、HTTP(S) webhook、SMTP email 或 Slack webhook sender 发送。支持同报告接口的阈值和 channel/target 配置，并支持 `force` 覆盖幂等通知、`mark_sent` 标记已发送。

#### `GET /api/llm/budget-approvals`

查询 LLM 预算升级审批记录，支持 `status`、`escalation_id`、`requested_by`、`limit`。返回 pending/approved 计数、当前有效成本预算和审批列表。

#### `POST /api/llm/budget-approvals`

基于当前 LLM 预算升级报告创建预算审批。可传 `escalation_id` 指定 `cost_budget_critical` / `cost_budget_warning` / `cost_threshold_breach` 升级项；未传时自动选取当前报告中的预算类升级项。`requested_budget` 或 `requested_cost_budget` 必须大于当前有效预算；也可用 `budget_multiplier` 自动放大。审批初始状态为 `pending`，并写入审计。

#### `POST /api/llm/budget-approvals/{approval_id}/decide`

由 `CEO`、`CIO`、`风险/合规` 或 `NLP/ML 负责人` 角色做出 `approved` / `rejected` 决策。批准后，该 `requested_budget` 会作为未过期的有效预算候选进入 `/api/llm/tasks/metrics`。

#### `POST /api/llm/budget-approvals/{approval_id}/sync`

把已批准的 LLM 预算审批写入外部财务/云预算系统同步 outbox。默认 `channel=budget_sync_outbox`、`target=budget://finance_cloud_budget`；也可传 `channel`、`target`、`external_system`、`max_delivery_attempts`、`delivery_backoff` 和 `metadata`，后续由 `/api/alerts/notifications/deliver` 复用 webhook/email/slack 发送状态机推进。

#### `GET|POST /api/llm/readiness-report`

输出 LLM / Agent 工作流生产验收报告，汇总 approved task templates、approved prompt change 回链、pending prompt、LLM run 的 prompt/model/cost/latency 追溯、研究答案 summary/prompt/model 版本、高风险 thesis challenger 覆盖率、人工复核/升级队列、预算审批同步 outbox、预算同步外部 evidence URI 和真实模型质量/回退质量 artifact URI。接口只检查台账和外部证据 URI，不调用外部模型；`budget_sync_evidence_uri` 必须关联已创建的预算同步 outbox 记录，单独提供 URI 不会通过预算同步 gate；固定 `automation_allowed=false`、`live_execution_allowed=false`。返回 `ready_for_llm_production`、`gates`、`missing_requirements`、`templates`、`prompt_governance`、`runs`、`research_answers`、`challenger` 和 `budget`；传 `record_readiness=true` 时写审计事件 `llm_readiness_report`。

请求字段：

- `gateway_configured`
- `artifact_uris`
- `review_limit`
- `escalation_limit`
- `record_readiness`

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
- `started_at`
- `completed_at`

#### `POST /api/orchestration/dags/{dag_id}/execute`

使用内置轻量 DAG 执行器按拓扑顺序运行白名单本地任务，并将每步结果写入 `WorkflowRun.task_statuses`、`inputs.task_results`、`output_refs` 和 `LineageEvent`。当前支持 `ingest_document`、`extract_evidence`、`structured_extraction` / `extract_structured_facts`、`search_rebuild`、`benchmark_sample_register`、`benchmark_run`、`market_data_backfill`、`document_parse` / `paddleocr` 和 `noop`。任务 payload 支持 `${inputs.foo}`、`${task_id.output_ids.0}`、`${task_id.output_refs.0}` 占位符，用于把上游产物传给下游任务。可传 `task_ids` / `tasks` / `task_id` 或 `queues` / `queue` 做任务级选择和队列隔离。接口仍是单进程内置执行器；分布式队列、外部 sensor 和大规模 backfill 达到阈值后应切换 Airflow/Dagster。

请求字段：

- `run_id`
- `inputs`
- `idempotency_key`
- `task_payloads`
- `code_version`
- `model_versions`
- `prompt_versions`
- `force`
- `continue_on_error`
- `allow_inactive`
- `allow_unresolved_dependencies`

#### `POST /api/orchestration/dags/{dag_id}/backfill`

生成或登记 DAG backfill 计划。默认 `dry_run=true`，仅返回按日期展开的计划，不写入 `WorkflowRun`；传 `dry_run=false` 且 `execute=true` 时会为每个运行日期登记一次 `queued` run，并在 `inputs.backfill` 中保留日期、任务选择、队列隔离和幂等信息。支持 `run_dates`，或 `start_date` / `end_date` 加 `cadence`；`business_daily` 会跳过周末。可用 `queues` / `queue` 和 `task_ids` / `tasks` 限制 backfill 范围，未选中的任务在计划和登记 run 中标为 `skipped`。同一 DAG、日期、任务选择和队列组合会复用已有幂等 run，除非传 `force=true`。

请求字段：

- `run_dates`
- `start_date`
- `end_date`
- `cadence`
- `max_runs`
- `as_of_field`
- `inputs`
- `queues`
- `task_ids`
- `dry_run`
- `execute`
- `force`
- `run_id_prefix`
- `idempotency_prefix`

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

#### `GET /api/orchestration/sla-report`

按 DAG/run 运行状态和任务级 `sla_minutes` 输出调度 SLA 报告。`failed`、`needs_review` 和超过 SLA 的 `queued/running` 会进入 `breach_count`，并返回 owner、失败 task、错误、是否可重试和是否需要建单。支持 `dag_id`、`status`、`as_of`、`default_sla_minutes`、`include_all`、`limit`。

#### `GET /api/orchestration/schedule-calendar`

按 DAG `cadence` 和历史 run 推导未来调度窗口，支持 `hourly`、`daily`、`business_daily`、`weekly`、`monthly` 和 `manual`。返回每个 workflow 的 last run、next run、upcoming runs、owner、任务数和是否需要外部调度器，并给出 Airflow/Dagster 触发阈值建议。支持 `dag_id`、`status`、`as_of`、`horizon_days`、`per_workflow_limit`、`include_manual`、`include_paused`、`limit`。

#### `POST /api/orchestration/schedule-calendar`

同 `GET /api/orchestration/schedule-calendar`，用于复杂过滤 payload。

#### `GET|POST /api/orchestration/scheduler-handoff`

导出外部调度器 handoff 规划包，不创建真实 Airflow/Dagster/Cron 部署。接口会汇总 DAG cadence、upcoming runs、队列到 worker pool 的映射、未解析依赖到 external sensor 的映射、backfill gap 预览、OpenLineage/MLflow 适配边界和缺失外部证据项。返回 `recommended_orchestrator`、`worker_pools`、`external_sensors`、逐 workflow `adapter_contract` 和 `missing_external_evidence`；固定 `automation_allowed=false`、`external_deployment_required=true`。

请求字段：

- `dag_id`
- `status`
- `include_paused`
- `include_backfill_plan`
- `as_of`
- `horizon_days`
- `backfill_window_days`
- `namespace`
- `limit`

#### `GET|POST /api/orchestration/readiness-report`

输出任务编排、血缘和模型治理生产验收报告，汇总 active workflow、run/retry/replay、dependency graph、SLA breach/incident、scheduler handoff、OpenLineage payload export/outbox、MLflow payload export/outbox、approved model artifact coverage，以及真实 Airflow/Dagster/Cron、worker pool、external sensor、大窗口 backfill、OpenLineage client 和 MLflow registry 证据 URI。worker pool、external sensor 和 backfill gate 都要求 artifact URI；即使当前样本为单队列、无外部 sensor 或无需 backfill，也要提供已复核为空/不适用的证据。接口不部署外部调度器、不连接外部 catalog/registry；固定 `automation_allowed=false`、`external_deployment_required=true`。返回 `ready_for_orchestration_production`、`gates`、`missing_requirements`、`workflow_summary`、`dependency_graph`、`sla`、`replay`、`lineage` 和 `model_registry`；传 `record_readiness=true` 时写审计事件 `orchestration_readiness_report`。

请求字段：

- `dag_id`
- `as_of`
- `scheduler_endpoint`
- `openlineage_endpoint`
- `mlflow_endpoint`
- `artifact_uris`
- `record_readiness`

#### `GET /api/orchestration/dependency-graph`

输出轻量 DAG 的任务依赖可视化报告，支持 task 字段 `depends_on` / `dependencies` / `upstream`。返回每个 workflow 的节点、边、拓扑顺序、未解析依赖、ready/blocked task、latest run 状态和 lineage 摘要。该接口仅用于可视化和排障，不替代生产调度器；响应中的 adapter recommendation 给出 Airflow/Dagster 与 OpenLineage adapter 的触发条件。支持 `dag_id`、`status`、`include_paused`、`include_runs`、`include_lineage`、`limit`。

#### `POST /api/orchestration/dependency-graph`

同 `GET /api/orchestration/dependency-graph`，用于复杂过滤 payload。

#### `POST /api/orchestration/incidents/create`

基于 SLA 报告为未建单的 failed、needs_review 或 runtime SLA breach run 自动创建 `IncidentReport`，默认使用 `pb_workflow_sla_breach`，幂等 report id 为 `ir_workflow_{run_id}`，避免重复建单。

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

#### `GET /api/orchestration/openlineage/export`

把轻量 workflow run、lineage event、模型版本和 prompt 版本整理为 OpenLineage-compatible payload。当前接口只做 dry-run payload export，不直接提交外部 lineage service；返回 `adapter.external_submission_required=true`。支持 `dag_id`、`run_id`、`status`、`namespace`、`producer`、`schema_url`、`include_model_facets`、`record_export`、`limit`。

#### `POST /api/orchestration/openlineage/export`

同 `GET /api/orchestration/openlineage/export`，用于复杂过滤 payload。`record_export=true` 时写入导出审计事件。

#### `POST /api/orchestration/openlineage/submit`

把 OpenLineage-compatible export payload 写入 `AlertNotification` outbox，默认 channel 为 `openlineage_submission_outbox`，默认 target 为 `openlineage://lineage-service`。接口不直接访问外部 lineage service；后续可由 `/api/alerts/notifications/deliver` dry-run 或通用 HTTP(S) webhook sender 推进 `pending/sent/failed` 状态，协议级 OpenLineage client 仍由生产适配器接入。支持 export 过滤字段，以及 `channel`、`target`、`force`、`mark_sent`、`max_delivery_attempts`、`delivery_backoff`。

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

#### `GET /api/model-versions/mlflow/export`

把内置模型版本记录转换为 MLflow Model Registry-compatible payload，包含 registered model、model version、stage/alias、tags、metrics/params 和 lineage 回链。当前接口只做 dry-run payload export，不直接调用外部 MLflow registry；返回 `adapter.external_registration_required=true`。支持 `model_name`、`model_version_id`、`status`、`registered_model_prefix`、`include_metrics`、`record_export`、`limit`。

#### `POST /api/model-versions/mlflow/export`

同 `GET /api/model-versions/mlflow/export`，用于复杂过滤 payload。`record_export=true` 时写入导出审计事件。

#### `POST /api/model-versions/mlflow/register`

把 MLflow Model Registry-compatible export payload 写入 `AlertNotification` outbox，默认 channel 为 `mlflow_registry_outbox`，默认 target 为 `mlflow://model-registry`。接口不直接访问外部 MLflow registry；后续可由 `/api/alerts/notifications/deliver` dry-run 或通用 HTTP(S) webhook sender 推进 `pending/sent/failed` 状态，协议级 MLflow client 仍由生产适配器接入。支持 export 过滤字段，以及 `channel`、`target`、`force`、`mark_sent`、`max_delivery_attempts`、`delivery_backoff`。

#### `POST /api/search/semantic`

使用本地语义检索 adapter 对已入库 SearchRecord 执行轻量向量化排序。当前实现为 term-frequency cosine，用于固定 Qdrant/reranker 替换前的 API 契约，并继承原始记录的权限边界。默认过滤 restricted 结果；可用 `include_restricted=true` 显式纳入本地参考/受限结果，返回项会标记 `source_boundary`、`rights_tag` 和 `risk_level`。

请求字段：

- `q`
- `issuer_id`
- `resource_types`
- `include_restricted`
- `limit`

#### `POST /api/search/semantic/rerank`

复用语义召回候选并执行本地可解释重排，作为 Qdrant/专用 reranker 接入前的 pipeline 契约。当前重排分由 `semantic_score`、query term coverage、资源权重和 restricted boundary penalty 组成；restricted 结果会标记 `requires_manual_boundary_review`。返回 `embedding_backend`、`reranker`、`score_components`、`matched_terms` 和 adapter trigger，便于后续替换向量库或 reranker 模型。支持 `q`、`issuer_id`、`resource_types`、`include_restricted`、`candidate_limit`、`limit`。

#### `GET /api/search/semantic/rerank`

同 `POST /api/search/semantic/rerank`，用于简单查询参数。

#### `POST /api/search/semantic/llm-rerank`

复用 `/api/search/semantic/rerank` 的候选集，再调用已审批 `llmtpl_search_rerank_v1` 模板执行 LLM ordering assist。模型输出只允许作为排序辅助，不得作为事实结论或交易信号；接口固定 `automation_allowed=false`、`live_execution_allowed=false`、`human_review_required=true`。当 LLM 网关未配置、上游失败或输出 JSON 无法解析时，自动保留本地可解释重排顺序，并返回 `fallback_used`、`llm_run`、`parse_error` 和 `rerank_source=local_fallback`。

请求字段：

- `q`
- `issuer_id`
- `resource_types`
- `include_restricted`
- `candidate_limit`
- `limit`

#### `POST /api/search/semantic/llm-rerank/benchmark`

对 LLM rerank / local fallback 排序做离线质量评估。请求字段：

- `benchmark_id`
- `samples`：每条包含 `q` / `query`、`issuer_id`、`expected_resource_refs` 或 `expected_resource_ids`、`resource_types`、`candidate_limit`、`limit`
- `run_model`
- `sample_limit`
- `candidate_limit`
- `limit`

返回 `top1_accuracy`、`coverage_at_k`、`mrr`、`fallback_rate`、`parse_error_rate`、`llm_ordering_rate` 和逐样本 `rank` / `returned_resource_refs`。该接口固定 `automation_allowed=false`、`live_execution_allowed=false`，只作为离线质量评估，不把模型排序视为事实结论或交易信号。
- `run_model`
- `llm_run_id`
- `temperature`

#### `GET /api/search/semantic/llm-rerank`

同 `POST /api/search/semantic/llm-rerank`，用于简单查询参数。

#### `POST /api/search/semantic/benchmark`

对语义检索样本计算 `recall_at_k`。每个样本包含 `q`、`issuer_id`、`resource_types`、`include_restricted` 和 `expected_resource_ids`，用于回归检索质量和权限过滤行为。

#### `GET /api/readiness/vision-gate`

返回项目愿景上线闸门报告，按证据覆盖率、研究结论原文回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、source governance 覆盖率、审计完整性、图谱回溯率、实体映射准确率、benchmark 指标、季度事故演练覆盖率和 readiness checklist 覆盖率计算 `ready` / `not_ready`，并列出仍需人工验收的真实数据 smoke、UI、容量、备份恢复、OpenTelemetry collector、权限红队、合规复核和上线 checklist 清单。

#### `GET /api/readiness/checklist`

查询上线验收台账。每个必填项包含 `check_id`、owner、状态、证据 URI、测量时间和指标；未写入记录时状态为 `pending`。可用 `status`、`owner_role` 过滤。过期的 `passed` 记录会在 `effective_status` 中标记为 `expired`，不会计入闸门通过。`passed` 记录还必须带外部归档型 evidence URI；裸本机路径、`file://`、`local://`、服务连接串和只有域名的 HTTP(S) 服务根地址不会计入通过，会标记为 `invalid_evidence_uri`。

#### `POST /api/readiness/checklist/{check_id}`

写入或更新真实上线验收记录，并进入审计日志。支持的 `check_id` 包括 `real_data_smoke_test`、`production_ui_screenshot_acceptance`、`cross_browser_acceptance`、`capacity_latency_report`、`backup_restore_drill`、`otel_collector_drill`、`permission_red_team_test`、`compliance_review_record` 和 `launch_checklist`。

请求字段：

- `status`
- `owner`
- `evidence_uri`
- `notes`
- `metrics`
- `measured_at`
- `expires_at`

#### `POST /api/readiness/capacity-baseline`

接收 `scripts/capacity_baseline.py` 或真实环境容量/延迟基线结果，按 `max_ms` 与阈值自动判定 `capacity_latency_report` 为 `passed` / `failed` 并回填 readiness checklist。返回 readiness check、阈值 breach 列表和 passed 布尔值。

#### `GET|POST /api/readiness/deployment-report`

生成生产部署验收报告，集中检查生产/预发环境名称、PostgreSQL/S3/OpenSearch 参数存在性、生产参数 manifest artifact URI、外部密钥管理 provider、密钥轮换证据、备份恢复记录、容量 baseline、权限红队、合规复核、CEO launch checklist、发布 checklist、灰度计划 artifact URI、回滚计划 artifact URI 和真实券商/自动下单关闭边界。灰度/回滚窗口字段只作为计划元数据，不能替代 artifact URI。接口会拒绝 `secret_value`、`api_key`、`token`、`password`、`private_key` 等敏感字段，响应只返回配置存在性和 evidence URI，不回显真实密钥或 DSN。传 `record_readiness=true` 时写审计事件 `readiness_deployment_report`。

请求字段：

- `environment_name`
- `postgres_configured`
- `s3_configured`
- `opensearch_configured`
- `secret_manager_provider`
- `secret_injection_mode`
- `release_plan`
- `artifact_uris`
- `record_readiness`

#### `GET|POST /api/readiness/ui-report`

生成 UI 上线验收报告，汇总 `scripts/ui_static_check.py` 静态合约、`production_ui_screenshot_acceptance` / `cross_browser_acceptance` readiness checklist、Headless Chrome browser acceptance metrics、真实数据量/分页/过滤/错误恢复工作流证据、无重叠/无溢出视觉复核和权限态复核 artifact URI。报告会把跨浏览器矩阵覆盖率、数据量、分页、过滤、错误恢复、文本无重叠、视觉无溢出和 allowed/denied 权限态拆成独立 gate；跨浏览器覆盖率必须从 metrics 中解析出足够 browser family 与 desktop/mobile viewport，单独提供 artifact URI 只能满足证据 URI gate，不能替代矩阵内容。接口只读取本地 HTML 与已回填 evidence，不启动浏览器、不把缺失的真实环境验收自动标记为通过；`record_readiness=true` 时写审计事件 `ui_readiness_report`。

请求字段：

- `artifact_uris`
- `browser_acceptance`
- `workflow_evidence`
- `min_real_data_rows`
- `required_browser_family_count`
- `run_node_static_check`
- `record_readiness`

`scripts/staging_acceptance.py --record-readiness` 默认只把 Headless Chrome 桌面/移动截图写入 `production_ui_screenshot_acceptance`；只有额外提供 `--cross-browser-matrix <json>` 或环境变量 `AI_QUANT_CROSS_BROWSER_MATRIX` 时才会写入 `cross_browser_acceptance`，避免把单浏览器截图伪装成跨浏览器验收。

#### `GET /api/readiness/evidence-package`

生成上线验收证据包 manifest，汇总 readiness checklist、vision gate 未通过项、owner 修复计划和外部 adapter 验证矩阵。该接口只产出审计清单，不把未执行的真实环境测试标记为通过；真实 smoke、UI 截图、容量、备份恢复、权限红队和合规复核仍必须通过 checklist 回填外部归档型 evidence URI。支持 `include_passed`、`record_export`、`limit`。

导出 JSON 后可用 `python3 scripts/readiness_evidence_package_check.py <package.json> --output artifacts/readiness-evidence-package-validation.json` 做离线发布前校验；导出给校验器的包应传 `include_passed=true`，否则已通过 checklist 的 evidence URI 不会全部出现在 manifest 中。该校验器要求 `ready_for_launch=true`、`missing_evidence_count=0`、`failed_gate_count=0`、9 个必填 readiness check 全覆盖、外部验证矩阵覆盖 PostgreSQL/S3/OpenSearch、OpenTelemetry、Neo4j/Qdrant、OpenLineage/MLflow、KMS/lifecycle executor 和生产 UI 浏览器，并检查每条 evidence URI 都是外部归档型引用且指向具体对象或路径；`artifact://local-*`、`artifact://staging-local`、`artifact://local-staging`、`artifact://staging-test`、`artifact://staging-acceptance` 和 `artifact://demo` 这类本机或样例前缀不会通过。`scripts/production_artifact_inventory_check.py` 进一步要求每条 release evidence URI 有归档 inventory 行，记录 sha256、size、环境、生产者、owner、content type、retention 和 immutability，并拒绝仍带模板占位符的 URI。`scripts/production_evidence_plan_check.py`、`scripts/production_closure_manifest_check.py` 和 `scripts/readiness_evidence_package_check.py` 均支持 `--output` 原子写入校验结果；发布归档建议使用 `artifacts/readiness-evidence-package-validation.json`、`artifacts/production-closure-manifest-validation.json` 和 release gate result。`scripts/production_evidence_plan_to_manifest.py` 可把 owner 回填的证据采集计划映射成 production closure manifest 草案，但不替代真实 readiness evidence package 导出；其 `manifest_generation` 对象包含 `skipped_mapping_count`、`mapped_readiness_check_count`、`missing_readiness_check_count` 和 `missing_external_validation_scope_count`，供自动化门禁直接读取映射覆盖情况；`scripts/production_release_gate.py` 可把 filled plan、真实 evidence package、artifact inventory、manifest 生成和严格校验串成一个发布门禁，并在结果中输出 `stage_count`、`passed_stage_count`、`failed_stage_count` 和 `failed_stage_names`；`scripts/production_task_status_finalize.py` 复跑同一门禁后才会把 `tasks/todo.md` 的 `BLOCKED` 项迁入 `DONE`。最终目标完成审计按部署目标分两类：本机个人生产运行使用 `python3 scripts/project_completion_audit.py --local-production-audit artifacts/local-production-audit.json --local-ai-acceptance artifacts/local-ai-capability-acceptance.json --output artifacts/project-completion-audit.json`；非本机组织级发布使用 `python3 scripts/project_completion_audit.py --manifest artifacts/production-closure-manifest.json --evidence-plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --output artifacts/project-completion-audit.json`。未达成对应证据时该脚本返回非零退出码。该审计的机器可读字段包括 `target_mode`、`local_production_ready`、`failed_requirement_ids`、`blocked_requirement_ids`、`open_requirement_ids`、`needs_code_work_count`、`blocked_external_evidence_count` 和 `blocked_external_evidence_task_ids`，发布脚本应以这些字段而不是人工阅读长报告来判断是否仍阻塞。

#### `POST /api/readiness/evidence-package`

同 `GET /api/readiness/evidence-package`，用于复杂过滤 payload。

#### `POST /api/readiness/evidence-package/notify`

根据证据包中缺失或未通过的必填 checklist 项写入 readiness notification outbox。支持 `owner_targets`、`owner_channels`、`channel`、`target`、`force`、`mark_sent`；通知仍需通过 `/api/alerts/notifications/deliver` 或外部发送器推进。

#### `GET /api/readiness/remediation-report`

基于 `/api/readiness/vision-gate` 和 readiness checklist 生成上线修复计划。返回未通过 gate、pending/expired checklist 的 owner、priority、当前值、阈值、建议动作和是否需要 evidence URI，并按 owner 汇总。支持 `owner_role`、`include_passed`、`limit`。

#### `POST /api/readiness/remediation-report`

同 `GET /api/readiness/remediation-report`，用于复杂过滤 payload。

请求字段：

- `result`
- `thresholds`
- `default_threshold_ms`
- `evidence_uri`
- `measured_at`
- `expires_at`
- `owner`

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

#### `GET /api/governance/source-review-escalations`

返回来源复核 SLA 升级报告。报告复用 source review reminders，按逾期天数、红/黄区来源、缺失复核、TOS/robots/publicness/usage blocker 计算 severity、owner、channel、target 和 recommended_action，并返回外部发送边界。支持 `as_of`、`due_before`、`due_within_days`、`owner`、`owner_role`、`source_type`、`risk_level`、`include_blocked`、`include_due_soon`、`include_missing_review`、`min_severity`、`critical_days_overdue`、`high_days_overdue`、`due_soon_high_risk_days`、`channels`、`targets`、`limit`。

#### `POST /api/governance/source-review-escalations/notify`

把来源复核 SLA 升级项写入 `AlertNotification` outbox，默认状态为 `pending`，供 `/api/alerts/notifications/deliver` dry-run、HTTP(S) webhook、SMTP email 或 Slack webhook sender 发送。支持同报告接口的过滤与策略字段，并支持 `force` 覆盖幂等通知、`mark_sent` 标记已发送、`max_delivery_attempts` 和 `delivery_backoff`。

#### `GET /api/governance/audit-report`

返回审计日志字段完整性报告，检查关键动作是否具备 `event_id`、`actor`、`action`、`resource_type`、`resource_id`、`source` 和 `timestamp`。可用 `action_prefix` 过滤。

#### `GET /api/governance/data-security-report`

扫描已入湖 document、evidence 和 research answer 中的邮箱、手机号、身份证样式和 secret/API key 字面量，返回脱敏 snippet、按类型/来源/严重级别聚合的统计，并用于 `sensitive_findings` 默认告警。可用 `resource_type`、`finding_type`、`issuer_id`、`source_id`、`scan_char_limit`、`limit` 过滤。越权 API 访问会被拦截并以 `permission_denied` 审计事件留痕，默认告警 `alert_permission_denied_events` 使用 `permission_denied_events` 指标触发。

#### `GET|POST /api/governance/security-readiness-report`

输出安全、密钥和权限生产验收报告。报告汇总 source governance、audit completeness、data security scan、permission matrix、permission denied 审计或已通过的 `permission_red_team_test` readiness 记录、secret rotation metadata、最小权限存储/搜索/数据库模板、cache retention 外部删除证据和红区训练记录。接口会拒绝 `secret_value`、`api_key`、`token`、`password`、`private_key` 等敏感字段，只记录 metadata 与 evidence URI；`permission_red_team_evidence=true` 这类布尔字段不会替代真实 403/audit 或 checklist 证据；不会在应用内执行对象存储或搜索索引物理删除。返回 `ready_for_security_production`、`gates`、`missing_requirements`、`artifact_uris`、`external_controls` 和各项汇总；传 `record_readiness=true` 时写审计事件 `security_readiness_report`。

请求字段：

- `secret_manager_provider`
- `api_key_scope`
- `delete_executor`
- `permission_red_team_evidence`
- `artifact_uris`
- `storage_policy`
- `record_readiness`

#### `GET /api/governance/permission-matrix`

返回 API 网关授权规则派生的角色 + 数据域 + 动作级权限矩阵。每条规则包含 `rule_id`、`method`、`action`、`data_domains`、`path_prefixes`、`sample_path`、`allowed_roles`、`denied_roles`、`public` 和 `sensitivity`；`role_matrix` 展开到单个角色/数据域/动作决策，`summary_by_role` 汇总 allowed/denied/red domain 数量。支持 `role`、`data_domain`、`action`、`method`、`include_role_matrix` 过滤，用于权限红队、UI 权限态和最小权限复核。

#### `POST /api/governance/permission-matrix`

同 `GET /api/governance/permission-matrix`，用于复杂过滤 payload。

#### `GET /api/governance/storage-policy-templates`

返回生产对象存储、检索和状态库的最小权限/生命周期模板。输出包含 `s3_iam_policy`、`s3_lifecycle_policy`、`opensearch_role`、`postgres_grants` 和 `ddl_rollback_approval`，并给出 scoped prefix、禁止 app role 删除对象、禁止 S3 full access、PostgreSQL app role 不授予 DROP 等检查项。支持 `environment`、`bucket`、`prefix`、`opensearch_index`、`postgres_schema`、`app_role`、`migration_role`、`transition_after_days`、`archive_after_days`、`delete_after_days`。

#### `POST /api/governance/storage-policy-templates`

同 `GET /api/governance/storage-policy-templates`，用于复杂过滤 payload。

#### `GET|POST /api/governance/storage-readiness-report`

输出 PostgreSQL/S3/OpenSearch 生产验收报告，汇总非本机 runtime 配置存在性、最小权限模板、PostgreSQL migration artifact URI、真实数据 smoke、容量/延迟 baseline、备份恢复 drill、PostgreSQL connect/query smoke artifact URI、S3 put/get/checksum smoke artifact URI 和 OpenSearch bulk/search smoke artifact URI。接口只生成证据 manifest，不执行压测、不连接外部对象存储或搜索集群；内联 migration/smoke payload 只作为指标摘要，不能替代外部 artifact URI；本机路径、`file://`、`local://`、服务连接串和只有域名的 HTTP(S) 服务根地址不会被视为生产归档证据；拒绝 secret/token/password/private_key 等敏感字段，响应只返回 redacted endpoint 和 evidence URI。传 `record_readiness=true` 时写审计事件 `storage_readiness_report`。

请求字段：

- `postgres_configured`
- `s3_configured`
- `opensearch_configured`
- `runtime`
- `migration`
- `s3_smoke`
- `opensearch_smoke`
- `artifact_uris`
- `record_readiness`

#### `GET /api/governance/secret-rotations`

查询密钥轮换 metadata 台账。只记录 secret 名称、外部密钥管理系统/provider、owner、轮换状态、证据 URI、轮换时间和下次到期时间，不保存任何密钥值。返回 overdue / due_soon 聚合，并驱动默认告警 `alert_secret_rotation_overdue`。

#### `POST /api/governance/secret-rotations`

写入密钥轮换记录。请求中如包含 `secret_value`、`api_key`、`token`、`password`、`private_key` 等真实密钥字段会被拒绝。

请求字段：

- `rotation_id`
- `secret_name`
- `provider`
- `owner`
- `status`
- `rotated_at`
- `next_rotation_due_at`
- `evidence_uri`
- `notes`

#### `GET /api/governance/cache-retention-report`

返回公开来源、本地研报和 PaddleOCR 运行时缓存的保留期/删除策略 dry-run 报告。每条记录包含 resource type/id、source、risk level、retention policy、cache TTL、cached/expires 时间、action、deletion_required、manual_approval_required 和 source governance gaps。支持 `as_of`、`source_id`、`source_type`、`risk_level`、`resource_type`、`action`、`include_retained`、`include_runtime_cache`、`due_within_days`、`limit` 过滤。

#### `POST /api/governance/cache-retention-report`

同 `GET /api/governance/cache-retention-report`，并支持 `record_run=true` 写入 `CacheRetentionRunRecord` 和 `record_cache_retention_run` 审计事件。`execute=true` 只把需要外部生命周期/KMS/DLP 执行的记录标为 `approval_required`，不会在应用内物理删除文档、研报或运行时缓存；响应中的 `usage_boundary` 固定说明该记录是治理证据而非删除动作本身。

#### `GET /api/governance/cache-retention-runs`

查询缓存保留/删除策略执行记录，支持 `status`、`actor`、`execute_requested`、`limit` 过滤，并返回 `approval_required` 与 `executed_outside_app` 聚合计数。

#### `POST /api/governance/cache-retention-runs/{run_id}/execute`

执行已记录的缓存保留 run。默认 `execute=false` 只返回待执行任务清单；`execute=true` 仅对 `document_parse_cache` 运行时缓存执行本进程清理，并把 document / research report / search index 删除列为 `external_handoff`，等待对象存储生命周期、OpenSearch/Qdrant 清理或 DLP/KMS 工具回填证据。响应包含 `runtime_deleted_count`、`external_handoff_count`、`tasks` 和 usage boundary；不会删除对象存储文件或研报资产。

#### `POST /api/governance/cache-retention-runs/{run_id}/execution-evidence`

回填外部对象存储生命周期、搜索索引清理、KMS/DLP 或运行时缓存清理 executor 的执行证据。请求需要 `evidence_uri`，可选 `provider`、`deleted_count`、`executed_at`、`notes`。接口只把 run 状态更新为 `executed_outside_app` 并写 `record_cache_retention_execution_evidence` 审计事件，不在应用内执行物理删除。

#### `POST /api/connectors/astock/seed`

写入 A 股补充接口候选注册表，只包括当前生产闭环计划内的免费/公开补充接口：东财研报发现、巨潮公告补充、腾讯估值快照、同花顺热点、百度概念/资金流、龙虎榜和解禁日历。默认不登记需要额外 key、商业授权或边界不清的接口。所有候选默认 restricted rights，不进入事实真相层或训练层。

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

#### `GET|POST /api/connectors/astock/verification-readiness`

输出 A 股补充 connector 真实验证验收包，不把第三方数据升级为事实真相层。可传 `connector_id` / `connector_ids`、`sample_rows`、`artifact_uris` 和 `record_readiness=true`。报告按 connector 检查 verification status、字段样本覆盖、rate limit 声明、allowed use、license/TOS 边界、真实 endpoint 可用性 artifact URI、endpoint 稳定性 artifact URI、调用限制/配额验证 artifact URI、license review URI 和 field sample URI；本地 `sample_rows` 只用于字段覆盖检查，不能替代外部 field sample artifact。返回每个 connector 的 `gates`、`missing_requirements`、`automation_blockers` 和 `ready_for_real_connector_acceptance`，总览返回 `ready_for_real_acceptance`。接口固定 `automation_allowed=false`、`live_execution_allowed=false`。

#### `POST /api/connectors/astock/fetch`

对 A 股补充 connector 的本地样本行执行字段归一化、source URI 脱敏和权限边界评估。当前入口用于公开接口接入前的可重复样本验证；默认只返回 `manual_reference_or_supplemental_research_only` 结果，不写入事实真相层。`blocked` connector 或红区来源会被合规闸门拦截。

请求字段：

- `connector_id`
- `sample_rows`
- `limit`

#### `GET /api/connectors/astock`

按 `provider`、`status`、`requires_key`、`limit` 查询 A 股补充接口注册表。

#### `POST /api/connectors/astock/supplemental/fetch`

（T-416）从已注册的 A 股补充 HTTP connector（东财研报、巨潮公告、腾讯估值、同花顺热点、百度概念、龙虎榜、解禁日历）拉取公开接口样本数据。所有结果固定为 `manual_reference_or_supplemental_research_only`，不进入事实真相层或自动化链路。`blocked` connector 或红区来源会被合规闸门拦截。空 `symbols` 列表时接口返回空数组（无 HTTP 调用）。

请求字段：

- `connector_id`：必填；已注册 connector ID（`eastmoney_research`、`cninfo_announcements`、`tencent_valuation_snapshot`、`ths_hot_topics`、`baidu_concepts`、`dragon_tiger_list`、`unlock_calendar` 等）
- `symbols`：可选；标的代码列表，支持 `sh600000`、`000001.SZ`、`600000.SS` 等多种格式
- `limit`：可选；最大返回条数，默认 10
- `user_agent`：可选；HTTP 请求 User-Agent

返回字段：

- `connector_id`
- `connector_type`
- `source_id`
- `documents`：归一化文档列表，每条含 `document_type`、`source_id`、`metadata.automation_allowed=false`、`metadata.source_boundary`
- `sample_count`
- `usage_boundary`：固定 `manual_reference_or_supplemental_research_only`

#### `POST /api/document-parsing/paddleocr`

调用配置的 PaddleOCR-VL 文档解析备用接口。请求必须配置 `AI_QUANT_PADDLEOCR_TOKEN`；服务端只记录 provider、job id、模型、缓存命中、耗时和估算成本审计，不记录 token。结果按文档/URL、content hash/source URI、模型和 optional payload 缓存在运行时内存中，可用 `use_cache=false` 强制重跑。传 `retry_attempts` / `retry_limit` 可对临时解析失败执行最多 3 次额外重试，成功响应会返回 `attempt_count`、`retry_attempts` 和 `retry_errors`；证据抽取的 OCR fallback 默认会做一次自动重试后才进入人工复核。

请求字段：

- `document_id` 可选；解析已入湖文档的 `object_uri`，如无本地对象且 `source_uri` 是 HTTP(S)，则提交 URL
- `file_url` 可选；直接提交远程文件 URL
- `optional_payload` 可选；覆盖 PaddleOCR 可选参数，例如 `useChartRecognition`
- `use_cache` 可选；默认 `true`
- `retry_attempts` 可选
- `retry_limit` 可选

返回字段：

- `provider`
- `model`
- `job_id`
- `state`
- `result_url`
- `page_count`
- `pages`
- `text`
- `cache_hit`
- `elapsed_ms`
- `estimated_cost`

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

从项目内本地通达信 `vipdoc/*.day` 文件只读预览行情，不写入状态库。`vipdoc` 默认路径由 `AI_QUANT_TDX_VIPDOC_PATH` 指定，本机默认使用 `data/local/tdx/vipdoc`。`.day` 文件按通达信官方日线二进制格式读取，symbol 会兼容 `sh600000`、`600000.SH`、`600000.XSHG` 等格式。

请求字段：

- `source_format`：`vipdoc`
- `symbols`
- `start_date`
- `end_date`
- `limit`
- `include_summary`

#### `POST /api/market-data/tdx/import`

从项目内本地通达信 `vipdoc/*.day` 文件读取行情，并写入公开/已提供 EOD/延时行情层。导入时会复用 `/api/market-data/points` 的 source rights、security、market 和 data_type 校验；symbol 格式兼容口径同 preview。

请求字段：

- `source_format`：`vipdoc`
- `symbols`
- `security_map`
- `start_date`
- `end_date`
- `limit`
- `source_id`
- `data_type`
- `skip_existing`

#### `POST /api/market-data/backfill`

统一补齐 A 股和美股 EOD/延时 K 线。A 股默认使用本地 TDX vipdoc 作为历史主源，并用 Baostock 补最近缺口；美股默认使用 `yahoo_chart_us_eod`。接口支持全市场发现、逐证券 `latest_as_of_date + 1` 增量、分片、dry-run 和幂等跳过；只写公开/候选 EOD 数据，不接入实时行情或交易链路，固定 `automation_allowed=false`、`live_execution_allowed=false`。

请求字段：

- `market`：`A`、`U` 或 `both`
- `symbols`
- `discover_universe`
- `start_date`
- `end_date`
- `fallback_window_days`
- `offset`
- `max_symbols`
- `dry_run`
- `skip_existing`
- `refresh_existing`

#### `GET|POST /api/market-data/backfill/coverage-report`

检查 A/U 已入库 K 线覆盖情况，返回各市场证券数、已覆盖数、最新行情日期、缺失样本、滞后样本和 source governance 缺口。该接口不导入行情。

请求字段：

- `market`
- `as_of_date`
- `data_type`
- `stale_after_days`
- `limit`

#### `GET|POST /api/market-data/schema-coverage-report`

只读检查本地 TDX `vipdoc/*.day` 文件是否能映射到公开 EOD 自动化字段边界。报告按通达信官方日线二进制格式识别 `date/open/high/low/close/amount/volume`，并映射到目标字段 `security_id/as_of_date/open/high/low/close/adjusted_close/volume`。接口不导入行情，只输出 `schema_recognition_coverage`、`target_field_coverage`、`anomaly_samples`、source whitelist 缺口和 `automation_ready`，用于 T-403 生产输入 schema 覆盖验收。

请求字段：

- `source_format`：当前支持 `vipdoc`
- `source_id`
- `schema_samples`
- `sample_limit`

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

写入 A/H/U 主体映射。可显式传入 `confidence`、`source`、`version`；如未传 confidence，系统会基于 LEI/CIK/FIGI/ISIN/ticker/market 标识符完整度给出可解释默认置信度。支持双时间轴字段 `valid_from`、`valid_to`、`recorded_at`、`supersedes_mapping_id` 和 `status`；当传入 `supersedes_mapping_id` 时，旧映射会在新版本 `valid_from` 处关闭并标记为 `superseded`。

#### `GET /api/entity-mappings`

查询 A/H/U 主体映射版本。支持 `issuer_id`、`ticker`、`market`、`status`、`valid_at`、`recorded_at`、`limit`；`valid_at` 表示映射业务生效时点，`recorded_at` 表示系统在该记录时间点已经知道的映射版本。

#### `POST /api/entity-mappings/batch`

批量写入 A/H/U 主体映射，逐条返回创建结果和错误。

#### `POST /api/entity-mappings/labels`

批量写入主体映射人工金标，用于上线闸门的 `entity_mapping_accuracy`。每条标签包含 `mapping_id`、期望 `issuer_id`、`ticker`、`market`、`reviewer`、`source` 和 `notes`；逐条返回创建结果和错误，并进入审计日志。

#### `GET /api/entity-mappings/labels`

按 `issuer_id`、`mapping_id`、`limit` 查询已登记人工金标。

#### `GET /api/entity-mappings/quality-report`

根据人工标签样本计算主体映射覆盖率、市场分布、准确率、不匹配样例、平均消歧置信度、低置信映射清单、双时间轴版本覆盖率和版本重叠清单。支持 `issuer_id`、`valid_at`、`recorded_at`、`labels`、`low_confidence_threshold`、`limit`；未传 `labels` 时使用已通过 `/api/entity-mappings/labels` 登记的持久化金标。

#### `GET|POST /api/entity-mappings/readiness-report`

汇总 A/H/U 主体映射和主体页图谱生产化验收。报告复用 entity mapping quality report、图谱 traceability、edge metadata quality、Neo4j payload export 和 Qdrant payload export，输出 `ready_for_entity_graph_production`、`missing_requirements`、`gates`、`quality_report`、`market_summary`、`label_summary`、`graph_traceability`、`edge_quality`、`graph_export`、`vector_export`、`adapters` 和 `artifact_uris`。默认 gate 要求 A/H/U 三市场覆盖、人工金标准确率 >= 98%、双时间轴版本覆盖率 100%、无低置信/时间重叠/金标 mismatch、观点/决策/问答到证据回溯率 >= 95%、边 source/timestamp/version/confidence 覆盖率 100%、Neo4j/Qdrant 非本地 endpoint 以及真实批量映射、ADR/中概队列、金标、主体页验收、图谱 adapter、向量 adapter artifact URI。支持 `min_accuracy`、`min_traceability_rate`、`required_markets`、`min_mapping_count`、`min_label_count`、`min_traceable_resource_count`、`neo4j_endpoint`、`qdrant_endpoint`、`artifact_uris` 和 `record_readiness`；固定 `automation_allowed=false`、`live_execution_allowed=false`，不会调用生产图数据库或向量库。

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

#### `POST /api/13f/filings/parse`

解析 SEC Form 13F information table XML，可直接提交 `information_table_xml` / `body`，也可通过 `document_id` 或 `source_uri` 拉取 SEC 附件正文。解析字段包括 `nameOfIssuer`、`titleOfClass`、`cusip`、`figi`、`value`（按 SEC 13F 千美元单位换算为 `value_usd`）、`sshPrnamt`、`sshPrnamtType`、`investmentDiscretion` 和 `votingAuthority`。设置 `import_holdings=true` 后，仅导入能通过 `security_mappings`、既有 EntityMapping 或 Security ISIN/FIGI 映射到本地 `issuer_id`/`security_id` 的记录；未映射行进入 `unmapped` 队列。接口固定返回 `automation_allowed=false`、`live_execution_allowed=false`，13F 只用于候选池、拥挤度和反身性风控。

请求字段：

- `information_table_xml` / `xml` / `body`
- `document_id`
- `source_uri`
- `filer_cik`
- `filer_name`
- `report_period`
- `import_holdings`
- `security_mappings`
- `create_missing_mappings`
- `user_agent`

#### `POST /api/13f/filings/batch-parse`

批量解析 13F information table。请求字段包括 `batch_id`、`filings`、`limit`，以及单文件解析支持的默认字段；每个 filing 可覆盖 `information_table_xml`、`document_id`、`source_uri`、`filer_cik`、`filer_name`、`report_period` 和 `security_mappings`。返回 `row_count`、`created_count`、`unmapped_count`、`mapping_counts`、`mapping_rate`、逐 filing 结果和错误列表，用于 13F 大样本跑批与 CUSIP/FIGI/issuer 映射验收。接口固定 `automation_allowed=false`、`live_execution_allowed=false`。

#### `GET|POST /api/13f/filings/mapping-readiness`

输出 13F 大样本映射验收包报告，不替代真实 Form 13F 跑批。接口可接收 `batch_result`（来自 `/api/13f/filings/batch-parse`）或直接传 `filing_count`、`row_count`、`unmapped_count`、`failed_count`、`mapping_rate`、`mapping_counts`。默认 gate 为 `target_filing_count=100`、`target_row_count=1000`、`min_mapping_rate=0.98`、`max_failed_rate=0`，并要求 `artifact_uris.batch_artifact_uri`、`mapping_gold_uri` 和 `unmapped_review_queue_uri`；即使未映射队列为空，也要提供已复核空队列 artifact。返回 `gates`、`missing_requirements`、`ready_for_real_acceptance`，固定 `automation_allowed=false`、`live_execution_allowed=false`。

#### `GET /api/13f/holdings`

按主体、证券或报告期查询 13F 持仓记录。

请求字段：

- `issuer_id`
- `security_id`
- `report_period`
- `limit`

#### `GET /api/13f/holdings/changes`

按 filer/issuer/security 计算 13F 持仓变化时间序列，返回新建、增持、减持、清仓和不变记录，以及 shares/value 的绝对和百分比变化。可用 `issuer_id`、`security_id`、`filer_cik`、`report_period`、`include_new`、`min_abs_value_delta`、`limit` 过滤。

#### `GET /api/13f/candidate-pool`

基于最新或指定报告期的 13F 持仓生成研究候选池和风控展示。按 issuer/security 聚合持仓价值、filer 数、净增减持、crowding score、FIGI/ISIN/ticker 映射和映射置信度，并输出 `candidate_score`、`score_components` 与 `risk_tags`。该接口固定 `automation_allowed=false`，只用于中低频研究候选和拥挤度风险，不生成交易信号。支持 `issuer_id`、`security_id`、`report_period`、`min_value_usd`、`max_crowding_score`、`limit`。

#### `POST /api/13f/crowding/update`

根据指定主体和报告期的 13F 持仓生成 `CrowdingSnapshot`。

请求字段：

- `issuer_id`
- `report_period`
- `snapshot_id`

#### `POST /api/disclosure-events/classify`

从 8-K、6-K、20-F 等披露文件生成事件标签、SEC item code/title、严重性、摘要和证据链接。8-K 支持常见 Item 1.01、2.02、2.05、5.02、7.01、8.01 的规则识别。

请求字段：

- `document_id`
- `event_id`
- `event_type`
- `item_code`
- `item_title`
- `severity`

#### `POST /api/disclosure-events`

手工登记披露事件。

#### `GET /api/disclosure-events`

按 `event_id`、`issuer_id`、`security_id`、`event_type`、`severity` 查询披露事件墙。已回写的 `post_event_performance` 会随事件返回。

#### `GET /api/disclosure-events/performance`

按事件和公开 EOD 行情计算披露后的后验表现，不写回事件记录。支持 `event_id` / `event_ids`、`issuer_id`、`security_id`、`event_type`、`severity`、`windows`、`benchmark_security_id`、`source_id`、`data_type`、`adjustment_mode`、`price_field` 和 `limit`。默认窗口为 1/5/20 天，默认来源为 `public_eod_market_data`。

#### `POST /api/disclosure-events/performance`

同上，但会把事件窗口收益、基准收益、超额收益、缺失行情问题、计算参数和 `computed_at` 回写到 `DisclosureEvent.post_event_performance`，用于事件墙、图谱和后续复盘。

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

从文档生成证据切片。若当前规则/PDF 文本流解析器无法得到文本，且 `AI_QUANT_PADDLEOCR_TOKEN` 已配置，会先调用 PaddleOCR-VL 备用解析并把 markdown 结果切成 evidence；备用解析未配置、失败或仍无文本时，会创建 `ManualReviewItem` 并返回 `422`。返回的 evidence 继续保留旧版 `bbox="page=...;chunk=..."` 字符串，同时新增 `locator` 结构：规则文本为 `page_chunk_v1`，OCR 版面结果为 `ocr_bbox_span_v1`，包含 page/chunk、span hash、真实 bbox、表格 cell bbox、图片/表格资产引用和 `legacy_bbox`。

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

返回 evidence 定位覆盖率、平均置信度、人工复核数量和解析失败率。报告同时输出 `structured_locator_coverage`、`bbox_coverage`、`table_cell_count`、`table_cell_bbox_coverage` 和 `asset_reference_count`，用于区分普通 page/chunk locator 与 OCR 真实 bbox/table cell 定位。传入 `bbox_gold_labels` 时会按 IoU 校验 OCR bbox 与人工金标，输出 `bbox_gold_validation.label_count`、`bbox_hit_rate`、`average_iou` 和失败样本，供真实扫描件大样本版面定位验收。

请求字段：

- `issuer_id`
- `bbox_gold_labels`
- `min_bbox_iou`

#### `POST /api/benchmarks`

登记抽取/定位/表格 benchmark 配置与阈值。

#### `POST /api/benchmarks/{benchmark_id}/samples`

登记中英文金标样本，字段包括 `document_id`、`language`、`expected_terms`、`expected_numbers`、`expected_periods`、`expected_tables`、`expected_pages`。

#### `GET /api/benchmarks/{benchmark_id}/samples`

按 `language`、`status` 查询 benchmark 样本集。

#### `POST /api/benchmarks/{benchmark_id}/run`

运行 benchmark suite。系统复用真实 evidence extraction 与结构化抽取规则，输出 `term_f1`、`number_recall`、`period_recall`、`table_recall`、`page_hit_rate`、`evidence_locator_rate`、`avg_confidence`、按语言拆分指标、失败样本和回归样例；低置信度样本会进入失败报告。

#### `GET|POST /api/benchmarks/{benchmark_id}/readiness-report`

输出真实大样本 benchmark 验收包报告，不替代 300-500 份真实样本执行。接口会检查 active sample 数、中文/英文样本覆盖、最近 benchmark run 指标、样本 manifest URI、中文样本集 URI、英文 SEC 样本集 URI、人工标注手册 URI、OCR/bbox gold label URI、表格 cell gold label URI、摘要质量样本 URI 和 regression baseline artifact URI。默认目标 `target_sample_size=300`、中英文各 `150`；可传 `artifact_uris`、`bbox_gold_labels`、`table_cell_gold_labels`、`summary_samples` 和 `record_readiness=true`；内联 gold/summary payload 只用于计数摘要，不能替代外部 artifact URI。返回 `gates`、`missing_requirements`、`ready_for_real_acceptance`、`external_artifact_required=true` 和固定 `automation_allowed=false`。

#### `POST /api/benchmarks/{benchmark_id}/evaluate`

对外部传入的聚合指标按 benchmark 阈值做一次轻量评估。

#### `POST /api/extractions/run`

对单条 evidence 运行规则基线抽取，生成术语、数值、期间、规则表格和定位指标；如传入 `benchmark_id`，会按阈值计算通过状态。传 `include_adjacent_tables=true` 时，会扫描同一文档相邻 evidence 的表格，并把同 header / 同列签名的跨页表格合并为一个 table，返回 `page_numbers`、`merged_from_table_count`、`merge_strategy` 和 cell 级 `source_page_no` / `source_row`，用于跨页表格回溯。

请求字段：

- `evidence_id`
- `benchmark_id`
- `expected_terms`
- `expected_numbers`
- `expected_periods`
- `expected_tables`
- `include_adjacent_tables`
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

#### `GET /api/research-reports/governance-report`

输出本地研报治理报告，用于“研报只能作为外部观点/本地参考”的边界控制。报告按 broker/source 统计集中度，按研报年月和 `as_of` 判断过期，按已登记 Document 回链 issuer/security，并返回 `stale_research_report`、`missing_document_link`、`single_broker_concentration_breach`、`single_source_concentration_breach` 等问题。支持 `issuer_id`、`security_id`、`broker`、`source_id`、`status`、`as_of`、`stale_after_days`、`max_single_source_share`、`limit`。

#### `GET /api/research-reports/mapping-report`

输出本地研报到公司、证券、行业和披露事件的映射报告。映射来自研报 ingest payload 中的 `issuer_id`、`security_id`、`industry`、`event_ids`，并可按同一 issuer/security 查找候选披露事件。报告固定返回 `automation_allowed=false` 和本地参考用途边界，研报不会升级为事实真相源或训练数据。支持 `issuer_id`、`security_id`、`broker`、`source_id`、`industry`、`event_id`、`status`、`include_candidate_events`、`limit`。

#### `GET /api/research-reports/viewpoint-report`

输出本地研报观点对比和偏见提示。报告按 issuer/security/broker/topic 过滤，基于题名、文件名和已登记 Document 文本里的主题词与情绪词，汇总同主题 broker 分布、情绪分布、单一 broker 占比，并返回 `single_broker_viewpoint`、`broker_concentration_bias`、`missing_negative_counterview`、`missing_positive_counterview` 等告警。报告固定 `automation_allowed=false`，只作为本地参考观点层。

#### `POST /api/research-reports/structure`

把已扫描的本地研报资产批量结构化为 `ResearchReport`、`ReportViewpoint`、`ReportForecast` 和 `AnalystProfile`。该接口复用研报题名、路径分类、已登记 `Document` 文本和 `research_report_citation` evidence，提取报告类型、评级、目标价、当前价、核心假设、盈利预测、估值方法、催化剂、风险和分析师；重复执行默认跳过已结构化研报，传 `force=true` 可重建同一研报的确定性子对象。`dry_run=true` 只返回计划，不写入。

请求字段：

- `report_ids` / `report_id`：可选；指定研报资产 ID
- `issuer_id` / `security_id`：可选；只处理已映射到该主体或证券的研报
- `broker` / `source_id` / `status` / `q`：可选过滤
- `limit`：默认 50，最大 1000
- `execute`：默认 `true`；`dry_run=true` 时强制不写入
- `dry_run`：默认 `false`
- `force`：默认 `false`

返回字段：

- `structured_count`、`viewpoint_count`、`forecast_count`、`analyst_count`
- `skipped_count`、`metadata_only_count`
- `reports[]`：每份研报的结构化分类、观点 ID、预测 ID 和用途边界
- `usage_boundary`：固定 `research_reports_are_viewpoint_signal_only_not_fact_source_or_training_data`

#### `GET /api/research-reports/extraction-queue`

返回本地研报文本抽取/OCR 队列 dry-run。每个条目包含 `report_id`、`document_id`、broker/source、文件类型、当前状态、`action`、`reason`、`parser_version` 和使用边界；动作包括 `ingest_first`、`ready_text_extract`、`ocr_required`、`skip_already_indexed`、`repair_document_link`。响应带 `cache_policy`，固定 raw text 和 citation index 的保留期口径。支持 `broker`、`source_id`、`status`、`file_type`、`force`、`limit`、`citation_char_limit`、`parser_version`、`raw_text_cache_ttl_days`、`citation_index_ttl_days`。

#### `POST /api/research-reports/extraction-queue`

同 `GET /api/research-reports/extraction-queue`；当 `execute=true` 时会批量调用单份抽取逻辑。可抽取文本会生成 citation evidence；无文本 PDF/扫描件会批量创建 `research_report_text_extraction_required` 人工复核项。

#### `POST /api/research-reports/incremental-schedule`

（T-417）为本地研报资产库大目录生成增量 OCR/抽取调度计划，解决 22G/11742 文件的批量 OCR 成本控制问题。接口比较文件 fingerprint，只处理新增或变更文件；固定为 `local_reference_only` 边界，不可进入训练层或事实真相层。`dry_run=true` 只生成计划，不会落库；`execute=true` 会在首批执行前为未入库的研报登记本地参考 `Document`，再执行文本抽取和 citation 索引。

本机长期运行的安全入口是 `scripts/research_report_inbox_ingest.py`。该脚本默认把宿主机 inbox 设为 `/home/xionglei/文档/6大投行研报汇总/inbox`，并让 API 扫描容器内 `/data/local/research_reports/inbox`，不会登录、订阅或下载外部研报。默认 dry-run 输出计划，传 `--execute` 后才登记并执行首批解析，产物写入 `artifacts/research-report-inbox-ingest.json`。

请求字段：

- `root_path`：必填；本地研报根目录，或由 `AI_QUANT_RESEARCH_REPORT_ROOT` 配置
- `dry_run`：默认 `true`；为 `true` 时只输出 `schedule_plan`，不执行任何提取
- `execute`：默认 `false`；`dry_run=true` 时强制为 `false`；为 `true` 时执行首批（`batch_size` 内）
- `batch_size`：每批最大文件数，默认 50，最大 500
- `ocr_budget_mb`：单次调度 OCR 文件体积上限（MB），默认 200；超出预算的文件进入 `deferred` 队列
- `scan_limit`：最大扫描文件数，默认 5000，最大 20000
- `broker`：可选；只处理指定 broker 下的研报
- `year`：可选；只处理指定年份
- `extensions`：文件扩展名过滤，默认 `[".pdf"]`
- `citation_char_limit`：引用片段长度上限，默认 1200

返回字段：

- `dry_run`、`execute`
- `total_scanned`、`new_count`、`changed_count`、`skipped_count`
- `ocr_budget_mb`、`ocr_budget_used_mb`、`deferred_count`
- `batch_count`、`schedule_plan`：每批含 `batch_index`、`report_ids`、`brokers`、`estimated_size_mb`、`trigger_suggestion`
- `candidates`：所有候选文件明细
- `executed_results`：`execute=true` 时首批执行结果
- `usage_boundary`：固定 `local_reference_only_not_training_or_fact_source`
- `airflow_dagster_trigger_suggestion`：外部调度器接入建议


将单份研报按需登记为 `Document`，保留本地 `object_uri` 和 restricted rights tag，供 OCR、证据抽取和人工引用使用。

请求字段：

- `issuer_id`
- `security_id`
- `document_id`
- `industry`
- `event_ids`
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

#### `GET|POST /api/research/citation-boundary/readiness-report`

汇总公开电话会/转录稿和研报线索引用策略的生产验收。报告检查 `company_public_webcast`、`manual_reference_transcripts`、`local_research_reports` 三类 canonical source 是否已登记并完成来源复核，非公开/边界不清 transcript 是否 metadata-only 且有 `manual_reference_boundary_review`，本地研报治理是否保持 local-reference-only，研究问答是否保留英文 evidence/document 链接、人工审核和受限来源引用长度上限，红区/手工来源是否没有正文进入训练或自动事实路径，并要求 citation policy、source review、manual reference review 和研报治理 artifact URI。即使当前无手工参考或本地研报资产，也要提供 reviewed-empty artifact URI。返回 `ready_for_citation_boundary_production`、`missing_requirements`、`gates`、`source_summary`、`manual_reference_summary`、`research_report_governance`、`research_viewpoints`、`research_answers`、`artifact_uris`；固定 `automation_allowed=false`、`live_execution_allowed=false`。

#### `POST /api/research/answers`

创建英文 evidence 优先的研究问答与中文摘要审计记录。接口会保留英文原文 evidence、标准化 `citations`（evidence/document/page/bbox/source URI/quote/format）、中文摘要、summary 版本、prompt 版本、模型版本、来源公开性和人工覆核状态，并写入审计日志。对非公开或本地参考来源，`english_source_text` 会按 `citation_char_limit` 截断并标记 `citation_truncated`，避免长片段外泄。

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

#### `POST /api/research/answers/filing-qa`

从单个 filing 文档直接生成原文优先的研究问答工作台结果。接口会按 `document_id` 自动抽取英文 evidence、生成/回退 `ResearchAnswer`、返回英文原文、中文摘要、证据表、质量报告和摘要 benchmark，并固定 `automation_allowed=false`、`live_execution_allowed=false`。适用于交互式 filing QA 场景，原文证据必须可回链到 document 与 evidence。

请求字段：

- `answer_id`
- `document_id`
- `question`
- `evidence_limit`
- `refresh_evidence`
- `run_model`
- `summary_version`
- `prompt_version`
- `model_version`
- `human_review_status`
- `citation_char_limit`

#### `GET /api/research/answers/{answer_id}`

返回研究问答与摘要审计记录。

#### `GET /api/research/answers/quality-report`

返回答案级质量和人工复核队列报告，检查 evidence/document 回链、英文原文保留、受限来源引用截断、人工复核状态、summary/prompt/model 版本，并输出 `source_link_rate`、`review_coverage`、`pending_review` 和逐答案 `issues`。可用 `issuer_id`、`human_review_status`、`limit` 过滤；默认告警 `alert_research_answer_pending_review` 使用 `research_answer_pending_reviews` 指标触发。

#### `GET /api/research/answers/summary-benchmark`

返回研究答案中文摘要质量 benchmark。规则基线会检查 evidence/document 回链、英文原文保留、中文摘要长度、summary/prompt/model 版本、受限来源引用边界、人工复核状态、过度确定性措辞和英文 anchor term 覆盖率，输出 `score`、`passed`、`blocking_issues`、`warnings`、`pass_rate`、`average_score` 和逐答案明细。支持 `issuer_id`、`answer_id`、`human_review_status`、`min_score`、`min_summary_chars`、`max_summary_chars`、`min_anchor_coverage`、`require_review`、`limit` 过滤。

#### `POST /api/research/answers/summary-benchmark`

同 `GET /api/research/answers/summary-benchmark`，用于复杂过滤 payload。

#### `GET|POST /api/research/answers/readiness-report`

汇总英文原文优先研究问答和中文摘要审计的生产验收。报告复用 answer quality report、summary benchmark 和 graph traceability，检查研究答案数量、英文 evidence/document 回链率、人工审核覆盖率、pending review、摘要通过率、平均分、英文原文保留、中文摘要存在但不替代原文、summary/prompt/model 版本元数据、过度确定性措辞、英文 anchor 覆盖率和 research answer 图谱回溯率，并要求真实模型质量评估、fallback 对照和摘要审核 rubric artifact URI。支持 `issuer_id`、`answer_id`、`min_answer_count`、`min_summary_pass_rate`、`min_average_score`、`min_anchor_coverage`、`artifact_uris`、`record_readiness`；固定 `automation_allowed=false`、`live_execution_allowed=false`，不会在 readiness 报告中调用外部模型。

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

从已审批的投委会决策生成纸面执行意图，用于模拟持仓和后续反馈分析。未审批决策必须返回 `423`。该接口不创建真实订单，不连接券商，也不代表自动调仓。

请求字段：

- `decision_id`
- `security_id`
- `action`
- `target_weight`
- `rationale`

#### `GET /api/execution-intents/{intent_id}`

返回纸面执行意图。

#### `POST /api/execution-intents/{intent_id}/simulate`

对已审批纸面执行意图做模拟成交，并同步写入 `PortfolioTransaction` ledger，作为模拟持仓、月报绩效、归因和复盘反馈的输入。接口只接受 `mode=simulated`，拒绝 live/broker 模式；无 `fill_price` 时可使用 intent 标的在 `trade_date` 前最近公开 EOD 收盘价。返回 `SimulatedExecution`、对应模拟交易流水、更新后的 intent，以及 `live_execution_allowed=false`。

请求字段：

- `execution_id`
- `transaction_id`
- `mode`
- `trade_date`
- `quantity`
- `fill_price`
- `slippage_bps`
- `fees`
- `account_id`
- `strategy_id`

#### `GET /api/simulated-executions`

按 `intent_id`、`account_id`、`status` 查询模拟成交记录。该接口只暴露模拟成交，不代表真实券商订单。

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

#### `POST /api/operating-reports/{report_id}/board-pack`

导出已发布月报的 Board pack 制品，支持 `format=markdown` 或 `format=pdf`，写入对象存储并返回 `object_uri`、`sha256`、`size_bytes`、`content_type` 和源 markdown 内容。PDF 由 markdown 源内容生成，适合作为可哈希、可归档的董事会包附件。默认要求 `status=published`；如确需草稿预览，可显式传 `allow_draft=true`。导出动作会写入审计日志，不会生成纸面执行意图、模拟交易流水或绕过投委会审批。

请求字段：

- `format`
- `object_id`
- `include_content`
- `allow_draft`

#### `POST /api/operating-reports/{report_id}/red-flags/{red_flag_id}/resolve`

逐条关闭月报红灯项，写入处理结论、责任人、时间戳和审计事件。

#### `GET /api/operating-reports/red-flag-reminders`

查询月报红灯项 owner、due_date 和逾期状态。可用 `as_of_date`、`owner`、`status` 过滤，供提醒和经营看板使用。

#### `GET /api/operating-reports/{report_id}`

返回月度经营报告。

#### `GET /api/strategy-replays`

按 `decision_id`、`version`、`actual_outcome`、`created_from`、`created_to` 筛选策略回放。

#### `GET /api/strategy-replays/compare`

按 `decision_id`、`version` 或 `replay_ids` 对比多个策略回放批次，返回最新 replay、版本分布、实际结果分布、variance 数量、下一步动作桶和逐 replay 对比行。该报告只用于投后复盘和策略实验室 UI，不会生成交易意图。

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

生成纸面组合候选方案。当前实现为可解释的 Black-Litterman 原型：由市场权重和波动率得到均衡先验，由 research view 的 `confidence` 绑定 `Omega`，再应用禁投清单、单证券上限、市场预算、行业预算，输出候选权重、风险贡献、换手、约束影子价格、压力测试、walk-forward 诊断，以及基于 `return_history` 的样本协方差、相关矩阵和对角 shrinkage 协方差。该接口不会创建纸面执行意图，也不会产生真实交易指令；建议作为投资分析和模拟组合构建入口。

请求字段：

- `proposal_id`
- `securities`
- `views`
- `benchmark_id`
- `require_benchmark_passed_evidence`
- `risk_aversion`
- `tau`
- `constraints`
- `risk_budget`
- `return_history`
- `covariance_shrinkage`

当 `require_benchmark_passed_evidence=true` 时，每个 view 的 `evidence_ids` 必须已有通过的结构化抽取/benchmark 结果；否则返回合规闸门错误，避免未通过证据链直接进入组合候选权重。
- `stress_scenarios`
- `return_history`

#### `POST /api/portfolio/optimizer/compare`

对既有 PortfolioProposal 做纸面对照，输出候选权重、基线权重和可选外部求解器权重的比较结果、约束报告和诊断摘要。支持 `proposal_id`、`baseline_method`、`external_optimizer_weights` / `solver_weights`、`external_optimizer_name`，固定 `simulation_only=true`、`live_execution_allowed=false`、`automation_allowed=false`。

外部对照入口：传 `run_external_optimizer=true` 且 `external_optimizer_name=cvxpy` 或 `pypfopt` 时，服务会尝试调用本机安装的 CVXPY / PyPortfolioOpt 做纸面求解器对照；未安装依赖或求解失败时不会伪造外部结果，而是在 `external_optimizer.status=unavailable|failed`、`diagnostics.reason/error` 和 `paper_compare_continues=true` 中明确说明，候选组合与本地 baseline 对照继续返回。生产环境需要安装依赖并归档求解器版本、参数和对照结果 artifact。

#### `GET|POST /api/portfolio/optimizer/readiness-report`

输出外部组合求解器对照归档验收包，不触发真实调仓。接口可接收 `/api/portfolio/optimizer/compare` 的 `compare_result`，或直接传 `external_optimizer`、`solver_version`、`solver_parameters` 和 `artifact_uris`。gate 检查 `proposal_id`、外部求解器状态（`solved` / `supplied`）、solver weights、版本、参数、solver artifact URI、comparison artifact URI、constraint report artifact URI、内联约束报告和 `paper_only` 边界。返回 `ready_for_production_comparison_archive`、`missing_requirements` 和 `gates`，固定 `simulation_only=true`、`automation_allowed=false`、`live_execution_allowed=false`。

#### `POST /api/portfolio/forward-report`

基于既有 PortfolioProposal 生成纸面前向跟踪报告。支持 `proposal_id`、`weights`、`benchmark_weights` 或 `benchmark_proposal_id`、`forward_start_date`、`forward_end_date`、`max_tracking_error`、`min_common_dates`、`max_drawdown_threshold`、`max_volatility` 和 `min_active_return`。输出组合收益、基准收益、active return、tracking error、information ratio、review flags 和收益覆盖度，固定 `simulation_only=true`、`live_execution_allowed=false`、`automation_allowed=false`。

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

基于公开/已提供行情做组合持仓估值。输入持仓股数和现金后，按 `as_of_date` 前最近行情价格计算市值、权重、现金权重和缺失价格清单，并返回 `risk_decomposition`，按 `market`、`currency`、`industry`、`style` 汇总市值/权重、外币权重、现金权重和集中度。`industry` / `style` 可通过 `groups[security_id]` 或 holdings 行内字段注入。该接口只用于研究、回测、估值和风险展示，不代表可交易价格。

请求字段：

- `as_of_date`
- `holdings`
- `cash`
- `currency`
- `groups`
- `source_id`
- `data_type`
- `price_field`

#### `POST /api/portfolio/transactions`

登记人工录入、模拟或回测交易流水，作为模拟持仓、月报绩效和归因的输入层。当前仅支持 long-only buy/sell，写入时校验证券、日期、数量、价格、费用和来源边界；模拟执行推荐通过 `/api/execution-intents/{intent_id}/simulate` 写入，避免绕过研究决策和审批链。该 ledger 不代表真实券商成交。

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

#### `POST /api/portfolio/transactions/import`

批量导入模拟或回测交易流水，兼容常见 backtest/fill 字段别名，不连接真实券商。支持 `security_id/symbol/ticker/code/ts_code/instrument`、`trade_date/date/datetime/timestamp/filled_at`、`side/action/direction/order_side`、`quantity/qty/shares/size/signed_qty/position_delta`、`price/fill_price/avg_price/execution_price`、`fees/commission/transaction_cost`、`account_id/account/portfolio_id/book` 和 `strategy_id/strategy/model/run_id`。无 `side` 但数量为负时会推断为 `sell`，数量取绝对值。默认 `source_id=simulated_trade_execution`，固定返回 `simulation_only=true`、`live_execution_allowed=false`。

请求字段：

- `rows`
- `items`
- `dry_run`
- `skip_existing`
- `source_id`
- `account_id`
- `strategy_id`
- `security_map`

#### `GET /api/portfolio/transactions`

按 `security_id`、`account_id`、`strategy_id` 查询交易流水。

#### `GET /api/portfolio/positions`

按交易流水派生 as-of 持仓，返回证券持仓股数、净成本、参与交易数和过滤条件。支持 `as_of_date`、`account_id`、`strategy_id`。

#### `GET /api/portfolio/proposals`

按 `status`、`created_by` 查询纸面组合候选方案。

#### `GET /api/portfolio/proposals/{proposal_id}`

返回纸面组合候选方案。

#### `POST /api/portfolio/attribution/backfill`

（T-408）对纸面/模拟组合执行绩效归因回填，将 market/currency/industry/style 分组收益归因写入对应 OperatingReport.annotations。接口固定为 `simulation_only=true`，不接真实交易账户。`dry_run=true` 时只计算归因，不写入任何报告。

请求字段：

- `holdings`：持仓列表，每条含 `security_id`、`weight`；或通过 `proposal_id` 引用已有 PortfolioProposal
- `proposal_id`：可选；优先于 `holdings`
- `start_date`：归因起始日期
- `end_date`：归因结束日期
- `report_ids`：可选；要回填的 OperatingReport ID 列表
- `dry_run`：默认 `false`；为 `true` 时只计算，不写入

返回字段：

- `dry_run`
- `annotated_count`：dry_run=true 时为 0
- `simulation_only`：固定 `true`
- `live_execution_allowed`：固定 `false`
- `attribution`：按 market/currency/industry/style 分组归因结果

#### `GET|POST /api/portfolio/attribution/readiness-report`

（T-408）生成月报/回放/绩效归因生产验收报告，检查 OperatingReport 归因注释覆盖率、已发布月报审批签名、红灯项 owner/due、StrategyReplay variance 复盘、模拟/回测 ledger 来源边界、forward attribution 结果与 artifact URI、绩效/NAV reconciliation artifact、ledger extract artifact、strategy replay artifact、board pack artifact URI 和真实券商/实盘账户禁用边界。本地 board pack 导出只作为审计事件，不替代外部归档 URI。接口只做证据 manifest，不接真实交易账户；`record_readiness=true` 时写入审计事件 `portfolio_attribution_readiness_report`。

请求字段：

- `artifact_uris`
- `forward_report`
- `account_id`
- `strategy_id`
- `record_readiness`

#### `POST /api/portfolio/simulated-feedback`

（T-409）投委会审批入口，对 PortfolioProposal 做模拟审批决策（approved/rejected/pending/needs_revision），并可触发模拟持仓估值和区间收益归因反馈。所有操作固定在纸面组合范围内；不连接真实券商，不自动下单。

请求字段：

- `proposal_id`：必填；目标 PortfolioProposal ID
- `decision`：`approved`、`rejected`、`pending`、`needs_revision` 之一
- `rationale`：投委会审批理由
- `committee_member`：审批人/角色（`cio`、`risk_officer`、`ceo` 等）
- `include_valuation`：可选；为 `true` 时触发模拟持仓估值
- `feedback_start_date`：可选；归因反馈起始日期
- `feedback_end_date`：可选；归因反馈结束日期

返回字段：

- `decision`
- `proposal_id`
- `proposal_status`：`paper`（approved）、`rejected`、`pending`、`needs_revision`
- `simulation_only`：固定 `true`
- `live_execution_allowed`：固定 `false`
- `automation_allowed`：固定 `false`
- `usage_boundary`：固定 `paper_portfolio_simulation`
- `valuation`：可选；触发估值时返回持仓市值、权重和缺失价格
- `attribution`：可选；触发归因时返回区间收益归因

#### `POST /api/macro-themes`

登记宏观主题、政策、技术周期或市场热点，用作产业链扩散分析入口。主题可以来自公开新闻、公告、研报观点、社媒热词、资金流或人工输入，但必须保留来源边界和采集时间。该接口不产生交易信号。

请求字段：

- `theme_id`
- `name`
- `description`
- `trigger_type`
- `as_of_date`
- `source_refs`
- `macro_drivers`
- `risk_factors`
- `confidence`

#### `GET /api/macro-themes`

按 `trigger_type`、关键词 `q` 查询宏观主题列表，返回 `count` 和 `themes`。

#### `POST /api/industry-chains`

登记产业链模板或专题链路。每个链路由一组层级节点和关系边组成，支持从“U 盘、硬盘、内存条、CPU、GPU、蓝牙、射频、WiFi、电源、IGBT、封装、设备、材料、电子化学、代工、硅晶、金属新材料、非金属材料”等节点横向扩展，也支持按上游/中游/下游、价值量、供需瓶颈、国产替代、周期位置和技术路线组织。

请求字段：

- `chain_id`
- `name`
- `root_theme_id`
- `nodes`
- `edges`
- `taxonomy_version`
- `source_refs`

节点字段建议：

- `node_id`
- `name`
- `level`
- `flow_order`
- `process_stage`
- `process_step`
- `process_description`
- `inputs`
- `outputs`
- `category`
- `parent_id`
- `keywords`
- `supply_demand_factors`
- `data_slots`
- `segment_economics`：建议包含 `revenue_pool`、`profit_pool`、`currency`、`period`，用于计算公司在该环节产值/利润池中的占比
  - 三级全景模板也支持证据化经济池条目：`metric`、`value`、`range_low`、`range_high`、`currency`、`period`、`scope`、`source_refs/evidence_ids`、`confidence`

边字段建议：

- `source_node_id`
- `target_node_id`
- `relation_type`
- `direction`
- `strength`
- `evidence_ids`

#### `GET /api/industry-chains`

按 `root_theme_id`、关键词 `q` 查询产业链模板列表，返回 `count` 和 `chains`。

#### `POST /api/industry-chains/template-candidates`

创建产业链模板候选，用于“候选生成 → 证据复核 → 发布入库”。第一条内置样板为 `ai-compute-chain-v1`，会生成 AI 算力链三级全景模板，并兼容发布为正式 `chain_ai_compute_cloud`。

请求字段：

- `template_id`：可传 `ai-compute-chain-v1`
- `candidate_id`
- `target_chain_id`
- `root_theme_id`
- `nodes`
- `edges`
- `official_evidence_ids` / `evidence_ids`
- `source_refs`

候选节点必须包含 `process_step`、`process_description`、`inputs`、`outputs`、`technology_routes`、`bottlenecks`、`source_refs/evidence_ids`；边使用 `source_node_id`、`target_node_id`、`relation_type`、`strength`、`evidence_ids` 表达输入输出流向。事实层只接受公开官方证据：公司公告/年报/招股书/监管披露/官方产品或业务说明。研报、新闻、本地观点只可作为线索或观点层，不能支撑事实发布。

返回字段：

- `candidate`
- `coverage`：包含 L1/L2/L3 覆盖、流程覆盖、官方证据覆盖、经济池缺口和 `publishable`
- `research_tasks`：经济池缺失时返回 `chain_segment_economics_backfill`；缺流程或官方证据时返回阻塞型补研任务
- `automation_allowed=false`

#### `GET /api/industry-chains/template-candidates`

按 `candidate_id`、`target_chain_id/chain_id`、`status`、关键词 `q` 查询候选模板。

#### `POST /api/industry-chains/template-candidates/{candidate_id}/submit-review`

提交候选模板进入复核态，状态变为 `needs_review`。

#### `POST /api/industry-chains/template-candidates/{candidate_id}/review`

提交复核结论。`decision=approved` 时会执行发布门禁：L1/L2/L3 节点必须有流程、输入输出、上下游边和官方证据；经济池可以缺失，但必须形成 `chain_segment_economics_backfill`。

#### `POST /api/industry-chains/template-candidates/{candidate_id}/publish`

把已批准候选发布为正式 `IndustryChain`。发布后的正式链带：

- `template_status=published`
- `template_candidate_id`
- `review_ids`
- `published_at`
- `governance.coverage`

历史未带状态的 `IndustryChain` 继续按 `published_legacy` 兼容。`panorama` 默认只聚合 `published` 与 `published_legacy`。`ai-compute-chain-v1` 发布时会迁移/替换 `chain_ai_compute_cloud`，并对 NVDA、MSFT、AAPL 的现有定位卡升级为按节点拆分的 `revenue_exposure.segments[]` / `profit_exposure.segments[]`；无法被官方证据证明的收入/利润拆分保留 `needs_review`，不估算占比。

#### `GET|POST /api/industry-chains/panorama`

输出全景产业链地图，用于从主题、产品、行业或公司出发，把多条已登记产业链合并成上游/中游/下游全局视图。它不是只看一条链，而是返回：

- `panorama_stages`：按 `upstream/midstream/downstream/supporting/adjacent` 汇总的流程层
- `process_map`：跨产业链的实际工序、输入、输出、上下游节点
- `segment_company_map`：每个环节的公司清单、产值池/利润池、公司环节占比
- `company_directory`：公司在多个链路/多个环节中的全景定位
- `coverage`：链路、节点、工序、公司、已计算占比和缺口任务覆盖
- `research_tasks`：缺流程、缺环节经济池、缺公司映射时生成的补研任务

请求过滤字段：

- `q`：按主题、产品、行业、公司名、代码、节点关键词检索相关产业链
- `root_theme_id`
- `chain_ids` / `chain_id`
- `issuer_id`
- `security_id`
- `node_id`
- `chain_limit`

返回固定包含 `automation_allowed=false` 和 `usage_boundary=panoramic_industry_chain_research_only_not_trade_signal`。接口只汇总已登记、可追溯的产业链与公司定位，不把缺失字段自动推断为事实。

#### `GET|POST /api/industry-chains/panorama/readiness-report`

输出全景产业链质量诊断，用于持续推进模板和公司归因的补研闭环。它会逐节点检查：

- 实际生产流程：`process_description`、`inputs`、`outputs`、`technology_routes`、`bottlenecks`
- 输入输出关系：节点是否接入上下游边
- 事实层证据：节点是否有公开官方 evidence
- 环节经济池：是否有收入池和利润池
- 公司目录：节点是否有公司定位
- 公司收入/利润归因：公司节点拆分是否有金额/比例和官方证据

请求字段沿用 panorama 过滤条件，并新增：

- `queue_tasks`：为 `true` 时，把缺流程、缺边、缺官方证据、缺经济池、缺公司映射、缺公司归因转成 `ResearchTask`

返回字段：

- `coverage`：含 `process_coverage`、`flow_coverage`、`official_evidence_coverage`、`economic_pool_coverage`、`company_mapping_coverage`、`company_attribution_coverage` 和加权 `readiness_score`
- `by_stage`：按 `upstream/midstream/downstream/supporting` 分阶段质量诊断
- `chains[].nodes[]`：节点级缺口、经济池和公司归因状态
- `research_tasks` / `queued_tasks`
- `automation_allowed=false`

#### `GET|POST /api/industry-chains/{chain_id}/analysis`

输出单条产业链的流程与环节公司占比分析。服务会按节点 `flow_order/level` 组织实际流程，汇总每个环节的公司定位卡，并在同时具备公司环节收入/利润金额和节点 `segment_economics.revenue_pool/profit_pool` 时计算：

- `revenue_share_of_segment`
- `profit_share_of_segment`
- `mapped_revenue_pool_coverage`
- `mapped_profit_pool_coverage`

如果公司定位卡只提供收入/利润暴露比例，且发行人 `fundamentals` 中存在对应收入/利润基数，接口会用“暴露比例 × 发行人财务基数”推导环节金额，并在 `*_calculation_basis` 中说明。缺少实际流程、环节经济池或公司映射时，返回 `research_tasks`，不会自动补结论。

公司定位也支持按节点拆分：

- `revenue_exposure.segments[]`
- `profit_exposure.segments[]`

每项建议包含 `node_id`、`amount` 或 `ratio`、`period`、`scope`、`evidence_ids`、`calculation_basis`、`needs_review`。占比仍按“公司环节收入/利润 ÷ 环节收入/利润池”计算；无可靠经济池时不估算，并返回补研任务。

请求过滤字段：

- `issuer_id`
- `security_id`
- `node_id`

返回字段：

- `chain`
- `process_flow`
- `segments`
- `stage_summary`
- `company_exposures`
- `coverage`
- `research_tasks`
- `automation_allowed=false`
- `usage_boundary`

#### `POST /api/industry-chains/{chain_id}/companies`

把公司映射到产业链节点，形成“公司定位卡”。同一家公司可落在多个节点，但必须说明主营角色、收入/利润/产能/客户/供应商/技术壁垒/风险暴露的证据来源。公司定位只用于投研分析和模拟组合候选池，不自动生成交易动作。

请求字段：

- `issuer_id`
- `security_id`
- `node_ids`
- `role`
- `positioning_summary`
- `revenue_exposure`
- `profit_exposure`
- `capacity`
- `customers`
- `suppliers`
- `competitors`
- `technology_tags`
- `valuation_metrics`
- `event_refs`
- `evidence_ids`
- `data_quality`

#### `GET /api/company-positions`

按 `chain_id`、`issuer_id`、`security_id`、`node_id`、`role` 查询公司定位卡，返回 `count` 和 `positions`。

#### `GET /api/analysis/latest`

读取本机最新分析产物，供 CEO Dashboard 和本地投研 UI 展示。接口优先读取 `artifacts/latest-analysis/latest-analysis.json`，兼容旧的 `artifacts/latest-analysis-ahu/latest-analysis.json`；如果尚未生成最新分析，会返回 `status=missing` 和空列表。该接口只展示投研分析、模拟组合和证据边界，不连接券商、不触发真实交易。

主要返回字段：

- `status`
- `generated_at`
- `latest_market_date`
- `assets`
- `snapshots`
- `returns`
- `weights`
- `research_evidence`
- `company_intelligence`
- `counts`
- `source_summary`

`research_evidence` 包含本地研报数量、`research_report_citation` 证据数量、语义检索召回状态、热点扩散召回状态和用途边界。研报 evidence 固定为观点/参考层，不能升级为事实真相源、训练源或真实交易信号。
`company_intelligence` 是按本机资产列表补出的公司情报链路快照，返回 `schema_id=latest-analysis-company-intelligence-v1`、`company_count`、`ready_count`、`needs_attention_count`、`companies[]` 和 `usage_boundary`。每条 company 条目会带 `company_counts`、`relationship_summary`、`coverage_score`、`relationship_status`、`next_actions`、`completeness_verdict` 和 `data_quality`，用于把公司画像、产业链、关系、结论和模拟反馈串成一条可视化链路；它只使用本地已有公司情报，不下载外部资料，也不触发真实交易。

#### `GET /api/company-positions/schema`

返回公司定位卡字段字典和必填数据槽位，包含 `schema_id`、`required_data_slots`、`data_quality_values`、`fields` 和 `usage_boundary`。该 schema 用于统一前端录入、批量导入、覆盖度报告和后续自动回填。

#### `GET|POST /api/company-positions/coverage-report`

输出公司定位卡覆盖度和缺口报告。接口按 `required_data_slots` 检查每个定位卡的字段完备性和 evidence 回链，返回 `coverage.slot_coverage`、`coverage.evidence_coverage`、`issues`、`research_tasks`，并按 `chain`、`node` 聚合覆盖率，用于补齐研究任务队列。

#### `POST /api/hotspot-lexicons`

登记热点扩散词表，用于把同义词、相关产业链节点和默认数据槽位配置化。词表只驱动研究召回和图谱扩展，不代表事实结论或交易信号。

请求字段：

- `lexicon_id`
- `name`
- `terms`
- `synonyms`
- `related_chain_nodes`
- `default_data_slots`
- `source_refs`
- `taxonomy_version`

#### `GET /api/hotspot-lexicons`

按关键词 `q` 查询热点扩散词表，返回 `count` 和 `lexicons`。

#### `POST /api/hotspots/expand`

从热点词、主题、技术名、产品名或公司名发散生成产业链研究地图。输出应包含扩散路径、相关公司、关键数据槽位、缺失证据、潜在反证、事实/观点/推断分层和后续研究任务；不得输出自动下单建议。

请求字段：

- `query`
- `as_of_date`
- `markets`
- `max_depth`
- `include_restricted`
- `seed_theme_id`
- `seed_chain_id`
- `required_data_slots`
- `page_size`
- `page_token`

返回字段：

- `theme`
- `matched_lexicons`
- `chain_nodes`
- `chain_edges`
- `company_positions`
- `data_coverage`
- `retrieval_recall`
- `ranked_candidates`
- `missing_evidence`
- `counter_theses`
- `research_tasks`
- `evidence_layers`
- `pagination`
- `automation_allowed=false`

`retrieval_recall` 分为 `public_facts`、`research_opinions`、`market_signals`，用于把公告/证据、研报观点和公开行情线索分开召回。`ranked_candidates` 使用本地可解释排序，综合词表命中、公司定位字段覆盖、evidence 回链、公开资料召回和数据质量，输出 `rank_score`、`score_components`、`matched_terms` 和后续 LLM rerank 触发建议。`evidence_layers` 分为 `facts`、`opinions`、`inferences`、`needs_verification`。只有具备 evidence 回链的公司定位或公开资料召回才进入 facts；主题描述和来源观点进入 opinions；词表扩展、链路邻接、缺字段或缺证据的公司定位进入 inferences 或 needs_verification。

生产态分页：`page_size` 默认 50、最大 200；`page_token` 是非负整数 offset。返回的 `pagination.sections` 按 `chain_nodes`、`chain_edges`、`company_positions`、`data_coverage`、`ranked_candidates`、`missing_evidence`、`research_tasks` 分别给出 `total`、`offset`、`page_size`、`returned`、`has_more` 和 `next_page_token`。默认未传分页参数时保持兼容，样本结果仍一次返回。

#### `GET|POST /api/hotspots/readiness-report`

汇总热点扩散、产业链公司定位和 LLM rerank 排序辅助的生产验收。请求字段同 `POST /api/hotspots/expand`，并支持 `min_chain_depth`、`min_company_positions`、`min_slot_coverage`、`min_evidence_coverage`、`min_rerank_samples`、`min_rerank_top1_accuracy`、`rerank_evaluation`、`artifact_uris` 和 `record_readiness`。报告会检查词表命中、3 层或配置深度的链路扩散、公司定位必填数据槽位、evidence 回链、facts/opinions/inferences/needs_verification 分层、缺口 research task 是否固化或复核、图谱 edge 元数据覆盖、离线 LLM rerank/gold refs 质量摘要和外部 artifact URI。返回 `ready_for_hotspot_research_production`、`missing_requirements`、`gates`、`coverage_report`、`layer_summary`、`boundary_summary`、`research_queue`、`graph_summary`、`rerank_evaluation`、`artifact_uris`。固定 `automation_allowed=false`、`live_execution_allowed=false`；不会在 readiness 报告中调用模型、图数据库、向量库或交易系统。

#### `POST /api/research/tasks/from-hotspot`

把热点扩散结果中的 `research_tasks` 固化为研究任务队列。重复提交同一热点/产业链/公司定位缺口时不会创建重复任务，而是刷新既有任务的缺失字段和更新时间。该接口只用于公开资料分析、产业链补全和模拟持仓反馈，不触发真实交易。

请求字段同 `POST /api/hotspots/expand`。即使 `page_size` 很小，默认也会跨页收集当前热点下全部 `research_tasks` 后固化；如只想固化当前页，可传 `queue_current_page=true`。返回 `created_count`、`existing_count`、`created_tasks`、`existing_tasks`、`source_research_task_count` 和 `usage_boundary`。

#### `POST /api/research/tasks/from-hotspot/batch`

批量把多个热点词展开并固化为研究任务队列。请求字段：

- `queries`
- `batch_limit`
- 其他字段同 `POST /api/hotspots/expand`

返回 `batch_id`、`query_count`、`created_count`、`existing_count`、`source_research_task_count`、逐 query `results`、`automation_allowed=false`、`live_execution_allowed=false` 和批量研究队列边界。重复提交同一批热点保持幂等，不会创建重复任务。

#### `POST /api/research/tasks`

手工创建研究任务，用于补齐公司定位卡、产业链节点公司映射、证据回链、财务/产能/客户字段等。

请求字段：

- `task_id`
- `task_type`
- `source`
- `issuer_id`
- `security_id`
- `chain_id`
- `node_ids`
- `position_id`
- `required_slots`
- `reason`
- `status=open|in_progress|done|dismissed`
- `priority`
- `assignee`
- `evidence_ids`
- `metadata`

#### `POST /api/research/tasks/sec-single-name/run`

把单标的 SEC 研究闭环产品化，默认以 Apple/AAPL 作为样例，串起 SEC recent ingestion、证据抽取、英文优先 research answer、thesis/scoring/challenger、research card、decision pack、approval、execution intent 和 simulated execution。默认 `ticker=AAPL`、`cik=0000320193`、`issuer_id=issuer_aapl`、`security_id=security_aapl_us`、`document_types=["10-K","10-Q"]`、`limit=1`、`include_body=true`、`fallback_mode=local_sample`。实时 SEC 优先；正文下载、限速或抽取失败时会回退到本地 SEC-like 样例文档，并在响应中保留 `fallback_reason`。全程固定 `simulation_only=true`、`live_execution_allowed=false`、`usage_boundary=sec_single_name_research_simulated_only_no_broker_execution`。

请求字段：

- `ticker`
- `cik`
- `issuer_id`
- `security_id`
- `company_name`
- `document_types`
- `limit`
- `include_body`
- `fallback_mode`
- `force_fallback`
- `question`
- `trade_date`
- `action`
- `target_weight`
- `owner`
- `reviewer`
- `risk_user`
- `ceo_user`
- `human_review_status`

返回字段：

- `workflow_status`
- `used_realtime_sec`
- `fallback_reason`
- `fallback_mode`
- `simulation_only`
- `live_execution_allowed`
- `usage_boundary`
- `ids`
- `summary`
- `workflow_stages`
- `ingestion`
- `extraction_errors`
- `issuer` / `security` / `document` / `documents`
- `evidence`
- `research_answer`
- `thesis`
- `signal`
- `challenger`
- `research_card`
- `decision`
- `decision_pack`：同 `decision`，作为编排 API 的投委会 pack 语义别名保留
- `intent`
- `simulated_execution`
- `task`

`research_answer` 默认使用英文证据优先路径，问题默认是 “What changed in revenue, services resilience, and key risk factors?”，并且会保留研究审计所需的 `summary_version`、`prompt_version` 和 `model_version` 元数据。

#### `GET /api/research/tasks`

按 `status`、`task_type`、`issuer_id`、`security_id`、`chain_id`、`node_id`、`position_id`、`source` 查询任务队列，返回 `count` 和 `tasks`。

#### `POST /api/research/tasks/{task_id}/status`

更新研究任务状态、负责人、优先级、证据回链和补充元数据。允许状态为 `open`、`in_progress`、`done`、`dismissed`。

#### 公司情报一等对象 API

以下接口是公司情报平台 T-432 至 T-435 的核心写入/查询入口。它们只服务本地研究、观点跟踪、观察任务、分析结论和 paper-only 模拟反馈，不连接真实券商，不把研报观点当作事实源。

| 接口 | 方法 | 用途 |
|---|---|---|
| `/api/company-profiles` | `GET` / `POST` | 查询或登记 `CompanyProfile`，可由 `Issuer`、`Security`、行情、事件、关系和研报覆盖计算画像质量 |
| `/api/company-profiles/schema` | `GET` | 返回公司画像核心字段、来源优先级和质量指标 |
| `/api/company-financial-metrics` | `GET` / `POST` | 查询或登记公司财务指标事实记录；只接受治理后的事实来源，不接受研报/新闻/人工参考作为事实源 |
| `/api/company-profiles/fields/extract` | `POST` | 从已入库官方披露、公司 IR、公司官网或监管/交易所文档抽取公司画像字段；默认 dry-run，显式 `execute=true` 才写入 |
| `/api/company-profiles/field-assertions` | `GET` / `POST` | 查询公司画像字段级事实断言，按字段返回来源、文档、证据、置信度和状态 |
| `/api/company-profiles/field-assertions/review` | `POST` | 复核画像字段断言冲突，支持 approve、supersede、reject，批准后才替换公司画像字段 |
| `/api/company-profiles/coverage/audit` | `GET` / `POST` | 按公司输出画像深字段覆盖率、缺失字段、来源记录、证据回链和推荐补齐来源 |
| `/api/company-database/profile-field-coverage/audit` | `GET` / `POST` | `company-profiles/coverage/audit` 的兼容别名，用于公司数据库补齐任务按深字段审计 |
| `/api/company-database/profile-field-assertions` | `GET` / `POST` | `company-profiles/field-assertions` 的兼容别名，用于公司数据库补齐任务查询字段级 provenance |
| `/api/company-database/profile-field-assertions/review` | `POST` | `company-profiles/field-assertions/review` 的兼容别名，用于补库流程处理字段冲突候选 |
| `/api/company-database/profile-fields/extract` | `POST` | `company-profiles/fields/extract` 的公司数据库兼容入口，用于补库流程先抽取画像字段再审计覆盖 |
| `/api/company-database/bootstrap` | `POST` | 为未知 symbol 创建本地 issuer/security/profile stub；默认 dry-run，返回材料 inbox manifest 模板和覆盖预览 |
| `/api/company-database/package/import` | `POST` | 从本地 watchlist / 公司包 JSON 或 CSV 批量创建本地 issuer/security/profile stub；默认 dry-run，返回每家公司材料 inbox 模板 |
| `/api/company-database/watchlist/import` | `POST` | `company-database/package/import` 的兼容别名，用于直接导入观察池 symbol 列表 |
| `/api/company-database/package/import/runs` | `GET` / `POST` | 查询本地 watchlist / 公司包导入运行历史，用于审计、失败复盘和后续材料 inbox 准备 |
| `/api/company-database/watchlist/import/runs` | `GET` / `POST` | `company-database/package/import/runs` 的兼容别名 |
| `/api/company-database/package/import/runs/{run_id}/material-manifests` | `POST` | 从公司包导入 run 生成本地 material inbox manifest sidecar 模板；默认 dry-run，显式 execute 才写入本地文件 |
| `/api/company-database/watchlist/import/runs/{run_id}/material-manifests` | `POST` | `company-database/package/import/runs/{run_id}/material-manifests` 的兼容别名 |
| `/api/company-database/build` | `POST` | 从现有主体、证券、行情和研报资产构建最小公司数据库；默认 dry-run，显式 `execute=true` 后才持久化公司画像和研报绑定 |
| `/api/company-database/batch/build` | `POST` | 按批次编排公司画像、事件、关系、观察结论和模拟反馈构建，并返回批次汇总和覆盖率 |
| `/api/company-database/batch/runs` | `GET` / `POST` | 查询公司数据库批量补齐运行历史，用于审计、复盘和后续断点续跑 |
| `/api/company-database/batch/runs/{run_id}/retry` | `POST` | 基于已持久化补库 run 本地重放全部或剩余公司，用于失败重试和断点续跑 |
| `/api/company-database/coverage/trends` | `GET` / `POST` | 从补库运行历史生成覆盖率趋势和可选本地 artifact，用于复盘补库是否改善公司数据库 |
| `/api/company-database/coverage/audit` | `GET` / `POST` | 按公司审计画像、证券、行情、财务、文档、事件、关系、研报、观察结论和模拟反馈覆盖情况 |
| `/api/company-database/quality/reconcile` | `POST` | 对公司事件和关系做本地去重、实体别名归并候选和来源质量评分；默认 dry-run，显式 `execute=true` 才标记 merge 或写入 source quality |
| `/api/data-health/runs/summary` | `GET` / `POST` | 聚合 ingestion、公司补库、公司包导入、闭环刷新、本地材料、日更和个人关注池刷新 run，返回统一只读摘要 |
| `/api/data-health/summary` | `GET` / `POST` | 面向个人用户的数据来源健康摘要，覆盖行情、研报、披露、IR/官网材料、公司数据库和 paper-only 闭环反馈 |
| `/api/company-database/events/build` | `POST` | 从已入库公开披露、披露正文证据、公开行情和研报覆盖生成公司事件时间线；研报事件固定为观点/关注度信号，不作为事实源 |
| `/api/company-database/events/review` | `POST` | 批量复核公司事件候选，支持 approve/reject/merge/reclassify，返回本地人工复核结果和推荐摘要 |
| `/api/company-database/relationships/build` | `POST` | 从证券上市关系、研报覆盖记录和公开披露文本生成最小公司关系层；研报覆盖关系固定为观点/关注度关系，公开披露抽取关系默认待复核 |
| `/api/company-database/relationships/review` | `POST` | 批量复核公司关系候选，支持 approve/reject/merge，返回本地人工复核结果和推荐摘要 |
| `/api/company-database/workflow/build` | `POST` | 从事件、关系和研报观点生成观察任务、公司情报基线结论和 paper-only 模拟反馈；默认 dry-run |
| `/api/company-events` | `GET` / `POST` | 查询或登记 `CompanyEvent`，覆盖公告、财报、新闻、政策、订单、诉讼、价格、供需等事件 |
| `/api/company-events/review` | `POST` | 批量复核 `CompanyEvent` 候选；用于人工时间线质量处理，不触发交易 |
| `/api/company-events/{event_id}/review` | `POST` | 人工审核事件候选，支持 approve、reject、merge、reclassify，保留审核历史和证据回链 |
| `/api/company-relationships` | `GET` / `POST` | 查询或登记 `CompanyRelationship`，覆盖客户、供应商、竞争、股权、机构覆盖、分析师覆盖和上下游 |
| `/api/company-relationships/review` | `POST` | 批量复核 `CompanyRelationship` 候选；用于人工图谱质量处理，不触发交易 |
| `/api/company-relationships/{relationship_id}/review` | `POST` | 人工审核关系候选，支持 approve、reject、merge，保留审核历史和证据回链 |
| `/api/research-reports/structure` | `POST` | 把本地研报资产批量结构化为研报、观点、预测和分析师画像，固定观点层边界 |
| `/api/research-reports/realization/update` | `POST` | 用本地最新行情更新研报目标价预测和观点兑现状态，并可重算分析师可靠性 |
| `/api/research-reports/structured` | `GET` / `POST` | 查询或登记结构化 `ResearchReport`，字段包含机构、分析师、发布时间、评级、目标价、估值方法和边界 |
| `/api/research-report-viewpoints` | `GET` / `POST` | 查询或登记 `ReportViewpoint`，记录研报观点、目标价、核心假设、催化剂、风险和兑现状态 |
| `/api/research-report-forecasts` | `GET` / `POST` | 查询或登记 `ReportForecast`，记录预测值、实际值、误差和兑现状态 |
| `/api/analyst-profiles` | `GET` / `POST` | 查询或登记 `AnalystProfile` |
| `/api/analyst-reliability-scores` | `GET` / `POST` | 查询或计算 `AnalystReliabilityScore`，基于预测样本、目标价命中和误差覆盖率 |
| `/api/observation-items` | `GET` / `POST` | 查询或登记 `ObservationItem`，用于观察池、触发条件和证据缺口 |
| `/api/analysis-conclusions` | `GET` / `POST` | 查询或登记 `AnalysisConclusion`，记录事实、推断、主观判断、证据、反证和复盘计划 |
| `/api/simulation-feedback` | `GET` / `POST` | 查询或登记 `SimulationFeedback`，固定 `paper_only=true`、`live_execution_allowed=false` |
| `/api/simulation-feedback/performance/update` | `POST` | 使用本地最新行情更新 paper-only 模拟反馈表现，不连接券商 |
| `/api/company-intelligence/{symbol}/cycle/run` | `POST` | 公司级闭环刷新 runner，串联研报兑现、workflow 重建和 paper-only 模拟反馈表现更新；默认 dry-run |

过滤字段通用支持 `issuer_id`、`security_id`、`limit`；各接口还支持与对象对应的状态、类型、分析师、研报或结论 ID 过滤。`/api/simulation-feedback` 会拒绝任何 `paper_only=false`、`live_execution_allowed=true` 或 `broker_connected=true` 的请求。

#### `POST /api/company-profiles/fields/extract`

从已入库并通过来源边界的 `Document` / `Evidence` 中抽取公司画像字段候选。该接口不访问外网、不下载文件、不调用真实券商；默认只返回候选，只有显式 `execute=true` 才更新 `Issuer.company_details`、`Issuer.fundamentals`、`Issuer.data_sources` 并物化 `CompanyProfile`。

兼容别名：`POST /api/company-database/profile-fields/extract`。

请求字段：

- `issuer_ids` / `symbols` / `symbol` / `ticker` / `q`：目标公司解析字段，复用公司数据库目标解析规则。
- `fields` / `required_fields`：可选；默认抽取 `business_summary`、`products`、`website_url`、`ir_url`、`headquarters`、`employee_count`、`management`、`key_customers`、`key_suppliers`、`country`、`region`、`sector`、`industry`、`period`、`revenue`、`net_income`、`gross_margin`、`cash`、`debt`。
- `document_ids`：可选；只从指定文档抽取。
- `limit`：目标公司数量上限，默认 100。
- `document_limit` / `max_documents`：每家公司扫描的合规文档数量上限，默认 20。
- `evidence_limit`：每家公司扫描的官方证据数量上限，默认 500。
- `min_confidence`：可选；低于该置信度的候选不返回。
- `require_evidence`：可选；为 `true` 时仅使用带 `Evidence` 回链的文本，不使用整篇文档正文。
- `refresh_existing` / `overwrite`：默认 `false`；已有字段不被覆盖，为 `true` 时可用更高优先级官方/IR 记录刷新。
- `execute` / `dry_run`：默认 dry-run；`execute=true` 且 `dry_run` 非真时才写入。

返回字段：

- `schema_id`：当前为 `company-profile-field-extraction-v1`。
- `status`：`dry_run` 或 `executed`。
- `totals.documents_scanned` / `evidence_scanned` / `candidates_found` / `fields_planned` / `fields_updated` / `assertions_recorded` / `conflict_assertions` / `profiles_saved`。
- `companies[].candidates[]`：字段候选，包含 `field`、`value`、`confidence`、`document_id`、`source_id`、`evidence_ids`、`section`、`extraction_method`、`source_policy` 和 `status`。
- `companies[].applied`：执行时返回写入字段、字段级 `assertion_ids`、是否保存 `CompanyProfile` 和保存后的 profile 摘要。
- `source_rules.research_reports`：固定为 `ignored_for_fact_fields_opinion_only`。

边界：抽取只接受 `_company_profile_document_is_fact_source` 和 `_evidence_is_official_public` 认可的官方披露、公司 IR、公司官网、交易所/监管披露或公开公司披露记录。`research_report`、`broker_research`、`local_reference`、`manual_reference`、`news` 和 `curated_public_profile` 不会写入事实字段，也不会生成 `CompanyProfileFieldAssertion`。

执行语义：`execute=true` 后，每个成功应用的字段会生成或更新一条幂等 `CompanyProfileFieldAssertion`，记录 `field_name`、`value`、`document_ids`、`evidence_ids`、`source_ids`、`confidence`、`source_policy`、`fact_status` 和 `review_status`。这些断言用于后续字段级证据审计、冲突处理和公司情报页 provenance 展示。财务字段 `revenue`、`net_income`、`gross_margin`、`cash`、`debt` 在同一轮存在 `period` 时，还会同步物化为 `FinancialMetric`，供公司情报页和深字段覆盖审计读取最新财务快照。

冲突语义：当 `refresh_existing=true` / `overwrite=true` 且同一公司、同一字段、同一 period 已存在 active 断言但新值不同，接口不会立即覆盖 `Issuer` 或 `CompanyProfile` 当前字段。它会生成 `assertion_status=conflict_candidate`、`review_status=needs_review` 的新断言，并在 `conflicts_with` 中记录被冲突的旧断言 ID。只有复核接口批准后，新值才会应用到公司画像。

#### `POST /api/company-database/bootstrap`

为本地还没有 `issuer/security` 的 symbol 建立最小公司数据库入口。该接口不访问外网、不下载资料、不运行研究、不连接券商；默认 dry-run，只返回将创建的主体、证券、画像和材料入库模板。显式 `execute=true` 后才创建本地 `Issuer`、`Security` 和可选 `CompanyProfile` stub。

请求字段：

- `symbol` / `ticker` / `code`：必填其一；例如 `SPCX`、`NEWC`、`600000.SH`。
- `company_name` / `legal_name` / `display_name`：可选；缺省使用 symbol。
- `issuer_id` / `security_id`：可选；用于指定本地 ID。缺省按 symbol 生成稳定 `issuer_bootstrap_*` / `sec_bootstrap_*`。
- `market` / `exchange` / `currency` / `country`：可选；未提供时按 A/H/U 简单推断。
- `sector` / `industry` / `region` / `board` / `listing_date`：可选画像字段。
- `create_profile`：默认 `true`；是否同步创建 `CompanyProfile` stub。
- `execute` / `dry_run`：默认 dry-run；`execute=true` 且 `dry_run` 非真时才写入。

返回字段：

- `schema_id`：当前为 `company-database-bootstrap-v1`。
- `status`：`dry_run`、`executed` 或 `already_exists`。
- `ids.issuer_id` / `ids.security_id`：目标本地 ID。
- `created` / `existing`：分别说明本次创建和已有对象。
- `issuer` / `security` / `company_profile`：计划或已创建对象摘要。
- `coverage`：执行后为真实覆盖审计；dry-run 时为本地覆盖预览。
- `material_inbox_manifest_template`：可复制到本地材料 inbox 的 manifest sidecar 模板，默认来源类型为 `company_ir`。
- `next_actions`：建档后建议先准备官方/IR/公告材料，再执行 material inbox、画像字段抽取和覆盖审计。

边界：bootstrap 只建立本地研究对象骨架。它不会用研报补事实字段，不会把新闻/人工参考作为事实源，不会下载外部数据，也不会创建真实交易或订单。

#### `POST /api/company-database/package/import`

从本地 watchlist / 公司包导入一组待研究公司，并逐家公司复用 `company-database/bootstrap` 创建或预览本地 `Issuer`、`Security` 和 `CompanyProfile` stub。兼容别名：`POST /api/company-database/watchlist/import`。

请求字段：

- `root_path` / `package_root`：可选；本地公司包目录。仅读取本地文件，不访问外网。
- `manifest_glob`：可选；默认 `*.watchlist.*`。支持 JSON 与 CSV。JSON 可为单对象、对象内 `companies[]` / `items[]` / `watchlist[]` 或数组；CSV 至少应包含 `symbol` / `ticker` / `code` 之一。
- `companies` / `items` / `watchlist`：可选数组；元素可以是 symbol 字符串或公司对象。
- `symbols` / `tickers` / `codes`：可选字符串或数组；用于直接导入观察池标的。
- `csv_text` / `csv`：可选；内联 CSV 文本。
- `market` / `exchange` / `currency` / `country` / `sector` / `industry` / `region` / `security_type` / `create_profile`：可选默认值，会传递给每家公司 bootstrap。
- `limit` / `scan_limit`：导入上限，默认 200，最大 1000。
- `execute` / `dry_run`：默认 dry-run；`execute=true` 且 `dry_run` 非真时才写入。
- `record_run`：可选；`execute=true` 默认记录导入运行历史，dry-run 默认不记录。dry-run 如需审计留痕，显式传 `record_run=true`。

返回字段：

- `schema_id`：当前为 `company-database-package-import-v1`。
- `status`：`dry_run`、`executed`、`partial` 或 `failed`。
- `totals`：包含 `input_count`、`valid_count`、`planned_count`、`executed_count`、`already_exists_count`、`invalid_count`、`duplicate_count`、`failed_count`、`created_issuers`、`created_securities`、`created_company_profiles` 和 `manifest_templates`。
- `companies[]` / `items[]`：逐家公司结果，包含 `symbol`、`status`、`ids`、`created`、`existing`、`coverage`、`material_inbox_manifest_template`、`next_actions` 和 `errors`。
- `coverage_after`：执行模式下，对本次导入公司做一次覆盖率审计。
- `run_id` / `run_recorded` / `run`：导入运行历史元数据。`execute=true` 或 `record_run=true` 时写入 `CompanyPackageImportRun`；否则只返回本次生成的 `run_id`，不落盘。
- `next_actions`：导入后建议先准备官方/IR/公告材料，再执行材料 inbox、批量补库和覆盖审计。

边界：该接口只处理本地 watchlist / 公司包，不下载外部数据，不把研报、新闻或人工参考提升为事实字段，不触发真实交易。它不会在空输入时 fallback 到全量 issuer；缺 symbol 的行会进入 `invalid`。

运行历史语义：

- `CompanyPackageImportRun` 独立于 `CompanyDatabaseBuildRun`，不复用补库 run；导入 run 只描述 watchlist / 公司包导入，不包含 retry/resume/batch 语义。
- 存储字段包括 `run_id`、`actor`、`status`、`execute`、`dry_run`、`root_path`、`manifest_glob`、`input_count`、`company_count`、`target_symbols`、`target_issuer_ids`、`created_issuer_ids`、`existing_issuer_ids`、`invalid_symbols`、`duplicate_symbols`、`totals`、`options`、`items`、`coverage_after`、`error`、`started_at`、`completed_at` 和 `usage_boundary`。
- `items` 只保存 slim 审计行：`index`、`input_source`、`symbol`、`status`、`issuer_id`、`security_id`、`created`、`existing`、`errors`。即时响应中的 `coverage`、`material_inbox_manifest_template` 和 `next_actions` 不进入运行历史，避免膨胀。

#### `GET|POST /api/company-database/package/import/runs`

查询本地 watchlist / 公司包导入运行历史。兼容别名：`GET|POST /api/company-database/watchlist/import/runs`。

查询字段：

- `run_id`：按单次导入运行过滤。
- `issuer_id`：按本次导入涉及的公司主体过滤。
- `symbol` / `ticker` / `code`：按本次导入涉及的证券代码过滤。
- `status`：可选，`dry_run`、`executed`、`partial` 或 `failed`。
- `limit`：返回数量上限，默认 20，最大 200。
- `include_items`：默认 `false`；为 `true` 时返回 slim `items` 明细。默认列表会返回 `items=[]` 和 `item_details_omitted=true`。

返回字段：

- `count`：过滤后的 run 总数。
- `include_items`：是否返回逐行明细。
- `runs[]`：导入运行历史，字段见 `CompanyPackageImportRun`。
- `usage_boundary`：固定为本地 watchlist 历史、无外部下载、无真实交易。

不支持：该接口不做 retry/resume，不重跑导入，不读取或下载外部公司包。需要再次导入时，重新调用 `POST /api/company-database/package/import`。

#### `POST /api/company-database/package/import/runs/{run_id}/material-manifests`

从已持久化的公司包导入 run 生成本地 material inbox manifest sidecar 模板，帮助用户把“公司包导入后的公司清单”转成“下一步需要补的官方/IR/公告材料清单”。兼容别名：`POST /api/company-database/watchlist/import/runs/{run_id}/material-manifests`。

请求字段：

- `output_root` / `root_path`：可选；manifest 输出目录。dry-run 可为空；`execute=true` 时必填。
- `limit`：生成数量上限，默认 200，最大 1000。
- `execute` / `dry_run`：默认 dry-run；`execute=true` 且 `dry_run` 非真时才写入本地 `*.manifest.json` 文件。
- `overwrite`：默认 `false`；目标 manifest 已存在时默认跳过并返回 `skipped_existing`。
- `source_uri_template`：可选；支持 `{symbol}`、`{raw_symbol}`、`{issuer_id}`、`{security_id}`。未传时优先使用本地公司画像里的 `ir_url` / `website_url` 或已登记官方 source provenance，仍无可用 URL 时才回退到示例 IR URL。
- `manifest_name_template`：可选；默认 `{symbol}-company-profile.manifest.json`。
- `file_path_template`：可选；默认 `./{symbol}-company-profile.md`，指向用户后续放入 inbox 的正文文件。
- `title_template`：可选；默认 `{raw_symbol} official company profile`。

返回字段：

- `schema_id`：当前为 `company-material-manifest-export-v1`。
- `status`：`dry_run` 或 `executed`。
- `manifest_count` / `written_count` / `skipped_count`：模板数量、实际写入数量和跳过数量。
- `items[]`：每个公司一条 manifest 模板，包含 `issuer_id`、`security_id`、`symbol`、`manifest_path`、`template`、`status` 和 `errors`。

#### `GET|POST /api/company-database/material-inbox/pending`

从本地公司包导入历史派生待补材料队列，帮助用户确认“已导入公司清单”里哪些公司还缺 manifest sidecar、哪些已经有 manifest 但缺正文文件、哪些已准备好进入材料 inbox 入库。

请求字段：

- `run_id`：可选；限定某次公司包导入 run。
- `symbol` / `ticker` / `code`：可选；限定某个公司代码。
- `material_root` / `output_root` / `root_path`：可选；本地材料目录，用于检查 `*.manifest.json` 和正文文件是否存在。
- `limit`：返回数量上限，默认 200，最大 1000。

返回字段：

- `schema_id`：当前为 `company-material-inbox-pending-v1`。
- `pending_count` / `status_counts`：待补队列数量和状态分布。
- `items[]`：包含 `run_id`、`issuer_id`、`security_id`、`symbol`、`status`、`manifest_path`、`material_path`、`manifest_exists`、`material_exists`、`source_uri` 和 `next_action`。
- `usage_boundary`：固定声明本地材料准备队列、无外部下载、无训练、无真实交易。
- `next_actions`：提示用户补正文文件后调用 `/api/company-database/material-inbox/ingest`。
- `usage_boundary`：固定为本地 manifest 导出、无外部下载、无训练、无真实交易。

边界：该接口只生成 sidecar 模板或写入本地 manifest JSON，不下载公司资料，不访问外网，不把研报当事实源，也不写入 `Source` / `Document` / `Evidence`。真正入库仍必须由 material inbox 在用户准备好官方/IR/公告正文后执行。

#### `GET|POST /api/company-financial-metrics`

公司财务指标事实记录入口。`GET` 用于查询；`POST` 用于登记单条治理后的财务指标。财务指标可以由官方/IR/监管材料抽取画像字段时自动物化，也可以由本地已治理事实管道显式登记。

查询字段：

- `issuer_id` / `issuer_ids` / `symbols` / `symbol` / `ticker` / `q`：目标公司过滤字段。
- `security_id`：可选；按证券过滤。
- `metric_name`：可选；如 `revenue`、`net_income`、`gross_margin`、`cash`、`debt`。
- `period` / `currency` / `unit` / `statement_type` / `fact_status` / `review_status`：可选过滤字段。
- `limit`：返回上限，默认 100。

登记字段：

- 必填：`issuer_id`、`metric_name`、`period`、`value`。
- 可选：`security_id`、`period_start`、`period_end`、`fiscal_year`、`fiscal_period`、`unit`、`currency`、`statement_type`、`confidence`、`source_ids`、`document_ids`、`evidence_ids`、`metadata`。
- `statement_type` 允许 `actual`、`guidance`、`restated`、`preliminary`，默认 `actual`。
- 必须至少提供 `source_ids`、`document_ids` 或 `evidence_ids` 之一，且来源必须能回链到治理后的事实源。

返回字段：

- `schema_id`：当前为 `financial-metrics-v1`。
- `count`：匹配指标总数。
- `metrics[]`：财务事实记录，包含 `metric_id`、`issuer_id`、`security_id`、`metric_name`、`period`、`value`、`period_start`、`period_end`、`unit`、`currency`、`statement_type`、`source_ids`、`document_ids`、`evidence_ids`、`confidence`、`fact_status` 和 `review_status`。
- `metric_counts` / `period_counts`：按指标和期间聚合的数量。

边界：研报、券商研究、新闻、人工参考、红色风险来源或任何 `source_type` 包含 research 的来源不能登记 `FinancialMetric`。研报里的盈利预测、目标价和估值方法应进入 `ReportForecast` / `ReportViewpoint`，只有经公告、财报、监管披露或其他治理事实源回链后的实际财务数据才进入 `FinancialMetric`。

#### `GET|POST /api/company-profiles/field-assertions`

查询公司画像字段级事实断言。兼容别名：`GET|POST /api/company-database/profile-field-assertions`。

请求字段：

- `issuer_id` / `issuer_ids` / `symbols` / `symbol` / `ticker` / `q`：目标公司过滤字段。
- `field_name`：可选；只查询某个画像字段。
- `security_id`：可选；按证券过滤。
- `source_policy` / `fact_status` / `review_status` / `assertion_status`：可选；按断言状态过滤。
- `limit`：返回上限，默认 100。

返回字段：

- `schema_id`：当前为 `company-profile-field-assertions-v1`。
- `count`：匹配断言总数。
- `status_counts` / `review_status_counts`：按断言状态和复核状态聚合的数量。
- `conflict_count` / `superseded_count`：待复核冲突候选和已被替代断言数量。
- `assertions[]`：字段级事实记录，包含 `assertion_id`、`issuer_id`、`field_name`、`value`、`source_ids`、`document_ids`、`evidence_ids`、`confidence`、`source_policy`、`fact_status`、`review_status`、`assertion_status`、`conflicts_with`、`resolved_by`、`extraction_method`、`created_at` 和 `updated_at`。
- `assertions[].conflicting_assertions[]`：冲突旧断言摘要，包含旧断言 ID、字段、旧值、来源、证据、置信度和状态，用于 UI 新旧值对比。
- `assertions[].review_recommendation`：本地复核辅助建议，包含 `recommended_action`、`candidate_score`、`best_conflict_score`、`source_priority_rank`、`freshness_score` 和 `reason`。该建议只用于人工复核排序，不会自动替换字段。

边界：字段断言是本地公司数据库 provenance，不是投资建议，不连接券商，不触发真实交易。

#### `POST /api/company-profiles/field-assertions/review`

复核公司画像字段断言。兼容别名：`POST /api/company-database/profile-field-assertions/review`。

请求字段：

- `assertion_id`：单条复核时必填；要复核的字段断言。
- `assertion_ids`：批量复核时使用；与 `assertion_id` 二选一。批量复核会逐条应用相同 `action` 和 `note`。
- `action`：必填；允许 `approve`、`supersede`、`reject`。
- `supersedes`：可选；手工指定被替代的断言 ID。系统也会读取当前断言的 `conflicts_with`。
- `note`：可选；复核说明。

返回字段：

- `schema_id`：当前为 `company-profile-field-assertion-review-v1`。
- `status`：单条固定为 `reviewed`；批量固定为 `reviewed_batch`。
- `action`：实际复核动作。
- `assertion`：复核后的断言。
- `reviewed_count` / `results[]`：批量复核时返回，表示处理数量和逐条结果。
- `superseded_assertion_ids`：被替代的旧断言。
- `changed_assertion_ids`：本次复核改动的断言 ID。

动作语义：

- `approve` / `supersede`：把当前断言置为 `active` / `approved`，应用字段值到 `Issuer` 和 `CompanyProfile`，并把 `conflicts_with` 或 `supersedes` 指向的旧断言置为 `superseded`。
- `reject`：把当前断言置为 `rejected`，不修改公司画像字段。

边界：复核只更新本地公司数据库字段 provenance 和画像事实字段，不生成投资建议，不连接真实券商，不触发自动交易。

#### `POST /api/company-database/material-inbox/ingest`

T-467 工作台入口，用于把本机已经下载或手工保存的公司官网、公司 IR、官方披露、交易所或监管材料送入公司数据库。该接口只读取本地 `*.manifest.json` sidecar 和对应文件，默认 dry-run；不会下载外部数据，也不会按文件名猜公司。

请求字段：

- `root_path`：可选；本地 inbox 目录。为空时使用 `AI_QUANT_COMPANY_MATERIAL_INBOX`，再回退到 `AI_QUANT_HOST_COMPANY_MATERIAL_ROOT/inbox`。
- `manifest_glob`：可选；默认 `*.manifest.json`。
- `extensions`：可选；允许读取的本地文件扩展名，默认 `.txt`、`.md`、`.html`、`.htm`。
- `scan_limit` / `limit`：可选；扫描上限，默认 1000，最大 10000。
- `execute`：可选；默认 `false`。仅 `true` 时写入 source/document/evidence/profile field assertion。
- `dry_run`：可选；为 `true` 时强制预览，不写库。
- `fields`：可选；画像字段白名单。
- `require_evidence`：可选；默认 `true`。
- `refresh_existing`：可选；默认 `false`。

返回字段：

- `schema_id`：当前为 `company-material-inbox-ingest-v1`。
- `status`：`dry_run`、`executed` 或 `failed`。
- `totals`：manifest、planned、invalid、source/document/evidence/profile field 计数。
- `items[]`：每条 manifest 的计划、执行或拒绝结果。
- `source_rules`：允许和拒绝的 source/document 类型。
- `usage_boundary`：固定为本地公司官方/IR 材料补库边界。

执行语义：

- `execute=true` 后，每条有效 manifest 会按需注册 `Source`、写入 `Document`、抽取 `Evidence`，再调用画像字段抽取生成或更新 `CompanyProfileFieldAssertion`。
- 返回的 `totals.sources_registered`、`documents_ingested`、`evidence_extracted`、`profile_fields_updated` 和 `profile_field_assertions_planned_or_written` 用于确认材料是否真正进入公司事实数据库。
- `dry_run=true` 优先级高于 `execute=true`；dry-run 只返回计划，不写入任何 source、document、evidence 或字段断言。

边界：

- 研报、券商研究、新闻、manual reference、未知类型和 `training_allowed=true` 记录会被标记 invalid，不进入事实字段链路。
- 该接口是本地公司事实数据库补库入口，不训练模型，不生成投资建议，不连接真实券商，不触发自动交易。

#### `scripts/company_material_inbox_ingest.py`

T-461 本地脚本，用于把已经下载或手工保存的公司官网、公司 IR、官方披露材料送入公司数据库。它不是新后端服务，不访问外网，不抓取网页；只扫描本机目录中的 `*.manifest.json` sidecar 和对应文本/HTML/Markdown 文件。

默认 dry-run：

```bash
python3 scripts/company_material_inbox_ingest.py --root-path /path/to/company_materials/inbox
```

执行写入：

```bash
python3 scripts/company_material_inbox_ingest.py --root-path /path/to/company_materials/inbox --execute
```

执行链路：

1. 读取 manifest 并校验来源边界。
2. 调用 `POST /api/ingestion/sources` 注册缺失 source。
3. 调用 `POST /api/ingestion/documents` 登记本地文本为 `Document`。
4. 调用 `POST /api/evidence/extract` 生成证据回链。
5. 调用 `POST /api/company-database/profile-fields/extract` 写入画像字段和 `CompanyProfileFieldAssertion`。

最小 manifest：

```json
{
  "issuer_id": "issuer_001",
  "security_id": "sec_001",
  "source_id": "local_demo_ir",
  "source_type": "company_ir",
  "document_type": "official_business_overview",
  "source_uri": "https://company.example.com/investors/profile",
  "file_path": "demo-ir-profile.txt",
  "title": "Demo IR profile",
  "language": "en",
  "published_at": "2026-06-25",
  "rights_tag": {
    "license_class": "public_company_ir_reference",
    "training_allowed": false,
    "redistribution_allowed": false,
    "display_use": "allowed",
    "non_display_use": "restricted",
    "derived_data_use": "restricted"
  }
}
```

允许来源：`company_ir`、`company_official`、`official_public`、`issuer_disclosure`、`exchange_disclosure`、`regulatory`、`public_company_disclosure`。

允许文档：`annual_report`、`10-K`、`10-Q`、`8-K`、`20-F`、`6-K`、`prospectus`、`registration_statement`、`company_announcement`、`official_product_page`、`official_business_overview`、`official_governance_page`、`presentation`、`transcript`、`webcast`。

拒绝边界：`research_report`、`broker_research`、`local_reference`、`manual_reference`、`news`、`curated_public_profile`、`training_allowed=true`。这些记录不会注册 source/document，不会生成 evidence，也不会写入公司事实字段或字段断言。

输出 artifact 默认为 `artifacts/company-material-inbox-ingest.json`，分类为 `local-only`，只用于本机补库审计，不可作为非本机生产发布证据。

#### `GET|POST /api/company-profiles/coverage/audit`

输出公司画像深字段覆盖率，用于回答“公司数据库还缺哪些字段、应该从哪些受治理来源补齐”。该接口只读本地记录，不触发外部下载，不写入画像，不把研报观点升级为事实源。

兼容别名：`GET|POST /api/company-database/profile-field-coverage/audit`。

请求字段：

- `issuer_ids` / `symbols` / `symbol` / `ticker` / `q`：目标公司解析字段，复用公司数据库目标解析规则。
- `limit`：目标公司数量上限，默认 100。
- `required_fields`：可选；只审计指定字段，如 `["legal_name", "business_summary", "authorized_documents"]`。
- `include_optional`：可选；为 `true` 时增加 `figi`、`isin`、`listing_date`、`gross_margin`、`cash`、`debt` 等字段。
- `require_evidence`：可选；为 `true` 时 identity/business/financial/source evidence 类事实字段必须有官方/公开证据回链才算 present。
- `include_research_opinion_slots`：默认 `true`；为 `false` 时研报覆盖、结构化观点和分析师覆盖槽位不计入覆盖率。

返回字段：

- `schema_id`：当前为 `company-profile-deep-field-coverage-v1`。
- `required_fields` / `field_missing_counts`：本次审计字段和字段级缺失统计。
- `companies[].field_coverage_score`、`coverage_level`、`missing_fields`：公司级字段覆盖率。
- `companies[].fields[field]`：字段状态，包含 `group`、`present`、`source_records`、`evidence_ids`、`assertion_ids`、`missing_reason` 和 `source_policy`。
- `companies[].research_tasks`：缺失字段的补齐任务建议，列出推荐来源类型。
- `source_plan`：字段组到优先来源的映射，包括官方披露、公司 IR、交易所/监管目录、公开行情、已治理本地记录和人工参考边界。
- `rules.research_reports`：固定为 `opinion_and_attention_slots_only_not_fact_source`。

字段组：

- `identity`：`legal_name`、`display_name`、`aliases`、`country`、`region`、`sector`、`industry`、`identifiers`。
- `listing`：`security_ids`、`tickers`、`exchange`、`market`、`currency`、`figi`、`isin`、`security_type`、`status`、`listing_date`。
- `business`：`business_summary`、`products`、`company_details`。
- `market_snapshot`：`as_of_date`、`close`、`volume`、`amount`、`valuation_metrics`。
- `financial_snapshot`：`period`、`revenue`、`net_income`、`gross_margin`、`cash`、`debt`。
- `source_evidence`：`source_ids`、`authorized_documents`、`field_evidence_ids`、`evidence_backlinks`。
- `coverage_opinion`：`research_report_count`、`structured_report_count`、`report_viewpoint_count`、`analyst_count`、`latest_report_at`。
- `workflow_feedback`：`latest_event_at`、`company_event_count`、`relationship_count`、`open_observation_count`、`analysis_conclusion_count`。
- `quality`：`profile_coverage`、`missing_fields`、`event_backlink_rate`、`relationship_backlink_rate`。

边界：`research_report`、`broker_research`、`local_reference`、`manual_reference` 和 `curated_public_profile` 不满足事实字段；研报只满足 coverage/opinion 字段，人工参考只能生成补齐计划或待复核线索。

#### `POST /api/company-database/build`

以公司数据库为中心，把已有原始记录物化为可展示、可复盘的公司情报底座。该接口不下载外部资料，不创建真实订单，不把研报当事实源；它只使用本地已有 `Issuer`、`Security`、`MarketDataPoint` 和 `ResearchReportAsset`，生成或预览 `CompanyProfile`，并把能通过 ticker/公司名匹配的本地研报挂到目标公司。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码，例如 `AAPL`、`600519`。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 20。
- `report_match_limit`：每家公司研报匹配上限，默认 100。
- `structure_reports`：可选；为 `true` 时对已匹配研报调用结构化入口。
- `structure_report_limit`：结构化研报数量上限，默认 20。
- `execute`：默认 `false`；为 `true` 时才写入公司画像和研报绑定。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `status`：`dry_run` 或 `executed`。
- `target_count`：解析到的目标公司数量。
- `profiles_planned` / `profiles_saved`：计划或已保存的公司画像数量。
- `research_reports_matched` / `research_reports_bound`：匹配和实际绑定的研报数量。
- `structure_result`：可选研报结构化结果。
- `companies`：每家公司画像覆盖率、缺失字段、证券和样本研报。

研报绑定是启发式结果，`asset_binding.review_status` 默认 `needs_review`；后续事实层仍需公告、财报、监管披露、公司 IR 或其他可信来源回链。

#### `POST /api/company-database/batch/build`

批量编排公司数据库构建链路，用于把观察池、重点股票清单或市场范围内的一批公司分批补齐。该接口默认 dry-run，只使用本地已有数据，不下载外部资料，不连接真实券商。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 100。
- `batch_size`：每批公司数量，默认 20。
- `report_match_limit`：每家公司研报匹配上限，默认 100。
- `structure_reports`：默认 `false`；为 `true` 时调用研报结构化。
- `structure_report_limit`：每批结构化研报数量上限，默认 20。
- `build_events` / `build_relationships` / `build_workflow`：默认 `true`，分别构建事件、关系和观察反馈闭环。
- `include_market_data` / `include_research_coverage` / `include_disclosures` / `include_structured_disclosures`：默认 `true`，透传给事件构建器。
- `include_listings` / `include_institution_coverage` / `include_disclosure_candidates`：默认 `true`，透传给关系构建器。
- `record_run`：默认随 `execute` 为 `true`；dry-run 需要显式传 `record_run=true` 才持久化运行记录。
- `run_id`：可选；调用方指定运行记录 ID，否则系统生成 `cdb_run_*`。
- `resume_run_id`：可选；基于已有 `CompanyDatabaseBuildRun` 重放。默认对 `failed`/`partial` run 使用 `remaining` 模式，只处理未完成公司；可用 `retry_failed=false` 或 `resume_mode=all` 重跑全部目标。
- `retry_failed`：可选；配合 `resume_run_id` 使用，默认 `true`。
- `resume_mode`：可选；`remaining` 或 `all`。
- `execute`：默认 `false`；为 `true` 时才落库。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划。

返回字段：

- `status`：`dry_run`、`executed`、`failed`、`partial` 或 retry 包装响应中的当前重放状态。
- `issuer_count` / `batch_count` / `batch_size`：目标公司和批次数。
- `totals`：画像、研报绑定、事件、关系、观察、结论和反馈的计划/创建汇总。
- `coverage_before` / `coverage_after`：同一目标范围补库前后的覆盖率审计结果。
- `run_id` / `run_recorded` / `run`：运行 ID、是否已持久化和运行记录快照。
- `batches`：每批的 `database_result`、`events_result`、`relationships_result` 和 `workflow_result`。

运行记录写入 `CompanyDatabaseBuildRun`，包含 actor、状态、目标公司、目标代码、retry/resume 关联、attempt、idempotency key、已完成公司、跳过公司、批次数、构建选项、totals、覆盖率前后、批次明细和 `usage_boundary=company_database_build_run_is_local_research_operations_history_no_live_trading`。该接口是本机补库编排入口；失败时会记录 `failed` 或 `partial` run，便于后续基于本地 run history 重放。

#### `GET|POST /api/company-database/batch/runs`

查询公司数据库批量补齐运行历史。该接口只读本地 `CompanyDatabaseBuildRun` 记录，不触发补库、不下载外部资料、不连接真实券商。

请求字段：

- `issuer_id`：可选；只返回包含该公司主体的运行。
- `run_id`：可选；只返回指定运行。
- `status`：可选；`dry_run`、`executed`、`failed` 或 `partial`。
- `limit`：返回数量上限，默认 20，最大 200。
- `include_batches`：默认 `false`；为 `true` 时返回完整批次明细。默认瘦身返回会清空 `batches` 并标记 `batch_details_omitted`。

返回字段：

- `count`：过滤后的运行记录总数。
- `runs`：按 `completed_at` 倒序排列的运行记录。
- `include_batches`：本次是否返回完整批次明细。
- `usage_boundary`：固定为本地操作历史，不是交易或生产发布证据。

#### `POST /api/company-database/batch/runs/{run_id}/retry`

从已持久化的 `CompanyDatabaseBuildRun` 重放补库。该接口只读取本地 run history 和本地公司数据库，不自动下载外部资料，不连接真实券商，不触发真实交易。

请求字段：

- `execute` / `dry_run`：默认 dry-run；`execute=true` 才落库。
- `record_run`：默认 `true`；重放结果默认写入新的 `CompanyDatabaseBuildRun`。
- `resume_mode`：`all` 或 `remaining`。未传时，`failed`/`partial` 源 run 默认 `remaining`，其他状态默认 `all`。
- 可覆盖字段：`batch_size`、`report_match_limit`、`structure_reports`、`structure_report_limit`、`build_events`、`build_relationships`、`build_workflow`、`event_limit`、`relationship_limit`、`workflow_link_limit` 等安全构建选项。
- `run_id` / `idempotency_key`：可选；指定新 run ID 或幂等键。

返回字段：

- `source_run_id` / `new_run_id`：源 run 和本次新 run。
- `resume_mode` / `attempt`：重放模式和尝试次数。
- `retry_issuer_ids` / `skipped_issuer_ids`：本次处理与跳过的公司主体。
- `result`：嵌套的批量补库结果。
- `usage_boundary`：固定为本地补库重放，不是交易记录或生产发布证据。

#### `GET|POST /api/company-database/coverage/trends`

从已持久化的 `CompanyDatabaseBuildRun.coverage_before` / `coverage_after` 快照生成覆盖率趋势报告。该接口不执行补库、不下载外部资料、不连接真实券商；它只用于判断公司数据库补齐是否让画像、事件、关系、研报观点、观察结论和模拟反馈覆盖变好。

请求字段：

- `issuer_id`：可选；只统计包含该公司主体的运行。
- `status`：可选；`dry_run`、`executed`、`failed` 或 `partial`。
- `limit`：运行数量上限，默认 50，最大 500。
- `write_artifact` / `record_artifact`：默认 `false`；为 `true` 时把趋势报告写入本地 JSON。
- `artifact_path`：可选；默认 `artifacts/company-database-coverage-trends.json`。该 artifact 固定为 `local-only`，不得作为非本机 production release gate 证据。

返回字段：

- `run_count`：纳入趋势计算的运行数量。
- `summary`：首尾覆盖率、累计覆盖率变化、最新缺失数、累计缺失变化、改善/恶化/不变运行数。
- `trend_rows`：按时间升序排列的运行趋势行，包含 `run_id`、状态、目标公司、批次、覆盖率前后、覆盖变化、缺失项前后、分项缺失变化、改善/恶化 section 和构建 totals。
- `artifact`：当写入本地 artifact 时返回路径、分类、producer、敏感数据标记和非 production 证据边界。
- `usage_boundary`：固定为本地研究操作历史，不是交易记录或生产发布证据。

#### `GET|POST /api/company-database/coverage/audit`

审计公司数据库覆盖率，输出每家公司哪些层已经可用、哪些层仍为空，用于指导下一轮补库和 UI 缺口提示。该接口只读本地记录。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 100。

返回字段：

- `issuer_count`：纳入审计的公司数量。
- `average_coverage_score`：覆盖率平均分。
- `required_sections`：审计的核心层，包括画像、证券、行情、财务、文档、披露事件、公司事件、关系、研报、结构化观点、观察、结论和模拟反馈。
- `missing_counts`：每个 section 缺失的公司数量。
- `companies`：逐公司 `coverage_score`、`coverage_level`、`missing_sections`、`section_available` 和对象计数。

覆盖率分数只表示本地数据库完整度，不代表投资价值或事实质量；事实质量仍依赖来源、证据回链和人工复核。

#### `POST /api/company-database/quality/reconcile`

对公司数据库中的 `CompanyEvent` 和 `CompanyRelationship` 做本地质量归并：识别重复事件、重复关系、实体别名归并候选，并计算来源质量评分。该接口只使用本地记录，不下载外部资料，不删除源记录，不生成投资建议。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 100。
- `include_events`：默认 `true`，识别并可合并重复公司事件。
- `include_relationships`：默认 `true`，识别并可合并重复公司关系。
- `merge_duplicates`：默认 `true`，启用重复归并计划；`execute=false` 时只返回计划。
- `score_sources`：默认 `true`，对事件/关系写入或返回 `metadata.source_quality`。
- `execute`：默认 `false`；为 `true` 时才把重复项标记为 `merged`、把关系重复项置为 `inactive`、并写入 source quality。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `schema_id`：当前为 `company-database-quality-reconciliation-v1`。
- `totals.event_duplicate_groups` / `event_duplicates` / `events_merged`。
- `totals.relationship_duplicate_groups` / `relationship_duplicates` / `relationships_merged`。
- `totals.entity_merge_candidates`：关系对象名称或 ID 可归并的候选数量。
- `totals.source_quality_scored`：本次计算 source quality 的事件/关系记录数。
- `companies[].event_duplicate_groups[]`：包含 `dedup_key`、`canonical_id`、`duplicate_ids`、`event_ids`、`reason` 和 canonical source quality。
- `companies[].relationship_duplicate_groups[]`：包含 `dedup_key`、`canonical_id`、`duplicate_ids`、`relationship_ids`、`entity_canonical_key`、`entity_names`、`entity_merge_candidate` 和 canonical source quality。
- `companies[].source_quality[]`：逐事件/关系来源质量，包含 `record_type`、`record_id`、`score`、`level`、`factors` 和 `source_types`。

行为：

- 事件去重 key 以 `issuer_id/security_id/event_type/occurred_date` 为基础，优先使用 `disclosure_event_id`，其次使用 `document_ids`、`evidence_ids` 或归一化摘要。
- 关系去重 key 以主体、关系类型、方向和归一化对象实体名为基础；`customer_candidate` 与 `supplier_candidate` 不会互相合并。
- execute 时保留 canonical 记录，重复事件设置 `review_status=merged`；重复关系设置 `review_status=merged`、`relationship_status=inactive`，并在 canonical 记录上合并 `source_ids`、`document_ids`、`evidence_ids`、`metadata.merged_from` 和 `metadata.entity_aliases`。
- source quality 是本地来源/证据/复核质量分，不是投资评级、买卖建议或公司质量判断。官方/监管/公司 IR 且有 evidence/document 回链的记录得分较高；研报、manual/local reference、news 或 opinion signal 得分较低，且不会被升级为事实源。

#### `GET|POST /api/data-health/runs/summary`

统一运行摘要 read model。该接口只聚合现有运行记录和本地 artifact，不创建新运行、不迁移 schema、不改变原始 run payload。

请求字段：

- `run_family` / `run_families`：可选；限定 `ingestion_job`、`ingestion_schedule_run`、`company_database_build_run`、`company_package_import_run`、`company_intelligence_cycle_run`、`material_inbox_pending`、`daily_data_update_pipeline`、`personal_intelligence_refresh`。
- `status` / `normalized_status`：可选；按原状态或规范化状态过滤。
- `symbol` / `ticker` / `code`：可选；按标的过滤支持 symbol 的 run。
- `issuer_id`：可选；按本地主体过滤。
- `limit`：默认 100，最大 500。

返回字段：

- `schema_id`：当前为 `data-health-run-summary-v1`。
- `summary`：运行总数、成功/部分/失败数量、待处理数和最近成功/失败时间。
- `runs[]`：统一摘要行，包含 `run_family`、`run_id`、`domain`、`status`、`normalized_status`、时间、目标公司/标的、计数、错误、artifact、下一步和 `detail_ref`。
- `local_only=true` / `acceptable_for_non_local_release=false`：本地运行摘要不能作为非本机生产发布证据。
- `usage_boundary`：固定声明本地 read model、无 schema migration、无真实交易。

#### `GET|POST /api/data-health/summary`

个人研究视角的数据来源健康中心。该接口从统一 run summary、公开行情、研报资产、披露事件、公司材料待办、公司数据库和 paper-only 闭环反馈中派生可读状态。

返回字段：

- `schema_id`：当前为 `data-health-summary-v1`。
- `summary`：来源数、状态分布、失败数、待处理数和下一步数量。
- `sources[]`：来源健康行，包含 `source_key`、`domain`、`label`、`status`、最近成功/失败、失败数、待处理数、freshness、last artifact、下一步、证据和边界。
- `run_summary` / `run_count`：底层统一运行摘要概览。
- `local_only=true` / `acceptable_for_non_local_release=false`。

边界：该接口是本地数据健康和来源追溯视图，不下载外部数据，不训练，不生成交易信号，不连接券商。

#### `POST /api/company-database/events/build`

为已有公司数据库构建事件时间线。该接口只使用本地已有数据，不下载外部资料。当前事件来源包括已入库公开披露/filing 事件、披露摘要/证据/非研报文档正文、公开/已提供行情快照和已绑定本地研报覆盖记录；研报覆盖事件表示“该公司进入研报视野”这一关注度事实，事件 `fact_status=opinion_signal`，不得把研报观点升级为公司事实。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 20。
- `event_limit`：每家公司事件数量上限，默认 100。
- `include_market_data`：默认 `true`，生成最新公开行情事件。
- `include_research_coverage`：默认 `true`，生成已绑定研报覆盖事件。
- `include_disclosures`：默认 `true`，从已有 `DisclosureEvent` 生成官方披露事件，`fact_status=verified`。
- `include_structured_disclosures`：默认 `true`，从官方披露摘要、`DisclosureEvent.evidence_ids` 对应 evidence 文本和非研报 `Document.body` 中抽取细粒度事件候选。当前支持 `earnings_result`、`management_change`、`litigation_regulatory`、`major_order_contract`、`capacity_supply_demand`、`policy_impact`。这些事件保留官方披露/证据回链，`fact_status=verified`，但分类本身为 `review_status=needs_review`。
- `execute`：默认 `false`；为 `true` 时才写入 `CompanyEvent`。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `status`：`dry_run` 或 `executed`。
- `events_planned` / `events_created`：计划或实际创建事件数。
- `include_structured_disclosures`：本次是否启用官方披露正文细粒度分类。
- `companies`：每家公司事件数量、市场事件数、官方披露事件数、研报覆盖事件数、结构化披露事件数和样本事件 ID。

结构化披露事件的 `metadata.source_layer=official_disclosure_text_classification`，会记录 `classification_rule`、`matched_terms`、`classification_status=candidate_needs_review` 和 `rights_boundary=official_disclosure_fact_with_classification_review`。后续新闻、官网、行业政策网页和更强实体抽取仍应通过该事件层扩展，并要求来源治理、证据回链和人工复核。

#### `POST /api/company-events/{event_id}/review`

审核公司事件候选。该接口用于把结构化披露事件、事件分类候选或重复事件纳入可信时间线、拒绝误抽取、合并重复事件或修正事件分类；不会把研报观点升级为公司事实，也不会触发真实交易。

请求字段：

- `action` / `review_action`：必填；`approve`、`reject`、`merge` 或 `reclassify`。
- `reason`：可选；审核说明。
- `reviewed_by`：可选；默认使用请求 actor。
- `confidence`：可选；`approve` 时用于提高置信度，默认至少提升到 0.8。
- `fact_status`：可选；只有显式传入时才改写事实状态。
- `target_event_id`：`merge` 必填；目标事件 ID。
- `event_type` / `new_event_type`：`reclassify` 必填；修正后的事件分类。

行为：

- `approve`：设置 `review_status=approved`、`metadata.candidate_status=approved`，并记录审核人和审核时间。
- `reject`：设置 `review_status=rejected`、`metadata.candidate_status=rejected`。
- `reclassify`：更新 `event_type`，在 `metadata.event_type_history` 中保留旧分类和新分类，默认设置 `review_status=approved`。
- `merge`：源事件设置为 `review_status=merged`，并把 source/document/evidence/impact tags 回链合并到目标事件。

所有审核动作都会在 `metadata.review_history` 中保留审核时间、审核人、动作、理由、旧分类、旧事实状态和旧置信度。

#### `POST /api/company-events/review`

批量复核公司事件候选。兼容别名：`POST /api/company-database/events/review`。该接口面向公司数据库补库后的人工时间线质量处理，仍只更新本地事件 provenance，不连接真实券商、不生成投资建议。

请求字段：

- `event_ids`：批量复核时必填；事件 ID 列表。
- `event_id`：单条复核兼容字段；可与 `event_ids` 合并去重。
- `action` / `review_action`：必填；`approve`、`reject`、`merge` 或 `reclassify`。
- `reason`：可选；批量复核备注，会进入每条事件的 `metadata.review_history`。
- `target_event_id`：`merge` 时必填；多条合并会使用同一目标事件。
- `event_type` / `new_event_type`：`reclassify` 时必填；多条改分类会使用同一新分类。

返回字段：

- `schema_id`：`company-event-batch-review-v1`。
- `reviewed_count`：本次复核的事件数量。
- `events[]`：复核后的事件行，包含 `source_quality` 和 `review_recommendation`。
- `changed_event_ids`：被修改的事件 ID。
- `usage_boundary`：固定声明为本地时间线 provenance 更新，不涉及真实交易。

`GET|POST /api/company-events` 返回的每条事件会补充 `source_quality` 与 `review_recommendation`。推荐字段只用于人工排序和复核提示，不会自动批准事件，也不会改变事实/观点边界。

#### `POST /api/company-database/relationships/build`

为已有公司数据库构建最小关系层。该接口只使用本地已有主体、证券、已绑定研报资产、公开披露证据和显式提供的本地结构化股权行，不下载外部资料。当前关系来源包括公司到上市证券的 `listed_security` 关系、公司到研报机构的 `institution_coverage` 关系、从公开披露/证据文本中抽取的 `customer_candidate`、`supplier_candidate`、`partner_candidate`、`subsidiary_candidate`、`shareholder_candidate`、`controller_candidate`、`investee_candidate` 候选关系，以及从 `structured_ownership_relationships` 输入生成的股东、实控人、子公司和参股候选关系。研报机构覆盖关系表示“该机构覆盖/发布过该公司相关研报”，不代表客户、供应商、竞争、股权或投资建议事实；公开披露和结构化股权候选关系默认仍需人工复核。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 20。
- `relationship_limit`：每家公司关系数量上限，默认 100。
- `include_listings`：默认 `true`，生成公司到证券的上市关系。
- `include_institution_coverage`：默认 `true`，生成公司到研报机构的覆盖关系。
- `include_disclosure_candidates`：默认 `true`，从已有 `DisclosureEvent`、`Evidence` 和非研报 `Document` 文本中抽取候选关系。
- `include_structured_ownership`：默认 `true`，当请求提供结构化股权行时生成候选关系。
- `structured_ownership_relationships` / `ownership_relationships`：可选数组；每行可包含 `issuer_id`、`security_id`、`ticker`/`symbol`、`kind`/`relationship_type`、`entity_name`/`holder_name`/`controller_name`/`subsidiary_name`/`investee_name`、`object_id`、`share_ratio`、`ownership_pct`、`voting_pct`、`report_period`、`source_id`、`source_ids`、`document_ids`、`evidence_ids`、`source_table` 和 `metadata`。`kind=top_shareholder/shareholder/holder` 归一为 `shareholder_candidate`，`actual_controller/controller/beneficial_owner` 归一为 `controller_candidate`，`subsidiary` 归一为 `subsidiary_candidate`，`investee/equity_investment/associate` 归一为 `investee_candidate`。
- `ownership_csv` / `ownership_tsv` / `ownership_table_text` / `shareholder_table_text` / `controller_table_text` / `subsidiary_table_text` / `investee_table_text`：可选本地表格文本，支持 CSV、TSV 和 Markdown 管道表；中英文字段名会归一到结构化股权行，例如 `股票代码`、`关系类型`、`股东名称`、`持股比例`、`报告期`、`来源`。
- `structured_ownership_tables` / `ownership_tables`：可选数组；每项可包含 `table_text`、`csv`、`tsv`、`markdown`、`default_kind`、`source_table` 和 `source_id`。
- `ownership_file_paths` / `ownership_files`：可选本地文件路径或文件说明数组；每项可以是路径字符串，也可以包含 `file_path`、`default_kind`、`source_table`、`source_id`、`encoding`。相对路径按 `ownership_root_path` 解析。
- `ownership_root_path`：可选；本地 ownership 文件根目录，默认当前工作目录。仅读取显式指定文件，不扫描目录。
- `ownership_file_extensions`：可选；允许扩展名，默认 `.csv`、`.tsv`、`.txt`、`.md`。
- `ownership_file_limit` / `ownership_file_max_bytes`：可选；默认最多 20 个文件、单文件 1MB，上限分别为 100 个文件和 5MB。
- `execute`：默认 `false`；为 `true` 时才写入 `CompanyRelationship`。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `status`：`dry_run` 或 `executed`。
- `relationships_planned` / `relationships_created`：计划或实际创建关系数。
- `ownership_file_inputs`：本地 ownership 文件解析摘要，包含路径、状态、行数和错误列表。
- `companies`：每家公司关系数量、上市关系数、机构覆盖关系数、公开披露候选关系数、结构化股权候选关系数和样本关系 ID。

公开披露候选关系使用 `review_status=needs_review`、`relationship_status=unknown`，并在 metadata 中记录 `candidate_status=candidate`，同时保留 `disclosure_event_id`、`document_ids`、`evidence_ids` 和 `source_ids`。客户、供应商、竞争、股权、上下游和人员关系后续仍需人工复核、来源质量评分和更细粒度抽取，不能从研报观点直接推断为事实。

公司情报工作台的后台维护区提供“股权表导入”入口，直接调用本接口的 `ownership_root_path`、`ownership_file_paths`、`ownership_file_default_kind` 和 `include_structured_ownership=true` 路径。该入口默认 dry-run 预览，显式执行后才写入待复核 `CompanyRelationship` 候选。

本地 ownership 表格可通过脚本提交到同一接口，默认 dry-run。可显式指定文件：

```bash
python3 scripts/import_company_ownership_tables.py --base-url http://127.0.0.1:8000 --symbols DEMO --root-path /path/to/ownership --files demo-ownership.csv --output artifacts/company-ownership-table-import.json
```

也可扫描目录：

```bash
python3 scripts/import_company_ownership_tables.py --base-url http://127.0.0.1:8000 --symbols DEMO --root-path /path/to/ownership --glob "**/*ownership*.csv,**/*股权*.md" --output artifacts/company-ownership-table-import.json
```

当未传 `--symbols` 时，脚本默认会从文件名或相对路径推断目标代码，例如 `DEMO-ownership.csv`、`600519.SH-股权.md` 或 `sh600000_十大股东.csv`；可用 `--no-infer-symbols-from-path` 关闭。

批量导入可使用 JSON manifest，记录每个文件的来源和默认类型：

```json
{
  "files": [
    {
      "file_path": "600519.SH-股权.csv",
      "symbol": "600519",
      "default_kind": "shareholder",
      "source_id": "annual_report_2026",
      "source_table": "top_ten_shareholders"
    }
  ]
}
```

然后运行：

```bash
python3 scripts/import_company_ownership_tables.py --base-url http://127.0.0.1:8000 --root-path /path/to/ownership --manifest ownership.manifest.json --output artifacts/company-ownership-table-import.json
```

也可以先扫描目录生成待编辑 manifest 草案，不调用 API：

```bash
python3 scripts/import_company_ownership_tables.py --root-path /path/to/ownership --glob "**/*ownership*.csv" --write-manifest-template ownership.manifest.json --default-source-id annual_report_2026 --default-kind shareholder
```

显式加 `--execute` 才会写入 review-required `CompanyRelationship` 候选。

#### `POST /api/company-database/ownership/manifest-template`

为本地 ownership 表生成待编辑 JSON manifest。该接口只扫描服务端本机目录，不下载外部资料，不写入关系候选；默认 dry-run 仅返回模板，`execute=true` 且提供 `output_path` 时才写入本地 JSON 文件。

请求字段：

- `root_path` / `ownership_root_path`：本地 ownership 表根目录。
- `files` / `file_paths` / `ownership_file_paths`：可选；显式文件列表，支持逗号分隔或数组。
- `glob` / `scan_patterns`：可选；逗号分隔 glob，例如 `**/*ownership*.csv,**/*股权*.md`。
- `scan_limit`：扫描上限，默认 100。
- `infer_symbols_from_path` / `infer_symbols`：默认 `true`，从文件名推断股票代码。
- `default_kind`：默认 `shareholder`。

公司情报 UI 的股权 manifest 预览表会把 `default_kind` 主显示映射为中文关系类型，例如 `shareholder` 显示“事实股东”；原始 `default_kind` 仍保留在高级 trace 和 manifest payload 中，供导入、脚本和审计追溯使用。
股权表导入预览/执行结果表的前三列只显示股权表名称、解析状态、候选关系数量和目标公司数量；`file_path`、`source_table`、`source_id`、原始状态和其他机器字段保留在最后一列的“股权表追溯”高级 trace 中，避免主视图被 raw 字段打断，同时不丢失导入审计证据。
- `default_source_id`：默认 `local_structured_ownership`。
- `default_source_table`：可选；为空时用文件名 stem。
- `output_path` / `manifest_path`：`execute=true` 时必填。
- `execute` / `dry_run`：默认 dry-run。

返回字段：

- `template`：`company-ownership-table-manifest-v1` 模板，包含 `root_path`、`defaults`、`files` 和 usage boundary。
- `file_count`：模板文件数。
- `written`：是否写入本地 JSON。
- `next_actions`：编辑 manifest 与导入股权表的后续动作。

#### `POST /api/company-relationships/{relationship_id}/review`

审核公开披露抽取出的候选关系。该接口用于把候选关系纳入可信图谱、拒绝误抽取或合并重复关系；不会从研报观点自动提升客户、供应商或竞争关系。

请求字段：

- `action` / `review_action`：必填；`approve`、`reject` 或 `merge`。
- `reason`：可选；审核说明。
- `reviewed_by`：可选；默认使用请求 actor。
- `confidence`：可选；`approve` 时用于提高置信度，默认至少提升到 0.8。
- `target_relationship_id`：`merge` 必填；目标关系 ID。

行为：

- `approve`：设置 `review_status=approved`、`relationship_status=active`、`metadata.candidate_status=approved`。
- `reject`：设置 `review_status=rejected`、`relationship_status=inactive`、`metadata.candidate_status=rejected`。
- `merge`：源关系设置为 `review_status=merged`、`relationship_status=inactive`，并把 evidence/document/source 回链合并到目标关系。

所有审核动作都会在 `metadata.review_history` 中保留审核时间、审核人、动作和理由。

#### `POST /api/company-relationships/review`

批量复核公司关系候选。兼容别名：`POST /api/company-database/relationships/review`。该接口面向公司数据库补库后的人工图谱质量处理，仍只更新本地关系 provenance，不连接真实券商、不生成投资建议。

请求字段：

- `relationship_ids`：批量复核时必填；关系 ID 列表。
- `relationship_id`：单条复核兼容字段；可与 `relationship_ids` 合并去重。
- `action` / `review_action`：必填；`approve`、`reject` 或 `merge`。
- `reason`：可选；批量复核备注，会进入每条关系的 `metadata.review_history`。
- `target_relationship_id`：`merge` 时必填；多条合并会使用同一目标关系。

返回字段：

- `schema_id`：`company-relationship-batch-review-v1`。
- `reviewed_count`：本次复核的关系数量。
- `relationships[]`：复核后的关系行，包含 `source_quality` 和 `review_recommendation`。
- `changed_relationship_ids`：被修改的关系 ID。
- `usage_boundary`：固定声明为本地图谱 provenance 更新，不涉及真实交易。

`GET|POST /api/company-relationships` 返回的每条关系会补充 `source_quality` 与 `review_recommendation`。推荐字段只用于人工排序和复核提示，不会自动批准关系，也不会把研报观点升级为事实关系。

#### `POST /api/company-database/workflow/build`

为已有公司数据库构建最小研究反馈闭环。该接口从本地已有公司事件、公司关系、结构化研报观点和行情快照生成 `ObservationItem`、`AnalysisConclusion` 和 `SimulationFeedback`，让公司页能显示“观察任务 -> 分析结论 -> 模拟反馈”的可复盘骨架。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；目标股票代码列表或单个代码。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：目标公司数量上限，默认 20。
- `link_limit`：每家公司回链事件、关系、观点和证据数量上限，默认 5。
- `include_observations`：默认 `true`，生成观察任务。
- `include_conclusions`：默认 `true`，生成公司情报基线结论。
- `include_feedback`：默认 `true`，生成 watch-only 模拟反馈。
- `refresh_existing`：默认 `true`，已有基线记录存在时刷新事件、关系、观点和证据回链。
- `execute`：默认 `false`；为 `true` 时才写入对象。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `status`：`dry_run` 或 `executed`。
- `observations_planned` / `observations_created`：计划或已创建观察任务数。
- `conclusions_planned` / `conclusions_created`：计划或已创建分析结论数。
- `feedback_planned` / `feedback_created`：计划或已创建模拟反馈数。
- `observations_updated` / `conclusions_updated` / `feedback_updated`：已有基线记录被刷新次数。
- `companies`：每家公司生成对象 ID、已回链事件/关系/观点数量和证据缺口。

生成的结论类型为 `company_intelligence_baseline`，默认只是研究基线和复盘计划，不输出买卖建议。生成的反馈固定 `feedback_type=watch_only`、`paper_only=true`、`live_execution_allowed=false`、`broker_connected=false`；模型层仍会拒绝任何真实交易或券商连接字段。

#### `POST /api/simulation-feedback/performance/update`

使用本地最新行情更新 `SimulationFeedback.performance`，用于验证分析结论和观察任务是否有效。该接口只读取本地 `MarketDataPoint`，不连接真实券商，不创建订单，不修改真实持仓。

请求字段：

- `feedback_ids` / `feedback_id`：可选；指定反馈记录。
- `symbols` / `symbol` / `ticker`：可选；按公司或证券筛选反馈记录。
- `issuer_ids`：可选；按公司主体筛选。
- `limit`：更新数量上限，默认 100。
- `execute`：默认 `false`；为 `true` 时才写入 performance。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划，不落库。

返回字段：

- `status`：`dry_run` 或 `executed`。
- `feedback_planned` / `feedback_updated` / `feedback_skipped`：计划、已更新和跳过记录数。
- `feedback`：每条反馈的 entry price、最新价、最新行情日期、纸面收益率和持有天数。
- `paper_only=true`、`live_execution_allowed=false`：固定边界声明。

若反馈记录没有最新行情或有效 entry price，会被跳过并返回原因。若 entry price 为空但有最新行情，接口只初始化 paper baseline，不生成真实交易行为。

#### `POST /api/research-reports/realization/update`

用本地最新行情更新结构化研报目标价预测和观点兑现状态，并可同步重算相关分析师可靠性评分。研报仍是观点层和关注度信号；兑现更新只是复盘预测质量，不把研报升级为事实源或交易信号。

请求字段：

- `symbols` / `symbol` / `ticker`：可选；按公司或证券筛选。
- `issuer_ids`：可选；直接指定公司主体。
- `limit`：预测或观点处理数量上限，默认 500。
- `recompute_analyst_scores`：默认 `true`；执行模式下重算相关分析师可靠性。
- `execute`：默认 `false`；为 `true` 时才写入 forecast/viewpoint/score。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划。

返回字段：

- `forecast_planned` / `forecast_updated` / `forecast_skipped`：目标价预测计划、更新和跳过数量。
- `viewpoint_planned` / `viewpoint_updated` / `viewpoint_skipped`：观点兑现计划、更新和跳过数量。
- `analyst_scores_recomputed`：重算的分析师可靠性评分数量。
- `forecasts`：每条预测的目标价、最新价、误差和兑现状态。
- `viewpoints`：每条观点的目标价、最新价和兑现状态。
- `usage_boundary`：固定声明本地行情、观点层、非事实源、非交易信号边界。

当前实现以“最新收盘价是否达到目标价”作为最小兑现判定；后续应补目标价期限、评级方向准确率、盈利预测 actuals、相对基准收益和人工复盘解释。

#### `GET|POST /api/company-intelligence/{symbol}`

按股票代码聚合公司情报工作台视图。该接口是只读聚合层，不自动创建 issuer/security，不下载外部资料，不触发真实交易；如果本地没有该代码，会返回 `status=not_found`、缺失 section 和 `next_actions`，引导用户先运行单标的研究或手工登记主体。已存在本地档案时，接口会按 ticker/security/entity mapping 解析主体，并聚合公司画像、行情、公司行动、文档、证据、公司事件、披露事件、公司关系、关系图谱、研报资产、结构化研报、研报观点、预测、分析师可靠性、研究问答、观察任务、分析结论、模拟反馈和旧纸面执行兼容对象。

请求字段：

- `symbol`：路径参数；例如 `SPCX`、`AAPL`、`600000`。
- `limit`：每类明细最大返回数量，默认 20，最大 100。

返回字段：

- `status`：`available` 或 `not_found`。
- `resolution`：匹配到的 `issuer_ids`、`security_ids`、`mapping_ids`。
- `company_profile`：主体、证券、映射和覆盖摘要。
- `facts_and_events`：行情、公司行动、资料、证据和披露事件。
- `relationships`：公司关系、公司定位、13F/crowding、`relationship_context` 和 `/api/graph/query` 聚合图谱。`relationship_context` 是只读派生视图，按公司中心汇总产业链位置、同类公司、上游公司、下游公司、股东/持有人、股东关联公司、关系类型分组和动态图谱展开建议；它复用本地 `CompanyRelationship`、`CompanyPosition`、`IndustryChain`、`InstitutionalHolding` 和图谱边，不要求重建数据库。`relationship_context.summary.industry_related_companies_total` 是同类、上游和下游公司的合计，`relationship_context.ownership.approved_relationships` 放已批准且 active 的事实股权/控制/参股关系，且每条会输出 `holder_key` / `holder_name` 供同一事实股东网络展开；`relationship_context.ownership.relationship_candidates` 只放仍需复核的股权候选，`relationship_context.ownership.relationships` 保留全部 ownership 关系聚合，`relationship_context.ownership.approved_shareholder_related_companies` 用已批准事实股权关系按同一股东/持有人反推“该股东还关联哪些公司”，`relationship_context.ownership.shareholder_related_companies` 继续表示 13F/持仓记录推导的同一持有人网络；`relationship_context.summary.shareholder_related_companies_total` 是两者合计，公司情报 UI 顶部“股东关联”计数会显示该合计并拆出“事实 / 持仓”分项。`relationship_context.coverage_diagnostics` 按产业链位置、同类公司、上游、下游、股权/控制、`shareholder_network`（13F/持仓同一持有人网络）、`approved_shareholder_network`（已批准事实股东网络）和动态图谱边输出 `coverage_score`、`status`、`missing_required_layers`、`missing_optional_layers`、`diagnostics`、`industry_network_summary`、`shareholder_network_summary`、`next_actions` 与 `enhancement_actions`，用于判断多维关系链条还缺哪一层和下一步该补什么数据；其中 `next_actions` 覆盖全部 `missing_required_layers`，不是示例列表或截断列表；`enhancement_actions` 覆盖全部 `missing_optional_layers`，用于 13F/持仓同一持有人网络和已批准事实股东网络等增强层的机器可读补齐建议。每条 action 都包含 `target` 块，声明 `target_type`、`endpoint`、`method`、`ui_action`、`default_execute=false` 和 `usage_boundary`；股权相关层还包含 `review_endpoint` 和 `manifest_endpoint`，动态图谱层指向 `/api/graph/query`。`industry_network_summary` 汇总 `total`、`peers`、`upstream`、`downstream`、`chain_nodes`、`available` 和来源层，公司情报 UI 会把该汇总写入“同类/上游/下游”计数的 `data-network-total`、`data-network-part`、`data-chain-nodes` 和 title 追溯；`shareholder_network_summary` 汇总 `total`、`fact_network`、`holding_network`、`available` 和来源层，两个分项诊断仍保留各自 provenance，公司情报 UI 会把该汇总写入“股东关联”计数的 `data-network-total`、`data-fact-network`、`data-holding-network` 和 title 追溯。每条 `diagnostics[]` 都包含 `evidence` 来源口径，公司情报 UI 的关系链缺口行会展示全部未覆盖层、该来源口径，并把同 layer 的 `next_actions` 或 `enhancement_actions` 合并为按钮 target；因此必补层和增强层都会写入 `data-target-ui-action` 与 `data-evidence` 供追溯。`relationship_context.dynamic_graph.recommended_filters` 固定声明可用于动态图谱探索的过滤键，包括 `issuer_id`、`security_id`、`relationship_type`、`chain_id`、`chain_node_id`、`industry_direction`、`ownership_holder_key` 和 `institutional_holder_key`；`dynamic_graph.recommended_queries[]` 进一步给出可直接传给 `/api/graph/query` 的 `{label, query, reason}` 建议，包括公司中心图、产业链节点、关系类型和同一事实股东网络入口，公司情报 UI 会把前几条建议渲染为“图谱推荐入口”并复用 `open-relationship-graph` 点击机制。
- 关系类型显示：公司情报 UI 的“多维关系”、“关键事实”、“关系候选审核”、“知识图谱关系边”和图谱 inspector 相邻关系主表会把常见 `relationship_type` 显示为中文标签，例如 `industry_peer` -> “同类关系”、`upstream_of` -> “上游关系”、`shareholder` -> “事实股东”、`controller_candidate` -> “实控候选”、`customer_candidate` -> “客户候选”；raw 枚举仍保留在行级 `data-relationship-type`、`data-industry-relationship`、`data-filter-raw-value`、title 和高级 trace JSON 中，供动态图谱过滤、脚本验收和审计追溯使用。知识图谱画布边 label、关系边表的主题/发现文本和 inspector 相邻关系使用中文关系名，但 link `type`、`relationship_type` 和 raw graph payload 不改写。
- 产业链行级追溯：公司情报 UI 的“产业链位置 / 同类公司 / 上游公司 / 下游公司”行会额外写入 `data-industry-relationship`、`data-industry-direction`、`data-chain-id`、`data-chain-node-id`、`data-chain-node-ids`、`data-chain-node-label` 和 `data-position-id`，用于追溯每条产业链关系来自哪个链条、节点和方向，并与 `/api/graph/query` 的 `chain_id` / `chain_node_id` 过滤保持一致。点击这些行进入知识图谱时，UI 会把 `data-industry-direction` 保留为可见的 `industryDirection` 过滤 chip，明确当前图谱来自“同类 / 上游 / 下游 / 产业链位置”哪一类展开；chip 对用户显示中文方向，但 `data-filter-raw-value` 和 title 保留 `peer` / `upstream` / `downstream` / `position` 原始枚举。该字段是 UI 追溯状态，不改变后端查询语义。
- 产业链推荐入口：`relationship_context.dynamic_graph.recommended_filters` 会声明 `industry_direction`，`recommended_queries[]` 在存在同类、上游或下游关系时，会额外生成方向级产业链推荐，`query.industry_direction` 取值为 `peer` / `upstream` / `downstream`，并与 `relationship_type`、`chain_id`、`chain_node_id` 一起由公司情报 UI 渲染为“图谱推荐入口”。点击后 UI 会保留同一个 `industryDirection` chip；`industry_direction` 仍是 UI 追溯状态，不作为 `/api/graph/query` 新过滤参数。
- 13F 持有人网络：`relationship_context.ownership.shareholders[]` 和 `shareholder_related_companies[]` 输出标准化 `holder_key`；`dynamic_graph.recommended_filters` 也包含 `institutional_holder_key`。`/api/graph/query` 支持 `institutional_holder_key` / `institutionalHolderKey` / `13f_holder_key`，按同一 13F/持仓持有人返回跨公司 `InstitutionalHolding`、`HAS_13F_HOLDING`、`HOLDS_SECURITY` 和 `SAME_HOLDER_RELATED_COMPANY` 边。公司情报 UI 的“股东/持有人”行和“股东关联公司”行都会写入 `data-institutional-holder-key` / `data-institutional-holder-label`，因此既可从某个股东本身，也可从该股东关联公司行展开同一持有人网络；图谱 chip 显示“13F持有人”并保留 raw key 追溯。该过滤不表示事实股权，只表示公开 13F/持仓网络，不改变 paper-only/no-broker 边界。
- 13F 持有人主显示：公司情报 UI 的“股东/持有人”行状态列优先显示 `report_period`；缺少报告期时显示治理后的来源标签，例如 `sec_edgar` 显示“SEC 官方披露”。原始 `source_id` 保留在行级 `data-source-id` 和高级 trace 语义中，供来源审计和脚本验收使用。
- 事实股东网络：公司情报 UI 的“事实股权关系”行和“事实股东关联”行都会写入 `data-ownership-holder-key` / `data-ownership-holder-label`；点击后会按同一已批准 active ownership fact 的股东/持有人 key 展开跨公司事实股东网络，不纳入 `*_candidate` 候选关系。
- `research_results`：研报资产、结构化研报、研报观点、预测、分析师、可靠性评分、研究答案、观点、信号、反方、研究卡、研究任务和搜索结果。
- `analysis_workflow`：观察任务、分析结论和一等模拟反馈记录。
- `simulation_feedback`：一等 `SimulationFeedback` 记录和旧纸面执行意图、模拟成交、模拟流水兼容对象，固定 `live_execution_allowed=false`。
- `data_quality`：画像、行情、事件、关系、研究结果和模拟反馈的可用性与缺口。
- `next_actions`：缺口对应的下一步入口。

研报字段只作为观点/关注度/可靠性复盘来源；事实仍需回链公告、财报、监管披露、公司 IR 或可信公开来源。返回的模拟反馈只用于验证分析结论有效性，不代表真实订单或投资建议。

#### `POST /api/company-intelligence/{symbol}/cycle/run`

公司级闭环刷新 runner，用于在新材料入库、事件/关系复核、行情更新或研报观点结构化后，把分析反馈链路刷新到同一家公司视图里。该接口默认 dry-run，只使用本地已有数据，不下载外部资料，不连接真实券商，不触发真实交易。

执行顺序：

1. 解析 `{symbol}` 到本地 `issuer_id`；若未建档，返回 `status=not_found` 和原公司情报 `next_actions`，不会回退到全库。
2. 读取刷新前的公司情报完整度和公司数据库覆盖率。
3. 可选调用 `POST /api/research-reports/realization/update` 更新研报预测/观点兑现状态。
4. 可选调用 `POST /api/company-database/workflow/build` 刷新观察任务、分析结论和 watch-only 模拟反馈。
5. 可选调用 `POST /api/simulation-feedback/performance/update` 更新 paper-only 反馈表现。
6. 读取刷新后的公司情报完整度和覆盖率，返回 compact summary。

请求字段：

- `execute`：默认 `false`；为 `true` 时才写入兑现状态、workflow 和 paper feedback performance。
- `dry_run`：默认随 `execute` 反向设置；为 `true` 时只返回计划。
- `limit`：目标/处理数量上限，默认 20。
- `link_limit` / `workflow_link_limit`：workflow 回链数量上限，默认 5。
- `include_realization`：默认 `true`。
- `include_workflow`：默认 `true`。
- `include_feedback_performance`：默认 `true`。
- `refresh_existing`：默认 `true`；已有基线观察/结论/反馈可刷新回链。
- `recompute_analyst_scores`：默认 `true`；执行研报兑现时重算分析师可靠性。
- `record_run`：默认随 `execute` 为真；执行模式会持久化一条本地闭环刷新历史，dry-run 只有显式 `record_run=true` 才记录。

返回字段：

- `schema_id`：当前为 `company-intelligence-cycle-v1`。
- `status`：`dry_run`、`executed` 或 `not_found`。
- `run_id` / `recorded`：本次闭环刷新 run ID 和是否写入历史。
- `issuer_ids`：本次解析到的公司主体；未知 symbol 为空。
- `steps`：三个子步骤的原始摘要：`research_report_realization`、`workflow_build`、`simulation_feedback_performance`。
- `summary`：完整度/覆盖率前后变化、兑现项、workflow 项和反馈更新项。
- `before` / `after`：刷新前后公司情报状态、section counts、完整度 verdict 和覆盖率。
- `usage_boundary`：固定声明本地记录、paper feedback、无券商执行。

边界：该 runner 是复盘和本地公司数据库维护动作，不生成投资建议，不把研报升级为事实源，不下单，不连接真实券商。

#### `GET|POST /api/company-intelligence/cycle/runs`

查询公司情报闭环刷新历史。该历史只记录本地 runner 的完整度变化、覆盖率变化、子步骤摘要和 paper-only 反馈数量，用于复盘刷新是否发生以及刷新后是否改善公司情报完整度。

请求字段：

- `run_id`：可选；限定单次闭环刷新。
- `symbol` / `ticker` / `code`：可选；按公司代码过滤。
- `issuer_id`：可选；按本地主体过滤。
- `status`：可选；`dry_run`、`executed`、`not_found` 或 `failed`。
- `limit`：返回数量上限，默认 20，最大 200。

返回字段：

- `schema_id`：当前为 `company-intelligence-cycle-runs-v1`。
- `count` / `summary`：过滤后 run 数和状态摘要。
- `runs[]`：闭环刷新历史，字段见 `CompanyIntelligenceCycleRun`。
- `usage_boundary`：固定声明本地历史、paper feedback、无真实交易。

#### `GET /api/graph/query`

按主体、证据、观点、产业链、公司定位和持仓关系查询图谱。

请求字段：

- `issuer_id`
- `security_id`
- `evidence_id`
- `thesis_id`
- `decision_id`
- `theme_id`
- `chain_id`
- `chain_node_id`
- `relationship_type`：可选；在主体图谱内只展开指定类型的 `CompanyRelationship`，用于从公司情报多维关系面板跳入关系类型子图。公司情报 UI 的图谱过滤 chip 会把常见关系类型显示为中文，例如 `upstream_of` 显示“上游关系”、`shareholder` 显示“事实股东”，但 `data-filter-raw-value` 和 title 仍保留原始关系类型。
- `ownership_holder_key`：可选；与 `relationship_type=shareholder` 等事实股权关系配合使用，按已批准 active ownership fact 的股东/持有人 key 展开同一股东跨公司网络。该过滤只返回非候选、已批准/已复核/自动生成且 active 的 ownership 关系，不把 `*_candidate` 候选纳入事实网络。

返回字段包含 `issuers`、`securities`、`market_data`、`corporate_actions`、`documents`、`evidence`、`manual_reviews`、`theses`、`signals`、`decisions`、`execution_intents`、`reviews`、`strategy_replays`、`exceptions`、`entity_mappings`、`research_cards`、`structured_research_reports`、`report_viewpoints`、`macro_themes`、`industry_chains`、`chain_nodes`、`company_positions`、`research_tasks`、`crowding`、`institutional_holdings`、`disclosure_events`、`challengers`、`portfolio_proposals`、`portfolio_positions` 和 `edges`。产业链研究任务通过 `CHAIN_HAS_RESEARCH_TASK`、`TASK_FOR_CHAIN_NODE`、`TASK_FOR_COMPANY_POSITION`、`ISSUER_HAS_RESEARCH_TASK` 与主题、链路、节点、公司定位和主体连接。结构化研报展示层使用 `structured_research_reports[].research_report_id` 作为研报节点 ID，`report_viewpoints[]` 优先用 `research_report_id` 连接观点节点，缺省时才回退到 `report_id` 或 `document_id`。每条 edge 默认包含 `source`、`timestamp`、`version`、`confidence` 元数据。其中 `portfolio_positions` 来自模拟/回测 ledger 或纸面执行意图，`portfolio_proposals` 是纸面组合候选方案，二者都不代表自动交易。

默认主体图会按焦点公司的产业定位裁剪 `chain_nodes`，并抑制 full-graph production universe 生成的低置信 `needs_review` 批量定位向同链公司扩散，避免首屏图谱被全市场目录污染。显式传入 `relationship_type`、`chain_id` 或 `chain_node_id` 时仍表示用户主动进入关系/产业链探索入口，返回结果继续保留原始 `relationship_type`、`chain_id`、`node_ids` 和 position 追溯。

前端展示模型把产业链节点 canonical 化为 `chain_id:node_id`，与后端 `HAS_CHAIN_NODE`、`POSITION_IN_CHAIN_NODE` 等边的端点保持一致；`chain_nodes[].node_id` 仍保留原始链内节点 ID，供 API 追溯和 `chain_node_id` 过滤使用。

#### `GET|POST /api/graph/quality-center`

只读审计公司关系图谱的数据缺口、展示质量门和可执行增强动作。该接口复用 `/api/graph/query` 和 `/api/graph/knowledge-network/readiness`，不会连接真实券商、不会自动交易；只有传 `run_enrichment=true` 且 `execute=true` 时才会调用既有事件/关系 builder 写入本地候选记录，候选仍默认 `needs_review`，不能直接作为可信事实。

请求字段：

- `market` / `markets`：可选；逗号分隔市场，默认 `A,U`。
- `limit` / `batch_size`：可选；抽样数量和批大小。
- `symbols`：可选；按指定股票代码集合评估。
- `run_enrichment`：默认 `false`；为 `true` 时调用已有公司事件和关系 builder。
- `execute`：默认 `false`；只有同时配合 `run_enrichment=true` 才写入本地候选事件/关系。
- `include_events` / `include_relationships`：可选；控制 enrichment builder 类型。
- `min_edges`、`min_communities`、`min_layers`、`min_structural_nodes`、`max_hub_edge_share`、`max_leaf_ratio`、`min_largest_component_ratio`：可选；覆盖质量门结构阈值。
- `max_display_duplicate_edges`：可选；默认 `0`，表示任何 UI 展示模型下的重复边都会让 `quality_gate.status=needs_attention`。临时诊断需要放宽时必须显式传值。
- `max_duplicate_edges`：可选；默认 `4`，只用于 raw 底层结构诊断，避免把展示模型已折叠的底层关系记录边等同为 UI 重复边。
- `max_duplicate_labels`：可选；默认 `0`，表示任何重复展示标签都会让 `quality_gate.status=needs_attention`。临时诊断需要放宽时必须显式传值。
- `max_raw_label_leaks`：可选；默认 `0`，表示任何 raw/internal label 泄漏都会让 `quality_gate.status=needs_attention`。临时诊断需要放宽时必须显式传值。

返回字段：

- `schema_id`：固定 `graph-quality-center-v1`。
- `status`：`passed`、`needs_attention` 或 `no_targets`。
- `processed_count`、`ready_count`、`passed_quality_count`、`needs_attention_count`。
- `global_failures`：例如空目标 universe 的 `target_universe`。
- `gap_summary`：跨样本 missing/thin layer 汇总。
- `items[]`：逐标的质量结果，包含 `issuer_id`、`security_id`、`symbol`、`market`、`readiness`、`quality_gate` 和 `enhancement_actions`。`enhancement_actions[]` 按该标的实际 `missing_layers` / `thin_layers` 生成，不是固定动作列表：`company_event` 指向 `/api/company-database/events/build`，`company_relationship` 指向 `/api/company-database/relationships/build`，`shareholder_holding` 指向 `/api/13f/filings/parse` / `/api/13f/holdings`，`document` 指向 `/api/ingestion/documents`，`evidence` 指向 `/api/evidence/extract` 和 `/api/graph/knowledge-network/evidence-links/backfill`，`research_report` / `viewpoint` 指向 `/api/research-reports/structure` 以及可选 `/api/research-report-viewpoints`。文档、证据、持仓、研报和观点 action 会包含 `required_source_fields`，与 `/api/graph/enrichment-runner` 的 `layer_action_plan` 共用同一来源字段定义。每条 action 固定 `default_execute=false`，且 `usage_boundary` 声明只使用本地、公开或已提供数据，不连接券商、不执行真实交易。
- `quality_gate`：包含 `status`、`node_count`、`edge_count`、`structure`、`raw_structure`、`community_count`、`present_layer_count`、`duplicate_labels`、`raw_label_leaks`、`failures`、`thresholds` 和 `remediation_actions`。`structure` 使用 UI 展示模型聚合行情节点、关系记录边，并用 `chain_id:node_id` canonical 产业节点评估图谱结构；`raw_structure` 保留原始底层边用于诊断，但同样使用稳定模型 identity，避免空 identity 或裸产业节点 ID 污染结构指标。`remediation_actions[]` 按失败门禁路由：数据层/密度/结构失败指向 `/api/graph/enrichment-runner` 的来源队列 dry-run，重复标签/重复展示边指向 `/api/company-database/quality/reconcile` 的质量归并预览，raw label 泄漏指向只读 `/api/graph/quality-center` 标签模型检查；所有动作固定 `default_execute=false`，并声明本地、公开或已提供数据边界。
- `enrichment_runs[]`：当 `run_enrichment=true` 时记录事件/关系 builder 的 dry-run 或执行摘要。
- `next_recommended_actions`：下一步补齐建议。
- `automation_allowed=false`、`live_execution_allowed=false`、`usage_boundary`：固定声明本地研究和 paper-only 边界。

#### `GET|POST /api/graph/enrichment-runner`

批量图谱增厚规划和小批执行入口。该接口按 production universe 与 `priority_layers` 选择标的，默认使用轻量层计数规划，事件/关系层可调用既有 builder；文档、证据、持仓、研报和观点层只输出 `layer_action_plan`，不会伪造来源材料或自动写入缺失事实。

请求字段：

- `market` / `markets`：可选；逗号分隔市场，默认 `A,U`。
- `limit`、`batch_size`：可选；目标 universe 和本次处理批量。
- `priority_layers`：可选；逗号分隔，支持 `company_event`、`company_relationship`、`document`、`evidence`、`shareholder_holding`、`research_report`、`viewpoint`。
- `quality_mode`：`fast` 或 `full`，默认 `fast`。`full` 会逐标的调用质量中心，成本更高。
- `include_events` / `include_relationships`：默认 `true`；控制是否调用事件/关系 builder。
- `force_build`：默认 `false`；为 `true` 时即使目标层已存在也会规划对应 builder。
- `execute`：默认 `false`；只对事件/关系 builder 生效。文档、证据、持仓、研报和观点层仍需要先通过 `layer_action_plan` 指向的来源入口补材料。
- `skip_issuer_ids`：可选；用于 resume 跳过已完成 issuer。

返回字段：

- `schema_id=graph-enrichment-runner-v1`、`status`、`processed_count`、`skipped_count`、`failed_count`、`batch_size`、`priority_layers`。
- `items[]`：逐标的结果，包含 `before`、`after`、`event_result`、`relationship_result`、`candidate_activity`、`layer_action_plan`、`manual_input_required_layers`、`status` 和 `next_action`。
- `layer_action_plan[]`：机器可读补齐计划。事件层指向 `/api/company-database/events/build`，关系层指向 `/api/company-database/relationships/build`；`document`、`evidence`、`shareholder_holding`、`research_report`、`viewpoint` 分别指向 `/api/ingestion/documents`、`/api/evidence/extract` / `/api/graph/knowledge-network/evidence-links/backfill`、`/api/13f/filings/parse` / `/api/13f/holdings`、`/api/research-reports/structure`、`/api/research-reports/structure` / `/api/research-report-viewpoints`。需要人工/来源输入的 action 会包含 `required_source_fields`，声明补齐该层前必须准备的来源字段。
- `manual_input_required_count`、`manual_input_required_layers`：当剩余层需要本地/公开来源材料时给出明确计数和层名；对应 item `status=waiting_for_source_inputs`，不会被 CLI resume state 记录为完成。
- `source_input_queue`：按层汇总的来源输入队列，`schema_id=graph-source-input-queue-v1`。包含 `status`、`layer_count`、跨层 action-target 合计 `target_count`、去重后的 `unique_target_count`，以及 `layers[]`。每个 `layers[]` 声明 `layer`、`action`、`endpoint`、`fallback_endpoint`、`secondary_endpoint`、`method`、`required_source_fields`、`target_count` 和前 200 个 `targets[]`。该队列是本地/公开/用户提供材料的操作清单，不代表数据已导入，也不允许自动事实提升、券商接入或真实交易。
- `event_totals`、`relationship_totals`：事件/关系 builder 的 planned/created 汇总。
- `automation_allowed=false`、`live_execution_allowed=false`、`usage_boundary`：固定声明本地研究和 paper-only 边界。

#### `GET|POST /api/graph/knowledge-network/readiness`

只读评估本地公司知识网络是否具备 Obsidian 式可探索图谱的数据密度。该接口不会导入数据、不会连接外部图数据库、不会触发交易。它复用现有 `Issuer`、`Security`、`CompanyProfile`、`CompanyPosition`、`IndustryChain`、`CompanyRelationship`、`InstitutionalHolding`、`Document`、`Evidence`、`CompanyEvent`、`ResearchReport`、`ReportViewpoint` 和 `/api/graph/query` 输出，按主体统计图谱层覆盖、社区来源、跨层链接、edge 数量以及 seed 依赖度。

请求字段：

- `issuer_id`：可选；按单一公司主体评估。
- `security_id`：可选；传给 `/api/graph/query` 作为图谱过滤。
- `relationship_type`、`ownership_holder_key`、`institutional_holder_key`、`chain_id`、`chain_node_id`：可选；用于评估特定关系子图。
- `min_layers`：默认 `7`，要求至少覆盖多少个知识层。
- `min_edges`：默认 `20`，要求图谱至少多少条边。
- `min_communities`：默认 `4`，要求至少多少个社区来源。
- `record_readiness`：默认 `false`，为 `true` 时记录审计事件。

返回字段包括 `ready_for_obsidian_exploration`、`status`、`layer_counts`、`layer_status`、`present_layers`、`missing_layers`、`thin_layers`、`community_sources`、`visible_communities`、`graph_summary`、`cross_links`、`seed_dependency` 和 `next_actions`。`seed_dependency.seed_dependent=true` 表示当前图谱主要由 Obsidian seed/fixture 记录支撑，不能当作真实生产数据已经足够丰富的证据。固定 `automation_allowed=false`、`live_execution_allowed=false`，保持本地研究和 paper-only 边界。

#### `POST /api/graph/knowledge-network/evidence-links/backfill`

本地回填知识网络跨层 evidence 链接。接口会在当前 `/api/graph/query` 子图内查找已具备 `Document -> Evidence` 的证据切片，并把同一文档的 evidence ids 回填到 `CompanyEvent.evidence_ids`、`CompanyRelationship.evidence_ids` 和 `ReportViewpoint.evidence_ids`。默认 `execute=false`，只返回计划；显式 `execute=true` 才写入本地记录并产生 `EVENT_EVIDENCE`、`RELATIONSHIP_EVIDENCE`、`VIEWPOINT_EVIDENCE` 等图谱边。该接口不抽取新事实、不批准事件/关系、不把研报观点提升为事实、不触发交易。

请求字段：

- `issuer_id`：必填建议项；限定公司知识网络。
- `security_id`、`relationship_type`、`ownership_holder_key`、`institutional_holder_key`、`chain_id`、`chain_node_id`：可选；传给 `/api/graph/query` 限定子图。
- `limit`：默认 `100`，最多 `500`。
- `execute`：默认 `false`；为 `true` 时才更新本地 provenance 链接。

返回字段包括 `planned_count`、`updated_count`、`planned_by_type`、`plans`、`updated`、`automation_allowed=false`、`live_execution_allowed=false` 和 `usage_boundary`。从 seed 文档抽取来的 evidence 仍应在 readiness 中计入 seed dependency，不能作为真实生产级图谱完成证据。

#### `GET /api/graph/traceability-report`

返回观点、决策和研究问答到 evidence/document 的回溯率报告，用于检查结论是否能沿图谱回到原始证据。可用 `issuer_id`、`include_details`、`limit` 过滤。报告会标记缺失 evidence、缺失 document、decision signal 断链和 research answer 英文原文缺失等问题。

#### `GET /api/graph/edge-quality-report`

检查图谱 edge 元数据覆盖率，要求每条边具备 `source`、`timestamp`、`version`、`confidence`。返回 `edge_metadata_coverage`、`missing_counts` 和逐边缺失明细。支持 `issuer_id`、`security_id`、`evidence_id`、`thesis_id`、`decision_id`、`limit`。

请求字段：

- `issuer_id`
- `include_details`
- `limit`

#### `GET /api/graph/neo4j/export`

把当前本地图谱导出为 Neo4j bulk upsert-compatible payload，包含 `nodes`、`relationships`、labels、relationship type、properties、node/relationship key 和 `content_sha256`。接口只生成 adapter payload，不直接连接 Neo4j。支持 `issuer_id`、`security_id`、`evidence_id`、`thesis_id`、`decision_id`、`record_export`。

#### `POST /api/graph/neo4j/sync`

把 Neo4j 导出 payload 写入 `AlertNotification` outbox，默认 `channel=neo4j_graph_sync_outbox`、`target=neo4j://graph-db`，可覆盖 `channel`、`target`、`provider`、`max_delivery_attempts`、`delivery_backoff`、`force` 和 `mark_sent`，后续由 `/api/alerts/notifications/deliver` 推进。

#### `GET|POST /api/graph-vector/readiness-report`

输出图谱/向量外部同步验收报告，不直接连接 Neo4j 或 Qdrant。报告复用 `/api/graph/neo4j/export` 与 `/api/search/qdrant/export` 的 payload 统计，并检查图谱追溯率、edge 元数据覆盖率、rights/risk 边界、非本机 Neo4j/Qdrant endpoint、同步 artifact URI、批量同步吞吐 baseline 和失败注入/重试恢复证据。返回 `ready_for_graph_vector_production`、`gates`、`missing_requirements`、`adapters`、`throughput`、`retry_summary`、`graph_export` 和 `qdrant_export`；传 `record_readiness=true` 时写审计事件 `graph_vector_readiness_report`。

请求字段：

- `issuer_id`
- `neo4j_endpoint`
- `qdrant_endpoint`
- `throughput`
- `retry_result`
- `artifact_uris`
- `record_readiness`

#### `GET /api/search`

内置全文检索 fallback，按 query 命中和字段权重返回结果。
当前混合索引覆盖 document、evidence、thesis、research card、research answer、research report、market data、corporate action、13F、disclosure event、portfolio proposal、company position、research task 和 benchmark sample，因此产业链缺字段/缺证据任务也可以被搜索召回。

请求字段：

- `q`
- `issuer_id`
- `limit`

#### `POST /api/search`

同 `GET /api/search`，用于复杂查询体。

#### `POST /api/search/rebuild`

从当前事实层重新生成混合 `SearchRecord`，并同步全文索引和语义索引。支持 `targets=["keyword","semantic"]`、`issuer_id`、`resource_types`、`include_restricted`；外部全文索引失败且启用 fallback 时会同步本地索引并返回 `fallback_from` / `fallback_error`，同时写入审计日志。返回 `record_count`、`resource_counts`、各目标 `sync` 结果和错误列表。

#### `GET /api/search/qdrant/export`

把混合 `SearchRecord` 导出为 Qdrant points upsert-compatible payload，包含 collection、vector name、64 维本地 hashed term-frequency 向量、payload 权限边界、rights tag 和 `content_sha256`。接口只生成 adapter payload，不直接连接 Qdrant。支持 `issuer_id`、`resource_types`、`include_restricted`、`collection`、`record_export`。

#### `POST /api/search/qdrant/sync`

把 Qdrant points payload 写入 `AlertNotification` outbox，默认 `channel=qdrant_vector_sync_outbox`、`target=qdrant://vector-store`，可覆盖 `channel`、`target`、`provider`、`max_delivery_attempts`、`delivery_backoff`、`force` 和 `mark_sent`，后续由 `/api/alerts/notifications/deliver` 推进。

#### `GET /api/search/adapter-sync/retry`

对 Neo4j / Qdrant adapter sync outbox 做失败重试演练。默认扫描 `neo4j_graph_sync_outbox` 和 `qdrant_vector_sync_outbox` 中 `status=failed` 的通知，也可用 `channels`、`notification_ids`、`status` 过滤；返回候选通知、尝试次数、最大尝试次数、最近错误和 `retryable` 判断。默认 dry-run，不直接调用外部 Neo4j/Qdrant client。

#### `POST /api/search/adapter-sync/retry`

同 `GET`，传 `execute=true` 时复用 `/api/alerts/notifications/deliver` 状态机对可重试通知再次发送。可传 `provider`、`max_delivery_attempts`、`timeout_ms` 覆盖本次演练参数，并写入审计日志。

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

把当前开放告警写入通知记录，可指定 `channel`、`target`、`alert_ids`。传 `route_failures=true` 或 `failure_routes` 时，会按 `playbook_id` / `rule_id` / `metric` 把采集、检索、LLM、OCR 和 workflow 失败路由到专属 channel/target，并把 provider、max attempts 和 backoff 写入 notification delivery policy；后续由 `/api/alerts/notifications/deliver` 执行。

请求字段：

- `channel`
- `target`
- `alert_ids`
- `mark_sent`
- `route_failures`
- `failure_routes`

#### `POST /api/alerts/notifications/deliver`

发送告警通知 outbox。默认 `execute=false` 只做 dry-run；`execute=true` 时按 `notification_ids`、`channel`、`status` 过滤通知并标记为 `sent` 或 `failed`，把 `delivery_provider`、`delivery_attempts`、`delivered_at`、`delivery_response` 和错误写回 notification payload，并遵守通知 payload 内的 `delivery_policy.max_attempts` 或请求级 `max_delivery_attempts`。当 `provider` 为 `webhook`、`http` 或 `https` 时，会对 HTTP(S) `target` 发起 JSON POST；当 `provider=email|smtp` 时使用请求或环境变量中的 SMTP 配置发送 EmailMessage；当 `provider=slack` 时向 Slack webhook URL 发送 JSON payload。非 HTTP(S) webhook/slack target、缺失 SMTP host、缺失 email 收件人等会失败并记录错误；其他 provider 保持 state-only 模式。

#### `GET /api/alerts/notifications`

按 `alert_id`、`channel`、`status` 查询告警通知记录。

#### `GET /api/alerts`

查询告警规则和系统告警。

请求字段：

- `status`
- `severity`
- `owner`

### 4.x 瓶颈研究

#### `POST /api/chokepoint/runs`

创建可持久化的 Serenity-style 瓶颈研究流水线 run。返回 7 个固定步骤：来源台账、事实审计、问题窄化、价值链映射、Chokepoint 排名、Thesis 草稿、验证与证伪。返回固定 `automation_allowed=false`、`live_execution_allowed=false`。

请求字段：

- `run_id` 可选
- `topic`
- `ticker`
- `theme`
- `chokepoint_node`
- `playbook`
- `mode`：`strict`、`balanced`、`exploratory`

#### `GET /api/chokepoint/runs`

查询历史瓶颈研究 run。

请求字段：

- `status`
- `topic` / `q`
- `ticker`
- `limit`

#### `GET|POST /api/chokepoint/readiness-report`

汇总瓶颈研究流水线的生产就绪度，不触发 LLM、图数据库、向量库或交易系统。报告会对样本 run 的来源 URL 覆盖、`confirmed/inferred/speculative/unknown` 分层比例、fallback 命中、验证任务关闭率、边界违规命中（投资建议/思维链）进行打分和门禁检查。

请求字段：

- `run_ids`（可选）
- `topic` / `q`（可选）
- `ticker`（可选）
- `status`（可选）
- `limit`（可选）
- `min_runs`
- `min_source_url_coverage`
- `min_confirmed_ratio`
- `max_fallback_rate`
- `min_needs_verification_closure_rate`
- `max_boundary_violation_rate`
- `record_readiness`

返回字段：

- `ready_for_chokepoint_research_production`
- `ready_for_external_acceptance`
- `missing_requirements`
- `gates`
- `scope`
- `coverage_report`
- `automation_allowed=false`
- `live_execution_allowed=false`
- `usage_boundary`

#### `GET /api/chokepoint/runs/{run_id}`

读取完整 run，包括 steps、issues、validation_context、conclusion 和 review_snapshot。

#### `POST /api/chokepoint/runs/{run_id}/steps/{step_id}/run`

运行或重跑单个步骤。后端使用 approved `llmtpl_chokepoint_step_v1` 调用 LLM，并持久化 `input_prompt`、`llm_run_id`、`output_text`、`summary`、`evidence_quality`、`issues` 和调优记录。若来源台账无 URL、输出含投资建议、出现思维链或 LLM fallback，则步骤进入 `review`。

请求字段：

- `input_prompt`
- `role`
- `max_tokens`
- `temperature`
- `timeout_seconds`
- `tuning_notes`

#### `POST /api/chokepoint/runs/{run_id}/run`

从当前步骤顺序运行流水线。门禁问题会写入 step/issues 并保留为 `review`，流水线继续推进；如果跑到最后一步且所有步骤进入 `done`/`review`，后端会自动执行 finalize，生成 `conclusion` 并固化验证任务。LLM 结论生成失败或限流时，仍返回规则结论，并在 `conclusion.fallback_used` 标记回退。

请求字段：

- `start_step`
- `step_limit`
- `role`
- `max_tokens`
- `temperature`
- `timeout_seconds`

#### `POST /api/chokepoint/runs/{run_id}/finalize`

生成或刷新瓶颈研究流水线结论。后端先根据 steps、issues、evidence_quality 和 validation_context 生成稳定规则结论，再尝试使用 approved `llmtpl_chokepoint_conclusion_v1` 做可读综合；AI 失败时不清空结论。接口会自动调用验证任务生成逻辑，把 open issue、unknown、needs_verification 和 P0 验证项固化为幂等 `ResearchTask`，并刷新验证资源计数。

请求字段：

- `role`
- `max_tokens`
- `temperature`
- `timeout_seconds`
- `verification_task_limit`

返回 `conclusion` 固定包含：

- `status`：`ready_for_review`、`needs_evidence` 或 `failed`
- `one_line_conclusion`
- `thesis_strength_score`
- `confidence`
- `evidence_quality_summary`
- `confirmed_summary`
- `inferred_summary`
- `speculative_summary`
- `core_facts`：事实层条目，只来自公告、财报、监管披露、公开行情或其他可信 evidence；包含 `evidence_id`、`document_id`、`source_uri` 和置信度。
- `inferences`：推断层条目，保留 step 来源，不升级为事实。
- `speculations`：投机/早期假设层条目，必须继续进入验证或证伪。
- `unknowns`：未知或待验证条目，包含 `verification_status`。
- `evidence_gaps`：由 open issue 和验证任务组成的证据缺口。
- `market_pricing_context`：行情上下文，只用于验证市场定价，不是买卖信号。
- `key_chokepoints`
- `catalysts`
- `falsification_conditions`
- `falsification_status`：`pending`、`needs_verification`、`verified` 或 `falsified`
- `validation_summary`
- `open_issues`
- `next_verification_tasks`
- `next_actions`
- `verification_tasks`：包含 `created_count`、`existing_count`、`open_count`、`closed_count`、`done_count`、`dismissed_count`、`status_counts` 和 `completion_rate`
- `llm_run_id`
- `fallback_used`
- `usage_boundary=research_only_not_investment_advice`

#### `POST /api/chokepoint/runs/{run_id}/review`

人工复核 run 或 step，可追加调优记录、关闭 issue、更新 review snapshot。

请求字段：

- `step_id`
- `status`
- `run_status`
- `tuning_notes`
- `close_issue_ids`
- `review_snapshot`

#### `POST /api/chokepoint/runs/{run_id}/verification-tasks`

把 open issue、unknown、needs_verification 和 P0 验证项固化为 `ResearchTask`。重复调用按稳定 task id 幂等返回 existing。

请求字段：

- `limit`

#### `POST /api/playbooks/seed`

写入默认事故剧本和季度演练计划，覆盖文档解析失败、数据采集失败、检索降级、LLM 网关失败和权限/敏感数据泄漏五类事故。返回 `playbooks` 与 `schedules`。

请求字段：

- `create_schedules`
- `limit`

#### `POST /api/drill-schedules/{schedule_id}/result`

回写事故演练结果，更新 `last_run_at`、`last_result`、`rca_summary`、`action_items`，并按 `cadence` 推进 `next_run_at`。`result` 支持 `passed`、`failed`、`partial`、`skipped`，回写动作进入审计日志并会出现在 `/api/incidents/calendar`。

请求字段：

- `result`
- `run_at`
- `next_run_at`
- `rca_summary`
- `action_items`
- `owner`
- `notes`

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
