# PostgreSQL Migration And Rollback

## Scope

`docs/postgresql-schema.sql` remains the baseline schema for the JSONB record store, audit log, typed market-data bars, indexes, and convenience views. Migrations are intentionally explicit because production state contains research evidence, approvals, market data, and audit events.

## Apply Baseline

```bash
python3 scripts/postgres_schema_migrate.py "$AI_QUANT_POSTGRES_DSN"
```

Use dry-run before applying in a new environment:

```bash
python3 scripts/postgres_schema_migrate.py "$AI_QUANT_POSTGRES_DSN" --dry-run
```

The script applies the schema and records `0001_baseline_jsonb_records` in `ai_quant.schema_migrations`.

`PostgreSQLStore` checks this migration record during app startup. When the baseline is already recorded, the runtime skips DDL and only loads state; schema/index changes should be applied explicitly with `scripts/postgres_schema_migrate.py`. This avoids service startup blocking behind long analytical reads that hold locks on `ai_quant.records`.

Production K-lines now use `ai_quant.market_data_bars` as the only runtime source of truth. New TDX, baostock, Yahoo, and API market-data writes go directly to the typed table instead of creating one `ai_quant.records` row per bar. `ai_quant.records` is still used for issuer/security/source metadata and audit-adjacent objects, but it must not contain runtime `collection='market_data'` rows after migration cleanup. The `ai_quant.market_data` view exposes typed bars only.

## Backfill Typed K-Line Table

After applying the schema to an existing PostgreSQL store, backfill typed bars from existing JSONB records:

```bash
python3 scripts/backfill_market_data_bars_from_records.py \
  --dsn "$AI_QUANT_POSTGRES_DSN" \
  --output artifacts/market-data-bars-backfill.json
```

Rerunning the backfill is idempotent while legacy JSONB rows still exist. After a successful backfill, delete legacy `ai_quant.records` rows where `collection='market_data'`; keep per-run evidence in artifacts and `audit_log`, while bar-level data lands only in `ai_quant.market_data_bars`.

## Rollback Policy

The rollback command removes only the migration record. It does not drop tables, views, indexes, records, evidence, approvals, or audit logs.

```bash
python3 scripts/postgres_schema_migrate.py "$AI_QUANT_POSTGRES_DSN" --rollback-last
```

Destructive rollback must be a separate, reviewed SQL file with:

- backup artifact path
- affected objects
- expected row counts
- restore command
- approval owner
- post-rollback smoke test

## Release Checklist

1. Run `python3 -m unittest discover -s tests`.
2. Run `python3 scripts/ui_static_check.py`.
3. Run migration dry-run.
4. Apply schema to staging.
5. Run `scripts/smoke_test.py` against staging.
6. Back up production.
7. Apply schema to production.
8. Verify `ai_quant.schema_migrations` and health checks.
