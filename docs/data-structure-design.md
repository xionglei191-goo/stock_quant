# 公司情报平台数据结构设计

- Status: active
- Owner group: Data and Evidence
- Last updated: 2026-06-25
- Related tasks: T-431, T-432, T-433, T-434, T-435, T-436, T-451, T-453, T-454, T-456, T-457, T-458, T-459, T-460, T-461, T-462, T-463
- Scope: 公司级数据库、事件、关系、研报观点、观察任务、分析结论和模拟反馈核心模型
- Non-goals: 真实交易订单模型、券商账户模型、把研报作为事实真相源

## 1. Purpose

本文档定义公司情报与市场综合分析平台的目标数据结构。模型中心从 `decision_id` / `execution_intent` 调整为公司、证券、事件、关系、观点、观察和模拟反馈。

旧 `DecisionPack`、`ExecutionIntent` 和签字链可以继续作为兼容对象存在，但不再是核心主键或主流程。新增实现应优先围绕 `issuer_id`、`security_id`、`event_id`、`relationship_id`、`viewpoint_id`、`observation_id` 和 `simulation_feedback_id` 设计。

## 2. Design Principles

- 公司级数据库是核心资产。
- 事实、事件、关系、观点和反馈必须分层。
- 所有事实必须可回链来源或证据。
- 研报属于观点层和关注度信号，不属于事实真相源。
- 分析结论必须记录假设、证据、反证、有效期和复盘计划。
- 模拟反馈只用于验证分析有效性，固定 paper-only。
- 所有对象保留版本、更新时间和审计字段。

## 3. Core Keys

| Domain | Primary Key | Purpose |
|---|---|---|
| 公司主体 | `issuer_id` | 公司/发行人统一主体 |
| 证券 | `security_id` | 股票、ADR、港股等证券对象 |
| 人物 | `person_id` | 高管、董事、分析师等人物 |
| 机构 | `institution_id` | 券商、基金、供应商、客户、监管/交易所等机构 |
| 产品 | `product_id` | 公司产品、服务或业务线 |
| 产业链节点 | `industry_node_id` | 上下游环节、产能、材料、渠道等节点 |
| 主题 | `theme_id` | 宏观、产业、热点或策略主题 |
| 文件 | `document_id` | 原始公告、财报、研报、网页或本地文件 |
| 证据 | `evidence_id` | 原文切片或结构化定位 |
| 公司事件 | `event_id` | 事件时间线主键 |
| 关系 | `relationship_id` | 公司/人物/机构/产品/主题关系主键 |
| 研报 | `research_report_id` | 单份研报资产和元数据 |
| 研报观点 | `viewpoint_id` | 单个结构化观点、评级、目标价或假设 |
| 研报预测 | `forecast_id` | 盈利预测、收入预测、目标价路径等 |
| 分析师 | `analyst_id` | 分析师画像和覆盖记录 |
| 观察任务 | `observation_id` | 观察池任务 |
| 分析结论 | `analysis_conclusion_id` | 个人或系统分析结论 |
| 模拟反馈 | `simulation_feedback_id` | 分析结论有效性反馈 |
| 补库运行 | `run_id` | 公司数据库批量补齐运行历史 |

降级主键：

| Legacy Key | New Role |
|---|---|
| `decision_id` | 兼容旧决策包，可映射到 `analysis_conclusion_id` 或复盘记录 |
| `intent_id` / `execution_intent` | 兼容旧纸面执行意图，可映射到 `simulation_feedback_id` 的模拟输入 |

## 4. Common Fields

所有核心对象建议包含：

```json
{
  "created_at": "datetime",
  "updated_at": "datetime",
  "created_by": "string",
  "updated_by": "string",
  "version": "string",
  "source_ids": ["string"],
  "evidence_ids": ["string"],
  "confidence": 0.0,
  "review_status": "unreviewed|pending|reviewed|rejected",
  "metadata": {}
}
```

## 5. Source and Evidence Foundation

### 5.1 SourceDefinition

```json
{
  "source_id": "string",
  "source_type": "regulatory|exchange|company_ir|public_market_data|public_web|local_reference|manual_reference|third_party_connector",
  "risk_level": "green|yellow|red",
  "field_whitelist": ["string"],
  "training_allowed": false,
  "redistribution_allowed": false,
  "automation_allowed": false,
  "retention_policy": "string",
  "cache_ttl_days": 0,
  "provenance_ref": "string",
  "usage_scope": "string",
  "collection_method": "string",
  "robots_policy": "string",
  "source_tos_uri": "string",
  "last_reviewed_at": "datetime|null",
  "review_cadence": "monthly|quarterly|semiannual|annual",
  "review_owner": "string"
}
```

### 5.2 Document

```json
{
  "document_id": "string",
  "issuer_id": "string|null",
  "security_id": "string|null",
  "document_type": "announcement|annual_report|financial_report|10-K|10-Q|8-K|20-F|6-K|research_report|news|policy|web_page|manual_note",
  "title": "string",
  "source_id": "string",
  "source_uri": "string",
  "object_uri": "string",
  "content_sha256": "string",
  "rights_tag": {
    "license_class": "string",
    "training_allowed": false,
    "redistribution_allowed": false,
    "display_use": "allowed|restricted",
    "non_display_use": "allowed|restricted"
  },
  "published_at": "datetime|null",
  "ingested_at": "datetime",
  "language": "zh|en|mixed|unknown",
  "parser_status": "pending|parsed|needs_review|failed",
  "version": "string"
}
```

### 5.3 Evidence

```json
{
  "evidence_id": "string",
  "document_id": "string",
  "source_id": "string",
  "section": "string",
  "page_no": 1,
  "span_text": "string",
  "canonical_text": "string",
  "locator": {
    "scheme": "page_chunk_v1|ocr_bbox_span_v1|html_selector_v1|table_cell_v1",
    "page_no": 1,
    "chunk_index": 1,
    "bbox": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
    "selector": "string",
    "text_sha256": "string"
  },
  "confidence": 0.0,
  "created_at": "datetime"
}
```

## 6. Entity Layer

### 6.1 CompanyProfile

`CompanyProfile` 是公司页的聚合视图，可以物化存储，也可以由 `Issuer`、`Security`、财务、行情、事件和关系记录计算生成。

```json
{
  "issuer_id": "string",
  "legal_name": "string",
  "display_name": "string",
  "aliases": ["string"],
  "markets": ["A", "H", "U"],
  "country": "string",
  "region": "string",
  "industry": "string",
  "sector": "string",
  "business_summary": "string",
  "products": ["product_id"],
  "company_details": {
    "website_url": "string",
    "ir_url": "string",
    "headquarters": "string",
    "employee_count": 0,
    "management": [{"role": "CEO", "name": "string"}],
    "key_customers": ["string"],
    "key_suppliers": ["string"]
  },
  "main_securities": ["security_id"],
  "identifiers": {
    "lei": "string",
    "cik": "string",
    "ticker": "string",
    "figi": "string",
    "isin": "string"
  },
  "latest_market_snapshot": {
    "as_of_date": "YYYY-MM-DD",
    "market_cap": 0.0,
    "currency": "string",
    "close": 0.0,
    "valuation": {}
  },
  "latest_financial_snapshot": {
    "period": "YYYYQn|YYYY",
    "revenue": 0.0,
    "net_income": 0.0,
    "gross_margin": 0.0,
    "cash": 0.0,
    "debt": 0.0
  },
  "coverage_summary": {
    "research_report_count": 0,
    "institution_count": 0,
    "analyst_count": 0,
    "latest_report_at": "datetime|null"
  },
  "event_summary": {
    "latest_event_at": "datetime|null",
    "high_impact_event_count": 0,
    "open_observation_count": 0
  },
  "data_quality": {
    "profile_coverage": 0.0,
    "event_backlink_rate": 0.0,
    "relationship_backlink_rate": 0.0,
    "missing_fields": ["string"]
  },
  "source_ids": ["string"],
  "evidence_ids": ["string"],
  "updated_at": "datetime"
}
```

### 6.1.1 CompanyProfileDeepCoverageAudit

`CompanyProfileDeepCoverageAudit` 是只读审计视图，不新增事实源，也不落库。它用于按公司检查画像字段是否由现有本地/公开/授权记录支撑，并为缺字段生成补齐来源计划。

```json
{
  "schema_id": "company-profile-deep-field-coverage-v1",
  "issuer_count": 1,
  "average_field_coverage_score": 0.0,
  "required_fields": ["legal_name", "business_summary", "authorized_documents"],
  "field_missing_counts": {"business_summary": 1},
  "companies": [
    {
      "issuer_id": "issuer_001",
      "display_name": "Demo Corp",
      "field_coverage_score": 0.0,
      "coverage_level": "sparse|partial|complete",
      "missing_fields": ["business_summary"],
      "fields": {
        "business_summary": {
          "group": "business",
          "present": false,
          "source_records": [],
          "evidence_ids": [],
          "assertion_ids": [],
          "missing_reason": "no_underlying_record|research_report_or_local_reference_is_not_fact_source|no_authorized_fact_source_document",
          "source_policy": "fact_or_governed_record|opinion_slot"
        }
      },
      "counts": {
        "authorized_documents": 0,
        "official_evidence": 0,
        "research_reports": 0,
        "company_events": 0,
        "company_relationships": 0
      },
      "research_tasks": [
        {
          "task_type": "company_profile_field_backfill",
          "field": "business_summary",
          "recommended_sources": ["annual_report", "10-K/20-F", "company_ir", "official_business_overview"]
        }
      ]
    }
  ],
  "source_plan": {
    "source_priority": ["official_disclosure", "company_ir", "company_official", "public_market_data", "local_reference", "manual_reference"],
    "research_report_boundary": "research_reports_can_fill_coverage_opinion_fields_only_not_fact_truth_fields",
    "manual_reference_boundary": "manual_reference_requires_review_before_any_fact_field_can_be_marked_present"
  }
}
```

字段组：

| group | fields |
|---|---|
| `identity` | `legal_name`, `display_name`, `aliases`, `country`, `region`, `sector`, `industry`, `identifiers` |
| `listing` | `security_ids`, `tickers`, `exchange`, `market`, `currency`, `figi`, `isin`, `security_type`, `status`, `listing_date` |
| `business` | `business_summary`, `products`, `employee_count`, `company_details` |
| `contact` | `website_url`, `ir_url`, `headquarters` |
| `governance_people` | `management` |
| `relationship_clues` | `key_customers`, `key_suppliers` |
| `market_snapshot` | `as_of_date`, `close`, `volume`, `amount`, `valuation_metrics` |
| `financial_snapshot` | `period`, `revenue`, `net_income`, `gross_margin`, `cash`, `debt` |
| `source_evidence` | `source_ids`, `authorized_documents`, `field_evidence_ids`, `evidence_backlinks` |
| `coverage_opinion` | `research_report_count`, `structured_report_count`, `report_viewpoint_count`, `analyst_count`, `latest_report_at` |
| `workflow_feedback` | `latest_event_at`, `company_event_count`, `relationship_count`, `open_observation_count`, `analysis_conclusion_count` |
| `quality` | `profile_coverage`, `missing_fields`, `event_backlink_rate`, `relationship_backlink_rate` |

事实字段只接受官方披露、公司 IR、公司官网、交易所/监管披露、公开行情或已治理的结构化本地记录。研报只满足 `coverage_opinion`，不能让 business、financial、identity 等事实字段变为 present。`manual_reference` 与边界不清来源只能进入补齐计划和人工复核。

### 6.1.2 CompanyProfileFieldAssertion

`CompanyProfileFieldAssertion` 是字段级事实/provenance 记录。它解决 `CompanyProfile.source_ids` / `evidence_ids` 只能表达“整张画像用过哪些来源”、不能证明“某个字段由哪个证据支撑”的问题。字段断言只由已入库、已治理的官方披露、公司 IR、公司官网、交易所/监管披露或公开公司披露生成；研报不会生成事实断言。

```json
{
  "assertion_id": "cpfa_xxx",
  "issuer_id": "issuer_001",
  "security_id": "sec_001",
  "field_name": "website_url",
  "value": "https://example.com",
  "normalized_value": "\"https://example.com\"",
  "period": "FY2026",
  "as_of_date": "datetime|null",
  "source_ids": ["src_company_ir"],
  "document_ids": ["doc_company_ir_profile"],
  "evidence_ids": ["evi_company_ir_profile"],
  "confidence": 0.98,
  "source_policy": "fact_or_governed_record",
  "fact_status": "verified",
  "review_status": "auto_generated|needs_review|approved|rejected|superseded",
  "assertion_status": "active|conflict_candidate|superseded|rejected",
  "extraction_method": "rule_company_profile_official_ir_v1",
  "supersedes": ["assertion_id"],
  "conflicts_with": ["assertion_id"],
  "resolved_by": "assertion_id_or_actor",
  "metadata": {},
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

冲突规则：同一 `issuer_id`、`field_name`、`period` 和 `security_id` 下，如果 active 断言已有不同 `normalized_value`，新抽取结果应先成为 `assertion_status=conflict_candidate`、`review_status=needs_review`，并把旧断言放入 `conflicts_with`。冲突候选不会更新 `Issuer` 或 `CompanyProfile` 当前字段，直到复核通过。

复核规则：批准冲突候选后，新断言变为 `active` / `approved` 并应用字段值；被替代断言变为 `superseded`，`resolved_by` 指向新断言。驳回候选时，新断言变为 `rejected`，不修改公司画像。

### 6.1.3 FinancialMetric

`FinancialMetric` 是公司数据库里的财务事实记录。它把 `CompanyProfile.latest_financial_snapshot` 从一个画像快照字段提升为可查询、可审计、可回链的指标表。它只能由已治理事实来源生成或登记；研报预测和观点不能直接写入该表。

```json
{
  "metric_id": "fin_issuer_001_xxx",
  "issuer_id": "issuer_001",
  "security_id": "sec_001",
  "metric_name": "revenue",
  "period": "FY2026",
  "value": 1200000000.0,
  "period_start": "datetime|null",
  "period_end": "datetime|null",
  "fiscal_year": "2026",
  "fiscal_period": "FY",
  "unit": "CNY",
  "currency": "CNY",
  "statement_type": "actual|guidance|restated|preliminary",
  "source_ids": ["src_company_ir"],
  "document_ids": ["doc_company_ir_profile"],
  "evidence_ids": ["evi_company_ir_profile"],
  "confidence": 0.98,
  "source_policy": "fact_or_governed_record",
  "fact_status": "verified|provisional|disputed",
  "review_status": "unreviewed|auto_generated|approved|rejected",
  "metadata": {
    "profile_field_assertion_id": "cpfa_xxx",
    "extraction_method": "rule_company_profile_official_ir_v1"
  },
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

主键规则：默认 `metric_id` 由 `issuer_id`、`security_id`、`metric_name`、`period` 和 `statement_type` 的稳定 hash 生成，保证同一公司同一期间同一类型指标幂等更新。查询主键仍以 `metric_id` 为准，业务过滤优先使用 `issuer_id`、`security_id`、`metric_name` 和 `period`。

来源规则：`source_ids`、`document_ids`、`evidence_ids` 至少需要一个可回链事实来源。`research_report`、`broker_research`、`news`、`manual_reference`、`local_reference`、红色风险来源或包含 research 语义的来源不能写入财务事实表。研报中的盈利预测应进入 `ReportForecast`，不是 `FinancialMetric`。

派生规则：公司画像字段抽取执行时，如果从官方/IR/监管材料中同时抽出 `period` 和 `revenue`、`net_income`、`gross_margin`、`cash`、`debt`，系统会为这些数值同步物化 `FinancialMetric`，再反向更新 `Issuer.fundamentals` 和 `CompanyProfile.latest_financial_snapshot` 的最新视图。

### 6.1.4 CompanyProfileFieldExtractionResult

`CompanyProfileFieldExtractionResult` 是一次本地抽取运行的 API 返回结构，不新增运行表。它从已入库并通过治理边界的 `Document` / `Evidence` 中生成画像字段候选；默认 dry-run，显式 `execute=true` 时才把候选写入 `Issuer` / `CompanyProfile`，并为每个已应用字段写入 `CompanyProfileFieldAssertion`。

```json
{
  "schema_id": "company-profile-field-extraction-v1",
  "status": "dry_run|executed",
  "execute": false,
  "dry_run": true,
  "issuer_count": 1,
  "fields": ["business_summary", "products", "website_url", "ir_url", "management", "revenue", "net_income"],
  "totals": {
    "documents_scanned": 1,
    "evidence_scanned": 1,
    "candidates_found": 4,
    "fields_planned": 4,
    "fields_updated": 0,
    "assertions_recorded": 0,
    "conflict_assertions": 0,
    "profiles_saved": 0,
    "skipped_research_or_reference_documents": 0
  },
  "companies": [
    {
      "issuer_id": "issuer_001",
      "display_name": "Demo Corp",
      "documents_scanned": 1,
      "evidence_scanned": 1,
      "source_document_ids": ["doc_demo_ir"],
      "source_evidence_ids": ["evi_demo_ir_business"],
      "candidates": [
        {
          "field": "business_summary",
          "value": "Demo Corp is engaged in advanced components.",
          "confidence": 0.95,
          "document_id": "doc_demo_ir",
          "source_id": "src_company_ir",
          "evidence_ids": ["evi_demo_ir_business"],
          "section": "business_overview",
          "extraction_method": "rule_company_profile_official_ir_v1",
          "source_policy": "fact_or_governed_record",
          "status": "planned|applied|skipped_existing"
        }
      ],
      "applied": {
        "fields_updated": 0,
        "profile_saved": false,
        "updated_fields": [],
        "assertion_ids": []
      }
    }
  ],
  "source_rules": {
    "allowed": ["official_disclosure", "company_ir", "company_official", "exchange_disclosure", "issuer_disclosure", "public_company_disclosure"],
    "research_reports": "ignored_for_fact_fields_opinion_only",
    "manual_reference": "ignored_until_reviewed_as_governed_fact_source"
  }
}
```

落库映射：

| Extracted field | Persistence target |
|---|---|
| `business_summary` | `Issuer.company_details.business_summary`, `CompanyProfile.business_summary` |
| `products` | `Issuer.company_details.products`, `CompanyProfile.products` |
| `website_url`, `ir_url`, `headquarters`, `employee_count`, `management`, `key_customers`, `key_suppliers` | `Issuer.company_details` 同名字段 |
| `country`, `region`, `sector`, `industry` | `Issuer` 同名字段；`sector` / `industry` 同步到 `CompanyProfile` |
| `period`, `revenue`, `net_income`, `gross_margin`, `cash`, `debt` | `Issuer.fundamentals`, `CompanyProfile.latest_financial_snapshot` |
| `source_id`, `evidence_ids` | `Issuer.data_sources`, `CompanyProfile.source_ids`, `CompanyProfile.evidence_ids` |
| 已应用字段候选 | `CompanyProfileFieldAssertion`，按字段保留 `document_ids`、`evidence_ids`、`confidence` 和 `source_policy` |

抽取结果保持 `review_status` 语义上的“自动候选，需要复核”：当前结构用 `status` 表示 planned/applied，不把规则抽取等同于人工确认。研报、券商研究、本地人工参考和新闻不会写入事实字段。

### 6.1.4 CompanyMaterialInboxManifest / RunSummary

`CompanyMaterialInboxManifest` 是 T-461 本地脚本 `scripts/company_material_inbox_ingest.py` 的 sidecar 输入，不落业务库。它用于把用户已下载或手工保存的公司官网、IR、官方披露材料映射到现有 `SourceDefinition`、`Document`、`Evidence` 和 `CompanyProfileFieldAssertion`。

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

`CompanyMaterialInboxRunSummary` 是脚本输出 artifact，默认路径 `artifacts/company-material-inbox-ingest.json`，分类为 `local-only`。它记录 dry-run 或 execute 的本地补库结果。

```json
{
  "generated_at": "datetime",
  "root_path": "/path/to/company_materials/inbox",
  "manifest_glob": "*.manifest.json",
  "dry_run": true,
  "execute": false,
  "fields": ["business_summary", "website_url", "ir_url"],
  "totals": {
    "manifests_scanned": 1,
    "planned_count": 1,
    "invalid_count": 0,
    "sources_registered": 0,
    "documents_ingested": 0,
    "evidence_extracted": 0,
    "profile_fields_updated": 0,
    "profile_field_assertions_planned_or_written": 0,
    "failed_count": 0
  },
  "items": [
    {
      "manifest_path": "/path/to/demo.manifest.json",
      "file_path": "/path/to/demo-ir-profile.txt",
      "issuer_id": "issuer_001",
      "source_id": "local_demo_ir",
      "document_id": "doc_cmat_issuer_001_xxx",
      "status": "planned|executed|invalid|failed",
      "errors": [],
      "evidence_count": 0,
      "fields_updated": 0,
      "profile_field_assertions": 0
    }
  ],
  "usage_boundary": "local_company_material_inbox_only_official_ir_public_materials_no_external_download_no_training_no_live_trading"
}
```

边界：manifest 只允许官方/IR/监管/交易所/公司官方公开材料进入事实层。研报、券商研究、新闻、人工参考、边界不清材料和 `training_allowed=true` 记录只能停留在观点/人工参考层，不能生成 `CompanyProfileFieldAssertion`。

### 6.2 Security

```json
{
  "security_id": "string",
  "issuer_id": "string",
  "ticker": "string",
  "exchange": "string",
  "market": "A|H|U",
  "currency": "string",
  "figi": "string",
  "isin": "string",
  "security_type": "stock|adr|etf|other",
  "status": "active|inactive|delisted",
  "listed_at": "date|null"
}
```

### 6.3 Person

```json
{
  "person_id": "string",
  "name": "string",
  "aliases": ["string"],
  "person_type": "executive|director|analyst|founder|other",
  "current_institution_id": "string|null",
  "roles": [
    {
      "issuer_id": "string|null",
      "institution_id": "string|null",
      "title": "string",
      "start_date": "date|null",
      "end_date": "date|null"
    }
  ],
  "source_ids": ["string"],
  "evidence_ids": ["string"]
}
```

### 6.4 Institution

```json
{
  "institution_id": "string",
  "name": "string",
  "institution_type": "broker|fund|bank|customer|supplier|regulator|exchange|company|media|other",
  "country": "string",
  "aliases": ["string"],
  "source_ids": ["string"],
  "evidence_ids": ["string"]
}
```

## 7. Fact and Event Layer

### 7.1 MarketDataPoint

```json
{
  "data_id": "string",
  "security_id": "string",
  "source_id": "string",
  "as_of_date": "YYYY-MM-DD",
  "data_type": "eod|delayed",
  "open": 0.0,
  "high": 0.0,
  "low": 0.0,
  "close": 0.0,
  "adjusted_close": 0.0,
  "volume": 0.0,
  "amount": 0.0,
  "currency": "string",
  "created_at": "datetime"
}
```

### 7.2 FinancialMetric

```json
{
  "metric_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "source_id": "string",
  "document_id": "string|null",
  "period": "YYYY|YYYYQn",
  "period_end": "date",
  "metric_name": "revenue|net_income|gross_margin|operating_cash_flow|capex|cash|debt|custom",
  "value": 0.0,
  "unit": "string",
  "currency": "string|null",
  "evidence_ids": ["string"],
  "created_at": "datetime"
}
```

### 7.3 CompanyEvent

```json
{
  "event_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "event_type": "financial_report|announcement|news|policy|order_contract|litigation|management_change|supply_demand|price_move|capital_action|relationship_change|research_coverage_change|other",
  "title": "string",
  "summary": "string",
  "occurred_at": "datetime",
  "detected_at": "datetime",
  "source_ids": ["string"],
  "document_ids": ["string"],
  "evidence_ids": ["string"],
  "impact_tags": ["positive|negative|neutral|uncertain|high_impact|watchlist"],
  "affected_entities": [
    {
      "entity_type": "issuer|security|institution|person|product|industry_node|theme",
      "entity_id": "string",
      "role": "subject|counterparty|related"
    }
  ],
  "confidence": 0.0,
  "fact_status": "confirmed|inferred|speculative|unknown",
  "review_status": "unreviewed|pending|reviewed|rejected"
}
```

### 7.4 CorporateAction

```json
{
  "action_id": "string",
  "event_id": "string|null",
  "security_id": "string",
  "source_id": "string",
  "action_type": "split|reverse_split|cash_dividend|stock_dividend|symbol_change",
  "ex_date": "YYYY-MM-DD",
  "ratio": 1.0,
  "cash_amount": 0.0,
  "currency": "string",
  "description": "string",
  "evidence_ids": ["string"]
}
```

## 8. Relationship Layer

### 8.1 CompanyRelationship

```json
{
  "relationship_id": "string",
  "subject_type": "issuer|security|person|institution|product|industry_node|theme",
  "subject_id": "string",
  "object_type": "issuer|security|person|institution|product|industry_node|theme",
  "object_id": "string",
  "relationship_type": "customer_of|supplier_of|competitor_of|owns_equity|covered_by_institution|covered_by_analyst|upstream_of|downstream_of|related_to_theme|employs|produces|other",
  "direction": "directed|undirected",
  "weight": 0.0,
  "valid_from": "date|null",
  "valid_to": "date|null",
  "source_ids": ["string"],
  "document_ids": ["string"],
  "evidence_ids": ["string"],
  "confidence": 0.0,
  "relationship_status": "active|inactive|historical|unknown",
  "review_status": "unreviewed|pending|reviewed|rejected",
  "metadata": {}
}
```

### 8.1.1 CompanyGraphQualityReconciliation

`CompanyGraphQualityReconciliation` 是本地质量归并 API 的返回结构，不新增持久化表。它识别事件/关系重复组、实体别名归并候选，并把来源质量评分写入 `CompanyEvent.metadata.source_quality` 或 `CompanyRelationship.metadata.source_quality`。

```json
{
  "schema_id": "company-database-quality-reconciliation-v1",
  "status": "dry_run|executed",
  "totals": {
    "event_duplicate_groups": 1,
    "event_duplicates": 1,
    "relationship_duplicate_groups": 1,
    "relationship_duplicates": 1,
    "entity_merge_candidates": 1,
    "events_merged": 0,
    "relationships_merged": 0,
    "source_quality_scored": 4
  },
  "companies": [
    {
      "issuer_id": "issuer_001",
      "event_duplicate_groups": [
        {
          "dedup_key": "issuer|security|event_type|date|document",
          "canonical_id": "ce_001",
          "duplicate_ids": ["ce_002"],
          "reason": "same_issuer_type_date_and_document_or_normalized_summary"
        }
      ],
      "relationship_duplicate_groups": [
        {
          "dedup_key": "issuer|company|issuer_001|company|mega_cloud|customer|directed",
          "canonical_id": "rel_001",
          "duplicate_ids": ["rel_002"],
          "entity_merge_candidate": true,
          "entity_canonical_key": "mega_cloud",
          "entity_names": ["Mega Cloud", "Mega Cloud Inc."]
        }
      ],
      "source_quality": [
        {
          "record_type": "company_event",
          "record_id": "ce_001",
          "source_quality": {
            "score": 0.9,
            "level": "high|medium|low",
            "factors": ["has_evidence_backlink", "official_or_public_company_source"],
            "source_types": ["regulatory"],
            "usage_boundary": "source_quality_is_local_provenance_score_not_investment_rating"
          }
        }
      ]
    }
  ]
}
```

归并写入规则：

| Object | Canonical record | Duplicate record |
|---|---|---|
| `CompanyEvent` | 合并 `source_ids`、`document_ids`、`evidence_ids`、`impact_tags`、`metadata.merged_from`，保留较高 `confidence` | `review_status=merged`，`metadata.merged_into=<canonical_id>` |
| `CompanyRelationship` | 合并 `source_ids`、`document_ids`、`evidence_ids`、`metadata.merged_from`、`metadata.entity_aliases`、`metadata.entity_canonical_key`，保留较高 `confidence` | `review_status=merged`，`relationship_status=inactive`，`metadata.merged_into=<canonical_id>` |

`source_quality.score` 只衡量本地来源/证据/复核质量：官方披露、公司 IR、监管/交易所来源、document/evidence 回链、verified fact 和 approved review 会提高分数；研报、manual/local reference、news、opinion signal、rejected/merged 记录会降低分数。它不是公司质量、投资评级或买卖建议。

### 8.2 EntityMapping

```json
{
  "mapping_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "identifier_type": "ticker|cik|lei|figi|isin|cusip|exchange_code|local_code",
  "identifier_value": "string",
  "market": "A|H|U|global",
  "confidence": 0.0,
  "source_ids": ["string"],
  "valid_from": "date|null",
  "valid_to": "date|null"
}
```

### 8.3 AnalystCoverage

```json
{
  "coverage_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "analyst_id": "string",
  "institution_id": "string",
  "started_at": "date|null",
  "ended_at": "date|null",
  "coverage_status": "active|inactive|unknown",
  "latest_report_id": "research_report_id|null",
  "source_ids": ["string"]
}
```

## 9. Research Report and Viewpoint Layer

### 9.1 ResearchReport

研报资产和元数据。研报是观点层对象，不能直接写入事实层。

```json
{
  "research_report_id": "string",
  "document_id": "string",
  "title": "string",
  "institution_id": "string",
  "institution_name": "string",
  "analyst_ids": ["analyst_id"],
  "analyst_names": ["string"],
  "published_at": "datetime",
  "issuer_id": "string|null",
  "security_id": "string|null",
  "covered_entities": [
    {"entity_type": "issuer|security|industry_node|theme", "entity_id": "string"}
  ],
  "report_type": "initiation|update|earnings_review|industry|strategy|event_comment|rating_change|target_price_change|other",
  "language": "zh|en|mixed|unknown",
  "source_id": "string",
  "source_uri": "string",
  "rights_tag": {
    "local_reference_only": true,
    "training_allowed": false,
    "fact_source_allowed": false,
    "redistribution_allowed": false
  },
  "current_price_at_publication": 0.0,
  "rating": "buy|outperform|hold|neutral|underperform|sell|not_rated|other",
  "target_price": 0.0,
  "target_price_currency": "string",
  "target_price_horizon": "3m|6m|12m|long_term|unknown",
  "summary": "string",
  "parser_status": "pending|parsed|needs_review|failed",
  "viewpoint_ids": ["viewpoint_id"],
  "forecast_ids": ["forecast_id"],
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

Required report fields:

- 机构
- 分析师
- 发布时间
- 标的
- 报告类型
- 评级
- 目标价
- 当前价
- 核心假设
- 盈利预测
- 估值方法
- 催化剂
- 风险
- 后续兑现状态

### 9.2 ReportViewpoint

```json
{
  "viewpoint_id": "string",
  "research_report_id": "string",
  "issuer_id": "string|null",
  "security_id": "string|null",
  "viewpoint_type": "rating|target_price|core_assumption|valuation|catalyst|risk|industry_view|event_view|other",
  "stance": "positive|negative|neutral|mixed|uncertain",
  "statement": "string",
  "rating": "buy|outperform|hold|neutral|underperform|sell|not_rated|other|null",
  "target_price": 0.0,
  "current_price": 0.0,
  "upside_downside_pct": 0.0,
  "valuation_method": "pe|pb|ps|dcf|ev_ebitda|sum_of_parts|asset_value|other|null",
  "core_assumptions": ["string"],
  "catalysts": ["string"],
  "risks": ["string"],
  "evidence_ids": ["string"],
  "source_quote_locator": "string",
  "view_status": "active|superseded|invalidated|expired|unknown",
  "realization_status": "pending|partially_realized|realized|missed|not_measurable",
  "realization_checked_at": "datetime|null",
  "notes": "string"
}
```

### 9.3 ReportForecast

```json
{
  "forecast_id": "string",
  "research_report_id": "string",
  "viewpoint_id": "string|null",
  "issuer_id": "string",
  "security_id": "string|null",
  "forecast_type": "revenue|net_income|eps|gross_margin|target_price|market_share|volume|price|other",
  "period": "YYYY|YYYYQn|date_range",
  "forecast_value": 0.0,
  "unit": "string",
  "currency": "string|null",
  "base_value": 0.0,
  "actual_value": 0.0,
  "actual_source_id": "string|null",
  "actual_evidence_ids": ["string"],
  "error_abs": 0.0,
  "error_pct": 0.0,
  "realization_status": "pending|realized|missed|not_available|not_measurable",
  "checked_at": "datetime|null"
}
```

### 9.4 AnalystProfile

```json
{
  "analyst_id": "string",
  "person_id": "string|null",
  "name": "string",
  "institution_id": "string",
  "coverage_markets": ["A", "H", "U"],
  "coverage_industries": ["string"],
  "covered_issuer_ids": ["issuer_id"],
  "first_seen_at": "datetime",
  "last_seen_at": "datetime",
  "report_count": 0,
  "active": true,
  "source_ids": ["string"]
}
```

### 9.5 AnalystReliabilityScore

```json
{
  "score_id": "string",
  "analyst_id": "string",
  "institution_id": "string",
  "issuer_id": "string|null",
  "period": "YYYYQn|YYYY",
  "sample_count": 0,
  "target_price_hit_rate": 0.0,
  "rating_direction_accuracy": 0.0,
  "earnings_forecast_mape": 0.0,
  "forecast_review_coverage": 0.0,
  "timeliness_score": 0.0,
  "revision_quality_score": 0.0,
  "overall_score": 0.0,
  "methodology_version": "string",
  "input_forecast_ids": ["forecast_id"],
  "notes": "string",
  "computed_at": "datetime"
}
```

## 10. Observation, Conclusion and Feedback Layer

### 10.1 ObservationItem

```json
{
  "observation_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "title": "string",
  "question": "string",
  "observation_type": "company_profile_gap|event_followup|relationship_watch|report_viewpoint_watch|price_volume_watch|financial_watch|policy_watch|custom",
  "trigger_conditions": [
    {
      "condition_type": "date|price|event|report|metric|manual",
      "description": "string",
      "threshold": {}
    }
  ],
  "related_event_ids": ["event_id"],
  "related_relationship_ids": ["relationship_id"],
  "related_viewpoint_ids": ["viewpoint_id"],
  "evidence_gap": ["string"],
  "priority": "low|medium|high|critical",
  "status": "open|in_progress|waiting|closed|cancelled",
  "owner": "string",
  "due_at": "datetime|null",
  "created_at": "datetime",
  "closed_at": "datetime|null"
}
```

### 10.2 AnalysisConclusion

```json
{
  "analysis_conclusion_id": "string",
  "issuer_id": "string",
  "security_id": "string|null",
  "title": "string",
  "conclusion": "string",
  "conclusion_type": "watch|positive|negative|neutral|avoid|needs_more_evidence|custom",
  "horizon": "short|medium|long|unknown",
  "hypothesis": "string",
  "facts": ["string"],
  "inferences": ["string"],
  "forecasts": ["string"],
  "subjective_judgments": ["string"],
  "supporting_evidence_ids": ["evidence_id"],
  "counter_evidence_ids": ["evidence_id"],
  "related_event_ids": ["event_id"],
  "related_relationship_ids": ["relationship_id"],
  "related_viewpoint_ids": ["viewpoint_id"],
  "related_observation_ids": ["observation_id"],
  "confidence": 0.0,
  "valid_from": "date",
  "valid_to": "date|null",
  "review_plan": {
    "review_at": "datetime|null",
    "review_questions": ["string"],
    "success_criteria": ["string"],
    "failure_criteria": ["string"]
  },
  "status": "draft|active|superseded|expired|reviewed|rejected",
  "created_by": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 10.3 SimulationFeedback

```json
{
  "simulation_feedback_id": "string",
  "analysis_conclusion_id": "string",
  "observation_id": "string|null",
  "issuer_id": "string",
  "security_id": "string|null",
  "feedback_type": "paper_trade|watch_only|portfolio_shadow|event_validation|forecast_validation",
  "paper_only": true,
  "live_execution_allowed": false,
  "broker_connected": false,
  "simulated_action": "buy|sell|hold|trim|add|watch|none",
  "simulated_size": {
    "quantity": 0.0,
    "weight": 0.0,
    "notional": 0.0,
    "currency": "string"
  },
  "start_at": "datetime",
  "end_at": "datetime|null",
  "entry_price": 0.0,
  "exit_price": 0.0,
  "benchmark_security_id": "string|null",
  "performance": {
    "absolute_return": 0.0,
    "benchmark_return": 0.0,
    "excess_return": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0
  },
  "validation": {
    "hypothesis_status": "pending|supported|partially_supported|rejected|inconclusive",
    "event_ids": ["event_id"],
    "forecast_ids": ["forecast_id"],
    "notes": "string"
  },
  "review_result": {
    "reviewed_at": "datetime|null",
    "lesson": "string",
    "next_action": "continue_watch|revise_conclusion|close|create_observation|other"
  },
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 10.4 CompanyDatabaseBuildRun

`CompanyDatabaseBuildRun` 记录公司数据库批量补齐的本地运行历史，用于审计、复盘、覆盖率趋势、失败重试和断点续跑。它不是交易指令，也不是生产发布证据。

```json
{
  "run_id": "string",
  "actor": "string",
  "status": "dry_run|executed|failed|partial",
  "execute": false,
  "dry_run": true,
  "retry_of": "source_run_id",
  "resume_of": "source_run_id",
  "resume_mode": "all|remaining",
  "attempt": 1,
  "idempotency_key": "string",
  "target_issuer_ids": ["issuer_id"],
  "target_symbols": ["string"],
  "completed_issuer_ids": ["issuer_id"],
  "skipped_issuer_ids": ["issuer_id"],
  "batch_count": 0,
  "batch_size": 0,
  "totals": {
    "profiles_saved": 0,
    "profiles_planned": 0,
    "research_reports_matched": 0,
    "research_reports_bound": 0,
    "events_created": 0,
    "events_planned": 0,
    "relationships_created": 0,
    "relationships_planned": 0,
    "observations_created": 0,
    "observations_planned": 0,
    "conclusions_created": 0,
    "conclusions_planned": 0,
    "feedback_created": 0,
    "feedback_planned": 0
  },
  "coverage_before": {},
  "coverage_after": {},
  "options": {},
  "batches": [],
  "error": "",
  "usage_boundary": "company_database_build_run_is_local_research_operations_history_no_live_trading",
  "started_at": "datetime",
  "completed_at": "datetime",
  "created_at": "datetime"
}
```

Retry/resume 语义：

- `retry_of` 指向被重放的源 run。
- `resume_of` 指向断点续跑的源 run；`resume_mode=remaining` 时只处理未完成公司。
- `completed_issuer_ids` 记录源 run 或本次 run 已完成的公司主体。
- `skipped_issuer_ids` 记录本次续跑因已完成而跳过的公司主体。
- `status=partial` 表示至少有一个批次完成后发生失败，后续可从本地 run history 续跑剩余公司。
- run history 默认返回瘦身摘要；只有显式 `include_batches=true` 才返回完整 `batches`。

覆盖率趋势报告由 `CompanyDatabaseBuildRun.coverage_before` / `coverage_after` 派生，不新增事实源。核心行字段包括：

```json
{
  "run_id": "string",
  "status": "dry_run|executed|failed|partial",
  "target_issuer_ids": ["issuer_id"],
  "coverage_before_score": 0.0,
  "coverage_after_score": 0.0,
  "coverage_delta": 0.0,
  "missing_before_count": 0,
  "missing_after_count": 0,
  "missing_delta": 0,
  "missing_delta_by_section": {
    "company_events": -1,
    "research_reports": 0
  },
  "improved_sections": ["company_events"],
  "worsened_sections": [],
  "usage_boundary": "company_database_build_run_is_local_research_operations_history_no_live_trading"
}
```

### 10.5 CompanyIntelligenceCycleRun

`CompanyIntelligenceCycleRun` 记录公司情报闭环刷新历史，用于复盘某家公司在本地执行研报兑现、workflow 重建和 paper-only 反馈更新后，完整度和覆盖率是否改善。它不是交易指令，也不是生产发布证据。

```json
{
  "run_id": "string",
  "actor": "string",
  "status": "dry_run|executed|not_found|failed",
  "execute": false,
  "dry_run": true,
  "symbol": "string",
  "issuer_ids": ["issuer_id"],
  "summary": {
    "completeness_before": 0.0,
    "completeness_after": 0.0,
    "completeness_delta": 0.0,
    "coverage_before": 0.0,
    "coverage_after": 0.0,
    "coverage_delta": 0.0,
    "realization_items": 0,
    "workflow_items": 0,
    "feedback_items": 0
  },
  "before": {},
  "after": {},
  "step_status": {},
  "error": "",
  "usage_boundary": "company_intelligence_cycle_runs_are_local_history_paper_feedback_no_live_trading",
  "started_at": "datetime",
  "completed_at": "datetime",
  "created_at": "datetime"
}
```

记录规则：

- `POST /api/company-intelligence/{symbol}/cycle/run` 在 `execute=true` 时默认记录。
- dry-run 只有显式 `record_run=true` 才记录。
- `GET|POST /api/company-intelligence/cycle/runs` 可按 `run_id`、`symbol`、`issuer_id` 和 `status` 查询。

本地 artifact 输出只用于个人研究复盘，固定 `classification=local-only`，不得当作非本机生产发布证据。

## 11. Relationship Model

| Relationship | From | To | Purpose |
|---|---|---|---|
| `ISSUES` | CompanyProfile | Security | 公司发行证券 |
| `HAS_DOCUMENT` | CompanyProfile | Document | 公司相关文件 |
| `HAS_EVIDENCE` | Document | Evidence | 文件切片 |
| `HAS_EVENT` | CompanyProfile | CompanyEvent | 公司事件时间线 |
| `EVENT_EVIDENCE` | CompanyEvent | Evidence | 事件证据 |
| `HAS_RELATIONSHIP` | CompanyProfile | CompanyRelationship | 公司关系 |
| `RELATIONSHIP_EVIDENCE` | CompanyRelationship | Evidence | 关系证据 |
| `COVERED_BY_REPORT` | CompanyProfile | ResearchReport | 研报覆盖 |
| `REPORT_HAS_VIEWPOINT` | ResearchReport | ReportViewpoint | 研报观点 |
| `VIEWPOINT_HAS_FORECAST` | ReportViewpoint | ReportForecast | 预测 |
| `ANALYST_AUTHORED_REPORT` | AnalystProfile | ResearchReport | 分析师报告 |
| `ANALYST_COVERS` | AnalystProfile | CompanyProfile | 分析师覆盖 |
| `SCORES_ANALYST` | AnalystReliabilityScore | AnalystProfile | 分析师可靠性 |
| `OBSERVES_COMPANY` | ObservationItem | CompanyProfile | 观察池 |
| `OBSERVES_EVENT` | ObservationItem | CompanyEvent | 观察事件 |
| `OBSERVES_VIEWPOINT` | ObservationItem | ReportViewpoint | 观察观点 |
| `CONCLUSION_ON_COMPANY` | AnalysisConclusion | CompanyProfile | 分析结论 |
| `CONCLUSION_USES_EVIDENCE` | AnalysisConclusion | Evidence | 结论证据 |
| `CONCLUSION_REFERENCES_VIEWPOINT` | AnalysisConclusion | ReportViewpoint | 引用观点 |
| `FEEDBACK_FOR_CONCLUSION` | SimulationFeedback | AnalysisConclusion | 反馈验证 |
| `FEEDBACK_REFERENCES_EVENT` | SimulationFeedback | CompanyEvent | 事件验证 |

## 12. Event Model

| Event | Trigger | Output |
|---|---|---|
| `document_ingested` | 文件入湖 | `document_id`, source, rights, object URI |
| `evidence_extracted` | 文档解析完成 | `evidence_id`, locator, confidence |
| `company_profile_updated` | 主体或画像字段更新 | `issuer_id`, changed fields |
| `company_event_created` | 新事实或事件识别 | `event_id`, evidence links |
| `relationship_created` | 新关系识别或人工确认 | `relationship_id`, evidence links |
| `research_report_registered` | 研报资产登记 | `research_report_id`, rights boundary |
| `report_viewpoint_extracted` | 观点结构化 | `viewpoint_id`, report fields |
| `forecast_reviewed` | 预测兑现复盘 | `forecast_id`, error metrics |
| `analyst_score_computed` | 分析师可靠性计算 | `score_id`, methodology version |
| `observation_created` | 新观察任务 | `observation_id`, trigger conditions |
| `analysis_conclusion_created` | 分析结论创建 | `analysis_conclusion_id`, evidence links |
| `simulation_feedback_recorded` | 模拟反馈记录 | `simulation_feedback_id`, paper-only flags |
| `review_completed` | 结论或反馈复盘 | lesson, next action |

## 13. Audit Log Fields

| Field | Description |
|---|---|
| `audit_id` | 审计事件 ID |
| `actor` | 操作者或系统任务 |
| `action` | 动作类型 |
| `resource_type` | 对象类型 |
| `resource_id` | 对象 ID |
| `source` | 数据或调用来源 |
| `trace_id` | 链路 ID |
| `model_version` | 模型版本 |
| `prompt_version` | prompt 版本 |
| `parser_version` | 解析器版本 |
| `rights_boundary` | 数据边界快照 |
| `paper_only` | 是否仅模拟 |
| `live_execution_allowed` | 是否允许真实执行，默认 false |
| `timestamp` | 时间戳 |

## 14. Versioning Strategy

- 事实和事件使用 `valid_time` 与 `system_time`。
- 公司画像记录字段更新时间和来源覆盖。
- 关系记录 `valid_from` / `valid_to` 和状态。
- 观点记录 `view_status`、`realization_status` 和后续复盘时间。
- 分析结论记录 `valid_from` / `valid_to`、状态和复盘计划。
- 模拟反馈记录起止时间、行情来源和复盘状态。
- prompt、parser、model 和 scoring methodology 使用独立版本。

## 15. Data Boundary Rules

- 研报是观点层和关注度信号，不是事实真相源。
- 事实字段必须来自公告、财报、监管披露、公司 IR、公开行情或其他可信来源。
- 研报中的事实描述若要进入事实层，必须创建独立 evidence 回链到可信事实来源。
- 边界不清数据只能 metadata-only 或 manual reference。
- 受限内容不得进入训练、再分发或自动事实抽取层。
- 模拟反馈不得产生真实券商订单或自动交易动作。

## 16. Migration Notes

| Existing Object | Target Meaning |
|---|---|
| `Issuer` | `CompanyProfile` 基础主体 |
| `DisclosureEvent` | `CompanyEvent` 的披露事件子类 |
| `ThesisCard` | 可迁移为 `AnalysisConclusion` |
| `ResearchAnswer` | 可作为观点/摘要材料并回链 evidence |
| `DecisionPack` | 兼容旧决策对象，不作为新核心对象 |
| `ExecutionIntent` | 兼容旧纸面模拟输入，不作为真实执行对象 |
| `PortfolioTransaction` | 模拟 ledger，可被 `SimulationFeedback` 引用 |
| `OperatingReport` | 复盘摘要，可从反馈和结论聚合 |
