"""Pure shared normalizer helpers.

Extracted from ``SystemService`` per the SystemService Modularization ADR
(Phase 1: stateless helpers and shared normalizers). Every function here is a
deterministic transform of its arguments only: none touch the store, audit log,
permissions, or any ``SystemService`` state. ``SystemService`` keeps the same
method names as thin facades that delegate here.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..errors import ValidationError
from ..research_reports import safe_source_part


def normalize_hotspot_research_task(
    raw_task: Mapping[str, Any], request: Mapping[str, Any], expansion: Mapping[str, Any]
) -> dict[str, Any]:
    task_type = str(raw_task.get("task_type", raw_task.get("type", "hotspot_research_backfill"))).strip()
    chain_id = str(raw_task.get("chain_id", request.get("seed_chain_id", ""))).strip()
    node_ids = [str(item) for item in raw_task.get("node_ids", [raw_task.get("node_id")]) if item]
    position_id = str(raw_task.get("position_id", "")).strip()
    issuer_id = str(raw_task.get("issuer_id", "")).strip()
    basis = "|".join([task_type, chain_id, position_id, issuer_id, ",".join(node_ids), str(expansion.get("query", ""))])
    task_id = str(raw_task.get("task_id") or f"rtask_{safe_source_part(basis)}").strip()
    return {
        "task_id": task_id,
        "task_type": task_type,
        "source": "hotspot_expansion",
        "issuer_id": issuer_id,
        "chain_id": chain_id,
        "node_ids": node_ids,
        "position_id": position_id,
        "required_slots": [str(item) for item in raw_task.get("required_slots", [])],
        "reason": str(raw_task.get("reason", "")),
        "status": "open",
        "priority": int(raw_task.get("priority", 70 if task_type == "company_position_backfill" else 55)),
        "metadata": {
            "query": expansion.get("query", ""),
            "seed_theme_id": request.get("seed_theme_id", ""),
            "seed_chain_id": request.get("seed_chain_id", ""),
            "usage_boundary": "macro_industry_chain_research_only_not_trade_signal",
        },
    }


def normalize_scores_with_caps(scores: Mapping[str, float], caps: Mapping[str, float]) -> dict[str, float]:
    result = {security_id: 0.0 for security_id in scores}
    active = {security_id for security_id, cap in caps.items() if cap > 0}
    remaining = min(1.0, sum(caps[security_id] for security_id in active))
    base = {security_id: max(0.0, float(scores.get(security_id, 0.0))) for security_id in scores}
    if sum(base[security_id] for security_id in active) <= 0:
        base = {security_id: 1.0 for security_id in active}
    while active and remaining > 0:
        total = sum(base.get(security_id, 0.0) for security_id in active)
        if total <= 0:
            break
        capped = False
        for security_id in list(active):
            proposed = remaining * base.get(security_id, 0.0) / total
            if proposed > caps[security_id]:
                result[security_id] = caps[security_id]
                remaining -= caps[security_id]
                active.remove(security_id)
                capped = True
        if not capped:
            for security_id in active:
                result[security_id] = remaining * base.get(security_id, 0.0) / total
            break
    return result


def normalize_tdx_symbol(symbol: str) -> str:
    """Normalize a TDX symbol to a bare 6-digit A-share code.
    Handles these real-world formats (T-403):
    - sh600000, sz000001, bj430047   (TDX internal prefix)
    - 600000.SH, 000001.SZ           (common Chinese data vendor)
    - 600000.SS, 000001.SHG, SZE     (Reuters/Refinitiv/Bloomberg variants)
    - 600000.XSHG, 000001.XSHE       (ISO MIC suffix)
    - CN0000000000 / CN000000xxx      (ISIN style — extract 6-digit code)
    """
    value = str(symbol).strip()
    # Handle ISIN-style (12 chars starting with CN)
    if re.match(r'^CN\d{10}$', value, re.IGNORECASE):
        return value[-6:]
    value = value.lower()
    # Strip exchange prefixes: sh/sz/bj
    value = re.sub(r'^(sh|sz|bj)', '', value)
    # Strip common exchange suffixes
    value = re.sub(r'\.(sh|sz|bj|ss|shg|sze|sse|szse|xshg|xshe|xbei)$', '', value)
    # Keep only digits
    return re.sub(r'\D+', '', value)


def normalize_gold_bbox(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        x = float(value.get("x", 0) or 0)
        y = float(value.get("y", 0) or 0)
        if "width" in value or "height" in value:
            width = float(value.get("width", 0) or 0)
            height = float(value.get("height", 0) or 0)
        else:
            width = float(value.get("right", value.get("x2", x)) or x) - x
            height = float(value.get("bottom", value.get("y2", y)) or y) - y
        return {"x": x, "y": y, "width": max(0.0, width), "height": max(0.0, height)}
    if isinstance(value, list) and len(value) >= 4:
        x1, y1, x2, y2 = [float(item or 0) for item in value[:4]]
        return {"x": x1, "y": y1, "width": max(0.0, x2 - x1), "height": max(0.0, y2 - y1)}
    return {}


def normalize_data_health_status(status: str) -> str:
    value = str(status or "").strip().lower()
    if value in {"executed", "completed", "passed", "success", "ok", "active"}:
        return "success"
    if value in {"partial", "retrying"}:
        return "partial"
    if value in {"failed", "error", "invalid"}:
        return "failed"
    if value in {"dry_run", "planned"}:
        return "planned"
    if value in {"skipped", "not_found", "inactive"}:
        return "skipped"
    if value in {"running", "pending"}:
        return "running"
    return value or "unknown"


def normalize_13f_report_period(payload: Mapping[str, Any], rows: list[Mapping[str, Any]]) -> str:
    del rows
    for field in ("report_period", "period_of_report", "report_date"):
        value = str(payload.get(field, "")).strip()
        if not value:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        compact = re.sub(r"[^0-9]", "", value)
        if len(compact) == 8:
            return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    raise ValidationError("13F report_period must use YYYY-MM-DD")


def normalize_transaction_side(value: Any, *, signed_quantity: Any = None) -> str:
    raw = str(value or "").strip().lower()
    if not raw and signed_quantity is not None:
        try:
            return "sell" if float(signed_quantity) < 0 else "buy"
        except (TypeError, ValueError):
            pass
    if raw in {"buy", "b", "long", "open_long", "1", "+1"}:
        return "buy"
    if raw in {"sell", "s", "short", "close_long", "-1"}:
        return "sell"
    raise ValidationError("transaction side must map to buy or sell")


def normalize_transaction_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValidationError("transaction row requires trade_date")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw[:10]):
        return raw[:10]
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 8:
        digits = digits[:8]
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    raise ValidationError("transaction trade_date must be YYYY-MM-DD or YYYYMMDD")


def normalize_relationship_entity_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n,.;:：，。；、()（）")
    cleaned = re.sub(r"\b(the|a|an|our|its|their|major|key)\b\s+", "", cleaned, flags=re.IGNORECASE).strip()
    if len(cleaned) < 2 or len(cleaned) > 80:
        return ""
    blocked = {"customer", "supplier", "partner", "subsidiary", "shareholder", "holder", "controller", "investee", "company", "group", "客户", "供应商", "合作伙伴", "子公司", "股东", "持有人", "实控人", "实际控制人", "参股"}
    if cleaned.lower() in blocked:
        return ""
    return cleaned


def normalize_us_backfill_symbol(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "", str(value or "").strip().upper())


def normalize_cusip(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def unique_strings(values: Any) -> list[str]:
    """Return input values as trimmed strings, de-duplicated, order-preserving."""
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
