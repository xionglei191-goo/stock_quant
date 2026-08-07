"""Tests for the personal ask assistant (/api/ask).

Covers the stateless helper (context assembly / prompt / rule fallback) and the
stateful SystemService.ask facade end-to-end through the router, so route
registration and authorization are exercised too. Paper-only red line and the
fact-before-opinion layering are asserted explicitly.
"""

from __future__ import annotations

from app.llm_gateway import LLMGateway
from app.models import ResearchReportAsset
from app.service_modules import ask_assistant

from tests.support import SystemServiceTestBase


class AskAssistantHelperTests(SystemServiceTestBase):
    def test_build_context_lists_facts_before_opinions_and_carries_boundary(self) -> None:
        intelligence = {
            "status": "available",
            "symbol": "SPCX",
            "resolution": {"matched": True},
            "company_profile": {
                "profile": {
                    "display_name": "SPCX Research Vehicle",
                    "sector": "Tech",
                    "industry": "Software",
                    "business_summary": "Demo business.",
                },
                "coverage_summary": {"report_viewpoint_count": 1},
            },
            "facts_and_events": {
                "latest_market_snapshot": {"as_of_date": "2026-06-24", "close": 25.5},
                "financial_metrics": [{"metric_name": "revenue", "value": 100}],
                "company_events": [{"occurred_at": "2026-06-01", "title": "Product launch"}],
                "evidence": [{"evidence_id": "ev_fact_1"}],
            },
            "research_results": {
                "report_viewpoints": [
                    {
                        "statement": "Long-term upside.",
                        "stance": "bullish",
                        "rating": "buy",
                        "catalysts": ["new product"],
                        "risks": ["competition"],
                        "evidence_ids": ["ev_view_1"],
                    }
                ]
            },
        }
        context = ask_assistant.build_context(intelligence)
        self.assertTrue(context["resolved"])
        self.assertEqual(context["fact_layer"]["display_name"], "SPCX Research Vehicle")
        self.assertEqual(context["fact_layer"]["latest_market_snapshot"]["close"], 25.5)
        self.assertEqual(context["opinion_layer"][0]["rights_boundary"], "opinion_only_not_fact_source")
        # Evidence from viewpoints comes first, then fact-layer evidence; deduped.
        self.assertEqual(context["evidence_ids"], ["ev_view_1", "ev_fact_1"])

        prompt = ask_assistant.build_prompt("这家公司怎么样？", context)
        fact_marker = prompt.index("事实层——最新行情")
        opinion_marker = prompt.index("观点层——研报观点")
        self.assertLess(fact_marker, opinion_marker)
        self.assertIn("不是事实真相", prompt)
        self.assertIn("这家公司怎么样？", prompt)

    def test_rule_based_answer_reports_insufficient_data_when_unresolved(self) -> None:
        context = ask_assistant.build_context({"status": "not_found", "symbol": "NOPE", "resolution": {"matched": False}})
        answer = ask_assistant.rule_based_answer("怎么样？", context)
        self.assertIn("现有资料不足", answer)


class AskAssistantEndpointTests(SystemServiceTestBase):
    def _seed_spcx(self) -> tuple[str, str]:
        run = self.router.dispatch(
            "POST",
            "/api/research/tasks/sec-single-name/run",
            {
                "ticker": "SPCX",
                "cik": "0000000000",
                "company_name": "SPCX Research Vehicle",
                "force_fallback": True,
                "fallback_close": 25.5,
                "fallback_volume": 1000,
                "trade_date": "2026-06-24",
                "quantity": 4,
            },
            role="analyst",
        )
        self.assertTrue(run.success, run.error)
        issuer_id = run.data["ids"]["issuer_id"]
        security_id = run.data["ids"]["security_id"]
        self.service.store.research_reports["rr_spcx_local"] = ResearchReportAsset(
            report_id="rr_spcx_local",
            source_id="local_research_reports",
            broker="Local Broker",
            file_path="/tmp/SPCX-report.pdf",
            file_name="SPCX-report.pdf",
            title="SPCX local research view",
            issuer_id=issuer_id,
            security_id=security_id,
            viewpoint={"rating": "watch", "target_price": 30.0, "boundary": "opinion_only"},
            status="text_indexed",
        )
        return issuer_id, security_id

    def test_ask_requires_a_question(self) -> None:
        response = self.router.dispatch("POST", "/api/ask", {"symbol": "SPCX"}, role="analyst")
        self.assertFalse(response.success)
        self.assertEqual(response.status_code, 422)

    def test_ask_falls_back_to_local_facts_when_gateway_unconfigured(self) -> None:
        self._seed_spcx()
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        response = self.router.dispatch("POST", "/api/ask", {"question": "最近怎么样？", "symbol": "SPCX"}, role="analyst")
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["mode"], "rule_fallback")
        self.assertFalse(response.data["gateway_configured"])
        self.assertTrue(response.data["resolved"])
        self.assertFalse(response.data["live_execution_allowed"])
        self.assertTrue(response.data["paper_only"])
        self.assertIn("SPCX Research Vehicle", response.data["answer"])
        self.assertEqual(self.service.store.audit_log[-1].action, "ask")

    def test_ask_uses_gateway_when_configured(self) -> None:
        self._seed_spcx()
        self.service.llm_gateway = LLMGateway(
            api_key="test-key",
            http_send=lambda _request, _timeout: '{"model":"qwen-test","choices":[{"message":{"content":"这是模型回答。"}}]}'.encode("utf-8"),
        )
        response = self.router.dispatch("POST", "/api/ask", {"question": "最近怎么样？", "symbol": "SPCX"}, role="analyst")
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["mode"], "llm")
        self.assertTrue(response.data["gateway_configured"])
        self.assertEqual(response.data["answer"], "这是模型回答。")
        self.assertEqual(response.data["model_version"], "qwen3.6-plus")

    def test_ask_survives_gateway_failure_with_rule_fallback(self) -> None:
        self._seed_spcx()

        def _boom(_request, _timeout):
            raise RuntimeError("upstream down")

        self.service.llm_gateway = LLMGateway(api_key="test-key", http_send=_boom)
        response = self.router.dispatch("POST", "/api/ask", {"question": "最近怎么样？", "symbol": "SPCX"}, role="analyst")
        self.assertTrue(response.success, response.error)
        self.assertEqual(response.data["mode"], "rule_fallback")
        self.assertIn("upstream_error", response.data)
        self.assertIn("SPCX Research Vehicle", response.data["answer"])

    def test_ask_without_symbol_returns_insufficient_data(self) -> None:
        self.service.llm_gateway = LLMGateway(api_key="", http_send=lambda _request, _timeout: b"{}")
        response = self.router.dispatch("POST", "/api/ask", {"question": "大盘怎么样？"}, role="analyst")
        self.assertTrue(response.success, response.error)
        self.assertFalse(response.data["resolved"])
        self.assertIn("现有资料不足", response.data["answer"])

    def test_ask_route_is_registered(self) -> None:
        from app.api_routes import build_route_table

        routes = {(method, pattern) for method, pattern, _handler in build_route_table(self.router)}
        self.assertIn(("POST", r"^/api/ask$"), routes)
