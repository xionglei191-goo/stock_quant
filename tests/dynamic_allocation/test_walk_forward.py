from __future__ import annotations

from datetime import date, timedelta
import unittest

from app.dynamic_allocation.backtest import BacktestEngine, WalkForwardBacktester, performance_metrics
from app.dynamic_allocation.portfolio import RebalancePolicy


def row(day: date, spy: float, *, target: float | None = None, feature: float = 0.0) -> dict[str, object]:
    value: dict[str, object] = {
        "date": day, "returns": {"SPY": spy, "QQQ": spy, "SGOV": 0.0}, "feature": feature,
    }
    if target is not None:
        value["target_equity_weight"] = target
    return value


class BacktestTests(unittest.TestCase):
    def test_close_signal_executes_on_next_observation(self) -> None:
        start = date(2020, 1, 1)
        engine = BacktestEngine(rebalance_policy=RebalancePolicy(no_trade_buffer=0.0, maximum_step=1.0))
        result = engine.run([
            row(start, 1.0, target=0.90),
            {**row(start + timedelta(days=1), 0.10, target=0.10), "scheduled_rebalance": True},
            {**row(start + timedelta(days=2), -0.10), "scheduled_rebalance": True},
        ], initial_equity_weight=0.10)
        self.assertAlmostEqual(result.points[0].return_value, 0.10)
        self.assertEqual(result.points[0].signal_as_of, None)
        self.assertEqual(result.points[1].signal_as_of, start)
        self.assertAlmostEqual(result.points[1].return_value, 0.09)
        self.assertAlmostEqual(result.points[2].return_value, -0.01)

    def test_default_rebalance_is_monthly_and_step_limited(self) -> None:
        result = BacktestEngine().run([
            row(date(2020, 1, 30), 0.0, target=0.90),
            row(date(2020, 1, 31), 0.0, target=0.90),
            row(date(2020, 2, 3), 0.0, target=0.90),
        ], initial_equity_weight=0.10)
        self.assertEqual(result.points[1].applied_equity_weight, 0.10)
        self.assertEqual(result.points[2].applied_equity_weight, 0.25)

    def test_metrics_benchmarks_stress_and_proxy_disclosure(self) -> None:
        start = date(2020, 2, 1)
        rows = [row(start + timedelta(days=index), value, target=0.50) for index, value in enumerate((0.01, -0.02, 0.03, 0.01))]
        rows[0]["cash_is_proxy"] = True
        rows[0]["cash_proxy_name"] = "3-month Treasury total-return proxy before SGOV inception"
        result = BacktestEngine(transaction_cost_bps=5).run(rows)
        self.assertEqual(set(result.metrics), {"cagr", "annual_return", "maximum_drawdown", "sharpe", "sortino", "calmar", "win_rate", "turnover"})
        self.assertEqual(set(result.benchmark_metrics), {"spy_buy_hold", "spy_sgov_60_40", "qqq_buy_hold", "spy_200ma"})
        self.assertTrue(result.stress_periods["2020"]["available"])
        self.assertFalse(result.stress_periods["2008"]["available"])
        self.assertIn("3-month Treasury", result.proxy_disclosures[0])
        self.assertTrue(result.paper_only)

    def test_walk_forward_fit_never_sees_test_or_future_rows(self) -> None:
        start = date(2023, 1, 1)
        rows = [row(start + timedelta(days=index), 0.001, feature=float(index)) for index in range(10)]
        observed_training_maxima: list[float] = []

        def fit(train):
            maximum = max(float(item["feature"]) for item in train)
            observed_training_maxima.append(maximum)
            return lambda item: 0.10 if float(item["feature"]) > maximum else 0.90

        result = WalkForwardBacktester().run(rows, train_size=4, test_size=2, fit=fit)
        self.assertEqual(observed_training_maxima, [3.0, 5.0, 7.0])
        self.assertEqual(len(result.folds), 3)
        self.assertEqual(len(result.backtest.points), 6)
        for fold in result.folds:
            self.assertLess(fold.train_end, fold.test_start)

    def test_metric_drawdown_sign_and_turnover(self) -> None:
        metrics = performance_metrics([0.10, -0.20, 0.05], turnover=0.25)
        self.assertLess(metrics["maximum_drawdown"], 0)
        self.assertEqual(metrics["turnover"], 0.25)


if __name__ == "__main__":
    unittest.main()
