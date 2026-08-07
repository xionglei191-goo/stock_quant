# 生产部署 Runbook

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-07-30
- Related tasks: T-430, T-482, T-492, T-602, T-605, T-610, T-611, T-625, T-626
- Scope: local production deployment, daily operations, backup, rollback, and release evidence
- Non-goals: live broker connectivity, automatic order execution, or non-local release approval from local-only evidence

## 1. 环境变量

| 变量 | 用途 | 生产建议 |
|---|---|---|
| `AI_QUANT_DB` | SQLite 路径；也可填 PostgreSQL DSN | 单机试运行用 SQLite；生产优先 PostgreSQL |
| `AI_QUANT_POSTGRES_DSN` | PostgreSQLStore DSN | 使用专用账号、最小权限、TLS 网络边界 |
| `AI_QUANT_DATABASE_URL` | PostgreSQLStore DSN 兼容别名 | 与 `AI_QUANT_POSTGRES_DSN` 二选一 |
| `AI_QUANT_OBJECT_STORE_BACKEND` | `local` 或 `s3` | 生产使用 `s3` |
| `AI_QUANT_OBJECT_STORE` | 本地对象目录 | 仅开发或单机试运行使用 |
| `AI_QUANT_S3_ENDPOINT` | S3 兼容 endpoint | 使用内网 endpoint 或受控公网 endpoint |
| `AI_QUANT_S3_BUCKET` | 原文对象 bucket | 单独 bucket，开启版本化和生命周期策略 |
| `AI_QUANT_S3_ACCESS_KEY` | S3 access key | 通过密钥管理注入，不写入镜像 |
| `AI_QUANT_S3_SECRET_KEY` | S3 secret key | 通过密钥管理注入，不写入镜像 |
| `AI_QUANT_SEARCH_BACKEND` | `local` 或 `opensearch` | 生产使用 `opensearch`，保留 fallback |
| `AI_QUANT_SEARCH_FALLBACK` | 外部检索失败是否回退本地 | 生产建议 `true`，并配置告警 |
| `AI_QUANT_OPENSEARCH_URL` | OpenSearch endpoint | 使用专用索引和最小权限账号 |
| `AI_QUANT_OPENSEARCH_INDEX` | 检索索引名 | 每环境独立命名 |
| `AI_QUANT_OPENSEARCH_USERNAME` | OpenSearch 用户 | 通过密钥管理注入 |
| `AI_QUANT_OPENSEARCH_PASSWORD` | OpenSearch 密码 | 通过密钥管理注入 |
| `AI_QUANT_DYNAMIC_ALLOCATION_DB` | 动态配置领域 SQLite 路径 | Compose 使用 `/data/local/dynamic_allocation.sqlite`，纳入现有 `./data:/data` 持久卷 |
| `AI_QUANT_DYNAMIC_ALLOCATION_DASHBOARD_HOST_PORT` | Streamlit Dashboard 宿主机端口 | 默认 `8501`；需与防火墙和入口跳转配置一致 |
| `AI_QUANT_DYNAMIC_ALLOCATION_DASHBOARD_URL` | Dashboard 完整外部地址覆盖 | 有反向代理时填写 HTTPS 地址；本机留空并按请求 host 生成 |
| `AI_QUANT_SEC_USER_AGENT` | SEC EDGAR 请求标识 | 必须包含团队或联系邮箱 |
| `AI_QUANT_ASHARE_USER_AGENT` | A 股公告请求标识 | 使用统一生产标识 |
| `AI_QUANT_HKEX_USER_AGENT` | HKEX 请求标识 | 使用统一生产标识 |

## 2. 首次部署

1. 复制 `.env.example` 为环境配置模板，并通过部署系统注入真实密钥。
2. PostgreSQL 执行 `docs/postgresql-schema.sql`；或启动服务时由 `PostgreSQLStore` 初始化 schema。
3. 若从 SQLite 迁移，先执行只读 preflight；正常写入路径只允许 target-wins 的 merge：

```bash
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db "$AI_QUANT_POSTGRES_DSN"
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db "$AI_QUANT_POSTGRES_DSN" --mode merge
```

   `exact-replace` 只用于经过审阅的例外恢复，必须同时提供最新 preflight 的计数绑定确认令牌和仍在保留期内的恢复验证备份 manifest；详见 `docs/postgresql-migrations.md`。

4. 配置对象存储 bucket、访问密钥、版本化和备份策略。
5. 配置 OpenSearch endpoint、索引名、账号和 fallback。
6. 启动主服务与动态配置 Dashboard：

```bash
docker compose up -d ai-quant-org dynamic-allocation-dashboard
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8501/_stcore/health
curl -I http://127.0.0.1:8000/dynamic-allocation
```

   `/dynamic-allocation` 应返回 HTTP 302，默认指向同一访问主机的 8501 端口。Docker 镜像内必须保留 `poppler-utils`、Streamlit、Plotly 和 `config/dynamic_allocation.yaml`。本地研报 PDF 的受限文本提取调用 `pdftotext`；缺少该依赖时报告只能进入 `needs_text_review`，不得把空提取当成可引用证据。

7. 运行上线前检查。

## 3. 上线前检查

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/capacity_baseline.py --records 100
python3 scripts/full_run_acceptance.py --capacity-records 10
python3 scripts/smoke_test.py http://127.0.0.1:8000
python3 scripts/staging_governance_acceptance.py http://127.0.0.1:8000 --record-readiness
python3 scripts/staging_security_acceptance.py http://127.0.0.1:8000 --secret-manager-provider local-development-metadata-only
python3 scripts/staging_otel_acceptance.py http://127.0.0.1:8000 --otel-endpoint http://127.0.0.1:4318/v1/logs --record-readiness
python3 scripts/staging_lineage_registry_acceptance.py http://127.0.0.1:8000 --openlineage-target http://127.0.0.1:5001/openlineage --mlflow-target http://127.0.0.1:5002/mlflow
python3 scripts/staging_vision_gate_acceptance.py http://127.0.0.1:8000 --record-launch-checklist
```

## 3.1 本机每日刷新闭环

本机个人生产使用 `scripts/run_daily_data_update.sh` 作为统一入口。它会启动 compose 服务、获取互斥锁、按 state offset 推进 A 股/美股增量，并写入 `artifacts/daily-update-local/latest-run.json`。

关键产物是每次运行目录里的 `daily-update-YYYY-MM-DD.json`：

- `summary.market_data` 记录 A/U 最新日期、行数增量、typed-only K 线存储和旧 JSONB 记录数。
- T-602 后 `ai_quant.market_data_bars` 只保存结构化行情、payload key mask、非重复扩展字段和权限策略引用；完整 `payload`/`rights_tag` 由 `ai_quant.market_data` 兼容视图重建。schema 迁移、停机、备份、回滚和 cleanup 命令见 `docs/postgresql-migrations.md`。
- `summary.actionable_insight` 记录今日可读研究摘要、异动标的、研报证据公司数和质量门禁。
- 顶层及 `summary` 的 `status`/`passed` 保持兼容并代表执行健康，`execution_status` 显式返回同一执行结论；数据导入、存储、接口、脚本异常等阻断故障会使其为 `failed`。
- `content_status` 独立返回 `ready`、`needs_evidence` 或 `unavailable`。研报直接证据不足时原始 daily insight 质量门仍保持失败并写入 `content_issues`，但只标记 `needs_evidence`，不会把已正常完成的 systemd 流水线误判为执行失败。
- `summary.latency` 记录关键 API 的最慢 probe 和阈值。
- `artifact_manifest` 列出本次所有 artifact 的存在性、状态和大小。
- `operator_next_actions` 是第一优先级排障入口。

公开源 scope 刷新默认有独立短超时 `AI_QUANT_DAILY_SCOPE_REFRESH_TIMEOUT_SECONDS=300`，不会占用 `AI_QUANT_DAILY_IMPORT_TIMEOUT_SECONDS` 的长导入窗口。`latest_analysis_run.py` 也受 `AI_QUANT_DAILY_ANALYSIS_TIMEOUT_SECONDS` 外层约束；超时或失败时会在目标 artifact 路径写入失败 JSON，随后继续执行 daily insight、latency audit 和本机生产审计。daily insight 能生成但证据门不足属于内容缺口，查看 `content_status`、`summary.content_issues` 和原始 insight artifact；生成过程抛错或 artifact 不可用属于执行故障。若需要把其他非阻断失败改成阻断，关闭对应 `ALLOW_*_FAILURE` 环境变量。

日更调度验收：

```bash
python3 scripts/audit_daily_update_schedule.py \
  --repo-root . \
  --output-dir artifacts/daily-update-local \
  --require-latest-run \
  --output artifacts/daily-update-local/daily-update-schedule-audit.json
```

进入 staging 后，对真实部署地址执行 HTTP 验收。该脚本只会使用模拟成交，不会开启真实券商或自动下单：

```bash
AI_QUANT_STAGING_URL=https://staging.example.internal \
AI_QUANT_STAGING_ARTIFACT_PREFIX=s3://ai-quant-staging-artifacts/readiness/$(date +%Y%m%d) \
AI_QUANT_POSTGRES_DSN=postgresql://... \
AI_QUANT_S3_BUCKET=ai-quant-staging \
AI_QUANT_OPENSEARCH_URL=https://search.example.internal \
AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.internal/v1/logs \
python3 scripts/staging_acceptance.py --record-readiness --notify-missing \
  --cross-browser-matrix artifacts/ui-cross-browser-matrix.json
```

`--cross-browser-matrix` 必须先通过 `python3 scripts/ui_cross_browser_matrix_check.py artifacts/ui-cross-browser-matrix.json`：矩阵至少覆盖 2 个浏览器 family、desktop/mobile viewport、必备 UI 文案且 failure_count=0。未提供该矩阵时，`scripts/staging_acceptance.py` 只回填 Headless Chrome 截图验收，不会写入 `cross_browser_acceptance`。

导出的上线证据包必须再做离线校验：

```bash
python3 scripts/readiness_evidence_package_check.py artifacts/readiness-evidence-package.example.json
```

生产闭环 manifest 先做离线结构校验；只想预检 manifest 时可加 `--skip-report-readiness`。

先审计任务级收口状态，确认开放项是代码层缺口还是外部证据缺口：

```bash
python3 scripts/production_task_closure_audit.py \
  --output artifacts/production-task-closure-audit.json
```

目标完成审计必须单独跑一次；该脚本会把用户目标映射到实际 artifact、任务状态、manifest 和外部证据。若仍缺真实生产/预发证据，它会返回非零退出码，这是正常的发布阻断信号：

```bash
python3 scripts/project_completion_audit.py \
  --output artifacts/project-completion-audit.json
```

若部署目标是本机个人长期运行，完成审计必须显式传入本机生产证据。该路径会接受 `artifact://staging-local/...` 等本机证据 namespace，但不会放宽非本机组织级发布门禁：

```bash
python3 scripts/project_completion_audit.py \
  --local-production-audit artifacts/local-production-audit.json \
  --local-ai-acceptance artifacts/local-ai-capability-acceptance.json \
  --output artifacts/project-completion-audit.json
```

真实发布签批前，目标完成审计必须带上 filled plan、readiness evidence package 和 artifact inventory，不能只依赖模板 manifest：

```bash
python3 scripts/project_completion_audit.py \
  --manifest artifacts/production-closure-manifest.json \
  --evidence-plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --artifact-inventory artifacts/production-artifact-inventory.json \
  --artifact-bundle-root artifacts/production-evidence-bundle \
  --output artifacts/project-completion-audit.json
```

如需把阻塞项分发给各 owner，可导出外部证据采集计划：

```bash
python3 scripts/production_task_closure_audit.py \
  --output artifacts/production-task-closure-audit.json \
  --output-plan artifacts/production-evidence-collection-plan.json
```

拿到真实归档前缀后，先把模板 URI 一次性替换成具体对象前缀：

```bash
python3 scripts/production_evidence_plan_fill.py \
  artifacts/production-evidence-collection-plan.json \
  --artifact-prefix s3://ai-quant-prod/evidence/release-20260518 \
  --output artifacts/production-evidence-collection-plan.json
```

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json
```

owner 回填真实证据 URI 后，再用严格模式确认模板占位符已经全部替换：

```bash
python3 scripts/production_evidence_plan_check.py \
  artifacts/production-evidence-collection-plan.json \
  --require-filled-uris \
  --output artifacts/production-evidence-plan-validation.json
```

把已回填 URI 的计划转换成 production closure manifest 草案；该脚本默认拒绝占位符，生成后仍需继续跑严格发布校验：

```bash
python3 scripts/production_evidence_plan_to_manifest.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --base artifacts/production-closure-manifest.example.json \
  --output artifacts/production-closure-manifest.json
```

也可以直接运行发布门禁编排器。它会按顺序执行 filled plan 校验、manifest 生成和严格 manifest 校验；默认必须提供真实 readiness evidence package，`--draft` 只用于模板预览：

```bash
python3 scripts/production_release_gate.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --artifact-inventory artifacts/production-artifact-inventory.json \
  --artifact-bundle-root artifacts/production-evidence-bundle \
  --manifest-output artifacts/production-closure-manifest.json
```

严格发布门禁通过后，才能把 `tasks/todo.md` 的 `BLOCKED` 项迁入 `DONE`：

```bash
python3 scripts/production_task_status_finalize.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --artifact-inventory artifacts/production-artifact-inventory.json \
  --artifact-bundle-root artifacts/production-evidence-bundle \
  --manifest-output artifacts/production-closure-manifest.json
```

```bash
python3 scripts/production_artifact_inventory_check.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --manifest artifacts/production-closure-manifest.json \
  --output-template artifacts/production-artifact-inventory.json
```

如已把归档对象导出到本地 bundle 目录，优先从 bundle 自动生成带 sha256/size 的 inventory：

```bash
python3 scripts/production_artifact_inventory_check.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --manifest artifacts/production-closure-manifest.json \
  --from-bundle-root artifacts/production-evidence-bundle \
  --generated-at 2026-05-18T00:00:00Z \
  --output artifacts/production-artifact-inventory.json
```

`--generated-at` 可省略，省略时脚本会写入当前 UTC 时间戳；不要保留 `<generated_at>` 等模板占位符。

```bash
python3 scripts/production_artifact_inventory_check.py \
  artifacts/production-artifact-inventory.json \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --manifest artifacts/production-closure-manifest.json
```

校验 inventory 时可同时复验导出文件存在、大小和 sha256：

```bash
python3 scripts/production_artifact_inventory_check.py \
  artifacts/production-artifact-inventory.json \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --manifest artifacts/production-closure-manifest.json \
  --bundle-root artifacts/production-evidence-bundle
```

```bash
python3 scripts/production_closure_manifest_check.py artifacts/production-closure-manifest.json
```

```bash
python3 scripts/readiness_evidence_package_check.py \
  artifacts/readiness-evidence-package.json \
  --output artifacts/readiness-evidence-package-validation.json
```

```bash
python3 scripts/production_closure_manifest_check.py \
  artifacts/production-closure-manifest.json \
  --output artifacts/production-closure-manifest-validation.json
```

校验器默认按真实发布口径运行，要求 manifest 顶层 `ready_for_launch=true`，并要求内嵌 evidence package 满足 `missing_evidence_count=0`、`failed_gate_count=0`、9 个必填 readiness check 和必填外部验证 scope 全覆盖。每条 checklist / external validation evidence URI 都必须是外部归档型引用并指向具体对象或路径；本机路径、`file://`、`local://`、服务连接串、只有域名的 HTTP(S) 根地址，以及 `artifact://local-*`、`artifact://staging-local`、`artifact://local-staging`、`artifact://staging-test`、`artifact://staging-acceptance`、`artifact://demo` 这类本机或样例前缀不会通过。导出给该校验器的 evidence package 必须传 `include_passed=true`。只校验模板结构时显式加 `--allow-template`，不要把模板校验结果作为发布签批证据。

生产收口时使用真实证据 manifest 一次性回填、跑 readiness reports、导出并校验 evidence package：

```bash
python3 scripts/production_closure.py https://staging.example.internal \
  --manifest artifacts/production-closure-manifest.json \
  --output artifacts/production-closure-result.json
```

`scripts/production_closure.py` 不生成或伪造生产证据，只消费真实 staging/production artifact URI。manifest 必须包含 9 个 readiness check 的外部归档 evidence URI、storage/security/observability/UI/deployment 报告 payload、已冻结的数据源类别，以及当前生产闭环实际使用的免费 A 股 connector；本机路径、样例 artifact、收费/商业授权数据源、未纳入冻结集合的 connector 会在回填前被拒绝。
本机 `pg_dump/pg_restore` 演练按当前数据量运行，单步默认超时由 `AI_QUANT_BACKUP_RESTORE_TIMEOUT_SECONDS=1800` 控制；容器内外都有超时保护，失败路径会清理临时 dump 和临时恢复库。大库需要更长窗口时必须显式记录调整值，不能跳过恢复验证后回填通过状态。
`scripts/production_task_closure_audit.py` 的 `blocked_external_evidence` 表示代码、路由、测试和验收脚本已存在，但仍缺真实外部 artifact；它不能替代 evidence package 校验，也不能作为发布签批证据。
任务审计输出会给出 `needs_code_work_count`、`blocked_external_evidence_count`、`needs_code_work_task_ids` 和 `blocked_external_evidence_task_ids`，用于区分还要继续开发的任务与只等待真实证据归档的任务；目标完成审计输出会给出 `failed_requirement_ids`、`blocked_requirement_ids` 和 `open_requirement_ids`，用于发布门禁直接判断卡点。`blocked_requirement_ids` 中仍包含 `R3` 或 `R6` 时，说明缺真实 staging/production evidence、artifact inventory 或 release gate 通过结果，不能执行任务状态 finalize。
发布门禁输出会给出 `stage_count`、`passed_stage_count`、`failed_stage_count` 和 `failed_stage_names`，用于 CI/签批系统直接定位失败阶段；`failed_stage_count>0` 时不要继续生成发布签批记录。
`--output-plan` 生成的采集计划只列 owner、readiness endpoint、artifact 字段和 URI 模板；`scripts/production_evidence_plan_fill.py` 可用真实归档前缀批量替换模板 URI，并立即按 `--require-filled-uris` 口径校验；`scripts/production_evidence_plan_check.py` 默认只校验采集计划结构，`--require-filled-uris` 才会拒绝未替换的模板占位符，并可用 `--output` 归档校验结果。`scripts/readiness_evidence_package_check.py` 和 `scripts/production_closure_manifest_check.py` 也支持 `--output`，发布签批应归档 evidence package validation、manifest validation、release gate result 和 completion audit。`scripts/production_artifact_inventory_check.py` 校验证据 URI 背后的归档清单，要求每条 evidence URI 有 sha256、size、生产/预发环境、producer、owner、content type、retention 和 immutable/object lock 记录，并会拒绝 inventory 或 required context 中仍带 `<production-evidence-bucket>` / `<release-id>` 这类占位符的 URI。`scripts/production_evidence_plan_to_manifest.py` 负责把已回填 URI 的计划映射到 manifest 的 task evidence、readiness checks、reports 和 A 股 connector 证据；`manifest_generation` 会给出 `skipped_mapping_count`、`mapped_readiness_check_count`、`missing_readiness_check_count` 和 `missing_external_validation_scope_count`，用于门禁脚本直接判断是否还有未映射的 readiness 或外部验证范围；它默认不会设置 `ready_for_launch=true`，真实发布仍必须嵌入由 staging/production 导出的 readiness evidence package 后通过严格校验。`scripts/production_release_gate.py` 是同一链路的一键门禁封装，默认没有真实 evidence package、artifact inventory 或 filled URI 就失败。`scripts/production_task_status_finalize.py` 会复跑同一严格门禁，只有通过后才更新任务状态。
同口径示例见 [`artifacts/production-closure-manifest.example.json`](../artifacts/production-closure-manifest.example.json)。

本机全量 staging 栈可直接用 Compose 启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector，以及 OpenLineage/MLflow HTTP sink 并自动跑验收：

```bash
bash scripts/local_staging_stack.sh
```

个人本机长期使用建议直接跑本机生产入口。它会先设置一组不易冲突的宿主机端口，再调用完整 staging 验收，随后生成 `artifacts/local-production-audit.json`；若 `/api/health` 显示 LLM gateway 和 PaddleOCR-VL 均已配置，还会生成 `artifacts/local-ai-capability-acceptance.json`。该入口默认用 `AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS=5000` 和 `AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS=5000` 保护本机交互请求；仅对 Neo4j、Qdrant、OTel、OpenLineage 和 MLflow 的明确外部同步/导出端点使用 `AI_QUANT_STAGING_CAPACITY_BATCH_THRESHOLD_MS=60000`，并对 demo fixture、DAG、模型和 lineage 的验收初始化使用 `AI_QUANT_STAGING_CAPACITY_SETUP_THRESHOLD_MS=20000`。批处理和 setup 阈值不会覆盖搜索、图谱查询、健康检查或模拟执行；需要更严格时可分别调小对应阈值。需要跳过真实 AI smoke 时设置 `AI_QUANT_LOCAL_PRODUCTION_SKIP_AI_ACCEPTANCE=true`。

```bash
bash scripts/local_production_stack.sh
```

本机长期使用不要靠手工反复执行全量导入；安装每日刷新任务，让它只跑增量和审计：

```bash
bash scripts/install_daily_update_systemd_user.sh --enable
python3 scripts/audit_daily_update_schedule.py \
  --require-latest-run \
  --output artifacts/daily-update-local/daily-update-schedule-audit.json
```

该 timer 默认在用户级 systemd 下安装 `ai-quant-daily-update.timer`，工作日 07:00 和 18:30 后触发 `scripts/run_daily_data_update.sh`。早上用于补美股上一交易日，晚上用于补 A 股当日可取 EOD；`scripts/daily_data_update_pipeline.py` 在未显式传 `--end-date` 时，会按市场时区和 ready window 选择目标日期：A 股默认 Asia/Shanghai 18:00 后才请求当天，美股默认 America/New_York 18:00 后才请求当天，否则回退到上一工作日。包装脚本会拉起 Compose 本机生产栈，调用 `scripts/daily_data_update_pipeline.py`，先把 A 股证券目录按当前 baostock active common-stock universe 刷成 `in_scope/reference_only`，再按 `AI_QUANT_DAILY_ASHARE_BATCH_SIZE=300`、美股 Yahoo 按 `AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true` 刷新 `market_data_refresh_scope`，只让一个 common-equity active refresh record per ticker 进入 `AI_QUANT_DAILY_US_TICKERS_FROM_DB=true` 与 `AI_QUANT_DAILY_US_BATCH_SIZE=300` 的 PostgreSQL securities universe 分批续跑；preferred/重复/特殊 ticker 和已判定 stale 的 Yahoo ticker 保留历史 K 线但不再计入 active refresh 覆盖率。动态配置严格刷新也默认启用：它先校验全部 38 个公开序列，来源不完整时整批不写入，完整批次才更新不可变 observation revision、纸面决策和哈希链账本。进度都记录在 `artifacts/daily-update-local/state.json`，并记录每批实际写入行数，便于区分新增写入和 `skipped_current`；latest analysis 仍只使用 `AI_QUANT_DAILY_US_TICKERS`/`--us-tickers` 指定的重点标的，语义检索由 `AI_QUANT_DAILY_LATEST_ANALYSIS_SEMANTIC_TIMEOUT_SECONDS` 做短超时降级，避免全量行情批次或慢检索拖慢分析闭环。TDX 默认只做 `audit_tdx_vipdoc_postgres_coverage.py` 覆盖审计，只有显式设置 `AI_QUANT_DAILY_TDX_INCREMENTAL=true` 才会导入本地 `.day` 文件。研报资产绑定、daily insight、K 线 typed-only 审计、延迟审计和本机生产审计都会产出按 run id 隔离的 artifact，并更新 `artifacts/daily-update-local/latest-run.json`。K 线只写 PostgreSQL typed 表 `ai_quant.market_data_bars`，`ai_quant.records(collection='market_data')` 必须保持为 0；不会 JSON/数据库双写，不接真实券商，也不会自动下单。`artifacts/daily-update-local` 是宿主用户可写目录，避免旧容器 root-owned artifact 影响 timer。

本地 compose 默认挂载当前工作区的 `app/`、`scripts/`、`docs/`、`tasks/`，所以日常修复脚本或页面后只需 `docker compose up -d ai-quant-org` 重启服务，不依赖重新构建镜像。需要从零构建依赖镜像时显式设置 `AI_QUANT_STACK_REBUILD=true bash scripts/local_production_stack.sh` 或 `AI_QUANT_DAILY_REBUILD=true bash scripts/run_daily_data_update.sh`。

只复核接口延迟时可独立运行：

```bash
python3 scripts/latency_audit.py \
  --base-url http://127.0.0.1:8000 \
  --max-ms 7000 \
  --output artifacts/daily-update-local/latency-audit-smoke.json
```

如果只想先生成 unit 文件而不启用 timer：

```bash
bash scripts/install_daily_update_systemd_user.sh
systemctl --user daemon-reload
systemctl --user enable --now ai-quant-daily-update.timer
```

手工立即跑一次完整每日链路可用：

```bash
bash scripts/run_daily_data_update.sh
```

常用覆盖变量：

- `AI_QUANT_DAILY_REBUILD=true`：刷新前重建 Compose 镜像。
- `AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH=true`：先按 baostock 当前 active universe 刷新 A 股证券 scope。
- `AI_QUANT_DAILY_RUN_ASHARE_INCREMENTAL=false`：临时跳过 baostock 分批增量，只跑审计和分析。
- `AI_QUANT_DAILY_ASHARE_OFFSET=600`：从指定 A 股 universe offset 续跑。
- `AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true`：先刷新美股 Yahoo active refresh universe，过滤 preferred/重复/特殊 ticker。
- `AI_QUANT_DAILY_TDX_INCREMENTAL=true`：在覆盖审计外追加本地 TDX `.day` 增量导入。
- `AI_QUANT_DAILY_RUN_DYNAMIC_ALLOCATION=true`：运行 38 序列严格刷新、当前纸面决策与账本追加；正式 timer 默认 true。
- `AI_QUANT_DAILY_ALLOW_DYNAMIC_ALLOCATION_FAILURE=false`：动态配置刷新失败时是否允许其余每日链路继续；正式 timer 默认 false，避免长期保留过期的 4/8 因子状态。
- `AI_QUANT_DAILY_DYNAMIC_ALLOCATION_TIMEOUT_SECONDS=1800`：动态配置公开源刷新单步超时。
- `AI_QUANT_DAILY_LATEST_ANALYSIS_SEMANTIC_TIMEOUT_SECONDS=8`：限制 latest analysis 内部每次语义检索时长，超时降级为 `needs_review`，不阻塞后续 daily insight 和审计。
- `AI_QUANT_DAILY_SKIP_RESEARCH_BINDING=true`、`AI_QUANT_DAILY_SKIP_LATEST_ANALYSIS=true`、`AI_QUANT_DAILY_SKIP_LOCAL_PRODUCTION_AUDIT=true`：仅用于轻量 smoke，正式 timer 保持默认 false。
- `AI_QUANT_DAILY_MIN_DIRECT_EVIDENCE_COMPANIES=7`：daily insight 至少要求多少家公司有直接研报证据。

本机脚本默认把 readiness evidence 记录到 `artifact://staging-local/...`。若部署目标明确为个人本机长期使用，可运行 `python3 scripts/local_production_audit.py --base-url http://127.0.0.1:8000 --output artifacts/local-production-audit.json`，用本机生产审计口径确认 PostgreSQLStore、S3/MinIO、OpenSearch、TDX、LLM/PaddleOCR 配置、vision gate 和 9 个 readiness checklist 均已通过。LLM 与 PaddleOCR-VL 密钥注入后，再运行 `.venv/bin/python scripts/local_ai_capability_acceptance.py --base-url http://127.0.0.1:8000 --output artifacts/local-ai-capability-acceptance.json`，以最小 LLM chat 和单页 PDF OCR 冒烟生成脱敏能力证据；脚本只保存模型、页数、耗时、缓存命中和短文本预览，不保存 token、签名结果 URL 或完整上游响应。完成审计可用 `python3 scripts/project_completion_audit.py --local-production-audit artifacts/local-production-audit.json --local-ai-acceptance artifacts/local-ai-capability-acceptance.json --output artifacts/project-completion-audit.json`，该结果只对当前机器有效，不会放宽非本机组织级发布门禁；对外/多机生产签批 manifest 必须改成真实 staging/production 归档 URI，例如受控 S3/OSS/GCS bucket、生产 artifact store 或内部证据系统的具体对象路径，不要复用本机 namespace。

若宿主机已有同类服务占用默认端口，可用以下变量覆盖：

```bash
AI_QUANT_POSTGRES_HOST_PORT=15432 \
AI_QUANT_S3_HOST_PORT=19000 \
AI_QUANT_S3_CONSOLE_HOST_PORT=19001 \
AI_QUANT_OPENSEARCH_HOST_PORT=19200 \
AI_QUANT_OPENSEARCH_MONITOR_PORT=19600 \
AI_QUANT_NEO4J_HTTP_HOST_PORT=17474 \
AI_QUANT_NEO4J_BOLT_HOST_PORT=17687 \
AI_QUANT_QDRANT_HOST_PORT=16333 \
AI_QUANT_QDRANT_GRPC_HOST_PORT=16334 \
AI_QUANT_OTEL_HOST_PORT=14318 \
AI_QUANT_OTEL_GRPC_HOST_PORT=14317 \
AI_QUANT_OTEL_PROM_HOST_PORT=18889 \
AI_QUANT_OPENLINEAGE_HOST_PORT=15001 \
AI_QUANT_MLFLOW_HOST_PORT=15002 \
AI_QUANT_CROSS_BROWSER_MATRIX=artifacts/ui-cross-browser-matrix.example.json \
bash scripts/local_staging_stack.sh
```

本机 staging 已验证的通过口径：`/api/health` 返回 `PostgreSQLStore`；对象存储为 S3/MinIO；检索为 OpenSearch；模拟成交通过且 `live_execution_allowed=false`；图谱回溯率 100%；HTTP 容量基线无 breach；Headless Chrome 桌面/移动截图只作为 `production_ui_screenshot_acceptance` 证据，真实 `cross_browser_acceptance` 必须附加通过校验的跨浏览器矩阵；PostgreSQL、S3/MinIO、OpenSearch、OTel、Neo4j、Qdrant、OpenLineage 和 MLflow 均可达；Neo4j/Qdrant/OpenLineage/MLflow outbox 演练通过；`scripts/local_backup_restore_drill.py` 会对 PostgreSQL 执行 `pg_dump/pg_restore` 到临时库并回填 `backup_restore_drill`；`scripts/staging_governance_acceptance.py` 会执行权限红队 403/audit 验证、来源合规复核并回填 `permission_red_team_test` 和 `compliance_review_record`；`scripts/staging_security_acceptance.py` 会验证密钥轮换 metadata-only、真实密钥值拒绝入库、公开来源 provenance 台账、最小权限存储模板、cache retention run、runtime cache executor 和外部 lifecycle/search/KMS-DLP executor 证据回填；`scripts/staging_otel_acceptance.py` 会直连 OpenTelemetry collector `/v1/logs`、`/v1/metrics` 和 `/v1/traces`，并触发 workflow 告警、通知 outbox 和发送状态机后回填 `otel_collector_drill`；`scripts/staging_lineage_registry_acceptance.py` 会把 OpenLineage/MLflow outbox 通过本地 HTTP sink 发送，验证 webhook sender 的 POST、响应记录和失败重试演练；在 Compose 内运行时该脚本使用 `http://openlineage:5000/openlineage` 和 `http://mlflow:5000/mlflow` 作为应用容器可访问的发送目标，并用宿主机端口变量做健康检查；`scripts/staging_graph_vector_acceptance.py` 会把 `/api/graph/neo4j/export` payload 直写 Neo4j、把 `/api/search/qdrant/export` points 直写 Qdrant collection，并执行失败 outbox 重试演练；`scripts/staging_vision_gate_acceptance.py` 会登记 A/H/U 主体映射金标、运行双语 benchmark、回写季度事故演练，并在所有非 launch gate 通过后记录 `launch_checklist`。本机 Compose 链路默认用 `AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS=2000` 作为 HTTP 验收基线余量；生产/预发可把该变量或 `scripts/staging_acceptance.py --capacity-default-threshold-ms` 调回 1000 或更严格阈值。若机器未安装 Docker/Podman，该脚本会退出并提示安装容器运行时；没有容器运行时无法在本机真实启动上述依赖。

可选外部 adapter 目标：

- `AI_QUANT_NEO4J_SYNC_TARGET`
- `AI_QUANT_QDRANT_SYNC_TARGET`
- `AI_QUANT_OPENLINEAGE_TARGET`
- `AI_QUANT_MLFLOW_TRACKING_URI`
- `AI_QUANT_SECRET_MANAGER_PROVIDER`

生成上线验收证据包，并把缺失证据分派到 outbox：

```bash
python3 - <<'PY'
from app.api import create_default_router

router = create_default_router()
package = router.dispatch("POST", "/api/readiness/evidence-package", {"record_export": True, "include_passed": True}, role="CEO", actor="release_owner")
print(package.data["status"], package.data["missing_evidence_count"], package.data["pending_checklist"])
notify = router.dispatch("POST", "/api/readiness/evidence-package/notify", {}, role="risk_compliance", actor="release_owner")
print(notify.data["notification_count"], notify.data["usage_boundary"])
PY
```

检查项：

- `/api/health` 返回 `status=ok`
- `/api/metrics` 返回 store、object_store、search_index
- `/ui` 可以加载，并包含目标信息架构
- `/api/demo/full-flow` 可以生成端到端 demo
- `/api/execution-intents/{intent_id}/simulate` 只生成模拟成交并写入组合流水，不连接真实券商
- `/api/alerts/rules/seed` 和 `/api/alerts/evaluate` 可运行
- PostgreSQL/S3/OpenSearch 使用生产账号和最小权限
- SEC/HKEX/A 股 connector 设置了合规 user agent

## 4. 备份与恢复

- PostgreSQL：每日全量备份，关键上线前手动快照；恢复后运行 smoke test。
- SQLite：停写后备份 `AI_QUANT_DB` 文件；迁移生产前优先导入 PostgreSQL。
- S3：开启 bucket versioning；原文对象不覆盖，只新增版本。
- OpenSearch：可从 records/search source 重建；索引快照用于快速恢复。

## 5. 回滚步骤

1. 停止新版本写入。
2. 恢复上一版本镜像和环境变量。
3. 如 schema 已变更，优先使用备份恢复；未验证前不手工删列或删数据。
4. 运行上线前检查。
5. 在 operating report 或 incident report 中记录回滚原因、影响范围和后续动作。

## 6. 月度运维检查

- 审查 source registry 和 rights tag 是否仍有效。
- 检查开放告警、开放例外、人工复核队列和失败 schedule。
- 抽样验证 evidence locator、object_uri、content_sha256。
- 检查 PostgreSQL 备份可恢复性、S3 versioning、OpenSearch fallback。
- 复盘 incident playbook 和 drill schedule 执行结果。
