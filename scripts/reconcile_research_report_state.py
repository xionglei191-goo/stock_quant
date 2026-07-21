#!/usr/bin/env python3
"""Read-only reconciliation of local research-report storage state.

The stores in this project intentionally have different grains: the filesystem
holds raw files, PostgreSQL holds workflow state, OpenSearch holds a derived
search projection, and the object store holds derived payloads.  This script
compares only compatible measures and never mutates any store.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research_reports import report_id_for_path


DEFAULT_REPORT_ROOT = Path("/home/xionglei/文档/6大投行研报汇总")
DEFAULT_REGISTRY_ROOT = "/data/local/research_reports"
DEFAULT_EXTENSIONS = (".pdf", ".txt", ".md")
DEFAULT_BASELINE_ARTIFACT = Path("artifacts/research-report-completion-audit.json")
DEFAULT_OUTPUT = Path("artifacts/research-report-state-reconciliation.json")
SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
RESEARCH_OBJECT_NAMESPACE_PATTERN = re.compile(r"^(?:local[_-]?research|research[_-]?report)", re.IGNORECASE)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_timestamp(value: float | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _normalize_extensions(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        item = str(value).strip().lower()
        if not item:
            continue
        normalized.add(item if item.startswith(".") else f".{item}")
    return normalized or set(DEFAULT_EXTENSIONS)


def _safe_endpoint(value: str) -> str:
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return "configured"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _sanitize_error(exc: BaseException, secrets: Iterable[str] = ()) -> str:
    value = str(exc)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "***REDACTED***")
    value = re.sub(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1***@", value, flags=re.IGNORECASE)
    value = re.sub(
        r"(?i)(X-Amz-(?:Signature|Credential|Security-Token)|access[_-]?key|secret[_-]?key|password|token)=([^&\s]+)",
        r"\1=***REDACTED***",
        value,
    )
    value = re.sub(r"(?i)(authorization:\s*)[^\s,]+", r"\1***REDACTED***", value)
    return value[:500]


def _availability(role: str, *, status: str = "available", error_code: str = "", error: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "availability": status,
        "source_of_truth_role": role,
    }
    if error_code:
        result["error_code"] = error_code
    if error:
        result["error"] = error
    return result


def inventory_filesystem(
    root: Path,
    *,
    extensions: set[str],
    registry_root_aliases: Iterable[str],
) -> tuple[dict[str, Any], dict[str, set[str]]]:
    role = "authoritative_raw_source_archive"
    root = root.expanduser().resolve()
    aliases = [str(Path(item).expanduser()) for item in registry_root_aliases if str(item).strip()]
    if str(root) not in aliases:
        aliases.append(str(root))
    ids_by_alias: dict[str, set[str]] = {alias: set() for alias in aliases}
    if not root.exists() or not root.is_dir():
        return (
            {
                **_availability(role, status="unavailable", error_code="root_not_found"),
                "root": str(root),
                "expected_grain": "one raw file per research-report asset",
            },
            ids_by_alias,
        )

    total_files = 0
    total_bytes = 0
    eligible_files = 0
    eligible_bytes = 0
    unreadable_metadata = 0
    by_extension: Counter[str] = Counter()
    manifest_rows: list[str] = []
    oldest_mtime: float | None = None
    newest_mtime: float | None = None

    for directory, _subdirectories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for filename in filenames:
            path = directory_path / filename
            try:
                stat = path.stat(follow_symlinks=False)
            except OSError:
                unreadable_metadata += 1
                continue
            if not path.is_file():
                continue
            total_files += 1
            total_bytes += int(stat.st_size)
            suffix = path.suffix.lower()
            by_extension[suffix or "<none>"] += 1
            if suffix not in extensions:
                continue
            eligible_files += 1
            eligible_bytes += int(stat.st_size)
            oldest_mtime = stat.st_mtime if oldest_mtime is None else min(oldest_mtime, stat.st_mtime)
            newest_mtime = stat.st_mtime if newest_mtime is None else max(newest_mtime, stat.st_mtime)
            relative = path.relative_to(root)
            manifest_rows.append(f"{relative.as_posix()}|{stat.st_size}|{int(stat.st_mtime)}")
            for alias in aliases:
                ids_by_alias[alias].add(report_id_for_path(Path(alias) / relative))

    manifest_hash = hashlib.sha256("\n".join(sorted(manifest_rows)).encode("utf-8")).hexdigest()
    result = {
        **_availability(role),
        "root": str(root),
        "expected_grain": "one raw file per research-report asset",
        "extensions_in_scope": sorted(extensions),
        "counts": {
            "all_files": total_files,
            "eligible_report_files": eligible_files,
            "out_of_scope_files": max(0, total_files - eligible_files),
            "unreadable_metadata": unreadable_metadata,
        },
        "size_bytes": {
            "all_files": total_bytes,
            "eligible_report_files": eligible_bytes,
        },
        "file_counts_by_extension": dict(sorted(by_extension.items())),
        "eligible_manifest_sha256": manifest_hash,
        "eligible_oldest_mtime": _iso_from_timestamp(oldest_mtime),
        "eligible_newest_mtime": _iso_from_timestamp(newest_mtime),
        "identifier_policy": {
            "algorithm": "rr_ + first 16 hex chars of sha256(absolute logical path)",
            "registry_root_aliases": aliases,
            "content_hashing_performed": False,
        },
    }
    return result, ids_by_alias


def _postgres_descriptor(dsn: str) -> dict[str, str]:
    parsed = urlsplit(dsn)
    return {
        "backend": parsed.scheme or "postgresql",
        "endpoint": _safe_endpoint(dsn),
        "database": parsed.path.lstrip("/"),
        "schema": "ai_quant",
    }


def inventory_postgres(
    dsn: str,
    *,
    connect_timeout: float = 10.0,
    connect_fn: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    role = "authoritative_workflow_registry_and_citation_state"
    if not dsn:
        return _availability(role, status="not_configured", error_code="dsn_missing"), set()
    if connect_fn is None:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            return (
                {
                    **_availability(role, status="unavailable", error_code="psycopg_missing", error=_sanitize_error(exc)),
                    "connection": _postgres_descriptor(dsn),
                },
                set(),
            )
        connect_fn = psycopg.connect

    report_ids: set[str] = set()
    try:
        with connect_fn(dsn, connect_timeout=connect_timeout) as connection:
            with connection.cursor() as cursor:
                target_collections = (
                    "research_reports",
                    "structured_research_reports",
                    "report_viewpoints",
                    "report_forecasts",
                    "documents",
                    "evidence",
                )
                cursor.execute(
                    """
                    SELECT collection, COUNT(*)
                    FROM ai_quant.records
                    WHERE collection = ANY(%s)
                    GROUP BY collection
                    ORDER BY collection
                    """,
                    (list(target_collections),),
                )
                collection_counts = {str(name): int(count) for name, count in cursor.fetchall()}
                for name in target_collections:
                    collection_counts.setdefault(name, 0)

                cursor.execute(
                    """
                    SELECT
                        item_id,
                        COALESCE(payload->>'status', ''),
                        COALESCE(payload->>'document_id', ''),
                        COALESCE(payload->>'file_path', ''),
                        COALESCE(payload->>'fingerprint', ''),
                        COALESCE(payload->>'content_sha256', '')
                    FROM ai_quant.records
                    WHERE collection = 'research_reports'
                    ORDER BY item_id
                    """
                )
                report_rows = [tuple(row) for row in cursor.fetchall()]
                report_ids = {str(row[0]) for row in report_rows}
                report_document_ids = {str(row[2]) for row in report_rows if str(row[2])}
                status_counts = Counter(str(row[1]) or "<missing>" for row in report_rows)

                cursor.execute(
                    """
                    SELECT item_id, COALESCE(payload->>'source_uri', '')
                    FROM ai_quant.records
                    WHERE collection = 'documents'
                      AND (
                        payload->>'document_type' = 'research'
                        OR payload->>'source_uri' LIKE 'research-report://%'
                        OR payload->>'source_id' LIKE 'local_research_%'
                        OR payload->'rights_tag'->>'license_class' = 'local_research_reference'
                      )
                    """
                )
                document_rows = [tuple(row) for row in cursor.fetchall()]
                research_document_ids = {str(row[0]) for row in document_rows}
                directly_linked_document_ids = {
                    str(row[0]) for row in document_rows if str(row[1]).startswith("research-report://")
                }

                cursor.execute(
                    """
                    SELECT
                        COUNT(*),
                        COUNT(DISTINCT payload->>'document_id'),
                        ARRAY_REMOVE(ARRAY_AGG(DISTINCT payload->>'document_id'), NULL)
                    FROM ai_quant.records
                    WHERE collection = 'evidence'
                      AND (
                        payload->>'section' = 'research_report_citation'
                        OR payload->>'bbox' LIKE 'research_report://%'
                      )
                    """
                )
                evidence_row = cursor.fetchone() or (0, 0, [])
                citation_document_ids = {str(item) for item in (evidence_row[2] or []) if str(item)}

        result = {
            **_availability(role),
            "connection": _postgres_descriptor(dsn),
            "expected_grain": {
                "research_reports": "one workflow asset per deterministic report_id",
                "documents": "one linked research document per ingested report asset",
                "evidence": "zero-to-many citation chunks per linked document",
                "structured_research_reports": "zero-or-one derived structured report per eligible asset",
            },
            "collection_counts": collection_counts,
            "research_asset_status_counts": dict(sorted(status_counts.items())),
            "research_asset_metadata_completeness": {
                "document_id_populated": sum(1 for row in report_rows if str(row[2])),
                "file_path_populated": sum(1 for row in report_rows if str(row[3])),
                "fingerprint_populated": sum(1 for row in report_rows if str(row[4])),
                "content_sha256_populated": sum(1 for row in report_rows if str(row[5])),
            },
            "research_document_counts": {
                "in_scope_documents": len(research_document_ids),
                "source_uri_linked_documents": len(directly_linked_document_ids),
            },
            "citation_evidence_counts": {
                "citation_chunks": int(evidence_row[0] or 0),
                "distinct_document_ids": int(evidence_row[1] or 0),
            },
            "referential_integrity": {
                "report_document_ids_missing_document": len(report_document_ids - research_document_ids),
                "research_documents_without_report_reference": len(research_document_ids - report_document_ids),
                "citation_document_ids_missing_document": len(citation_document_ids - research_document_ids),
            },
        }
        return result, report_ids
    except Exception as exc:  # noqa: BLE001 - audit must report partial availability
        return (
            {
                **_availability(
                    role,
                    status="unavailable",
                    error_code="query_failed",
                    error=_sanitize_error(exc, [dsn]),
                ),
                "connection": _postgres_descriptor(dsn),
            },
            set(),
        )


def _http_json(
    request: Request,
    *,
    timeout: float,
    http_send: Callable[[Request], bytes] | None,
) -> dict[str, Any]:
    if http_send is not None:
        raw = http_send(request)
    else:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    return json.loads(raw.decode("utf-8"))


def inventory_opensearch(
    endpoint_url: str,
    index_name: str,
    *,
    username: str = "",
    password: str = "",
    timeout: float = 10.0,
    http_send: Callable[[Request], bytes] | None = None,
) -> dict[str, Any]:
    role = "derived_rebuildable_search_projection"
    if not endpoint_url or not index_name:
        return _availability(role, status="not_configured", error_code="endpoint_or_index_missing")
    endpoint_url = endpoint_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if username or password:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    def request_json(method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(f"{endpoint_url}{path}", data=body, method=method, headers=headers)
        return _http_json(request, timeout=timeout, http_send=http_send)

    try:
        count_payload = request_json("GET", f"/{quote(index_name, safe='')}/_count")
        total_count = int(count_payload.get("count", 0))
        aggregation_error = ""
        resource_type_counts: dict[str, int] = {}
        try:
            aggregation_payload = request_json(
                "POST",
                f"/{quote(index_name, safe='')}/_search",
                {
                    "size": 0,
                    "track_total_hits": True,
                    "aggs": {"resource_types": {"terms": {"field": "resource_type.keyword", "size": 100}}},
                },
            )
            buckets = aggregation_payload.get("aggregations", {}).get("resource_types", {}).get("buckets", [])
            resource_type_counts = {str(item.get("key", "")): int(item.get("doc_count", 0)) for item in buckets}
        except Exception as exc:  # noqa: BLE001 - total count is still useful
            aggregation_error = _sanitize_error(exc, [username, password])

        stats = request_json("GET", f"/{quote(index_name, safe='')}/_stats/docs,store")
        primary = stats.get("_all", {}).get("primaries", {})
        docs = primary.get("docs", {})
        store = primary.get("store", {})
        result = {
            **_availability(role),
            "endpoint": _safe_endpoint(endpoint_url),
            "index": index_name,
            "expected_grain": "one derived SearchRecord projection per resource_type/resource_id",
            "counts": {
                "live_documents": total_count,
                "primary_documents": int(docs.get("count", total_count) or 0),
                "deleted_documents": int(docs.get("deleted", 0) or 0),
            },
            "primary_store_size_bytes": int(store.get("size_in_bytes", 0) or 0),
            "resource_type_counts": dict(sorted(resource_type_counts.items())),
            "comparison_boundary": "Only research_report projections are directly comparable to PostgreSQL research-report assets; document and evidence projections have different grains.",
        }
        if aggregation_error:
            result["resource_type_aggregation_error"] = aggregation_error
        return result
    except Exception as exc:  # noqa: BLE001 - audit must report partial availability
        return {
            **_availability(
                role,
                status="unavailable",
                error_code="query_failed",
                error=_sanitize_error(exc, [username, password]),
            ),
            "endpoint": _safe_endpoint(endpoint_url),
            "index": index_name,
        }


def _aws_quote(value: str) -> str:
    return quote(str(value), safe="-_.~")


def _s3_list_request(
    *,
    endpoint_url: str,
    bucket: str,
    prefix: str,
    continuation_token: str,
    access_key: str,
    secret_key: str,
    region: str,
    now: datetime | None = None,
) -> Request:
    now = now or datetime.now(timezone.utc)
    endpoint = urlsplit(endpoint_url.rstrip("/"))
    if not endpoint.scheme or not endpoint.netloc:
        raise ValueError("S3 endpoint must be an absolute HTTP(S) URL")
    query_items = [("list-type", "2"), ("max-keys", "1000")]
    if prefix:
        query_items.append(("prefix", prefix))
    if continuation_token:
        query_items.append(("continuation-token", continuation_token))
    canonical_query = "&".join(
        f"{_aws_quote(key)}={_aws_quote(value)}" for key, value in sorted(query_items, key=lambda item: (item[0], item[1]))
    )
    endpoint_path = endpoint.path.rstrip("/")
    canonical_uri = f"{endpoint_path}/{_aws_quote(bucket)}/"
    payload_hash = hashlib.sha256(b"").hexdigest()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    headers = {
        "host": endpoint.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in signed_headers.split(";"))
    canonical_request = "\n".join(
        ["GET", canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    date_key = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    signing_key = hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
    )
    url = f"{endpoint_url.rstrip('/')}/{_aws_quote(bucket)}/?{canonical_query}"
    return Request(url, method="GET", headers=headers)


def _xml_text(element: ET.Element, name: str) -> str:
    child = element.find(f"{{*}}{name}")
    return child.text if child is not None and child.text is not None else ""


def _safe_namespace(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return sanitized[:80] or "<root>"


def inventory_s3(
    *,
    endpoint_url: str,
    bucket: str,
    prefix: str,
    access_key: str,
    secret_key: str,
    region: str,
    timeout: float = 10.0,
    max_pages: int = 1000,
    http_send: Callable[[Request], bytes] | None = None,
) -> dict[str, Any]:
    role = "derived_object_payload_store_not_raw_report_archive"
    if not endpoint_url or not bucket or not access_key or not secret_key:
        return _availability(role, status="not_configured", error_code="s3_configuration_incomplete")
    object_count = 0
    size_bytes = 0
    namespace_counts: Counter[str] = Counter()
    research_namespace_objects = 0
    continuation_token = ""
    pages = 0
    normalized_prefix = prefix.strip("/")
    query_prefix = f"{normalized_prefix}/" if normalized_prefix else ""
    try:
        while True:
            if pages >= max_pages:
                raise RuntimeError(f"S3 inventory exceeded max_pages={max_pages}")
            request = _s3_list_request(
                endpoint_url=endpoint_url,
                bucket=bucket,
                prefix=query_prefix,
                continuation_token=continuation_token,
                access_key=access_key,
                secret_key=secret_key,
                region=region,
            )
            if http_send is not None:
                raw = http_send(request)
            else:
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read()
            root = ET.fromstring(raw)
            pages += 1
            for item in root.findall(".//{*}Contents"):
                key = _xml_text(item, "Key")
                raw_size = _xml_text(item, "Size")
                item_size = int(raw_size or 0)
                relative_key = key[len(query_prefix) :] if query_prefix and key.startswith(query_prefix) else key
                namespace = _safe_namespace(relative_key.split("/", 1)[0])
                namespace_counts[namespace] += 1
                if RESEARCH_OBJECT_NAMESPACE_PATTERN.match(namespace):
                    research_namespace_objects += 1
                object_count += 1
                size_bytes += item_size
            truncated = _xml_text(root, "IsTruncated").strip().lower() == "true"
            continuation_token = _xml_text(root, "NextContinuationToken")
            if not truncated:
                break
            if not continuation_token:
                raise RuntimeError("S3 response is truncated but has no continuation token")

        top_namespaces = dict(namespace_counts.most_common(50))
        return {
            **_availability(role),
            "backend": "s3",
            "endpoint": _safe_endpoint(endpoint_url),
            "bucket": bucket,
            "prefix": normalized_prefix,
            "expected_grain": "zero-or-more derived objects per ingested document or generated artifact",
            "counts": {
                "objects": object_count,
                "research_named_namespace_objects": research_namespace_objects,
                "namespaces": len(namespace_counts),
                "pages_scanned": pages,
            },
            "size_bytes": size_bytes,
            "top_namespace_counts": top_namespaces,
            "comparison_boundary": "Object count is not expected to equal raw report, document, evidence, or search-record count.",
        }
    except Exception as exc:  # noqa: BLE001 - audit must report partial availability
        return {
            **_availability(
                role,
                status="unavailable",
                error_code="list_failed",
                error=_sanitize_error(exc, [access_key, secret_key]),
            ),
            "backend": "s3",
            "endpoint": _safe_endpoint(endpoint_url),
            "bucket": bucket,
            "prefix": normalized_prefix,
        }


def inventory_local_object_store(root: Path) -> dict[str, Any]:
    role = "derived_object_payload_store_not_raw_report_archive"
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return {
            **_availability(role, status="unavailable", error_code="root_not_found"),
            "backend": "local",
            "root": str(root),
        }
    count = 0
    size_bytes = 0
    namespaces: Counter[str] = Counter()
    unreadable = 0
    for directory, _subdirectories, filenames in os.walk(root, followlinks=False):
        for filename in filenames:
            path = Path(directory) / filename
            try:
                stat = path.stat(follow_symlinks=False)
            except OSError:
                unreadable += 1
                continue
            relative = path.relative_to(root)
            namespaces[_safe_namespace(relative.parts[0] if relative.parts else "<root>")] += 1
            count += 1
            size_bytes += int(stat.st_size)
    return {
        **_availability(role),
        "backend": "local",
        "root": str(root),
        "expected_grain": "zero-or-more derived objects per ingested document or generated artifact",
        "counts": {"objects": count, "namespaces": len(namespaces), "unreadable_metadata": unreadable},
        "size_bytes": size_bytes,
        "top_namespace_counts": dict(namespaces.most_common(50)),
        "comparison_boundary": "Object count is not expected to equal raw report, document, evidence, or search-record count.",
    }


def load_historical_baseline(path: Path | None) -> dict[str, Any]:
    role = "historical_acceptance_evidence_not_current_source_of_truth"
    if path is None:
        return _availability(role, status="not_configured", error_code="artifact_not_supplied")
    path = path.expanduser().resolve()
    if not path.exists():
        return {
            **_availability(role, status="unavailable", error_code="artifact_not_found"),
            "artifact": str(path),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values: list[int] = []
        aggregate = payload.get("aggregate_counts") or []
        if aggregate and isinstance(aggregate[0], str):
            values = [int(item) for item in aggregate[0].split("|") if str(item).strip().isdigit()]
        counts = {
            "research_reports": values[0] if len(values) > 0 else 0,
            "research_documents": values[1] if len(values) > 1 else 0,
            "research_report_citation_evidence": values[2] if len(values) > 2 else 0,
        }
        generated_at = str(payload.get("generated_at") or "")
        age_days: float | None = None
        if generated_at:
            generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            age_days = round((datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() / 86400, 2)
        return {
            **_availability(role),
            "artifact": str(path),
            "generated_at": generated_at,
            "age_days": age_days,
            "reported_counts": counts,
            "confidence": "medium",
            "limitation": "Historical acceptance evidence proves a prior observed state, not current persistence or recoverability.",
        }
    except Exception as exc:  # noqa: BLE001 - malformed evidence is a reportable finding
        return {
            **_availability(role, status="unavailable", error_code="artifact_invalid", error=_sanitize_error(exc)),
            "artifact": str(path),
        }


def inspect_backup_manifest(path: Path | None) -> dict[str, Any]:
    role = "rollback_safety_evidence"
    if path is None:
        return _availability(role, status="not_configured", error_code="manifest_not_supplied")
    path = path.expanduser().resolve()
    if not path.exists():
        return {
            **_availability(role, status="unavailable", error_code="manifest_not_found"),
            "manifest": str(path),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        manifest_dump_path = Path(str(payload.get("dump_path") or ""))
        dump_candidates = [manifest_dump_path]
        if manifest_dump_path.name:
            dump_candidates.append(path.parent / manifest_dump_path.name)
        dump_path = next((candidate for candidate in dump_candidates if candidate.is_file()), manifest_dump_path)
        source_counts = payload.get("source_counts") if isinstance(payload.get("source_counts"), Mapping) else {}
        restored_counts = payload.get("restored_counts") if isinstance(payload.get("restored_counts"), Mapping) else {}
        collection_counts = payload.get("collection_counts") if isinstance(payload.get("collection_counts"), Mapping) else {}
        restored_collection_counts = (
            payload.get("restored_collection_counts")
            if isinstance(payload.get("restored_collection_counts"), Mapping)
            else {}
        )
        report_count_recorded = "research_reports" in collection_counts
        return {
            **_availability(role),
            "manifest": str(path),
            "classification": str(payload.get("classification") or ""),
            "generated_at": str(payload.get("generated_at") or ""),
            "retained_until": str(payload.get("retained_until") or ""),
            "restore_verified": bool(payload.get("restore_verified")),
            "dump_exists": dump_path.is_file(),
            "dump_path_resolution": (
                "manifest_path" if dump_path == manifest_dump_path else "manifest_sibling_relocated_environment"
            ),
            "dump_size_matches_manifest": bool(
                dump_path.is_file() and dump_path.stat().st_size == int(payload.get("dump_size_bytes") or -1)
            ),
            "source_restore_counts_match": bool(source_counts and dict(source_counts) == dict(restored_counts)),
            "collection_restore_counts_match": bool(
                collection_counts and dict(collection_counts) == dict(restored_collection_counts)
            ),
            "research_collection_count_recorded": report_count_recorded,
            "research_report_count_in_backup": int(collection_counts.get("research_reports", 0)) if report_count_recorded else None,
            "contains_sensitive_data": bool(payload.get("contains_sensitive_data")),
            "acceptable_for_non_local_release": bool(payload.get("acceptable_for_non_local_release")),
            "limitation": "A restore-verified database dump is not proof that the historical research-report collection is present unless collection-level counts were recorded.",
        }
    except Exception as exc:  # noqa: BLE001 - malformed evidence is a reportable finding
        return {
            **_availability(role, status="unavailable", error_code="manifest_invalid", error=_sanitize_error(exc)),
            "manifest": str(path),
        }


def _finding(
    finding_id: str,
    severity: str,
    confidence: str,
    dimension: str,
    what_failed: str,
    evidence: Mapping[str, Any],
    why_it_matters: str,
    likely_cause: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "confidence": confidence,
        "dimension": dimension,
        "what_failed": what_failed,
        "evidence": dict(evidence),
        "why_it_matters": why_it_matters,
        "likely_cause": likely_cause,
        "next_action": next_action,
    }


def analyze_reconciliation(
    *,
    filesystem: Mapping[str, Any],
    filesystem_ids_by_alias: Mapping[str, set[str]],
    postgres: Mapping[str, Any],
    postgres_report_ids: set[str],
    opensearch: Mapping[str, Any],
    object_store: Mapping[str, Any],
    historical_baseline: Mapping[str, Any],
    backup: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for store_name, store, severity in (
        ("filesystem", filesystem, "critical"),
        ("postgres", postgres, "critical"),
        ("opensearch", opensearch, "medium"),
        ("object_store", object_store, "medium"),
    ):
        if store.get("availability") not in {"available"}:
            findings.append(
                _finding(
                    f"{store_name}_unavailable",
                    severity,
                    "high",
                    "availability",
                    f"{store_name} could not be inventoried.",
                    {"availability": store.get("availability"), "error_code": store.get("error_code", "")},
                    "The multi-store audit is partial and cannot establish a complete recovery boundary.",
                    "Configuration, connectivity, or local path availability is incomplete.",
                    "Restore read-only access and rerun this audit before any recovery action.",
                )
            )

    raw_count = int(filesystem.get("counts", {}).get("eligible_report_files", 0) or 0)
    pg_count = int(postgres.get("collection_counts", {}).get("research_reports", 0) or 0)
    best_alias = ""
    best_match_count = 0
    if postgres.get("availability") == "available" and filesystem.get("availability") == "available":
        for alias, expected_ids in filesystem_ids_by_alias.items():
            match_count = len(expected_ids & postgres_report_ids)
            if match_count > best_match_count or not best_alias:
                best_alias = alias
                best_match_count = match_count
        identity_coverage = round(best_match_count / max(1, raw_count), 6)
        if raw_count != pg_count or best_match_count != raw_count:
            findings.append(
                _finding(
                    "raw_registry_drift",
                    "critical",
                    "high",
                    "completeness_and_identity",
                    "Raw report files and PostgreSQL research-report assets do not reconcile.",
                    {
                        "raw_eligible_files": raw_count,
                        "postgres_research_reports": pg_count,
                        "best_logical_root_alias": best_alias,
                        "matching_deterministic_ids": best_match_count,
                        "identity_coverage_rate": identity_coverage,
                    },
                    "Research workflows can report zero coverage while the local raw archive still exists.",
                    "Registry loss, migration drift, or connection to a different database is more likely than source-file loss.",
                    "Create a collection-aware backup, generate an exact idempotent recovery manifest, and test a bounded pilot without deleting raw files or the search index.",
                )
            )

    historical_count = int(historical_baseline.get("reported_counts", {}).get("research_reports", 0) or 0)
    if historical_baseline.get("availability") == "available" and postgres.get("availability") == "available" and historical_count != pg_count:
        findings.append(
            _finding(
                "historical_registry_regression",
                "critical" if historical_count > pg_count else "high",
                "medium",
                "temporal_volume",
                "Current PostgreSQL research-report count differs from historical completion evidence.",
                {
                    "historical_report_count": historical_count,
                    "current_report_count": pg_count,
                    "historical_generated_at": historical_baseline.get("generated_at", ""),
                },
                "Previously accepted research coverage is no longer reproducible from the current registry.",
                "The historical artifact may describe an earlier database state or a database that was replaced without collection-level migration evidence.",
                "Locate a backup containing collection-level research-report counts or rebuild conservatively from the unchanged raw archive.",
            )
        )

    if postgres.get("availability") == "available":
        integrity = postgres.get("referential_integrity", {})
        missing_documents = int(integrity.get("report_document_ids_missing_document", 0) or 0)
        missing_citation_documents = int(integrity.get("citation_document_ids_missing_document", 0) or 0)
        if missing_documents or missing_citation_documents:
            findings.append(
                _finding(
                    "postgres_referential_drift",
                    "high",
                    "high",
                    "referential_integrity",
                    "Research-report, document, and citation references are not internally complete.",
                    {
                        "report_document_ids_missing_document": missing_documents,
                        "citation_document_ids_missing_document": missing_citation_documents,
                    },
                    "Research evidence cannot be traced back to the expected document layer.",
                    "Partial writes or incomplete migration/backfill may have separated related collections.",
                    "Repair only from an explicit report/document/evidence manifest with pre/post referential checks.",
                )
            )

    os_report_count = int(opensearch.get("resource_type_counts", {}).get("research_report", 0) or 0)
    if opensearch.get("availability") == "available" and postgres.get("availability") == "available" and os_report_count != pg_count:
        findings.append(
            _finding(
                "search_projection_drift",
                "high",
                "high",
                "derived_projection_consistency",
                "OpenSearch research-report projections differ from the PostgreSQL workflow registry.",
                {"opensearch_research_report_projections": os_report_count, "postgres_research_reports": pg_count},
                "Search results may expose stale or incomplete derived records and cannot be used as recovery truth.",
                "OpenSearch is a rebuildable projection whose last successful sync may predate the registry drift.",
                "Preserve the index for forensic comparison; rebuild it only after the PostgreSQL registry is restored and exact IDs are validated.",
            )
        )

    backup_has_report_count = bool(backup.get("research_collection_count_recorded"))
    backup_report_count = backup.get("research_report_count_in_backup")
    backup_protects_current_reports = bool(
        backup.get("availability") == "available"
        and backup.get("restore_verified")
        and backup.get("dump_exists")
        and backup.get("dump_size_matches_manifest")
        and backup.get("source_restore_counts_match")
        and backup.get("collection_restore_counts_match")
        and backup_has_report_count
        and int(backup_report_count or 0) >= pg_count
    )
    backup_protects_reports = bool(
        backup_protects_current_reports
        and (historical_count == 0 or int(backup_report_count or 0) >= historical_count)
    )
    if backup.get("availability") == "available" and not backup_protects_reports:
        findings.append(
            _finding(
                "backup_research_coverage_unproven",
                "high",
                "high",
                "recoverability",
                "The supplied backup does not prove that the expected research-report collection can be restored.",
                {
                    "restore_verified": bool(backup.get("restore_verified")),
                    "dump_exists": bool(backup.get("dump_exists")),
                    "research_collection_count_recorded": backup_has_report_count,
                    "research_report_count_in_backup": backup_report_count,
                },
                "A general database restore can succeed while still restoring the already-drifted zero-report state.",
                (
                    "The backup captures the already-drifted current registry but does not contain the historical research state."
                    if backup_protects_current_reports
                    else "The backup does not provide a restore-matched research collection snapshot of the current registry."
                ),
                (
                    "Use the current-state backup only as rollback evidence for a disposable clone pilot; historical coverage "
                    "must be rebuilt from the preserved raw archive or proven by an older collection-aware backup."
                ),
            )
        )

    availability_values = [
        filesystem.get("availability"),
        postgres.get("availability"),
        opensearch.get("availability"),
        object_store.get("availability"),
    ]
    audit_status = "complete" if all(value == "available" for value in availability_values) else "partial"
    if all(value != "available" for value in availability_values):
        audit_status = "failed"
    highest = max((item["severity"] for item in findings), key=lambda value: SEVERITY_ORDER[value], default="none")
    reconciliation = {
        "audit_status": audit_status,
        "reconciliation_status": "drift_detected" if findings else "consistent_within_checked_boundaries",
        "highest_severity": highest,
        "finding_count": len(findings),
        "critical_finding_count": sum(1 for item in findings if item["severity"] == "critical"),
        "high_finding_count": sum(1 for item in findings if item["severity"] == "high"),
    }

    raw_and_registry_available = filesystem.get("availability") == "available" and postgres.get("availability") == "available"
    recovery = {
        "safe_to_delete_raw_reports": False,
        "safe_to_delete_search_index": False,
        "safe_to_treat_opensearch_as_source_of_truth": False,
        "automatic_recovery_authorized": False,
        "backup_protects_current_research_state": backup_protects_current_reports,
        "backup_protects_expected_research_state": backup_protects_reports,
        "recovery_readiness": (
            "manual_review_required"
            if raw_and_registry_available and backup_protects_reports
            else (
                "clone_pilot_review_required"
                if raw_and_registry_available and backup_protects_current_reports
                else "blocked_missing_collection_aware_rollback_evidence"
            )
        ),
        "safe_next_actions": [
            "Retain the raw report directory and current OpenSearch index unchanged as forensic inputs.",
            "Create or locate a restore-verified PostgreSQL backup with explicit per-collection counts and deterministic report-ID samples.",
            "Generate an idempotent raw-file-to-report/document/evidence recovery manifest and prove zero ID collisions before writes.",
            "Run a bounded pilot in a cloned database, validate report/document/evidence referential integrity, then rerun this audit.",
            "Rebuild OpenSearch only after PostgreSQL becomes the validated current workflow source of truth.",
        ],
        "prohibited_inferences": [
            "Count equality alone does not make deletion safe.",
            "OpenSearch live-document count is not a report count unless filtered to resource_type=research_report.",
            "Object-store object count is not expected to equal any raw or relational count.",
            "A restore-verified current-state backup may preserve the already-drifted state and is not historical coverage proof.",
        ],
    }
    return findings, reconciliation, recovery


def build_report(
    *,
    filesystem: Mapping[str, Any],
    filesystem_ids_by_alias: Mapping[str, set[str]],
    postgres: Mapping[str, Any],
    postgres_report_ids: set[str],
    opensearch: Mapping[str, Any],
    object_store: Mapping[str, Any],
    historical_baseline: Mapping[str, Any],
    backup: Mapping[str, Any],
) -> dict[str, Any]:
    findings, reconciliation, recovery = analyze_reconciliation(
        filesystem=filesystem,
        filesystem_ids_by_alias=filesystem_ids_by_alias,
        postgres=postgres,
        postgres_report_ids=postgres_report_ids,
        opensearch=opensearch,
        object_store=object_store,
        historical_baseline=historical_baseline,
        backup=backup,
    )
    return {
        "schema_version": "research-report-state-reconciliation-v1",
        "generated_at": utc_iso(),
        "classification": "local-only",
        "owner_group": "Data and Evidence",
        "related_task": "T-604",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
        "mode": "read_only_dry_run",
        "mutation_guard": {
            "database_writes": False,
            "object_store_writes": False,
            "search_index_writes": False,
            "filesystem_content_hashing": False,
            "filesystem_mutation": False,
        },
        "grain_and_authority": [
            {"store": "filesystem", "grain": "raw report file", "role": "authoritative raw archive"},
            {"store": "postgres", "grain": "workflow asset/document/citation record", "role": "authoritative current workflow state"},
            {"store": "opensearch", "grain": "resource projection", "role": "derived and rebuildable"},
            {"store": "object_store", "grain": "stored document/artifact payload", "role": "derived payload store"},
        ],
        "summary": reconciliation,
        "stores": {
            "filesystem": dict(filesystem),
            "postgres": dict(postgres),
            "opensearch": dict(opensearch),
            "object_store": dict(object_store),
        },
        "historical_baseline": dict(historical_baseline),
        "backup_evidence": dict(backup),
        "findings": findings,
        "recovery_assessment": recovery,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only inventory and reconciliation for raw research reports, PostgreSQL, OpenSearch, and object storage."
    )
    parser.add_argument("--filesystem-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS))
    parser.add_argument(
        "--registry-root-alias",
        action="append",
        default=[],
        help="Logical root used when report IDs were registered; repeat for multiple historical mount paths.",
    )
    parser.add_argument("--postgres-dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", ""))
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--opensearch-url", default=os.environ.get("AI_QUANT_OPENSEARCH_URL", ""))
    parser.add_argument("--opensearch-index", default=os.environ.get("AI_QUANT_OPENSEARCH_INDEX", "ai_quant_research"))
    parser.add_argument(
        "--opensearch-user",
        default=os.environ.get("AI_QUANT_OPENSEARCH_USER", os.environ.get("AI_QUANT_OPENSEARCH_USERNAME", "")),
    )
    parser.add_argument("--opensearch-password", default=os.environ.get("AI_QUANT_OPENSEARCH_PASSWORD", ""))
    parser.add_argument("--skip-opensearch", action="store_true")
    parser.add_argument(
        "--object-store-backend",
        choices=("auto", "local", "s3", "skip"),
        default="auto",
    )
    parser.add_argument("--local-object-root", type=Path, default=Path(os.environ.get("AI_QUANT_OBJECT_STORE", "data/objects")))
    parser.add_argument("--s3-endpoint", default=os.environ.get("AI_QUANT_S3_ENDPOINT", ""))
    parser.add_argument("--s3-bucket", default=os.environ.get("AI_QUANT_S3_BUCKET", ""))
    parser.add_argument("--s3-prefix", default=os.environ.get("AI_QUANT_S3_PREFIX", ""))
    parser.add_argument("--s3-region", default=os.environ.get("AI_QUANT_S3_REGION", "us-east-1"))
    parser.add_argument("--s3-access-key", default=os.environ.get("AI_QUANT_S3_ACCESS_KEY", ""))
    parser.add_argument("--s3-secret-key", default=os.environ.get("AI_QUANT_S3_SECRET_KEY", ""))
    parser.add_argument("--s3-max-pages", type=int, default=1000)
    parser.add_argument("--baseline-artifact", type=Path, default=DEFAULT_BASELINE_ARTIFACT)
    parser.add_argument("--backup-manifest", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    extensions = _normalize_extensions(args.extensions.split(","))
    aliases = list(args.registry_root_alias)
    if not aliases:
        aliases.append(os.environ.get("AI_QUANT_RESEARCH_REPORT_API_ROOT", DEFAULT_REGISTRY_ROOT))
    filesystem, filesystem_ids = inventory_filesystem(
        args.filesystem_root,
        extensions=extensions,
        registry_root_aliases=aliases,
    )

    if args.skip_postgres:
        postgres, postgres_ids = _availability(
            "authoritative_workflow_registry_and_citation_state",
            status="not_configured",
            error_code="skipped_by_operator",
        ), set()
    else:
        postgres, postgres_ids = inventory_postgres(
            args.postgres_dsn,
            connect_timeout=args.timeout_seconds,
        )

    if args.skip_opensearch:
        opensearch = _availability(
            "derived_rebuildable_search_projection",
            status="not_configured",
            error_code="skipped_by_operator",
        )
    else:
        opensearch = inventory_opensearch(
            args.opensearch_url,
            args.opensearch_index,
            username=args.opensearch_user,
            password=args.opensearch_password,
            timeout=args.timeout_seconds,
        )

    backend = args.object_store_backend
    if backend == "auto":
        configured = os.environ.get("AI_QUANT_OBJECT_STORE_BACKEND", "").strip().lower()
        backend = configured or ("s3" if args.s3_endpoint and args.s3_bucket else "local")
    if backend == "skip":
        object_store = _availability(
            "derived_object_payload_store_not_raw_report_archive",
            status="not_configured",
            error_code="skipped_by_operator",
        )
    elif backend == "s3":
        object_store = inventory_s3(
            endpoint_url=args.s3_endpoint,
            bucket=args.s3_bucket,
            prefix=args.s3_prefix,
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_region,
            timeout=args.timeout_seconds,
            max_pages=max(1, args.s3_max_pages),
        )
    else:
        object_store = inventory_local_object_store(args.local_object_root)

    baseline = load_historical_baseline(args.baseline_artifact)
    backup = inspect_backup_manifest(args.backup_manifest)
    report = build_report(
        filesystem=filesystem,
        filesystem_ids_by_alias=filesystem_ids,
        postgres=postgres,
        postgres_report_ids=postgres_ids,
        opensearch=opensearch,
        object_store=object_store,
        historical_baseline=baseline,
        backup=backup,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 2 if report["summary"]["audit_status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
