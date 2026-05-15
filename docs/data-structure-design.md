# 数据结构设计

## 1. 目标

定义系统的核心实体、对象、关系、事件和日志结构，为研发提供统一的数据模型。

## 2. 设计原则

- 所有结论必须能回链到证据
- 所有实体必须有稳定主键
- 所有操作必须可审计
- 所有版本必须可回放
- 所有三市场对象必须可映射

## 3. 核心主键

| 领域 | 主键 | 说明 |
|---|---|---|
| 公司主体 | `issuer_id` | 内部统一主体 ID |
| 美股主体 | `cik` | SEC 主体标识 |
| 全球实体 | `lei` | 法律实体标识 |
| 证券标识 | `figi` / `isin` / `ticker` | 证券层主键 |
| 文件 | `document_id` | 原始披露唯一标识 |
| 证据 | `evidence_id` | 证据片段唯一标识 |
| 研究结论 | `thesis_id` | Thesis Card 主键 |
| 决策 | `decision_id` | 投委会决策主键 |
| 复盘 | `review_id` | 复盘记录主键 |

## 4. 核心实体模型

### 4.0 SourceDefinition

```json
{
  "source_id": "string",
  "source_type": "regulatory|exchange|company_ir|public_market_data|public_web|local_reference|manual_reference|third_party_connector",
  "risk_level": "green|yellow|red",
  "field_whitelist": ["string"],
  "retention_policy": "string",
  "cache_ttl_days": 0,
  "provenance_ref": "string",
  "usage_scope": "string",
  "collection_method": "string",
  "robots_policy": "string",
  "last_reviewed_at": "datetime|null",
  "review_cadence": "monthly|quarterly|semiannual|annual",
  "review_owner": "string",
  "review_owner_role": "string",
  "source_tos_uri": "string"
}
```

### 4.0.1 SourceReviewRecord

```json
{
  "review_id": "string",
  "source_id": "string",
  "reviewer": "string",
  "reviewed_at": "datetime",
  "review_period": "YYYYQn",
  "status": "approved|conditional|rejected",
  "publicness_status": "confirmed_public_or_local|manual_reference_only|unclear",
  "tos_status": "reviewed|not_applicable|needs_review",
  "robots_status": "reviewed_or_not_applicable|blocked|needs_review",
  "usage_scope_status": "within_boundary|manual_reference_only|blocked",
  "findings": ["string"],
  "next_review_due_at": "datetime|null"
}
```

### 4.1 Issuer

```json
{
  "issuer_id": "string",
  "legal_name": "string",
  "aliases": ["string"],
  "market": ["A", "H", "U"],
  "lei": "string",
  "cik": "string",
  "country": "string",
  "status": "active|inactive",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.1.1 IngestionJob

```json
{
  "job_id": "string",
  "status": "running|completed|partial|failed",
  "total": 0,
  "created": 0,
  "skipped": 0,
  "failed": 0,
  "created_document_ids": ["string"],
  "errors": [
    {
      "index": 0,
      "error": "string"
    }
  ],
  "started_at": "datetime",
  "completed_at": "datetime"
}
```

### 4.1.2 IngestionSchedule

```json
{
  "schedule_id": "string",
  "name": "string",
  "payload": {},
  "cadence": "manual|hourly|daily|weekly",
  "status": "active|retrying|failed|paused",
  "retry_limit": 2,
  "retry_count": 0,
  "last_job_id": "string",
  "last_status": "string",
  "last_error": "string",
  "next_run_at": "datetime",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.2 Security

```json
{
  "security_id": "string",
  "issuer_id": "string",
  "ticker": "string",
  "figi": "string",
  "isin": "string",
  "exchange": "string",
  "currency": "string",
  "market": "A|H|U",
  "status": "active|inactive"
}
```

### 4.2.1 MarketDataPoint

```json
{
  "data_id": "string",
  "security_id": "string",
  "source_id": "string",
  "market": "A|H|U",
  "as_of_date": "YYYY-MM-DD",
  "data_type": "eod|delayed",
  "currency": "string",
  "open": 0.0,
  "high": 0.0,
  "low": 0.0,
  "close": 0.0,
  "adjusted_close": 0.0,
  "volume": 0.0,
  "rights_tag": {
    "license_class": "string",
    "training_allowed": false,
    "redistribution_allowed": false,
    "display_use": "allowed|restricted",
    "non_display_use": "allowed|restricted",
    "derived_data_use": "allowed|restricted"
  },
  "created_at": "datetime"
}
```

### 4.2.2 CorporateAction

```json
{
  "action_id": "string",
  "security_id": "string",
  "source_id": "string",
  "action_type": "split|reverse_split|cash_dividend|stock_dividend|symbol_change",
  "ex_date": "YYYY-MM-DD",
  "ratio": 1.0,
  "cash_amount": 0.0,
  "currency": "string",
  "description": "string",
  "created_at": "datetime"
}
```

### 4.2.3 AdjustedMarketDataView

`AdjustedMarketDataView` 是 `/api/market-data/adjusted` 的计算视图，不覆盖原始行情点。`raw` 保留入库价格；`backward` 将未来拆股、反向拆股和送股作用到更早价格；`forward` 将已发生公司行动作用到更新价格。现金分红作为 ex-date 现金流返回，不进入价格因子；`/api/market-data/returns` 在 `total_return_method=cash_dividend_reinvested` 时才计入收益。

```json
{
  "security_id": "string",
  "source_id": "string",
  "data_type": "eod|delayed",
  "adjustment_mode": "raw|backward|forward",
  "adjustment_policy": {},
  "corporate_actions": [],
  "market_data": [
    {
      "data_id": "string",
      "as_of_date": "YYYY-MM-DD",
      "raw_close": 0.0,
      "adjustment_factor": 1.0,
      "computed_adjusted_close": 0.0,
      "corporate_action_ids": ["string"]
    }
  ]
}
```

### 4.3 Document

```json
{
  "document_id": "string",
  "issuer_id": "string",
  "security_id": "string",
  "document_type": "announcement|annual_report|10-K|10-Q|8-K|20-F|6-K|research|transcript",
  "source_type": "regulatory|exchange|company_ir|public_market_data|local_reference|manual_reference|third_party_connector",
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
  "published_at": "datetime",
  "ingested_at": "datetime",
  "language": "zh|en|mixed",
  "version": "string"
}
```

### 4.4 Evidence

```json
{
  "evidence_id": "string",
  "document_id": "string",
  "section": "string",
  "page_no": "number",
  "bbox": "string",
  "span_text": "string",
  "canonical_text": "string",
  "confidence": 0.0
}
```

### 4.5 ManualReviewItem

```json
{
  "review_id": "string",
  "document_id": "string",
  "issue_type": "empty_or_scanned_document|parser_error|low_locator_confidence",
  "severity": "low|medium|high",
  "status": "open|closed",
  "parser_version": "string",
  "message": "string",
  "suggested_action": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.6 ResearchAnswer

```json
{
  "answer_id": "string",
  "question": "string",
  "issuer_id": "string",
  "evidence_ids": ["string"],
  "source_document_ids": ["string"],
  "english_source_text": "string",
  "chinese_summary": "string",
  "summary_version": "string",
  "prompt_version": "string",
  "model_version": "string",
  "source_publicness": "public|restricted|unknown",
  "human_review_status": "pending|approved|rejected",
  "reviewer": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.7 ThesisCard

```json
{
  "thesis_id": "string",
  "issuer_id": "string",
  "horizon": "short|mid|long",
  "hypothesis": "string",
  "catalyst": ["string"],
  "evidence_ids": ["string"],
  "falsifiers": ["string"],
  "risk_factors": ["string"],
  "confidence": 0.0,
  "owner": "string",
  "status": "draft|review|approved|rejected|expired",
  "valid_from": "date",
  "valid_to": "date"
}
```

### 4.8 ResearchSignal

```json
{
  "signal_id": "string",
  "thesis_id": "string",
  "signal_type": "value|industry|event|momentum|sentiment|crowding",
  "direction": "long|short|neutral",
  "score": 0.0,
  "source_model": "string",
  "model_version": "string",
  "generated_at": "datetime"
}
```

### 4.8.1 InstitutionalHolding

```json
{
  "holding_id": "string",
  "issuer_id": "string",
  "security_id": "string",
  "source_id": "sec_edgar",
  "filer_cik": "string",
  "filer_name": "string",
  "report_period": "YYYY-MM-DD",
  "shares": 0.0,
  "value_usd": 0.0,
  "voting_authority": "string",
  "created_at": "datetime"
}
```

### 4.8.2 DisclosureEvent

```json
{
  "event_id": "string",
  "document_id": "string",
  "issuer_id": "string",
  "security_id": "string",
  "event_type": "current_report|management_change|guidance_update|material_agreement|capital_allocation|annual_foreign_private_issuer_report|filing_update",
  "severity": "low|medium|high",
  "summary": "string",
  "evidence_ids": ["string"],
  "source_id": "string",
  "occurred_at": "datetime",
  "created_at": "datetime"
}
```

### 4.9 ExtractionResult

```json
{
  "extraction_id": "string",
  "evidence_id": "string",
  "document_id": "string",
  "language": "zh|en|mixed",
  "task_type": "term_extraction|evidence_linking|table_reading",
  "terms": [
    {
      "term": "string",
      "canonical": "string",
      "page_no": 1,
      "bbox": "string",
      "confidence": 0.0
    }
  ],
  "numbers": [
    {
      "raw": "string",
      "value": 0.0,
      "unit": "string",
      "page_no": 1,
      "bbox": "string"
    }
  ],
  "periods": [
    {
      "raw": "string",
      "page_no": 1,
      "bbox": "string"
    }
  ],
  "tables": [
    {
      "headers": ["string"],
      "rows": [["string"]],
      "cells": [
        {
          "row": 1,
          "column": "string",
          "value": "string",
          "page_no": 1,
          "bbox": "string"
        }
      ],
      "row_count": 0,
      "column_count": 0,
      "page_no": 1,
      "bbox": "string"
    }
  ],
  "metrics": {},
  "benchmark_id": "string",
  "passed": false,
  "parser_version": "string"
}
```

### 4.10 DecisionPack

```json
{
  "decision_id": "string",
  "signal_ids": ["string"],
  "risk_checks": ["string"],
  "red_team_note": "string",
  "approval_state": "pending|approved|rejected|exception",
  "signatures": [
    {
      "role": "string",
      "user": "string",
      "signed_at": "datetime"
    }
  ]
}
```

### 4.11 ReviewRecord

```json
{
  "review_id": "string",
  "decision_id": "string",
  "realized_outcome": "string",
  "attribution": "string",
  "lesson": "string",
  "next_action": "string",
  "created_at": "datetime"
}
```

### 4.12 ExecutionIntent

```json
{
  "intent_id": "string",
  "decision_id": "string",
  "action": "buy|sell|hold|trim|add",
  "security_id": "string",
  "target_weight": 0.0,
  "rationale": "string",
  "status": "draft|cancelled|submitted",
  "created_by": "string",
  "created_at": "datetime"
}
```

### 4.13 OperatingReport

```json
{
  "report_id": "string",
  "period": "YYYY-MM",
  "metrics": {
    "twr": 0.0,
    "total_return": 0.0,
    "max_drawdown": 0.0,
    "turnover": 0.0,
    "information_ratio": 0.0,
    "attribution": {}
  },
  "red_flags": [
    {
      "type": "string",
      "owner": "string",
      "due": "string"
    }
  ],
  "owner": "string",
  "status": "draft|published",
  "approvals": [
    {
      "role": "CEO|CIO|风险/合规",
      "user": "string",
      "comment": "string",
      "signed_at": "datetime"
    }
  ],
  "created_at": "datetime",
  "published_at": "datetime|null"
}
```

### 4.14 StrategyReplay

```json
{
  "replay_id": "string",
  "decision_id": "string",
  "expected_outcome": "string",
  "actual_outcome": "string",
  "variance_reason": "string",
  "next_action": "string",
  "version": "string",
  "created_at": "datetime"
}
```

### 4.15 PortfolioProposal

```json
{
  "proposal_id": "string",
  "universe": ["security_id"],
  "prior_returns": {"security_id": 0.0},
  "posterior_returns": {"security_id": 0.0},
  "candidate_weights": {"security_id": 0.0},
  "constraints": {
    "paper_only": true,
    "max_weight": 0.0,
    "restricted_securities": ["security_id"],
    "market_budget": {"A": 0.0, "H": 0.0, "U": 0.0},
    "industry_budget": {"industry": 0.0}
  },
  "risk_budget": {},
  "diagnostics": {
    "method": "diagonal_black_litterman",
    "view_diagnostics": [
      {"security_id": "string", "confidence": 0.0, "omega": 0.0}
    ],
    "market_exposure": {},
    "industry_exposure": {},
    "theme_exposure": {},
    "currency_exposure": {},
    "risk_contribution": {},
    "turnover": 0.0,
    "stress_report": [],
    "walk_forward": {}
  },
  "status": "candidate|archived|committee_input",
  "created_by": "string",
  "created_at": "datetime"
}
```

### 4.16 AlertRule

```json
{
  "rule_id": "string",
  "metric": "counts.open_manual_reviews|counts.open_exceptions|pending_prompt_changes",
  "operator": ">|>=|<|<=|==|!=",
  "threshold": 0.0,
  "severity": "low|medium|high|critical",
  "owner": "string",
  "description": "string",
  "enabled": true,
  "playbook_id": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.17 SystemAlert

```json
{
  "alert_id": "string",
  "rule_id": "string",
  "metric": "string",
  "value": 0.0,
  "threshold": 0.0,
  "severity": "low|medium|high|critical",
  "status": "open|resolved",
  "message": "string",
  "owner": "string",
  "playbook_id": "string",
  "incident_report_id": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### 4.18 AlertNotification

```json
{
  "notification_id": "string",
  "alert_id": "string",
  "channel": "webhook|email|slack|internal",
  "target": "string",
  "status": "pending|sent|failed",
  "payload": {},
  "created_at": "datetime"
}
```

## 5. 关系模型

| 关系 | 起点 | 终点 | 说明 |
|---|---|---|---|
| `ISSUES` | Issuer | Security | 主体发行证券 |
| `HAS_MAPPING` | Issuer | EntityMapping | LEI/FIGI/CIK/ISIN/ticker 跨市场映射 |
| `DISCLOSES` | Issuer | Document | 主体发布或关联文件 |
| `DISCLOSURE_FOR` | Document | Security | 文件关联具体证券 |
| `HAS_EVIDENCE` | Document | Evidence | 文件切片形成证据 |
| `NEEDS_REVIEW` | Document | ManualReviewItem | 空文本、扫描件或低置信度解析进入人工复核 |
| `ANSWERS_WITH` | ResearchAnswer | Evidence | 英文原文证据支持研究问答/摘要 |
| `SUPPORTS` | Evidence | ThesisCard | 证据支持研究结论 |
| `HAS_THESIS` | Issuer | ThesisCard | 主体关联研究观点 |
| `GENERATES_SIGNAL` | ThesisCard | ResearchSignal | 研究结论转成信号 |
| `INCLUDED_IN_DECISION` | ResearchSignal | DecisionPack | 信号进入决策包 |
| `APPROVES` | User | DecisionPack | 人工签字 |
| `CREATES_INTENT` | DecisionPack | ExecutionIntent | 已审批决策形成执行意图 |
| `INTENT_ON` | ExecutionIntent | Security | 纸面执行意图关联证券和目标权重 |
| `REVIEW_OF` | ReviewRecord | DecisionPack | 决策形成复盘 |
| `REPLAY_OF` | StrategyReplay | DecisionPack | 决策形成策略回放 |
| `HAS_PORTFOLIO_PROPOSAL` | Issuer | PortfolioProposal | 主体关联纸面组合候选方案 |
| `PROPOSES_WEIGHT` | PortfolioProposal | Security | 纸面组合候选方案给出证券候选权重 |
| `HAS_MARKET_DATA` | Security | MarketDataPoint | 证券关联公开/已提供 EOD/延时行情 |
| `HAS_CORPORATE_ACTION` | Security | CorporateAction | 公司行动用于复权、估值和回测链路 |
| `HAS_13F_HOLDING` | Issuer | InstitutionalHolding | 主体关联 13F 机构持仓 |
| `HOLDS_SECURITY` | InstitutionalHolding | Security | 13F 持仓关联证券 |
| `HAS_DISCLOSURE_EVENT` | Issuer | DisclosureEvent | 主体关联披露事件墙 |
| `EVENT_FROM_DOCUMENT` | DisclosureEvent | Document | 披露事件来自原始文件 |
| `EVENT_ON_SECURITY` | DisclosureEvent | Security | 披露事件关联证券 |
| `EVENT_EVIDENCE` | DisclosureEvent | Evidence | 披露事件引用证据切片 |
| `HAS_CROWDING` | Issuer | CrowdingSnapshot | 主体关联拥挤度快照 |
| `CONTRIBUTES_TO_CROWDING` | InstitutionalHolding | CrowdingSnapshot | 13F 持仓参与生成拥挤度 |
| `SUMMARIZED_BY` | ThesisCard | ResearchCard | 观点形成研究卡 |
| `CHALLENGES` | ChallengerResult | ThesisCard | 反证或挑战者结果挑战结论 |
| `HAS_EXCEPTION` | DecisionPack | ExceptionItem | 决策关联例外事项 |
| `TRIGGERS_ALERT` | AlertRule | SystemAlert | 指标规则触发系统告警 |

## 6. 配置对象

### 6.1 公开来源治理矩阵

```json
{
  "source_id": "string",
  "source_type": "regulatory|exchange|company_ir|public_market_data|local_reference|manual_reference|third_party_connector",
  "license_class": "string",
  "training_allowed": false,
  "redistribution_allowed": false,
  "retention_policy": "string",
  "provenance_ref": "string",
  "source_tos_uri": "string",
  "collection_method": "string",
  "robots_policy": "string",
  "usage_scope": "string",
  "last_reviewed_at": "datetime",
  "display_use": "allowed|restricted",
  "non_display_use": "allowed|restricted",
  "derived_data_use": "allowed|restricted"
}
```

### 6.1.1 来源复核记录

```json
{
  "review_id": "string",
  "source_id": "string",
  "reviewer": "string",
  "reviewed_at": "datetime",
  "review_period": "2026Q2",
  "status": "approved|conditional|rejected",
  "publicness_status": "confirmed_public_or_local|manual_reference_only|unclear",
  "tos_status": "reviewed|not_applicable|needs_review",
  "robots_status": "reviewed_or_not_applicable|blocked|needs_review",
  "usage_scope_status": "within_boundary|manual_reference_only|blocked",
  "findings": ["string"],
  "next_review_due_at": "datetime"
}
```

### 6.2 Benchmark

```json
{
  "benchmark_id": "string",
  "language": "zh|en|mixed",
  "task_type": "term_extraction|evidence_linking|table_reading",
  "sample_size": 0,
  "metrics": {
    "f1": 0.0,
    "em": 0.0,
    "anls": 0.0
  },
  "threshold": {
    "f1": 0.0,
    "em": 0.0,
    "anls": 0.0
  }
}
```

### 6.3 BenchmarkSample

```json
{
  "sample_id": "string",
  "benchmark_id": "string",
  "document_id": "string",
  "language": "zh|en|mixed",
  "expected_terms": ["revenue"],
  "expected_numbers": 0,
  "expected_periods": 0,
  "expected_tables": 0,
  "expected_pages": [1],
  "notes": "string",
  "status": "active|disabled",
  "created_at": "datetime"
}
```

### 6.4 BenchmarkRun

```json
{
  "run_id": "string",
  "benchmark_id": "string",
  "sample_ids": ["sample_id"],
  "passed": false,
  "metrics": {
    "term_f1": 0.0,
    "page_hit_rate": 0.0,
    "table_recall": 0.0,
    "evidence_locator_rate": 0.0,
    "low_confidence_intercept_rate": 0.0,
    "language_metrics": {}
  },
  "threshold": {},
  "failed_samples": [],
  "regression_examples": ["sample_id"],
  "created_at": "datetime"
}
```

## 7. 事件模型

| 事件 | 触发 | 输出 |
|---|---|---|
| `document_ingested` | 文件入湖 | 元数据、版本、权限标签 |
| `evidence_extracted` | 文档切片完成 | evidence_id、页码、片段 |
| `thesis_created` | 研究结论生成 | thesis_id、owner、状态 |
| `signal_scored` | 评分完成 | signal_id、score、方向 |
| `decision_approved` | 人工签字 | approval_state、签字链 |
| `review_completed` | 复盘完成 | 归因、教训、后续动作 |
| `prompt_changed` | prompt 变更 | 版本、审批、回滚信息 |
| `exception_raised` | 触发例外 | 例外原因、处理人、状态 |

## 8. 审计日志字段

| 字段 | 说明 |
|---|---|
| `event_id` | 事件唯一 ID |
| `actor` | 执行动作者 |
| `action` | 动作类型 |
| `resource_type` | 资源类型 |
| `resource_id` | 资源 ID |
| `source` | 数据或系统来源 |
| `version` | 版本号 |
| `model_version` | 模型版本 |
| `prompt_version` | prompt 版本 |
| `approval_state` | 审批状态 |
| `timestamp` | 时间戳 |
| `trace_id` | 链路追踪 ID |

## 9. 版本策略

- 事实数据使用 `valid_time` 和 `system_time`
- 研究结论使用 `status` 和 `valid_to`
- 决策使用审批版本和签字链版本
- 提示词使用单独的版本号与审批记录
