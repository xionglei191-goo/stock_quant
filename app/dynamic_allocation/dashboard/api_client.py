"""Small HTTP client for the dynamic-allocation API boundary."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True)
class DynamicAllocationApiError(RuntimeError):
    """A display-safe API failure with enough context for recovery."""

    message: str
    status_code: int | None = None
    error_type: str = "api_error"
    trace_id: str = ""
    retryable: bool = False

    def __str__(self) -> str:
        suffix = f" (trace: {self.trace_id})" if self.trace_id else ""
        return f"{self.message}{suffix}"


class DynamicAllocationApiClient:
    """Read-only client used by Streamlit; it never accesses persistence directly."""

    def __init__(
        self,
        base_url: str,
        *,
        actor: str = "dashboard_user",
        role: str = "analyst",
        token: str = "",
        timeout_seconds: float = 10.0,
    ) -> None:
        normalized = str(base_url).strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("API URL must start with http:// or https://")
        self.base_url = normalized
        self.actor = str(actor).strip() or "dashboard_user"
        self.role = str(role).strip() or "analyst"
        self.token = str(token).strip()
        self.timeout_seconds = max(0.5, float(timeout_seconds))

    def get_current(self) -> dict[str, Any]:
        return self._get("/api/dynamic-allocation/current")

    def get_history(self, *, limit: int = 180) -> dict[str, Any]:
        bounded = min(max(int(limit), 1), 2000)
        return self._get("/api/dynamic-allocation/history", {"limit": bounded})

    def get_data_health(self) -> dict[str, Any]:
        return self._get("/api/dynamic-allocation/data-health")

    def get_backtests(self, *, limit: int = 50) -> dict[str, Any]:
        bounded = min(max(int(limit), 1), 200)
        return self._get("/api/dynamic-allocation/backtests", {"limit": bounded})

    def get_backtest(self, run_id: str) -> dict[str, Any]:
        normalized = str(run_id).strip()
        if not normalized:
            raise ValueError("run_id is required")
        encoded = urllib.parse.quote(normalized, safe="")
        return self._get(f"/api/dynamic-allocation/backtests/{encoded}")

    def _get(self, path: str, query: Mapping[str, Any] | None = None) -> dict[str, Any]:
        suffix = f"?{urllib.parse.urlencode(query)}" if query else ""
        request = urllib.request.Request(
            f"{self.base_url}{path}{suffix}",
            headers=self._headers(),
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            self._raise_http_error(raw, int(exc.code))
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            reason = getattr(exc, "reason", exc)
            raise DynamicAllocationApiError(
                message=f"无法连接动态配置 API：{reason}",
                error_type="connection_error",
                retryable=True,
            ) from exc

        if status < 200 or status >= 300:
            self._raise_http_error(raw, status)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DynamicAllocationApiError(
                message="动态配置 API 返回了无效 JSON",
                status_code=status,
                error_type="invalid_response",
                retryable=True,
            ) from exc
        return self._unwrap(payload, status_code=status)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "ai-quant-dynamic-allocation-dashboard/0.1",
            "X-Actor": self.actor,
            "X-Role": self.role,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _unwrap(payload: Any, *, status_code: int) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise DynamicAllocationApiError(
                message="动态配置 API 响应必须是对象",
                status_code=status_code,
                error_type="invalid_response",
            )
        trace_id = str(payload.get("trace_id") or "")
        if payload.get("success") is not True:
            error = payload.get("error")
            if isinstance(error, Mapping):
                message = str(error.get("message") or "动态配置 API 请求失败")
                error_type = str(error.get("type") or "api_error")
            else:
                message = str(error or "动态配置 API 请求失败")
                error_type = "api_error"
            raise DynamicAllocationApiError(
                message=message,
                status_code=status_code,
                error_type=error_type,
                trace_id=trace_id,
                retryable=status_code >= 500,
            )
        data = payload.get("data")
        if data is None:
            return {}
        if not isinstance(data, Mapping):
            raise DynamicAllocationApiError(
                message="动态配置 API data 字段必须是对象",
                status_code=status_code,
                error_type="invalid_response",
                trace_id=trace_id,
            )
        result = dict(data)
        result.setdefault("trace_id", trace_id)
        return result

    @classmethod
    def _raise_http_error(cls, raw: str, status_code: int) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "success": False,
                "error": {"type": "http_error", "message": f"API HTTP {status_code}"},
            }
        cls._unwrap(payload, status_code=status_code)
        raise DynamicAllocationApiError(
            message=f"API HTTP {status_code}",
            status_code=status_code,
            error_type="http_error",
            retryable=status_code >= 500,
        )
