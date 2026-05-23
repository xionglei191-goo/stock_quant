from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


ARCHIVE_SCHEMES = {
    "artifact",
    "s3",
    "s3a",
    "s3n",
    "gs",
    "az",
    "azure",
    "abfs",
    "abfss",
    "oci",
    "oss",
    "cos",
    "minio",
    "vault",
    "kms",
    "secret",
    "urn",
    "grafana-loki",
    "loki",
}

NON_PRODUCTION_ARTIFACT_PREFIXES = (
    "local",
    "local-",
    "staging-test",
    "demo",
    "example",
    "sample",
    "tmp",
    "test",
)

NON_PRODUCTION_CLOSURE_ARTIFACT_PREFIXES = (
    *NON_PRODUCTION_ARTIFACT_PREFIXES,
    "local-staging",
    "staging-local",
    "staging-acceptance",
    "staging-governance",
    "staging-security",
    "staging-otel",
    "staging-vision-gate",
    "staging-lineage",
    "staging-graph",
    "full-run",
)


def _is_local_host(host: str) -> bool:
    return host in {"", "localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _artifact_name_has_specific_path(parsed) -> bool:
    name = (parsed.netloc + parsed.path).strip("/")
    return "/" in name.strip("/")


def is_external_artifact_uri(uri: Any) -> bool:
    value = str(uri or "").strip()
    if not value:
        return False
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if not scheme or scheme in {"file", "local"}:
        return False
    if scheme in {"http", "https"}:
        host = parsed.hostname or ""
        if _is_local_host(host):
            return False
        return bool(parsed.path.strip("/") or parsed.query or parsed.fragment)
    if scheme not in ARCHIVE_SCHEMES:
        return False
    if scheme == "urn":
        return bool(parsed.path.strip(": /"))

    name = (parsed.netloc + parsed.path).strip("/")
    if not name:
        return False
    if scheme == "artifact" and name.lower().startswith(NON_PRODUCTION_ARTIFACT_PREFIXES):
        return False
    return _artifact_name_has_specific_path(parsed)


def is_production_artifact_uri(uri: Any) -> bool:
    if not is_external_artifact_uri(uri):
        return False
    parsed = urlparse(str(uri or "").strip())
    if parsed.scheme.lower() == "artifact":
        name = (parsed.netloc + parsed.path).strip("/").lower()
        if name.startswith(NON_PRODUCTION_CLOSURE_ARTIFACT_PREFIXES):
            return False
    return True
