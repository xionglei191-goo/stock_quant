from __future__ import annotations

import json
import mimetypes
import time
import uuid
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import ValidationError
from .utils import env_float, env_int, env_text


DEFAULT_PADDLEOCR_JOB_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_PADDLEOCR_MODEL = "PaddleOCR-VL-1.5"
DEFAULT_PADDLEOCR_OPTIONAL_PAYLOAD = {
    "useDocOrientationClassify": False,
    "useDocUnwarping": False,
    "useChartRecognition": False,
}


class PaddleOCRParser:
    def __init__(
        self,
        *,
        job_url: str | None = None,
        token: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        poll_interval: float | None = None,
        max_polls: int | None = None,
        http_send: Callable[[Request, int], bytes] | None = None,
    ):
        self.job_url = (job_url or env_text("AI_QUANT_PADDLEOCR_JOB_URL", DEFAULT_PADDLEOCR_JOB_URL) or DEFAULT_PADDLEOCR_JOB_URL).rstrip("/")
        self.token = token if token is not None else str(env_text("AI_QUANT_PADDLEOCR_TOKEN", "") or "")
        self.model = model or env_text("AI_QUANT_PADDLEOCR_MODEL", DEFAULT_PADDLEOCR_MODEL) or DEFAULT_PADDLEOCR_MODEL
        self.timeout = int(timeout) if timeout is not None else env_int("AI_QUANT_PADDLEOCR_TIMEOUT_SECONDS", 60, minimum=1)
        self.poll_interval = float(poll_interval) if poll_interval is not None else env_float("AI_QUANT_PADDLEOCR_POLL_INTERVAL_SECONDS", 5.0, minimum=0.0)
        self.max_polls = int(max_polls) if max_polls is not None else env_int("AI_QUANT_PADDLEOCR_MAX_POLLS", 120, minimum=1)
        self._http_send = http_send or self._default_send

    def configured(self) -> bool:
        return bool(self.token)

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "paddleocr",
            "job_url": self.job_url,
            "model": self.model,
            "timeout_seconds": self.timeout,
            "poll_interval_seconds": self.poll_interval,
            "max_polls": self.max_polls,
            "configured": self.configured(),
        }

    def parse_url(self, file_url: str, *, optional_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        file_url = str(file_url).strip()
        if not file_url.startswith(("http://", "https://")):
            raise ValidationError("file_url must start with http:// or https://")
        payload = {
            "fileUrl": file_url,
            "model": self.model,
            "optionalPayload": self._optional_payload(optional_payload),
        }
        job = self._post_json(self.job_url, payload)
        return self._poll_and_collect(job)

    def parse_bytes(
        self,
        data: bytes,
        *,
        filename: str = "document.pdf",
        optional_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not data:
            raise ValidationError("document parser received empty file bytes")
        fields = {
            "model": self.model,
            "optionalPayload": json.dumps(self._optional_payload(optional_payload), ensure_ascii=False),
        }
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body, boundary = self._multipart_body(fields, {"file": (filename or "document.pdf", content_type, data)})
        headers = self._auth_headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = Request(self.job_url, data=body, headers=headers, method="POST")
        job = self._send_json_request(request, "PaddleOCR job submission failed")
        return self._poll_and_collect(job)

    def _optional_payload(self, optional_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(DEFAULT_PADDLEOCR_OPTIONAL_PAYLOAD)
        if optional_payload:
            payload.update(dict(optional_payload))
        return payload

    def _post_json(self, url: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method="POST")
        return self._send_json_request(request, "PaddleOCR job submission failed")

    def _get_json(self, url: str, *, auth: bool = True) -> dict[str, Any]:
        headers = self._auth_headers() if auth else {}
        request = Request(url, headers=headers, method="GET")
        return self._send_json_request(request, "PaddleOCR result request failed")

    def _poll_and_collect(self, job_response: Mapping[str, Any]) -> dict[str, Any]:
        data = job_response.get("data", {})
        if not isinstance(data, Mapping):
            raise ValidationError("PaddleOCR job response missing data")
        job_id = str(data.get("jobId", "")).strip()
        if not job_id:
            raise ValidationError("PaddleOCR job response missing jobId")
        for _attempt in range(max(1, self.max_polls)):
            status = self._get_json(f"{self.job_url}/{job_id}")
            status_data = status.get("data", {})
            if not isinstance(status_data, Mapping):
                raise ValidationError("PaddleOCR status response missing data")
            state = str(status_data.get("state", "")).strip()
            if state == "done":
                jsonl_url = self._jsonl_url(status_data)
                pages = self._fetch_markdown_pages(jsonl_url)
                return {
                    "provider": "paddleocr",
                    "model": self.model,
                    "job_id": job_id,
                    "state": state,
                    "result_url": jsonl_url,
                    "page_count": len(pages),
                    "pages": pages,
                    "text": "\f".join(page["markdown"] for page in pages if page["markdown"].strip()),
                }
            if state == "failed":
                raise ValidationError(f"PaddleOCR job failed: {status_data.get('errorMsg', 'unknown error')}")
            if self.poll_interval > 0:
                time.sleep(self.poll_interval)
        raise ValidationError(f"PaddleOCR job {job_id} did not finish before max polls")

    def _jsonl_url(self, status_data: Mapping[str, Any]) -> str:
        result_url = status_data.get("resultUrl", {})
        if not isinstance(result_url, Mapping):
            raise ValidationError("PaddleOCR done response missing resultUrl")
        jsonl_url = str(result_url.get("jsonUrl", "")).strip()
        if not jsonl_url:
            raise ValidationError("PaddleOCR done response missing jsonUrl")
        return jsonl_url

    def _fetch_markdown_pages(self, jsonl_url: str) -> list[dict[str, Any]]:
        request = Request(jsonl_url, method="GET")
        try:
            raw = self._http_send(request, self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ValidationError(f"PaddleOCR JSONL download returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValidationError(f"PaddleOCR JSONL download failed: {exc.reason}") from exc
        pages: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"PaddleOCR JSONL line {line_number} is not valid JSON") from exc
            result = record.get("result", {})
            if not isinstance(result, Mapping):
                continue
            layout_results = result.get("layoutParsingResults", [])
            if not isinstance(layout_results, list):
                continue
            for layout in layout_results:
                if not isinstance(layout, Mapping):
                    continue
                markdown = layout.get("markdown", {})
                text = markdown.get("text", "") if isinstance(markdown, Mapping) else ""
                markdown_images = markdown.get("images", {}) if isinstance(markdown, Mapping) else {}
                output_images = layout.get("outputImages", {})
                layout_items = self._layout_items(layout)
                tables = self._table_items(layout)
                pages.append(
                    {
                        "page_no": len(pages) + 1,
                        "markdown": str(text),
                        "markdown_images": dict(markdown_images) if isinstance(markdown_images, Mapping) else {},
                        "output_images": dict(output_images) if isinstance(output_images, Mapping) else {},
                        "layout_items": layout_items,
                        "tables": tables,
                        "assets": self._page_assets(markdown_images, output_images),
                    }
                )
        return pages

    def _layout_items(self, layout: Mapping[str, Any]) -> list[dict[str, Any]]:
        pruned = layout.get("prunedResult", {})
        if not isinstance(pruned, Mapping):
            pruned = {}
        candidates = layout.get("layoutDetections") or layout.get("layoutParsingResults") or pruned.get("layoutDetections", [])
        if not isinstance(candidates, list):
            candidates = []
        items: list[dict[str, Any]] = []
        for index, item in enumerate(candidates, start=1):
            if not isinstance(item, Mapping):
                continue
            bbox = self._normalize_bbox(item.get("bbox") or item.get("box") or item.get("coordinate") or item.get("poly") or item.get("points"))
            text = str(item.get("text") or item.get("content") or item.get("label") or "").strip()
            item_type = str(item.get("type") or item.get("label") or item.get("category") or "layout").strip() or "layout"
            if bbox or text:
                items.append({"index": index, "type": item_type, "bbox": bbox, "text": text, "confidence": float(item.get("score", item.get("confidence", 0.0)) or 0.0)})
        return items

    def _table_items(self, layout: Mapping[str, Any]) -> list[dict[str, Any]]:
        pruned = layout.get("prunedResult", {})
        if not isinstance(pruned, Mapping):
            pruned = {}
        candidates = layout.get("tables") or layout.get("tableResults") or pruned.get("tables", [])
        if not isinstance(candidates, list):
            candidates = []
        tables: list[dict[str, Any]] = []
        for table_index, table in enumerate(candidates, start=1):
            if not isinstance(table, Mapping):
                continue
            cells = []
            for cell_index, cell in enumerate(table.get("cells", []) if isinstance(table.get("cells", []), list) else [], start=1):
                if not isinstance(cell, Mapping):
                    continue
                cells.append(
                    {
                        "cell_index": cell_index,
                        "row": int(cell.get("row", cell.get("row_index", 0)) or 0),
                        "col": int(cell.get("col", cell.get("column", cell.get("col_index", 0))) or 0),
                        "rowspan": int(cell.get("rowspan", 1) or 1),
                        "colspan": int(cell.get("colspan", 1) or 1),
                        "text": str(cell.get("text") or cell.get("content") or "").strip(),
                        "bbox": self._normalize_bbox(cell.get("bbox") or cell.get("box") or cell.get("coordinate") or cell.get("poly") or cell.get("points")),
                    }
                )
            tables.append(
                {
                    "table_index": table_index,
                    "bbox": self._normalize_bbox(table.get("bbox") or table.get("box") or table.get("coordinate") or table.get("poly") or table.get("points")),
                    "cells": cells,
                }
            )
        return tables

    def _page_assets(self, markdown_images: Any, output_images: Any) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        for source, images in (("markdown", markdown_images), ("output", output_images)):
            if not isinstance(images, Mapping):
                continue
            for name, uri in images.items():
                assets.append({"asset_type": "image", "source": source, "name": str(name), "uri": str(uri)})
        return assets

    def _normalize_bbox(self, value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            if {"x", "y", "width", "height"}.issubset(value.keys()):
                return {key: float(value[key]) for key in ("x", "y", "width", "height")}
            if {"left", "top", "right", "bottom"}.issubset(value.keys()):
                left = float(value["left"])
                top = float(value["top"])
                right = float(value["right"])
                bottom = float(value["bottom"])
                return {"x": left, "y": top, "width": max(0.0, right - left), "height": max(0.0, bottom - top)}
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            numbers: list[float] = []
            for item in value:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    numbers.extend([float(item[0]), float(item[1])])
                elif isinstance(item, (int, float)):
                    numbers.append(float(item))
            if len(numbers) == 4:
                x1, y1, x2, y2 = numbers
                return {"x": x1, "y": y1, "width": max(0.0, x2 - x1), "height": max(0.0, y2 - y1)}
            if len(numbers) >= 8:
                xs = numbers[0::2]
                ys = numbers[1::2]
                return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
        return {}

    def _send_json_request(self, request: Request, error_prefix: str) -> dict[str, Any]:
        if not self.token:
            raise ValidationError("AI_QUANT_PADDLEOCR_TOKEN is required for PaddleOCR document parsing")
        try:
            raw = self._http_send(request, self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ValidationError(f"{error_prefix}: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise ValidationError(f"{error_prefix}: {exc.reason}") from exc
        text = raw.decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{error_prefix}: upstream returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise ValidationError(f"{error_prefix}: upstream returned non-object response")
        return payload

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"bearer {self.token}"}

    def _multipart_body(self, fields: Mapping[str, str], files: Mapping[str, tuple[str, str, bytes]]) -> tuple[bytes, str]:
        boundary = f"----aiquant{uuid.uuid4().hex}"
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.append(f"--{boundary}\r\n".encode("ascii"))
            parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            parts.append(str(value).encode("utf-8"))
            parts.append(b"\r\n")
        for name, (filename, content_type, data) in files.items():
            safe_filename = filename.replace('"', "")
            parts.append(f"--{boundary}\r\n".encode("ascii"))
            parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{safe_filename}"\r\n'.encode("utf-8"))
            parts.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
            parts.append(data)
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("ascii"))
        return b"".join(parts), boundary

    def _default_send(self, request: Request, timeout: int) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
