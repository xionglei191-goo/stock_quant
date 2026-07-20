from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.dynamic_allocation.dashboard.api_client import (
    DynamicAllocationApiClient,
    DynamicAllocationApiError,
)
from app.dynamic_allocation.dashboard.presentation import (
    normalize_backtest,
    normalize_backtest_runs,
    normalize_current,
    normalize_health,
    normalize_history,
)


class _FixtureHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(
            {
                "path": self.path,
                "actor": self.headers.get("X-Actor", ""),
                "role": self.headers.get("X-Role", ""),
                "authorization": self.headers.get("Authorization", ""),
            }
        )
        if self.path.startswith("/api/dynamic-allocation/current"):
            self._json(
                200,
                {
                    "success": True,
                    "data": {
                        "as_of": "2026-07-17T15:00:00Z",
                        "market_regime": "Recovery",
                        "target_equity_allocation": 0.7,
                        "allocations": {"SPY": 0.35, "QQQ": 0.35, "SGOV": 0.3},
                        "factors": {
                            "valuation": {"score": 68, "coverage": 1.0, "freshness": "fresh"},
                            "trend": {"score": 74, "coverage": 1.0, "freshness": "fresh"},
                        },
                        "caps": {
                            "score_allocation": 0.9,
                            "kelly_cap": 0.7,
                            "risk_cap": 0.7,
                            "maximum_allocation": 0.9,
                            "final_allocation": 0.7,
                        },
                        "config_hash": "sha256:fixture",
                        "freshness": "fresh",
                        "paper_only": True,
                        "live_execution_allowed": False,
                        "broker_connected": False,
                    },
                    "error": None,
                    "trace_id": "trace_current",
                },
            )
            return
        if self.path.startswith("/api/dynamic-allocation/history"):
            self._json(
                200,
                {
                    "success": True,
                    "data": {
                        "items": [
                            {"as_of": "2026-07-01", "regime": "Risk On", "equity_allocation": 0.9, "nav": 1.0},
                            {"as_of": "2026-07-17", "regime": "Recovery", "equity_allocation": 0.7, "nav": 1.02},
                        ]
                    },
                    "error": None,
                    "trace_id": "trace_history",
                },
            )
            return
        if self.path.startswith("/api/dynamic-allocation/data-health"):
            self._json(
                200,
                {
                    "success": True,
                    "data": {
                        "series": [
                            {
                                "series_id": "SPY.close",
                                "source": "governed-market-data",
                                "observation_date": "2026-07-16",
                                "release_date": "2026-07-16",
                                "available_at": "2026-07-16T20:00:00Z",
                                "vintage": "initial",
                                "freshness": "fresh",
                                "proxy": False,
                            }
                        ]
                    },
                    "error": None,
                    "trace_id": "trace_health",
                },
            )
            return
        if self.path.startswith("/api/dynamic-allocation/backtests?"):
            self._json(
                200,
                {
                    "success": True,
                    "data": {"items": [{"run_id": "bt_fixture", "created_at": "2026-07-17T15:00:00Z"}]},
                    "error": None,
                    "trace_id": "trace_backtests",
                },
            )
            return
        if self.path == "/api/dynamic-allocation/backtests/bt_fixture":
            self._json(
                200,
                {
                    "success": True,
                    "data": {
                        "run_id": "bt_fixture",
                        "result": {
                            "metrics": {"cagr": 0.08, "maximum_drawdown": -0.1},
                            "benchmark_metrics": {"spy_buy_hold": {"cagr": 0.07, "maximum_drawdown": -0.2}},
                            "points": [
                                {"as_of": "2026-07-01", "equity_curve": 1.0, "drawdown": 0.0},
                                {"as_of": "2026-07-17", "equity_curve": 1.02, "drawdown": -0.01},
                            ],
                            "stress_periods": {"2020": {"available": True}},
                        },
                    },
                    "error": None,
                    "trace_id": "trace_backtest",
                },
            )
            return
        self._json(
            404,
            {
                "success": False,
                "data": None,
                "error": {"type": "not_found", "message": "run not found"},
                "trace_id": "trace_missing",
            },
        )

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DashboardApiClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _FixtureHandler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_client_unwraps_envelope_and_sends_identity_headers(self) -> None:
        client = DynamicAllocationApiClient(
            self.base_url,
            actor="researcher",
            role="analyst",
            token="local-token",
        )
        payload = client.get_current()
        self.assertEqual(payload["market_regime"], "Recovery")
        self.assertEqual(payload["trace_id"], "trace_current")
        request = _FixtureHandler.requests[-1]
        self.assertEqual(request["actor"], "researcher")
        self.assertEqual(request["role"], "analyst")
        self.assertEqual(request["authorization"], "Bearer local-token")

    def test_history_limit_is_bounded(self) -> None:
        DynamicAllocationApiClient(self.base_url).get_history(limit=99999)
        self.assertIn("limit=2000", _FixtureHandler.requests[-1]["path"])

    def test_backtest_list_limit_is_bounded(self) -> None:
        payload = DynamicAllocationApiClient(self.base_url).get_backtests(limit=99999)
        self.assertIn("limit=200", _FixtureHandler.requests[-1]["path"])
        self.assertEqual(payload["items"][0]["run_id"], "bt_fixture")

    def test_api_error_retains_trace_and_recovery_context(self) -> None:
        with self.assertRaises(DynamicAllocationApiError) as raised:
            DynamicAllocationApiClient(self.base_url).get_backtest("missing")
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.error_type, "not_found")
        self.assertEqual(raised.exception.trace_id, "trace_missing")
        self.assertFalse(raised.exception.retryable)

    def test_invalid_base_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DynamicAllocationApiClient("localhost:8000")


class DashboardPresentationTests(unittest.TestCase):
    def test_current_payload_normalizes_summary_factors_caps_and_boundaries(self) -> None:
        view = normalize_current(
            {
                "as_of": "2026-07-17T15:00:00Z",
                "market_regime": "Recovery",
                "target_equity_allocation": 70,
                "allocations": {"SPY": 0.35, "QQQ": 0.35, "SGOV": 0.30},
                "factors": {
                    "trend": {
                        "score": 72,
                        "coverage_ratio": 0.875,
                        "freshness": "fresh",
                        "components": [{"name": "200ma", "contribution": 12}],
                        "sources": [{"series_id": "SPY.close", "available_at": "2026-07-17"}],
                    },
                    "valuation": 61,
                },
                "caps": {
                    "score_allocation": 0.9,
                    "kelly_cap": 0.7,
                    "risk_cap": 0.7,
                    "maximum_allocation": 0.9,
                    "final_allocation": 0.7,
                },
                "kelly_input": {
                    "source": "estimated",
                    "sample_size": 40,
                    "expected_return": 0.12,
                    "volatility": 0.17,
                },
                "paper_only": True,
                "live_execution_allowed": False,
                "broker_connected": False,
                "config_hash": "sha256:test",
                "trace_id": "trace_test",
                "data_health": {"ready_for_factor_calculation": True},
            }
        )
        self.assertEqual(view.regime, "Recovery")
        self.assertEqual(view.equity_allocation, 0.7)
        self.assertEqual(view.allocations["SGOV"], 0.3)
        self.assertEqual([factor.key for factor in view.factors], ["valuation", "trend"])
        self.assertEqual(view.factors[1].coverage, 87.5)
        self.assertEqual(view.freshness, "ready")
        self.assertEqual(view.caps["Kelly cap"], 0.7)
        self.assertEqual(view.kelly_input["source"], "estimated")
        self.assertEqual(view.kelly_input["sample_size"], 40)
        self.assertTrue(view.paper_only)
        self.assertFalse(view.live_execution_allowed)

    def test_nested_decision_and_missing_factor_remain_explicit(self) -> None:
        view = normalize_current(
            {
                "decision": {
                    "regime": "Risk Off",
                    "equity_weight": 0.3,
                    "factor_results": [{"factor_name": "credit", "score": None, "warnings": ["stale"]}],
                }
            }
        )
        self.assertEqual(view.regime, "Risk Off")
        self.assertEqual(view.equity_allocation, 0.3)
        self.assertIsNone(view.factors[0].score)
        self.assertEqual(view.factors[0].warnings, ["stale"])

    def test_snake_case_regime_uses_stable_display_label(self) -> None:
        self.assertEqual(normalize_current({"market_regime": "late_cycle"}).regime, "Late Cycle")
        self.assertEqual(normalize_current({"market_regime": "risk_on"}).regime, "Risk On")
        history = normalize_history({"items": [{"as_of": "2026-07-17", "regime": "risk_off"}]})
        self.assertEqual(history[0]["regime"], "Risk Off")

    def test_history_health_and_backtest_normalize_aliases(self) -> None:
        history = normalize_history(
            {"decisions": [{"date": "2026-07-01", "regime_label": "Risk On", "allocation": 90, "portfolio_value": 1.04}]}
        )
        self.assertEqual(history[0]["equity_allocation"], 0.9)
        self.assertEqual(history[0]["nav"], 1.04)

        health = normalize_health(
            {
                "items": [
                    {
                        "name": "cpi",
                        "source_id": "FRED",
                        "timestamp": "2026-06-01",
                        "release_date": "2026-07-14",
                        "available_time": "2026-07-14T12:30:00Z",
                        "status": "fresh",
                        "is_proxy": True,
                        "vintage_date": "2026-07-14",
                    }
                ]
            }
        )
        self.assertEqual(health[0]["序列"], "cpi")
        self.assertEqual(health[0]["来源"], "FRED")
        self.assertEqual(health[0]["Vintage"], "2026-07-14")
        self.assertEqual(health[0]["Proxy"], "是")

        backtest = normalize_backtest(
            {
                "run": {
                    "id": "bt_1",
                    "summary": {"cagr": 0.08},
                    "equity_curves": {"strategy": [{"date": "2026-01-01", "nav": 1.0}]},
                    "drawdowns": [{"date": "2026-01-01", "value": -0.02}],
                }
            }
        )
        self.assertEqual(backtest["run_id"], "bt_1")
        self.assertEqual(backtest["metrics"]["cagr"], 0.08)
        self.assertEqual(len(backtest["curves"]["strategy"]), 1)

    def test_backtest_normalizes_real_api_result_shape(self) -> None:
        backtest = normalize_backtest(
            {
                "run_id": "dyn_backtest_1",
                "result": {
                    "metrics": {"cagr": 0.09, "maximum_drawdown": -0.12},
                    "benchmark_metrics": {
                        "spy_buy_hold": {"cagr": 0.08, "maximum_drawdown": -0.2},
                        "spy_sgov_60_40": {"cagr": 0.05, "maximum_drawdown": -0.1},
                    },
                    "points": [
                        {"as_of": "2026-01-01", "equity_curve": 1.0, "drawdown": 0.0},
                        {"as_of": "2026-01-02", "equity_curve": 1.01, "drawdown": -0.01},
                    ],
                    "stress_periods": {"2020": {"available": True}, "2008": {"available": False}},
                },
            }
        )
        self.assertEqual(backtest["metrics"]["cagr"], 0.09)
        self.assertEqual(backtest["curves"]["strategy"][1]["nav"], 1.01)
        self.assertEqual(backtest["drawdown"][1]["value"], -0.01)
        self.assertIn("spy_buy_hold", backtest["benchmark_metrics"])
        self.assertEqual(backtest["stress_periods"][0]["period"], "2020")

    def test_backtest_run_list_keeps_api_order_for_latest_default(self) -> None:
        runs = normalize_backtest_runs(
            {
                "items": [
                    {"run_id": "latest", "created_at": "2026-07-17T15:00:00Z"},
                    {"run_id": "older", "created_at": "2026-07-16T15:00:00Z"},
                    {"created_at": "missing id"},
                ]
            }
        )
        self.assertEqual([item["run_id"] for item in runs], ["latest", "older"])


if __name__ == "__main__":
    unittest.main()
