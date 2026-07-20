"""Normalize versioned API payloads into stable dashboard view models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


FACTOR_LABELS = {
    "valuation": "估值",
    "trend": "趋势",
    "volatility": "波动率",
    "credit": "信用",
    "leverage": "杠杆",
    "macro": "宏观",
    "liquidity": "流动性",
    "breadth": "市场宽度",
}

REGIME_LABELS = {
    "risk_on": "Risk On",
    "late_cycle": "Late Cycle",
    "risk_off": "Risk Off",
    "crisis": "Crisis",
    "recovery": "Recovery",
}


@dataclass(slots=True)
class FactorView:
    key: str
    label: str
    score: float | None
    coverage: float | None = None
    freshness: str = "未知"
    contributions: list[dict[str, Any]] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CurrentView:
    as_of: str = "-"
    regime: str = "数据不足"
    equity_allocation: float | None = None
    allocations: dict[str, float] = field(default_factory=dict)
    freshness: str = "未知"
    factors: list[FactorView] = field(default_factory=list)
    caps: dict[str, float | None] = field(default_factory=dict)
    kelly_input: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    config_hash: str = "-"
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False
    trace_id: str = ""


def first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def as_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def as_allocation(value: Any) -> float | None:
    number = as_number(value)
    if number is None:
        return None
    return number / 100.0 if number > 1.0 else number


def normalize_regime(value: Any) -> str:
    raw = str(value or "数据不足").strip()
    key = raw.lower().replace("-", "_").replace(" ", "_")
    return REGIME_LABELS.get(key, raw)


def as_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def normalize_current(payload: Mapping[str, Any]) -> CurrentView:
    decision = first(payload, "decision", "current", "snapshot", default={})
    if not isinstance(decision, Mapping):
        decision = {}
    merged = dict(payload)
    merged.update(decision)
    allocation_block = first(merged, "allocations", "target_allocations", "weights", default={})
    allocations = {
        str(key).upper(): normalized
        for key, value in (allocation_block.items() if isinstance(allocation_block, Mapping) else [])
        if (normalized := as_allocation(value)) is not None
    }
    equity = as_allocation(first(merged, "target_equity_allocation", "equity_allocation", "target_equity", "equity_weight"))
    if equity is None and allocations:
        equity = sum(value for key, value in allocations.items() if key != "SGOV")

    factor_payload = first(merged, "factors", "factor_scores", "factor_results", default=[])
    factors: list[FactorView] = []
    if isinstance(factor_payload, Mapping):
        factor_items = []
        for key, value in factor_payload.items():
            row = dict(value) if isinstance(value, Mapping) else {"score": value}
            row.setdefault("name", key)
            factor_items.append(row)
    else:
        factor_items = as_rows(factor_payload)
    for row in factor_items:
        key = str(first(row, "name", "factor", "factor_name", "key", default="unknown")).strip().lower()
        coverage = as_number(first(row, "coverage", "coverage_ratio"))
        if coverage is not None and coverage <= 1:
            coverage *= 100
        contributions = as_rows(first(row, "contributions", "components", default=[]))
        provenance = as_rows(first(row, "provenance", "sources", default=[]))
        if not provenance:
            provenance = [
                {
                    "observation_id": first(item, "observation_id", default="-"),
                    "available_at": first(item, "available_at", default="-"),
                    "status": first(item, "status", default="-"),
                }
                for item in contributions
                if first(item, "observation_id", "available_at")
            ]
        factors.append(
            FactorView(
                key=key,
                label=FACTOR_LABELS.get(key, key.replace("_", " ").title()),
                score=as_number(first(row, "score", "factor_score")),
                coverage=coverage,
                freshness=str(first(row, "freshness", "freshness_status", "status", default="未知")),
                contributions=contributions,
                provenance=provenance,
                warnings=[str(item) for item in first(row, "warnings", default=[]) or []],
            )
        )
    factor_order = {key: index for index, key in enumerate(FACTOR_LABELS)}
    factors.sort(key=lambda item: factor_order.get(item.key, len(factor_order)))

    cap_payload = first(merged, "caps", "allocation_caps", "risk_limits", default={})
    if not isinstance(cap_payload, Mapping):
        cap_payload = {}
    caps: dict[str, float | None] = {}
    for key, aliases in {
        "评分仓位": ("score_allocation", "scored_allocation", "base_allocation"),
        "Kelly cap": ("kelly_cap", "kelly_position"),
        "Risk cap": ("risk_cap", "risk_limit"),
        "Maximum": ("maximum_allocation", "max_allocation"),
        "最终仓位": ("final_allocation", "recommended_position", "target_equity_allocation"),
    }.items():
        value = first(cap_payload, *aliases)
        if value is None:
            value = first(merged, *aliases)
        caps[key] = as_allocation(value)

    warnings = first(merged, "warnings", "risk_warnings", "alerts", default=[])
    normalized_warnings = []
    for item in warnings or []:
        if isinstance(item, Mapping):
            normalized_warnings.append(str(first(item, "message", "description", "type", default="风险警告")))
        else:
            normalized_warnings.append(str(item))
    freshness = first(merged, "freshness", "data_freshness", default="未知")
    if isinstance(freshness, Mapping):
        freshness = first(freshness, "status", "label", "overall", default="未知")
    if freshness == "未知" and isinstance(merged.get("data_health"), Mapping):
        health = merged["data_health"]
        freshness = "ready" if bool(health.get("ready_for_factor_calculation")) else "incomplete"
    raw_kelly_input = first(merged, "kelly_input", default={})
    kelly_input = dict(raw_kelly_input) if isinstance(raw_kelly_input, Mapping) else {}

    return CurrentView(
        as_of=str(first(merged, "as_of", "timestamp", "decision_time", default="-")),
        regime=normalize_regime(first(merged, "market_regime", "regime", "regime_label", default="数据不足")),
        equity_allocation=equity,
        allocations=allocations,
        freshness=str(freshness),
        factors=factors,
        caps=caps,
        kelly_input=kelly_input,
        warnings=normalized_warnings,
        config_hash=str(first(merged, "config_hash", "configuration_hash", default="-")),
        paper_only=bool(first(merged, "paper_only", default=True)),
        live_execution_allowed=bool(first(merged, "live_execution_allowed", default=False)),
        broker_connected=bool(first(merged, "broker_connected", default=False)),
        trace_id=str(first(payload, "trace_id", default="")),
    )


def normalize_history(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = first(payload, "items", "rows", "history", "decisions", default=[])
    rows = []
    for item in as_rows(source):
        allocation = as_allocation(first(item, "target_equity_allocation", "equity_allocation", "target_equity", "allocation"))
        rows.append(
            {
                "timestamp": str(first(item, "as_of", "timestamp", "date", "decision_time", default="-")),
                "regime": normalize_regime(first(item, "market_regime", "regime", "regime_label", default="-")),
                "equity_allocation": allocation,
                "nav": as_number(first(item, "nav", "equity", "portfolio_value")),
                "config_hash": str(first(item, "config_hash", default="-")),
            }
        )
    return rows


def normalize_health(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = first(payload, "series", "items", "rows", "data_health", default=[])
    rows = []
    for item in as_rows(source):
        rows.append(
            {
                "序列": str(first(item, "series_id", "series", "name", default="-")),
                "来源": str(first(item, "source", "source_id", "provider", default="-")),
                "观察日": str(first(item, "observation_date", "timestamp", default="-")),
                "发布日期": str(first(item, "release_date", default="-")),
                "可用时间": str(first(item, "available_at", "available_time", default="-")),
                "Vintage": str(first(item, "vintage", "vintage_id", "vintage_date", default="-")),
                "Freshness": str(first(item, "freshness", "freshness_status", "status", default="未知")),
                "Proxy": "是" if bool(first(item, "proxy", "is_proxy", default=False)) else "否",
            }
        )
    return rows


def normalize_backtest_runs(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    source = first(payload, "items", "runs", "backtests", default=[])
    rows = []
    for item in as_rows(source):
        run_id = str(first(item, "run_id", "id", default="")).strip()
        if not run_id:
            continue
        rows.append(
            {
                "run_id": run_id,
                "created_at": str(first(item, "created_at", "as_of", "timestamp", default="-")),
                "status": str(first(item, "status", default="-")),
            }
        )
    return rows


def normalize_backtest(payload: Mapping[str, Any]) -> dict[str, Any]:
    run = first(payload, "run", "backtest", default={})
    merged = dict(payload)
    if isinstance(run, Mapping):
        merged.update(run)
    result = merged.get("result")
    if not isinstance(result, Mapping):
        result = {}
    metrics = first(merged, "metrics", "summary")
    if metrics is None:
        metrics = first(result, "metrics", "summary", default={})
    if not isinstance(metrics, Mapping):
        metrics = {}
    curves = first(merged, "curves", "equity_curves", default={})
    if not isinstance(curves, Mapping):
        curves = {}
    normalized_curves = {str(key): as_rows(value) for key, value in curves.items()}
    points = as_rows(first(result, "points", default=[]))
    if not normalized_curves and points:
        normalized_curves["strategy"] = [
            {
                "date": first(point, "as_of", "date", "timestamp"),
                "nav": first(point, "equity_curve", "nav", "equity"),
            }
            for point in points
        ]
    drawdown = as_rows(first(merged, "drawdown", "drawdowns", "drawdown_curve", default=[]))
    if not drawdown and points:
        drawdown = [
            {
                "date": first(point, "as_of", "date", "timestamp"),
                "value": first(point, "drawdown"),
            }
            for point in points
            if first(point, "drawdown") is not None
        ]
    benchmarks = first(merged, "benchmark_metrics")
    if benchmarks is None:
        benchmarks = first(result, "benchmark_metrics", default={})
    if not isinstance(benchmarks, Mapping):
        benchmarks = {}
    stress = first(merged, "stress_periods")
    if stress is None:
        stress = first(result, "stress_periods", default=[])
    if isinstance(stress, Mapping):
        stress_rows = [
            {"period": str(period), **(dict(detail) if isinstance(detail, Mapping) else {"value": detail})}
            for period, detail in stress.items()
        ]
    else:
        stress_rows = as_rows(stress)
    return {
        "run_id": str(first(merged, "run_id", "id", default="-")),
        "status": str(first(merged, "status", default="未知")),
        "metrics": dict(metrics),
        "benchmark_metrics": {str(key): dict(value) for key, value in benchmarks.items() if isinstance(value, Mapping)},
        "curves": normalized_curves,
        "drawdown": drawdown,
        "stress_periods": stress_rows,
        "leakage_checks": as_rows(first(merged, "leakage_checks", "pit_checks", default=[])),
        "warnings": [str(item) for item in first(merged, "warnings", default=[]) or []],
    }
