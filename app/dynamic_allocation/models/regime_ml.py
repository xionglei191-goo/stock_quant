"""Explainable, optional-dependency ML candidates for dynamic allocation.

These models are research candidates.  They only emit one of the five paper
allocation buckets and cannot bypass the portfolio risk layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module, util
import math
from typing import Mapping, Sequence

from .allocation_score import AllocationScorer
from .regime_rules import MarketRegime


BUCKETS = AllocationScorer.BUCKETS
REGIMES = tuple(MarketRegime)


@dataclass(frozen=True)
class DependencyStatus:
    package: str
    available: bool
    detail: str


@dataclass(frozen=True)
class CandidatePrediction:
    target_equity_weight: float
    probabilities: dict[float, float]
    contributions: dict[str, float]
    explanation: str
    model_name: str
    diagnostics: tuple[str, ...] = ()
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


@dataclass(frozen=True)
class MarkovRegimePrediction:
    regime: MarketRegime
    probabilities: dict[str, float]
    feature_drivers: dict[str, float]
    explanation: str
    diagnostics: tuple[str, ...]
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


def dependency_status(package: str) -> DependencyStatus:
    available = util.find_spec(package) is not None
    return DependencyStatus(package, available, "available for lazy import" if available else "not installed")


class LinearAllocationModel:
    """Ridge or multinomial-logistic five-bucket allocation candidate."""

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        kind: str = "ridge",
        random_state: int = 17,
        alpha: float = 1.0,
    ) -> None:
        if kind not in {"ridge", "logistic"}:
            raise ValueError("kind must be ridge or logistic")
        if not feature_names:
            raise ValueError("feature_names cannot be empty")
        self.feature_names = tuple(feature_names)
        self.kind = kind
        self.random_state = random_state
        self.alpha = float(alpha)
        self._model = None
        self._scaler = None
        self._residual_scale = 0.15
        self._classes: tuple[float, ...] = ()

    @property
    def name(self) -> str:
        return self.kind

    @property
    def availability(self) -> DependencyStatus:
        return dependency_status("sklearn")

    def fit(self, rows: Sequence[Mapping[str, object]]) -> "LinearAllocationModel":
        if not self.availability.available:
            raise RuntimeError("scikit-learn is unavailable; linear candidate was not fitted")
        x, y = _training_arrays(rows, self.feature_names)
        if len(x) < 3:
            raise ValueError("at least three chronological training rows are required")
        preprocessing = import_module("sklearn.preprocessing")
        self._scaler = preprocessing.StandardScaler().fit(x)
        scaled = self._scaler.transform(x)
        if self.kind == "ridge":
            model_cls = import_module("sklearn.linear_model").Ridge
            self._model = model_cls(alpha=self.alpha).fit(scaled, y)
            residuals = [actual - predicted for actual, predicted in zip(y, self._model.predict(scaled))]
            self._residual_scale = max(0.05, math.sqrt(sum(item * item for item in residuals) / len(residuals)))
        else:
            model_cls = import_module("sklearn.linear_model").LogisticRegression
            labels = [_bucket_index(value) for value in y]
            if len(set(labels)) < 2:
                raise ValueError("logistic candidate requires at least two allocation classes")
            self._model = model_cls(C=1.0 / max(self.alpha, 1e-9), max_iter=500, random_state=self.random_state).fit(scaled, labels)
            self._classes = tuple(BUCKETS[int(value)] for value in self._model.classes_)
        return self

    def predict(self, row: Mapping[str, object]) -> CandidatePrediction:
        self._require_fitted()
        vector = [[_finite_feature(row, name) for name in self.feature_names]]
        scaled = self._scaler.transform(vector)
        if self.kind == "ridge":
            raw = float(self._model.predict(scaled)[0])
            probabilities = _distance_probabilities(raw, self._residual_scale)
            coefficients = [float(value) for value in self._model.coef_]
        else:
            values = [float(value) for value in self._model.predict_proba(scaled)[0]]
            probabilities = {bucket: 0.0 for bucket in BUCKETS}
            probabilities.update(dict(zip(self._classes, values)))
            winning_class = int(self._model.predict(scaled)[0])
            class_index = list(self._model.classes_).index(winning_class)
            coefficients = [float(value) for value in self._model.coef_[class_index]]
        target = max(probabilities, key=probabilities.get)
        contributions = {
            name: round(float(scaled[0][index]) * coefficients[index], 6)
            for index, name in enumerate(self.feature_names)
        }
        top = sorted(contributions.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
        explanation = (
            f"{self.kind} candidate selects {target:.0%}; probability={probabilities[target]:.3f}; "
            f"largest standardized drivers: " + ", ".join(f"{name}={value:+.3f}" for name, value in top)
        )
        return CandidatePrediction(target, _rounded_probabilities(probabilities), contributions, explanation, self.name)

    def _require_fitted(self) -> None:
        if self._model is None or self._scaler is None:
            raise RuntimeError(f"{self.kind} candidate must be fitted before prediction")


class TreeAllocationModel:
    """Lazy XGBoost or LightGBM five-bucket classifier candidate."""

    PACKAGES = {"xgboost": "xgboost", "lightgbm": "lightgbm"}

    def __init__(self, feature_names: Sequence[str], *, kind: str, random_state: int = 17) -> None:
        if kind not in self.PACKAGES:
            raise ValueError("kind must be xgboost or lightgbm")
        if not feature_names:
            raise ValueError("feature_names cannot be empty")
        self.feature_names = tuple(feature_names)
        self.kind = kind
        self.random_state = random_state
        self._model = None
        self._classes: tuple[float, ...] = ()

    @property
    def name(self) -> str:
        return self.kind

    @property
    def availability(self) -> DependencyStatus:
        return dependency_status(self.PACKAGES[self.kind])

    def fit(self, rows: Sequence[Mapping[str, object]]) -> "TreeAllocationModel":
        status = self.availability
        if not status.available:
            raise RuntimeError(f"{status.package} is unavailable; {self.kind} candidate was not fitted")
        x, y = _training_arrays(rows, self.feature_names)
        labels = [_bucket_index(value) for value in y]
        classes = sorted(set(labels))
        if len(x) < 5 or len(classes) < 2:
            raise ValueError("tree candidates require five rows and at least two allocation classes")
        remap = {original: index for index, original in enumerate(classes)}
        mapped = [remap[value] for value in labels]
        if self.kind == "xgboost":
            cls = import_module("xgboost").XGBClassifier
            self._model = cls(
                n_estimators=24, max_depth=2, learning_rate=0.08, subsample=1.0,
                colsample_bytree=1.0, random_state=self.random_state, n_jobs=1,
                objective="multi:softprob", eval_metric="mlogloss",
            )
        else:
            cls = import_module("lightgbm").LGBMClassifier
            self._model = cls(
                n_estimators=24, max_depth=2, learning_rate=0.08, random_state=self.random_state,
                n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True,
            )
        self._model.fit(x, mapped)
        self._classes = tuple(BUCKETS[original] for original in classes)
        return self

    def predict(self, row: Mapping[str, object]) -> CandidatePrediction:
        if self._model is None:
            raise RuntimeError(f"{self.kind} candidate must be fitted before prediction")
        vector = [[_finite_feature(row, name) for name in self.feature_names]]
        values = [float(value) for value in self._model.predict_proba(vector)[0]]
        probabilities = {bucket: 0.0 for bucket in BUCKETS}
        probabilities.update(dict(zip(self._classes, values)))
        target = max(probabilities, key=probabilities.get)
        importances = [float(value) for value in self._model.feature_importances_]
        contributions = {
            name: round(importances[index] * abs(float(vector[0][index])), 6)
            for index, name in enumerate(self.feature_names)
        }
        top = sorted(contributions.items(), key=lambda item: item[1], reverse=True)[:3]
        explanation = (
            f"{self.kind} candidate selects {target:.0%}; probability={probabilities[target]:.3f}; "
            "global-importance weighted drivers: " + ", ".join(f"{name}={value:.3f}" for name, value in top)
        )
        diagnostics = ("tree contributions are global feature importances, not causal effects",)
        return CandidatePrediction(
            target, _rounded_probabilities(probabilities), contributions, explanation, self.name, diagnostics
        )


class HiddenMarkovRegimeClassifier:
    """Stable Gaussian Markov-state approximation with explicit diagnostics.

    The state prototypes are estimated from labelled historical regimes and a
    smoothed transition matrix.  This deterministic approximation is preferred
    to pretending that a numerically failed tiny-sample HMM fit succeeded.
    """

    def __init__(self, feature_names: Sequence[str], *, smoothing: float = 1.0) -> None:
        if not feature_names:
            raise ValueError("feature_names cannot be empty")
        if smoothing <= 0:
            raise ValueError("smoothing must be positive")
        self.feature_names = tuple(feature_names)
        self.smoothing = float(smoothing)
        self._means: dict[MarketRegime, tuple[float, ...]] = {}
        self._variances: tuple[float, ...] = ()
        self._transitions: dict[MarketRegime, dict[MarketRegime, float]] = {}
        self._last_regime: MarketRegime | None = None
        self._diagnostics: tuple[str, ...] = ()

    @property
    def availability(self) -> DependencyStatus:
        return dependency_status("statsmodels")

    def fit(self, rows: Sequence[Mapping[str, object]], *, regime_key: str = "regime") -> "HiddenMarkovRegimeClassifier":
        if len(rows) < 5:
            raise ValueError("Markov regime approximation requires at least five rows")
        grouped: dict[MarketRegime, list[list[float]]] = {regime: [] for regime in REGIMES}
        sequence: list[MarketRegime] = []
        all_vectors: list[list[float]] = []
        for row in rows:
            regime = _row_regime(row, regime_key)
            vector = [_finite_feature(row, name) for name in self.feature_names]
            grouped[regime].append(vector)
            sequence.append(regime)
            all_vectors.append(vector)
        observed = [regime for regime in REGIMES if grouped[regime]]
        if len(observed) < 2:
            raise ValueError("Markov regime approximation requires at least two observed regimes")
        global_mean = tuple(sum(row[i] for row in all_vectors) / len(all_vectors) for i in range(len(self.feature_names)))
        self._means = {
            regime: tuple(sum(row[i] for row in grouped[regime]) / len(grouped[regime]) for i in range(len(self.feature_names)))
            for regime in observed
        }
        self._variances = tuple(
            max(1.0, sum((row[i] - global_mean[i]) ** 2 for row in all_vectors) / len(all_vectors))
            for i in range(len(self.feature_names))
        )
        counts = {source: {target: self.smoothing for target in observed} for source in observed}
        for source, target in zip(sequence, sequence[1:]):
            counts[source][target] += 1.0
        self._transitions = {
            source: {target: value / sum(targets.values()) for target, value in targets.items()}
            for source, targets in counts.items()
        }
        self._last_regime = sequence[-1]
        backend_note = "statsmodels available" if self.availability.available else "statsmodels unavailable"
        missing = [regime.value for regime in REGIMES if regime not in observed]
        self._diagnostics = (
            "backend=gaussian_markov_approximation",
            backend_note,
            f"observed_states={len(observed)}",
            f"unobserved_states={','.join(missing) if missing else 'none'}",
        )
        return self

    def predict(self, row: Mapping[str, object]) -> MarkovRegimePrediction:
        if not self._means or self._last_regime is None:
            raise RuntimeError("Markov regime approximation must be fitted before prediction")
        vector = [_finite_feature(row, name) for name in self.feature_names]
        log_scores: dict[MarketRegime, float] = {}
        for regime, mean in self._means.items():
            distance = sum((vector[i] - mean[i]) ** 2 / self._variances[i] for i in range(len(vector)))
            transition = self._transitions.get(self._last_regime, {}).get(regime, self.smoothing)
            log_scores[regime] = -0.5 * distance + math.log(max(transition, 1e-12))
        peak = max(log_scores.values())
        exp_scores = {regime: math.exp(value - peak) for regime, value in log_scores.items()}
        total = sum(exp_scores.values())
        probabilities = {regime.value: value / total for regime, value in exp_scores.items()}
        selected = max(self._means, key=lambda regime: probabilities[regime.value])
        mean = self._means[selected]
        drivers = {
            name: round((vector[i] - mean[i]) / math.sqrt(self._variances[i]), 6)
            for i, name in enumerate(self.feature_names)
        }
        top = sorted(drivers.items(), key=lambda item: abs(item[1]), reverse=True)[:3]
        explanation = (
            f"Markov approximation selects {selected.value} with probability {probabilities[selected.value]:.3f}; "
            "largest prototype deviations: " + ", ".join(f"{name}={value:+.3f}" for name, value in top)
        )
        return MarkovRegimePrediction(
            selected, {key: round(value, 8) for key, value in probabilities.items()}, drivers,
            explanation, self._diagnostics,
        )


def _training_arrays(
    rows: Sequence[Mapping[str, object]], feature_names: Sequence[str]
) -> tuple[list[list[float]], list[float]]:
    x: list[list[float]] = []
    y: list[float] = []
    for row in rows:
        x.append([_finite_feature(row, name) for name in feature_names])
        target = float(row["target_equity_weight"])
        if not math.isfinite(target):
            raise ValueError("target_equity_weight must be finite")
        y.append(target)
    return x, y


def _finite_feature(row: Mapping[str, object], name: str) -> float:
    value = float(row[name])
    if not math.isfinite(value):
        raise ValueError(f"feature {name} must be finite")
    return value


def _bucket_index(value: float) -> int:
    return min(range(len(BUCKETS)), key=lambda index: abs(BUCKETS[index] - value))


def _distance_probabilities(value: float, scale: float) -> dict[float, float]:
    scores = {bucket: math.exp(-0.5 * ((value - bucket) / scale) ** 2) for bucket in BUCKETS}
    total = sum(scores.values())
    return {bucket: score / total for bucket, score in scores.items()}


def _rounded_probabilities(values: Mapping[float, float]) -> dict[float, float]:
    return {bucket: round(float(values.get(bucket, 0.0)), 8) for bucket in BUCKETS}


def _row_regime(row: Mapping[str, object], regime_key: str) -> MarketRegime:
    if regime_key in row:
        return MarketRegime(str(row[regime_key]))
    target = BUCKETS[_bucket_index(float(row["target_equity_weight"]))]
    mapping = {
        0.10: MarketRegime.CRISIS,
        0.30: MarketRegime.RISK_OFF,
        0.50: MarketRegime.LATE_CYCLE,
        0.70: MarketRegime.RECOVERY,
        0.90: MarketRegime.RISK_ON,
    }
    return mapping[target]
