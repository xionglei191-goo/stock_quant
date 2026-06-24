# Handoff: T-430 Daily Data Sync Universe Repair

## Metadata
- Task ID: T-430
- Title: Daily data sync universe repair
- Status: DONE
- Priority: high
- Owner Group: Platform and Quality
- Current Agent: codex-gpt5
- Reviewer: Data and Evidence
- Created At: 2026-06-24
- Updated At: 2026-06-24T10:58:00+08:00

## Objective
Repair the local daily data update path where A-share and US refresh universes were empty, causing incremental imports to run with zero symbols and leaving market data stale.

## Scope
In scope:
- Daily market data refresh scripts
- A-share and US refresh universe reconstruction
- Focused regression tests
- Local PostgreSQL verification

Out of scope:
- Live broker integration
- Non-local production release evidence
- Daily insight quality scoring redesign

## Background
The 2026-06-24 daily update service ran but did not import new market data. Artifacts showed A-share and US incremental import steps were `passed` with zero symbols and zero rows. Direct DB inspection found `ai_quant.market_data_bars` still held large typed market data history, but `ai_quant.records` had no A-share securities and only one US demo security, so DB-universe refreshes had no active universe to batch.

## Problem Statement
The daily runner depended on `records.securities` for resumable A-share and US batches, but that directory could be empty or incomplete even when typed market data already existed. Scope refresh scripts updated existing security rows but did not reconstruct missing rows, so the daily runner could repeatedly succeed with no actual market data updates.

## Expected Deliverables
- A-share scope refresh can seed missing active securities from current baostock common-stock directory.
- US Yahoo scope refresh can seed missing records from existing typed Yahoo bars.
- Resumable US batches do not mark unprocessed tickers stale.
- Local verification proves A-share and US max dates can advance to the latest target date.
- Handoff records exact commands, artifacts, and residual risk.

## Current Findings
1. A-share scope refresh now seeds missing `records.securities` and `records.issuers` rows from current baostock active common-stock symbols.
2. US Yahoo scope refresh now seeds missing refresh records from existing typed `ai_quant.market_data_bars` Yahoo securities.
3. US post-import stale marking now runs only for a full-universe refresh, avoiding false stale labels during resumable batches.
4. Current DB has A-share and Yahoo US typed bars through `2026-06-23`.
5. A small daily update smoke imported 5 A-share symbols and 5 US tickers successfully.
6. The smoke pipeline final status still failed because `daily_market_insight` failed its quality gate; that is separate from market data syncing.

## Proposed Work Plan
1. Reproduce zero-universe behavior from latest daily artifacts. (completed)
2. Inspect daily runner, scope refresh scripts, and live DB payload shape. (completed)
3. Add universe reconstruction paths for A-share and US records. (completed)
4. Prevent US batch smoke runs from stale-marking unprocessed tickers. (completed)
5. Run focused syntax checks and local DB smoke verification. (completed)
6. Record handoff and validation evidence. (completed)

## Validation Plan
```bash
.venv/bin/python -m py_compile scripts/daily_data_update_pipeline.py scripts/scope_ashare_current_baostock_universe.py scripts/scope_us_current_yahoo_universe.py tests/test_system.py
docker compose exec -T ai-quant-org python scripts/scope_ashare_current_baostock_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --output /tmp/ashare-scope-fix.json
docker compose exec -T ai-quant-org python scripts/scope_us_current_yahoo_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --target-date 2026-06-23 --output /tmp/us-scope-fix-2.json
AI_QUANT_DAILY_RUNNER=compose AI_QUANT_DAILY_RUN_ID=fix-smoke-$(date +%H%M%S) AI_QUANT_DAILY_ASHARE_BATCH_SIZE=5 AI_QUANT_DAILY_US_BATCH_SIZE=5 AI_QUANT_DAILY_SKIP_LATEST_ANALYSIS=true AI_QUANT_DAILY_SKIP_LOCAL_PRODUCTION_AUDIT=true AI_QUANT_DAILY_SKIP_RESEARCH_BINDING=true AI_QUANT_DAILY_SKIP_TDX_COVERAGE_AUDIT=true AI_QUANT_DAILY_ALLOW_IMPORT_FAILURE=false bash scripts/run_daily_data_update.sh
docker compose exec -T ai-quant-org python scripts/scope_us_current_yahoo_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --target-date 2026-06-23 --clear-stale --output /tmp/us-scope-restore.json
```

## Risks
- `daily_market_insight` can still fail after data sync is repaired when direct report evidence coverage is below its threshold.
- Full universe refresh is resumable; it should be advanced by scheduled batches rather than one long manual run unless explicitly needed.
- This repair seeds security directory rows from local/public refresh surfaces; richer issuer metadata remains a separate data-quality task.

## Dependencies
- `scripts/run_daily_data_update.sh`
- `scripts/daily_data_update_pipeline.py`
- `scripts/scope_ashare_current_baostock_universe.py`
- `scripts/scope_us_current_yahoo_universe.py`
- `scripts/import_ashare_eod_baostock.py`
- `scripts/import_us_eod_yahoo_chart.py`
- PostgreSQL `ai_quant.records` and `ai_quant.market_data_bars`

## Blockers
- None for market data sync.
- Daily pipeline green status is still blocked by separate `daily_market_insight` quality gate behavior.

## Handoff Checklist
- [x] Code changes implemented
- [x] Validation commands executed
- [x] Test results captured
- [x] Artifact or log references added
- [ ] Reviewer assigned

## Evidence
- Validation commands:
  ```bash
  .venv/bin/python -m py_compile scripts/daily_data_update_pipeline.py scripts/scope_ashare_current_baostock_universe.py scripts/scope_us_current_yahoo_universe.py tests/test_system.py
  docker compose exec -T ai-quant-org python scripts/scope_ashare_current_baostock_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --output /tmp/ashare-scope-fix.json
  docker compose exec -T ai-quant-org python scripts/scope_us_current_yahoo_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --target-date 2026-06-23 --output /tmp/us-scope-fix-2.json
  AI_QUANT_DAILY_RUNNER=compose AI_QUANT_DAILY_RUN_ID=fix-smoke-$(date +%H%M%S) AI_QUANT_DAILY_ASHARE_BATCH_SIZE=5 AI_QUANT_DAILY_US_BATCH_SIZE=5 AI_QUANT_DAILY_SKIP_LATEST_ANALYSIS=true AI_QUANT_DAILY_SKIP_LOCAL_PRODUCTION_AUDIT=true AI_QUANT_DAILY_SKIP_RESEARCH_BINDING=true AI_QUANT_DAILY_SKIP_TDX_COVERAGE_AUDIT=true AI_QUANT_DAILY_ALLOW_IMPORT_FAILURE=false bash scripts/run_daily_data_update.sh
  docker compose exec -T ai-quant-org python scripts/scope_us_current_yahoo_universe.py --dsn postgresql://ai_quant:ai_quant_dev_password@postgres:5432/ai_quant --target-date 2026-06-23 --clear-stale --output /tmp/us-scope-restore.json
  ```
- Result summary:
  - `py_compile`: passed
  - A-share scope refresh: passed, `updated_in_scope=5202`
  - US scope refresh: passed, `updated_in_scope=5418`
  - Small daily update smoke: market data import steps passed; final pipeline status failed only because `daily_market_insight` failed
  - DB verification after smoke: A `public_eod_market_data` max date `2026-06-23`; U `yahoo_chart_us_eod` max date `2026-06-23`
- Artifact references:
  - `artifacts/daily-update-local/runs/fix-smoke-105428/ashare-eod-baostock-incremental-2026-06-24.json`: local-only smoke import, A-share `typed_bar_rows=95`, `max_date=2026-06-23`
  - `artifacts/daily-update-local/runs/fix-smoke-105428/us-eod-yahoo-incremental-2026-06-24.json`: local-only smoke import, US `typed_bar_rows=20`, `max_date=2026-06-23`
  - `artifacts/daily-update-local/runs/fix-smoke-105428/daily-update-2026-06-24.json`: local-only smoke pipeline, market data latest by market `A=2026-06-23`, `U=2026-06-23`

## Next Recommended Action
Let the next scheduled daily timer continue normal batches, or run a larger manual batch if faster catch-up is desired. If a fully green daily pipeline status is required, handle the separate `daily_market_insight` quality gate failure next.
