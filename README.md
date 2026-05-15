# AI Native Quant Org

一个基于项目文档实现的最小可运行后端原型，覆盖三市场数据接入骨架、证据链、评分、决策治理、审计、challenger、知识图谱查询和事故剧本管理。

## 目录

- `app/`: 应用代码
- `tests/`: 单元测试
- `docs/`: 项目与架构文档
- `tasks/`: 执行待办清单

## 运行测试

```bash
python3 -m unittest discover -s tests
python3 -m py_compile app/*.py tests/*.py scripts/*.py
```

## 启动服务

```bash
python3 -m app.server
```

默认启动地址：

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/ui`

默认使用内存存储。需要重启后保留数据时，设置 `AI_QUANT_DB` 使用 SQLite 状态库：

```bash
AI_QUANT_DB=./data/state.db python3 -m app.server
```

生产状态库可使用 PostgreSQL。先安装可选依赖 `psycopg`，再设置 `AI_QUANT_POSTGRES_DSN`；也可以直接让 `AI_QUANT_DB` 使用 `postgresql://` 或 `postgres://` DSN：

```bash
python3 -m pip install '.[postgres]'
AI_QUANT_POSTGRES_DSN=postgresql://user:password@localhost:5432/ai_quant python3 -m app.server
```

从 SQLite 状态库迁移到 PostgreSQL 时，使用显式迁移脚本。`--replace` 会重写目标 PostgreSQL 的 `ai_quant.records` 和 `ai_quant.audit_log`：

```bash
python3 scripts/migrate_sqlite_to_postgres.py ./data/state.db postgresql://user:password@localhost:5432/ai_quant --replace
```

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

UI 静态验收会检查左侧信息架构、顶部状态条、关键面板 ID 和前端脚本语法：

```bash
python3 scripts/ui_static_check.py
```

提交或部署前可运行密钥与 `.env` 误提交检查：

```bash
python3 scripts/security_check.py .
```

Docker Compose：

```bash
docker compose up --build
```

生产部署、备份、恢复、回滚和月度运维步骤见 [docs/production-runbook.md](./docs/production-runbook.md)。环境变量模板见 [.env.example](./.env.example)。

## 当前实现范围

- 三市场 source registry 与权限标签
- 上交所 A 股最近公告检索预览和入湖
- SEC EDGAR 最近 filings 元数据抓取和可选正文入湖
- HKEXnews 最近公告检索预览和入湖
- 授权 EOD/延时行情点入库，包含 source rights 校验、实时数据阻断、红区来源阻断和 dashboard 摘要
- 13F 持仓记录入库，并可生成中低频拥挤度 snapshot
- HTML 文档正文清洗并生成可读证据片段
- PDF 对象文本流/Flate 流抽取兜底，可从本地 PDF 对象生成证据片段
- `/api/document-parsing/paddleocr` PaddleOCR-VL 文档解析备用接口，证据抽取在本地解析无文本且配置 token 时会自动兜底
- `/api/market-data/tdx/preview` 与 `/api/market-data/tdx/import` 读取本地通达信 DuckDB 日线库并导入授权 EOD 行情
- `/api/research-reports/scan` 本地研报 manifest 索引，研报默认作为授权外部观点层维护
- 术语、数值、期间和规则表格读取基线抽取，并可按中英 benchmark 样本集运行阈值、定位、表格和低置信度拦截评估
- Issuer / Security / MarketDataPoint / Document / Evidence / Thesis / Signal / Decision / Review
- CorporateAction 用于拆股、分红、代码变更等复权和估值链路
- 英文 evidence 优先的研究问答与中文摘要审计，保留 summary/prompt/model 版本和人工覆核状态
- benchmark、prompt 审批、scorecard、research card
- Reg FD / non-display 合规闸门
- approved decision 到 execution intent 的审批闸门
- 13F institutional holding、crowding、8-K/6-K/20-F disclosure event、challenger、playbook、incident report、drill schedule
- Black-Litterman 纸面组合原型，支持观点置信度/Omega、风险预算、禁投清单、压力测试和 walk-forward 诊断
- dashboard、graph/evidence/portfolio query、review query
- 可选 SQLite / PostgreSQL 持久化，覆盖核心对象、审批签字和审计日志
- `/ui` 静态单页界面，覆盖目标运营台总览、CEO Dashboard、主体页、投委会页、A/H/U 预览、结构化抽取、采集调度和事故日历
- UI 静态验收脚本，覆盖 `pic/UI.png` 对应的左侧信息架构、顶部市场/风险/冲突状态和关键控件存在性
- `/api/demo/full-flow` 生成一套可展示的端到端 demo 数据
- operating report 与 strategy replay，覆盖月报红灯项、治理指标、TWR/最大回撤/换手/信息比率、发布审批和版本化决策回放
- `/api/search` 内置全文检索 fallback，跨 Document、Evidence、Thesis、Research Card 搜索
- 对象存储 adapter：本地文件默认，S3 兼容存储可通过环境变量启用；Document 记录 `object_uri` 和 `content_sha256`
- 检索 adapter：本地全文检索默认，OpenSearch 兼容检索可通过环境变量启用，异常时可回退本地检索
- 批量 ingestion job，支持 connector normalize、去重、错误记录和任务状态查询
- 采集调度 schedule，支持 cadence、retry_limit、最近 job 状态和失败重试
- `/api/health` 与 `/api/metrics`，提供最小部署健康检查和运行指标
- `/api/alerts` 告警闭环，支持默认规则播种、指标评估、开放告警查询和恢复状态
- Evidence extraction 支持 `\f` 分页文本，记录 `page_no` 和稳定 locator
- 扫描件/空文本会优先尝试 PaddleOCR-VL 备用解析；未配置或解析失败时进入人工复核队列，并提供 evidence quality report

## 说明

当前实现是 MVP 后端与前端初版，重点是把文档中的核心对象、接口、治理规则、最小持久化和可操作页面落成可测试代码。A/H/U 三市场公告/filing 真实检索已补上最小入口；状态库、对象存储和检索已具备本地 fallback 与生产 adapter 边界。专用图谱/向量存储、复杂 OCR/PDF、真实外部环境压测和前端生产化验收仍是后续建设项。

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

## A 股补充接口注册表

`a-stock-data` 这类外部接口先进入候选注册表，逐项声明来源、字段映射、限速、是否需要 key、rights tag 和验证状态。默认只作为人工参考或补充研究，不替代本地/授权核心数据。

```bash
curl -sS -X POST http://127.0.0.1:8000/api/connectors/astock/seed \
  -H 'X-Role: data_engineer'

curl -sS -X POST http://127.0.0.1:8000/api/connectors/astock/verify \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"connector_id":"eastmoney_research","status":"passed"}'
```

## 图谱与语义检索

`/api/graph/query` 保留证据、观点、决策和复盘的关系回查；`/api/search/semantic` 提供本地轻量语义检索 adapter，当前用 term-frequency cosine 固定接口和权限边界，后续可替换为 Qdrant/embedding/reranker。

## 愿景上线闸门

`/api/readiness/vision-gate` 会返回 `ready` / `not_ready` 和逐项指标，避免把 demo 状态误判为生产可上线。UI 截图验收、跨浏览器、容量延迟、备份恢复、权限红队和合规复核仍作为上线前人工检查项。

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

本地通达信 DuckDB 默认读取 `./data/local/tdx/market_data.duckdb`，需要安装可选依赖：

```bash
python3 -m pip install '.[tdx]'
```

预览日线：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/market-data/tdx/preview \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"symbols":["600000"],"start_date":"2026-01-01","end_date":"2026-05-15","limit":5}'
```

导入到授权 EOD 行情层：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/market-data/tdx/import \
  -H 'Content-Type: application/json' \
  -H 'X-Role: data_engineer' \
  -d '{"symbols":["600000"],"security_map":{"600000":"sec_600000"},"start_date":"2026-01-01","end_date":"2026-05-15","limit":200}'
```

## 本地研报资产库

研报默认只做“授权外部观点层”，不作为事实真相源，也不默认进入训练。扫描本地目录生成 manifest：

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
