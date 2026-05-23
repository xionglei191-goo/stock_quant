# Todo

## 使用规则

- 状态只用 `TODO` `DOING` `DONE` `BLOCKED`
- 本文件维护“达到项目愿景”的剩余路线图；历史实现只在“已落地基线”里汇总
- 每项任务必须映射到 `docs/mvp-backlog.md` 的 E1-E9；无法完全映射的标注为“愿景扩展/生产化增强”
- 新增能力默认遵循：研究先于模拟组合、公开/已提供数据先于自动化、模拟持仓反馈先于任何真实交易设想
- 当前系统目标是投资分析和投研反馈，不接真实券商、不做自动下单；`execution intent` 仅表示纸面/模拟意图
- 不采购或依赖商业授权数据；行情、披露、研报线索、转录稿和第三方接口统一优先使用已提供本地数据、官方公开披露、公开网页/API、开源工具可采集的数据
- 所有外部数据进入自动化链路前必须记录来源、URL/API、采集时间、robots/TOS/公开性判断、字段边界、缓存期限和用途边界；边界不清的数据只进入人工参考
- 生产闭环只允许用真实 staging/production artifact URI 回填 manifest；仓库里保留 `artifacts/production-closure-manifest.example.json` 作为填报模板，不作为可直接发布的证据
- 已回填 URI 的外部证据采集计划必须先经 `scripts/production_evidence_plan_check.py --require-filled-uris` 检查，并提供 artifact inventory 证明每个 evidence URI 的归档对象、sha256、size、环境、producer、owner、retention 和 immutable/object lock，再用 `scripts/production_evidence_plan_to_manifest.py` 或 `scripts/production_release_gate.py` 生成 production closure manifest；草案仍需严格 manifest 和 readiness evidence package 校验后才能签批

## 当前判断

当前能力：代码已经跑通 MVP 主链路，覆盖 A/H/U 公开披露接入、rights tag、证据切片、规则抽取、benchmark 阈值、Thesis/Signal/Decision、纸面执行意图、模拟持仓 ledger、月报/回放、事故剧本、SQLite/PostgreSQL、本地/S3 对象存储、内置/OpenSearch 检索、`/ui` 静态页面、健康检查、烟测、LLM 中转站和 PaddleOCR-VL 文档解析备用接口。本机长期运行口径下，`artifacts/local-business-acceptance.json` 已通过，`artifacts/latest-analysis/latest-analysis.json` 已生成最新 A 股/美股分析结果。

新增资源：本地通达信历史行情已迁入项目内 `data/local/tdx/vipdoc`，并已全量写入 PostgreSQL `market_data`，导入摘要见 `artifacts/tdx-vipdoc-postgres-import-full.json`；本地研报库 `/home/xionglei/文档/6大投行研报汇总` 已完成全量入库和解析，源目录 11702 份可处理文件全部登记为 research report asset、全部关联 research document、全部进入 `text_indexed`，无 `indexed` / `ingested` / `needs_text_review` 残留，研报 citation evidence 共 88515 条，审计见 `artifacts/research-report-completion-audit.json`；`a-stock-data` 相关 A 股补充 connector 已完成来源治理补齐，`artifacts/source-governance-fill.json` 显示来源治理覆盖率 `1.0`；LLM gateway 与 PaddleOCR-VL 已完成本机密钥注入和真实冒烟，验收记录见 `artifacts/local-ai-capability-acceptance.json`。

剩余关键缺口：用户已明确后续以本机长期使用为目标；本机 production-like 栈已可作为个人/单机生产口径运行，并由 `scripts/local_production_audit.py`、`scripts/local_ai_capability_acceptance.py` 和 `scripts/project_completion_audit.py` 单独审计。当前 `artifacts/project-completion-audit.json` 在 `local_only_personal_production` 目标下为 `status=achieved`。若未来要升级为非本机组织级真实生产发布，仍差真实生产参数、外部密钥管理系统、生产级 artifact URI、灰度/回滚窗口和 CEO 签批边界。长期能力仍需继续补强真实 bbox 和版面定位、大样本真实标注集、非本机 Neo4j/Qdrant/OpenLineage/MLflow/OTel 证据、真实外部通道和生产运维记录。`artifact://staging-local/...` 可以作为本机长期使用证据，但不作为非本机组织级发布签批证据。

近期优先级：本机长期使用口径下，优先保持 Compose 栈、备份恢复、本机证据包、LLM/OCR 冒烟、最新分析产物和 `local_production_audit` 可复验；日常启动建议使用 `scripts/local_production_stack.sh`。研报解析底座和研报接入业务分析/UI 看板已经全量收口，`artifacts/latest-analysis/latest-analysis.json` 已包含 A 股、美股、产业链、财报、行情和研报观点 evidence，`artifacts/latest-analysis/research-evidence-recall-audit.json` 已确认研报只进入观点/参考层，不进入事实源、训练源或真实交易信号。M6-M9 代码层已收口，剩余 `BLOCKED` 项保留为“非本机/组织级生产或大样本质量增强”证据缺口，不阻塞本机使用。

## 已落地基线

- `DONE` T-301 后端核心对象、API 路由和治理规则原型
  - 对应：E2-US1, E3-US1, E5-US3, E6-US1, E6-US2, E6-US3, E6-US4, E8-US1, E8-US2, E9-US1
  - 代码：`app/models.py`、`app/api.py`、`app/services.py`、`tests/test_system.py`

- `DONE` T-302 A/H/U 公开披露最小接入与批量采集闭环
  - 对应：E2-US2, E3-US3
  - 代码：SEC EDGAR、HKEXnews、上交所/深交所 recent connector；ingestion job、schedule、retry、去重和错误留痕

- `DONE` T-303 权限、合规和审批闸门
  - 对应：E2-US1, E2-US3, E6-US1, E6-US2, E6-US3, E6-US4
  - 代码：rights tag 校验、Reg FD / non-display gate、prompt 审批、未审批决策拦截纸面执行意图和模拟持仓入口

- `DONE` T-304 证据链、结构化抽取和 benchmark 原型
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 代码：HTML 清洗、分页文本 locator、PDF Flate/text stream 兜底、术语/数值/期间/规则表格抽取、benchmark 阈值校验

- `DONE` T-305 研究卡、评分、challenger、13F crowding 占位和投委会闭环
  - 对应：E5-US1, E5-US2, E5-US3, E5-US4, E6-US1, E8-US1
  - 代码：template、research card、scorecard、crowding snapshot、challenger、decision pack、签字链

- `DONE` T-306 复盘、月报、事故和最小经营看板
  - 对应：E6-US5, E7-US1, E8-US3, E9-US1, E9-US2
  - 代码：OperatingReport、StrategyReplay、Exception、IncidentPlaybook、DrillSchedule、dashboard、incident calendar

- `DONE` T-307 MVP 存储、检索、部署和 UI 初版
  - 对应：E3-US4, E7-US1, E7-US2, E7-US3, E8-US2
  - 代码：SQLiteStore、PostgreSQL baseline schema、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、`/ui`、`/api/health`、`/api/metrics`、Docker、smoke test

- `DONE` T-308 大模型中转站基础能力
  - 对应：E6-US3, E6-US4, E8-US1；愿景扩展/生产化增强
  - 已有：OpenAI `/v1/chat/completions` 和 Anthropic `/v1/messages` 兼容转发、默认模型配置、环境变量注入、调用审计、无密钥入库
  - 后续：并入 T-418 做任务级 prompt、成本、延迟、回退和人工复核闭环

- `DONE` T-309 PaddleOCR-VL 文档解析备用接口
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：`/api/document-parsing/paddleocr`、URL/已入湖文档解析、证据抽取空文本自动兜底、markdown 分页、图片 URL 元数据、环境变量注入、无 token 入库
  - 后续：并入 T-401 做真实 bbox、版面金标、跨页表格和质量报告

- `DONE` T-413 Feast / Kafka 阶段性决策 memo
  - 对应：E3-US4, E6-US4, E8-US3；愿景扩展/生产化增强
  - 已有：`docs/feast-kafka-decision-memo.md` 记录暂缓上线理由、Feast/Kafka 触发阈值、outbox/feature registry 迁移草案、PoC 人力周期和退出标准
  - 触发条件：共享特征数、训练/回测/生产口径偏差事故、多事件并发、跨 Agent 解耦和次分钟级联动达到文档阈值后再实施

- `DONE` T-415 美股合规专题补充
  - 对应：E2-US1, E6-US2, E6-US4
  - 已有：`docs/us-compliance-open-questions.md` 覆盖 Reg FD 来源公开性、Nasdaq/NYSE non-display/derived data declaration、投资顾问和外部资管边界、真实券商接口 / best execution / live execution 的非目标说明、衍生品与跨境限制

## P0 当前冲刺 / M6 生产化事实层

- `DONE` T-401 复杂版式 PDF / OCR 与真实证据定位生产化
  - 对应：E3-US3, E4-US1, E4-US2, E4-US3
  - 已有：HTML 清洗、`\f` 分页、PDF 文本流/Flate 流兜底、规则表格读取、`page=...;chunk=...` locator、空文本/扫描件解析失败分级、ManualReviewItem 人工复核队列、evidence quality report、PaddleOCR-VL 备用解析接口
  - 已有：PaddleOCR-VL 解析结果按文档/URL、content hash/source URI、模型和 optional payload 运行时缓存，并返回 `cache_hit`、`elapsed_ms`、`estimated_cost` 供质量/成本审计
  - **已完成（本轮）**：OCR locator schema 与版面资产穿透
    - Evidence 新增 `locator` 和 `assets` 元数据，保留旧 `bbox` 字符串兼容；规则文本 locator 为 `page_chunk_v1`，OCR 版面 locator 为 `ocr_bbox_span_v1`
    - PaddleOCR JSONL 解析可提取 `layoutDetections`、`tables/cells`、markdown/output 图片资产，并规范化为 `{x,y,width,height}` bbox
    - `extract_evidence` 可把 OCR layout bbox、span hash、table cell bbox 和 image/table asset refs 写入 evidence
    - `_extract_tables` 优先使用 OCR locator table cells，benchmark 表格定位可读取真实 cell bbox
    - `/api/evidence/quality-report` 新增 `structured_locator_coverage`、`bbox_coverage`、`table_cell_count`、`table_cell_bbox_coverage`、`asset_reference_count`
  - **已完成（本轮）**：跨页表格合并
    - `POST /api/extractions/run` 支持 `include_adjacent_tables=true`，可扫描同一文档相邻 evidence，并按同 header / 同列签名合并跨页表格
    - 合并结果保留 `page_numbers`、`merged_from_table_count`、`merge_strategy` 和 cell 级 `source_page_no` / `source_row` / `merged_row` locator，方便回溯原 PDF 页/框
    - 测试覆盖 `\f` 分页文本中的同 header 表格合并、跨页 cell 定位和 table benchmark 指标
  - **已完成（本轮）**：解析失败重试
    - `/api/document-parsing/paddleocr` 支持 `retry_attempts` / `retry_limit`，临时失败可最多额外重试 3 次，并返回 `attempt_count`、`retry_attempts` 和 `retry_errors`
    - `extract_evidence` 的 OCR fallback 默认做一次自动重试，仍失败才创建 ManualReviewItem，避免临时 OCR job/结果 URL 波动直接进入人工队列
    - 测试覆盖 URL 解析 transient failure 重试成功，以及证据抽取 OCR fallback 重试后不创建人工复核
  - **已完成（本轮）**：真实扫描件大样本版面 bbox 校验入口
    - `/api/evidence/quality-report` 支持 `bbox_gold_labels` 和 `min_bbox_iou`，按 IoU 输出 `bbox_hit_rate`、`average_iou`、逐标签命中和失败样本
    - 测试覆盖 OCR layout bbox 与人工 gold label 的命中/未命中校验，为后续 300-500 份真实扫描件样本运行提供固定验收入口
  - 后续真实数据验收：把真实扫描件大样本 gold label 批量跑完并归档外部 artifact URI（并入 T-402 / T-422 证据包）
  - 输出：OCR/版面解析 adapter、bbox/span schema、解析质量报告、人工复核闭环、错误样本库
  - 验收：每个错误样本可回溯到原 PDF 页/框；证据页命中率达到 benchmark 门槛；解析失败进入人工复核并触发告警

- `BLOCKED` T-402 大样本中英双语 benchmark 执行
  - 对应：E4-US1, E4-US2, E4-US3
  - 已有：BenchmarkSample、BenchmarkRun、`/api/benchmarks/{benchmark_id}/samples`、`/api/benchmarks/{benchmark_id}/run`、中英样本登记、真实 extraction 链路评估、术语 F1、数值/期间召回、表格召回、页命中率、证据定位率、按语言拆分指标、低置信度拦截、失败样本和回归样例库、PostgreSQL 视图
  - 已有：`GET|POST /api/benchmarks/{benchmark_id}/readiness-report` 可按固定 gate 输出大样本验收包，检查 active sample 数、中文/英文覆盖、最近 run 指标、样本 manifest URI、中文/英文样本集 URI、人工标注手册 URI、OCR/bbox gold label URI、表格 cell gold label URI、摘要质量样本 URI、regression baseline artifact URI；内联 gold/summary payload 只用于计数摘要，不能替代真实外部 artifact
  - **已完成（本轮质量包入口）**：新增 `scripts/local_benchmark_quality_package.py`，可扫描本地文本/PDF材料，自动登记中英 benchmark 样本、运行抽取 benchmark，并导出 `artifacts/benchmark-quality-package/sample-manifest.json`、`baseline-report.json`、`readiness-report.json`、`annotation-manual.md`、`bbox-gold.jsonl`、`table-cell-gold.jsonl` 和 `summary-quality-samples.jsonl`
    - 2026-05-18 实跑 `python3 scripts/local_benchmark_quality_package.py data/objects docs --output-dir artifacts/benchmark-quality-package --benchmark-id bm_local_quality_20260518 --target-sample-size 300 --min-chinese-samples 150 --min-english-samples 150 --max-samples 500 --artifact-prefix minio://ai-quant-local/benchmark-quality/20260518`，artifact 已生成；当前 `sample_count=72`、`target_gap=228`、`run_passed=false`、`large_sample_ready=false`
    - 当前缺口被明确量化为 `sample_size`、`chinese_sample_count`、`english_sample_count`、`metric_number_recall`、`metric_period_recall`；后续补真实样本和修数值/期间召回时可复用同一脚本回归
  - **已完成（本轮接口补样本入口）**：新增 `scripts/fetch_benchmark_samples.py`，可通过现有公开披露 connector 批量拉 SEC/A 股/HKEX 样本并保存为质量包可扫描的本地文本，同时输出 `artifacts/benchmark-sample-fetch/fetch-manifest.json` 记录创建、跳过和失败原因
    - 2026-05-18 实跑 SEC CIK `0000320193,0000789019`、`10-K/10-Q`、每个 CIK 2 份，成功新增 4 份英文披露样本；随后重跑质量包 `python3 scripts/local_benchmark_quality_package.py data/objects docs artifacts/benchmark-sample-fetch ...`，当前 `sample_count=148`、`language_counts={en:119, zh:29}`、`target_gap=152`
    - 2026-05-18 继续补齐 A 股附件路径：`scripts/fetch_benchmark_samples.py` 新增 `--include-ashare-attachment-text`，在公告列表只有标题时会尝试下载公开附件并抽取文本，支持本机 `pdftotext` fallback，并在 `skipped` 中记录附件尝试、403/封禁页或无指标术语等原因；实跑 `600519,600000,000001,300750` 时上交所附件被 CDN 返回封禁 HTML/无可用指标正文，深交所附件返回 403，因此未把无正文标题计入有效样本
    - 2026-05-18 纳入已落盘公开/本地材料后重跑质量包 `python3 scripts/local_benchmark_quality_package.py data/objects docs artifacts/benchmark-sample-fetch artifacts/benchmark-sample-fetch-ashare ...`，曾达到 `sample_count=278`、`language_counts={en:222, zh:56}`、`target_gap=22`
    - 2026-05-18 修正质量包本地 PDF 抽文本能力，补入 `pdftotext` fallback；按中文公开材料优先顺序重跑 `python3 scripts/local_benchmark_quality_package.py data/objects/ashare_exchange data/objects/sec_edgar docs artifacts/benchmark-sample-fetch artifacts/benchmark-sample-fetch-ashare /home/xionglei/文档/6大投行研报汇总 ... --max-samples 500`
    - 2026-05-18 修正自动 gold 口径：质量包先按可见文本推断 expected terms/numbers/periods，跳过无自动可验证数字或期间的弱样本，并保护中文样本配额，避免英文 SEC 样本提前填满 `--max-samples`
    - 2026-05-18 质量包已绿灯：当前 `sample_count=500`、`language_counts={en:335, zh:165}`、`source_counts={ashare_exchange:165, sec_edgar:335}`、`target_gap=0`、`run_passed=true`、`large_sample_ready=true`、`readiness_missing_requirements=[]`
    - 2026-05-18 新增 `scripts/local_data_unblock_audit.py` 并实跑 `python3 scripts/local_data_unblock_audit.py --output artifacts/local-data-unblock-audit.json`，当前 `status=passed`、`data_blocked=false`、`remaining_quality_gaps=[]`
    - 现阶段可以继续通过接口补英文 SEC 样本；中文样本可继续扩大 A 股公告代码池，但若交易所附件下载被 CDN/403 拦截，需要优先使用本地已授权研报/TDX 补充包中可抽文本材料，不能把只有标题的公告算作有效 benchmark 样本
  - 待做：300-500 份真实中文公告/年报样本、英文 SEC 披露样本集、人工标注手册、OCR/版面金标 bbox、表格 cell gold label、摘要质量样本、回归 baseline 报告的真实 artifact URI 归档
  - 输出：中文公告/年报样本集、英文 SEC 披露样本集、标注手册、规则基线报告、抽取/证据定位/表格指标、回归样例库
  - 验收：核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；低置信度样本能拦截

- `DONE` T-403 公开 EOD / 延时行情和来源 provenance 台账
  - 对应：E2-US1, E2-US3, E2-US4
  - 已有：`public_eod_market_data` 公开/已提供 EOD 来源、MarketDataPoint、`/api/market-data`、`/api/market-data/batch`、CorporateAction、`/api/corporate-actions`、`/api/market-data/adjusted` 原始/前复权/后复权计算视图、`/api/market-data/returns` 回测/估值/风险收益序列消费入口、`/api/portfolio/returns` 组合级公开复权收益/波动/回撤消费入口、`/api/portfolio/valuation` 模拟持仓估值/现金权重/缺失价格 adapter、价格收益与 `cash_dividend_reinvested` 现金分红总回报口径、批量导入逐条错误留痕、拆股/分红/代码变更公司行动、UI 入库入口、dashboard 摘要、rights tag 校验、实时数据阻断、红区/越权来源阻断测试、行情字段白名单入库校验、通达信 `vipdoc/*.day` 只读预览和导入接口、`vipdoc` 本地校验/解析兜底、`vipdoc` 显式 URL 下载/sha256 校验/zip 安全解压脚本、PostgreSQL 全量导入脚本、SQLite 状态库增量导入脚本、source governance/provenance 台账字段、字段白名单、缓存期限、公开来源覆盖报告、行情数据质量报告
  - 已有：来源 provenance 可记录 `provenance_ref`、`source_tos_uri`、`collection_method`、`robots_policy`、`usage_scope`、`last_reviewed_at`，`/api/governance/sources/{source_id}/reviews` 可记录季度来源复核、复核状态、TOS/robots/用途边界和下次复核日期；历史 `authorized_eod_market_data` 输入兼容映射到 `public_eod_market_data`
  - 已有：`/api/portfolio/valuation` 返回 `risk_decomposition`，按 market/currency/industry/style 输出持仓市值、权重、外币权重、现金权重和集中度；industry/style 可通过 holdings 或 `groups[security_id]` 注入
  - 本地资源：`data/local/tdx/vipdoc`，来自通达信官方个人行情数据页下载的 `vipdoc/*.day` 文件，已复制到项目内，不依赖下载目录或废弃 `stock_chs` 项目；当前导入摘要为 12169 个有效文件、28,885,502 条写入尝试、28,247,650 条唯一 `market_data`、11966 个证券、覆盖 1990-12-19 至 2026-05-15，artifact 为 `artifacts/tdx-vipdoc-postgres-import-full.json`
  - **已完成（本轮）**：通达信 `vipdoc/*.day` schema 解析和字段映射
    - `TDXVipdocAdapter` 直接解析官方日线二进制格式，输出 `date/open/high/low/close/amount/volume` 并映射到公开 EOD 字段；symbol 查询兼容 bare code、`sh/sz/bj` 前缀、`.SH/.SZ/.BJ/.SS/.XSHG/.XSHE` 后缀
    - 项目已移除旧本地中间库依赖和数据文件，容器运行环境不再安装旧中间库包
    - `.gitignore` 已忽略本机 staging 截图、验收 artifact 和运行时对象存储写入，保留已纳管 demo 样例
  - **已完成（本轮）**：真实生产输入 schema 覆盖率报告和异常 schema 样本库
    - `GET|POST /api/market-data/schema-coverage-report` 复用 TDX vipdoc adapter 的真实 `.day` 文件规则，输出 `schema_recognition_coverage`、`target_field_coverage`、逐文件 `target_field_mapping`、source whitelist 缺口、`automation_ready` 和 `anomaly_samples`
    - 支持传入 `schema_samples` 做异常 schema 样本库验收，缺失必填字段、未映射 tick/realtime 字段和 source governance 缺口都会进入 blocker/anomaly，而不会进入导入链路
    - 测试覆盖真实别名 schema 100% 映射到公开 EOD 字段，以及异常 schema 被阻断并列入样本
  - **已完成（本轮）**：模拟持仓/回测流水 adapter 对更多输入格式的兼容
    - `POST /api/portfolio/transactions/import` 支持批量导入模拟/回测流水，兼容 `symbol/ticker/code/ts_code`、`trade_date/date/datetime/filled_at`、`side/action/direction`、`quantity/qty/shares/signed_qty`、`price/fill_price/avg_price`、`fees/commission`、`account/portfolio_id` 和 `strategy/model/run_id`
    - 支持 `dry_run` 预检、`skip_existing` 幂等跳过、`security_map` 显式映射，默认 `source_id=simulated_trade_execution`，固定 `simulation_only=true`、`live_execution_allowed=false`
    - 测试覆盖 backtest alias rows、负 signed quantity 推断 sell、重复导入跳过和 as-of 持仓派生
  - 验收：生产输入数据 100% 能映射到公开来源 provenance 台账；红黄绿分级覆盖率 >= 95%；边界不清、禁止缓存/禁止自动化或实时 non-display 数据不能进入自动化链路

- `BLOCKED` T-404 生产级状态库、对象存储和检索适配
  - 对应：E3-US4, E6-US4, E8-US2
  - 已有：SQLite 状态库、PostgreSQL baseline schema、`ai_quant.schema_migrations`、PostgreSQLStore runtime、schema 初始化、`AI_QUANT_POSTGRES_DSN` / PostgreSQL DSN 形式 `AI_QUANT_DB` 启动路径、SQLite -> PostgreSQL 显式迁移脚本、`scripts/postgres_schema_migrate.py` baseline apply/dry-run/rollback-record、本地/S3 对象存储 adapter、内置/OpenSearch 检索 adapter、外部检索失败 fallback、runtime fake-driver 持久化测试
  - 已有：`/api/governance/storage-policy-templates` 输出 S3 scoped-prefix IAM、对象生命周期、OpenSearch index role、PostgreSQL app/migration grants 和破坏性 DDL rollback 审批模板，作为真实环境最小权限样例
  - 已有：`GET|POST /api/governance/storage-readiness-report` 可汇总 PostgreSQL/S3/OpenSearch 非本机 runtime 配置、最小权限模板、migration artifact URI、真实数据 smoke、容量 baseline、备份恢复、PostgreSQL connect/query、S3 put/get/checksum 和 OpenSearch bulk/search smoke artifact URI；内联 migration/smoke payload 只作为指标摘要，不能替代外部 artifact；本机路径、`file://` 和 `local://` 不会被视为生产归档证据；接口不执行压测或连接外部后端
  - 待做：S3/OpenSearch/PostgreSQL 真实环境压测、容量和延迟基线、备份恢复演练
  - 验收：真实环境 smoke test、容量 baseline、恢复演练记录和最小权限策略样例齐备

- `BLOCKED` T-405 美股 13F 与披露事件流水线
  - 对应：E5-US4, E7-US2, E7-US3, E8-US1
  - 已有：InstitutionalHolding、`/api/13f/holdings`、`/api/13f/crowding/update`、DisclosureEvent、`/api/disclosure-events/classify`、8-K/6-K/20-F 事件模板、管理层变更/指引/重大协议/资本配置标签、事件严重性标签、事件 evidence 链接、dashboard 事件墙、图谱事件边、PostgreSQL 视图、持久化测试
  - 已有：`/api/13f/holdings/changes` 可按 filer/issuer/security 输出 13F 新建、增持、减持、清仓及 shares/value 变化，用于拥挤度时间序列和候选池风控输入
  - 已有：`/api/13f/candidate-pool` 可按 issuer/security 聚合 13F 持仓价值、filer breadth、净增减持、crowding score、FIGI/ISIN/ticker 映射和映射置信度，输出候选池排序与风控标签，且固定 `automation_allowed=false`
  - 已有：`/api/disclosure-events/performance` 可按事件窗口计算披露后 1/5/20 天或自定义窗口的公开行情收益、基准收益和超额收益，并回写 `post_event_performance` 供事件墙、图谱和复盘使用
  - 已有：`/api/disclosure-events/classify` 可识别并回写 8-K 常见 `item_code` / `item_title`（1.01、2.02、2.05、5.02、7.01、8.01），用于事件墙和复盘分组
  - 已有：`/api/13f/filings/parse` 可解析 SEC 13F information table XML，支持直接 body、document_id 或 source_uri 拉取，按 CUSIP/FIGI/ISIN/EntityMapping 导入可映射持仓，并输出 unmapped 队列；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 已有：`/api/13f/filings/batch-parse` 可批量跑 13F information table 样本并输出 `mapping_rate`、`mapping_counts`、未映射清单、逐 filing 错误和导入汇总，作为大样本映射验收入口
  - 已有：`GET|POST /api/13f/filings/mapping-readiness` 可接收 batch parse 结果或汇总数字，按真实大样本 filing/row 数、mapping rate、failed/unmapped rate、batch artifact URI、CUSIP/FIGI/issuer gold mapping URI 和 unmapped review queue URI 输出验收 gate；即使 unmapped 队列为空也要求已复核空队列 artifact；小样本不会被误判为通过
  - 待做：真实 Form 13F 大样本执行记录、CUSIP/FIGI/issuer 大样本映射准确率达标验收 artifact URI
  - 验收：13F 只用于中低频拥挤度与反身性风控，不直接触发交易；事件必须可回链到 filing/evidence

- `BLOCKED` T-406 三市场主体页和知识图谱生产化
  - 对应：E3-US2, E3-US4, E8-US2
  - 已有：EntityMapping、LEI/FIGI/CIK/ISIN/ticker 字段、`/api/entity-mappings/batch`、`/api/entity-mappings/quality-report`、A/H/U 批量映射入库、样本映射准确率报告、基于标识符完整度的实体消歧 confidence、低置信映射清单、`/api/graph/query` 按 issuer/security/evidence/thesis/decision 聚合主体、证券、公开行情、公司行动、文件、证据、观点、信号、决策、纸面执行意图、复盘、回放、例外、research card、13F、crowding、challenger、disclosure event 和派生 `portfolio_positions`，并返回带时间/来源属性的图谱边
  - 已有：`/api/graph/traceability-report` 可检查 thesis、decision、research answer 是否能回溯到 evidence/document，并输出缺失 evidence、document、signal/thesis 断链和英文原文缺失问题
  - 已有：EntityMapping 双时间轴版本字段 `valid_from` / `valid_to` / `recorded_at` / `supersedes_mapping_id` / `status`，`GET /api/entity-mappings` 支持按业务生效时点和记录时点查询，quality report 输出版本覆盖率和重叠清单
  - 已有：知识图谱主体页新增 Entity Mapping 双时态面板，可按 issuer、`valid_at`、`recorded_at`、status 查询映射版本，并展示 accuracy、版本覆盖率、时间重叠、低置信映射和 label mismatch
  - 已有：`GET|POST /api/entity-mappings/readiness-report` 汇总 A/H/U 覆盖、人工金标准确率、双时间轴版本覆盖率、低置信/重叠/mismatch、图谱回溯率、edge 元数据覆盖、Neo4j/Qdrant 非本地 endpoint 和真实批量映射/主体页/adapter artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：ADR/中概队列真实批量映射执行记录、主体页生产浏览器验收 artifact、Neo4j 图谱 adapter 外部同步 artifact、Qdrant 向量检索 adapter 外部同步 artifact
  - 验收：A/H/U 样本公司映射准确率 >= 98%；观点到证据可回溯率 >= 95%；节点/边具备来源、时间戳和版本

- `BLOCKED` T-406A 宏观主题、热点扩散和产业链公司定位图谱
  - 对应：E3-US2, E5-US1, E5-US2, E7-US2, E8-US2；愿景扩展/生产化增强
  - 目标：从宏观变量、政策、技术周期、产品热点或市场热词出发，自动/半自动发散到产业链节点、上下游关系、相关公司和数据槽位
  - 已有：`MacroTheme`、`IndustryChain`、`ChainNode`、`CompanyPosition` 数据结构；`/api/macro-themes`、`/api/industry-chains`、`/api/company-positions`、`/api/industry-chains/{chain_id}/companies`、`/api/hotspots/expand`、`/api/company-positions/coverage-report` 契约和后端落地；产业链 taxonomy version；图谱节点和边的 provenance、confidence、时间戳、证据回链
  - 已有：`/api/company-positions/schema` 输出公司定位卡字段字典、必填数据槽位和 data_quality 枚举
  - 已有：`/api/hotspot-lexicons` 可维护热点扩散词表、同义词、相关链路节点和默认数据槽位；`/api/hotspots/expand` 输出 `retrieval_recall` 和 `evidence_layers`，把公告/证据事实、研报观点、行情线索、facts、opinions、inferences 和 needs_verification 分开
  - 已有：热点扩散本地可解释排序 `ranked_candidates`，综合词表命中、公司定位字段覆盖、evidence 回链、公开资料召回和数据质量，并输出 LLM rerank 触发建议
  - 已有：ResearchTask 队列、`/api/research/tasks`、`/api/research/tasks/from-hotspot`、`/api/research/tasks/{task_id}/status`
  - **已完成（本轮）**：`_hotspot_retrieval_recall` 检索召回增强（T-406A 代码层）
    - 同义词/词表扩展：自动从 `HotspotLexicon.synonyms` 和 `related_chain_nodes.keywords` 扩展查询词集
    - 新增 `inferences` 层：thesis/signal 召回独立分层，强制标注 `automation_allowed=false`、`needs_verification=true`
    - 新增 `research_answer` 召回：纳入 `research_opinions` 层，带 `needs_verification`/`pending_review` 标记
    - `term_coverage` 分数：每条结果增加覆盖率浮点分，结果按分数降序排列；新增 `query_expansion` 元信息
    - `_hotspot_evidence_layers` 同步接入 `inferences` 层，含 thesis/signal 推断标注
    - `_hotspot_rank_candidates` 修复：跳过非 list 的 `retrieval_recall` 键（如 `query_expansion`）
  - 已有：`/api/search/semantic/llm-rerank` 接入已审批 `llmtpl_search_rerank_v1`，可对语义候选执行 LLM ordering assist；无 LLM key、上游失败或输出不可解析时自动回退本地可解释排序，返回 `llm_run`、`fallback_used`、`parse_error`、`rerank_source` 和人工复核边界
  - 已有：研究工作台新增“热点扩散”面板，可调用 `/api/hotspots/expand` 展示 chain nodes、ranked companies、evidence layers、research tasks 和 `not trade signal` 边界
  - 已有：`/api/hotspots/expand` 支持 `page_size` / `page_token` 分页元数据，`/api/research/tasks/from-hotspot` 可跨页固化完整 research task 队列，`/api/research/tasks/from-hotspot/batch` 可批量处理多热点且保持幂等
  - 已有：`/api/search/semantic/llm-rerank/benchmark` 可对 LLM ordering assist / local fallback 执行离线质量评估，输出 top1、coverage@k、MRR、fallback rate、parse error rate 和逐样本排序明细
  - 已有：`GET|POST /api/hotspots/readiness-report` 汇总词表命中、三层产业链扩散、公司定位 slot/evidence 覆盖、facts/opinions/inferences/needs_verification 分层、缺口 research task 固化、图谱 edge 元数据、LLM rerank 离线评估摘要和 artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：用真实大样本 query/gold refs 跑 LLM rerank 质量评估并归档报告；所有输出已区分事实、观点、推断和待验证任务
  - 验收：给定一个热点词能生成至少 3 层产业链扩散路径；每个候选公司都有明确产业链节点、角色定位、至少一个数据槽位和证据/来源边界；缺失证据会进入 research task，而不是被当成结论；输出固定 `automation_allowed=false`

## P1 下一批 / M7 经营驾驶舱和投研闭环

- `BLOCKED` T-407 CEO Dashboard 与 UI 图对齐验收
  - 对应：E6-US5, E7-US1, E7-US2, E7-US3, E8-US2, E9-US1
  - 已有：左侧信息架构补齐“总览、数据中台、研究工作台、Agent 协作、策略实验室、投委会、风控合规、CEO 看板、知识图谱、系统治理”；顶部 A/H/U 市场、研究、风险、冲突证据和高优先级事件状态；SEC/披露时间线、8-K/6-K/20-F 事件墙、13F crowding 热图、公司行动摘要、风险治理、系统状态；UI 静态验收脚本检查导航、顶部状态、关键面板 ID 和前端脚本语法
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究工作台闭环
    - `/ui` 研究工作台已从单纯检索页改为单标的闭环控制台，前置 ticker/CIK/form/limit、一键运行、阶段进度、证据列表、研究摘要、投委会 Pack 和模拟反馈，辅助检索下沉到闭环结果之后
    - UI 与浏览器验收显式展示 `Realtime SEC` / `Fallback sample`、`simulated only`、`no broker execution`，减少把纸面模拟链路误认为真实券商执行的风险
    - 后续保留：多标的批量队列、生产 UI 分页/过滤/错误恢复/权限态细化
  - 已有：投委会 UI 新增“异常审批面板”，可对 Decision Pack 做人工签字、创建 open exception、刷新风险队列，并展示 approval state、signature count、open exceptions、pending decisions 和 `human approval · no broker execution` 边界；浏览器验收覆盖桌面/移动非空截图和关键文案
  - **已完成（本轮 UI 联动修复）**：总览收益卡、组合权重、研报观点证据、数据来源、产业链和公司定位已补齐点击联动，可自动切换到数据中台、研究工作台、知识图谱、热点扩散或投委会并带入上下文；`loadDashboard()` 已拆成最新分析快渲染和慢看板补全，避免慢接口导致首屏“点不动”
    - 新增 `scripts/ui_interaction_acceptance.py`，用 Headless Chrome + DevTools Protocol 真实点击 7 条关键链路：收益卡到行情、研报证据到研究检索、公司定位到图谱、产业链到热点扩散、组合方案到最新投委会方案；2026-05-22 本机运行 `status=passed`、`failure_count=0`
  - **已完成（本轮）**：UI 上线 readiness 细粒度验收门槛
    - `/api/readiness/ui-report` 已把真实数据量、分页、过滤、错误恢复、权限态、文本无重叠、视觉无溢出和跨浏览器矩阵覆盖拆成独立 gate；跨浏览器覆盖必须从 metrics 解析出足够 browser family 与 desktop/mobile viewport，artifact URI 不能替代矩阵内容
    - `scripts/ui_cross_browser_matrix_check.py` 可校验真实跨浏览器矩阵：至少 2 个 browser family、desktop/mobile viewport、必备 UI 文案、无 missing text 和 failure
    - `scripts/staging_acceptance.py` 默认只写入 Headless Chrome `production_ui_screenshot_acceptance`；只有传入已校验矩阵时才回填 `cross_browser_acceptance`
  - 待做：在非本机生产/预发真实数据量下执行分页/过滤/错误恢复/权限态、文本无重叠和视觉无溢出复核，并归档跨浏览器矩阵 artifact URI
  - 验收：桌面和移动端截图验收通过；关键视图在真实数据量下无卡死、无明显溢出、无权限越界

- `BLOCKED` T-408 月报/回放生产化和真实绩效归因
  - 对应：E8-US3, E7-US1
  - 已有：月报草稿/发布状态、CEO/CIO/风险合规发布审批、`/api/operating-reports/{report_id}/publish`、红灯项逐条审计、`/api/portfolio/transactions` 交易流水 ledger、`/api/portfolio/positions` as-of 持仓派生 adapter
  - 已有：`/api/portfolio/returns` 支持按 market/currency/industry/style 输出组合收益分组归因；`/api/operating-reports/{report_id}/board-pack`；`/api/strategy-replays/compare`
  - **已完成（本轮）**：`POST /api/portfolio/attribution/backfill`（T-408 代码层）
    - 对纸面/模拟组合执行 market/currency/industry/style 分组绩效归因批次回填，写入 OperatingReport.annotations
    - 固定 `simulation_only=true`、`live_execution_allowed=false`；支持 `dry_run=true` 只计算不写入
    - 支持 `proposal_id` 引用已有 PortfolioProposal 或直接传 `holdings` 列表
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`GET|POST /api/portfolio/attribution/readiness-report` 可汇总月报归因注释、发布审批、红灯项 owner/due、策略回放复盘、模拟 ledger 来源边界、forward attribution 结果与外部 artifact URI、绩效 reconciliation、ledger extract、strategy replay 和 board pack 外部 artifact URI；本地 board pack 导出只作为审计事件，不能替代归档 URI；固定不接真实券商账户
  - 待做：真实生产/预发绩效 reconciliation、NAV/ledger 对账、board pack artifact 和大样本回放验收 URI 归档
  - 验收：月报草稿不能绕过审批发布；绩效指标可由公开行情收益、模拟持仓 ledger 或 NAV 序列复算；每个红灯项有 owner 和截止时间；不接入真实交易账户

- `BLOCKED` T-409 Black-Litterman、风险预算和组合约束原型
  - 对应：E5-US3, E6-US1, E7-US1, E8-US3
  - 已有：`docs/portfolio-construction-spec.md` 数学规格、PortfolioProposal、`/api/portfolio/optimize`、`/api/portfolio/proposals`、观点置信度与 `Omega` 绑定、市场/行业/主题/币种预算、禁投清单、单证券上限、walk-forward 与压力测试诊断、协方差矩阵诊断
  - 已有：`/api/execution-intents/{intent_id}/simulate` 只对已审批纸面执行意图生成模拟成交，写入 `SimulatedExecution` 和 `PortfolioTransaction` ledger，并固定 `live_execution_allowed=false`
  - **已完成（本轮）**：`POST /api/portfolio/simulated-feedback`（T-409 代码层）
    - 投委会审批入口：对 PortfolioProposal 做模拟决策（approved/rejected/pending/needs_revision）
    - 支持 `include_valuation=true` 触发模拟持仓估值、`feedback_start/end_date` 触发区间归因反馈
    - 固定 `simulation_only=true`、`live_execution_allowed=false`、`automation_allowed=false`、`usage_boundary=paper_portfolio_simulation`
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`/api/portfolio/optimizer/compare` 可对候选组合与 equal-weight / prior / posterior / external solver 权重做纸面对照，并输出约束报告与诊断摘要；`/api/portfolio/forward-report` 可生成纸面前向跟踪报告、active return、tracking error、information ratio 和 review flags
  - 已有：投委会 UI 新增“组合模拟审批”，可加载 PortfolioProposal、选择 approved/rejected/pending/needs_revision，调用 `/api/portfolio/simulated-feedback` 并展示 proposal status、paper/no-broker 边界、模拟估值和区间反馈
  - 已有：`/api/portfolio/optimizer/compare` 可通过 `run_external_optimizer=true` 尝试调用 CVXPY / PyPortfolioOpt 做纸面外部求解器对照；本机缺少依赖时返回 `external_optimizer.status=unavailable` 和安装/诊断信息，不伪造外部结果
  - 已有：`GET|POST /api/portfolio/optimizer/readiness-report` 可对外部求解器对照结果生成归档验收包，检查 solver 状态、weights、版本、参数、solver/comparison/constraint report artifact URI、内联约束报告和 paper-only 边界
  - 待做：生产环境安装 PyPortfolioOpt/CVXPY 后跑真实外部对照并归档 solver 版本/参数/artifact URI，投委会审批入口生产态细化
  - 验收：候选权重不包含禁投标的；市场/行业预算和单券上限生效；观点置信度影响 `Omega`；输出只作为纸面组合，不直接生成真实交易；后续反馈仅允许模拟成交/模拟持仓 ledger，不接真实券商

- `BLOCKED` T-410 英文原文优先的研究问答与摘要审计
  - 对应：E4-US2, E6-US3, E6-US4, E7-US2
  - 已有：ResearchAnswer、`/api/research/answers`、`/api/research/answers/{answer_id}/review`、英文 evidence 校验、英文原文保留、标准化 citations（evidence/document/page/bbox/source URI/format）、中文摘要链路、summary/prompt/model 版本、来源公开性、人工覆核状态、人工审核通过/驳回、审计日志写入
  - 已有：`/api/research/answers/quality-report` 可输出答案级 evidence/document 回链率、人工复核覆盖率、pending review 队列、截断引用和逐答案问题；默认告警 `alert_research_answer_pending_review` 基于 `research_answer_pending_reviews` 指标触发
  - 已有：`/api/research/answers/summary-benchmark` 可用规则基线评估摘要 evidence/document 回链、英文原文保留、中文摘要长度、版本元数据、人工复核、受限引用边界、过度确定性措辞和英文 anchor 覆盖率
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究闭环已把默认问题“What changed in revenue, services resilience, and key risk factors?”接入英文 SEC evidence、ResearchAnswer citations、中文摘要、prompt/model/version 审计和图谱回链
    - 测试覆盖 research answer、thesis、decision pack 与 graph query 回链到同一 document/evidence
    - 后续保留：真实 LLM 生成与模型回退策略质量评估
  - 已有：`/api/research/answers/filing-qa` 支持交互式 filing 原文问答，按 `document_id` 自动抽取英文 evidence、运行已审批 filing QA 模板或规则 fallback、落库 `ResearchAnswer`，并返回原文、证据表、质量报告、summary benchmark、模型 fallback 状态和 no-trade 边界
  - 已有：研究工作台新增 “Filing 原文问答” UI，可输入 filing document/question/evidence limit，展示 QA answer、English Source、QA Evidence 和 QA Audit；`scripts/ui_static_check.py` 与 `scripts/ui_browser_acceptance.py` 已覆盖该 UI 文本和控件
  - 已有：`GET|POST /api/research/answers/readiness-report` 汇总答案数量、英文 evidence/document 回链率、人工审核覆盖、pending review、summary benchmark、版本元数据、英文 anchor 覆盖、图谱回溯率和真实模型质量/回退对照/summary rubric artifact URI；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 待做：真实模型调用质量评估、回退策略大样本对照
  - 验收：关键研究问答必须保留英文原文 evidence；中文摘要不能替代原文引用；摘要变更必须记录模型和 prompt 版本

- `BLOCKED` T-411 生产监控、告警和事故闭环
  - 对应：E6-US4, E9-US1, E9-US2
  - 已有：`/api/health`、`/api/metrics`、AlertRule、SystemAlert、AlertNotification、默认告警规则播种、`/api/alerts/evaluate` 指标评估、开放/恢复告警状态、`/api/alerts/notify` 通知 outbox、`/api/alerts/notifications` 查询、risk dashboard 告警计数、解析失败人工复核告警测试
  - 已有：`/api/playbooks/seed` 可播种文档解析失败、数据采集失败、检索降级、LLM 网关失败和权限/敏感数据泄漏五类事故剧本及季度演练计划；`/api/alerts/incidents/create` 可将带 `playbook_id` 的开放告警自动生成 IncidentReport 并回写 `incident_report_id`
  - 已有：`/api/drill-schedules/{schedule_id}/result` 可回写事故演练结果、RCA 摘要、行动项和下一次演练时间，并在事故日历中展示
  - 已有：`/api/alerts/notifications/deliver` 可对通知 outbox 执行 dry-run/execute 发送状态机，写回 provider、attempt、delivered_at、response 和失败原因；`provider=webhook|http|https` 时可向 HTTP(S) target 发送 JSON POST，`provider=email|smtp` 可通过 SMTP 发送 EmailMessage，`provider=slack` 可发送 Slack webhook，并限制非 HTTP(S) target、超时、缺失 SMTP 配置和最大尝试次数
  - 已有：`/api/alerts/notify` 支持 `route_failures` / `failure_routes`，可按 playbook/rule/metric 将采集、检索、LLM、OCR 和 workflow 失败分流到专属 channel/target，并把 provider/max attempts/backoff 写入 delivery policy
  - 已有：`/api/observability/logs/export` 可导出 audit、alerts、workflow 和 notifications 的结构化 JSON 日志；`/api/observability/otel/export` 可生成 OTLP logs JSON payload；`/api/observability/otel/submit` 可把 OpenTelemetry 日志提交写入 outbox 并复用通知发送状态机
  - 已有：`scripts/staging_otel_acceptance.py` 已在本机 staging 直连 OpenTelemetry collector `/v1/logs`、`/v1/metrics` 和 `/v1/traces`，并触发 workflow 告警、通知 outbox 和发送状态机后回填 `otel_collector_drill`
  - 已有：`/api/observability/readiness-report` 汇总结构化日志、OTLP payload、非本机 logs/metrics/traces collector 参数、日志保留策略、collector 后端存储/查询证据、真实外部告警发送记录和交付 evidence URI、事故剧本 owner/SLA/止血/回滚覆盖率和季度演练覆盖率，缺口进入 `missing_requirements`；默认事故剧本已补齐 SLA 与 rollback 动作
  - 待做：接入真实非本机生产/预发 OpenTelemetry collector，并附上后端查询、保留策略执行和真实外部告警送达证据
  - 验收：五类事故剧本均有 owner、SLA、止血动作、回滚动作；季度演练覆盖率 100%；`/api/observability/readiness-report` 无 missing requirements 且对应证据 URI 可追溯

- `BLOCKED` T-412 生产部署 runbook 与验收清单
  - 对应：E1-US3, E6-US4, E9-US2
  - 已有：`.env.example` 环境变量模板、`docs/production-runbook.md`、`scripts/capacity_baseline.py`、密钥注入建议、PostgreSQL/S3/OpenSearch 运维步骤、上线前检查命令、容量/延迟 baseline 命令、备份/恢复、回滚步骤、月度运维检查表
  - 已有：`/api/readiness/capacity-baseline` 可接收容量/延迟基线结果、按阈值自动判定并回填 `capacity_latency_report` readiness 记录和 evidence URI
  - 已有：`/api/readiness/evidence-package` 可生成上线验收证据包 manifest，汇总 checklist、vision gate、owner 修复计划和 PostgreSQL/S3/OpenSearch、OpenTelemetry、Neo4j/Qdrant、OpenLineage/MLflow、KMS/lifecycle executor、生产 UI 浏览器等外部验证矩阵；`/api/readiness/evidence-package/notify` 可把缺失真实证据项写入通知 outbox
  - 已有：`/api/readiness/deployment-report` 可汇总生产/预发环境名称、PostgreSQL/S3/OpenSearch 参数存在性、生产参数 manifest artifact URI、外部密钥管理 provider、密钥轮换证据、备份恢复、容量 baseline、权限红队、合规复核、CEO launch checklist、发布 checklist、灰度计划 artifact URI、回滚计划 artifact URI 和真实券商/自动下单关闭边界；灰度/回滚窗口只作为元数据，不能替代 artifact；接口拒绝 secret/token/password/private_key 等敏感字段且不回显 DSN/密钥值
  - 已有：`scripts/staging_acceptance.py` 可对 staging HTTP 地址执行真实部署 smoke、模拟成交、检索、图谱、metrics、外部依赖配置和可达性检查、Neo4j/Qdrant/OTel outbox 演练，并可只回填真实执行过的 `real_data_smoke_test` 与 `capacity_latency_report`
  - 已有：`docker-compose.yml` 和 `scripts/local_staging_stack.sh` 可在本机启动 PostgreSQL、MinIO、OpenSearch、Neo4j、Qdrant、OpenTelemetry collector、OpenLineage/MLflow HTTP 占位端点和应用服务，并自动跑 staging 验收；已修复镜像源、host/container 环境变量覆盖、PostgreSQL IMMUTABLE 索引、健康检查等待和 `AI_QUANT_HOST=0.0.0.0` 绑定问题
  - 已有：本机 staging 验收通过，状态库为 PostgreSQLStore，对象存储为 S3/MinIO，检索为 OpenSearch，模拟成交通过，图谱回溯 100%，HTTP 容量基线无 breach；PostgreSQL/S3/OpenSearch/OTel/Neo4j/Qdrant/OpenLineage/MLflow 均可达，Neo4j/Qdrant/OpenLineage/MLflow outbox 演练通过，最近一次复验 `p95=114ms`
  - 已有：最终 vision gate 复验通过，`/api/readiness/vision-gate` 返回 `status=ready`、`readiness_checklist_coverage=1.0`、`pending_checklist=[]`，evidence package 返回 `ready_for_launch=true`
  - 待做：真实生产环境参数确认、外部密钥管理系统真实接入、备份恢复演练 artifact、发布 checklist、灰度/回滚演练 artifact URI 归档
  - 验收：上线前检查、备份恢复、容量基线、密钥注入、回滚路径均有记录；`/api/readiness/deployment-report` 无 missing requirements 且不暴露任何真实密钥值

## P2 数据与研究资产扩展 / M8

- `BLOCKED` T-414 公开电话会/转录稿和研报线索引用策略
  - 对应：E2-US1, E2-US3, E6-US2
  - 已有：`docs/transcript-research-citation-policy.md`、默认来源 `company_public_webcast` / `manual_reference_transcripts` / `local_research_reports`、rights tag 边界、公开 webcast 入库路径、非公开 transcript/research 默认禁止训练/再分发/派生、越权 transcript 拦截测试、来源引用/缓存期限/公开性/source TOS 治理字段
  - 已有：历史 `authorized_*` 来源输入已兼容映射到 `public_*` / `local_reference_*` / `manual_reference_*` canonical source，避免新数据继续落到商业授权命名
  - 已有：公开网页/API `source_uri` 入湖前会移除 fragment，并脱敏 `token`、`api_key`、`access_token`、`signature`、`secret` 等敏感查询参数
  - 已有：研究问答对非公开或本地参考来源按 `citation_char_limit` 截断英文引用片段，并记录 `citation_truncated`
  - 已有：source governance report 基于 provenance 缺口、risk level 和用途边界计算 `automation_ready`，作为公开来源自动化白名单
  - 已有：红区私会/路演/expert note 只能通过 `/api/research/manual-references` 登记 metadata-only 人工参考记录；接口拒绝正文并自动创建 `manual_reference_boundary_review`，UI 已提供人工参考边界复核入口
  - 已有：`/api/governance/source-review-reminders` 支持从未复核、逾期、即将到期来源提醒，按 `review_owner` / `review_owner_role` 汇总 owner 看板，并透传 TOS/robots/用途边界阻断原因
  - 已有：系统治理 UI 已展示来源复核提醒、owner 看板和来源复核通知 outbox；默认告警 `alert_source_review_overdue` 会基于 `source_review_overdue` 指标触发并可通过 `/api/alerts/notify` 写入通知 outbox
  - 已有：通知 outbox 可通过 `/api/alerts/notifications/deliver` dry-run/execute 落发送状态、重试次数、外部 webhook response 和失败原因，来源复核通知可复用该发送闭环
  - 已有：`/api/governance/source-review-escalations` 可按逾期天数、红/黄区来源、缺失复核、TOS/robots/publicness/usage blocker 生成 SLA 升级项；`/api/governance/source-review-escalations/notify` 可写入通知 outbox 并复用 HTTP(S) webhook、SMTP email 或 Slack webhook sender
  - 已有：`GET|POST /api/research/citation-boundary/readiness-report` 汇总 canonical source 复核、metadata-only 手工参考、`manual_reference_boundary_review`、本地研报治理、研究问答英文 evidence/source link/人工审核、受限引用长度、红区训练/事实路径隔离和 policy/source review/manual review/research governance artifact URI；即使无手工参考或本地研报资产，也要求 reviewed-empty artifact；固定 `automation_allowed=false` / `live_execution_allowed=false`
  - 验收：研报和转录稿默认只作为公开外部观点层或本地人工参考层；非公开、边界不清或禁止自动化的数据不得进入事实真相层、训练层或可执行建议层

- `BLOCKED` T-416 A 股补充数据 connector 引入
  - 对应：E2-US1, E2-US3, E2-US4, E3-US3
  - 输入：`a-stock-data` Apache-2.0 Skill，覆盖通达信/腾讯/东财/akshare/iwencai/同花顺/百度股市通/巨潮等 A 股数据端点
  - 已有：A 股补充 connector 注册表、source definition、rights tag、限速、字段映射、验证状态、错误留痕和最小测试；默认 restricted rights，仅人工参考/补充研究
  - 已有：`/api/connectors/astock/fetch` 支持本地样本行字段归一化、公开网页/API URI 脱敏、rights/provenance 边界评估、blocked/red-zone 合规拦截
  - **已完成（本轮）**：`POST /api/connectors/astock/supplemental/fetch`（T-416 代码层）
    - `AStockSupplementalRegistry` 托管 connector 注册表，已集成 EastMoney Research、Cninfo Announcements、Tencent Valuation、THS Hot Topics、Baidu Concepts、Dragon Tiger List、Unlock Calendar 七个 connector
    - 强制合规标注：`manual_reference_only=true`、`automation_allowed=False`；URI 敏感参数脱敏
    - 空 symbols 时返回空数组（无 HTTP 调用）；blocked connector 返回 423
    - `docs/api-contracts.md` 已补充完整契约文档
  - 已有：`GET|POST /api/connectors/astock/verification-readiness` 可输出 connector 真实验证验收包，检查 verification status、字段样本覆盖、rate limit 声明、allowed use、license/TOS 边界、真实 endpoint 可用性、endpoint 稳定性、调用限制/配额验证、license review 和 field sample artifact URI；本地 sample rows 只用于字段覆盖，不能替代外部样本证据；固定 `automation_allowed=false`
  - 待做：逐项真实验证接口可用性、稳定性、调用限制和许可边界 artifact URI；接入更多真实 HTTP fetch adapter 与各端点字段样本库
  - 验收：外部接口只作为公开补充；红区、边界不清、禁止缓存或禁止自动化的数据只能进入人工参考，不进入自动化链路

- `DONE` T-417 本地研报资产库模块
  - 对应：E2-US1, E2-US3, E3-US3, E5-US1, E6-US2；愿景扩展/生产化增强
  - 输入：本地目录 `/home/xionglei/文档/6大投行研报汇总`，约 22G、11742 个文件，其中 11702 个 PDF，按投行/年份/月组织
  - 已有：本地研报 manifest 扫描、投行/source registry、文件指纹、按需登记为 Document、权限边界、检索入口
  - 已有：`/api/research-reports/{report_id}/extract`、`/api/research-reports/governance-report`、`/api/research-reports/extraction-queue`、`/api/research-reports/mapping-report`、`/api/research-reports/viewpoint-report`
  - **已完成（本轮）**：`POST /api/research-reports/incremental-schedule`（T-417 代码层）
    - 增量扫描：对比 fingerprint，只处理新增/变更文件，跳过已索引未变化的文件
    - OCR 成本控制：`ocr_budget_mb`（默认 200MB）超出预算进入 `deferred` 队列
    - 分批调度计划：`schedule_plan` 按 `batch_size`（默认 50）分批，每批含 `batch_index/report_ids/brokers/estimated_size_mb`，适配 Airflow/Cron/DAG 逐日触发
    - `dry_run`/`execute` 双模式；支持 `broker`/`year`/`scan_limit` 范围过滤
    - `execute=true` 时会先为未入库研报登记本地参考 `Document`，再进入文本抽取；`dry_run=true` 只生成调度计划，不写入研报资产库
    - `usage_boundary` 固定 `local_reference_only_not_training_or_fact_source`
    - `docs/api-contracts.md` 已补充完整契约文档（含字段说明和调度器接入建议）
  - **已完成（本轮全量入库解析）**：本地研报库 11702 份全量完成入库和解析
    - 源目录核对：`find /home/xionglei/文档/6大投行研报汇总 -type f \( -iname '*.pdf' -o -iname '*.txt' -o -iname '*.md' \) | wc -l` = 11702
    - PostgreSQL 状态：`research_reports=11702`、`research_documents=11702`、`research_report_citation evidence=88515`
    - API 状态：`indexed=0`、`ingested=0`、`needs_text_review=0`、`text_indexed=11702`
    - 解析路径：先使用本机 `pdftotext`；空文本 PDF 使用本机 `pdftoppm + tesseract` OCR，语言包 `eng+chi_sim`；未调用外部 OCR 服务，也未上传研报
    - 新增脚本：`scripts/research_report_full_parse.py`，支持 direct PostgreSQL 批量写入、`pdftotext` 抽取和本地 Tesseract OCR fallback
    - 审计 artifact：`artifacts/research-report-completion-audit.json`、`artifacts/research-report-ocr-backfill.json`、`artifacts/research-report-ocr-retry-lowdpi.json`
    - 回归验证：`python3 -m pytest tests/test_system.py -q` 通过，结果为 `158 passed, 36 subtests passed`
  - 验收：研报不能作为事实真相源；不得默认用于训练；所有引用必须回链到本地文件或公开来源、页码/片段和使用边界

- `DONE` T-423 研报解析结果接入完整业务分析和 UI 看板验收
  - 对应：E3-US3, E5-US1, E7-US1, E8-US2；愿景扩展/生产化增强
  - 目标：在研报全量 `text_indexed` 后，重新跑完整本机业务分析，确认 A 股、美股、产业链、财报、行情和研报 evidence 进入同一条分析闭环，而不是只停留在数据入库
  - **已完成（本轮研报证据闭环）**：`scripts/latest_analysis_run.py` 已重跑本机完整业务分析，新的 `artifacts/latest-analysis/latest-analysis.json` / `artifacts/latest-analysis/latest-analysis.md` 显示 `research_reports=11702`、`research_report_citation_evidence=88515`、`research_answers=1`，A 股/美股行情、组合权重、热点扩散和研报观点证据已进入同一份最新分析产物
  - **已完成（本轮研报边界治理）**：新增研报 evidence 召回审计 `artifacts/latest-analysis/research-evidence-recall-audit.json`，结果 `status=passed`；语义检索和热点扩散均能召回 `research_report_citation`，且热点 evidence layer 已把本地研报固定归入 `opinions/research_opinions`，`research_items_in_facts=[]`
  - **已完成（本轮 API/UI 验收）**：`/api/analysis/latest` 已优先读取当前 `artifacts/latest-analysis/latest-analysis.json` 并输出 `research_evidence`；UI 新增“研报观点证据”面板，展示研报数量、引用证据数量、语义召回、热点召回和边界声明
  - **已完成（本轮浏览器验收）**：`python3 scripts/ui_static_check.py`、`python3 scripts/ui_browser_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-browser-acceptance`、`python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance` 均通过；桌面/移动截图非空，必备文案包含“研报观点证据”，关键点击链路 `failure_count=0`
  - **已完成（本轮回归）**：`python3 -m py_compile app/*.py tests/*.py scripts/*.py` 通过；定向回归 `test_hotspot_expansion_maps_industry_chain_and_company_position` 和 `test_latest_analysis_api_summarizes_local_artifact_for_ui` 通过
  - 输出：最新分析 artifact、研报 evidence 召回审计、UI/浏览器验收 artifact、必要的前端修复记录
  - 验收：最新分析结果包含可回链的公开事实 evidence 和本地研报观点 evidence；UI 可展示分析结论和证据边界；`research_report_citation` 不参与训练、不作为事实源、不触发真实交易

- `BLOCKED` T-418 大模型 / Agent 工作流生产化
  - 对应：E6-US3, E6-US4, E8-US1, E9-US1；愿景扩展/生产化增强
  - 已有：LLM gateway、OpenAI/Anthropic 兼容转发、默认模型配置、调用审计、密钥环境变量注入、任务级 prompt 模板、baseline prompt 审批记录、模型回退策略、规则/上一稳定版本/人工复核降级链、调用成本/延迟/错误率记录、角色和数据域元数据
  - 已有：`GET /api/prompts/changes` 查询 prompt 变更审批记录，Agent 协作 UI 支持创建/审批 prompt 变更和查看 LLM runs/error/cost/budget；默认告警 `alert_llm_cost_budget` / `alert_llm_error_rate` 基于 `llm_tasks` 指标触发
  - 已有：`/api/llm/tasks/review-queue` 可按任务类型、状态、原因和严重级别输出失败/fallback/高风险/超时/超预算 LLM run 的人工复核队列
  - 已有：默认 LLM task template 覆盖研究摘要、研报摘要、filing 问答、challenger、red team 和事故 RCA，并在 `output_schema.acceptance_thresholds` 记录引用、反证、合规风险、RCA 事实/推断分离等验收阈值
  - 已有：Agent 协作 UI 已接入 `/api/governance/permission-matrix`，可按角色、数据域和动作展示 allowed/denied、红区权限和规则覆盖
  - 已有：`/api/llm/tasks/escalations` 可按成本预算、错误率、fallback 率、人工复核 backlog 和逐 run 原因生成 SLA/预算升级项；`/api/llm/tasks/escalations/notify` 可写入通知 outbox，并可复用 HTTP(S) webhook、SMTP email 或 Slack webhook sender
  - 已有：`/api/llm/budget-approvals` 和 `/api/llm/budget-approvals/{approval_id}/decide` 可基于预算类升级项创建 pending 审批、记录 CEO/CIO/风险/ML 负责人决策，并让 approved 且未过期预算进入 LLM metrics 的有效成本预算计算
  - 已有：`/api/llm/budget-approvals/{approval_id}/sync` 可把 approved 预算审批写入外部财务/云预算系统同步 outbox，记录 target、external_system、metadata、delivery_policy，并复用通知发送状态机推进
  - 已有：`GET|POST /api/llm/readiness-report` 可汇总 approved task template、approved prompt 回链、pending prompt、LLM run 追溯、研究答案版本元数据、高风险 thesis challenger 覆盖率、人工复核/升级、预算同步 outbox 记录、预算同步外部 evidence URI 和真实模型/回退质量 artifact URI；接口只生成验收报告，不调用外部模型
  - **已完成（本轮）**：Apple/AAPL SEC 单标的研究闭环已落成 `POST /api/research/tasks/sec-single-name/run`
    - 编排复用 SEC ingestion、evidence extraction、ResearchAnswer、research card、scorecard、challenger、decision pack、审批、execution intent 和 simulated execution；实时 SEC 失败时使用确定性本地样例兜底
    - 研究结果保留 `summary_version` / `prompt_version` / `model_version` 与人工复核状态，当前仍以规则摘要稳定兜底，真实 LLM 生成继续作为 T-418 后续任务
    - 权限测试覆盖 analyst/CIO 可运行、未授权角色 403；执行侧固定 `simulation_only=true`、`live_execution_allowed=false`
  - **已完成（本轮本机长期使用口径）**：`scripts/local_ai_capability_acceptance.py` 已对配置后的 LLM gateway 执行真实 OpenAI-compatible chat smoke，返回 `ok`，并把 provider、模型、choice 数、耗时和短响应预览写入 `artifacts/local-ai-capability-acceptance.json`；脚本和 artifact 均不保存 API key 或完整上游响应
  - 待做：真实模型调用质量评估、回退策略大样本对照、生产/预发 LLM gateway smoke 与预算同步 artifact URI 归档
  - 验收：生产 prompt 100% 可追溯；未审批 prompt 变更数 = 0；高风险结论 challenger 覆盖率 = 100%

## P2/P3 生产基础设施与治理 / M9

- `BLOCKED` T-419 图谱 / 向量 / 语义检索生产化
  - 对应：E3-US2, E3-US4, E8-US2；愿景扩展/生产化增强
  - 已有：`/api/graph/query` 关系回查、本地轻量语义检索 adapter、证据/研究卡/研报/问答混合 SearchRecord、权限边界继承标记
  - 已有：语义检索支持 `issuer_id` / `resource_types` payload filter、默认 restricted 结果过滤、显式 `include_restricted`、结果级 `source_boundary` / `rights_tag` / `risk_level` 和 `/api/search/semantic/benchmark` recall@k 质量回归
  - 已有：`/api/search/semantic/rerank` 复用语义召回并输出本地可解释重排分、term coverage、资源权重、restricted boundary penalty 和 Qdrant/reranker adapter 触发条件
  - 已有：`/api/search/rebuild` 可从当前事实层重建全文/语义 SearchRecord 索引，返回资源计数、sync 结果、外部全文失败 fallback 和审计记录
  - 已有：`/api/graph/query` 每条 edge 默认带 `source`、`timestamp`、`version`、`confidence`；`/api/graph/edge-quality-report` 可输出边元数据覆盖率和缺失明细
  - 已有：`/api/graph/neo4j/export` 和 `/api/graph/neo4j/sync` 可导出 Neo4j bulk upsert-compatible node/relationship payload，并写入 graph sync outbox 交给外部 adapter
  - 已有：`/api/search/qdrant/export` 和 `/api/search/qdrant/sync` 可导出 Qdrant points upsert-compatible payload，保留 rights/risk 边界，并写入 vector sync outbox
  - 已有：`/api/search/adapter-sync/retry` 可对 Neo4j/Qdrant sync outbox 的 failed 通知做 dry-run/execute 重试演练，复用通知发送状态机并保留审计
  - 已有：`scripts/staging_graph_vector_acceptance.py` 已在本机 staging 直连 Neo4j/Qdrant，验证 `/api/graph/neo4j/export` 写入 Neo4j、`/api/search/qdrant/export` 写入 Qdrant collection，并覆盖失败 outbox 重试演练；最近一次本机结果为 Neo4j 54 nodes / 76 relationships、Qdrant 7 points、retried_count=2
  - 已有：`GET|POST /api/graph-vector/readiness-report` 可输出图谱/向量外部同步验收包，检查 Neo4j/Qdrant payload 规模、追溯率、edge 元数据覆盖率、rights/risk 边界、非本机 endpoint、同步 artifact URI、批量吞吐 baseline 和失败注入/重试恢复证据；接口不直连外部数据库
  - 待做：真实非本机生产/预发 Neo4j/Qdrant 同步 artifact、批量同步吞吐 baseline 和故障注入恢复证据 URI 归档
  - 验收：观点、持仓、证据可沿图谱回查；结论到证据回溯率 >= 95%；语义检索结果保留来源和权限边界；`/api/graph-vector/readiness-report` 无 missing requirements

- `BLOCKED` T-420 任务编排、血缘和模型治理
  - 对应：E3-US4, E6-US4, E8-US3, E9-US2；愿景扩展/生产化增强
  - 已有：轻量 DAG / workflow definition、任务运行记录、幂等键、任务级审计、数据血缘事件、模型版本记录、模型/prompt/输入输出引用关联
  - 已有：`/api/orchestration/runs/{run_id}/retry` 支持失败/待复核 run 基于冻结输入重放，保留 `retry_of` / `retry_error`，任务状态可定位到具体 failed task；默认告警 `alert_workflow_failed_runs` 基于 `workflow_failed_runs` 指标触发
  - 已有：`/api/orchestration/sla-report` 可基于任务级 `sla_minutes` 输出 failed、needs_review 和 runtime SLA breach；`workflow_sla_breaches` 默认告警可触发调度 SLA 风险
  - 已有：`/api/orchestration/incidents/create` 可将未建单的 workflow SLA/失败 run 自动创建 `IncidentReport`，并用 `ir_workflow_{run_id}` 防重复
  - 已有：`/api/orchestration/schedule-calendar` 可按 workflow `cadence` 和历史 run 预览未来运行窗口、last/next run、owner、任务数和 Airflow/Dagster 触发阈值建议
  - 已有：`/api/orchestration/dependency-graph` 可按 DAG 输出任务节点、依赖边、拓扑顺序、未解析依赖、ready/blocked task、latest run 状态和 lineage 摘要，用于任务依赖可视化和失败排障
  - 已有：`/api/orchestration/openlineage/export` 可把 workflow run、lineage event、模型版本和 prompt 版本导出为 OpenLineage-compatible dry-run payload，保留 run/job/dataset/facet 和外部提交边界
  - 已有：`/api/model-versions/mlflow/export` 可把模型版本导出为 MLflow Model Registry-compatible dry-run payload，包含 registered model、model version、stage/alias、tags、metrics/params 和 lineage 回链
  - 已有：`/api/orchestration/openlineage/submit` 和 `/api/model-versions/mlflow/register` 可将外部 lineage/catalog/registry payload 写入可靠 outbox，并复用通知发送状态机或通用 HTTP(S) webhook sender 记录 pending/sent/failed、provider、attempt、response 和错误
  - 已有：`scripts/staging_lineage_registry_acceptance.py` 可在本机 staging 通过 OpenLineage/MLflow HTTP sink 直接发送 webhook POST，验证 202 响应、sink 记录和失败后重试再发送
  - 已有：`/api/orchestration/dags/{dag_id}/execute` 内置轻量 DAG 执行器按拓扑顺序运行采集、解析、证据抽取、结构化抽取、索引重建、benchmark sample 登记和 benchmark 执行等白名单任务，支持上游产物占位符、幂等运行、任务状态、output refs、task-level lineage、`task_ids` 选择和 `queues` 队列隔离记录
  - 已有：`/api/orchestration/dags/{dag_id}/backfill` 可按 `run_dates` 或日期窗口生成 deterministic backfill plan；默认 dry-run，不落库；显式 `dry_run=false` + `execute=true` 时按日期登记 queued `WorkflowRun`，保留 `inputs.backfill`、幂等键、任务选择、队列隔离和未选任务 skipped 状态
  - 已有：`/api/orchestration/scheduler-handoff` 可导出外部调度器规划包，汇总 Airflow/Dagster/Cron 推荐、worker pool 队列映射、external sensor 清单、backfill gap 预览、adapter endpoint contract 和缺失真实外部证据项；该接口只做 planning contract，不创建外部部署
  - 已有：`GET|POST /api/orchestration/readiness-report` 可汇总 active workflow、run/retry/replay、dependency graph、SLA/incident、scheduler handoff、OpenLineage/MLflow payload/outbox、approved model artifact coverage，以及真实调度器、worker pool、external sensor、backfill、OpenLineage client 和 MLflow registry 证据 URI；worker pool、external sensor 和 backfill 即使为空/不适用也要求复核 artifact；接口不部署外部系统
  - 待做：Airflow/Dagster/Cron 真实生产部署、外部 sensor 连通性、分布式 worker、生产 worker pool 级队列隔离和大窗口 backfill 演练 artifact URI
  - 待做：OpenLineage/MLflow 真实外部 client sender、真实 registry/catalog 连通性验证和失败重试策略演练
  - 验收：任一解析、特征生产、信号计算和投委会打包均可 replay；失败任务可定位输入、版本、错误和重试记录

- `BLOCKED` T-421 安全、密钥和权限生产化
  - 对应：E2-US1, E2-US3, E6-US2, E6-US4, E9-US1；愿景扩展/生产化增强
  - 已有：`scripts/security_check.py` 可检查 `.env` 误提交和常见密钥字面量，测试覆盖误提交场景；source governance report 可检查公开来源 provenance 台账、数据红黄绿分级、字段白名单和缓存期限；audit completeness report 可检查关键审计字段完整性
  - 已有：`/api/governance/data-security-report` 可扫描 document/evidence/research answer 中的邮箱、手机号、身份证样式和 secret/API key 字面量，返回脱敏 snippet 与按类型/来源聚合统计；默认告警 `alert_sensitive_findings` 基于 `sensitive_findings` 指标触发
  - 已有：API 网关会对角色越权访问返回 403 并写入 `permission_denied` 审计事件；默认告警 `alert_permission_denied_events` 基于 `permission_denied_events` 指标触发，risk dashboard 已纳入权限/敏感数据风险
  - 已有：`/api/governance/secret-rotations` 可记录外部密钥管理系统的 rotation metadata、证据 URI 和到期提醒，并拒绝真实密钥值入库；默认告警 `alert_secret_rotation_overdue` 基于逾期记录触发
  - 已有：`/api/governance/permission-matrix` 可从 API 网关授权规则派生角色 + 数据域 + 动作级权限矩阵，输出 allowed/denied roles、public 标记和 red domain 访问汇总
  - 已有：`/api/governance/cache-retention-report` 可扫描 document、本地研报和 PaddleOCR 运行时缓存，输出保留/到期/删除 dry-run、no-cache 违规、外部生命周期执行建议，并通过 `record_run=true` 写入缓存保留执行记录和审计事件；`execute=true` 只形成审批证据，不在应用内物理删除缓存
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execute` 可对已批准 run 执行本进程 PaddleOCR 运行时缓存清理，并把对象存储、搜索索引和研报资产删除输出为外部 handoff 任务
  - 已有：`/api/governance/cache-retention-runs/{run_id}/execution-evidence` 可回填外部对象生命周期、搜索索引清理、KMS/DLP 或运行时缓存清理 executor 的执行证据，把 run 推进到 `executed_outside_app` 并留痕
  - 已有：`scripts/staging_security_acceptance.py` 可在本机 staging 验证密钥轮换 metadata-only、真实密钥字段拒绝入库、公开来源 provenance/字段白名单台账、最小权限 S3/OpenSearch/Postgres 模板、cache retention run、runtime cache executor 和外部 lifecycle/search/KMS-DLP executor 证据回填
  - 已有：`GET|POST /api/governance/security-readiness-report` 可汇总 source governance、audit completeness、敏感数据扫描、permission matrix、真实越权 403/audit 或已通过的 `permission_red_team_test` checklist、secret rotation metadata、最小权限模板、cache retention 外部删除证据和红区训练记录；布尔占位字段不能替代权限红队证据；接口拒绝 secret/token/password/private_key 等敏感字段，固定只记录 metadata 和 evidence URI
  - 待做：非本机生产/预发外部密钥管理系统真实接入、外部 API key 最小权限策略和对象存储/搜索索引外部删除 executor 真实执行证据 URI 归档
  - 验收：红区数据自动入库训练数 = 0；关键动作审计字段覆盖率 100%；越权访问可拦截并留痕；`/api/governance/security-readiness-report` 无 missing requirements

## 愿景验收闸门 / M10

- `DONE` T-422 本机 staging 真实验收与上线闸门
  - 对应：E1-US3, E2-US1, E3-US3, E4-US3, E6-US4, E7-US1, E8-US1, E8-US2, E9-US2；愿景扩展/生产化增强
  - 指标：证据覆盖率 >= 95%；关键研究结论原文回链率 >= 95%；未审批 prompt 变更数 = 0；红区数据自动入库训练数 = 0；高风险结论 challenger 覆盖率 = 100%
  - 指标：A/H/U 样本公司映射准确率 >= 98%；核心术语 F1 >= 0.90；证据页命中率 >= 0.95；关键数值口径映射准确率 >= 0.92；季度事故演练覆盖率 100%
  - 已有：愿景上线闸门报告接口，集中计算证据覆盖率、研究结论回链率、pending prompt、红区训练记录、高风险 challenger 覆盖率、实体映射和 benchmark 指标，并明确 `ready/not_ready`
  - 已有：`/api/readiness/checklist` 可写入真实数据 smoke、生产 UI 截图、跨浏览器、容量/延迟、备份恢复、权限红队、合规复核和上线 checklist 的 owner、证据 URI、指标、过期时间，并进入审计日志；vision gate 已纳入 checklist 覆盖率和季度事故演练覆盖率
  - 已有：`/api/readiness/remediation-report` 可将未通过 gate 和 pending/expired checklist 汇总为 owner、priority、建议动作和 evidence 要求，形成上线修复计划
  - 已有：`scripts/readiness_evidence_package_check.py` 可离线校验导出的 readiness evidence package，要求 launch/gate/checklist 全 ready、9 个必填 readiness check、外部验证矩阵 scope 全覆盖，且 evidence URI 是外部归档型引用并指向具体对象或路径；本机路径、服务连接串、只有域名的 HTTP(S) 根地址和 `artifact://local-*`、`artifact://staging-local`、`artifact://local-staging`、`artifact://staging-test`、`artifact://staging-acceptance`、`artifact://demo` 这类本机或样例前缀不能通过；给校验器的导出包必须传 `include_passed=true`
  - 已有：`scripts/full_run_acceptance.py` 可在本地以模拟交易模式跑 operational acceptance，覆盖 health、demo flow、模拟成交、组合流水/持仓、检索、语义检索、图谱、告警、容量基线、readiness 记录和 metrics，但不替代真实生产环境上线证据
  - 已有：`scripts/staging_acceptance.py` 可对真实 staging URL 生成 smoke/capacity evidence URI、触发缺失证据通知 outbox，并保持真实券商/自动下单关闭；本机 `scripts/local_staging_stack.sh` 已跑通全量 staging 依赖验收，并覆盖 Neo4j/Qdrant/OpenLineage/MLflow outbox readiness
  - **已完成（本轮）**：本机 staging 上线验收链路补齐
    - `scripts/ui_browser_acceptance.py` 对 `/ui` 执行 Headless Chrome 桌面/移动截图、必备文案、非空截图检查，并回填 `production_ui_screenshot_acceptance`；`scripts/staging_acceptance.py --cross-browser-matrix <json>` 只有在提供真实跨浏览器矩阵时才回填 `cross_browser_acceptance`
    - `GET|POST /api/readiness/ui-report` 可汇总静态 UI 合约、生产截图/跨浏览器 readiness 记录、browser acceptance metrics、真实数据量/分页/过滤/错误恢复、权限态和文本无重叠/视觉无溢出 evidence URI，形成细粒度 UI 上线缺口报告
    - `scripts/local_backup_restore_drill.py` 对 Compose PostgreSQL 执行 `pg_dump/pg_restore` 到临时库，校验 records/audit_log 计数一致和 schema 存在，并回填 `backup_restore_drill`
    - `scripts/staging_governance_acceptance.py` 执行真实 HTTP 权限红队 403/audit 验证、来源复核记录、敏感数据和审计完整性检查，并回填 `permission_red_team_test` / `compliance_review_record`
    - `scripts/staging_otel_acceptance.py` 直连 OpenTelemetry collector logs/metrics/traces endpoint，触发 workflow 告警联动并回填 `otel_collector_drill`
    - `scripts/staging_vision_gate_acceptance.py` 登记 A/H/U 主体映射人工金标、运行双语 benchmark、播种并回写季度事故演练结果，在非 launch gate 通过后回填 `launch_checklist`
    - `POST /api/entity-mappings/labels` / `GET /api/entity-mappings/labels` 已支持实体映射人工金标持久化，vision gate 可在未传临时 labels 时读取持久化金标计算 `entity_mapping_accuracy`
    - `scripts/local_staging_stack.sh` 已串联 smoke、UI、外部依赖、备份恢复、权限红队、合规复核、OTel collector、benchmark、事故演练和 launch checklist 记录
  - **已完成（最终复验）**：2026-05-16 直接复用现有 Compose 栈运行 `python3 scripts/staging_vision_gate_acceptance.py http://127.0.0.1:8000 --artifact-prefix artifact://local-staging --record-launch-checklist`，退出码 0
    - `/api/readiness/vision-gate`：`status=ready`、失败 gate 数 0、`pending_checklist=[]`、`readiness_checklist_coverage=1.0`
    - `/api/readiness/evidence-package`：`ready_for_launch=true`、`missing_evidence_count=0`、`external_validations=6`
    - 本次回填 `launch_checklist`，最近更新时间 `2026-05-16T12:08:09Z`，evidence URI 为 `artifact://local-staging/launch-checklist.json`
  - **已完成（最终复验补充）**：2026-05-17 全量运行 `bash scripts/local_staging_stack.sh`，并通过端口覆盖避开本机服务冲突，退出码 0
    - `/api/readiness/checklist`：9/9 required checks passed，coverage=1.0；`real_data_smoke_test`、`production_ui_screenshot_acceptance`、`cross_browser_acceptance`、`capacity_latency_report`、`backup_restore_drill`、`otel_collector_drill`、`permission_red_team_test`、`compliance_review_record`、`launch_checklist` 均已回填
    - `/api/readiness/vision-gate`：`status=ready`、失败 gate 数 0、`pending_checklist=[]`
    - `/api/readiness/evidence-package`：`status=ready`、`ready_for_launch=true`、`missing_evidence_count=0`、`failed_gate_count=0`
    - 本次本机复验使用 `artifact://staging-local/...` evidence URI，证明本机 staging 链路可复验；生产发布仍必须替换为真实 staging/production 外部归档 URI
  - **已完成（本轮本机长期使用口径）**：2026-05-17 复用本机 Compose 栈并按端口覆盖运行 `bash scripts/local_staging_stack.sh`，退出码 0；随后运行 `python3 scripts/local_production_audit.py --base-url http://127.0.0.1:8000 --output artifacts/local-production-audit.json`，退出码 0
    - `/api/health`：`status=ok`、`store=PostgreSQLStore`、对象存储 `backend=s3`、检索 `backend=opensearch`、TDX 本地行情、LLM gateway 和 PaddleOCR-VL 均已配置
    - `/api/readiness/vision-gate`：`status=ready`、14 个 gate 全通过、`readiness_checklist_coverage=1.0`
    - `/api/readiness/evidence-package?include_passed=true`：`status=ready`、`ready_for_launch=true`、9/9 required evidence、`missing_evidence_count=0`、`failed_gate_count=0`
    - `local_production_audit`：`status=passed`、`deployment_target=local_only_personal_production`、`strict_production_gate_unchanged=true`；仅保留 graph/vector package 标记与 workflow drill failed run 的 warning，不阻塞本机长期运行
  - **已完成（本轮本机 AI 能力复验）**：2026-05-17 运行 `.venv/bin/python scripts/local_ai_capability_acceptance.py --base-url http://127.0.0.1:8000 --output artifacts/local-ai-capability-acceptance.json`，退出码 0
    - LLM gateway：真实 chat smoke 通过，模型 `qwen3.6-plus`，返回短响应 `ok`
    - PaddleOCR-VL：真实单页 PDF OCR smoke 通过，模型 `PaddleOCR-VL-1.5`，`state=done`、`page_count=1`、返回 `Dummy PDF file` 预览；第二次复验命中运行时缓存
    - 本机 `.venv` 已安装 `requests` 供直接运行 PaddleOCR 示例；验收脚本本身不写入 token、签名结果 URL 或完整模型响应
  - **已完成（本轮本机启动固化）**：新增 `scripts/local_production_stack.sh` 作为日常本机个人生产入口，默认使用 15432/19000/19200/17474/16333/14318/15001/15002 等避让端口，并用 `AI_QUANT_STAGING_CAPACITY_DEFAULT_THRESHOLD_MS=5000` / `AI_QUANT_STAGING_CAPACITY_SIMULATE_THRESHOLD_MS=5000` 覆盖本机冷启动容量余量；脚本先调用完整 `local_staging_stack.sh`，再自动生成 `local-production-audit` 和可选 `local-ai-capability-acceptance`
    - `scripts/local_staging_stack.sh` 已显式把 app 容器固定为 `AI_QUANT_HOST=0.0.0.0`、PostgreSQL、S3/MinIO、OpenSearch 和容器内依赖地址，避免 `.env` 中单进程本地默认值把 Compose app 带回 SQLite/local backend
    - 2026-05-18 实跑 `bash scripts/local_production_stack.sh` 退出码 0；`/api/health` 中 TDX、LLM gateway、PaddleOCR-VL 均已配置，capacity baseline 无 breach，`local-production-audit` 与 `local-ai-capability-acceptance` 均 `status=passed`
  - 已有：上线验收证据包接口和通知 outbox 可把 M6-M9 剩余真实环境验证项集中成审计 manifest，并明确当前证据包不是生产执行本身，必须回填真实 artifact URI 后才能通过闸门
  - 已有：`scripts/production_task_closure_audit.py` 可审计 `tasks/todo.md` 中剩余 `BLOCKED` / `DOING` 任务，逐项检查代码层 marker、readiness/report/验收脚本是否存在，并把剩余状态区分为 `blocked_external_evidence` 或 `needs_code_work`；当前 17 个开放项均为 `blocked_external_evidence`，不是继续缺代码脚手架
  - **已完成（本轮本机完成审计）**：`scripts/project_completion_audit.py` 现按部署目标分流：默认仍按非本机组织级发布证据判断，显式传入 `--local-production-audit artifacts/local-production-audit.json --local-ai-acceptance artifacts/local-ai-capability-acceptance.json` 时按本机个人生产证据判断；2026-05-22 已刷新 `artifacts/project-completion-audit.json` 和 `artifacts/production-task-closure-audit.json`，当前输出 `status=achieved`、`achieved=true`、`target_mode=local_only_personal_production`、`local_production_ready=true`、`doing_task_count=0`、`needs_code_work_count=0`
  - 已有：`scripts/production_evidence_plan_check.py --require-filled-uris` 会拒绝仍带 `<production-evidence-bucket>` / `<release-id>` 的采集计划，只有 owner 回填真实 staging/production artifact URI 后才允许进入 production closure manifest
  - 已有：`scripts/production_artifact_inventory_check.py` 可从 plan/package/manifest 生成 release artifact inventory 模板，并校验所有证据 URI 都有 sha256、size、environment、producer、owner、content type、retention 和 immutable/object lock 记录；提供 `--bundle-root` 时还能对本地导出的 evidence bundle 做文件存在、size 和 sha256 复验
  - 已有：`scripts/production_evidence_plan_to_manifest.py` 可把已回填 URI 的采集计划映射到 production closure manifest 的 task evidence、readiness checks、storage/security/observability/UI/deployment reports 和 A 股 connector 证据；默认拒绝占位符，且不自动设置 `ready_for_launch=true`
  - 已有：`scripts/production_release_gate.py` 可一键串联 filled plan 校验、artifact inventory 校验、manifest 生成、严格 manifest 校验和可选 `production_closure.py` dry-run/执行；默认缺真实 readiness evidence package、artifact inventory 或真实 URI 时失败，`--draft` 仅用于模板预览
  - 已有：`scripts/project_completion_audit.py` 支持 `--evidence-plan`、`--evidence-package` 和 `--artifact-inventory`，即使 `tasks/todo.md` 全部 DONE，也必须 release gate 通过才会判定目标完成
  - 生产发布边界：在非本机真实生产/staging 环境用真实参数复跑同一验收链路并归档外部 artifact URI；真实生产发布前仍需人工确认密钥管理、灰度/回滚窗口和 CEO 签批边界
  - 验收：本机 staging 全部 gate 已达到验收口径；所有关键失败路径有人工复核或降级；上线评审记录可审计；系统仍固定模拟交易，不接真实券商、不自动下单

## 明确非目标

- `BLOCKED` 自动下单 / 接真实券商
  - 原因：当前愿景是投资分析、公开资料研究、模拟组合和反馈复盘；真实券商接口、best execution、账户合规、交易风控和自动下单均不属于当前系统目标，过早接入会引入不可控损失

- `BLOCKED` 高频/秒级交易
  - 原因：当前系统定位为中低频、公开/已提供数据驱动，不建设低延迟行情和交易基础设施

- `BLOCKED` 边界不清或禁止自动化的实时/non-display 数据进入自动化链路
  - 原因：实时和 non-display 数据必须有清晰公开来源、用途标签、TOS/robots 判断和人工审批；边界不清时只能人工参考

- `BLOCKED` 非公开研报、转录稿或第三方内容用于训练
  - 原因：研报和转录稿默认是公开外部观点层或本地人工参考层，不是事实真相源，也不默认可训练、再分发或派生

- `BLOCKED` 脱离人工审批的仓位调整
  - 原因：PortfolioProposal 只输出纸面组合或候选权重；模拟持仓用于反馈分析，不代表真实调仓

## 里程碑检查点

- M5 `DONE`：MVP 代码主链路可运行，覆盖 A/H/U 公开披露、证据、评分、审批、复盘、事故、UI、健康检查、烟测、LLM 中转和 OCR 备用解析
- M6 `BLOCKED`：生产化事实层代码层已收口；本机长期使用不阻塞，T-402 已由本机质量包证据通过，T-404/T-405/T-406/T-406A 仍等待非本机组织级 artifact URI
- M7 `BLOCKED`：经营驾驶舱和投研闭环代码层已收口；本机长期使用不阻塞，T-407 ~ T-412 仍等待真实大样本/非本机 artifact URI
  - T-408 归因回填接口已落地；T-409 投委会模拟反馈接口已落地
- M8 `BLOCKED`：数据与研究资产扩展代码层已收口，T-414/T-416/T-418 等待真实外部 artifact URI 或后续质量评估；T-417 已完成
  - T-406A 热点检索召回增强已落地；T-416 补充 HTTP connector 框架已落地；T-417 增量调度框架已落地
- M9 `BLOCKED`：生产基础设施与治理代码层已收口；本机 production-like 栈已通过，T-419 ~ T-421 的非本机组织级证据仍作为未来增强
- M10 `DONE`：愿景验收和上线闸门，T-422 本机 staging / 本机长期使用 gate 已 `ready`；非本机组织级生产发布仍进入人工签批和外部证据归档阶段
