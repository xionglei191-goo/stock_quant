"""Pure market-disturbance scan and candidate-pool helpers (daily mainline domain).

Stateless functions only: the daily mainline orchestration facade owns IO
(market reads, persistence, audit) and delegates the candidate selection
judgement here, per AGENTS.md §8.1.

Metric definitions and thresholds are the ones already used by
``scripts/daily_market_insight.py`` (``one_day_return`` 0.07, ``amount_ratio``
3.0, ``volume_ratio`` 3.0, ``intraday_range`` 0.08). No new data source and no
new metric is introduced here: rows are expected to be the derived movers rows
produced by the existing scan (``security_id`` / ``market`` / ``ticker`` /
``issuer_id`` / ``as_of_date`` plus the four derived metrics).

Ranking contract (design §4.2):

- Rows are ordered by the strength tuple ``(|one_day_return|, amount_ratio,
  volume_ratio)`` descending, with ``security_id`` ascending as the final
  tiebreak, so the same input always yields the same output.
- The strength tuple is compared on the *published* (rounded) metric values, so
  ``trigger_strength`` read in ``rank`` order is guaranteed non-increasing.
- ``rank`` is 1..n contiguous and unique after the ``candidate_limit`` total cap
  and the per-market ``market_quota`` are applied.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

# (metric name, inclusive threshold, selection reason text)
TRIGGER_RULES: tuple[tuple[str, float, str], ...] = (
    ("one_day_return", 0.07, "涨跌幅异常"),
    ("amount_ratio", 3.0, "成交额显著放大"),
    ("volume_ratio", 3.0, "成交量显著放大"),
    ("intraday_range", 0.08, "日内振幅较高"),
)

# ``one_day_return`` triggers on its absolute value (a -8% move is a candidate too),
# mirroring ``abs(one_day_return) >= 0.07`` in scripts/daily_market_insight.py.
ABSOLUTE_TRIGGER_METRICS: frozenset[str] = frozenset({"one_day_return"})

# Output precision per metric, identical to the existing scan payload.
METRIC_PRECISION: dict[str, int] = {
    "one_day_return": 8,
    "amount_ratio": 4,
    "volume_ratio": 4,
    "intraday_range": 8,
}

# Ordered ranking components; the tuple built from these decides ``rank``.
RANKING_METRICS: tuple[str, ...] = ("one_day_return", "amount_ratio", "volume_ratio")

SELECTION_REASON_SEPARATOR = "、"


def _safe_float(value: Any) -> float:
    """Coerce any scan value to a finite float (same tolerance as the scan script)."""

    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def derive_disturbance_row(
    latest: Mapping[str, Any],
    *,
    previous_close: Any = 0.0,
    average_volume: Any = 0.0,
    average_amount: Any = 0.0,
    security: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project raw EOD values to the metrics consumed by ``build_candidate_pool``."""

    row = dict(latest) if isinstance(latest, Mapping) else {}
    identity = security if isinstance(security, Mapping) else {}
    close = _safe_float(row.get("close"))
    prior_close = _safe_float(previous_close)
    volume = _safe_float(row.get("volume"))
    amount = _safe_float(row.get("amount"))
    avg_volume = _safe_float(average_volume)
    avg_amount = _safe_float(average_amount)
    one_day_return = close / prior_close - 1.0 if prior_close else 0.0
    intraday_range = (
        (_safe_float(row.get("high")) - _safe_float(row.get("low"))) / prior_close
        if prior_close
        else 0.0
    )
    security_id = str(row.get("security_id") or identity.get("security_id") or "").strip()
    return {
        "security_id": security_id,
        "issuer_id": str(row.get("issuer_id") or identity.get("issuer_id") or "").strip(),
        "ticker": str(row.get("ticker") or identity.get("ticker") or security_id).strip(),
        "market": str(row.get("market") or identity.get("market") or "").strip().upper(),
        "source_id": str(row.get("source_id") or "").strip(),
        "data_type": str(row.get("data_type") or "eod").strip(),
        "as_of_date": str(row.get("as_of_date") or "").strip(),
        "open": _safe_float(row.get("open")),
        "high": _safe_float(row.get("high")),
        "low": _safe_float(row.get("low")),
        "close": close,
        "volume": volume,
        "amount": amount,
        "previous_close": prior_close,
        "avg_volume": round(avg_volume, 4),
        "avg_amount": round(avg_amount, 4),
        "one_day_return": round(one_day_return, 8),
        "volume_ratio": round(volume / avg_volume, 4) if avg_volume else 0.0,
        "amount_ratio": round(amount / avg_amount, 4) if avg_amount else 0.0,
        "intraday_range": round(intraday_range, 8),
    }


def _metric_value(row: Mapping[str, Any], metric: str) -> float:
    """Published value of ``metric``, rounded to the scan payload precision."""

    return round(_safe_float(row.get(metric)), METRIC_PRECISION.get(metric, 8))


def _comparable_value(row: Mapping[str, Any], metric: str) -> float:
    value = _metric_value(row, metric)
    return abs(value) if metric in ABSOLUTE_TRIGGER_METRICS else value


def trigger_matches(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return every triggered rule for ``row`` in ``TRIGGER_RULES`` declaration order."""

    matches: list[dict[str, Any]] = []
    for metric, threshold, reason in TRIGGER_RULES:
        value = _metric_value(row, metric)
        compared = abs(value) if metric in ABSOLUTE_TRIGGER_METRICS else value
        if compared >= threshold:
            matches.append(
                {
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "reason": reason,
                }
            )
    return matches


def trigger_strength(row: Mapping[str, Any]) -> list[float]:
    """Ranking strength tuple ``(|one_day_return|, amount_ratio, volume_ratio)``."""

    return [_comparable_value(row, metric) for metric in RANKING_METRICS]


def _sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, str]:
    strength = trigger_strength(row)
    return (-strength[0], -strength[1], -strength[2], _security_id(row))


def _security_id(row: Mapping[str, Any]) -> str:
    return str(row.get("security_id") or "").strip()


def _market(row: Mapping[str, Any]) -> str:
    return str(row.get("market") or "").strip()


def build_candidate_pool(
    rows: Iterable[Mapping[str, Any]],
    *,
    candidate_limit: int,
    market_quota: int,
) -> list[dict[str, Any]]:
    """Build the daily candidate pool from derived market-disturbance rows.

    Selection: a row is a candidate when at least one ``TRIGGER_RULES`` metric
    reaches its threshold. Rows without ``security_id`` are dropped (nothing
    downstream could bind them) and only the strongest row per ``security_id``
    is kept.

    Caps: ``market_quota`` limits entries per market, ``candidate_limit`` caps
    the whole pool. Both are strict caps, so a non-positive value yields an
    empty pool.

    Every entry carries ``rank`` / ``selection_reason`` / ``trigger_metric`` /
    ``trigger_value`` / ``as_of_date`` / ``security_id`` / ``issuer_id`` /
    ``ticker`` / ``market``; ``rank`` is 1..n contiguous and unique, and
    ``trigger_strength`` is non-increasing in ``rank`` order.
    """

    total_cap = int(candidate_limit)
    per_market_cap = int(market_quota)
    if total_cap <= 0 or per_market_cap <= 0:
        return []

    triggered: list[tuple[Mapping[str, Any], list[dict[str, Any]]]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not _security_id(row):
            continue
        matches = trigger_matches(row)
        if not matches:
            continue
        triggered.append((row, matches))

    triggered.sort(key=lambda item: _sort_key(item[0]))

    pool: list[dict[str, Any]] = []
    seen_securities: set[str] = set()
    market_counts: dict[str, int] = {}
    for row, matches in triggered:
        security_id = _security_id(row)
        if security_id in seen_securities:
            continue
        market = _market(row)
        market_key = market.upper()
        if market_counts.get(market_key, 0) >= per_market_cap:
            continue
        primary = matches[0]
        pool.append(
            {
                "rank": len(pool) + 1,
                "security_id": security_id,
                "issuer_id": str(row.get("issuer_id") or "").strip(),
                "ticker": str(row.get("ticker") or security_id).strip(),
                "market": market,
                "as_of_date": str(row.get("as_of_date") or "").strip(),
                "selection_reason": SELECTION_REASON_SEPARATOR.join(match["reason"] for match in matches),
                "trigger_metric": primary["metric"],
                "trigger_value": primary["value"],
                "trigger_threshold": primary["threshold"],
                "trigger_rules": [dict(match) for match in matches],
                "trigger_strength": trigger_strength(row),
                "metrics": {metric: _metric_value(row, metric) for metric, _threshold, _reason in TRIGGER_RULES},
            }
        )
        seen_securities.add(security_id)
        market_counts[market_key] = market_counts.get(market_key, 0) + 1
        if len(pool) >= total_cap:
            break
    return pool
