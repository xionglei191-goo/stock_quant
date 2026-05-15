# 生产部署 Runbook

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
| `AI_QUANT_SEC_USER_AGENT` | SEC EDGAR 请求标识 | 必须包含团队或联系邮箱 |
| `AI_QUANT_ASHARE_USER_AGENT` | A 股公告请求标识 | 使用统一生产标识 |
| `AI_QUANT_HKEX_USER_AGENT` | HKEX 请求标识 | 使用统一生产标识 |

## 2. 首次部署

1. 复制 `.env.example` 为环境配置模板，并通过部署系统注入真实密钥。
2. PostgreSQL 执行 `docs/postgresql-schema.sql`；或启动服务时由 `PostgreSQLStore` 初始化 schema。
3. 若从 SQLite 迁移，先停止写入，再执行：

```bash
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db postgresql://user:password@host:5432/ai_quant --replace
```

4. 配置对象存储 bucket、访问密钥、版本化和备份策略。
5. 配置 OpenSearch endpoint、索引名、账号和 fallback。
6. 启动服务：

```bash
python3 -m app.server
```

7. 运行上线前检查。

## 3. 上线前检查

```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
python3 scripts/capacity_baseline.py --records 100
python3 scripts/full_run_acceptance.py --capacity-records 10
python3 scripts/smoke_test.py http://127.0.0.1:8000
```

进入 staging 后，对真实部署地址执行 HTTP 验收。该脚本只会使用模拟成交，不会开启真实券商或自动下单：

```bash
AI_QUANT_STAGING_URL=https://staging.example.internal \
AI_QUANT_STAGING_ARTIFACT_PREFIX=s3://ai-quant-staging-artifacts/readiness/$(date +%Y%m%d) \
AI_QUANT_POSTGRES_DSN=postgresql://... \
AI_QUANT_S3_BUCKET=ai-quant-staging \
AI_QUANT_OPENSEARCH_URL=https://search.example.internal \
AI_QUANT_OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.internal/v1/logs \
python3 scripts/staging_acceptance.py --record-readiness --notify-missing
```

本机全量 staging 栈可直接用 Compose 启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector，以及 OpenLineage/MLflow HTTP 占位端点并自动跑验收：

```bash
bash scripts/local_staging_stack.sh
```

本机 staging 已验证的通过口径：`/api/health` 返回 `PostgreSQLStore`；对象存储为 S3/MinIO；检索为 OpenSearch；模拟成交通过且 `live_execution_allowed=false`；图谱回溯率 100%；HTTP 容量基线无 breach；PostgreSQL、S3/MinIO、OpenSearch、OTel、Neo4j、Qdrant、OpenLineage 和 MLflow 均可达；Neo4j/Qdrant/OpenLineage/MLflow outbox 演练通过。最近一次本机复验 `p95=114ms`。若机器未安装 Docker/Podman，该脚本会退出并提示安装容器运行时；没有容器运行时无法在本机真实启动上述依赖。

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
package = router.dispatch("POST", "/api/readiness/evidence-package", {"record_export": True}, role="CEO", actor="release_owner")
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
