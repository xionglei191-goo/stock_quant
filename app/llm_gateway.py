from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import ValidationError
from .utils import env_int, env_text


DEFAULT_LLM_BASE_URL = "https://llm.nananobanana.cn"
DEFAULT_LLM_MODEL = "qwen3.6-plus"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"


class LLMGateway:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: int | None = None,
        http_send: Callable[[Request, int], bytes] | None = None,
    ):
        self.base_url = (base_url or env_text("AI_QUANT_LLM_BASE_URL", DEFAULT_LLM_BASE_URL) or DEFAULT_LLM_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else str(env_text("AI_QUANT_LLM_API_KEY", "") or "")
        self.default_model = default_model or env_text("AI_QUANT_LLM_DEFAULT_MODEL", DEFAULT_LLM_MODEL) or DEFAULT_LLM_MODEL
        self.timeout = int(timeout) if timeout is not None else env_int("AI_QUANT_LLM_TIMEOUT_SECONDS", 120, minimum=1)
        self._http_send = http_send or self._default_send

    def openai_chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._payload_with_default_model(payload)
        return self._post_json("/v1/chat/completions", body, provider="openai")

    def anthropic_messages(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._payload_with_default_model(payload)
        return self._post_json("/v1/messages", body, provider="anthropic")

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "default_model": self.default_model,
            "timeout_seconds": self.timeout,
            "configured": bool(self.api_key),
        }

    def _payload_with_default_model(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValidationError("LLM gateway payload must be an object")
        body = dict(payload)
        body.setdefault("model", self.default_model)
        return body

    def _post_json(self, path: str, payload: Mapping[str, Any], *, provider: str) -> dict[str, Any]:
        if not self.api_key:
            raise ValidationError("AI_QUANT_LLM_API_KEY is required for LLM gateway calls")
        timeout = self._request_timeout(payload)
        clean_payload = {key: value for key, value in payload.items() if key not in {"timeout", "timeout_seconds"}}
        data = json.dumps(clean_payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if provider == "anthropic":
            headers["x-api-key"] = self.api_key
            headers["anthropic-version"] = str(env_text("AI_QUANT_ANTHROPIC_VERSION", DEFAULT_ANTHROPIC_VERSION) or DEFAULT_ANTHROPIC_VERSION)
        request = Request(f"{self.base_url}{path}", data=data, headers=headers, method="POST")
        try:
            raw = self._send_with_hard_timeout(request, timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ValidationError(f"LLM upstream returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValidationError(f"LLM upstream request failed: {exc.reason}") from exc
        except FutureTimeoutError as exc:
            raise ValidationError(f"LLM upstream request timed out after {timeout}s") from exc
        text = raw.decode("utf-8", errors="replace")
        try:
            response: Any = json.loads(text)
        except json.JSONDecodeError:
            response = {"raw": text}
        if not isinstance(response, dict):
            response = {"data": response}
        return {
            "provider": provider,
            "endpoint": path,
            "model": str(clean_payload.get("model", self.default_model)),
            "timeout_seconds": timeout,
            "response": response,
        }

    def _default_send(self, request: Request, timeout: int) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    def _send_with_hard_timeout(self, request: Request, timeout: int) -> bytes:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._http_send, request, timeout)
        try:
            return future.result(timeout=timeout)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _request_timeout(self, payload: Mapping[str, Any]) -> int:
        raw_timeout = payload.get("timeout_seconds", payload.get("timeout", self.timeout))
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            timeout = self.timeout
        return max(1, min(timeout, self.timeout))
