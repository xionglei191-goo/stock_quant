# Feast / Kafka Decision Memo

## Decision

Do not introduce Feast or Kafka in the current productionization phase. The system is still centered on batch-oriented A/H/U public filings, public or locally provided EOD/delayed market data, evidence extraction, research review, and human committee approval. SQLite/PostgreSQL records, object storage, OpenSearch-compatible retrieval, ingestion schedules, audit logs, and alert rules are sufficient for the present workload.

## Why Not Now

| Area | Current State | Decision |
|---|---|---|
| Feature reuse | Most features are document/evidence/research artifacts, not shared low-latency model features | Keep features in records and benchmark outputs |
| Online serving | No approved automated trading path; execution intent remains human-gated | No online feature store yet |
| Event rate | Filings, 13F, schedules, reports, and alerts are low-frequency | Batch jobs and retryable schedules are enough |
| Operational load | Small team, few production services, clear audit requirements | Avoid extra brokers, registries, and replay infrastructure |
| Failure mode | Main risks are rights misuse, extraction errors, stale evidence, and review gaps | Invest in permissions, benchmarks, alerts, and runbooks first |

## Trigger Thresholds

Feast becomes worth a PoC when at least two of these are true:

| Trigger | Threshold |
|---|---:|
| Shared features | 30+ features reused by research, backtest, scoring, and production review |
| Point-in-time incidents | 2+ training/serving or backtest/live leakage incidents in a quarter |
| Serving latency | Approved use case needs sub-second feature reads for human-facing review |
| Feature ownership | 3+ owners publish features that require registry, lineage, and freshness contracts |

Kafka becomes worth a PoC when at least two of these are true:

| Trigger | Threshold |
|---|---:|
| Event concurrency | 5+ independent ingestion/event streams need coordinated replay |
| Event volume | Sustained 10k+ events/day or bursty workflows that exceed scheduler retry ergonomics |
| Consumer fan-out | 4+ downstream consumers need the same ordered event stream |
| Exactly-once pressure | Duplicate processing causes material review, compliance, or cost issues |

## Migration Draft

1. Keep current PostgreSQL records as the source of truth.
2. Add event outbox rows for ingestion, extraction, benchmark, alert, and decision events.
3. Introduce Kafka only as a replayable event transport after outbox coverage is tested.
4. Introduce Feast only for features that have owners, definitions, freshness checks, and offline/online parity tests.
5. Keep `DecisionPack` and `ExecutionIntent` approval gates outside Feast/Kafka so infrastructure cannot bypass governance.

## PoC Cost

| PoC | Team | Duration | Exit Criteria |
|---|---:|---:|---|
| Feast | 1 data engineer + 1 quant | 2 weeks | 10 features, point-in-time join test, freshness check, rollback plan |
| Kafka | 1 platform engineer + 1 data engineer | 2 weeks | Outbox bridge, replay test, duplicate handling, dead-letter runbook |
| Combined | 2 engineers + 1 reviewer | 4 weeks | One benchmark-to-alert pipeline with lineage, replay, and recovery drill |

## Next Review

Review this memo after M7, or earlier if any trigger threshold is met. Until then, keep improving PostgreSQL migrations, benchmark coverage, alerting, and runbook drills.
