"""Pure portfolio analytics / risk-math helpers (portfolio domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These are deterministic computations over plain weight/security/position inputs
(group exposure, risk contribution, turnover, stress scenarios, optimizer weight
comparison, valuation risk decomposition). They hold no ``SystemService`` state;
``SystemService`` keeps the same method names as facades that delegate here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from ..errors import ValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import PortfolioProposal


def group_exposure(
    weights: Mapping[str, float],
    securities: Mapping[str, dict[str, Any]],
    group_key: str,
) -> dict[str, float]:
    exposure: dict[str, float] = {}
    for security_id, weight in weights.items():
        group = str(securities[security_id].get(group_key, "unknown"))
        exposure[group] = exposure.get(group, 0.0) + float(weight)
    return {key: round(value, 6) for key, value in sorted(exposure.items())}


def risk_contribution(
    weights: Mapping[str, float],
    securities: Mapping[str, dict[str, Any]],
) -> dict[str, float]:
    raw = {
        security_id: max(0.0, float(weight)) * securities[security_id]["volatility"]
        for security_id, weight in weights.items()
    }
    total = sum(raw.values())
    if total <= 0:
        return {security_id: 0.0 for security_id in weights}
    return {security_id: round(value / total, 6) for security_id, value in raw.items()}


def turnover(weights: Mapping[str, float], current_weights: Any) -> float:
    if not isinstance(current_weights, Mapping):
        return 0.0
    all_ids = set(weights) | {str(key) for key in current_weights}
    total = 0.0
    for security_id in all_ids:
        try:
            current = float(current_weights.get(security_id, 0.0))
        except (TypeError, ValueError):
            current = 0.0
        total += abs(float(weights.get(security_id, 0.0)) - current)
    return total / 2


def stress_report(weights: Mapping[str, float], scenarios: Any) -> list[dict[str, Any]]:
    if not isinstance(scenarios, list):
        return []
    report: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping):
            continue
        shocks = scenario.get("shocks", {})
        if not isinstance(shocks, Mapping):
            continue
        portfolio_return = 0.0
        for security_id, weight in weights.items():
            try:
                portfolio_return += float(weight) * float(shocks.get(security_id, 0.0))
            except (TypeError, ValueError):
                continue
        report.append({"name": str(scenario.get("name", "stress")), "portfolio_return": round(portfolio_return, 6)})
    return report


def weight_comparison_row(
    optimizer_label: str,
    weights: Mapping[str, float],
    reference_weights: Mapping[str, float],
    proposal: "PortfolioProposal",
    *,
    reference_label: str,
) -> dict[str, Any]:
    universe = sorted(set(weights) | set(reference_weights))
    if not universe:
        raise ValidationError("portfolio comparison requires weights")
    candidate = {security_id: max(0.0, float(weights.get(security_id, 0.0))) for security_id in universe}
    reference = {security_id: max(0.0, float(reference_weights.get(security_id, 0.0))) for security_id in universe}
    candidate_total = sum(candidate.values())
    reference_total = sum(reference.values())
    if candidate_total <= 0 or reference_total <= 0:
        raise ValidationError("portfolio comparison requires positive normalized weights")
    candidate = {security_id: value / candidate_total for security_id, value in candidate.items()}
    reference = {security_id: value / reference_total for security_id, value in reference.items()}
    score_source = {
        security_id: float(proposal.posterior_returns.get(security_id, proposal.prior_returns.get(security_id, 0.0)))
        for security_id in universe
    }
    candidate_score = sum(candidate[security_id] * score_source[security_id] for security_id in universe)
    reference_score = sum(reference[security_id] * score_source[security_id] for security_id in universe)
    restricted = {str(item) for item in proposal.constraints.get("restricted_securities", [])}
    max_weight_limit = float(proposal.constraints.get("max_weight", 1.0))
    candidate_restricted_weight = sum(candidate.get(security_id, 0.0) for security_id in restricted)
    candidate_breaches = sorted([security_id for security_id, weight in candidate.items() if weight > max_weight_limit + 1e-6])
    top_security_id = max(candidate, key=candidate.get)
    return {
        "optimizer": optimizer_label,
        "reference": reference_label,
        "security_count": len(candidate),
        "reference_security_count": len(reference),
        "weight_sum": round(sum(candidate.values()), 8),
        "reference_weight_sum": round(sum(reference.values()), 8),
        "top_security_id": top_security_id,
        "top_weight": round(candidate[top_security_id], 8),
        "l1_distance_to_reference": round(sum(abs(candidate[security_id] - reference[security_id]) for security_id in universe) / 2, 8),
        "concentration": round(sum(weight * weight for weight in candidate.values()), 8),
        "expected_return_proxy": round(candidate_score, 8),
        "reference_expected_return_proxy": round(reference_score, 8),
        "expected_return_delta": round(candidate_score - reference_score, 8),
        "restricted_security_weight": round(candidate_restricted_weight, 8),
        "max_weight_limit": round(max_weight_limit, 8),
        "max_weight_breach_count": len(candidate_breaches),
        "max_weight_breach_securities": candidate_breaches,
        "weights": {security_id: round(candidate[security_id], 8) for security_id in universe if candidate[security_id] > 0},
        "reference_weights": {security_id: round(reference[security_id], 8) for security_id in universe if reference[security_id] > 0},
    }


def valuation_risk_decomposition(
    positions: list[dict[str, Any]],
    *,
    cash: float,
    cash_weight: float,
    portfolio_currency: str,
) -> dict[str, Any]:
    group_keys = ["market", "currency", "industry", "style"]
    exposures: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in group_keys}
    for position in positions:
        market_value = float(position.get("market_value", 0.0))
        weight = float(position.get("weight", 0.0))
        for group_key in group_keys:
            group_value = str(position.get(group_key) or "unknown")
            row = exposures[group_key].setdefault(group_value, {"market_value": 0.0, "weight": 0.0, "position_count": 0, "top_position": "", "top_weight": 0.0})
            row["market_value"] += market_value
            row["weight"] += weight
            row["position_count"] += 1
            if weight > float(row["top_weight"]):
                row["top_position"] = str(position.get("security_id", ""))
                row["top_weight"] = weight
    rounded_exposures = {
        group_key: {
            group_value: {
                "market_value": round(values["market_value"], 6),
                "weight": round(values["weight"], 8),
                "position_count": values["position_count"],
                "top_position": values["top_position"],
                "top_weight": round(values["top_weight"], 8),
            }
            for group_value, values in sorted(group_values.items())
        }
        for group_key, group_values in exposures.items()
    }
    sorted_positions = sorted(positions, key=lambda item: float(item.get("weight", 0.0)), reverse=True)
    weights = [float(item.get("weight", 0.0)) for item in positions]
    foreign_currency_weight = sum(float(item.get("weight", 0.0)) for item in positions if str(item.get("currency", "")) != portfolio_currency)
    unclassified = {
        group_key: round(float(rounded_exposures[group_key].get("unclassified", {}).get("weight", 0.0)), 8)
        for group_key in ["industry", "style"]
    }
    return {
        "by_market": rounded_exposures["market"],
        "by_currency": rounded_exposures["currency"],
        "by_industry": rounded_exposures["industry"],
        "by_style": rounded_exposures["style"],
        "cash": {"market_value": round(cash, 6), "weight": cash_weight, "currency": portfolio_currency},
        "concentration": {
            "position_count": len(positions),
            "top_position_weight": round(weights[0], 8) if weights else 0.0,
            "top_5_weight": round(sum(sorted(weights, reverse=True)[:5]), 8),
            "herfindahl_index": round(sum(weight * weight for weight in weights), 8),
        },
        "foreign_currency_weight": round(foreign_currency_weight, 8),
        "unclassified_weight": unclassified,
    }
