from __future__ import annotations

from pathlib import Path
import threading
import unittest

import yaml

from app.api import ApiRouter
from app.server import _dynamic_allocation_dashboard_url
from app.services import SystemService


ROOT = Path(__file__).resolve().parents[2]


class _DynamicAllocationFixture:
    def evaluate(self, _payload: object, *, persist: bool = False) -> dict[str, object]:
        return {
            "ready": True,
            "persisted": persist,
            "paper_only": True,
            "live_execution_allowed": False,
        }


class _BlockingDailyMainlineService(SystemService):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run_daily_mainline(self, _payload: object, *, actor: str = "system") -> dict[str, object]:
        self.started.set()
        self.release.wait(timeout=5)
        return {"actor": actor, "paper_only": True}


class DynamicAllocationRuntimeTests(unittest.TestCase):
    def test_dashboard_url_uses_request_host_and_configured_port(self) -> None:
        url = _dynamic_allocation_dashboard_url(
            {"Host": "research-box.local:8000"},
            env={"AI_QUANT_DYNAMIC_ALLOCATION_DASHBOARD_PORT": "18501"},
        )
        self.assertEqual(url, "http://research-box.local:18501")

    def test_dashboard_url_honors_proxy_and_explicit_override(self) -> None:
        proxied = _dynamic_allocation_dashboard_url(
            {
                "Host": "127.0.0.1:8000",
                "X-Forwarded-Host": "quant.example.test",
                "X-Forwarded-Proto": "https",
            },
            env={},
        )
        configured = _dynamic_allocation_dashboard_url(
            {"Host": "ignored.test:8000"},
            env={"AI_QUANT_DYNAMIC_ALLOCATION_DASHBOARD_URL": "https://dashboard.example.test/"},
        )
        self.assertEqual(proxied, "https://quant.example.test:8501")
        self.assertEqual(configured, "https://dashboard.example.test")

    def test_health_and_dynamic_reads_do_not_wait_for_main_dispatch_lock(self) -> None:
        service = _BlockingDailyMainlineService()
        router = ApiRouter(service, dynamic_allocation=_DynamicAllocationFixture())
        responses: dict[str, object] = {}

        mainline_thread = threading.Thread(
            target=lambda: responses.setdefault(
                "mainline",
                router.dispatch(
                    "POST",
                    "/api/daily-mainline/run",
                    {},
                    actor="runtime-test",
                    role="analyst",
                ),
            ),
            daemon=True,
        )
        mainline_thread.start()
        self.assertTrue(service.started.wait(timeout=1))

        health_thread = threading.Thread(
            target=lambda: responses.setdefault(
                "health",
                router.dispatch("GET", "/api/health", {}, role="analyst"),
            ),
            daemon=True,
        )
        dynamic_thread = threading.Thread(
            target=lambda: responses.setdefault(
                "dynamic",
                router.dispatch("GET", "/api/dynamic-allocation/current", {}, role="analyst"),
            ),
            daemon=True,
        )
        health_thread.start()
        dynamic_thread.start()
        health_thread.join(timeout=1)
        dynamic_thread.join(timeout=1)

        try:
            self.assertFalse(health_thread.is_alive(), "health request waited for the main dispatch lock")
            self.assertFalse(dynamic_thread.is_alive(), "dynamic allocation read waited for the main dispatch lock")
            self.assertTrue(responses["health"].success)
            self.assertEqual(responses["health"].data["status"], "ok")
            self.assertTrue(responses["dynamic"].success)
            self.assertTrue(responses["dynamic"].data["paper_only"])
            self.assertFalse(responses["dynamic"].data["live_execution_allowed"])
        finally:
            service.release.set()
            mainline_thread.join(timeout=2)

    def test_container_runtime_declares_dashboard_dependencies_and_service(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("COPY config ./config", dockerfile)
        self.assertIn("dynamic-allocation-dashboard", dockerfile)
        self.assertIn("EXPOSE 8000 8501", dockerfile)
        self.assertIn('href="/dynamic-allocation"', html)

        services = compose["services"]
        app = services["ai-quant-org"]
        dashboard = services["dynamic-allocation-dashboard"]
        self.assertIn("./config:/app/config:ro", app["volumes"])
        self.assertIn("AI_QUANT_DYNAMIC_ALLOCATION_DB", app["environment"])
        self.assertEqual(dashboard["environment"]["AI_QUANT_API_BASE_URL"], "http://ai-quant-org:8000")
        self.assertIn("app/dynamic_allocation/dashboard/app.py", dashboard["command"])
        self.assertTrue(dashboard["ports"][0].endswith(":-8501}:8501"))
        self.assertIn("_stcore/health", " ".join(dashboard["healthcheck"]["test"]))
        self.assertEqual(dashboard["restart"], "unless-stopped")


if __name__ == "__main__":
    unittest.main()
