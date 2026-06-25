from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_HOST_ROOT = os.getenv(
    "AI_QUANT_COMPANY_MATERIAL_INBOX",
    str(Path(os.getenv("AI_QUANT_HOST_COMPANY_MATERIAL_ROOT", "/home/xionglei/文档/company_materials")) / "inbox"),
)
DEFAULT_OUTPUT = Path("artifacts/company-material-inbox-ingest.json")
DEFAULT_FIELDS = [
    "business_summary",
    "products",
    "website_url",
    "ir_url",
    "headquarters",
    "employee_count",
    "management",
    "key_customers",
    "key_suppliers",
    "period",
    "revenue",
    "net_income",
    "gross_margin",
    "cash",
    "debt",
]
ALLOWED_SOURCE_TYPES = {
    "company_ir",
    "company_official",
    "official_public",
    "issuer_disclosure",
    "exchange_disclosure",
    "regulatory",
    "public_company_disclosure",
}
DISALLOWED_SOURCE_TYPES = {"research_report", "broker_research", "local_reference", "manual_reference", "news", "curated_public_profile"}
ALLOWED_DOCUMENT_TYPES = {
    "annual_report",
    "10-K",
    "10-Q",
    "8-K",
    "20-F",
    "6-K",
    "prospectus",
    "registration_statement",
    "company_announcement",
    "official_product_page",
    "official_business_overview",
    "official_governance_page",
    "presentation",
    "transcript",
    "webcast",
}
DEFAULT_EXTENSIONS = [".txt", ".md", ".html", ".htm"]
DEFAULT_RIGHTS_TAG = {
    "license_class": "public_company_ir_reference",
    "training_allowed": False,
    "redistribution_allowed": False,
    "display_use": "allowed",
    "non_display_use": "restricted",
    "derived_data_use": "restricted",
}


class ApiRequestError(RuntimeError):
    def __init__(self, method: str, path: str, payload: dict[str, Any]):
        super().__init__(f"{method} {path} failed: {payload}")
        self.method = method
        self.path = path
        self.payload = payload


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Role": "platform",
                "X-Actor": "company_material_inbox_ingest",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        if not payload.get("success"):
            raise ApiRequestError(method, path, payload)
        return payload["data"]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id_part(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned[:40] or "unknown"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_records(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict) and isinstance(payload.get("documents"), list):
        shared = {key: value for key, value in payload.items() if key != "documents"}
        records = [{**shared, **dict(item)} for item in payload["documents"] if isinstance(item, dict)]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise ValueError("manifest must be an object, an object with documents, or a list of objects")
    return [dict(record, manifest_path=str(path)) for record in records]


def _iter_manifest_records(root: Path, manifest_glob: str, *, scan_limit: int) -> Iterable[dict[str, Any]]:
    count = 0
    for manifest_path in sorted(root.rglob(manifest_glob)):
        for record in _manifest_records(manifest_path):
            count += 1
            if count > scan_limit:
                return
            yield record


def _resolve_material_path(root: Path, manifest_path: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    near_manifest = manifest_path.parent / candidate
    if near_manifest.exists():
        return near_manifest
    return root / candidate


def _rights_tag(record: dict[str, Any]) -> dict[str, Any]:
    rights = record.get("rights_tag") or {}
    merged = dict(DEFAULT_RIGHTS_TAG)
    merged.update(rights)
    merged["training_allowed"] = bool(merged.get("training_allowed", False))
    merged["redistribution_allowed"] = bool(merged.get("redistribution_allowed", False))
    return merged


def _source_payload(record: dict[str, Any], rights_tag: dict[str, Any]) -> dict[str, Any]:
    document_type = str(record["document_type"]).strip()
    allowed_types = record.get("allowed_document_types") or sorted(ALLOWED_DOCUMENT_TYPES)
    return {
        "source_id": str(record["source_id"]).strip(),
        "source_type": str(record["source_type"]).strip(),
        "description": str(record.get("source_description") or "Local company official/IR material inbox source."),
        "risk_level": str(record.get("risk_level") or "green"),
        "allowed_document_types": [str(item).strip() for item in allowed_types if str(item).strip()],
        "provenance_ref": str(record.get("provenance_ref") or record.get("source_uri") or record.get("source_home") or ""),
        "source_tos_uri": str(record.get("source_tos_uri", "")),
        "usage_scope": str(
            record.get("usage_scope")
            or "company_official_ir_local_inbox_fact_backfill_only_no_training_no_live_trading"
        ),
        "collection_method": str(record.get("collection_method") or "local_manifest_sidecar_official_public_material"),
        "robots_policy": str(record.get("robots_policy") or "reviewed_public_or_local_source"),
        "review_owner_role": str(record.get("review_owner_role") or "数据工程"),
        "rights_tag": rights_tag,
    }


def _document_payload(record: dict[str, Any], material_path: Path, body: str, rights_tag: dict[str, Any]) -> dict[str, Any]:
    content_hash = _content_sha256(material_path)
    document_id = str(record.get("document_id") or "").strip()
    if not document_id:
        identity = "|".join(
            [
                str(record.get("issuer_id", "")),
                str(record.get("security_id", "")),
                str(record.get("source_id", "")),
                str(record.get("source_uri", "")),
                content_hash,
            ]
        )
        document_id = f"doc_cmat_{_safe_id_part(str(record.get('issuer_id', 'issuer')))}_{_sha16(identity)}"
    return {
        "document_id": document_id,
        "issuer_id": str(record["issuer_id"]).strip(),
        "security_id": str(record.get("security_id", "")).strip(),
        "document_type": str(record["document_type"]).strip(),
        "source_id": str(record["source_id"]).strip(),
        "source_type": str(record["source_type"]).strip(),
        "source_uri": str(record["source_uri"]).strip(),
        "title": str(record.get("title") or material_path.stem),
        "body": body,
        "content_sha256": content_hash,
        "published_at": record.get("published_at") or utc_iso(),
        "language": str(record.get("language") or "zh"),
        "version": str(record.get("version") or "company-material-inbox-v1"),
        "rights_tag": rights_tag,
    }


def _validate_record(record: dict[str, Any], root: Path, extensions: set[str]) -> tuple[list[str], Path | None]:
    errors: list[str] = []
    for field in ["issuer_id", "source_id", "source_type", "document_type", "source_uri", "file_path"]:
        if not str(record.get(field, "")).strip():
            errors.append(f"missing_{field}")
    source_type = str(record.get("source_type", "")).strip()
    document_type = str(record.get("document_type", "")).strip()
    if source_type in DISALLOWED_SOURCE_TYPES:
        errors.append("disallowed_source_type")
    elif source_type and source_type not in ALLOWED_SOURCE_TYPES:
        errors.append("unsupported_source_type")
    if document_type == "research_report" or document_type in {"broker_research", "news", "manual_reference"}:
        errors.append("disallowed_document_type")
    elif document_type and document_type not in ALLOWED_DOCUMENT_TYPES:
        errors.append("unsupported_document_type")
    rights = _rights_tag(record)
    if rights.get("training_allowed"):
        errors.append("training_allowed_not_permitted")
    manifest_path = Path(str(record.get("manifest_path", "")))
    material_path = None
    if record.get("file_path"):
        material_path = _resolve_material_path(root, manifest_path, str(record["file_path"]))
        if not material_path.exists() or not material_path.is_file():
            errors.append("file_not_found")
        elif material_path.suffix.lower() not in extensions:
            errors.append("unsupported_extension")
    return errors, material_path


def _source_exists(client: ApiClient, source_id: str) -> bool:
    try:
        report = client.request("POST", "/api/governance/sources/report", {"source_id": source_id, "limit": 1})
    except ApiRequestError:
        return False
    return any(row.get("source_id") == source_id for row in report.get("sources", []))


def _document_exists(client: ApiClient, document_id: str) -> bool:
    try:
        client.request("GET", f"/api/ingestion/documents/{document_id}", None)
        return True
    except ApiRequestError:
        return False


def run_company_material_inbox_ingest(
    *,
    base_url: str,
    root_path: str,
    output: Path,
    manifest_glob: str,
    extensions: list[str],
    fields: list[str],
    scan_limit: int,
    execute: bool,
    dry_run: bool,
    require_evidence: bool,
    refresh_existing: bool,
    timeout: float,
) -> dict[str, Any]:
    root = Path(root_path).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    allowed_extensions = {item.strip().lower() for item in extensions if item.strip()}
    client = ApiClient(base_url, timeout=timeout)
    execute = bool(execute and not dry_run)
    items: list[dict[str, Any]] = []
    totals = {
        "manifests_scanned": 0,
        "planned_count": 0,
        "skipped_count": 0,
        "invalid_count": 0,
        "sources_registered": 0,
        "sources_existing": 0,
        "documents_ingested": 0,
        "documents_existing": 0,
        "evidence_extracted": 0,
        "profile_fields_updated": 0,
        "profile_field_assertions_planned_or_written": 0,
        "failed_count": 0,
    }
    seen_sources: set[str] = set()
    for record in _iter_manifest_records(root, manifest_glob, scan_limit=scan_limit):
        totals["manifests_scanned"] += 1
        errors, material_path = _validate_record(record, root, allowed_extensions)
        item = {
            "manifest_path": record.get("manifest_path", ""),
            "file_path": str(material_path) if material_path else str(record.get("file_path", "")),
            "issuer_id": str(record.get("issuer_id", "")),
            "security_id": str(record.get("security_id", "")),
            "source_id": str(record.get("source_id", "")),
            "source_type": str(record.get("source_type", "")),
            "document_type": str(record.get("document_type", "")),
            "source_uri": str(record.get("source_uri", "")),
            "status": "invalid" if errors else ("planned" if not execute else "pending"),
            "errors": errors,
            "document_id": "",
            "evidence_count": 0,
            "fields_updated": 0,
            "profile_field_assertions": 0,
        }
        if errors or material_path is None:
            totals["invalid_count"] += 1
            items.append(item)
            continue
        body = material_path.read_text(encoding=str(record.get("encoding") or "utf-8"), errors="replace")
        rights = _rights_tag(record)
        document = _document_payload(record, material_path, body, rights)
        item["document_id"] = document["document_id"]
        if not execute:
            item["planned_actions"] = ["register_source_if_missing", "ingest_document", "extract_evidence", "extract_profile_fields"]
            totals["planned_count"] += 1
            items.append(item)
            continue
        try:
            source_id = str(record["source_id"]).strip()
            if source_id not in seen_sources:
                if _source_exists(client, source_id):
                    totals["sources_existing"] += 1
                else:
                    client.request("POST", "/api/ingestion/sources", _source_payload(record, rights))
                    totals["sources_registered"] += 1
                seen_sources.add(source_id)
            if _document_exists(client, document["document_id"]):
                totals["documents_existing"] += 1
                item["document_status"] = "exists"
            else:
                client.request("POST", "/api/ingestion/documents", document)
                totals["documents_ingested"] += 1
                item["document_status"] = "ingested"
            evidence = client.request(
                "POST",
                "/api/evidence/extract",
                {
                    "document_id": document["document_id"],
                    "parser_version": "company-material-inbox-v1",
                    "model_version": "rule-company-material-inbox-v1",
                },
            )
            evidence_rows = evidence.get("evidence", [])
            item["evidence_count"] = len(evidence_rows)
            totals["evidence_extracted"] += len(evidence_rows)
            extraction = client.request(
                "POST",
                "/api/company-database/profile-fields/extract",
                {
                    "issuer_ids": [document["issuer_id"]],
                    "document_ids": [document["document_id"]],
                    "fields": fields,
                    "require_evidence": require_evidence,
                    "refresh_existing": refresh_existing,
                    "execute": True,
                },
            )
            profile_totals = extraction.get("totals", {})
            item["fields_updated"] = int(profile_totals.get("fields_updated", 0) or 0)
            item["profile_field_assertions"] = item["fields_updated"]
            totals["profile_fields_updated"] += item["fields_updated"]
            totals["profile_field_assertions_planned_or_written"] += item["profile_field_assertions"]
            item["status"] = "executed"
        except Exception as exc:
            item["status"] = "failed"
            item["errors"] = [str(exc)]
            totals["failed_count"] += 1
        items.append(item)
    totals["skipped_count"] = sum(1 for item in items if item["status"] == "invalid")
    summary = {
        "generated_at": utc_iso(),
        "base_url": base_url,
        "root_path": str(root),
        "manifest_glob": manifest_glob,
        "dry_run": not execute,
        "execute": execute,
        "status": "passed" if totals["failed_count"] == 0 else "failed",
        "fields": fields,
        "totals": totals,
        "items": items,
        "source_rules": {
            "allowed_source_types": sorted(ALLOWED_SOURCE_TYPES),
            "allowed_document_types": sorted(ALLOWED_DOCUMENT_TYPES),
            "disallowed_source_types": sorted(DISALLOWED_SOURCE_TYPES),
            "research_reports": "skipped_opinion_only_not_fact_source",
            "news_and_manual_reference": "skipped_not_fact_source",
        },
        "usage_boundary": "local_company_material_inbox_only_official_ir_public_materials_no_external_download_no_training_no_live_trading",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan local company official/IR material manifests and optionally backfill profile fields.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--root-path", default=DEFAULT_HOST_ROOT, help="Host filesystem inbox path containing *.manifest.json sidecars.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-glob", default="*.manifest.json")
    parser.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS))
    parser.add_argument("--fields", default=",".join(DEFAULT_FIELDS))
    parser.add_argument("--scan-limit", type=int, default=1000)
    parser.add_argument("--execute", action="store_true", help="Register sources/documents, extract evidence and backfill fields. Default is dry-run.")
    parser.add_argument("--allow-document-text-only", action="store_true", help="Allow profile extraction without evidence. Off by default.")
    parser.add_argument("--refresh-existing", action="store_true", help="Overwrite existing company profile fields when new governed evidence is found.")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    fields = [item.strip() for item in args.fields.split(",") if item.strip()]
    extensions = [item.strip() for item in args.extensions.split(",") if item.strip()]
    summary = run_company_material_inbox_ingest(
        base_url=args.base_url,
        root_path=args.root_path,
        output=args.output,
        manifest_glob=args.manifest_glob,
        extensions=extensions,
        fields=fields,
        scan_limit=args.scan_limit,
        execute=args.execute,
        dry_run=not args.execute,
        require_evidence=not args.allow_document_text_only,
        refresh_existing=args.refresh_existing,
        timeout=args.timeout,
    )
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
