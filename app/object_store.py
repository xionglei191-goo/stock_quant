from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import os
from pathlib import Path
import re
from typing import Callable
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class StoredObject:
    uri: str
    sha256: str
    size_bytes: int


class ObjectStoreConfigError(RuntimeError):
    pass


class LocalObjectStore:
    backend = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_text(self, namespace: str, object_id: str, text: str, *, suffix: str = ".txt") -> StoredObject:
        data = text.encode("utf-8")
        return self.put_bytes(namespace, object_id, data, suffix=suffix)

    def put_bytes(self, namespace: str, object_id: str, data: bytes, *, suffix: str = ".bin") -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        safe_namespace = self._safe_part(namespace)
        safe_id = self._safe_part(object_id)
        path = self.root / safe_namespace / f"{safe_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(uri=str(path), sha256=digest, size_bytes=len(data))

    def read_bytes(self, uri: str) -> bytes:
        return Path(uri).read_bytes()

    def describe(self) -> dict[str, str]:
        return {"backend": self.backend, "root": str(self.root)}

    def _safe_part(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return safe.strip("._") or "object"


class S3CompatibleObjectStore:
    backend = "s3"

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        prefix: str = "",
        http_send: Callable[[Request], bytes] | None = None,
    ):
        if not endpoint_url:
            raise ObjectStoreConfigError("AI_QUANT_S3_ENDPOINT is required for s3 object store")
        if not bucket:
            raise ObjectStoreConfigError("AI_QUANT_S3_BUCKET is required for s3 object store")
        if not access_key or not secret_key:
            raise ObjectStoreConfigError("AI_QUANT_S3_ACCESS_KEY and AI_QUANT_S3_SECRET_KEY are required for s3 object store")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.bucket = bucket.strip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region or "us-east-1"
        self.prefix = prefix.strip("/")
        self.root = f"s3://{self.bucket}/{self.prefix}".rstrip("/")
        self._http_send = http_send or self._default_send

    def put_text(self, namespace: str, object_id: str, text: str, *, suffix: str = ".txt") -> StoredObject:
        return self.put_bytes(namespace, object_id, text.encode("utf-8"), suffix=suffix)

    def put_bytes(self, namespace: str, object_id: str, data: bytes, *, suffix: str = ".bin") -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        key = self._object_key(namespace, object_id, suffix)
        self._request("PUT", key, data=data)
        return StoredObject(uri=f"s3://{self.bucket}/{key}", sha256=digest, size_bytes=len(data))

    def read_bytes(self, uri: str) -> bytes:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or parsed.netloc != self.bucket:
            raise ValueError(f"object uri {uri} does not belong to bucket {self.bucket}")
        key = parsed.path.lstrip("/")
        return self._request("GET", key)

    def describe(self) -> dict[str, str]:
        return {
            "backend": self.backend,
            "root": self.root,
            "endpoint": self.endpoint_url,
            "bucket": self.bucket,
            "region": self.region,
        }

    def _object_key(self, namespace: str, object_id: str, suffix: str) -> str:
        safe_namespace = self._safe_part(namespace)
        safe_id = self._safe_part(object_id)
        key = f"{safe_namespace}/{safe_id}{suffix}"
        return f"{self.prefix}/{key}" if self.prefix else key

    def _request(self, method: str, key: str, *, data: bytes = b"") -> bytes:
        payload = data if method != "GET" else b""
        payload_hash = hashlib.sha256(payload).hexdigest()
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        parsed_endpoint = urlparse(self.endpoint_url)
        host = parsed_endpoint.netloc
        encoded_key = quote(key, safe="/")
        endpoint_path = parsed_endpoint.path.rstrip("/")
        canonical_uri = f"{endpoint_path}/{quote(self.bucket, safe='')}/{encoded_key}"
        url = f"{self.endpoint_url}/{quote(self.bucket, safe='')}/{encoded_key}"
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in signed_headers.split(";"))
        canonical_request = "\n".join(
            [
                method,
                canonical_uri,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(self._signing_key(date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        request = Request(url, data=data if method != "GET" else None, headers=headers, method=method)
        return self._http_send(request)

    def _signing_key(self, date_stamp: str) -> bytes:
        date_key = hmac.new(("AWS4" + self.secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
        region_key = hmac.new(date_key, self.region.encode("utf-8"), hashlib.sha256).digest()
        service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
        return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()

    def _default_send(self, request: Request) -> bytes:
        with urlopen(request, timeout=30) as response:
            return response.read()

    def _safe_part(self, value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
        return safe.strip("._") or "object"


def create_object_store_from_env(default_root: str | Path) -> LocalObjectStore | S3CompatibleObjectStore:
    backend = os.environ.get("AI_QUANT_OBJECT_STORE_BACKEND", "local").strip().lower()
    if backend in {"", "local"}:
        return LocalObjectStore(os.environ.get("AI_QUANT_OBJECT_STORE", str(default_root)))
    if backend == "s3":
        return S3CompatibleObjectStore(
            endpoint_url=os.environ.get("AI_QUANT_S3_ENDPOINT", ""),
            bucket=os.environ.get("AI_QUANT_S3_BUCKET", ""),
            access_key=os.environ.get("AI_QUANT_S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("AI_QUANT_S3_SECRET_KEY", ""),
            region=os.environ.get("AI_QUANT_S3_REGION", "us-east-1"),
            prefix=os.environ.get("AI_QUANT_S3_PREFIX", ""),
        )
    raise ObjectStoreConfigError(f"unsupported object store backend: {backend}")
