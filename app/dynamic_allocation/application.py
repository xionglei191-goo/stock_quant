from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .backtest.engine import BacktestEngine
from .backtest.benchmarks import benchmark_returns
from .config import DynamicAllocationConfig, load_config
from .contracts import PointInTimeObservation, ensure_aware
from .data.quality import DataQualityService
from .data.repository import SQLiteObservationRepository
from .factors.base import (
    ComponentSpec,
    ConfiguredPercentileFactorCalculator,
    FactorContext,
    HistoricalValue,
    SeriesSnapshot,
)
from .models.allocation_score import AllocationScorer
from .models.regime_rules import RuleRegimeClassifier
from .portfolio.allocation import AllocationPolicy
from .paper import build_paper_snapshot
from .records import SQLiteAllocationRecordRepository
from .risk.estimator import HistoricalReturnKellyEstimator
from .risk.kelly import FractionalKellySizer
from .risk.limits import RiskLimitPolicy


ROOT = Path(__file__).resolve().parents[2]


class DynamicAllocationApplication:
    """Application boundary for PIT evaluation, research backtests and audit records."""

    def __init__(
        self,
        *,
        config_path: str | Path | None = None,
        observation_repository: Any | None = None,
        record_repository: SQLiteAllocationRecordRepository | None = None,
    ) -> None:
        self.config_path = Path(config_path or ROOT / "config" / "dynamic_allocation.yaml")
        self.config: DynamicAllocationConfig = load_config(self.config_path)
        database_path = Path(os.getenv(
            "AI_QUANT_DYNAMIC_ALLOCATION_DB",
            str(ROOT / "data" / "local" / "dynamic_allocation.sqlite"),
        ))
        self.observations = observation_repository or SQLiteObservationRepository(database_path)
        self.records = record_repository or SQLiteAllocationRecordRepository(database_path)
        self.factor_models = self._build_factor_models()

    def ingest(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_rows = payload.get("observations", [])
        if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
            raise ValueError("observations must be a list")
        rows = [self._observation(item) for item in raw_rows]
        unknown = sorted({row.series_id for row in rows} - set(self.config.series))
        if unknown:
            raise ValueError(f"series not registered in config: {', '.join(unknown)}")
        mismatched = sorted(
            row.series_id for row in rows
            if self.config.series[row.series_id].source_id != row.source_id
        )
        if mismatched:
            raise ValueError(f"source_id differs from governed registry: {', '.join(mismatched)}")
        result = self.observations.upsert(rows)
        return {**asdict(result), "config_hash": self.config.config_hash, **self._boundary()}

    def data_health(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        as_of = self._as_of(body.get("as_of"))
        requested = body.get("series_ids")
        series_ids = tuple(str(item) for item in requested) if isinstance(requested, list) else None
        unknown = sorted(set(series_ids or ()) - set(self.config.series))
        if unknown:
            raise ValueError(f"unknown configured series: {', '.join(unknown)}")
        return DataQualityService(self.observations, self.config).evaluate(as_of, series_ids).to_dict()

    def evaluate(self, payload: Mapping[str, Any] | None = None, *, persist: bool = False) -> dict[str, Any]:
        body = payload or {}
        as_of = self._as_of(body.get("as_of"))
        context = self._factor_context(as_of)
        results = [model.calculate(context) for model in self.factor_models]
        factors = [result.to_dict() for result in results]
        warnings = [
            f"{result.name}: factor unavailable ({result.freshness_status}, coverage {result.coverage_ratio:.0%})"
            for result in results if not result.ready
        ]
        scores = {result.name: result.score for result in results if result.ready and result.score is not None}
        required = set(self._model_config("allocation", "weights", default={}))
        data_health = self.data_health({"as_of": as_of.isoformat()})
        health_ready = bool(data_health["ready_for_factor_calculation"])
        ready = bool(required) and required.issubset(scores) and health_ready
        base: dict[str, Any] = {
            "as_of": as_of.isoformat(),
            "factors": factors,
            "data_health": data_health,
            "config_hash": self.config.config_hash,
            "model_version": "rules-v1",
            "warnings": list(dict.fromkeys(warnings)),
            "ready": ready,
            **self._boundary(),
        }
        if not ready:
            missing = sorted(required - set(scores))
            health_failures = [
                item["series_id"]
                for item in data_health["series"]
                if item["critical"] and item["status"] != "fresh"
            ]
            reasons = []
            if missing:
                reasons.append(f"unavailable factors {', '.join(missing)}")
            if health_failures:
                reasons.append(f"critical data health {', '.join(health_failures)}")
            base.update({
                "market_regime": None,
                "target_equity_allocation": None,
                "allocations": {},
                "caps": {},
                "explanation": f"decision blocked: {'; '.join(reasons) or 'data readiness failed'}",
            })
            base["warnings"].append(base["explanation"])
            return base

        rule = self._model_config("regime", default={})
        regime = RuleRegimeClassifier(
            minimum_residence_periods=int(rule.get("minimum_residence_periods", 2)),
            transition_margin=float(rule.get("transition_margin", 5)),
        ).classify(scores)
        allocation_config = self._model_config("allocation", default={})
        scored = AllocationScorer(allocation_config.get("weights", {})).score(scores, regime.regime)
        kelly_config = self._model_config("kelly", default={})
        kelly_input = self._kelly_input(body, as_of, kelly_config)
        base["warnings"] = list(dict.fromkeys([*base["warnings"], *kelly_input.get("warnings", [])]))
        kelly = FractionalKellySizer(str(kelly_config.get("fraction", "quarter"))).continuous(
            expected_return=self._optional_float(kelly_input.get("expected_return")),
            volatility=self._optional_float(kelly_input.get("volatility")),
            confidence=self._optional_float(kelly_input.get("confidence")),
            sample_size=int(kelly_input["sample_size"]) if kelly_input.get("sample_size") is not None else None,
            minimum_samples=int(kelly_config.get("minimum_samples", 24)),
        )
        risk_config = self._model_config("risk", default={})
        decision = RiskLimitPolicy(maximum_allocation=float(risk_config.get("maximum_allocation", 0.9))).decide(
            scored.target_equity_weight,
            kelly=kelly,
            permanent_loss_cap=float(body.get("permanent_loss_cap", 1.0)),
            asset_cap=float(body.get("asset_cap", 1.0)),
            correlation_cap=float(body.get("correlation_cap", 1.0)),
            data_quality_cap=float(body.get("data_quality_cap", 1.0)),
        )
        policy = AllocationPolicy(
            spy_share=float(allocation_config.get("spy_share", 0.7)),
            qqq_share=float(allocation_config.get("qqq_share", 0.3)),
        )
        assets = policy.allocate(decision.final_allocation, require_bucket=False)
        source_ids = sorted({
            *{item for result in results for item in result.source_observation_ids},
            *{str(item) for item in kelly_input.get("source_observation_ids", [])},
        })
        source_series = {item.series_id for model in self.factor_models for item in model.components}
        if kelly_input.get("series_id"):
            source_series.add(str(kelly_input["series_id"]))
        source_rows = {
            row.observation_id: row
            for row in self.observations.history_available(
                sorted(source_series), as_of
            )
            if row.observation_id in source_ids
        }
        paper_snapshot = build_paper_snapshot({
            "as_of": as_of.isoformat(),
            "data_observations": [
                {
                    "observation_id": row.observation_id,
                    "series_id": row.series_id,
                    "observation_date": row.observation_date.isoformat(),
                    "release_date": row.release_date.isoformat(),
                    "available_at": row.available_at.isoformat(),
                    "vintage_date": row.vintage_date.isoformat(),
                    "source_id": row.source_id,
                    "source_uri": row.source_uri,
                    "rights_tag": row.rights_tag,
                    "quality_flags": list(row.quality_flags),
                }
                for row in source_rows.values()
            ],
            "factors": {result.name: result.to_dict() for result in results},
            "model": {
                "name": "rule_regime", "version": "rules-v1", "regime": regime.regime.value,
                "raw_equity_score": scored.raw_score, "bucket_equity_weight": scored.score_bucket,
                "requested_allocation": scored.target_equity_weight, "explanation": scored.explanation,
            },
            "risk": {
                "kelly_cap": decision.kelly_cap, "risk_cap": decision.risk_cap,
                "maximum_allocation": decision.maximum_allocation, "final_allocation": decision.final_allocation,
                "binding_limit": decision.binding_limit, "component_caps": decision.component_caps,
                "kelly": self._jsonable(asdict(kelly)), "kelly_input": kelly_input,
                "explanation": decision.explanation,
            },
            "allocation": assets.weights,
            "config": {"version": self.config.version, "hash": self.config.config_hash},
            "explanation": [regime.explanation, scored.explanation, decision.explanation],
            "warnings": list(dict.fromkeys([*base["warnings"], *decision.warnings])),
        })
        decision_id = paper_snapshot.run_id
        base.update({
            "decision_id": decision_id,
            "market_regime": regime.regime.value,
            "regime": self._jsonable(asdict(regime)),
            "target_equity_allocation": decision.final_allocation,
            "allocations": assets.weights,
            "caps": {
                "score_allocation": scored.target_equity_weight,
                "kelly_cap": decision.kelly_cap,
                "risk_cap": decision.risk_cap,
                "maximum_allocation": decision.maximum_allocation,
                "final_allocation": decision.final_allocation,
                "binding_limit": decision.binding_limit,
            },
            "kelly": self._jsonable(asdict(kelly)),
            "kelly_input": kelly_input,
            "risk": self._jsonable(asdict(decision)),
            "source_observation_ids": source_ids,
            "paper_snapshot": paper_snapshot.to_dict(),
            "explanation": f"{regime.explanation}; {scored.explanation}; {decision.explanation}",
        })
        base["warnings"] = list(dict.fromkeys([*base["warnings"], *decision.warnings]))
        base = self._jsonable(base)
        if persist:
            existing = self.records.get("decision", decision_id)
            if existing is not None:
                return existing
            base["created_at"] = datetime.now(timezone.utc).isoformat()
            self.records.append("decision", decision_id, as_of.isoformat(), base)
        return base

    def history(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        return {"items": self.records.list("decision", limit=int(body.get("limit", 100))), **self._boundary()}

    def run_backtest(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise ValueError("backtest rows are required")
        result = BacktestEngine(transaction_cost_bps=float(payload.get("transaction_cost_bps", 0))).run(rows)
        plain = self._jsonable(asdict(result))
        curves: dict[str, list[dict[str, Any]]] = {
            "strategy": [
                {"date": point.as_of.isoformat(), "nav": point.equity_curve}
                for point in result.points
            ]
        }
        for name, returns in benchmark_returns(rows).items():
            nav = 1.0
            curve = []
            for row, value in zip(rows, returns):
                nav *= 1 + float(value)
                curve.append({"date": str(row.get("date", row.get("as_of"))), "nav": nav})
            curves[name] = curve
        material = json.dumps({
            "rows": rows,
            "transaction_cost_bps": float(payload.get("transaction_cost_bps", 0)),
            "config_hash": self.config.config_hash,
        }, sort_keys=True, default=str, separators=(",", ":"))
        run_id = "dyn_backtest_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
        existing = self.records.get("backtest", run_id)
        if existing is not None:
            return existing
        record = {
            "run_id": run_id,
            "as_of": self._as_of(payload.get("as_of")).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": plain,
            "metrics": plain["metrics"],
            "benchmark_metrics": plain["benchmark_metrics"],
            "curves": curves,
            "drawdown": [
                {"date": point.as_of.isoformat(), "value": point.drawdown}
                for point in result.points
            ],
            "stress_periods": plain["stress_periods"],
            "leakage_checks": [{
                "check": "signal_t_applies_t_plus_1",
                "passed": all(point.signal_as_of is None or point.signal_as_of < point.as_of for point in result.points),
            }],
            "warnings": list(plain["proxy_disclosures"]),
            "config_hash": self.config.config_hash,
            **self._boundary(),
        }
        self.records.append("backtest", run_id, record["as_of"], record)
        return record

    def get_backtest(self, run_id: str) -> dict[str, Any] | None:
        return self.records.get("backtest", run_id)

    def backtests(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = payload or {}
        records = self.records.list("backtest", limit=int(body.get("limit", 50)))
        items = [
            {
                "run_id": record.get("run_id"),
                "as_of": record.get("as_of"),
                "created_at": record.get("created_at"),
                "metrics": record.get("metrics", {}),
                "paper_only": True,
            }
            for record in records
        ]
        return {"items": items, **self._boundary()}

    def _factor_context(self, as_of: datetime) -> FactorContext:
        required = sorted({item.series_id for model in self.factor_models for item in model.components})
        rows = self.observations.history_available(required, as_of)
        by_series: dict[str, list[PointInTimeObservation]] = {}
        for row in rows:
            by_series.setdefault(row.series_id, []).append(row)
        snapshots: dict[str, SeriesSnapshot] = {}
        for series_id, history in by_series.items():
            latest = history[-1]
            snapshots[series_id] = SeriesSnapshot(
                latest.value, latest.available_at, latest.observation_id,
                tuple(HistoricalValue(row.value, row.available_at, row.observation_id) for row in history),
                latest.quality_flags,
            )
        return FactorContext(as_of, snapshots, self.config.config_hash)

    def _build_factor_models(self) -> list[ConfiguredPercentileFactorCalculator]:
        raw = self.config.raw.get("factors", {})
        if not isinstance(raw, Mapping) or not raw:
            raise ValueError("factor configuration is required")
        models: list[ConfiguredPercentileFactorCalculator] = []
        for name, item in raw.items():
            if not isinstance(item, Mapping):
                raise ValueError(f"factor {name} must be a mapping")
            components = []
            for component in item.get("components", []):
                components.append(ComponentSpec(
                    str(component["series_id"]), float(component["weight"]),
                    str(component.get("direction", "high")), bool(component.get("critical", False)),
                    int(component.get("min_history", 3)),
                    float(component["max_age_days"]) if component.get("max_age_days") is not None else None,
                    float(component["target"]) if component.get("target") is not None else None,
                ))
            models.append(ConfiguredPercentileFactorCalculator(
                str(name), components, version=str(item.get("version", "1.0")),
                minimum_coverage=float(item.get("minimum_coverage", 0.65)),
            ))
        return models

    def _kelly_input(
        self,
        body: Mapping[str, Any],
        as_of: datetime,
        kelly_config: Any,
    ) -> dict[str, Any]:
        expected_return = self._optional_float(body.get("expected_return"))
        volatility = self._optional_float(body.get("volatility"))
        explicit = expected_return is not None or volatility is not None
        if explicit:
            available = expected_return is not None and volatility is not None
            warning = [] if available else ["explicit Kelly input requires both expected_return and volatility"]
            return {
                "available": available,
                "source": "explicit",
                "method": "caller_supplied_continuous_kelly_inputs",
                "series_id": "",
                "expected_return": expected_return,
                "volatility": volatility,
                "confidence": self._optional_float(body.get("confidence")),
                "sample_size": int(body["sample_size"]) if body.get("sample_size") is not None else None,
                "sample_start": None,
                "sample_end": None,
                "source_observation_ids": [],
                "explanation": (
                    "expected return and volatility were explicitly supplied by the caller"
                    if available else "explicit Kelly input is incomplete; no estimated value was mixed in"
                ),
                "warnings": warning,
            }
        estimator_config = kelly_config.get("estimator", {}) if isinstance(kelly_config, Mapping) else {}
        if not isinstance(estimator_config, Mapping) or not bool(estimator_config.get("enabled", False)):
            return {
                "available": False,
                "source": "unavailable",
                "method": "disabled",
                "series_id": "",
                "expected_return": None,
                "volatility": None,
                "confidence": None,
                "sample_size": None,
                "sample_start": None,
                "sample_end": None,
                "source_observation_ids": [],
                "explanation": "historical Kelly input estimator is disabled",
                "warnings": ["historical Kelly input estimator is disabled"],
            }
        estimator = HistoricalReturnKellyEstimator(
            series_id=str(estimator_config.get("series_id", "return_3m")),
            lookback_years=int(estimator_config.get("lookback_years", 10)),
            minimum_samples=int(kelly_config.get("minimum_samples", 24)),
            confidence=float(estimator_config.get("confidence", 0.35)),
            expected_return_floor=float(estimator_config.get("expected_return_floor", -0.10)),
            expected_return_cap=float(estimator_config.get("expected_return_cap", 0.12)),
            volatility_floor=float(estimator_config.get("volatility_floor", 0.08)),
        )
        rows = self.observations.history_available([estimator.series_id], as_of)
        return self._jsonable(asdict(estimator.estimate(rows, as_of=as_of)))

    def _model_config(self, name: str, child: str | None = None, *, default: Any) -> Any:
        models = self.config.raw.get("models", {})
        value = models.get(name, default) if isinstance(models, Mapping) else default
        if child is not None:
            return value.get(child, default) if isinstance(value, Mapping) else default
        return value

    @staticmethod
    def _as_of(value: Any) -> datetime:
        if value is None or value == "":
            return datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return ensure_aware(parsed, "as_of")

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None or value == "" else float(value)

    @staticmethod
    def _boundary() -> dict[str, bool]:
        return {"paper_only": True, "live_execution_allowed": False, "broker_connected": False}

    @staticmethod
    def _observation(raw: Any) -> PointInTimeObservation:
        if not isinstance(raw, Mapping):
            raise ValueError("each observation must be a mapping")
        available_at = DynamicAllocationApplication._as_of(raw.get("available_at"))
        release_date = date.fromisoformat(str(raw["release_date"]))
        observation_date = date.fromisoformat(str(raw["observation_date"]))
        payload_hash = str(raw.get("payload_hash", "")) or hashlib.sha256(
            json.dumps(dict(raw), sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return PointInTimeObservation(
            observation_id=str(raw["observation_id"]), series_id=str(raw["series_id"]),
            observation_date=observation_date, value=float(raw["value"]), release_date=release_date,
            available_at=available_at,
            vintage_date=date.fromisoformat(str(raw.get("vintage_date", release_date.isoformat()))),
            revision_seq=int(raw.get("revision_seq", 0)), source_id=str(raw["source_id"]),
            source_uri=str(raw.get("source_uri", "")), rights_tag=dict(raw.get("rights_tag", {})),
            quality_flags=tuple(raw.get("quality_flags", ())), payload_hash=payload_hash,
        )

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonable(item) for item in value]
        return value
