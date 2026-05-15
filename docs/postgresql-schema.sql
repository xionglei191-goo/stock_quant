-- AI Native Quant Org PostgreSQL baseline schema.
-- Mirrors the current SQLiteStore record model while adding JSONB indexes
-- for production filtering, audit ordering, and idempotent upserts.

CREATE SCHEMA IF NOT EXISTS ai_quant;

CREATE TABLE IF NOT EXISTS ai_quant.schema_migrations (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_quant.records (
    collection TEXT NOT NULL,
    item_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    position BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection, item_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_quant_records_collection
    ON ai_quant.records (collection);

CREATE INDEX IF NOT EXISTS idx_ai_quant_records_position
    ON ai_quant.records (collection, position, item_id)
    WHERE position IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ai_quant_records_payload_gin
    ON ai_quant.records USING GIN (payload);

CREATE INDEX IF NOT EXISTS idx_ai_quant_astock_connectors_status
    ON ai_quant.records ((payload->>'provider'), (payload->>'status'), (payload->>'last_check_status'))
    WHERE collection = 'astock_connectors';

CREATE INDEX IF NOT EXISTS idx_ai_quant_documents_issuer
    ON ai_quant.records ((payload->>'issuer_id'))
    WHERE collection = 'documents';

CREATE INDEX IF NOT EXISTS idx_ai_quant_documents_source
    ON ai_quant.records ((payload->>'source_id'), (payload->>'document_type'))
    WHERE collection = 'documents';

CREATE INDEX IF NOT EXISTS idx_ai_quant_market_data_security_date
    ON ai_quant.records ((payload->>'security_id'), (payload->>'as_of_date'))
    WHERE collection = 'market_data';

CREATE INDEX IF NOT EXISTS idx_ai_quant_market_data_source
    ON ai_quant.records ((payload->>'source_id'), (payload->>'data_type'))
    WHERE collection = 'market_data';

CREATE INDEX IF NOT EXISTS idx_ai_quant_corporate_actions_security
    ON ai_quant.records ((payload->>'security_id'), (payload->>'action_type'), (payload->>'ex_date'))
    WHERE collection = 'corporate_actions';

CREATE INDEX IF NOT EXISTS idx_ai_quant_13f_issuer_period
    ON ai_quant.records ((payload->>'issuer_id'), (payload->>'report_period'))
    WHERE collection = 'institutional_holdings';

CREATE INDEX IF NOT EXISTS idx_ai_quant_13f_security
    ON ai_quant.records ((payload->>'security_id'), (payload->>'filer_cik'))
    WHERE collection = 'institutional_holdings';

CREATE INDEX IF NOT EXISTS idx_ai_quant_disclosure_events_issuer
    ON ai_quant.records ((payload->>'issuer_id'), (payload->>'event_type'), (payload->>'severity'))
    WHERE collection = 'disclosure_events';

CREATE INDEX IF NOT EXISTS idx_ai_quant_evidence_document
    ON ai_quant.records ((payload->>'document_id'))
    WHERE collection = 'evidence';

CREATE INDEX IF NOT EXISTS idx_ai_quant_manual_reviews_status
    ON ai_quant.records ((payload->>'status'), (payload->>'severity'), (payload->>'document_id'))
    WHERE collection = 'manual_reviews';

CREATE INDEX IF NOT EXISTS idx_ai_quant_benchmark_samples_benchmark
    ON ai_quant.records ((payload->>'benchmark_id'), (payload->>'language'), (payload->>'status'))
    WHERE collection = 'benchmark_samples';

CREATE INDEX IF NOT EXISTS idx_ai_quant_benchmark_runs_benchmark
    ON ai_quant.records ((payload->>'benchmark_id'), (payload->>'passed'))
    WHERE collection = 'benchmark_runs';

CREATE INDEX IF NOT EXISTS idx_ai_quant_research_answers_issuer
    ON ai_quant.records ((payload->>'issuer_id'), (payload->>'source_publicness'), (payload->>'human_review_status'))
    WHERE collection = 'research_answers';

CREATE INDEX IF NOT EXISTS idx_ai_quant_research_reports_source
    ON ai_quant.records ((payload->>'source_id'), (payload->>'broker'), (payload->>'status'))
    WHERE collection = 'research_reports';

CREATE INDEX IF NOT EXISTS idx_ai_quant_llm_task_templates_status
    ON ai_quant.records ((payload->>'task_type'), (payload->>'status'), (payload->>'prompt_version'))
    WHERE collection = 'llm_task_templates';

CREATE INDEX IF NOT EXISTS idx_ai_quant_llm_task_runs_status
    ON ai_quant.records ((payload->>'task_type'), (payload->>'status'), (payload->>'fallback_used'))
    WHERE collection = 'llm_task_runs';

CREATE INDEX IF NOT EXISTS idx_ai_quant_workflow_runs_status
    ON ai_quant.records ((payload->>'dag_id'), (payload->>'status'), (payload->>'idempotency_key'))
    WHERE collection = 'workflow_runs';

CREATE INDEX IF NOT EXISTS idx_ai_quant_lineage_events_dataset
    ON ai_quant.records ((payload->>'dataset'), (payload->>'job_run_id'))
    WHERE collection = 'lineage_events';

CREATE INDEX IF NOT EXISTS idx_ai_quant_model_versions_status
    ON ai_quant.records ((payload->>'model_name'), (payload->>'status'), (payload->>'version'))
    WHERE collection = 'model_versions';

CREATE INDEX IF NOT EXISTS idx_ai_quant_cache_retention_runs_status
    ON ai_quant.records ((payload->>'status'), (payload->>'as_of'))
    WHERE collection = 'cache_retention_runs';

CREATE INDEX IF NOT EXISTS idx_ai_quant_theses_issuer
    ON ai_quant.records ((payload->>'issuer_id'), (payload->>'status'))
    WHERE collection = 'theses';

CREATE INDEX IF NOT EXISTS idx_ai_quant_decisions_state
    ON ai_quant.records ((payload->>'approval_state'))
    WHERE collection = 'decisions';

CREATE INDEX IF NOT EXISTS idx_ai_quant_simulated_executions_intent
    ON ai_quant.records ((payload->>'intent_id'), (payload->>'status'), (payload->>'account_id'))
    WHERE collection = 'simulated_executions';

CREATE INDEX IF NOT EXISTS idx_ai_quant_portfolio_transactions_filter
    ON ai_quant.records ((payload->>'account_id'), (payload->>'strategy_id'), (payload->>'security_id'), (payload->>'trade_date'))
    WHERE collection = 'portfolio_transactions';

CREATE INDEX IF NOT EXISTS idx_ai_quant_operating_reports_status
    ON ai_quant.records ((payload->>'status'), (payload->>'period'))
    WHERE collection = 'operating_reports';

CREATE INDEX IF NOT EXISTS idx_ai_quant_strategy_replays_filter
    ON ai_quant.records ((payload->>'decision_id'), (payload->>'version'), (payload->>'actual_outcome'))
    WHERE collection = 'strategy_replays';

CREATE INDEX IF NOT EXISTS idx_ai_quant_portfolio_proposals_status
    ON ai_quant.records ((payload->>'status'), (payload->>'created_by'))
    WHERE collection = 'portfolio_proposals';

CREATE INDEX IF NOT EXISTS idx_ai_quant_schedules_status
    ON ai_quant.records ((payload->>'status'), (payload->>'next_run_at'))
    WHERE collection = 'ingestion_schedules';

CREATE INDEX IF NOT EXISTS idx_ai_quant_alert_rules_enabled
    ON ai_quant.records ((payload->>'enabled'), (payload->>'severity'), (payload->>'metric'))
    WHERE collection = 'alert_rules';

CREATE INDEX IF NOT EXISTS idx_ai_quant_system_alerts_status
    ON ai_quant.records ((payload->>'status'), (payload->>'severity'), (payload->>'owner'))
    WHERE collection = 'system_alerts';

CREATE INDEX IF NOT EXISTS idx_ai_quant_alert_notifications_status
    ON ai_quant.records ((payload->>'alert_id'), (payload->>'channel'), (payload->>'status'))
    WHERE collection = 'alert_notifications';

CREATE TABLE IF NOT EXISTS ai_quant.audit_log (
    event_id TEXT PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    source TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '',
    model_version TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    approval_state TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_quant_audit_resource
    ON ai_quant.audit_log (resource_type, resource_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ai_quant_audit_actor
    ON ai_quant.audit_log (actor, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_ai_quant_audit_trace
    ON ai_quant.audit_log (trace_id)
    WHERE trace_id <> '';

CREATE OR REPLACE FUNCTION ai_quant.touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ai_quant_records_touch_updated_at ON ai_quant.records;

CREATE TRIGGER trg_ai_quant_records_touch_updated_at
BEFORE UPDATE ON ai_quant.records
FOR EACH ROW
EXECUTE FUNCTION ai_quant.touch_updated_at();

CREATE OR REPLACE VIEW ai_quant.documents AS
SELECT
    item_id AS document_id,
    payload->>'issuer_id' AS issuer_id,
    payload->>'security_id' AS security_id,
    payload->>'source_id' AS source_id,
    payload->>'document_type' AS document_type,
    payload->>'source_uri' AS source_uri,
    payload->>'object_uri' AS object_uri,
    payload->>'content_sha256' AS content_sha256,
    (payload->>'published_at')::timestamptz AS published_at,
    payload
FROM ai_quant.records
WHERE collection = 'documents';

CREATE OR REPLACE VIEW ai_quant.evidence AS
SELECT
    item_id AS evidence_id,
    payload->>'document_id' AS document_id,
    (payload->>'page_no')::integer AS page_no,
    payload->>'bbox' AS bbox,
    payload->>'canonical_text' AS canonical_text,
    payload
FROM ai_quant.records
WHERE collection = 'evidence';

CREATE OR REPLACE VIEW ai_quant.manual_reviews AS
SELECT
    item_id AS review_id,
    payload->>'document_id' AS document_id,
    payload->>'issue_type' AS issue_type,
    payload->>'severity' AS severity,
    payload->>'status' AS status,
    payload->>'parser_version' AS parser_version,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'manual_reviews';

CREATE OR REPLACE VIEW ai_quant.benchmark_samples AS
SELECT
    item_id AS sample_id,
    payload->>'benchmark_id' AS benchmark_id,
    payload->>'document_id' AS document_id,
    payload->>'language' AS language,
    payload->>'status' AS status,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'benchmark_samples';

CREATE OR REPLACE VIEW ai_quant.benchmark_runs AS
SELECT
    item_id AS run_id,
    payload->>'benchmark_id' AS benchmark_id,
    (payload->>'passed')::boolean AS passed,
    payload->'metrics' AS metrics,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'benchmark_runs';

CREATE OR REPLACE VIEW ai_quant.research_answers AS
SELECT
    item_id AS answer_id,
    payload->>'issuer_id' AS issuer_id,
    payload->>'question' AS question,
    payload->>'summary_version' AS summary_version,
    payload->>'prompt_version' AS prompt_version,
    payload->>'model_version' AS model_version,
    payload->>'source_publicness' AS source_publicness,
    payload->>'human_review_status' AS human_review_status,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'research_answers';

CREATE OR REPLACE VIEW ai_quant.astock_connectors AS
SELECT
    item_id AS connector_id,
    payload->>'provider' AS provider,
    payload->>'endpoint_type' AS endpoint_type,
    payload->>'source_id' AS source_id,
    payload->>'status' AS status,
    payload->>'last_check_status' AS last_check_status,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'astock_connectors';

CREATE OR REPLACE VIEW ai_quant.llm_task_runs AS
SELECT
    item_id AS run_id,
    payload->>'template_id' AS template_id,
    payload->>'task_type' AS task_type,
    payload->>'status' AS status,
    payload->>'model' AS model,
    payload->>'prompt_version' AS prompt_version,
    payload->>'fallback_used' AS fallback_used,
    (payload->>'latency_ms')::numeric AS latency_ms,
    (payload->>'estimated_cost')::numeric AS estimated_cost,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'llm_task_runs';

CREATE OR REPLACE VIEW ai_quant.workflow_runs AS
SELECT
    item_id AS run_id,
    payload->>'dag_id' AS dag_id,
    payload->>'status' AS status,
    payload->>'idempotency_key' AS idempotency_key,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'workflow_runs';

CREATE OR REPLACE VIEW ai_quant.lineage_events AS
SELECT
    item_id AS lineage_id,
    payload->>'job_run_id' AS job_run_id,
    payload->>'dataset' AS dataset,
    payload->>'code_version' AS code_version,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'lineage_events';

CREATE OR REPLACE VIEW ai_quant.model_versions AS
SELECT
    item_id AS model_version_id,
    payload->>'model_name' AS model_name,
    payload->>'version' AS version,
    payload->>'model_type' AS model_type,
    payload->>'status' AS status,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'model_versions';

CREATE OR REPLACE VIEW ai_quant.market_data AS
SELECT
    item_id AS data_id,
    payload->>'security_id' AS security_id,
    payload->>'source_id' AS source_id,
    payload->>'market' AS market,
    (payload->>'as_of_date')::date AS as_of_date,
    payload->>'data_type' AS data_type,
    (payload->>'close')::numeric AS close,
    (payload->>'volume')::numeric AS volume,
    payload
FROM ai_quant.records
WHERE collection = 'market_data';

CREATE OR REPLACE VIEW ai_quant.corporate_actions AS
SELECT
    item_id AS action_id,
    payload->>'security_id' AS security_id,
    payload->>'source_id' AS source_id,
    payload->>'action_type' AS action_type,
    (payload->>'ex_date')::date AS ex_date,
    (payload->>'ratio')::numeric AS ratio,
    (payload->>'cash_amount')::numeric AS cash_amount,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'corporate_actions';

CREATE OR REPLACE VIEW ai_quant.institutional_holdings AS
SELECT
    item_id AS holding_id,
    payload->>'issuer_id' AS issuer_id,
    payload->>'security_id' AS security_id,
    payload->>'source_id' AS source_id,
    payload->>'filer_cik' AS filer_cik,
    payload->>'filer_name' AS filer_name,
    (payload->>'report_period')::date AS report_period,
    (payload->>'shares')::numeric AS shares,
    (payload->>'value_usd')::numeric AS value_usd,
    payload
FROM ai_quant.records
WHERE collection = 'institutional_holdings';

CREATE OR REPLACE VIEW ai_quant.disclosure_events AS
SELECT
    item_id AS event_id,
    payload->>'document_id' AS document_id,
    payload->>'issuer_id' AS issuer_id,
    payload->>'security_id' AS security_id,
    payload->>'event_type' AS event_type,
    payload->>'severity' AS severity,
    (payload->>'occurred_at')::timestamptz AS occurred_at,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'disclosure_events';

CREATE OR REPLACE VIEW ai_quant.decisions AS
SELECT
    item_id AS decision_id,
    payload->>'approval_state' AS approval_state,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'decisions';

CREATE OR REPLACE VIEW ai_quant.operating_reports AS
SELECT
    item_id AS report_id,
    payload->>'period' AS period,
    payload->>'status' AS status,
    (payload->>'published_at')::timestamptz AS published_at,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'operating_reports';

CREATE OR REPLACE VIEW ai_quant.strategy_replays AS
SELECT
    item_id AS replay_id,
    payload->>'decision_id' AS decision_id,
    payload->>'version' AS version,
    payload->>'actual_outcome' AS actual_outcome,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'strategy_replays';

CREATE OR REPLACE VIEW ai_quant.portfolio_proposals AS
SELECT
    item_id AS proposal_id,
    payload->>'status' AS status,
    payload->>'created_by' AS created_by,
    payload->'candidate_weights' AS candidate_weights,
    payload->'diagnostics' AS diagnostics,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'portfolio_proposals';

CREATE OR REPLACE VIEW ai_quant.simulated_executions AS
SELECT
    item_id AS execution_id,
    payload->>'intent_id' AS intent_id,
    payload->>'transaction_id' AS transaction_id,
    payload->>'mode' AS mode,
    payload->>'status' AS status,
    (payload->>'fill_price')::numeric AS fill_price,
    (payload->>'quantity')::numeric AS quantity,
    (payload->>'notional')::numeric AS notional,
    (payload->>'live_execution_allowed')::boolean AS live_execution_allowed,
    payload->>'account_id' AS account_id,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'simulated_executions';

CREATE OR REPLACE VIEW ai_quant.portfolio_transactions AS
SELECT
    item_id AS transaction_id,
    payload->>'security_id' AS security_id,
    (payload->>'trade_date')::date AS trade_date,
    payload->>'side' AS side,
    (payload->>'quantity')::numeric AS quantity,
    (payload->>'price')::numeric AS price,
    (payload->>'fees')::numeric AS fees,
    payload->>'source_id' AS source_id,
    payload->>'account_id' AS account_id,
    payload->>'strategy_id' AS strategy_id,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'portfolio_transactions';

CREATE OR REPLACE VIEW ai_quant.alert_rules AS
SELECT
    item_id AS rule_id,
    payload->>'metric' AS metric,
    payload->>'operator' AS operator,
    (payload->>'threshold')::numeric AS threshold,
    payload->>'severity' AS severity,
    payload->>'owner' AS owner,
    (payload->>'enabled')::boolean AS enabled,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'alert_rules';

CREATE OR REPLACE VIEW ai_quant.system_alerts AS
SELECT
    item_id AS alert_id,
    payload->>'rule_id' AS rule_id,
    payload->>'metric' AS metric,
    (payload->>'value')::numeric AS value,
    payload->>'severity' AS severity,
    payload->>'status' AS status,
    payload->>'owner' AS owner,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'system_alerts';

CREATE OR REPLACE VIEW ai_quant.alert_notifications AS
SELECT
    item_id AS notification_id,
    payload->>'alert_id' AS alert_id,
    payload->>'channel' AS channel,
    payload->>'target' AS target,
    payload->>'status' AS status,
    payload,
    updated_at
FROM ai_quant.records
WHERE collection = 'alert_notifications';
