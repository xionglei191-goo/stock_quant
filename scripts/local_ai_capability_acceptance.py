from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import time
from typing import Any, Mapping
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_OCR_FILE_URL = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"


def _unwrap_response(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), Mapping):
        return payload["data"]
    return payload


def _fetch_json(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    with urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return data


def _post_json(base_url: str, path: str, payload: Mapping[str, Any], *, timeout: float) -> tuple[dict[str, Any], int]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    started = time.perf_counter()
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{url} did not return a JSON object")
    return data, int((time.perf_counter() - started) * 1000)


def _choice_text(llm_data: Mapping[str, Any]) -> str:
    response = llm_data.get("response", {})
    if not isinstance(response, Mapping):
        return ""
    choices = response.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message", {})
    if isinstance(message, Mapping):
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(str(item.get("text", "")) if isinstance(item, Mapping) else str(item) for item in content)
        return str(content or "")
    return str(first.get("text", "") or "")


def _failure(check: str, error: str, **extra: Any) -> dict[str, Any]:
    return {"check": check, "error": error, **extra}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def build_local_ai_capability_acceptance(
    *,
    health: Mapping[str, Any],
    llm_response: Mapping[str, Any] | None = None,
    llm_wall_ms: int | None = None,
    ocr_response: Mapping[str, Any] | None = None,
    ocr_wall_ms: int | None = None,
    expected_llm_text: str = "ok",
) -> dict[str, Any]:
    health_data = _unwrap_response(health)
    llm_gateway = health_data.get("llm_gateway", {})
    document_parser = health_data.get("document_parser", {})
    if not isinstance(llm_gateway, Mapping):
        llm_gateway = {}
    if not isinstance(document_parser, Mapping):
        document_parser = {}

    failures: list[dict[str, Any]] = []
    if llm_gateway.get("configured") is not True:
        failures.append(_failure("llm_configured", "LLM gateway must be configured for local AI acceptance"))
    if document_parser.get("configured") is not True:
        failures.append(_failure("paddleocr_configured", "PaddleOCR parser must be configured for local AI acceptance"))

    llm_summary: dict[str, Any] = {
        "configured": bool(llm_gateway.get("configured")),
        "model": str(llm_gateway.get("default_model", "")),
        "smoke_passed": False,
    }
    if llm_response is not None:
        llm_payload = dict(llm_response)
        llm_data = _unwrap_response(llm_payload)
        content = _choice_text(llm_data)
        response = llm_data.get("response", {})
        choices = response.get("choices", []) if isinstance(response, Mapping) else []
        llm_summary.update(
            {
                "success": llm_payload.get("success", llm_response.get("success")),
                "provider": llm_data.get("provider", ""),
                "model": llm_data.get("model", llm_summary["model"]),
                "choice_count": len(choices) if isinstance(choices, list) else 0,
                "content_preview": content[:80],
                "wall_ms": llm_wall_ms,
            }
        )
        llm_ok = llm_payload.get("success") is True and content.strip().lower() == expected_llm_text.strip().lower()
        llm_summary["smoke_passed"] = llm_ok
        if not llm_ok:
            failures.append(
                _failure(
                    "llm_smoke",
                    "LLM smoke must return the expected short response",
                    content_preview=content[:80],
                    expected=expected_llm_text,
                )
            )
    else:
        failures.append(_failure("llm_smoke", "LLM smoke response is required"))

    ocr_summary: dict[str, Any] = {
        "configured": bool(document_parser.get("configured")),
        "model": str(document_parser.get("model", "")),
        "smoke_passed": False,
    }
    if ocr_response is not None:
        ocr_payload = dict(ocr_response)
        ocr_data = _unwrap_response(ocr_payload)
        text = str(ocr_data.get("text", "") or "")
        page_count = int(ocr_data.get("page_count", 0) or 0)
        ocr_summary.update(
            {
                "success": ocr_payload.get("success", ocr_response.get("success")),
                "provider": ocr_data.get("provider", ""),
                "model": ocr_data.get("model", ocr_summary["model"]),
                "state": ocr_data.get("state", ""),
                "job_id_present": bool(ocr_data.get("job_id")),
                "page_count": page_count,
                "attempt_count": ocr_data.get("attempt_count"),
                "retry_attempts": ocr_data.get("retry_attempts"),
                "cache_hit": bool(ocr_data.get("cache_hit")),
                "elapsed_ms_reported": ocr_data.get("elapsed_ms"),
                "wall_ms": ocr_wall_ms,
                "text_preview": text[:120],
            }
        )
        ocr_ok = ocr_payload.get("success") is True and ocr_data.get("state") == "done" and page_count >= 1 and bool(text.strip())
        ocr_summary["smoke_passed"] = ocr_ok
        if not ocr_ok:
            failures.append(
                _failure(
                    "paddleocr_smoke",
                    "PaddleOCR smoke must finish and return extractable text",
                    state=ocr_data.get("state", ""),
                    page_count=page_count,
                )
            )
    else:
        failures.append(_failure("paddleocr_smoke", "PaddleOCR smoke response is required"))

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "deployment_target": "local_only_personal_production",
        "requests_available_in_python": importlib.util.find_spec("requests") is not None,
        "health_summary": {
            "store": health_data.get("store", ""),
            "object_store_backend": (health_data.get("object_store") or {}).get("backend", "")
            if isinstance(health_data.get("object_store"), Mapping)
            else "",
            "search_backend": (health_data.get("search_index") or {}).get("backend", "")
            if isinstance(health_data.get("search_index"), Mapping)
            else "",
            "tdx_market_data_configured": bool((health_data.get("tdx_market_data") or {}).get("configured"))
            if isinstance(health_data.get("tdx_market_data"), Mapping)
            else False,
        },
        "llm_gateway": llm_summary,
        "paddleocr": ocr_summary,
        "failure_count": len(failures),
        "failures": failures,
    }


def run_local_ai_capability_acceptance(
    *,
    base_url: str,
    ocr_file_url: str,
    force_ocr_rerun: bool,
    timeout: float,
) -> dict[str, Any]:
    health = _fetch_json(base_url, "/api/health", timeout=timeout)
    llm_response, llm_wall_ms = _post_json(
        base_url,
        "/api/llm/openai/chat/completions",
        {
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "temperature": 0,
            "max_tokens": 8,
        },
        timeout=timeout,
    )
    ocr_response, ocr_wall_ms = _post_json(
        base_url,
        "/api/document-parsing/paddleocr",
        {
            "file_url": ocr_file_url,
            "optional_payload": {
                "useDocOrientationClassify": False,
                "useDocUnwarping": False,
                "useChartRecognition": False,
            },
            "use_cache": not force_ocr_rerun,
            "retry_attempts": 1,
        },
        timeout=max(timeout, 720.0),
    )
    return build_local_ai_capability_acceptance(
        health=health,
        llm_response=llm_response,
        llm_wall_ms=llm_wall_ms,
        ocr_response=ocr_response,
        ocr_wall_ms=ocr_wall_ms,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local LLM and PaddleOCR-VL smoke acceptance without writing secrets.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ocr-file-url", default=DEFAULT_OCR_FILE_URL)
    parser.add_argument("--force-ocr-rerun", action="store_true", help="Disable PaddleOCR cache and submit a fresh OCR job.")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = run_local_ai_capability_acceptance(
        base_url=args.base_url,
        ocr_file_url=args.ocr_file_url,
        force_ocr_rerun=args.force_ocr_rerun,
        timeout=args.timeout,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
