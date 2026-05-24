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

使用内置轻量 DAG 执行器按拓扑顺序运行白名单本地任务，并将每步结果写入 `WorkflowRun.task_statuses`、`inputs.task_results`、`output_refs` 和 `LineageEvent`。当前支持 `ingest_document`、`extract_evidence`、`structured_extraction` / `extract_structured_facts`、`search_rebuild`、`benchmark_sample_register`、`benchmark_run`、`document_parse` / `paddleocr` 和 `noop`。任务 payload 支持 `${inputs.foo}`、`${task_id.output_ids.0}`、`${task_id.output_refs.0}` 占位符，用于把上游产物传给下游任务。可传 `task_ids` / `tasks` / `task_id` 或 `queues` / `queue` 做任务级选择和队列隔离。接口仍是单进程内置执行器；分布式队列、外部 sensor 和大规模 backfill 达到阈值后应切换 Airflow/Dagster。

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
- `counts`
- `source_summary`

`research_evidence` 包含本地研报数量、`research_report_citation` 证据数量、语义检索召回状态、热点扩散召回状态和用途边界。研报 evidence 固定为观点/参考层，不能升级为事实真相源、训练源或真实交易信号。

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

返回字段包含 `issuers`、`securities`、`market_data`、`corporate_actions`、`documents`、`evidence`、`manual_reviews`、`theses`、`signals`、`decisions`、`execution_intents`、`reviews`、`strategy_replays`、`exceptions`、`entity_mappings`、`research_cards`、`macro_themes`、`industry_chains`、`chain_nodes`、`company_positions`、`research_tasks`、`crowding`、`institutional_holdings`、`disclosure_events`、`challengers`、`portfolio_proposals`、`portfolio_positions` 和 `edges`。产业链研究任务通过 `CHAIN_HAS_RESEARCH_TASK`、`TASK_FOR_CHAIN_NODE`、`TASK_FOR_COMPANY_POSITION`、`ISSUER_HAS_RESEARCH_TASK` 与主题、链路、节点、公司定位和主体连接。每条 edge 默认包含 `source`、`timestamp`、`version`、`confidence` 元数据。其中 `portfolio_positions` 来自模拟/回测 ledger 或纸面执行意图，`portfolio_proposals` 是纸面组合候选方案，二者都不代表自动交易。

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
