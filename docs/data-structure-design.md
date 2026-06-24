# 公司情报平台数据结构设计

- Status: active
- Owner group: Data and Evidence
- Last updated: 2026-06-24
- Related tasks: T-431, T-432, T-433, T-434, T-435, T-436
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
