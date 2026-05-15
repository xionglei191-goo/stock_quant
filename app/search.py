from __future__ import annotations

from dataclasses import asdict, dataclass
import base64
from collections import Counter
import json
import math
import os
import re
from typing import Any, Callable, Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class SearchRecord:
    resource_type: str
    resource_id: str
    issuer_id: str
    title: str
    body: str
    weight: float = 1.0


class SearchConfigError(RuntimeError):
    pass


class LocalSearchIndex:
    backend = "local"

    def sync(self, records: Iterable[SearchRecord]) -> dict[str, Any]:
        count = sum(1 for _item in records)
        return {"backend": self.backend, "indexed": count, "mode": "inline"}

    def search(self, records: Iterable[SearchRecord], *, query: str, issuer_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)]
        if not terms:
            return []
        results: list[dict[str, Any]] = []
        for record in records:
            if issuer_id and record.issuer_id != issuer_id:
                continue
            haystack = f"{record.title}\n{record.body}".lower()
            score = sum(haystack.count(term) for term in terms) * record.weight
            if score <= 0:
                continue
            results.append(
                {
                    "resource_type": record.resource_type,
                    "resource_id": record.resource_id,
                    "issuer_id": record.issuer_id,
                    "title": record.title,
                    "snippet": self._snippet(f"{record.title}. {record.body}", terms),
                    "score": round(score, 4),
                }
            )
        results.sort(key=lambda item: (-item["score"], item["resource_type"], item["resource_id"]))
        return results[:limit]

    def describe(self) -> dict[str, str]:
        return {"backend": self.backend}

    def _snippet(self, text: str, terms: list[str]) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        lowered = compact.lower()
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        if not positions:
            return compact[:220]
        start = max(0, min(positions) - 70)
        end = min(len(compact), start + 220)
        return compact[start:end]


class LocalSemanticIndex:
    backend = "local-semantic"

    def sync(self, records: Iterable[SearchRecord]) -> dict[str, Any]:
        count = sum(1 for _item in records)
        return {"backend": self.backend, "indexed": count, "mode": "inline"}

    def search(self, records: Iterable[SearchRecord], *, query: str, issuer_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        query_vector = self._vector(query)
        if not query_vector:
            return []
        results: list[dict[str, Any]] = []
        for record in records:
            if issuer_id and record.issuer_id != issuer_id:
                continue
            record_text = f"{record.title}\n{record.body}"
            score = self._cosine(query_vector, self._vector(record_text)) * record.weight
            if score <= 0:
                continue
            results.append(
                {
                    "resource_type": record.resource_type,
                    "resource_id": record.resource_id,
                    "issuer_id": record.issuer_id,
                    "title": record.title,
                    "snippet": LocalSearchIndex()._snippet(f"{record.title}. {record.body}", list(query_vector.keys())),
                    "score": round(score, 4),
                    "source_boundary": "inherits_record_rights",
                }
            )
        results.sort(key=lambda item: (-item["score"], item["resource_type"], item["resource_id"]))
        return results[:limit]

    def describe(self) -> dict[str, str]:
        return {"backend": self.backend, "embedding": "term-frequency-cosine"}

    def _vector(self, text: str) -> Counter[str]:
        tokens = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", text) if len(term.strip()) > 1]
        return Counter(tokens)

    def _cosine(self, left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        overlap = set(left) & set(right)
        numerator = sum(left[token] * right[token] for token in overlap)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)


class OpenSearchIndex:
    backend = "opensearch"

    def __init__(
        self,
        *,
        endpoint_url: str,
        index_name: str,
        username: str = "",
        password: str = "",
        http_send: Callable[[Request], bytes] | None = None,
    ):
        if not endpoint_url:
            raise SearchConfigError("AI_QUANT_OPENSEARCH_URL is required for opensearch search backend")
        if not index_name:
            raise SearchConfigError("AI_QUANT_OPENSEARCH_INDEX is required for opensearch search backend")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.index_name = index_name
        self.username = username
        self.password = password
        self._http_send = http_send or self._default_send

    def sync(self, records: Iterable[SearchRecord]) -> dict[str, Any]:
        lines: list[str] = []
        count = 0
        for record in records:
            doc_id = f"{record.resource_type}:{record.resource_id}"
            lines.append(json.dumps({"index": {"_index": self.index_name, "_id": doc_id}}, ensure_ascii=False))
            lines.append(json.dumps(asdict(record), ensure_ascii=False))
            count += 1
        if lines:
            body = ("\n".join(lines) + "\n").encode("utf-8")
            self._request("POST", "/_bulk", body=body, content_type="application/x-ndjson")
        return {"backend": self.backend, "indexed": count, "index": self.index_name}

    def search(self, _records: Iterable[SearchRecord], *, query: str, issuer_id: str = "", limit: int = 20) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if issuer_id:
            filters.append({"term": {"issuer_id.keyword": issuer_id}})
        payload = {
            "size": limit,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": query, "fields": ["title^2", "body"]}}],
                    "filter": filters,
                }
            },
        }
        raw = self._request("POST", f"/{self.index_name}/_search", body=json.dumps(payload).encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        results: list[dict[str, Any]] = []
        for hit in data.get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            title = str(source.get("title", ""))
            body = str(source.get("body", ""))
            results.append(
                {
                    "resource_type": source.get("resource_type", ""),
                    "resource_id": source.get("resource_id", ""),
                    "issuer_id": source.get("issuer_id", ""),
                    "title": title,
                    "snippet": self._snippet(title, body, query),
                    "score": round(float(hit.get("_score") or 0.0), 4),
                }
            )
        return results

    def describe(self) -> dict[str, str]:
        parsed = urlparse(self.endpoint_url)
        return {
            "backend": self.backend,
            "endpoint": f"{parsed.scheme}://{parsed.netloc}",
            "index": self.index_name,
        }

    def _request(self, method: str, path: str, *, body: bytes = b"", content_type: str = "application/json") -> bytes:
        headers = {"Content-Type": content_type}
        if self.username or self.password:
            token = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        request = Request(f"{self.endpoint_url}{path}", data=body if method != "GET" else None, method=method, headers=headers)
        return self._http_send(request)

    def _default_send(self, request: Request) -> bytes:
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _snippet(self, title: str, body: str, query: str) -> str:
        terms = [term.lower() for term in re.findall(r"[\w\u4e00-\u9fff]+", query)]
        return LocalSearchIndex()._snippet(f"{title}. {body}", terms)


def create_search_index_from_env() -> LocalSearchIndex | OpenSearchIndex:
    backend = os.environ.get("AI_QUANT_SEARCH_BACKEND", "local").strip().lower()
    if backend in {"", "local"}:
        return LocalSearchIndex()
    if backend == "opensearch":
        return OpenSearchIndex(
            endpoint_url=os.environ.get("AI_QUANT_OPENSEARCH_URL", ""),
            index_name=os.environ.get("AI_QUANT_OPENSEARCH_INDEX", "ai_quant_research"),
            username=os.environ.get("AI_QUANT_OPENSEARCH_USER", ""),
            password=os.environ.get("AI_QUANT_OPENSEARCH_PASSWORD", ""),
        )
    raise SearchConfigError(f"unsupported search backend: {backend}")
