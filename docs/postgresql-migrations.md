# PostgreSQL Migration And Rollback

- Status: active
- Owner group: Platform and Quality
- Last updated: 2026-07-19
- Related tasks: T-404, T-424, T-601, T-602
- Scope: PostgreSQL baseline, explicit schema changes, backup, rollback, and market-data storage migration
- Non-goals: broker integration, automatic order execution, or non-local release evidence

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

## Compact Market-Data Storage Migration

T-602 replaces duplicated row-level `payload` and `rights_tag` JSONB with structured columns, `extra_payload`, a payload key mask, and an immutable rights-policy reference. `NUMERIC` columns and the `MarketDataPoint`/HTTP contracts remain unchanged. The public SQL compatibility surface is `ai_quant.market_data`; direct access to physical JSONB columns on `ai_quant.market_data_bars` is no longer supported.

Stop the application, daily timer, and all import scripts. First create a durable backup and verify a full restore:

```bash
python3 scripts/postgres_durable_backup.py \
  --output-dir data/local/backups/postgres \
  --retention-days 7 \
  --timeout-seconds 3600
```

Run each phase with one stable run ID. `copy` commits resumable keyset batches.

```bash
python3 scripts/migrate_market_data_storage_v2.py prepare --run-id <run-id>
python3 scripts/migrate_market_data_storage_v2.py copy --run-id <run-id> --batch-size 500000
python3 scripts/migrate_market_data_storage_v2.py validate --run-id <run-id> --target-size-gb 22
python3 scripts/migrate_market_data_storage_v2.py cutover --run-id <run-id>
```

Before cleanup, run API, daily-update, query-plan, and storage acceptance. Until cleanup, rollback is an atomic table rename:

```bash
python3 scripts/migrate_market_data_storage_v2.py rollback --run-id <run-id>
```

Legacy deletion requires the exact run ID and a restore-verified backup manifest. Cleanup also verifies that the referenced dump still exists and its SHA-256 still matches the manifest:

```bash
python3 scripts/migrate_market_data_storage_v2.py cleanup \
  --run-id <run-id> \
  --confirm-drop-legacy <run-id> \
  --backup-manifest data/local/backups/postgres/<manifest>.json
```

After cleanup, rollback requires restoring the retained dump. Local backup files contain database content, remain under Git-ignored `data/local/`, and are not valid non-local production evidence.

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
