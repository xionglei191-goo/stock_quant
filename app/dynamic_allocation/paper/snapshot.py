"""Validated, deterministic paper-allocation decision snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "dynamic-allocation-paper-snapshot/v1"
USAGE_BOUNDARY = "paper_only_dynamic_allocation_research_no_broker_no_orders"
ALLOWED_ASSETS = frozenset({"SPY", "QQQ", "SGOV"})
ALLOWED_REGIMES = frozenset({"risk_on", "late_cycle", "risk_off", "crisis", "recovery"})


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _stable_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot fields must be finite JSON values") from exc


def _aware(value: Any, name: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _weight(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise ValueError(f"{name} must be finite and within 0-1")
    return parsed


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


@dataclass(frozen=True, slots=True)
class PaperDecisionSnapshot:
    run_id: str
    as_of: str
    evaluated_at: str
    data_observations: tuple[dict[str, Any], ...]
    factors: dict[str, dict[str, Any]]
    model: dict[str, Any]
    risk: dict[str, Any]
    allocation: dict[str, float]
    config: dict[str, Any]
    explanation: tuple[str, ...]
    warnings: tuple[str, ...]
    schema_version: str = SCHEMA_VERSION
    classification: str = "local-only"
    acceptable_for_non_local_release_gate: bool = False
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False
    order_execution_allowed: bool = False
    usage_boundary: str = USAGE_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "as_of": self.as_of,
            "evaluated_at": self.evaluated_at,
            "classification": self.classification,
            "acceptable_for_non_local_release_gate": self.acceptable_for_non_local_release_gate,
            "paper_only": self.paper_only,
            "live_execution_allowed": self.live_execution_allowed,
            "broker_connected": self.broker_connected,
            "order_execution_allowed": self.order_execution_allowed,
            "usage_boundary": self.usage_boundary,
            "data_observations": list(self.data_observations),
            "factors": self.factors,
            "model": self.model,
            "risk": self.risk,
            "allocation": self.allocation,
            "config": self.config,
            "explanation": list(self.explanation),
            "warnings": list(self.warnings),
        }


def build_paper_snapshot(payload: Mapping[str, Any]) -> PaperDecisionSnapshot:
    """Validate and normalize one replayable as-of decision.

    ``evaluated_at`` defaults to ``as_of`` so the same research payload always
    receives the same run id. Runtime append timestamps live in the repository
    envelope and are deliberately excluded from the decision identity.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("snapshot payload must be an object")
    _assert_paper_boundary(payload)
    as_of = _aware(payload.get("as_of"), "as_of")
    evaluated_at = _aware(payload.get("evaluated_at", as_of), "evaluated_at")
    if evaluated_at < as_of:
        raise ValueError("evaluated_at cannot precede as_of")

    observations = _normalize_observations(payload.get("data_observations"), as_of)
    observation_ids = {row["observation_id"] for row in observations}
    factors = _normalize_factors(payload.get("factors"), as_of, observation_ids)
    model = _normalize_model(_required_mapping(payload, "model"))
    risk = _normalize_risk(_required_mapping(payload, "risk"), model)
    allocation = _normalize_allocation(_required_mapping(payload, "allocation"), risk["final_allocation"])
    config = _normalize_config(_required_mapping(payload, "config"))
    mismatched = sorted(name for name, factor in factors.items() if factor["config_hash"] != config["hash"])
    if mismatched:
        raise ValueError(f"factor config_hash differs from decision config: {', '.join(mismatched)}")
    explanation = tuple(str(item).strip() for item in payload.get("explanation", ()) if str(item).strip())
    if not explanation:
        raise ValueError("at least one decision explanation is required")
    warnings = tuple(str(item).strip() for item in payload.get("warnings", ()) if str(item).strip())

    identity = {
        "schema_version": SCHEMA_VERSION,
        "as_of": _iso(as_of),
        "evaluated_at": _iso(evaluated_at),
        "data_observations": observations,
        "factors": factors,
        "model": model,
        "risk": risk,
        "allocation": allocation,
        "config": config,
        "explanation": list(explanation),
        "warnings": list(warnings),
        "usage_boundary": USAGE_BOUNDARY,
    }
    run_id = "dap_" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:24]
    return PaperDecisionSnapshot(
        run_id=run_id,
        as_of=_iso(as_of),
        evaluated_at=_iso(evaluated_at),
        data_observations=tuple(observations),
        factors=factors,
        model=model,
        risk=risk,
        allocation=allocation,
        config=config,
        explanation=explanation,
        warnings=warnings,
    )


def _assert_paper_boundary(payload: Mapping[str, Any]) -> None:
    if payload.get("classification", "local-only") != "local-only":
        raise ValueError("classification must remain local-only")
    if payload.get("acceptable_for_non_local_release_gate", False) is not False:
        raise ValueError("local paper evidence is not acceptable for non-local release gates")
    if payload.get("paper_only", True) is not True:
        raise ValueError("paper_only must remain true")
    for key in ("live_execution_allowed", "broker_connected", "order_execution_allowed"):
        if payload.get(key, False) is not False:
            raise ValueError(f"{key} must remain false")


def _normalize_observations(value: Any, as_of: datetime) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        raise ValueError("data_observations must be a non-empty array")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("each data observation must be an object")
        observation_id = str(raw.get("observation_id", "")).strip()
        series_id = str(raw.get("series_id", "")).strip()
        if not observation_id or not series_id:
            raise ValueError("data observations require observation_id and series_id")
        if observation_id in seen:
            raise ValueError(f"duplicate observation_id: {observation_id}")
        available_at = _aware(raw.get("available_at"), f"observation {observation_id} available_at")
        if available_at > as_of:
            raise ValueError(f"future observation is unavailable as of decision time: {observation_id}")
        row = _stable_copy(dict(raw))
        row["observation_id"] = observation_id
        row["series_id"] = series_id
        row["available_at"] = _iso(available_at)
        rows.append(row)
        seen.add(observation_id)
    return sorted(rows, key=lambda item: (item["series_id"], item["available_at"], item["observation_id"]))


def _normalize_factors(value: Any, as_of: datetime, observation_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("factors must be a non-empty object")
    result: dict[str, dict[str, Any]] = {}
    for raw_name, raw in sorted(value.items(), key=lambda item: str(item[0])):
        name = str(raw_name).strip()
        if not name or not isinstance(raw, Mapping):
            raise ValueError("each factor must be a named object")
        score = raw.get("score")
        if score is not None:
            try:
                score_value = float(score)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"factor {name} score must be numeric or null") from exc
            if not math.isfinite(score_value) or not 0 <= score_value <= 100:
                raise ValueError(f"factor {name} score must be within 0-100 or null")
        factor_as_of = _aware(raw.get("as_of", as_of), f"factor {name} as_of")
        if factor_as_of > as_of:
            raise ValueError(f"factor {name} uses a future as_of")
        if raw.get("data_cutoff_at") is not None:
            cutoff = _aware(raw["data_cutoff_at"], f"factor {name} data_cutoff_at")
            if cutoff > as_of:
                raise ValueError(f"factor {name} uses a future data cutoff")
        refs = [str(item).strip() for item in raw.get("source_observation_ids", ())]
        unknown = sorted({item for item in refs if item and item not in observation_ids})
        if unknown:
            raise ValueError(f"factor {name} references unknown observations: {', '.join(unknown)}")
        normalized = _stable_copy(dict(raw))
        normalized["as_of"] = _iso(factor_as_of)
        if raw.get("data_cutoff_at") is not None:
            normalized["data_cutoff_at"] = _iso(_aware(raw["data_cutoff_at"], f"factor {name} data_cutoff_at"))
        normalized["source_observation_ids"] = sorted(set(item for item in refs if item))
        if not str(normalized.get("version", "")).strip():
            raise ValueError(f"factor {name} requires version")
        if not str(normalized.get("config_hash", "")).strip():
            raise ValueError(f"factor {name} requires config_hash")
        result[name] = normalized
    return result


def _normalize_model(raw: Mapping[str, Any]) -> dict[str, Any]:
    _assert_paper_boundary(raw)
    result = _stable_copy(dict(raw))
    for key in ("name", "version", "regime", "explanation"):
        if not str(result.get(key, "")).strip():
            raise ValueError(f"model requires {key}")
    if str(result["regime"]) not in ALLOWED_REGIMES:
        raise ValueError("model regime is not one of the five supported states")
    try:
        raw_score = float(result.get("raw_equity_score"))
    except (TypeError, ValueError) as exc:
        raise ValueError("model.raw_equity_score must be numeric") from exc
    if not math.isfinite(raw_score) or not 0 <= raw_score <= 100:
        raise ValueError("model.raw_equity_score must be within 0-100")
    result["raw_equity_score"] = raw_score
    result["bucket_equity_weight"] = _weight(result.get("bucket_equity_weight"), "model.bucket_equity_weight")
    if not any(abs(result["bucket_equity_weight"] - item) <= 1e-9 for item in (0.10, 0.30, 0.50, 0.70, 0.90)):
        raise ValueError("model.bucket_equity_weight must use a 10/30/50/70/90 bucket")
    result["requested_allocation"] = _weight(result.get("requested_allocation"), "model.requested_allocation")
    if result["requested_allocation"] > result["bucket_equity_weight"] + 1e-9:
        raise ValueError("model.requested_allocation cannot exceed its score bucket")
    return result


def _normalize_risk(raw: Mapping[str, Any], model: Mapping[str, Any]) -> dict[str, Any]:
    _assert_paper_boundary(raw)
    result = _stable_copy(dict(raw))
    for key in ("risk_cap", "maximum_allocation", "final_allocation"):
        result[key] = _weight(result.get(key), f"risk.{key}")
    kelly = result.get("kelly_cap")
    result["kelly_cap"] = None if kelly is None else _weight(kelly, "risk.kelly_cap")
    for key in ("binding_limit", "explanation"):
        if not str(result.get(key, "")).strip():
            raise ValueError(f"risk requires {key}")
    component_caps = result.get("component_caps")
    if not isinstance(component_caps, Mapping) or not component_caps:
        raise ValueError("risk.component_caps must preserve the named risk limits")
    result["component_caps"] = {
        str(name): _weight(value, f"risk.component_caps.{name}")
        for name, value in sorted(component_caps.items(), key=lambda item: str(item[0]))
    }
    kelly_details = result.get("kelly")
    if not isinstance(kelly_details, Mapping):
        raise ValueError("risk.kelly must preserve fractional-Kelly inputs and explanation")
    fraction = str(kelly_details.get("fraction", ""))
    if fraction not in {"quarter", "half"}:
        raise ValueError("risk.kelly fraction must be quarter or half; full Kelly is prohibited")
    if not str(kelly_details.get("explanation", "")).strip():
        raise ValueError("risk.kelly requires an explanation")
    available = kelly_details.get("available")
    if available is not True and available is not False:
        raise ValueError("risk.kelly.available must be boolean")
    if available and result["kelly_cap"] is None:
        raise ValueError("available Kelly result requires risk.kelly_cap")
    if not available and result["kelly_cap"] is not None:
        raise ValueError("unavailable Kelly result must not set risk.kelly_cap")
    candidates = [float(model["requested_allocation"]), result["risk_cap"], result["maximum_allocation"]]
    if result["kelly_cap"] is not None:
        candidates.append(result["kelly_cap"])
    expected = min(candidates)
    if abs(result["final_allocation"] - expected) > 1e-9:
        raise ValueError("risk.final_allocation must equal min(requested, Kelly if available, risk, maximum)")
    return result


def _normalize_allocation(raw: Mapping[str, Any], final_equity: float) -> dict[str, float]:
    assets = {str(key).upper(): _weight(value, f"allocation.{key}") for key, value in raw.items()}
    unsupported = sorted(set(assets) - ALLOWED_ASSETS)
    if unsupported:
        raise ValueError(f"unsupported phase-one allocation assets: {', '.join(unsupported)}")
    if set(assets) != ALLOWED_ASSETS:
        raise ValueError("allocation must contain exactly SPY, QQQ, and SGOV")
    if abs(sum(assets.values()) - 1.0) > 1e-9:
        raise ValueError("allocation weights must sum to one")
    if abs(assets["SPY"] + assets["QQQ"] - final_equity) > 1e-9:
        raise ValueError("SPY plus QQQ must equal risk.final_allocation")
    return dict(sorted(assets.items()))


def _normalize_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    result = _stable_copy(dict(raw))
    if not str(result.get("version", "")).strip() or not str(result.get("hash", "")).strip():
        raise ValueError("config requires version and hash")
    return result
