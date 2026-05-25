from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


def backfill_market_data_bars(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required: python3 -m pip install 'psycopg[binary]>=3.1'") from exc

    started_at = datetime.now(timezone.utc).isoformat()
    filter_where = ["collection = 'market_data'"]
    filter_params: list[Any] = []
    if args.market:
        filter_where.append("payload->>'market' = %s")
        filter_params.append(args.market)
    if args.source_id:
        filter_where.append("payload->>'source_id' = %s")
        filter_params.append(args.source_id)
    if args.data_type:
        filter_where.append("payload->>'data_type' = %s")
        filter_params.append(args.data_type)
    if args.start_date:
        filter_where.append("payload->>'as_of_date' >= %s")
        filter_params.append(args.start_date)
    if args.end_date:
        filter_where.append("payload->>'as_of_date' <= %s")
        filter_params.append(args.end_date)

    summary: dict[str, Any] = {
        "started_at": started_at,
        "status": "passed",
        "market": args.market,
        "source_id": args.source_id,
        "data_type": args.data_type,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "scanned_records": 0,
        "upserted_bars": 0,
        "skipped_records": 0,
        "failed_records": [],
        "min_date": "",
        "max_date": "",
    }
    batch_limit = args.batch_size
    if args.limit:
        batch_limit = min(batch_limit, args.limit)
    last_item_id = ""
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            while True:
                where = [*filter_where, "item_id > %s"]
                params = [*filter_params, last_item_id, batch_limit]
                if args.limit:
                    remaining = args.limit - summary["scanned_records"]
                    if remaining <= 0:
                        break
                    params[-1] = min(batch_limit, remaining)
                sql = f"""
                    WITH batch AS (
                        SELECT item_id, payload
                        FROM ai_quant.records
                        WHERE {' AND '.join(where)}
                        ORDER BY item_id
                        LIMIT %s
                    ),
                    typed AS (
                        SELECT
                            item_id,
                            payload,
                            payload->>'security_id' AS security_id,
                            payload->>'source_id' AS source_id,
                            COALESCE(payload->>'data_type', 'eod') AS data_type,
                            (payload->>'as_of_date')::date AS as_of_date,
                            payload->>'market' AS market,
                            COALESCE(payload->>'currency', '') AS currency,
                            COALESCE((payload->>'open')::numeric, 0) AS open,
                            COALESCE((payload->>'high')::numeric, 0) AS high,
                            COALESCE((payload->>'low')::numeric, 0) AS low,
                            (payload->>'close')::numeric AS close,
                            COALESCE((payload->>'adjusted_close')::numeric, (payload->>'close')::numeric) AS adjusted_close,
                            COALESCE((payload->>'volume')::numeric, 0) AS volume,
                            COALESCE((payload->>'amount')::numeric, 0) AS amount,
                            COALESCE(payload->>'data_id', item_id) AS data_id,
                            COALESCE(payload->'rights_tag', '{{}}'::jsonb) AS rights_tag,
                            COALESCE((payload->>'created_at')::timestamptz, %s::timestamptz) AS created_at
                        FROM batch
                    ),
                    inserted AS (
                        INSERT INTO ai_quant.market_data_bars (
                            security_id,
                            source_id,
                            data_type,
                            as_of_date,
                            market,
                            currency,
                            open,
                            high,
                            low,
                            close,
                            adjusted_close,
                            volume,
                            amount,
                            data_id,
                            rights_tag,
                            payload,
                            created_at
                        )
                        SELECT
                            security_id,
                            source_id,
                            data_type,
                            as_of_date,
                            market,
                            currency,
                            open,
                            high,
                            low,
                            close,
                            adjusted_close,
                            volume,
                            amount,
                            data_id,
                            rights_tag,
                            payload,
                            created_at
                        FROM typed
                        WHERE close > 0
                          AND security_id <> ''
                          AND source_id <> ''
                          AND market <> ''
                        ON CONFLICT (security_id, source_id, data_type, as_of_date)
                        DO UPDATE SET
                            market = EXCLUDED.market,
                            currency = EXCLUDED.currency,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            adjusted_close = EXCLUDED.adjusted_close,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            data_id = EXCLUDED.data_id,
                            rights_tag = EXCLUDED.rights_tag,
                            payload = EXCLUDED.payload,
                            updated_at = now()
                        RETURNING data_id
                    )
                    SELECT
                        (SELECT count(*) FROM batch) AS scanned,
                        (SELECT count(*) FROM inserted) AS upserted,
                        (SELECT max(item_id) FROM batch) AS last_item_id,
                        (SELECT min(payload->>'as_of_date') FROM batch WHERE (payload->>'close')::numeric > 0) AS min_date,
                        (SELECT max(payload->>'as_of_date') FROM batch WHERE (payload->>'close')::numeric > 0) AS max_date
                """
                cursor.execute(sql, (*params, started_at))
                scanned, upserted, batch_last_item_id, batch_min_date, batch_max_date = cursor.fetchone()
                connection.commit()
                scanned = int(scanned or 0)
                upserted = int(upserted or 0)
                if scanned == 0:
                    break
                summary["scanned_records"] += scanned
                summary["upserted_bars"] += upserted
                summary["skipped_records"] += max(0, scanned - upserted)
                if batch_min_date:
                    summary["min_date"] = str(batch_min_date) if not summary["min_date"] else min(summary["min_date"], str(batch_min_date))
                if batch_max_date:
                    summary["max_date"] = str(batch_max_date) if not summary["max_date"] else max(summary["max_date"], str(batch_max_date))
                last_item_id = str(batch_last_item_id or last_item_id)
                if args.progress_every and summary["scanned_records"] % args.progress_every < scanned:
                    print(
                        json.dumps(
                            {
                                "scanned_records": summary["scanned_records"],
                                "upserted_bars": summary["upserted_bars"],
                                "last_item_id": last_item_id,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
    summary["failed_record_count"] = len(summary["failed_records"])
    summary["failed_records"] = summary["failed_records"][:100]
    if summary["failed_record_count"]:
        summary["status"] = "partial"
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill typed PostgreSQL market_data_bars from JSONB market_data records.")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"))
    parser.add_argument("--market", choices=["", "A", "H", "U"], default="")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--data-type", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100000)
    parser.add_argument("--max-failures", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=1000000)
    parser.add_argument("--output", default="artifacts/market-data-bars-backfill.json")
    args = parser.parse_args()
    result = backfill_market_data_bars(args)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
