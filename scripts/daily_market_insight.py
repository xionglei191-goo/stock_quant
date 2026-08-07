from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.service_modules.market_data import (  # noqa: E402
    market_eod_key,
    market_freshness_annotation,
)

DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"
DEFAULT_SOURCE_A = "public_eod_market_data"
DEFAULT_SOURCE_U = "yahoo_chart_us_eod"
DEFAULT_OUTPUT_JSON = "artifacts/daily-insight/latest.json"
DEFAULT_OUTPUT_MD = "artifacts/daily-insight/latest.md"

RESEARCH_VALUE_TERMS = [
    "ai",
    "app store",
    "azure",
    "bottom line",
    "buy rating",
    "capex",
    "cash flow",
    "cloud",
    "consensus",
    "datacenter",
    "data center",
    "deliveries",
    "demand",
    "eps",
    "estimate",
    "fsd",
    "gross margin",
    "growth",
    "guidance",
    "investor",
    "margin",
    "rating",
    "revenue",
    "robotaxi",
    "stock",
    "tariff",
    "valuation",
    "yoy",
    "qoq",
    "收入",
    "营收",
    "增长",
    "毛利",
    "利润",
    "估值",
    "目标价",
    "风险",
    "需求",
]

LOW_VALUE_EVIDENCE_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+\*{2,}@\*{2,}|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\+?\d[\d() -]{7,}\d"),
    re.compile(r"\b(CFA|LLC|Ltd\.?|Goldman Sachs|Morgan Stanley|Deutsche Bank|JPMorgan)\b", re.IGNORECASE),
    re.compile(r"\b(disclosures?|analyst certification|see disclosures?)\b", re.IGNORECASE),
]


def _connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required. Run inside the app container or install psycopg[binary].") from exc
    return psycopg.connect(dsn)


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _pct(value: Any) -> str:
    return f"{_safe_float(value) * 100:.2f}%"


def _short_text(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    meaningful = sum(1 for char in text if char.isalpha() or "\u4e00" <= char <= "\u9fff")
    return meaningful / max(1, len(text))


def _private_use_ratio(text: str) -> float:
    if not text:
        return 0.0
    private_chars = sum(1 for char in text if "\ue000" <= char <= "\uf8ff")
    return private_chars / max(1, len(text))


def _evidence_quality(text: Any) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = normalized.lower()
    value_hits = [term for term in RESEARCH_VALUE_TERMS if term.lower() in lowered]
    low_value_hits = [pattern.pattern for pattern in LOW_VALUE_EVIDENCE_PATTERNS if pattern.search(normalized)]
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", normalized))
    private_use_ratio = _private_use_ratio(normalized)
    looks_like_ocr_noise = bool(
        normalized
        and not has_cjk
        and len(normalized) >= 24
        and _alpha_ratio(normalized) > 0.85
        and not re.search(r"\s", normalized)
    )
    too_short = len(normalized) < 40
    content_score = len(value_hits) * 2
    if len(normalized) >= 120:
        content_score += 1
    if re.search(r"\d+(\.\d+)?\s*%|yoy|qoq|revenue|margin|growth|deliveries|估值|收入|增长", lowered):
        content_score += 1
    if low_value_hits:
        content_score -= min(2, len(low_value_hits))
    if looks_like_ocr_noise:
        content_score -= 4
    if private_use_ratio > 0.08:
        content_score -= 4
    if too_short:
        content_score -= 2
    is_useful = content_score >= 1 and not looks_like_ocr_noise and private_use_ratio <= 0.08 and not (too_short and not value_hits)
    return {
        "is_useful": is_useful,
        "score": content_score,
        "value_terms": value_hits[:8],
        "low_value_reason_count": len(low_value_hits),
        "looks_like_ocr_noise": looks_like_ocr_noise,
        "private_use_ratio": round(private_use_ratio, 4),
    }


def _date_prefix(value: Any) -> str:
    match = re.search(r"(20\d{2})[-_/年](\d{1,2})[-_/月](\d{1,2})", str(value or ""))
    if not match:
        return ""
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _date_part(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def _fetch_one(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return tuple(row or ())


def _fetch_all(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    cursor.execute(sql, params)
    return [tuple(row) for row in cursor.fetchall()]


def _market_eod_target(market: str, *, data_type: str, source_a: str, source_u: str) -> dict[str, str]:
    """按 `market_eod_key` 解析单个市场的 `(market, source_id, data_type)` 三元键。

    `--source-a` / `--source-u` 作为显式覆盖传入，保留既有覆盖通路；未登记市场
    （如 H）不传覆盖，由 `market_eod_key` 回落到 A 市场公开 EOD 源，与既有
    “非 U 市场一律走 public_eod_market_data”的行为一致（需求 5.6）。
    """

    normalized = str(market or "").strip().upper()
    override = {"A": source_a, "U": source_u}.get(normalized, "")
    return market_eod_key(normalized, data_type=data_type, source_id=override)


def _market_eod_targets(*, data_type: str, source_a: str, source_u: str) -> list[dict[str, str]]:
    """`market_freshness` 与公司活动条目共用的市场取数键列表（需求 5.6）。"""

    return [_market_eod_target(market, data_type=data_type, source_a=source_a, source_u=source_u) for market in ("A", "U")]


def _latest_date(cursor: Any, *, market: str, source_id: str, data_type: str) -> str:
    row = _fetch_one(
        cursor,
        """
        SELECT as_of_date::text
        FROM ai_quant.market_data_bars
        WHERE market = %s
          AND source_id = %s
          AND data_type = %s
        ORDER BY as_of_date DESC
        LIMIT 1
        """,
        (market, source_id, data_type),
    )
    return str(row[0] or "") if row else ""


def _fetch_market_movers(
    cursor: Any,
    *,
    market: str,
    source_id: str,
    data_type: str,
    as_of_date: str,
    current_row_limit: int,
    history_rows: int,
) -> list[dict[str, Any]]:
    if not as_of_date:
        return []
    rows = _fetch_all(
        cursor,
        """
        SELECT
            c.security_id,
            c.market,
            c.source_id,
            c.as_of_date::text,
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.amount,
            COALESCE(sec.payload->>'ticker', c.security_id) AS ticker,
            COALESCE(sec.payload->>'issuer_id', '') AS issuer_id,
            COALESCE(iss.payload->>'legal_name', sec.payload->>'ticker', c.security_id) AS issuer_name,
            p.as_of_date::text AS previous_date,
            p.close AS previous_close,
            p.volume AS previous_volume,
            p.amount AS previous_amount,
            h.avg_volume,
            h.avg_amount,
            h.history_count
        FROM (
            SELECT *
            FROM ai_quant.market_data_bars
            WHERE market = %s
              AND source_id = %s
              AND data_type = %s
              AND as_of_date = %s::date
            ORDER BY data_id
            LIMIT %s
        ) AS c
        LEFT JOIN ai_quant.records AS sec
          ON sec.collection = 'securities'
         AND sec.item_id = c.security_id
        LEFT JOIN ai_quant.records AS iss
          ON iss.collection = 'issuers'
         AND iss.item_id = COALESCE(sec.payload->>'issuer_id', '')
        LEFT JOIN LATERAL (
            SELECT as_of_date, close, volume, amount
            FROM ai_quant.market_data_bars AS b
            WHERE b.security_id = c.security_id
              AND b.source_id = c.source_id
              AND b.data_type = c.data_type
              AND b.as_of_date < c.as_of_date
            ORDER BY b.as_of_date DESC
            LIMIT 1
        ) AS p ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                AVG(NULLIF(volume, 0)) AS avg_volume,
                AVG(NULLIF(amount, 0)) AS avg_amount,
                COUNT(*) AS history_count
            FROM (
                SELECT volume, amount
                FROM ai_quant.market_data_bars AS b
                WHERE b.security_id = c.security_id
                  AND b.source_id = c.source_id
                  AND b.data_type = c.data_type
                  AND b.as_of_date < c.as_of_date
                ORDER BY b.as_of_date DESC
                LIMIT %s
            ) AS hist
        ) AS h ON TRUE
        """,
        (market, source_id, data_type, as_of_date, current_row_limit, history_rows),
    )
    movers: list[dict[str, Any]] = []
    for row in rows:
        (
            security_id,
            row_market,
            row_source_id,
            row_date,
            row_open,
            high,
            low,
            close,
            volume,
            amount,
            ticker,
            issuer_id,
            issuer_name,
            previous_date,
            previous_close,
            previous_volume,
            previous_amount,
            avg_volume,
            avg_amount,
            history_count,
        ) = row
        close_f = _safe_float(close)
        previous_close_f = _safe_float(previous_close)
        volume_f = _safe_float(volume)
        amount_f = _safe_float(amount)
        avg_volume_f = _safe_float(avg_volume)
        avg_amount_f = _safe_float(avg_amount)
        one_day_return = close_f / previous_close_f - 1.0 if previous_close_f else 0.0
        volume_ratio = volume_f / avg_volume_f if avg_volume_f else 0.0
        amount_ratio = amount_f / avg_amount_f if avg_amount_f else 0.0
        intraday_range = (_safe_float(high) - _safe_float(low)) / previous_close_f if previous_close_f else 0.0
        abnormal_reasons = []
        if abs(one_day_return) >= 0.07:
            abnormal_reasons.append("涨跌幅异常")
        if amount_ratio >= 3.0:
            abnormal_reasons.append("成交额显著放大")
        if volume_ratio >= 3.0:
            abnormal_reasons.append("成交量显著放大")
        if intraday_range >= 0.08:
            abnormal_reasons.append("日内振幅较高")
        movers.append(
            {
                "security_id": str(security_id),
                "market": str(row_market),
                "source_id": str(row_source_id),
                "ticker": str(ticker or security_id),
                "issuer_id": str(issuer_id or ""),
                "issuer_name": str(issuer_name or ticker or security_id),
                "as_of_date": str(row_date),
                "previous_date": str(previous_date or ""),
                "open": _safe_float(row_open),
                "high": _safe_float(high),
                "low": _safe_float(low),
                "close": close_f,
                "previous_close": previous_close_f,
                "one_day_return": round(one_day_return, 8),
                "volume": volume_f,
                "amount": amount_f,
                "previous_volume": _safe_float(previous_volume),
                "previous_amount": _safe_float(previous_amount),
                "avg_volume": round(avg_volume_f, 4),
                "avg_amount": round(avg_amount_f, 4),
                "volume_ratio": round(volume_ratio, 4),
                "amount_ratio": round(amount_ratio, 4),
                "intraday_range": round(intraday_range, 8),
                "history_count": int(history_count or 0),
                "abnormal": bool(abnormal_reasons),
                "abnormal_reasons": abnormal_reasons,
            }
        )
    return movers


def _rank_market(movers: list[dict[str, Any]], *, limit: int) -> dict[str, list[dict[str, Any]]]:
    def top(key: str, *, absolute: bool = False, reverse: bool = True, row_limit: int = limit) -> list[dict[str, Any]]:
        return sorted(
            movers,
            key=lambda item: abs(_safe_float(item.get(key))) if absolute else _safe_float(item.get(key)),
            reverse=reverse,
        )[:row_limit]

    return {
        "top_abs_return": top("one_day_return", absolute=True),
        "top_gainers": top("one_day_return"),
        "top_losers": top("one_day_return", reverse=False),
        "top_volume_ratio": top("volume_ratio"),
        "top_amount_ratio": top("amount_ratio"),
        "abnormal": [item for item in top("one_day_return", absolute=True, row_limit=limit * 3) if item.get("abnormal")][:limit],
    }


def _fetch_positions(cursor: Any, security_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not security_ids:
        return {}
    rows = _fetch_all(
        cursor,
        """
        SELECT item_id, payload
        FROM ai_quant.records
        WHERE collection = 'company_positions'
          AND payload->>'security_id' = ANY(%s)
        """,
        (security_ids,),
    )
    by_security: dict[str, list[dict[str, Any]]] = {}
    for item_id, payload in rows:
        doc = _payload(payload)
        security_id = str(doc.get("security_id") or "")
        if not security_id:
            continue
        by_security.setdefault(security_id, []).append({"position_id": str(item_id), **doc})
    return by_security


def _fetch_chains(cursor: Any, chain_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not chain_ids:
        return {}
    rows = _fetch_all(
        cursor,
        """
        SELECT item_id, payload
        FROM ai_quant.records
        WHERE collection = 'industry_chains'
          AND item_id = ANY(%s)
        """,
        (chain_ids,),
    )
    return {str(item_id): _payload(payload) for item_id, payload in rows}


def _node_names(chain: Mapping[str, Any], node_ids: list[str]) -> list[str]:
    nodes = chain.get("nodes") or []
    by_id = {
        str(item.get("node_id") or ""): str(item.get("name") or item.get("node_id") or "")
        for item in nodes
        if isinstance(item, Mapping)
    }
    return [by_id.get(str(node_id), str(node_id)) for node_id in node_ids if str(node_id)]


def _fetch_recent_records(cursor: Any, *, collection: str, timestamp_field: str, since_date: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_all(
        cursor,
        f"""
        SELECT item_id, payload
        FROM ai_quant.records
        WHERE collection = %s
          AND COALESCE(payload->>%s, payload->>'published_at', payload->>'created_at', payload->>'indexed_at', '') >= %s
        ORDER BY COALESCE(payload->>%s, payload->>'published_at', payload->>'created_at', payload->>'indexed_at', '') DESC
        LIMIT %s
        """,
        (collection, timestamp_field, since_date, timestamp_field, limit),
    )
    results = []
    for item_id, payload in rows:
        doc = _payload(payload)
        results.append({"item_id": str(item_id), **doc})
    return results


def _fetch_asset_reports(cursor: Any, candidates: list[dict[str, Any]], *, limit_per_asset: int) -> dict[str, list[dict[str, Any]]]:
    by_security: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        security_id = str(candidate.get("security_id") or "")
        issuer_id = str(candidate.get("issuer_id") or "")
        ticker = str(candidate.get("ticker") or "").strip()
        issuer_name = str(candidate.get("issuer_name") or "").strip()
        direct_rows = _fetch_all(
            cursor,
            """
            SELECT item_id, payload
            FROM ai_quant.records
            WHERE collection = 'research_reports'
              AND (
                    payload->>'security_id' = %s
                 OR payload->>'issuer_id' = %s
              )
            ORDER BY COALESCE(payload->>'indexed_at', payload->>'published_at', '') DESC
            LIMIT %s
            """,
            (security_id, issuer_id, limit_per_asset),
        )
        rows = list(direct_rows)
        fallback_terms = [term for term in [ticker, issuer_name] if len(term) >= 3 and term != security_id]
        for term in fallback_terms:
            if len(rows) >= limit_per_asset:
                break
            fallback_rows = _fetch_all(
                cursor,
                """
                SELECT item_id, payload
                FROM ai_quant.records
                WHERE collection = 'research_reports'
                  AND (
                       payload->>'title' ILIKE %s
                    OR payload->>'file_name' ILIKE %s
                  )
                ORDER BY COALESCE(payload->>'indexed_at', payload->>'published_at', '') DESC
                LIMIT %s
                """,
                (f"%{term}%", f"%{term}%", limit_per_asset),
            )
            rows.extend(fallback_rows)
        seen: set[str] = set()
        reports: list[dict[str, Any]] = []
        for item_id, payload in rows:
            if str(item_id) in seen:
                continue
            seen.add(str(item_id))
            doc = _payload(payload)
            reports.append(
                {
                    "report_id": str(doc.get("report_id") or item_id),
                    "title": _short_text(doc.get("title") or doc.get("file_name") or item_id, 120),
                    "broker": doc.get("broker", ""),
                    "indexed_at": doc.get("indexed_at", ""),
                    "published_at": doc.get("published_at", ""),
                    "document_id": doc.get("document_id", ""),
                    "source_boundary": (doc.get("rights_tag") or {}).get("license_class", ""),
                }
            )
            if len(reports) >= limit_per_asset:
                break
        by_security[security_id] = reports
    return by_security


def _fetch_evidence_for_reports(cursor: Any, reports_by_security: dict[str, list[dict[str, Any]]], *, limit_per_asset: int) -> dict[str, list[dict[str, Any]]]:
    by_security: dict[str, list[dict[str, Any]]] = {}
    for security_id, reports in reports_by_security.items():
        document_ids = [str(item.get("document_id") or "") for item in reports if item.get("document_id")]
        if not document_ids:
            by_security[security_id] = []
            continue
        rows = _fetch_all(
            cursor,
            """
            SELECT item_id, payload
            FROM ai_quant.records
            WHERE collection = 'evidence'
              AND payload->>'document_id' = ANY(%s)
            ORDER BY COALESCE((payload->>'confidence')::numeric, 0) DESC, item_id
            LIMIT %s
            """,
            (document_ids, limit_per_asset * 12),
        )
        samples = []
        for item_id, payload in rows:
            doc = _payload(payload)
            text = doc.get("canonical_text") or doc.get("span_text") or ""
            quality = _evidence_quality(text)
            if not quality["is_useful"]:
                continue
            samples.append(
                {
                    "evidence_id": str(doc.get("evidence_id") or item_id),
                    "document_id": doc.get("document_id", ""),
                    "page_no": doc.get("page_no", ""),
                    "confidence": _safe_float(doc.get("confidence")),
                    "text": _short_text(text, 260),
                    "quality": quality,
                }
            )
            if len(samples) >= limit_per_asset:
                break
        by_security[security_id] = samples
    return by_security


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _rights_license(payload: Mapping[str, Any]) -> str:
    rights_tag = payload.get("rights_tag")
    return str(rights_tag.get("license_class") or "") if isinstance(rights_tag, Mapping) else ""


def _primary_asset_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    matches = [item for item in _list(report.get("asset_matches")) if isinstance(item, Mapping)]
    primary = dict(matches[0]) if matches else {}
    return {
        "security_id": str(report.get("security_id") or primary.get("security_id") or ""),
        "issuer_id": str(report.get("issuer_id") or primary.get("issuer_id") or ""),
        "ticker": str(report.get("ticker") or primary.get("ticker") or ""),
        "market": str(report.get("market") or primary.get("market") or ""),
        "issuer_name": str(primary.get("legal_name") or report.get("issuer_name") or ""),
    }


def _fetch_latest_market_rows(
    cursor: Any,
    *,
    security_ids: list[str],
    market: str,
    source_id: str,
    data_type: str,
    history_rows: int,
) -> dict[str, dict[str, Any]]:
    """按单个 `(market, source_id, data_type)` 键取这批证券的最新一根 K 线。

    旧实现用 `source_id = ANY([source_a, source_u])` 跨市场源混取，同一 security
    的最新日期可能落到另一市场的源上；改为按 `market_eod_key` 的三元键分市场取数
    （需求 5.6）。`market` 为空（证券未登记市场）时退化为按 `source_id` + `data_type`
    过滤，避免漏掉市场字段缺失的证券。
    """

    if not security_ids:
        return {}
    rows = _fetch_all(
        cursor,
        """
        WITH latest AS (
            SELECT DISTINCT ON (security_id)
                security_id,
                market,
                source_id,
                data_type,
                as_of_date,
                open,
                high,
                low,
                close,
                volume,
                amount
            FROM ai_quant.market_data_bars
            WHERE security_id = ANY(%s)
              AND source_id = %s
              AND data_type = %s
              AND (%s::text = '' OR market = %s::text)
            ORDER BY security_id, as_of_date DESC
        )
        SELECT
            c.security_id,
            c.market,
            c.source_id,
            c.as_of_date::text,
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
            c.amount,
            p.as_of_date::text AS previous_date,
            p.close AS previous_close,
            p.volume AS previous_volume,
            p.amount AS previous_amount,
            h.avg_volume,
            h.avg_amount,
            h.history_count
        FROM latest AS c
        LEFT JOIN LATERAL (
            SELECT as_of_date, close, volume, amount
            FROM ai_quant.market_data_bars AS b
            WHERE b.security_id = c.security_id
              AND b.source_id = c.source_id
              AND b.data_type = c.data_type
              AND b.as_of_date < c.as_of_date
            ORDER BY b.as_of_date DESC
            LIMIT 1
        ) AS p ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                AVG(NULLIF(volume, 0)) AS avg_volume,
                AVG(NULLIF(amount, 0)) AS avg_amount,
                COUNT(*) AS history_count
            FROM (
                SELECT volume, amount
                FROM ai_quant.market_data_bars AS b
                WHERE b.security_id = c.security_id
                  AND b.source_id = c.source_id
                  AND b.data_type = c.data_type
                  AND b.as_of_date < c.as_of_date
                ORDER BY b.as_of_date DESC
                LIMIT %s
            ) AS hist
        ) AS h ON TRUE
        """,
        (security_ids, source_id, data_type, market, market, history_rows),
    )
    by_security: dict[str, dict[str, Any]] = {}
    for row in rows:
        (
            security_id,
            row_market,
            row_source_id,
            as_of_date,
            row_open,
            high,
            low,
            close,
            volume,
            amount,
            previous_date,
            previous_close,
            previous_volume,
            previous_amount,
            avg_volume,
            avg_amount,
            history_count,
        ) = row
        close_f = _safe_float(close)
        previous_close_f = _safe_float(previous_close)
        volume_f = _safe_float(volume)
        amount_f = _safe_float(amount)
        avg_volume_f = _safe_float(avg_volume)
        avg_amount_f = _safe_float(avg_amount)
        by_security[str(security_id)] = {
            "market": str(row_market or ""),
            "source_id": str(row_source_id or ""),
            "as_of_date": str(as_of_date or ""),
            "previous_date": str(previous_date or ""),
            "open": _safe_float(row_open),
            "high": _safe_float(high),
            "low": _safe_float(low),
            "close": close_f,
            "previous_close": previous_close_f,
            "one_day_return": round(close_f / previous_close_f - 1.0, 8) if previous_close_f else 0.0,
            "volume": volume_f,
            "amount": amount_f,
            "previous_volume": _safe_float(previous_volume),
            "previous_amount": _safe_float(previous_amount),
            "avg_volume": round(avg_volume_f, 4),
            "avg_amount": round(avg_amount_f, 4),
            "volume_ratio": round(volume_f / avg_volume_f, 4) if avg_volume_f else 0.0,
            "amount_ratio": round(amount_f / avg_amount_f, 4) if avg_amount_f else 0.0,
            "history_count": int(history_count or 0),
        }
    return by_security


def _fetch_latest_market_context(
    cursor: Any,
    *,
    security_ids: list[str],
    data_type: str,
    source_a: str,
    source_u: str,
    history_rows: int,
    security_markets: Mapping[str, str] | None = None,
    security_statuses: Mapping[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """按每只证券所属市场的 EOD 三元键取最新行情，并标注相对市场 EOD 的滞后。

    - 取数键由 `market_eod_key` 提供，与 `market_freshness`（`_latest_date`）同键，
      修正“公司条目 2026-05-25 与市场 EOD 2026-07-24 并列且无解释”的问题（需求 5.6）。
    - 公司最新行情日期早于该市场 EOD 日期时，追加 `lag_days` / `reason_code` /
      `reason_label` / `is_lagging` / `market_eod_date`（需求 5.7）。
    - 原因码判定信号：`security_statuses` 提供 `Security.status`（停牌/退市优先），
      未提供时稳定落到 `security_not_in_latest_eod_batch`。
    """

    if not security_ids:
        return {}
    markets = security_markets or {}
    statuses = security_statuses or {}
    grouped: dict[tuple[str, str, str], list[str]] = {}
    keys: dict[tuple[str, str, str], dict[str, str]] = {}
    for security_id in security_ids:
        target = _market_eod_target(markets.get(security_id, ""), data_type=data_type, source_a=source_a, source_u=source_u)
        key = (target["market"], target["source_id"], target["data_type"])
        keys.setdefault(key, target)
        grouped.setdefault(key, []).append(security_id)
    context: dict[str, dict[str, Any]] = {}
    for key, scoped_ids in grouped.items():
        target = keys[key]
        market_eod_date = _latest_date(cursor, **target) if target["market"] else ""
        rows = _fetch_latest_market_rows(
            cursor,
            security_ids=scoped_ids,
            market=target["market"],
            source_id=target["source_id"],
            data_type=target["data_type"],
            history_rows=history_rows,
        )
        for security_id, snapshot in rows.items():
            annotation = market_freshness_annotation(
                market=target["market"],
                company_as_of_date=str(snapshot.get("as_of_date") or ""),
                market_eod_date=market_eod_date,
                data_type=target["data_type"],
                source_id=target["source_id"],
                security_status=str(statuses.get(security_id, "")),
            )
            context[security_id] = {
                **snapshot,
                "market_eod_date": annotation["market_eod_date"],
                "eod_source_id": annotation["source_id"],
                "data_type": annotation["data_type"],
                "lag_days": annotation["lag_days"],
                "reason_code": annotation["reason_code"],
                "reason_label": annotation["reason_label"],
                "is_lagging": annotation["is_lagging"],
            }
    return context


def _research_readout(item: Mapping[str, Any]) -> str:
    reports = [report for report in _list(item.get("reports")) if isinstance(report, Mapping)]
    topics = _unique_strings([topic for report in reports for topic in _list(report.get("topic_tags"))])
    risks = _unique_strings([risk for report in reports for risk in _list(report.get("risk_tags"))])
    metrics = _unique_strings([metric for report in reports for metric in _list(report.get("financial_metric_tags"))])
    latest = _first_mapping(item.get("latest_market"))
    parts: list[str] = []
    if latest.get("as_of_date"):
        parts.append(f"{latest.get('as_of_date')} 收盘 {_safe_float(latest.get('close')):.2f}，涨跌幅 {_pct(latest.get('one_day_return'))}")
        freshness_note = _freshness_note(latest)
        if freshness_note:
            parts.append(freshness_note)
    if topics:
        parts.append(f"研报主题: {', '.join(topics[:4])}")
    if metrics:
        parts.append(f"财务关注: {', '.join(metrics[:4])}")
    if risks:
        parts.append(f"风险标签: {', '.join(risks[:4])}")
    evidence_count = len(_list(item.get("evidence")))
    if evidence_count:
        parts.append(f"已绑定 {evidence_count} 条摘录证据")
    return _short_text("；".join(parts), 320)


def _evidence_quality_summary(*groups: list[dict[str, Any]]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            for evidence in _list(item.get("evidence")):
                if not isinstance(evidence, Mapping):
                    continue
                evidence_id = str(evidence.get("evidence_id") or "")
                key = evidence_id or f"{item.get('security_id')}:{len(samples)}"
                if key in seen:
                    continue
                seen.add(key)
                samples.append(dict(evidence))
    scores = [_safe_float((sample.get("quality") or {}).get("score")) for sample in samples if isinstance(sample.get("quality"), Mapping)]
    useful_count = sum(1 for sample in samples if isinstance(sample.get("quality"), Mapping) and sample["quality"].get("is_useful"))
    low_value_count = sum(1 for sample in samples if isinstance(sample.get("quality"), Mapping) and _safe_float(sample["quality"].get("low_value_reason_count")) > 0)
    private_use_count = sum(1 for sample in samples if isinstance(sample.get("quality"), Mapping) and _safe_float(sample["quality"].get("private_use_ratio")) > 0.08)
    return {
        "sample_count": len(samples),
        "useful_sample_count": useful_count,
        "low_value_sample_count": low_value_count,
        "private_use_noise_sample_count": private_use_count,
        "average_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "minimum_quality_score": round(min(scores), 4) if scores else 0.0,
    }


def _direct_evidence_headline(watchlist: list[dict[str, Any]], *, limit: int = 3) -> str:
    direct_items = [item for item in watchlist if item.get("evidence_status") == "direct_report_evidence"]
    if not direct_items:
        return ""
    fragments: list[str] = []
    for item in direct_items[: max(1, limit)]:
        latest = item.get("latest_market") if isinstance(item.get("latest_market"), Mapping) else {}
        if not latest:
            latest = item
        market = item.get("market") or latest.get("market") or "-"
        close = latest.get("close")
        pct = latest.get("one_day_return")
        price_part = f"收盘 {close}，涨跌幅 {_pct(pct)}" if close not in {None, ""} else "行情待补"
        chain = item.get("chain_name") or "产业链待补"
        evidence_count = len(item.get("evidence") or [])
        report_count = len(item.get("reports") or [])
        fragments.append(f"{market} {item.get('ticker')} {chain}: {price_part}，{report_count} 份研报/{evidence_count} 条证据")
    return "直接研报证据优先: " + "；".join(fragments)


def _market_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    latest = _first_mapping(item.get("latest_market"))
    source = latest if latest else item
    return {
        "market": str(source.get("market") or item.get("market") or ""),
        "source_id": str(source.get("source_id") or item.get("source_id") or ""),
        "as_of_date": str(source.get("as_of_date") or item.get("as_of_date") or ""),
        "close": source.get("close", ""),
        "one_day_return": _safe_float(source.get("one_day_return")),
        "amount_ratio": _safe_float(source.get("amount_ratio")),
        "volume_ratio": _safe_float(source.get("volume_ratio")),
        # 与 market_freshness 同键的市场 EOD 基准与滞后标注（需求 5.6、5.7）。
        "market_eod_date": str(source.get("market_eod_date") or ""),
        "lag_days": int(_safe_float(source.get("lag_days"))),
        "reason_code": str(source.get("reason_code") or ""),
        "reason_label": str(source.get("reason_label") or ""),
        "is_lagging": bool(source.get("is_lagging")),
    }


def _freshness_note(latest: Mapping[str, Any]) -> str:
    """公司最新行情早于市场 EOD 时的中文滞后说明；不滞后返回空串（需求 5.7）。"""

    if not latest.get("is_lagging"):
        return ""
    lag_days = int(_safe_float(latest.get("lag_days")))
    note = f"滞后市场 EOD {latest.get('market_eod_date') or '-'} 共 {lag_days} 天"
    label = str(latest.get("reason_label") or "")
    return f"{note}（{label}）" if label else note


def _ensure_company_activity(rows: dict[str, dict[str, Any]], seed: Mapping[str, Any]) -> dict[str, Any]:
    primary = _primary_asset_from_report(seed)
    security_id = str(seed.get("security_id") or primary.get("security_id") or "")
    if not security_id:
        return {}
    row = rows.setdefault(
        security_id,
        {
            "security_id": security_id,
            "issuer_id": "",
            "ticker": "",
            "issuer_name": "",
            "market": "",
            "chain_id": "",
            "chain_name": "",
            "node_ids": [],
            "node_names": [],
            "position_role": "",
            "positioning_summary": "",
            "latest_market": {},
            "activity_items": [],
            "evidence_samples": [],
            "_activity_keys": set(),
            "_evidence_keys": set(),
        },
    )
    for key in ("issuer_id", "ticker", "issuer_name", "market", "chain_id", "chain_name", "position_role", "positioning_summary"):
        value = seed.get(key) or primary.get(key)
        if value and not row.get(key):
            row[key] = str(value)
    for key in ("node_ids", "node_names"):
        values = _list(seed.get(key))
        if values and not row.get(key):
            row[key] = [str(item) for item in values if str(item)]
    snapshot = _market_snapshot(seed)
    if any(snapshot.get(key) not in {"", 0.0} for key in ("as_of_date", "close", "one_day_return", "amount_ratio", "volume_ratio")):
        existing = _first_mapping(row.get("latest_market"))
        if not existing or str(snapshot.get("as_of_date") or "") >= str(existing.get("as_of_date") or ""):
            row["latest_market"] = snapshot
            if snapshot.get("market") and not row.get("market"):
                row["market"] = snapshot["market"]
    return row


def _add_company_activity_item(row: dict[str, Any], item: Mapping[str, Any]) -> None:
    key = str(
        item.get("activity_id")
        or item.get("report_id")
        or item.get("document_id")
        or f"{item.get('activity_type')}:{item.get('title')}:{item.get('as_of_date') or item.get('indexed_at') or item.get('published_at')}"
    )
    keys = row.setdefault("_activity_keys", set())
    if key in keys:
        return
    keys.add(key)
    row.setdefault("activity_items", []).append(dict(item))


def _add_company_evidence_sample(row: dict[str, Any], sample: Mapping[str, Any]) -> None:
    key = str(sample.get("evidence_id") or f"{sample.get('document_id')}:{sample.get('text')}")
    keys = row.setdefault("_evidence_keys", set())
    if not key or key in keys:
        return
    keys.add(key)
    row.setdefault("evidence_samples", []).append(
        {
            "evidence_id": sample.get("evidence_id", ""),
            "document_id": sample.get("document_id", ""),
            "page_no": sample.get("page_no", ""),
            "confidence": _safe_float(sample.get("confidence")),
            "quality_score": _safe_float((sample.get("quality") or {}).get("score")) if isinstance(sample.get("quality"), Mapping) else 0.0,
            "text": _short_text(sample.get("text"), 220),
        }
    )


def _report_activity(report: Mapping[str, Any], *, activity_type: str) -> dict[str, Any]:
    return {
        "activity_type": activity_type,
        "report_id": str(report.get("report_id") or report.get("item_id") or ""),
        "document_id": str(report.get("document_id") or ""),
        "title": _short_text(report.get("title") or report.get("file_name") or report.get("report_id"), 150),
        "broker": report.get("broker", ""),
        "indexed_at": report.get("indexed_at", ""),
        "published_at": report.get("published_at", ""),
        "source_boundary": report.get("source_boundary", ""),
        "topic_tags": _unique_strings(_list(report.get("topic_tags"))),
        "risk_tags": _unique_strings(_list(report.get("risk_tags"))),
        "financial_metric_tags": _unique_strings(_list(report.get("financial_metric_tags"))),
    }


def _document_activity(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "activity_type": "recent_document_event",
        "document_id": str(document.get("document_id") or document.get("item_id") or ""),
        "title": _short_text(document.get("title") or document.get("file_name") or document.get("document_id"), 150),
        "document_type": document.get("document_type", ""),
        "published_at": document.get("published_at", ""),
        "source": document.get("source", ""),
    }


def _activity_date(item: Mapping[str, Any]) -> str:
    return str(item.get("indexed_at") or item.get("published_at") or item.get("as_of_date") or "")


def _activity_summary(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    latest = _first_mapping(row.get("latest_market"))
    if latest.get("as_of_date"):
        price = f"收盘 {latest.get('close')}" if latest.get("close") not in {None, ""} else "收盘待补"
        parts.append(f"{latest.get('as_of_date')} {price}，涨跌幅 {_pct(latest.get('one_day_return'))}")
        freshness_note = _freshness_note(latest)
        if freshness_note:
            parts.append(freshness_note)
    reports = [item for item in _list(row.get("activity_items")) if str(item.get("activity_type") or "").endswith("research_report")]
    documents = [item for item in _list(row.get("activity_items")) if item.get("activity_type") == "recent_document_event"]
    market_events = [item for item in _list(row.get("activity_items")) if item.get("activity_type") == "market_abnormal"]
    if reports:
        parts.append(f"{len(reports)} 条公司绑定研报")
    if documents:
        parts.append(f"{len(documents)} 条近期文档/事件")
    if market_events:
        reasons = _unique_strings([reason for event in market_events for reason in _list(event.get("reasons"))])
        parts.append(f"异动: {', '.join(reasons[:3]) if reasons else '涨跌/成交排序靠前'}")
    evidence_count = len(_list(row.get("evidence_samples")))
    if evidence_count:
        parts.append(f"{evidence_count} 条可用证据摘录")
    return _short_text("；".join(parts), 320)


def _build_company_recent_activity(
    *,
    evidence_bindings: list[dict[str, Any]],
    evidence_backed_watchlist: list[dict[str, Any]],
    recent_reports: list[dict[str, Any]],
    recent_documents: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}

    for item in evidence_backed_watchlist:
        row = _ensure_company_activity(rows, item)
        if not row:
            continue
        for report in _list(item.get("reports"))[:3]:
            if isinstance(report, Mapping):
                _add_company_activity_item(row, _report_activity(report, activity_type="bound_research_report"))
        for sample in _list(item.get("evidence"))[:3]:
            if isinstance(sample, Mapping):
                _add_company_evidence_sample(row, sample)

    for item in evidence_bindings:
        row = _ensure_company_activity(rows, item)
        if not row:
            continue
        if item.get("abnormal_reasons") or item.get("as_of_date"):
            _add_company_activity_item(
                row,
                {
                    "activity_type": "market_abnormal",
                    "activity_id": f"market:{item.get('security_id')}:{item.get('as_of_date')}",
                    "as_of_date": item.get("as_of_date", ""),
                    "reasons": _list(item.get("abnormal_reasons")),
                    "one_day_return": _safe_float(item.get("one_day_return")),
                    "amount_ratio": _safe_float(item.get("amount_ratio")),
                    "volume_ratio": _safe_float(item.get("volume_ratio")),
                },
            )
        for report in _list(item.get("reports"))[:3]:
            if isinstance(report, Mapping):
                _add_company_activity_item(row, _report_activity(report, activity_type="abnormal_mover_research_report"))
        for sample in _list(item.get("evidence"))[:3]:
            if isinstance(sample, Mapping):
                _add_company_evidence_sample(row, sample)

    for report in recent_reports:
        primary = _primary_asset_from_report(report)
        if not primary.get("security_id"):
            continue
        row = _ensure_company_activity(rows, {**primary, **report})
        if row:
            _add_company_activity_item(row, _report_activity(report, activity_type="recent_research_report"))

    for document in recent_documents:
        security_id = str(document.get("security_id") or "")
        if not security_id:
            continue
        row = _ensure_company_activity(rows, document)
        if row:
            _add_company_activity_item(row, _document_activity(document))

    cleaned: list[dict[str, Any]] = []
    for row in rows.values():
        row["activity_items"] = sorted(_list(row.get("activity_items")), key=_activity_date, reverse=True)[:6]
        row["evidence_samples"] = _list(row.get("evidence_samples"))[:4]
        row["activity_summary"] = _activity_summary(row)
        row.pop("_activity_keys", None)
        row.pop("_evidence_keys", None)
        cleaned.append(row)

    def sort_key(row: Mapping[str, Any]) -> tuple[int, int, str, float, float]:
        latest = _first_mapping(row.get("latest_market"))
        return (
            1 if row.get("chain_name") or row.get("node_names") else 0,
            len(_list(row.get("evidence_samples"))),
            max([_activity_date(item) for item in _list(row.get("activity_items"))] or [""]),
            abs(_safe_float(latest.get("one_day_return"))),
            _safe_float(latest.get("amount_ratio")),
        )

    return sorted(cleaned, key=sort_key, reverse=True)[:limit]


def _abnormal_headline(movers_by_market: Mapping[str, Any]) -> str:
    lines = []
    for market in ("A", "U"):
        market_payload = movers_by_market.get(market) if isinstance(movers_by_market.get(market), Mapping) else {}
        abnormal = market_payload.get("abnormal") or []
        if abnormal:
            sample = abnormal[0]
            lines.append(f"{market} 市场首要异动: {sample.get('ticker')} {sample.get('issuer_name')} 涨跌幅 {_pct(sample.get('one_day_return'))}")
    if not lines:
        lines.append("未检测到达到默认阈值的异常涨跌或成交放大，仍需查看涨跌/放量排序。")
    return "；".join(lines)


def _fetch_bound_research_watchlist(
    cursor: Any,
    *,
    as_of_date: str,
    limit: int,
    reports_per_asset: int,
    evidence_per_asset: int,
    data_type: str,
    source_a: str,
    source_u: str,
    history_rows: int,
) -> list[dict[str, Any]]:
    rows = _fetch_all(
        cursor,
        """
        SELECT
            rr.item_id,
            rr.payload,
            sec.item_id,
            sec.payload,
            iss.payload
        FROM ai_quant.records AS rr
        LEFT JOIN ai_quant.records AS sec
          ON sec.collection = 'securities'
         AND sec.item_id = COALESCE(NULLIF(rr.payload #>> '{security_id}', ''), rr.payload #>> '{asset_matches,0,security_id}')
        LEFT JOIN ai_quant.records AS iss
          ON iss.collection = 'issuers'
         AND iss.item_id = COALESCE(sec.payload->>'issuer_id', NULLIF(rr.payload #>> '{issuer_id}', ''), rr.payload #>> '{asset_matches,0,issuer_id}')
        WHERE rr.collection = %s
          AND (
                 rr.payload #>> '{asset_binding,status}' = 'matched'
              OR COALESCE(rr.payload #>> '{security_id}', '') <> ''
              OR CASE
                    WHEN jsonb_typeof(rr.payload->'asset_matches') = 'array'
                    THEN jsonb_array_length(rr.payload->'asset_matches')
                    ELSE 0
                 END > 0
          )
        ORDER BY COALESCE(rr.payload->>'indexed_at', rr.payload->>'published_at', rr.payload->>'created_at', '') DESC,
                 rr.item_id DESC
        LIMIT %s
        """,
        ("research_reports", max(limit * 8, limit)),
    )
    grouped: dict[str, dict[str, Any]] = {}
    security_statuses: dict[str, str] = {}
    for report_item_id, raw_report, security_item_id, raw_security, raw_issuer in rows:
        report = _payload(raw_report)
        report_date = (
            _date_part(report.get("published_at"))
            or _date_prefix(report.get("title"))
            or _date_prefix(report.get("file_name"))
            or _date_part(report.get("indexed_at"))
            or _date_part(report.get("created_at"))
        )
        if as_of_date and report_date and report_date > as_of_date:
            continue
        security = _payload(raw_security)
        issuer = _payload(raw_issuer)
        primary = _primary_asset_from_report(report)
        security_id = str(primary.get("security_id") or security.get("security_id") or security_item_id or "")
        if not security_id:
            continue
        if security_id not in grouped and len(grouped) >= limit:
            continue
        ticker = str(security.get("ticker") or primary.get("ticker") or security_id)
        issuer_id = str(security.get("issuer_id") or primary.get("issuer_id") or "")
        # 停牌/退市是滞后原因码的最高优先信号（需求 5.7）；空串按未知处理。
        if str(security.get("status") or ""):
            security_statuses[security_id] = str(security.get("status") or "")
        entry = grouped.setdefault(
            security_id,
            {
                "security_id": security_id,
                "issuer_id": issuer_id,
                "ticker": ticker,
                "market": str(security.get("market") or primary.get("market") or ""),
                "issuer_name": str(issuer.get("legal_name") or primary.get("issuer_name") or ticker),
                "reports": [],
            },
        )
        if len(entry["reports"]) >= reports_per_asset:
            continue
        viewpoint = report.get("viewpoint") if isinstance(report.get("viewpoint"), Mapping) else {}
        report_topics = _list(report.get("evidence_topics")) or _list(viewpoint.get("topics"))
        report_risks = _list(report.get("risk_tags")) or _list(viewpoint.get("risks"))
        report_metrics = _list(report.get("financial_metric_tags")) or _list(viewpoint.get("financial_metrics"))
        entry["reports"].append(
            {
                "report_id": str(report.get("report_id") or report_item_id),
                "title": _short_text(report.get("title") or report.get("file_name") or report_item_id, 150),
                "broker": report.get("broker", ""),
                "indexed_at": report.get("indexed_at", ""),
                "published_at": report.get("published_at", ""),
                "document_id": report.get("document_id", ""),
                "source_boundary": _rights_license(report),
                "topic_tags": _unique_strings(report_topics),
                "risk_tags": _unique_strings(report_risks),
                "financial_metric_tags": _unique_strings(report_metrics),
                "viewpoint": {
                    "sentiment": viewpoint.get("sentiment", ""),
                    "topics": _unique_strings(report_topics),
                    "risks": _unique_strings(report_risks),
                    "financial_metrics": _unique_strings(report_metrics),
                },
            }
        )

    security_ids = list(grouped)
    positions = _fetch_positions(cursor, security_ids)
    chain_ids = sorted({str(position.get("chain_id") or "") for values in positions.values() for position in values if position.get("chain_id")})
    chains = _fetch_chains(cursor, chain_ids)
    reports_by_security = {security_id: entry["reports"] for security_id, entry in grouped.items()}
    evidence = _fetch_evidence_for_reports(cursor, reports_by_security, limit_per_asset=evidence_per_asset)
    latest_market = _fetch_latest_market_context(
        cursor,
        security_ids=security_ids,
        data_type=data_type,
        source_a=source_a,
        source_u=source_u,
        history_rows=history_rows,
        security_markets={security_id: str(entry.get("market") or "") for security_id, entry in grouped.items()},
        security_statuses=security_statuses,
    )

    watchlist: list[dict[str, Any]] = []
    for security_id, entry in grouped.items():
        position = (positions.get(security_id) or [{}])[0]
        chain_id = str(position.get("chain_id") or "")
        node_ids = [str(item) for item in (position.get("node_ids") or [])]
        chain = chains.get(chain_id, {})
        item = {
            **entry,
            "latest_market": latest_market.get(security_id, {}),
            "chain_id": chain_id,
            "chain_name": chain.get("name", ""),
            "node_ids": node_ids,
            "node_names": _node_names(chain, node_ids),
            "position_role": position.get("role", ""),
            "positioning_summary": _short_text(position.get("positioning_summary", ""), 220),
            "evidence": evidence.get(security_id, []),
            "evidence_status": "direct_report_evidence" if evidence.get(security_id) else "direct_report_no_extracted_evidence",
        }
        item["research_readout"] = _research_readout(item)
        watchlist.append(item)
    return watchlist


def _bind_evidence(
    *,
    movers: list[dict[str, Any]],
    positions: dict[str, list[dict[str, Any]]],
    chains: dict[str, dict[str, Any]],
    reports: dict[str, list[dict[str, Any]]],
    evidence: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, Any]]:
    rows = []
    for mover in movers[:limit]:
        security_id = str(mover.get("security_id") or "")
        position = (positions.get(security_id) or [{}])[0]
        chain_id = str(position.get("chain_id") or "")
        node_ids = [str(item) for item in (position.get("node_ids") or [])]
        chain = chains.get(chain_id, {})
        asset_reports = reports.get(security_id, [])
        asset_evidence = evidence.get(security_id, [])
        if asset_evidence:
            evidence_status = "direct_report_evidence"
        elif asset_reports:
            evidence_status = "direct_report_no_extracted_evidence"
        elif position:
            evidence_status = "position_only_no_report_evidence"
        else:
            evidence_status = "missing_direct_evidence"
        rows.append(
            {
                "security_id": security_id,
                "ticker": mover.get("ticker", ""),
                "issuer_id": mover.get("issuer_id", ""),
                "issuer_name": mover.get("issuer_name", ""),
                "market": mover.get("market", ""),
                "as_of_date": mover.get("as_of_date", ""),
                "one_day_return": mover.get("one_day_return", 0),
                "amount_ratio": mover.get("amount_ratio", 0),
                "volume_ratio": mover.get("volume_ratio", 0),
                "abnormal_reasons": mover.get("abnormal_reasons", []),
                "chain_id": chain_id,
                "chain_name": chain.get("name", ""),
                "node_ids": node_ids,
                "node_names": _node_names(chain, node_ids),
                "position_role": position.get("role", ""),
                "positioning_summary": _short_text(position.get("positioning_summary", ""), 220),
                "reports": asset_reports,
                "evidence": asset_evidence,
                "evidence_status": evidence_status,
            }
        )
    return rows


def build_daily_market_insight(
    *,
    dsn: str,
    as_of_date: str,
    source_a: str,
    source_u: str,
    data_type: str,
    top_limit: int,
    current_row_limit: int,
    history_rows: int,
    recent_days: int,
    min_direct_evidence_companies: int = 1,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    since_date = (date.fromisoformat(as_of_date) - timedelta(days=recent_days)).isoformat()
    with _connect(dsn) as connection:
        with connection.cursor() as cursor:
            legacy_count = int(_fetch_one(cursor, "SELECT COUNT(*) FROM ai_quant.records WHERE collection = 'market_data'")[0] or 0)
            # market_freshness 与公司活动条目共用 market_eod_key 解析的三元键（需求 5.6）。
            market_targets = _market_eod_targets(data_type=data_type, source_a=source_a, source_u=source_u)
            market_freshness = []
            movers_by_market: dict[str, Any] = {}
            all_ranked: list[dict[str, Any]] = []
            for target in market_targets:
                latest = _latest_date(cursor, market=target["market"], source_id=target["source_id"], data_type=target["data_type"])
                market_freshness.append({**target, "latest_date": latest})
                movers = _fetch_market_movers(
                    cursor,
                    market=target["market"],
                    source_id=target["source_id"],
                    data_type=target["data_type"],
                    as_of_date=latest,
                    current_row_limit=current_row_limit,
                    history_rows=history_rows,
                )
                ranked = _rank_market(movers, limit=top_limit)
                movers_by_market[target["market"]] = {
                    "market": target["market"],
                    "source_id": target["source_id"],
                    "latest_date": latest,
                    "current_row_count": len(movers),
                    **ranked,
                }
                all_ranked.extend(ranked["top_abs_return"][: max(3, top_limit // 2)])
                all_ranked.extend(ranked["top_amount_ratio"][: max(3, top_limit // 2)])
                all_ranked.extend(ranked["top_volume_ratio"][: max(3, top_limit // 2)])

            seen_security_ids: set[str] = set()
            candidates: list[dict[str, Any]] = []
            for item in sorted(
                all_ranked,
                key=lambda row: (
                    abs(_safe_float(row.get("one_day_return"))),
                    _safe_float(row.get("amount_ratio")),
                    _safe_float(row.get("volume_ratio")),
                ),
                reverse=True,
            ):
                security_id = str(item.get("security_id") or "")
                if not security_id or security_id in seen_security_ids:
                    continue
                seen_security_ids.add(security_id)
                candidates.append(item)
                if len(candidates) >= top_limit * 2:
                    break

            positions = _fetch_positions(cursor, [str(item.get("security_id")) for item in candidates])
            chain_ids = sorted({str(position.get("chain_id") or "") for values in positions.values() for position in values if position.get("chain_id")})
            chains = _fetch_chains(cursor, chain_ids)
            reports = _fetch_asset_reports(cursor, candidates, limit_per_asset=3)
            evidence = _fetch_evidence_for_reports(cursor, reports, limit_per_asset=3)
            evidence_bindings = _bind_evidence(
                movers=candidates,
                positions=positions,
                chains=chains,
                reports=reports,
                evidence=evidence,
                limit=top_limit,
            )
            evidence_backed_watchlist = _fetch_bound_research_watchlist(
                cursor,
                as_of_date=as_of_date,
                limit=top_limit,
                reports_per_asset=3,
                evidence_per_asset=4,
                data_type=data_type,
                source_a=source_a,
                source_u=source_u,
                history_rows=history_rows,
            )
            recent_reports = _fetch_recent_records(cursor, collection="research_reports", timestamp_field="indexed_at", since_date=since_date, limit=top_limit)
            recent_documents = _fetch_recent_records(cursor, collection="documents", timestamp_field="published_at", since_date=since_date, limit=top_limit)

    company_recent_activity = _build_company_recent_activity(
        evidence_bindings=evidence_bindings,
        evidence_backed_watchlist=evidence_backed_watchlist,
        recent_reports=recent_reports,
        recent_documents=recent_documents,
        limit=top_limit,
    )

    abnormal_count = sum(len((movers_by_market.get(market) or {}).get("abnormal") or []) for market in movers_by_market)
    bound_count = sum(1 for item in evidence_bindings if item.get("evidence_status") in {"direct_report_evidence", "direct_report_no_extracted_evidence", "position_only_no_report_evidence"})
    direct_evidence_security_ids = {
        str(item.get("security_id") or "")
        for item in evidence_bindings
        if item.get("evidence_status") == "direct_report_evidence" and item.get("security_id")
    }
    direct_evidence_security_ids.update(
        str(item.get("security_id") or "")
        for item in evidence_backed_watchlist
        if item.get("evidence_status") == "direct_report_evidence" and item.get("security_id")
    )
    direct_evidence_count = len(direct_evidence_security_ids)
    evidence_quality_summary = _evidence_quality_summary(evidence_bindings, evidence_backed_watchlist)
    failures = []
    if legacy_count:
        failures.append({"check": "typed_only_market_data", "error": "legacy records.market_data rows exist", "value": legacy_count})
    if not any((movers_by_market.get(market) or {}).get("current_row_count") for market in movers_by_market):
        failures.append({"check": "market_mover_rows", "error": "no current market rows available"})
    min_direct_evidence_companies = max(0, int(min_direct_evidence_companies or 0))
    if direct_evidence_count < min_direct_evidence_companies:
        failures.append(
            {
                "check": "direct_report_evidence",
                "error": "not enough companies have useful direct research-report evidence",
                "value": direct_evidence_count,
                "minimum": min_direct_evidence_companies,
            }
        )

    direct_headline = _direct_evidence_headline(evidence_backed_watchlist) or _direct_evidence_headline(evidence_bindings)
    abnormal_headline = _abnormal_headline(movers_by_market)

    return {
        "status": "failed" if failures else "passed",
        "passed": not failures,
        "generated_at": generated_at,
        "as_of_date": as_of_date,
        "production_boundary": "local_research_summary_only_no_live_broker_no_auto_order",
        "query_strategy": "typed_market_data_bars_only_indexed_latest_date_and_security_date_queries",
        "market_freshness": market_freshness,
        "legacy_market_data_records": legacy_count,
        "movers_by_market": movers_by_market,
        "research_and_events": {
            "recent_since_date": since_date,
            "recent_report_count": len(recent_reports),
            "recent_document_count": len(recent_documents),
            "company_recent_activity_count": len(company_recent_activity),
            "recent_reports": [
                {
                    "report_id": item.get("report_id") or item.get("item_id"),
                    "title": _short_text(item.get("title") or item.get("file_name"), 140),
                    "broker": item.get("broker", ""),
                    "indexed_at": item.get("indexed_at", ""),
                    "security_id": item.get("security_id", ""),
                    "issuer_id": item.get("issuer_id", ""),
                }
                for item in recent_reports
            ],
            "recent_documents": [
                {
                    "document_id": item.get("document_id") or item.get("item_id"),
                    "title": _short_text(item.get("title"), 140),
                    "document_type": item.get("document_type", ""),
                    "published_at": item.get("published_at", ""),
                    "security_id": item.get("security_id", ""),
                    "issuer_id": item.get("issuer_id", ""),
                }
                for item in recent_documents
            ],
            "company_recent_activity": [
                {
                    "issuer_id": item.get("issuer_id", ""),
                    "security_id": item.get("security_id", ""),
                    "ticker": item.get("ticker", ""),
                    "issuer_name": item.get("issuer_name", ""),
                    "market": item.get("market", ""),
                    "chain_id": item.get("chain_id", ""),
                    "chain": item.get("chain_name", ""),
                    "nodes": item.get("node_names", []),
                    "position_role": item.get("position_role", ""),
                    "latest_market": item.get("latest_market", {}),
                    "activity_summary": item.get("activity_summary", ""),
                    "activity_count": len(item.get("activity_items") or []),
                    "evidence_count": len(item.get("evidence_samples") or []),
                    "activities": item.get("activity_items", []),
                    "evidence_samples": item.get("evidence_samples", []),
                }
                for item in company_recent_activity
            ],
        },
        "evidence_bindings": evidence_bindings,
        "evidence_backed_watchlist": evidence_backed_watchlist,
        "actionable_research_summary": {
            "status": "research_only" if direct_evidence_count else "needs_direct_report_evidence",
            "headline": direct_headline or abnormal_headline,
            "abnormal_headline": abnormal_headline,
            "direct_evidence_headline": direct_headline,
            "abnormal_company_count": abnormal_count,
            "evidence_bound_company_count": bound_count,
            "direct_report_evidence_company_count": direct_evidence_count,
            "evidence_backed_watchlist_count": len(evidence_backed_watchlist),
            "company_recent_activity_count": len(company_recent_activity),
            "evidence_quality": evidence_quality_summary,
            "watch_items": [
                {
                    "ticker": item.get("ticker"),
                    "issuer_name": item.get("issuer_name"),
                    "market": item.get("market"),
                    "reason": ", ".join(item.get("abnormal_reasons") or []) or "涨跌/放量排序靠前",
                    "chain": item.get("chain_name", ""),
                    "nodes": item.get("node_names", []),
                    "evidence_status": item.get("evidence_status"),
                }
                for item in evidence_bindings[: min(8, len(evidence_bindings))]
            ],
            "direct_report_watch_items": [
                {
                    "ticker": item.get("ticker"),
                    "issuer_name": item.get("issuer_name"),
                    "market": item.get("market"),
                    "chain": item.get("chain_name", ""),
                    "nodes": item.get("node_names", []),
                    "evidence_status": item.get("evidence_status"),
                    "report_count": len(item.get("reports") or []),
                    "evidence_count": len(item.get("evidence") or []),
                    "research_readout": item.get("research_readout", ""),
                }
                for item in evidence_backed_watchlist[: min(8, len(evidence_backed_watchlist))]
            ],
            "company_recent_activity_items": [
                {
                    "issuer_id": item.get("issuer_id"),
                    "security_id": item.get("security_id"),
                    "ticker": item.get("ticker"),
                    "issuer_name": item.get("issuer_name"),
                    "market": item.get("market"),
                    "chain": item.get("chain_name", ""),
                    "nodes": item.get("node_names", []),
                    "latest_market": item.get("latest_market", {}),
                    "activity_summary": item.get("activity_summary", ""),
                    "activity_count": len(item.get("activity_items") or []),
                    "evidence_count": len(item.get("evidence_samples") or []),
                }
                for item in company_recent_activity[: min(8, len(company_recent_activity))]
            ],
        },
        "quality_gates": {
            "typed_only_market_data": legacy_count == 0,
            "has_current_market_rows": any((movers_by_market.get(market) or {}).get("current_row_count") for market in movers_by_market),
            "has_evidence_bindings": bound_count > 0,
            "has_direct_report_evidence": direct_evidence_count > 0,
            "has_min_direct_report_evidence": direct_evidence_count >= min_direct_evidence_companies,
            "has_company_recent_activity": len(company_recent_activity) > 0,
            "min_direct_evidence_companies": min_direct_evidence_companies,
            "direct_report_evidence_company_count": direct_evidence_count,
            "company_recent_activity_company_count": len(company_recent_activity),
            "useful_evidence_sample_count": evidence_quality_summary["useful_sample_count"],
            "failure_count": len(failures),
            "failures": failures,
        },
    }


def _format_mover_row(item: Mapping[str, Any]) -> str:
    return (
        f"| {item.get('ticker')} | {item.get('issuer_name')} | {item.get('as_of_date')} | "
        f"{_pct(item.get('one_day_return'))} | {item.get('close')} | "
        f"{_safe_float(item.get('amount_ratio')):.2f} | {_safe_float(item.get('volume_ratio')):.2f} | "
        f"{', '.join(item.get('abnormal_reasons') or []) or '-'} |"
    )


def build_markdown(result: Mapping[str, Any]) -> str:
    lines = [
        "# 每日可行动研究摘要",
        "",
        f"- 生成时间: {result.get('generated_at')}",
        f"- 状态: {result.get('status')}",
        f"- 边界: {result.get('production_boundary')}",
        f"- 查询策略: {result.get('query_strategy')}",
        "",
        "## 行情时效",
        "",
        "| 市场 | 来源 | 最新日期 |",
        "| --- | --- | --- |",
    ]
    for item in result.get("market_freshness", []) or []:
        lines.append(f"| {item.get('market')} | {item.get('source_id')} | {item.get('latest_date')} |")

    summary = result.get("actionable_research_summary") or {}
    lines.extend(["", "## 研究结论", "", f"- {summary.get('headline', '')}", ""])
    for item in summary.get("watch_items", []) or []:
        nodes = ", ".join(item.get("nodes") or [])
        lines.append(
            f"- {item.get('market')} {item.get('ticker')} {item.get('issuer_name')}: "
            f"{item.get('reason')}；产业链={item.get('chain') or '-'}；节点={nodes or '-'}；证据={item.get('evidence_status')}"
        )

    watchlist = result.get("evidence_backed_watchlist") or []
    lines.extend(["", "## 直接研报证据观察池", ""])
    if not watchlist:
        lines.append("- 暂无已绑定到标的的研报证据。")
    for item in watchlist[:10]:
        latest = item.get("latest_market") or {}
        nodes = ", ".join(item.get("node_names") or [])
        lines.append(
            f"- {item.get('market') or latest.get('market') or '-'} {item.get('ticker')} {item.get('issuer_name')}: "
            f"{item.get('research_readout') or '-'}；产业链={item.get('chain_name') or '-'}；节点={nodes or '-'}"
        )
        for report in (item.get("reports") or [])[:2]:
            tags = ", ".join(
                _unique_strings(
                    _list(report.get("topic_tags"))
                    + _list(report.get("financial_metric_tags"))
                    + _list(report.get("risk_tags"))
                )[:6]
            )
            lines.append(
                f"  - 研报: {_short_text(report.get('title'), 140)} "
                f"({report.get('broker') or '-'}, {report.get('indexed_at') or report.get('published_at') or '-'})"
                f"{'；标签=' + tags if tags else ''}"
            )
        for sample in (item.get("evidence") or [])[:2]:
            lines.append(f"  - 证据: {_short_text(sample.get('text'), 180)}")

    company_recent_activity = result.get("research_and_events", {}).get("company_recent_activity", []) or []
    lines.extend(["", "## 公司级新研报/公告/事件", ""])
    if not company_recent_activity:
        lines.append("- 暂无可绑定到公司的近期研报/公告/事件。")
    for item in company_recent_activity[:8]:
        latest = item.get("latest_market") or {}
        nodes = ", ".join(item.get("nodes") or [])
        market_text = (
            f"{latest.get('as_of_date')} 收盘 {latest.get('close')}，涨跌幅 {_pct(latest.get('one_day_return'))}"
            if latest.get("as_of_date")
            else "行情待补"
        )
        freshness_note = _freshness_note(latest)
        if freshness_note:
            market_text = f"{market_text}（{freshness_note}）"
        lines.append(
            f"- {item.get('market') or latest.get('market') or '-'} {item.get('ticker')} {item.get('issuer_name')}: "
            f"{item.get('activity_summary') or '-'}；产业链={item.get('chain') or '-'}；节点={nodes or '-'}；行情={market_text}"
        )
        for activity in (item.get("activities") or [])[:2]:
            lines.append(
                f"  - 活动: {activity.get('activity_type') or '-'} "
                f"{_short_text(activity.get('title') or activity.get('document_id') or activity.get('report_id'), 120)} "
                f"({activity.get('indexed_at') or activity.get('published_at') or activity.get('as_of_date') or '-'})"
            )
        for sample in (item.get("evidence_samples") or [])[:2]:
            lines.append(f"  - 证据: {_short_text(sample.get('text'), 180)}")

    for market, label in (("A", "A 股"), ("U", "美股")):
        market_payload = (result.get("movers_by_market") or {}).get(market) or {}
        lines.extend(
            [
                "",
                f"## {label}异动",
                "",
                "| 代码 | 公司 | 日期 | 涨跌幅 | 收盘 | 成交额倍率 | 成交量倍率 | 原因 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        rows = market_payload.get("abnormal") or market_payload.get("top_abs_return") or []
        for item in rows[:10]:
            lines.append(_format_mover_row(item))

    lines.extend(
        [
            "",
            "## 证据与产业链绑定",
            "",
            "| 标的 | 产业链 | 节点 | 定位 | 研报样本 | 证据样本 |",
            "| --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for item in result.get("evidence_bindings", []) or []:
        lines.append(
            f"| {item.get('ticker')} {item.get('issuer_name')} | {item.get('chain_name') or '-'} | "
            f"{', '.join(item.get('node_names') or []) or '-'} | {_short_text(item.get('position_role'), 80) or '-'} | "
            f"{len(item.get('reports') or [])} | {len(item.get('evidence') or [])} |"
        )

    recent = result.get("research_and_events") or {}
    lines.extend(["", "## 新研报/文档", ""])
    for item in recent.get("recent_reports", [])[:8]:
        lines.append(f"- 研报: {_short_text(item.get('title'), 140)} ({item.get('broker') or '-'}, {item.get('indexed_at') or '-'})")
    for item in recent.get("recent_documents", [])[:8]:
        lines.append(f"- 文档/事件: {_short_text(item.get('title'), 140)} ({item.get('document_type') or '-'}, {item.get('published_at') or '-'})")

    gates = result.get("quality_gates") or {}
    lines.extend(
        [
            "",
            "## 门禁",
            "",
            f"- typed-only K线: {gates.get('typed_only_market_data')}",
            f"- 当前行情行: {gates.get('has_current_market_rows')}",
            f"- 证据绑定: {gates.get('has_evidence_bindings')}",
            f"- 公司级近期活动: {gates.get('has_company_recent_activity')}",
            f"- 直接研报证据: {gates.get('has_direct_report_evidence')}",
            f"- 直接研报证据标的数: {gates.get('direct_report_evidence_company_count')} / {gates.get('min_direct_evidence_companies')}",
            f"- 可用证据样本数: {gates.get('useful_evidence_sample_count')}",
            "- 本摘要只用于本机研究和模拟组合，不构成投资建议或交易指令。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a daily actionable research summary from typed K-line bars, reports, evidence, and industry-chain positions.")
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--source-a", default=DEFAULT_SOURCE_A)
    parser.add_argument("--source-u", default=DEFAULT_SOURCE_U)
    parser.add_argument("--data-type", default="eod")
    parser.add_argument("--top-limit", type=int, default=12)
    parser.add_argument("--current-row-limit", type=int, default=50000)
    parser.add_argument("--history-rows", type=int, default=20)
    parser.add_argument("--recent-days", type=int, default=7)
    parser.add_argument("--min-direct-evidence-companies", type=int, default=1)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--markdown-output", default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    result = build_daily_market_insight(
        dsn=args.dsn,
        as_of_date=args.as_of_date,
        source_a=args.source_a,
        source_u=args.source_u,
        data_type=args.data_type,
        top_limit=max(1, args.top_limit),
        current_row_limit=max(1, args.current_row_limit),
        history_rows=max(1, args.history_rows),
        recent_days=max(1, args.recent_days),
        min_direct_evidence_companies=max(0, args.min_direct_evidence_companies),
    )
    _write_json(args.output, result)
    _write_text(args.markdown_output, build_markdown(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result.get("passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        raise
