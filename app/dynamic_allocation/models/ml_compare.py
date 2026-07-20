"""Deterministic expanding-window comparison and conservative promotion gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, Sequence

from ..backtest.engine import BacktestEngine


class AllocationCandidate(Protocol):
    name: str

    def fit(self, rows: Sequence[Mapping[str, object]]) -> "AllocationCandidate": ...
    def predict(self, row: Mapping[str, object]): ...


@dataclass(frozen=True)
class FoldComparison:
    train_end: object
    test_start: object
    test_end: object
    baseline_sharpe: float
    candidate_sharpe: float
    baseline_maximum_drawdown: float
    candidate_maximum_drawdown: float
    improved: bool


@dataclass(frozen=True)
class CandidateEvaluation:
    name: str
    available: bool
    eligible_for_promotion: bool
    overall_metrics: dict[str, float]
    folds: tuple[FoldComparison, ...]
    improved_fold_ratio: float
    reason: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelComparisonResult:
    selected_model: str
    baseline_metrics: dict[str, float]
    candidates: dict[str, CandidateEvaluation]
    explanation: str
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


class WalkForwardModelComparator:
    """Compare candidates using only expanding-window out-of-sample predictions."""

    def __init__(
        self,
        *,
        train_size: int,
        test_size: int,
        minimum_folds: int = 3,
        minimum_improved_fold_ratio: float = 2 / 3,
        minimum_sharpe_improvement: float = 0.05,
        maximum_drawdown_tolerance: float = 0.01,
        engine_factory: Callable[[], BacktestEngine] = BacktestEngine,
    ) -> None:
        if train_size < 1 or test_size < 1 or minimum_folds < 1:
            raise ValueError("train_size, test_size, and minimum_folds must be positive")
        if not 0 <= minimum_improved_fold_ratio <= 1:
            raise ValueError("minimum_improved_fold_ratio must be within 0-1")
        if minimum_sharpe_improvement < 0 or maximum_drawdown_tolerance < 0:
            raise ValueError("promotion thresholds must be non-negative")
        self.train_size = train_size
        self.test_size = test_size
        self.minimum_folds = minimum_folds
        self.minimum_improved_fold_ratio = minimum_improved_fold_ratio
        self.minimum_sharpe_improvement = minimum_sharpe_improvement
        self.maximum_drawdown_tolerance = maximum_drawdown_tolerance
        self.engine_factory = engine_factory

    def compare(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        baseline_predict: Callable[[Mapping[str, object]], float],
        candidate_factories: Mapping[str, Callable[[], AllocationCandidate]],
    ) -> ModelComparisonResult:
        source = list(rows)
        dates = [BacktestEngine._date(row) for row in source]
        if dates != sorted(dates) or len(dates) != len(set(dates)):
            raise ValueError("comparison rows must have unique ascending dates")
        windows = self._windows(len(source))
        if not windows:
            raise ValueError("insufficient observations for an out-of-sample comparison")
        baseline_rows = self._predicted_rows(source, windows, baseline_predict)
        baseline_metrics = self.engine_factory().run(baseline_rows).metrics
        evaluations: dict[str, CandidateEvaluation] = {}

        for name, factory in candidate_factories.items():
            predicted: list[dict[str, object]] = []
            folds: list[FoldComparison] = []
            errors: list[str] = []
            for train_end, test_end in windows:
                train = tuple(source[:train_end])
                test = source[train_end:test_end]
                try:
                    model = factory().fit(train)
                    candidate_rows = []
                    baseline_fold_rows = []
                    for row in test:
                        candidate_row = dict(row)
                        candidate_row["target_equity_weight"] = float(model.predict(row).target_equity_weight)
                        candidate_rows.append(candidate_row)
                        baseline_row = dict(row)
                        baseline_row["target_equity_weight"] = float(baseline_predict(row))
                        baseline_fold_rows.append(baseline_row)
                    predicted.extend(candidate_rows)
                    candidate_metrics = self.engine_factory().run(candidate_rows).metrics
                    baseline_fold_metrics = self.engine_factory().run(baseline_fold_rows).metrics
                    improved = self._fold_improved(candidate_metrics, baseline_fold_metrics)
                    folds.append(FoldComparison(
                        BacktestEngine._date(train[-1]), BacktestEngine._date(test[0]),
                        BacktestEngine._date(test[-1]), baseline_fold_metrics["sharpe"],
                        candidate_metrics["sharpe"], baseline_fold_metrics["maximum_drawdown"],
                        candidate_metrics["maximum_drawdown"], improved,
                    ))
                except (ImportError, RuntimeError, ValueError) as error:
                    errors.append(f"fold starting {BacktestEngine._date(test[0])}: {error}")
            evaluations[name] = self._evaluate(name, predicted, folds, errors, baseline_metrics)

        eligible = [evaluation for evaluation in evaluations.values() if evaluation.eligible_for_promotion]
        selected = max(eligible, key=lambda item: item.overall_metrics["sharpe"]).name if eligible else "rule_baseline"
        if selected == "rule_baseline":
            explanation = "Rule baseline retained: no complex candidate passed every stability and risk-adjusted OOS gate."
        else:
            explanation = f"{selected} promoted for research use after passing all fixed walk-forward stability gates."
        return ModelComparisonResult(selected, baseline_metrics, evaluations, explanation)

    def _windows(self, count: int) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        start = self.train_size
        while start < count:
            result.append((start, min(start + self.test_size, count)))
            start += self.test_size
        return result

    @staticmethod
    def _predicted_rows(
        source: Sequence[Mapping[str, object]],
        windows: Sequence[tuple[int, int]],
        predictor: Callable[[Mapping[str, object]], float],
    ) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for start, end in windows:
            for row in source[start:end]:
                enriched = dict(row)
                enriched["target_equity_weight"] = float(predictor(row))
                result.append(enriched)
        return result

    def _fold_improved(self, candidate: Mapping[str, float], baseline: Mapping[str, float]) -> bool:
        return (
            candidate["sharpe"] >= baseline["sharpe"] + self.minimum_sharpe_improvement
            and candidate["maximum_drawdown"] >= baseline["maximum_drawdown"] - self.maximum_drawdown_tolerance
        )

    def _evaluate(
        self,
        name: str,
        predicted: list[dict[str, object]],
        folds: list[FoldComparison],
        errors: list[str],
        baseline_metrics: Mapping[str, float],
    ) -> CandidateEvaluation:
        available = bool(predicted) and not errors
        overall = self.engine_factory().run(predicted).metrics if predicted else {}
        ratio = sum(fold.improved for fold in folds) / len(folds) if folds else 0.0
        enough_folds = len(folds) >= self.minimum_folds
        overall_improved = bool(overall) and (
            overall["sharpe"] >= baseline_metrics["sharpe"] + self.minimum_sharpe_improvement
            and overall["maximum_drawdown"] >= baseline_metrics["maximum_drawdown"] - self.maximum_drawdown_tolerance
        )
        eligible = available and enough_folds and ratio >= self.minimum_improved_fold_ratio and overall_improved
        reasons = []
        if errors:
            reasons.append("one or more folds failed or dependency was unavailable")
        if not enough_folds:
            reasons.append(f"needs {self.minimum_folds} successful folds; got {len(folds)}")
        if ratio < self.minimum_improved_fold_ratio:
            reasons.append(f"improved fold ratio {ratio:.3f} below {self.minimum_improved_fold_ratio:.3f}")
        if not overall_improved:
            reasons.append("overall Sharpe/drawdown gate not passed")
        if eligible:
            reasons.append("all OOS stability gates passed")
        return CandidateEvaluation(name, available, eligible, overall, tuple(folds), round(ratio, 6), "; ".join(reasons), tuple(errors))
