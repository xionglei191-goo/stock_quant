from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping


MARKET_DATA_STORAGE_MIGRATION = "0002_market_data_storage_v2"

CANONICAL_PAYLOAD_KEYS = (
    "data_id",
    "security_id",
    "source_id",
    "market",
    "as_of_date",
    "data_type",
    "currency",
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "amount",
    "rights_tag",
)


def market_data_payload_sql(bar_alias: str = "b", policy_alias: str = "p") -> str:
    expressions = []
    column_by_key = {
        "data_id": "data_id",
        "security_id": "security_id",
        "source_id": "source_id",
        "market": "market",
        "as_of_date": "as_of_date",
        "data_type": "data_type",
        "currency": "currency",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "adjusted_close": "adjusted_close",
        "volume": "volume",
        "amount": "amount",
    }
    for bit, key in enumerate(CANONICAL_PAYLOAD_KEYS):
        value_sql = f"{policy_alias}.rights_tag" if key == "rights_tag" else f"{bar_alias}.{column_by_key[key]}"
        expressions.append(
            f"CASE WHEN ({bar_alias}.payload_key_mask & {1 << bit}) <> 0 "
            f"THEN jsonb_build_object('{key}', {value_sql}) ELSE '{{}}'::jsonb END"
        )
    return " || ".join([*expressions, f"{bar_alias}.extra_payload"])


def market_data_view_sql(table_name: str = "market_data_bars") -> str:
    payload_sql = market_data_payload_sql()
    return f"""
        CREATE OR REPLACE VIEW ai_quant.market_data AS
        SELECT
            b.data_id,
            b.security_id,
            b.source_id,
            b.market,
            b.as_of_date,
            b.data_type,
            b.open,
            b.high,
            b.low,
            b.close,
            b.adjusted_close,
            b.volume,
            b.amount,
            p.rights_tag,
            ({payload_sql}) AS payload,
            b.updated_at
        FROM ai_quant.{table_name} AS b
        JOIN ai_quant.market_data_rights_policies AS p
          ON p.policy_id = b.rights_policy_id
    """


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def rights_policy_hash(rights_tag: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(rights_tag).encode("utf-8")).hexdigest()


def split_market_data_payload(payload: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
    key_mask = 0
    extra_payload = dict(payload)
    for bit, key in enumerate(CANONICAL_PAYLOAD_KEYS):
        if key in payload:
            key_mask |= 1 << bit
            extra_payload.pop(key, None)
    return key_mask, extra_payload


def market_data_bar_params(payload: Mapping[str, Any], *, amount: float | None = None) -> tuple[Any, ...]:
    rights_tag = dict(payload.get("rights_tag", {}) or {})
    row_amount = float(payload.get("amount", 0.0) if amount is None else amount)
    normalized_payload = dict(payload)
    if amount is not None:
        normalized_payload["amount"] = row_amount
    key_mask, extra_payload = split_market_data_payload(normalized_payload)
    close = payload["close"]
    return (
        rights_policy_hash(rights_tag),
        canonical_json(rights_tag),
        payload["security_id"],
        payload["source_id"],
        payload.get("data_type", "eod"),
        payload["as_of_date"],
        payload["market"],
        payload.get("currency", ""),
        payload.get("open", 0.0),
        payload.get("high", 0.0),
        payload.get("low", 0.0),
        close,
        payload.get("adjusted_close", close),
        payload.get("volume", 0.0),
        row_amount,
        payload["data_id"],
        key_mask,
        json.dumps(extra_payload, ensure_ascii=False, sort_keys=True),
        payload.get("created_at") or datetime.now(timezone.utc),
    )


UPSERT_MARKET_DATA_BAR_SQL = """
    WITH inserted_policy AS (
        INSERT INTO ai_quant.market_data_rights_policies (policy_hash, rights_tag)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (policy_hash) DO NOTHING
        RETURNING policy_id
    ), resolved_policy AS (
        SELECT policy_id FROM inserted_policy
        UNION ALL
        SELECT policy_id
        FROM ai_quant.market_data_rights_policies
        WHERE policy_hash = %s
          AND rights_tag = %s::jsonb
        LIMIT 1
    )
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
        rights_policy_id,
        payload_key_mask,
        extra_payload,
        created_at
    )
    SELECT
        %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        policy_id, %s, %s::jsonb, %s
    FROM resolved_policy
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
        rights_policy_id = EXCLUDED.rights_policy_id,
        payload_key_mask = EXCLUDED.payload_key_mask,
        extra_payload = EXCLUDED.extra_payload,
        updated_at = now()
"""


def upsert_market_data_bar(cursor: Any, payload: Mapping[str, Any], *, amount: float | None = None) -> None:
    params = market_data_bar_params(payload, amount=amount)
    policy_hash, rights_json, *bar_params = params
    cursor.execute(
        UPSERT_MARKET_DATA_BAR_SQL,
        (policy_hash, rights_json, policy_hash, rights_json, *bar_params),
    )
    if getattr(cursor, "rowcount", 1) == 0:
        raise RuntimeError("market-data rights policy hash collision or unresolved policy")
