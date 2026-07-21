# 公司情报与市场综合分析平台

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-07-17
- Related tasks: T-431, T-424, T-573, T-575, T-581, T-582, T-583, T-584, T-585, T-586, T-587, T-588, T-589, T-590, T-591, T-598
- Scope: 产品定位、本机运行入口、数据边界与当前验收快照
- Non-goals: 真实券商连接、自动下单、将本机证据声明为非本机生产发布证据

本项目是一个本地优先的公司情报与市场综合分析平台。核心目标是为每只股票/公司建立结构化与非结构化结合的全天候数据库，支持公司画像、事件时间线、关系图谱、研报观点追踪、观察任务、分析结论记录和模拟反馈复盘。

系统用于投资研究、证据整理和分析有效性验证，不连接真实券商，不做自动下单，也不是实时量化交易平台。既有的投委会、签批、执行意图和生产发布门禁能力保留为兼容/运维模块，但不再作为产品主叙事。

## 核心主线

```text
数据入湖 -> 公司画像 -> 事件时间线 -> 关系图谱 -> 多源观点 -> 观察任务 -> 分析结论 -> 模拟反馈
```

核心价值：

- 每只股票建立可持续更新的公司级数据库。
- 结构化管理行情、财务、公告、公司事件和实体关系。
- 将研报、新闻、政策、网页和本地文件作为可回链的非结构化情报来源。
- 把研报作为关注度信号、观点样本库和分析师可靠性复盘来源。
- 用模拟交易和观察反馈验证分析结论是否有效，不触发真实交易。

## 数据与研报边界

事实层优先使用公告、财报、监管披露、公司 IR、公开/已提供行情和其他可信来源。研报属于观点层：可以用于筛选关注池、结构化机构观点、记录目标价/评级/盈利预测和复盘分析师可靠性，但不能直接作为事实真相源、训练源或真实交易触发源。

## 目录

- `app/`: 应用代码
- `tests/`: 单元测试
- `docs/`: 项目与架构文档
- `tasks/`: 执行待办清单

## Python 支持矩阵

- Python `3.11`
- Python `3.12`

## 运行测试

```bash
python3 -m pip install '.[test]'
python3 -m unittest discover -s tests
python3 -m py_compile app/*.py tests/*.py scripts/*.py
```

单测默认会隔离本机 `AI_QUANT_*` 变量，不需要手工清理本地 `.env`。

日常本机质量门可直接执行：

```bash
make local-ci
```

## 动态资产配置与风险控制

该模块长期持有美国资产，但只输出 paper-only 目标仓位，不输出买卖指令。第一阶段资产池为 `SPY`、`QQQ`、`SGOV`，股票风险仓位限定为 `10%/30%/50%/70%/90%`。PIT 数据、八类因子、规则与 ML 对照、Fractional Kelly、walk-forward 回测和决策快照均保留解释与数据回链。

安装研究与 Dashboard 依赖：

```bash
python3 -m pip install '.[dynamic-allocation-analysis,dynamic-allocation-ml,dynamic-allocation-dashboard]'
```

主 API 启动后，可单独启动 Streamlit 研究页面：

```bash
AI_QUANT_API_BASE_URL=http://127.0.0.1:8000 streamlit run app/dynamic_allocation/dashboard/app.py --server.port 8501
```

首次运行先接入官方免密公开数据并生成当前纸面决策：

```bash
python3 scripts/backfill_dynamic_allocation_public_data.py \
  --market-start 2000-01-01 \
  --persist-decision \
  --output /tmp/dynamic-allocation-public-data.json
```

脚本接入 FRED、Cboe、FINRA 和项目已治理的 Yahoo EOD，要求 38/38 序列和关键 freshness 全部通过才返回成功。同一天重复运行读取本地原始响应缓存并保持幂等；缓存目录可用 `AI_QUANT_DYNAMIC_ALLOCATION_CACHE` 调整。免费源无法提供的历史 Forward PE、FCF Yield、专有 ISM 和 survivorship-safe 市场宽度使用明确命名的价格/工业生产代理，代理公式和 `backtest_eligible=false` 会进入 observation lineage。当前修订版回填只允许形成当前纸面决策，不能作为历史 walk-forward 的 PIT 证据。

日常运行默认是只读预览；显式执行会刷新数据、持久化决策、追加 JSONL 哈希链并生成本机运营报告：

```bash
python3 scripts/dynamic_allocation_daily_run.py
python3 scripts/dynamic_allocation_daily_run.py \
  --execute \
  --ledger data/local/dynamic-allocation-paper.jsonl \
  --output artifacts/dynamic-allocation/daily-run-latest.json \
  --history-dir artifacts/dynamic-allocation/daily-history
```

纵向运营报告默认只读，校验账本哈希链并按月汇总成功、失败和数据健康状态，同时显示 3/6/12 个月复核门；只有显式 `--execute --output` 才写盘：

```bash
python3 scripts/dynamic_allocation_operations_report.py \
  --ledger data/local/dynamic-allocation-paper.jsonl \
  --daily-report artifacts/dynamic-allocation/daily-run-latest.json \
  --daily-reports artifacts/dynamic-allocation/daily-history \
  --performance-input /absolute/path/to/forward-paper-performance.json
```

可选绩效输入必须符合 `dynamic-allocation-paper-performance/v1`，使用显式市场日历和 SPY/QQQ/SGOV adjusted-close 来源，仅计算决策发布后的次期纸面 NAV、基准、回撤、换手和费用。缺失开市日、缺价、未来数据或当前区间内才出现的信号都会阻断绩效门。即使绩效覆盖完整，仍需到期后的具名人工复核才能改变 `efficacy_proven`；当前记录不满足该条件。

本机 systemd 用户级 timer 模板也默认只打印、不安装、不启用。必须提供绝对路径；显式 `--execute --install-dir` 只写 unit 文件，仍需人工审查后启用：

```bash
python3 scripts/dynamic_allocation_scheduler_template.py \
  --project-root /absolute/path/to/sotck_quant \
  --python /absolute/path/to/python \
  --state-dir /absolute/path/to/sotck_quant/data/local \
  --artifact-dir /absolute/path/to/sotck_quant/artifacts/dynamic-allocation
```

Kelly 输入优先使用调用方同时提供的 `expected_return` 与 `volatility`。未显式提供时，系统使用最近 10 年 SPY `return_3m` 的非重叠季度末样本；至少 24 个样本才可用，并披露收益上限、波动下限、置信收缩、样本区间和 observation lineage。该估计只用于当前纸面风险裁剪，不是收益保证，也不能替代真实历史 vintage 回测。

已有决策快照也可单独校验或追加账本；只有显式 `--execute --output` 才写盘：

```bash
python3 scripts/dynamic_allocation_paper_run.py --input /path/to/decision.json
python3 scripts/dynamic_allocation_paper_run.py --input /path/to/decision.json --execute --output data/local/dynamic-allocation-paper.jsonl
```

架构与接口说明见 `docs/dynamic-asset-allocation-architecture.md`、`docs/dynamic-allocation-operations.md` 和 `docs/api-contracts.md`。本机纸面记录不是非本机发布证据，且项目仍不连接券商、不自动下单。

## 公开基础信息回填

本机生产闭环使用公开/本地来源补齐公司基础画像，不接真实券商、不做自动下单。全量回填行业、板块、估值快照和公司详情：

```bash
python3 scripts/backfill_company_fundamentals_public.py --market both
python3 scripts/scope_public_company_universe.py
python3 scripts/backfill_company_financials_public.py --market A --ashare-max-pages 120
python3 scripts/backfill_us_cik_sec.py
python3 scripts/backfill_us_financials_sec_companyfacts.py --limit 50 --missing-only --min-market-cap 10000000000
python3 scripts/run_us_companyfacts_batches.py --batches 3 --batch-size 100 --min-market-cap 1000000000
python3 scripts/company_basic_info_production_audit.py
```

当前落库产物见 `artifacts/company-fundamentals-public-backfill-a.json`、`artifacts/company-fundamentals-public-backfill-u.json` 和 `artifacts/public-company-universe-scope.json`。A 股自动生产公司宇宙按当前公开公司信息命中结果收口；未命中的历史/异常 TDX 代码保留在证券目录，但退出自动产业链分析。
A 股财务摘要已覆盖自动生产公司宇宙；美股 SEC companyfacts 已按 `missing-only` 批处理补齐到明确状态。以下数量是 2026-07-17 对现有本机产物的文档重基线快照，不是实时指标：`4945/5412` 个 US issuer 有财务摘要，`467/5412` 个明确标记为 SEC companyfacts 不可得或缺 CIK，未知缺口为 `0`。复验来源为 `artifacts/company-fundamentals-public-backfill-u.json` 和 `scripts/company_basic_info_production_audit.py`；本机门禁当时输出 `ready_for_local_production_basic_info=true`。

本机长期运行口径的闭环产物快照（文档复核日期：2026-07-17；以产物内生成时间为实际新鲜度，不可作为非本机发布证据）：

- `artifacts/source-governance-fill.json`：31 个来源治理覆盖率 `1.0`。
- `artifacts/local-business-acceptance.json`：业务验收 `status=passed`、`failed_count=0`。
- `artifacts/latest-analysis/latest-analysis.json`：A 股 `600000/000001/300750/600519` 与美股 `AAPL/MSFT/NVDA/TSLA/SPY` 最新分析 `status=passed`，包含 `11702` 份本地研报和 `88515` 条受限研报引用证据的观点层召回。
- `artifacts/local-production-audit.json`：本机生产审计 `status=passed`、`ready_for_launch=true`。
- `artifacts/project-completion-audit.json`：本机个人生产目标 `status=achieved`。
- `docs/logic-map.md`：逻辑总地图入口，作为四条主线的第一入口。
- `docs/logic-chain-overview.md`：逻辑链条总览入口，串联公司情报、多维关系、最新分析和个人研究闭环。

## 文档导览

如果需要快速理解当前系统，建议先看：

1. [`docs/logic-map.md`](docs/logic-map.md) - 四条主线的第一入口。
2. [`docs/logic-chain-overview.md`](docs/logic-chain-overview.md) - 公司情报与逻辑链条总览。
3. [`docs/latest-analysis-chain.md`](docs/latest-analysis-chain.md) - 最新分析链路总览。
4. [`docs/multidimensional-relationship-closure.md`](docs/multidimensional-relationship-closure.md) - 多维关系链总收口证明。
5. [`docs/personal-research-loop-overview.md`](docs/personal-research-loop-overview.md) - 个人研究闭环总览。

新增研报采用本机 inbox 模式，不做外部登录或下载。默认把新文件放入宿主机研报目录 `/home/xionglei/文档/6大投行研报汇总/inbox`；服务容器会通过只读挂载在 `/data/local/research_reports/inbox` 扫描同一批文件。先 dry-run：

```bash
python3 scripts/research_report_inbox_ingest.py --base-url http://127.0.0.1:8000
```

确认候选和预算后执行首批登记/解析：

```bash
python3 scripts/research_report_inbox_ingest.py --base-url http://127.0.0.1:8000 --execute
```

输出为 `artifacts/research-report-inbox-ingest.json`。无可抽文本的 PDF/扫描件会进入人工复核队列；可抽文本的 TXT/MD 会生成受限 citation evidence。

从现有主体、证券、行情和本地研报索引构建最小公司数据库时，先 dry-run 检查目标公司画像和研报绑定计划：

```bash
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519,300750,600887
```

确认匹配结果后再落库；如需同时生成最小事件时间线、关系层、结构化研报观点和观察/结论/模拟反馈闭环，可追加 `--build-events --build-relationships --structure-reports --build-workflow`：

```bash
python3 scripts/build_company_database_minimum.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,600519,300750,600887 --build-events --build-relationships --structure-reports --build-workflow --execute
```

输出为 `artifacts/company-database-build.json`。研报绑定是观点层/关注度信号，默认 `needs_review`；研报覆盖事件和机构覆盖关系只表示关注度变化，不得作为事实真相源或真实交易触发源。`--build-workflow` 只生成观察任务、公司情报基线结论和 watch-only 模拟反馈，固定 paper-only，不连接券商。

## 启动服务

```bash
python3 -m app.server
```

默认启动地址：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/ui`

可用 `AI_QUANT_HOST` 和 `AI_QUANT_PORT` 覆盖监听地址。比如 8000 端口已有旧服务时，可以启动当前代码到临时端口做验收：

```bash
AI_QUANT_PORT=55537 python3 -m app.server
```

需要给本地图谱准备一组可探索的多社区样本时，可以运行 Obsidian 式知识网络 seed。该 seed 只写入本地公司、证券、产业位置、上市证券关系和 13F 持有人样本，不连接券商、不触发交易：

```bash
python3 scripts/seed_obsidian_knowledge_graph.py http://127.0.0.1:8000 --output artifacts/obsidian-knowledge-graph-seed.json
```

默认使用内存存储。需要重启后保留数据时，设置 `AI_QUANT_DB` 使用 SQLite 状态库：

```bash
AI_QUANT_DB=./data/state.db python3 -m app.server
```

如果本机 `.env` 已配置 `AI_QUANT_POSTGRES_DSN` 或 `AI_QUANT_DATABASE_URL`，服务会优先使用 PostgreSQL；未安装 `psycopg` 时裸跑会启动失败。需要临时用 SQLite 本地启动时，显式清空 Postgres DSN：

```bash
AI_QUANT_POSTGRES_DSN= AI_QUANT_DATABASE_URL= AI_QUANT_DB=./data/state.db python3 -m app.server
```

生产状态库可使用 PostgreSQL。先安装可选依赖 `psycopg`，再设置 `AI_QUANT_POSTGRES_DSN`；也可以直接让 `AI_QUANT_DB` 使用 `postgresql://` 或 `postgres://` DSN：

```bash
python3 -m pip install '.[postgres]'
AI_QUANT_POSTGRES_DSN=postgresql://user:password@localhost:5432/ai_quant python3 -m app.server
```

A 股增量脚本依赖 `baostock` + `psycopg`，可单独安装：

```bash
python3 -m pip install '.[market-data]'
```

从 SQLite 状态库迁移到 PostgreSQL 时，先运行默认的只读 preflight；正常迁移使用 target-wins 的 insert-only `merge`，保留 PostgreSQL 中已有记录和审计：

```bash
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db "$AI_QUANT_POSTGRES_DSN"
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db "$AI_QUANT_POSTGRES_DSN" --mode merge
```

`exact-replace` 仅用于经过审阅的例外恢复，必须提供最新 preflight 的计数绑定确认令牌和与当前目标库精确匹配、仍在保留期内的恢复验证备份；详见 `docs/postgresql-migrations.md`。兼容参数 `--replace` 也受同一门禁约束。

文档入湖会把原文保存到对象存储。默认是本地目录 `./data/objects`，也可以用 `AI_QUANT_OBJECT_STORE` 指定。仓库里的 `data/objects` 主要保留演示/测试样例；本地运行建议改用未纳管目录，例如 `./data/local/objects`：

```bash
AI_QUANT_DB=./data/state.db AI_QUANT_OBJECT_STORE=./data/local/objects python3 -m app.server
```

也可以切到 S3 兼容对象存储和 OpenSearch 兼容检索。实现只使用标准库 HTTP 客户端；未配置外部检索或外部检索异常时，`AI_QUANT_SEARCH_FALLBACK=true` 会回退到内置全文检索：

```bash
AI_QUANT_OBJECT_STORE_BACKEND=s3 \
AI_QUANT_S3_ENDPOINT=https://objects.example.com \
AI_QUANT_S3_BUCKET=ai-quant \
AI_QUANT_S3_ACCESS_KEY=... \
AI_QUANT_S3_SECRET_KEY=... \
AI_QUANT_SEARCH_BACKEND=opensearch \
AI_QUANT_OPENSEARCH_URL=https://search.example.com \
AI_QUANT_OPENSEARCH_INDEX=ai_quant_research \
python3 -m app.server
```

## 部署烟测

服务启动后运行：

```bash
python3 scripts/smoke_test.py http://127.0.0.1:8000
```

本地全链路验收可直接运行，不需要真实券商或外部生产环境；组合反馈环节固定使用模拟成交/模拟持仓 ledger：

```bash
python3 scripts/full_run_acceptance.py --capacity-records 10
```

预发布环境接入真实 PostgreSQL/S3/OpenSearch 等依赖后，运行 staging HTTP 验收。该脚本会回填已执行的 smoke/capacity readiness 记录，并保持交易为模拟成交：

```bash
AI_QUANT_STAGING_URL=https://staging.example.internal \
AI_QUANT_STAGING_ARTIFACT_PREFIX=s3://ai-quant-staging-artifacts/readiness/$(date +%Y%m%d) \
python3 scripts/staging_acceptance.py --record-readiness --notify-missing
```

UI 静态验收会检查左侧信息架构、顶部状态条、关键面板 ID 和前端脚本语法：

```bash
python3 scripts/ui_static_check.py
```

UI 点击联动验收会用 Headless Chrome 打开 `/ui` 并真实点击总览收益卡、研报观点证据、公司定位、产业链和模拟反馈/兼容方案入口，确认能切换到对应工作台并带入上下文：

```bash
python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance
```

提交或部署前可运行密钥与 `.env` 误提交检查：

```bash
python3 scripts/security_check.py .
```

Docker Compose：

```bash
docker compose up --build
```

本机全量 staging 栈会启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector，以及 OpenLineage/MLflow HTTP 占位端点，然后自动跑 staging 验收：

```bash
bash scripts/local_staging_stack.sh
```

以后只在本机长期使用时，建议直接运行本机个人生产入口。它会使用较少冲突的默认端口、显式把 app 容器固定到 PostgreSQL/S3/OpenSearch，并依次生成本机 staging readiness、本机生产审计和可选 LLM/PaddleOCR-VL 脱敏验收：

```bash
bash scripts/local_production_stack.sh
```

通过口径包括 PostgreSQLStore、S3/MinIO、OpenSearch、模拟成交、图谱回溯、HTTP 容量基线和外部依赖可达性。如果当前机器没有 Docker 或 Podman，脚本会直接提示安装容器运行时；没有容器运行时就无法在本机真实启动这些依赖。
宿主机端口可通过 `AI_QUANT_POSTGRES_HOST_PORT`、`AI_QUANT_S3_HOST_PORT`、`AI_QUANT_OPENSEARCH_HOST_PORT`、`AI_QUANT_NEO4J_HTTP_HOST_PORT`、`AI_QUANT_QDRANT_HOST_PORT`、`AI_QUANT_OTEL_HOST_PORT`、`AI_QUANT_OPENLINEAGE_HOST_PORT` 和 `AI_QUANT_MLFLOW_HOST_PORT` 等变量覆盖，避免和本机已有服务冲突。
当前 staging 验收会同时演练 Neo4j、Qdrant、OpenTelemetry、OpenLineage 和 MLflow 的外部配置与 outbox 通道，但仍固定为模拟交易，不连接真实券商。
本机脚本默认使用 `artifact://staging-local/...` 作为 evidence namespace；如果系统只在本机长期使用，可用 `python3 scripts/local_production_audit.py --base-url http://127.0.0.1:8000 --output artifacts/local-production-audit.json` 作为本机生产审计口径。LLM 与 PaddleOCR-VL 配好后，可运行 `.venv/bin/python scripts/local_ai_capability_acceptance.py --base-url http://127.0.0.1:8000 --output artifacts/local-ai-capability-acceptance.json`，生成不含 token、签名结果 URL 或完整模型响应的本机 AI 能力验收记录。该口径不等同于非本机组织级发布签批；对外/多机生产仍必须用真实 staging/production 归档 URI 回填 `artifacts/production-closure-manifest.json` 并通过严格 release gate。

大样本质量增强有独立的本机质量包入口。它会扫描本地文本/PDF材料，登记中英 benchmark 样本，运行现有抽取 benchmark，并导出 sample manifest、baseline report、annotation manual、bbox/table/summary 待标注文件和 readiness report；样本不足或指标不达标时仍会落盘 artifacts，但命令返回非零，便于 CI 阻断质量回归：

```bash
python3 scripts/fetch_benchmark_samples.py \
  --output-dir artifacts/benchmark-sample-fetch \
  --sec-ciks 0000320193,0000789019 \
  --ashare-codes 600519,600000,000001,300750 \
  --include-ashare-attachment-text \
  --sec-document-types 10-K,10-Q \
  --limit-per-symbol 2 \
  --user-agent 'company-intelligence-platform/0.1 contact@example.com'

python3 scripts/local_benchmark_quality_package.py \
  data/objects/ashare_exchange data/objects/sec_edgar docs artifacts/benchmark-sample-fetch \
  --output-dir artifacts/benchmark-quality-package \
  --benchmark-id bm_local_quality_20260518 \
  --target-sample-size 300 \
  --min-chinese-samples 150 \
  --min-english-samples 150 \
  --max-samples 500 \
  --artifact-prefix minio://ai-quant-local/benchmark-quality/20260518

python3 scripts/local_data_unblock_audit.py \
  --output artifacts/local-data-unblock-audit.json
```

A 股样本补齐仍只走已冻结的公开披露/本地材料边界。`--include-ashare-attachment-text` 会在公告列表只有标题时尝试下载附件并抽取正文；若交易所 CDN 返回封禁页、403 或附件无法抽出指标术语，脚本会在 `fetch-manifest.json` 的 `skipped` 中记录原因，不把无正文标题伪装成有效 benchmark 样本。
本机质量包建议把 `data/objects/ashare_exchange` 放在 `data/objects/sec_edgar` 前面，避免英文 SEC 样本先填满 `--max-samples` 后误报中文覆盖不足；`scripts/local_data_unblock_audit.py` 用来判断数据来源是否仍阻塞主体流程，它会把样本规模/中英覆盖/接口拉取失败与抽取质量缺口分开。当前自动质量包用于证明本机数据流和抽取回归可重复，最终大样本签批仍应以人工 gold label 与 readiness report 为准。
当前本机质量包已生成可复验绿灯 artifact：`sample_count=500`、`language_counts={en:335, zh:165}`、`run_passed=true`、`large_sample_ready=true`、`readiness_missing_requirements=[]`；`artifacts/local-data-unblock-audit.json` 为 `status=passed`、`data_blocked=false`。
当前 `scripts/production_task_closure_audit.py --local-benchmark-quality-package artifacts/benchmark-quality-package/quality-package.json --local-data-unblock-audit artifacts/local-data-unblock-audit.json` 会把 T-402 识别为本机证据已完成，剩余非本机组织级外部证据阻塞项为 16 个。

生产部署、备份、恢复、回滚和月度运维步骤见 [docs/production-runbook.md](./docs/production-runbook.md)。环境变量模板见 [.env.example](./.env.example)。

## 当前实现范围

- 三市场 source registry 与权限标签
- 上交所 A 股最近公告检索预览和入湖
- SEC EDGAR 最近 filings 元数据抓取和可选正文入湖
- HKEXnews 最近公告检索预览和入湖
- 公开/已提供 EOD/延时行情点入库，包含 source rights 校验、实时数据阻断、红区来源阻断和 dashboard 摘要
- 13F 持仓记录入库，并可生成中低频拥挤度 snapshot
- HTML 文档正文清洗并生成可读证据片段
- PDF 对象文本流/Flate 流抽取兜底，可从本地 PDF 对象生成证据片段
- `/api/document-parsing/paddleocr` PaddleOCR-VL 文档解析备用接口，证据抽取在本地解析无文本且配置 token 时会自动兜底
- `/api/market-data/tdx/preview` 与 `/api/market-data/tdx/import` 读取项目内通达信 `vipdoc/*.day` 日线文件并导入公开/已提供 EOD 行情
- `/api/research-reports/scan`、`/api/research-reports/extraction-queue` 与 `scripts/research_report_inbox_ingest.py` 维护本地研报 manifest、抽取/OCR 队列和新增研报 inbox；研报默认只作为本地参考观点层，最新分析与 UI 已展示研报观点证据，不进入事实源、训练源或真实交易信号
- 免费 A 股补充接口候选会以 `a-stock-data` 生态为参考登记，但默认只作为人工参考或补充研究，不替代本地通达信和官方公开披露核心数据
- 宏观主题、热点扩散和产业链公司定位将作为知识图谱一等能力：从热点词扩展到上下游节点、相关公司、数据槽位、证据缺口和后续研究任务
- 术语、数值、期间和规则表格读取基线抽取，并可按中英 benchmark 样本集运行阈值、定位、表格和低置信度拦截评估
- Issuer / Security / MarketDataPoint / Document / Evidence / Thesis / Signal / Decision / Review，其中 Issuer/Security/Document/Evidence 是公司情报主数据底座，Thesis/Decision/Review 作为旧研究结论与复盘兼容对象继续保留
- CorporateAction 用于拆股、分红、代码变更等复权和估值链路
- `/api/market-data/adjusted` 提供 `raw`、`backward`、`forward` 复权计算视图；现金分红只作为公司行动返回，不默认混入价格因子
- `/api/market-data/returns` 基于复权价格输出收益序列、累计收益、波动和最大回撤；默认价格收益，传 `total_return_method=cash_dividend_reinvested` 时计入 ex-date 现金分红
- `/api/portfolio/returns` 将多个证券的公开复权收益按权重聚合为组合级收益、波动和回撤，仍保持 paper-only
- `/api/portfolio/valuation` 用 as-of 前最近公开行情价计算持仓市值、权重、现金权重和缺失价格清单
- `/api/portfolio/transactions` 和 `/api/portfolio/positions` 记录交易流水并按 as-of 派生持仓，供月报绩效和归因复算
- 英文 evidence 优先的研究问答与中文摘要审计，保留 summary/prompt/model 版本、人工覆核状态和答案级质量/复核队列报告
- `/api/company-profiles`、`/api/company-events`、`/api/company-relationships`、`/api/research-reports/structured`、`/api/research-report-viewpoints`、`/api/observation-items`、`/api/analysis-conclusions` 和 `/api/simulation-feedback` 提供公司情报平台的一等对象写入与查询入口
- `/api/company-intelligence/{symbol}` 按股票代码聚合公司画像、行情、事件、关系图谱、结构化研报、研报观点、观察任务、分析结论和模拟反馈；`SPCX` 可作为默认输入，未入库时返回下一步研究入口
- benchmark、prompt 版本记录、scorecard、research card
- Reg FD / non-display 合规闸门
- 旧 approved decision 到纸面执行意图和模拟持仓反馈的兼容闸门；新路线应以分析结论和模拟反馈为中心
- 13F institutional holding、crowding、8-K/6-K/20-F disclosure event、challenger、playbook、incident report、drill schedule
- Black-Litterman 纸面组合原型，支持观点置信度/Omega、风险预算、禁投清单、压力测试和 walk-forward 诊断
- dashboard、graph/evidence/portfolio query、macro theme / industry chain / company positioning query、review query
- 可选 SQLite / PostgreSQL 持久化，覆盖核心对象、旧审批签字兼容记录和审计日志
- `/ui` 静态单页界面，主路径已调整为公司情报工作台，覆盖总览、公司画像、事件/关系、研报观点、观察结论、模拟反馈和旧运营/审批兼容入口
- UI 静态验收脚本，覆盖 `pic/UI.png` 对应的左侧信息架构、顶部市场/风险/冲突状态和关键控件存在性
- `/api/demo/full-flow` 生成一套可展示的端到端 demo 数据
- operating report 与 strategy replay，覆盖月报红灯项、治理指标、TWR/最大回撤/换手/信息比率、发布审批和版本化决策回放
- `/api/search` 内置全文检索 fallback，跨 Document、Evidence、Thesis、Research Card 搜索
- 对象存储 adapter：本地文件默认，S3 兼容存储可通过环境变量启用；Document 记录 `object_uri` 和 `content_sha256`
- 检索 adapter：本地全文检索默认，OpenSearch 兼容检索可通过环境变量启用，异常时可回退本地检索
- 批量 ingestion job，支持 connector normalize、去重、错误记录和任务状态查询
- 采集调度 schedule，支持 cadence、retry_limit、最近 job 状态和失败重试
- `/api/health` 与 `/api/metrics`，提供最小部署健康检查和运行指标
- `/api/alerts` 告警闭环，支持默认规则播种、指标评估、开放告警查询、恢复状态、通知 outbox 和基于 playbook 的事故自动建单
- Evidence extraction 支持 `\f` 分页文本，记录 `page_no` 和稳定 locator
- 扫描件/空文本会优先尝试 PaddleOCR-VL 备用解析；未配置或解析失败时进入人工复核队列，并提供 evidence quality report

## 说明

当前实现是 MVP 后端与前端初版，重点是把公司情报所需的核心对象、接口、治理规则、最小持久化和可操作页面落成可测试代码。A/H/U 三市场公告/filing 真实检索已补上最小入口；状态库、对象存储和检索已具备本地 fallback 与生产 adapter 边界。公司画像、事件时间线、关系图谱、研报观点追踪、观察任务、分析结论和模拟反馈闭环已有最小可验收实现；专用图谱/向量存储、复杂 OCR/PDF、真实外部环境压测和前端生产化验收属于增强项。

## 存储与检索配置

| 能力 | 默认 | 生产适配 |
|---|---|---|
| 状态库 | 内存；`AI_QUANT_DB` 后启用 SQLite | `AI_QUANT_POSTGRES_DSN` 或 PostgreSQL DSN 形式的 `AI_QUANT_DB` 启用 PostgreSQLStore |
| 对象存储 | `AI_QUANT_OBJECT_STORE_BACKEND=local` | `AI_QUANT_OBJECT_STORE_BACKEND=s3`，配置 `AI_QUANT_S3_*` |
| 全文检索 | `AI_QUANT_SEARCH_BACKEND=local` | `AI_QUANT_SEARCH_BACKEND=opensearch`，配置 `AI_QUANT_OPENSEARCH_*` |
| 检索降级 | 本地检索 | `AI_QUANT_SEARCH_FALLBACK=true` 时外部检索失败会回退本地 |

## 大模型中转站

服务提供 OpenAI / Anthropic 兼容上游的内部中转接口。默认模型为 `qwen3.6-plus`，默认上游地址为 `https://llm.nananobanana.cn`。API key 不应写入仓库，请通过环境变量注入：

```bash
export AI_QUANT_LLM_BASE_URL=https://llm.nananobanana.cn
export AI_QUANT_LLM_API_KEY=...
export AI_QUANT_LLM_DEFAULT_MODEL=qwen3.6-plus
```

OpenAI 兼容入口：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/llm/openai/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"messages":[{"role":"user","content":"用一句话说明今天的研究重点"}]}'
```

Anthropic 兼容入口：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/llm/anthropic/messages \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"max_tokens":256,"messages":[{"role":"user","content":"用一句话说明今天的研究重点"}]}'
```

生产工作流入口会先登记已审批 prompt 模板，再按任务运行并记录模型、prompt 版本、成本估算、延迟、回退路径和人工复核标记：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/llm/task-templates/seed \
  -H 'X-Role: nlp_ml'

curl -sS -X POST http://127.0.0.1:8000/api/llm/tasks/run \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"template_id":"llmtpl_filing_qa_v1","role":"分析师","variables":{"question":"收入变化是什么？","source_text":"Revenue rose 12% year over year."}}'

curl -sS http://127.0.0.1:8000/api/llm/tasks/metrics \
  -H 'X-Role: nlp_ml'
```

## 任务编排与血缘

M9 生产治理底座提供轻量 DAG、运行记录、血缘事件和模型版本接口。现阶段它不替代 Airflow/Dagster，而是先固定幂等键、输入输出引用、代码版本、模型版本和 prompt 版本，确保任何解析、抽取、索引、benchmark 或投研打包任务都能被审计和 replay。

```bash
curl -sS -X POST http://127.0.0.1:8000/api/orchestration/dags \
  -H 'Content-Type: application/json' \
  -H 'X-Role: platform' \
  -d '{"dag_id":"dag_daily_research","name":"Daily research pipeline","idempotency_key_fields":["as_of_date"],"tasks":[{"task_id":"collect_filings"},{"task_id":"extract_evidence"}]}'

curl -sS -X POST http://127.0.0.1:8000/api/orchestration/dags/dag_daily_research/run \
  -H 'Content-Type: application/json' \
  -H 'X-Role: platform' \
  -d '{"inputs":{"as_of_date":"2026-05-15"}}'
```

## A 股补充接口集合

`a-stock-data` 这类外部接口先进入候选注册表，逐项声明来源、字段映射、限速、是否需要 key、rights tag 和验证状态。默认只作为人工参考或补充研究，不替代本地通达信和官方公开披露核心数据。

```bash
curl -sS -X POST http://127.0.0.1:8000/api/connectors/astock/seed \
  -H 'X-Role: data_engineer'

curl -sS -X POST http://127.0.0.1:8000/api/connectors/astock/verify \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"connector_id":"eastmoney_research","status":"passed"}'
```

## 图谱与语义检索

`/api/graph/query` 保留证据、观点、决策和复盘的关系回查；`/api/graph/knowledge-network/readiness` 只读检查公司图谱是否具备 Obsidian 式可探索网络所需的数据密度，输出缺失层、薄弱层、社区来源、跨层链接和 seed 依赖度；`/api/search/semantic` 提供本地轻量语义检索 adapter，当前用 term-frequency cosine 固定接口和权限边界，后续可替换为 Qdrant/embedding/reranker。

```bash
python3 scripts/graph_knowledge_network_readiness.py http://127.0.0.1:8000 \
  --issuer-id issuer_aapl \
  --output artifacts/graph-knowledge-network-readiness-aapl.json

python3 scripts/backfill_knowledge_network_evidence.py http://127.0.0.1:8000 \
  --issuer-id issuer_aapl \
  --execute \
  --output artifacts/knowledge-network-evidence-backfill-aapl.json

python3 scripts/backfill_knowledge_network_evidence_links.py http://127.0.0.1:8000 \
  --issuer-id issuer_aapl \
  --execute \
  --output artifacts/knowledge-network-evidence-link-backfill-aapl.json

# 宿主机直连本机 Compose PostgreSQL 时，用 127.0.0.1:15432 覆盖容器内 DSN。
AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant \
python3 scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 \
  --audit-only \
  --market A,U \
  --limit 50

AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant \
python3 scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 \
  --dry-run \
  --market A,U \
  --limit 100 \
  --batch-size 20

AI_QUANT_POSTGRES_DSN=postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant \
python3 scripts/backfill_full_knowledge_graph.py http://127.0.0.1:8000 \
  --execute \
  --market A,U \
  --limit 20 \
  --batch-size 5 \
  --resume

python3 scripts/graph_quality_center.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 50 \
  --output artifacts/graph-quality-center/latest.json

python3 scripts/graph_quality_center.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 20 \
  --max-duplicate-labels 2 \
  --max-raw-label-leaks 3 \
  --output artifacts/graph-quality-center/diagnostic-relaxed-labels.json

python3 scripts/graph_quality_center.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 10 \
  --run-enrichment \
  --output artifacts/graph-quality-center/enrichment-dry-run.json

python3 scripts/graph_quality_center.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 5 \
  --browser-matrix \
  --output artifacts/graph-quality-center/browser-quality.json

python3 scripts/graph_enrichment_runner.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 100 \
  --batch-size 20 \
  --priority-layers company_event,company_relationship \
  --quality-mode fast \
  --output artifacts/graph-enrichment-runner/latest.json

python3 scripts/graph_enrichment_runner.py http://127.0.0.1:8000 \
  --market A,U \
  --limit 20 \
  --batch-size 5 \
  --priority-layers company_event,company_relationship \
  --execute \
  --resume
```

`backfill_full_knowledge_graph.py` 默认只生产基础关系图谱层和缺口状态，不逐股票跑完整图查询式证据链回填；需要补历史事件/关系/观点的 evidence links 时，再显式追加 `--include-evidence-links` 单独分批运行。

`graph_quality_center.py` 是 T-568 的统一验收入口：默认只读输出每只样本的图谱缺口、质量门、重复/底层标签泄漏、跨层链接和下一步增强动作；质量门会按前端语义标签清洗口径评估 issuer/security/market_data 等内部 ID，避免已清洗展示的行情节点被误判为 raw label 泄漏。默认展示质量门对重复标签和 raw label 泄漏采用 0 容忍，需要临时放宽时必须显式传 `max_duplicate_labels` / `max_raw_label_leaks`。质量门同时输出 `structure` 与 `raw_structure`：`structure` 使用 UI 展示模型聚合多日行情节点后评估 hub dominance、leaf ratio、fragmentation、边类型分布和有效展示边，`raw_structure` 保留底层原始边诊断；`--run-enrichment` 会调用已有公司事件和关系 builder，默认仍是 dry-run，只有同时传 `--execute` 才写入本地事件/关系候选；`--browser-matrix` 会复用浏览器级图谱验收，确认 UI 不空图、可点击展开和布局质量。

`graph_enrichment_runner.py` 是 T-569 的批量增厚入口：按图谱层缺口优先筛选股票，分批调用现有公司事件和关系 builder，并为文档、证据、持仓、研报和观点层输出 `layer_action_plan`。默认 `--quality-mode fast` 使用轻量层计数做规划，批后再用 `graph_quality_center.py` / 浏览器矩阵验收；需要逐股票完整质量中心 before/after 时可显式传 `--quality-mode full`。默认 dry-run；`--execute` 只写入本地 `needs_review` 候选事件/关系，仍需审核后才可提升为可信事实边。`document`、`evidence`、`shareholder_holding`、`research_report` 和 `viewpoint` 不会被 runner 伪造写入；它们会进入 `manual_input_required_layers`，状态为 `waiting_for_source_inputs`，并指向 `/api/ingestion/documents`、`/api/evidence/extract`、`/api/13f/filings/parse`、`/api/research-reports/structure` 等来源入口。报告顶层还会输出 `source_input_queue`，按层汇总待补齐标的、入口 endpoint 和 `required_source_fields`，可直接作为本地来源材料收集队列；它只是来源输入清单，不代表已导入数据，也不允许自动事实提升。runner 只对实际缺口层调用对应 builder；例如 `company_relationship` 已存在时会跳过关系 builder，除非显式传 `--force-build`。若某只股票没有任何 planned/created/review-candidate 活动且没有可执行来源计划，行状态会是 `no_candidate_sources`，不会写入 `completed_issuer_ids`，方便后续补入公告、研报、股东表或行情后继续 `--resume`。

## 愿景上线闸门

`/api/readiness/vision-gate` 会返回 `ready` / `not_ready` 和逐项指标，避免把 demo 状态误判为生产可上线。`/api/readiness/checklist` 可记录真实数据 smoke、UI 截图、跨浏览器、容量延迟、备份恢复、权限红队、合规复核和上线 checklist 的证据 URI、owner 与指标；未审计通过的项会留在闸门 `pending_checklist` 中。

生产闭环不依赖新增外部收费数据源，而是依赖真实环境证据收口。把生产/预发生成的 evidence URI 汇总成 manifest 后，先用离线校验器检查结构，再用收口脚本统一回填 readiness checklist、运行 storage/security/observability/UI/deployment 报告、导出并离线校验证据包：

```bash
python3 scripts/production_task_closure_audit.py \
  --output artifacts/production-task-closure-audit.json
```

```bash
python3 scripts/project_completion_audit.py \
  --output artifacts/project-completion-audit.json
```

如果部署目标明确是当前机器长期运行，完成审计应显式带入本机证据，而不是继续套用非本机发布门禁：

```bash
python3 scripts/project_completion_audit.py \
  --local-production-audit artifacts/local-production-audit.json \
  --local-ai-acceptance artifacts/local-ai-capability-acceptance.json \
  --output artifacts/project-completion-audit.json
```

真实发布证据齐备后，目标完成审计应显式带上 filled plan、readiness package 和 artifact inventory：

```bash
python3 scripts/project_completion_audit.py \
  --manifest artifacts/production-closure-manifest.json \
  --evidence-plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --artifact-inventory artifacts/production-artifact-inventory.json \
  --artifact-bundle-root artifacts/production-evidence-bundle \
  --output artifacts/project-completion-audit.json
```

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

```bash
python3 scripts/production_evidence_plan_check.py \
  artifacts/production-evidence-collection-plan.json \
  --require-filled-uris \
  --output artifacts/production-evidence-plan-validation.json
```

```bash
python3 scripts/production_evidence_plan_to_manifest.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --base artifacts/production-closure-manifest.example.json \
  --output artifacts/production-closure-manifest.json
```

```bash
python3 scripts/production_release_gate.py \
  --plan artifacts/production-evidence-collection-plan.json \
  --evidence-package artifacts/readiness-evidence-package.json \
  --artifact-inventory artifacts/production-artifact-inventory.json \
  --artifact-bundle-root artifacts/production-evidence-bundle \
  --manifest-output artifacts/production-closure-manifest.json
```

严格发布门禁通过后，才允许把 `tasks/todo.md` 中对应 `BLOCKED` 任务收口为 `DONE`：

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

校验 inventory 时可同时复验文件存在、大小和 sha256：

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

```bash
python3 scripts/production_closure.py https://staging.example.internal \
  --manifest artifacts/production-closure-manifest.json \
  --output artifacts/production-closure-result.json
```

`scripts/production_task_closure_audit.py` 用于审计 `tasks/todo.md` 中仍开放的任务是否还存在代码层缺口，或只是缺真实 staging/production artifact URI；`scripts/project_completion_audit.py` 会把“完成剩余内容、实现项目目标”映射到部署目标对应的 artifact checklist：默认仍按非本机组织级发布证据判断，显式传入 `--local-production-audit` 和 `--local-ai-acceptance` 时按本机个人生产证据判断；未达成时返回非零退出码。`--output-plan` 可导出 owner、readiness endpoint 和 artifact 字段模板，`scripts/production_evidence_plan_fill.py` 可用真实归档前缀批量替换模板 URI，并立即按 `--require-filled-uris` 口径校验；`scripts/production_evidence_plan_check.py` 可离线校验该采集计划，`--require-filled-uris` 会进一步拒绝仍带 `<production-evidence-bucket>` 这类占位符的计划。`scripts/production_artifact_inventory_check.py` 要求每个 release evidence URI 都有 inventory 行，包含 sha256、size、environment、producer、owner、content type、retention 和 immutable/object lock 信息，并会拒绝 inventory 或 required context 中仍带占位符的 URI。`scripts/production_evidence_plan_to_manifest.py` 把已回填 URI 的采集计划映射到 production closure manifest 的 task evidence、readiness checks、reports 和 A 股 connector 证据；生成结果的 `manifest_generation` 会输出 `skipped_mapping_count`、`mapped_readiness_check_count`、`missing_readiness_check_count` 和 `missing_external_validation_scope_count`，CI 可直接读取这些计数字段判断映射缺口；它默认拒绝占位符，且只有显式提供真实 readiness evidence package 并通过严格校验时才允许 `--release-ready`。`scripts/production_release_gate.py` 把 filled plan、真实 evidence package、artifact inventory、manifest 生成和严格校验串成一个门禁命令，默认没有真实 package 或 inventory 就失败；`--draft` 只用于模板预览。`scripts/production_task_status_finalize.py` 只在严格 release gate 通过后把对应 `BLOCKED` 任务改为 `DONE`，不会生成或伪造证据。`scripts/production_closure.py` 会拒绝本机路径、样例 artifact、收费/商业授权数据源和未冻结的 A 股 connector；通过标准仍是 evidence package `ready_for_launch=true` 且 `scripts/readiness_evidence_package_check.py` 校验通过。
`scripts/production_task_closure_audit.py` 会在顶层输出 `needs_code_work_count`、`blocked_external_evidence_count`、`needs_code_work_task_ids` 和 `blocked_external_evidence_task_ids`，便于 CI 或发布负责人直接分派剩余阻塞项；`scripts/project_completion_audit.py` 会在顶层输出 `failed_requirement_ids`、`blocked_requirement_ids` 和 `open_requirement_ids`，其中 `blocked_requirement_ids=["R3","R6"]` 表示代码层已收口但真实生产证据链仍未通过，不能把项目目标标记为完成。
`scripts/production_release_gate.py` 会在顶层输出 `stage_count`、`passed_stage_count`、`failed_stage_count` 和 `failed_stage_names`，发布脚本可直接用这些字段判断门禁卡在哪个阶段，而不必遍历 `stages` 明细。
仓库内提供 [`artifacts/production-closure-manifest.example.json`](artifacts/production-closure-manifest.example.json) 作为同口径模板，真实发布时复制后再替换成生产/预发证据 URI；只检查模板结构时使用 `python3 scripts/production_closure_manifest_check.py artifacts/production-closure-manifest.example.json --allow-template`，默认校验会要求真实发布口径的 `ready_for_launch=true`。

## 公开来源治理

`/api/governance/sources/report` 汇总公开来源 provenance 台账覆盖率，`/api/governance/sources/{source_id}/reviews` 记录季度来源复核，`/api/governance/source-review-reminders` 输出复核 owner 看板和逾期/即将到期提醒，系统治理 UI 会展示该看板，并可通过默认告警 `alert_source_review_overdue` 写入来源复核通知 outbox。`/api/governance/audit-report` 检查关键审计字段完整性，`/api/governance/data-security-report` 扫描已入湖文本中的邮箱、手机号、身份证样式和 secret/API key 字面量并返回脱敏片段；越权 API 访问会被 403 拦截并写入 `permission_denied` 审计事件。外部公开来源应补齐 `provenance_ref`、`source_tos_uri`、`retention_policy`、`cache_ttl_days`、`usage_scope` 和 `field_whitelist`，边界不清时只进入人工参考。

## PaddleOCR-VL 文档解析备用接口

本地 PDF/文本流解析拿不到内容时，`/api/evidence/extract` 会在 `AI_QUANT_PADDLEOCR_TOKEN` 已配置的情况下自动调用 PaddleOCR-VL，并把返回 markdown 切成 evidence。也可以直接调用备用解析接口；密钥不要写入仓库，请通过环境变量注入：

```bash
export AI_QUANT_PADDLEOCR_TOKEN=...
export AI_QUANT_PADDLEOCR_MODEL=PaddleOCR-VL-1.5
```

解析远程文件 URL：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/document-parsing/paddleocr \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"file_url":"https://example.com/report.pdf"}'
```

解析已入湖文档：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/document-parsing/paddleocr \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"document_id":"doc_001","optional_payload":{"useChartRecognition":true}}'
```

## 通达信本地行情

本地通达信行情默认读取项目内 `./data/local/tdx/vipdoc` 标准 `.day` 文件。当前副本来自通达信官方个人行情数据页面 `https://www.tdx.com.cn/article/vipdata.html` 下载的沪深京日线完整包，运行不依赖下载目录，也不再使用旧本地中间库。

预览日线：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/market-data/tdx/preview \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"source_format":"vipdoc","symbols":["sh600000"],"start_date":"2026-01-01","end_date":"2026-05-15","limit":5}'
```

导入到公开/已提供 EOD 行情层：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/market-data/tdx/import \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"source_format":"vipdoc","symbols":["sh600000"],"security_map":{"600000":"sec_600000"},"start_date":"2026-01-01","end_date":"2026-05-15","limit":200}'
```

增量导入脚本会读取 SQLite 状态库中每个 symbol 对应 security 的最后入库日期，并从下一交易日开始拉取；`--dry-run` 只返回预览数量，不写状态库：

```bash
python3 scripts/import_tdx_market_data.py ./data/state.db \
  --symbols sh600000,sz000001 \
  --security-map '{"600000":"sec_600000","000001":"sec_000001"}' \
  --source-format vipdoc \
  --end-date 2026-05-15
```

本机生产栈运行时，推荐用 API 批处理脚本按 symbol 分片导入，避免单个 HTTP 请求长时间占用：

```bash
python3 scripts/tdx_batch_import.py \
  --base-url http://127.0.0.1:8000 \
  --discover-from-tdx ./data/local/tdx/vipdoc \
  --symbol-prefix 60 \
  --max-symbols 20 \
  --start-date 2026-03-25 \
  --end-date 2099-12-31 \
  --limit-per-symbol 5 \
  --register-missing \
  --output artifacts/tdx-batch-import.json
```

全量 PostgreSQL 写入使用容器内专用批量脚本，避免逐 symbol HTTP 往返；最近一次全量导入摘要见 `artifacts/tdx-vipdoc-postgres-import-full.json`。日常生产恢复或复查时先跑覆盖审计，不直接重复全量导入：

```bash
python3 scripts/audit_tdx_vipdoc_postgres_coverage.py \
  --dsn postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant \
  --vipdoc-path data/local/tdx/vipdoc \
  --output artifacts/tdx-vipdoc-postgres-coverage.json
```

当 `artifacts/tdx-vipdoc-postgres-coverage.json` 中 `ready_to_skip_import=true` 时，说明本地 vipdoc 与 PostgreSQL 行情覆盖已经匹配，可以跳过导入。只有审计结果为 `status=needs_import`，或更换了 `vipdoc` 数据目录、日期窗口、`source_id`/`data_type` 时，才执行全量或限定范围导入：

```bash
python3 scripts/import_tdx_vipdoc_postgres.py \
  --dsn postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant \
  --vipdoc-path data/local/tdx/vipdoc \
  --output artifacts/tdx-vipdoc-postgres-import-full.json
```

全量导入是幂等的，但会重写大规模 JSONB 行情记录；以后本机生产闭环默认采用“覆盖审计 -> 缺口导入 -> 再审计”的顺序。

`vipdoc` 压缩包下载必须显式传入公开可审计 URL 或本地文件，并建议提供 sha256：

```bash
python3 scripts/download_tdx_vipdoc.py https://example.invalid/tdx/vipdoc.zip \
  --target-dir ./data/local/tdx/vipdoc_downloads \
  --expected-sha256 <sha256>
```

## 本地研报资产库

研报默认只做“本地参考观点层”，不作为事实真相源，也不默认进入训练。扫描本地目录生成 manifest：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/research-reports/scan \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"root_path":"/home/xionglei/文档/6大投行研报汇总","limit":100}'
```

按需把单份研报登记为 Document：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/research-reports/rr_xxx/ingest \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"issuer_id":"issuer_001","security_id":"sec_001"}'
```

私会、路演或边界不清转录稿只能登记 metadata-only 人工参考记录；接口会拒绝正文并创建人工复核项：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/research/manual-references \
  -H 'Content-Type: application/json' \
  -H 'X-Role: analyst' \
  -d '{"document_id":"doc_private_note_meta","issuer_id":"issuer_demo","security_id":"security_demo_us","document_type":"private_meeting_note","title":"Private meeting metadata","source_uri":"private://meetings/demo","notes":"Metadata only; confirm publicness and Reg FD boundary."}'
```

## A 股公告接入

预览 A 股交易所最近公告元数据；`exchange=auto` 会按证券代码选择上交所或深交所：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/connectors/ashare/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"security_code":"600000","exchange":"auto","begin_date":"2026-04-01","end_date":"2026-05-14","limit":1,"user_agent":"your-app contact@example.com"}'
```

入湖最近公告；`include_attachment=true` 时会把公告附件下载到本地对象存储：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/ingestion/ashare/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"issuer_id":"issuer_001","security_id":"sec_001","security_code":"600000","exchange":"auto","begin_date":"2026-04-01","end_date":"2026-05-14","limit":1,"include_attachment":true,"user_agent":"your-app contact@example.com"}'
```

也可以用 `AI_QUANT_ASHARE_USER_AGENT` 设置默认 A 股公告 User-Agent。

## SEC EDGAR 接入

预览最近 filing 元数据：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/connectors/sec/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"cik":"0000320193","document_types":["10-K"],"limit":1,"user_agent":"your-app contact@example.com"}'
```

入湖最近 filing；`include_body=true` 时会下载主文档正文，`include_attachment=true` 时会把主文档附件下载到本地对象存储：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/ingestion/sec/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"issuer_id":"issuer_001","security_id":"sec_001","cik":"0000320193","document_types":["10-K"],"limit":1,"include_body":true,"include_attachment":true,"user_agent":"your-app contact@example.com"}'
```

也可以用 `AI_QUANT_SEC_USER_AGENT` 设置默认 SEC User-Agent。

## HKEXnews 接入

预览最近公告元数据：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/connectors/hkex/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"query":"annual","file_type":"pdf","limit":1,"user_agent":"your-app contact@example.com"}'
```

入湖最近公告；`include_attachment=true` 时会把公告附件下载到本地对象存储：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/ingestion/hkex/recent \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"issuer_id":"issuer_001","security_id":"sec_001","query":"annual","file_type":"pdf","limit":1,"include_attachment":true,"user_agent":"your-app contact@example.com"}'
```

也可以用 `AI_QUANT_HKEX_USER_AGENT` 设置默认 HKEX User-Agent。

## HTTP 调用约定

服务会读取 `X-Actor` 和 `X-Role` 请求头写入审计和执行角色校验。HTTP header 建议使用 ASCII 角色别名：`ceo`、`cio`、`pm`、`risk_compliance`、`platform`、`analyst`、`data_engineer`、`nlp_ml`、`overseas_research`。GET 请求支持 query string，例如：

```bash
curl -sS 'http://127.0.0.1:8000/api/graph/query?issuer_id=issuer_001' \
  -H 'X-Role: ceo' \
  -H 'X-Actor: ceo_owner'
```
