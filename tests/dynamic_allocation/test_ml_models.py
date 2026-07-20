from __future__ import annotations

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from app.dynamic_allocation.models import (
    HiddenMarkovRegimeClassifier,
    LinearAllocationModel,
    MarketRegime,
    TreeAllocationModel,
    WalkForwardModelComparator,
    dependency_status,
)


def training_rows(count: int = 30) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = date(2020, 1, 1)
    regimes = list(MarketRegime)
    buckets = (0.10, 0.30, 0.50, 0.70, 0.90)
    for index in range(count):
        bucket_index = index % len(buckets)
        market_return = (bucket_index - 2) * 0.003 + (0.001 if index % 2 else -0.0005)
        rows.append({
            "date": start + timedelta(days=index),
            "trend": 10.0 + bucket_index * 20 + index * 0.01,
            "credit": 15.0 + bucket_index * 18,
            "regime": regimes[bucket_index].value,
            "target_equity_weight": buckets[bucket_index],
            "returns": {"SPY": market_return, "QQQ": market_return * 1.1, "SGOV": 0.0001},
        })
    return rows


class MLModelTests(unittest.TestCase):
    def test_ridge_and_logistic_emit_probabilities_and_explanations(self) -> None:
        rows = training_rows()
        for kind in ("ridge", "logistic"):
            with self.subTest(kind=kind):
                model = LinearAllocationModel(("trend", "credit"), kind=kind, random_state=7).fit(rows)
                prediction = model.predict(rows[-1])
                self.assertIn(prediction.target_equity_weight, (0.10, 0.30, 0.50, 0.70, 0.90))
                self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0, places=6)
                self.assertEqual(set(prediction.contributions), {"trend", "credit"})
                self.assertIn(kind, prediction.explanation)
                self.assertTrue(prediction.paper_only)
                self.assertFalse(prediction.live_execution_allowed)

    def test_tree_adapters_are_lazy_and_explain_predictions(self) -> None:
        rows = training_rows()
        for kind in ("xgboost", "lightgbm"):
            with self.subTest(kind=kind):
                model = TreeAllocationModel(("trend", "credit"), kind=kind, random_state=7)
                self.assertTrue(model.availability.available)
                prediction = model.fit(rows).predict(rows[-1])
                self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0, places=6)
                self.assertIn(kind, prediction.explanation)
                self.assertIn("global feature importances", prediction.diagnostics[0])

    def test_dependency_unavailability_is_explicit_and_does_not_import(self) -> None:
        model = TreeAllocationModel(("trend",), kind="xgboost")
        with patch("app.dynamic_allocation.models.regime_ml.util.find_spec", return_value=None):
            self.assertFalse(model.availability.available)
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                model.fit(training_rows(10))
        self.assertTrue(dependency_status("sklearn").available)

    def test_markov_approximation_outputs_state_probabilities_and_diagnostics(self) -> None:
        model = HiddenMarkovRegimeClassifier(("trend", "credit")).fit(training_rows())
        prediction = model.predict({"trend": 92.0, "credit": 88.0})
        self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0, places=6)
        self.assertIn(prediction.regime.value, prediction.probabilities)
        self.assertIn("Markov approximation", prediction.explanation)
        self.assertIn("backend=gaussian_markov_approximation", prediction.diagnostics)
        self.assertEqual(set(prediction.feature_drivers), {"trend", "credit"})

    def test_comparator_is_chronological_and_retains_baseline_when_unstable(self) -> None:
        rows = training_rows(24)
        observed_training_maxima: list[date] = []

        class UnstableCandidate:
            name = "unstable"

            def fit(self, train):
                observed_training_maxima.append(max(row["date"] for row in train))
                return self

            def predict(self, row):
                class Prediction:
                    target_equity_weight = 0.90 if int(str(row["date"])[-2:]) % 2 else 0.10
                return Prediction()

        comparator = WalkForwardModelComparator(
            train_size=9, test_size=5, minimum_folds=3,
            minimum_sharpe_improvement=0.01, minimum_improved_fold_ratio=2 / 3,
        )
        result = comparator.compare(
            rows,
            baseline_predict=lambda row: float(row["target_equity_weight"]),
            candidate_factories={"unstable": UnstableCandidate},
        )
        self.assertEqual(result.selected_model, "rule_baseline")
        self.assertFalse(result.candidates["unstable"].eligible_for_promotion)
        self.assertIn("retained", result.explanation)
        test_starts = [rows[index]["date"] for index in (9, 14, 19)]
        self.assertEqual(len(observed_training_maxima), 3)
        self.assertTrue(all(train_end < test_start for train_end, test_start in zip(observed_training_maxima, test_starts)))

    def test_comparator_rejects_unsorted_or_duplicate_dates(self) -> None:
        rows = training_rows(10)
        rows[3]["date"] = rows[2]["date"]
        comparator = WalkForwardModelComparator(train_size=5, test_size=2)
        with self.assertRaisesRegex(ValueError, "unique ascending"):
            comparator.compare(rows, baseline_predict=lambda row: 0.5, candidate_factories={})

    def test_candidate_fold_failure_is_visible_and_cannot_promote(self) -> None:
        class MissingCandidate:
            name = "missing"

            def fit(self, rows):
                raise RuntimeError("optional dependency unavailable")

        result = WalkForwardModelComparator(train_size=9, test_size=5).compare(
            training_rows(24),
            baseline_predict=lambda row: 0.5,
            candidate_factories={"missing": MissingCandidate},
        )
        evaluation = result.candidates["missing"]
        self.assertFalse(evaluation.available)
        self.assertFalse(evaluation.eligible_for_promotion)
        self.assertEqual(len(evaluation.errors), 3)
        self.assertIn("dependency", evaluation.errors[0])


if __name__ == "__main__":
    unittest.main()
