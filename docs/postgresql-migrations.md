# PostgreSQL Migration And Rollback

## Scope

`docs/postgresql-schema.sql` remains the baseline schema for the JSONB record store, audit log, indexes, and convenience views. Migrations are intentionally explicit because production state contains research evidence, approvals, and audit events.

## Apply Baseline

```bash
python3 scripts/postgres_schema_migrate.py "$AI_QUANT_POSTGRES_DSN"
```

Use dry-run before applying in a new environment:

```bash
python3 scripts/postgres_schema_migrate.py "$AI_QUANT_POSTGRES_DSN" --dry-run
```

The script applies the schema and records `0001_baseline_jsonb_records` in `ai_quant.schema_migrations`.

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
