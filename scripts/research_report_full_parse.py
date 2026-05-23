#!/usr/bin/env python3
"""Backfill local research reports from metadata-only state into parsed records.

The API incremental scheduler only processes newly discovered files. This script
consumes existing ``indexed`` research report assets, creates their reference
documents, and feeds extracted local text back to the citation extractor.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "app" / "models.py").exists() and Path("/app/app/models.py").exists():
    ROOT = Path("/app")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import AuditEvent, Document, Evidence, Issuer, ManualReviewItem
from app.store import PostgreSQLStore
from app.utils import chunk_text, new_id, utcnow


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_API_ROOT = "/data/local/research_reports"
DEFAULT_HOST_ROOT = "/home/xionglei/文档/6大投行研报汇总"
DEFAULT_FALLBACK_ISSUER_ID = "issuer_local_research_reference"
DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"

SENSITIVE_CONTACT_PATTERNS = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\w)")),
    (
        "secret_literal",
        re.compile(r"\b(api[_-]?key|access[_-]?token|bearer[_-]?token|secret|signature)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})", re.IGNORECASE),
    ),
]


class ApiClient:
    def __init__(self, base_url: str, *, role: str, actor: str, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.role = role
        self.actor = actor
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "X-Role": self.role,
                "X-Actor": self.actor,
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {path} failed: {exc}") from exc
        body = json.loads(raw) if raw else {}
        if isinstance(body, dict) and body.get("success") is False:
            raise RuntimeError(f"{method} {path} failed: {body.get('error') or body}")
        if isinstance(body, dict) and "data" in body:
            data_body = body["data"]
            if isinstance(data_body, dict):
                return data_body
        if not isinstance(body, dict):
            raise RuntimeError(f"{method} {path} returned non-object JSON")
        return body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-root", default=DEFAULT_API_ROOT)
    parser.add_argument("--host-root", default=DEFAULT_HOST_ROOT)
    parser.add_argument("--status", default="indexed", help="research report status to consume")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--max-reports", type=int, default=0, help="0 means no explicit cap")
    parser.add_argument("--citation-char-limit", type=int, default=1200)
    parser.add_argument("--max-text-chars", type=int, default=50000)
    parser.add_argument("--pdf-first-page", type=int, default=1)
    parser.add_argument("--pdf-last-page", type=int, default=1)
    parser.add_argument("--pdftotext-timeout", type=int, default=1)
    parser.add_argument("--ocr-fallback", action="store_true", help="Render PDF pages and run local Tesseract when pdftotext is empty.")
    parser.add_argument("--ocr-first-page", type=int, default=1)
    parser.add_argument("--ocr-last-page", type=int, default=3)
    parser.add_argument("--ocr-dpi", type=int, default=180)
    parser.add_argument("--ocr-lang", default="eng+chi_sim")
    parser.add_argument("--ocr-timeout", type=int, default=30)
    parser.add_argument("--parser-version", default="research-report-full-local-pdftotext-v1")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--fallback-issuer-id", default=DEFAULT_FALLBACK_ISSUER_ID)
    parser.add_argument("--role", default="data_engineer")
    parser.add_argument("--actor", default="research_report_full_parse")
    parser.add_argument("--request-timeout", type=int, default=300)
    parser.add_argument("--output", default="artifacts/research-report-full-parse.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=["direct", "api"], default="direct")
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get("AI_QUANT_DATABASE_URL") or DEFAULT_DSN)
    return parser.parse_args()


def map_api_path_to_host(file_path: str, *, api_root: str, host_root: str) -> Path | None:
    if not file_path:
        return None
    if file_path.startswith(api_root.rstrip("/") + "/"):
        suffix = file_path[len(api_root.rstrip("/")) :].lstrip("/")
        return Path(host_root) / suffix
    path = Path(file_path)
    if path.exists():
        return path
    return None


def extract_pdf_text(path: Path, *, timeout: int, max_chars: int, first_page: int, last_page: int) -> tuple[str, str]:
    if not path.exists():
        return "", "missing_file"
    command = ["pdftotext", "-raw", "-q"]
    if first_page > 0:
        command.extend(["-f", str(first_page)])
    if last_page > 0:
        command.extend(["-l", str(last_page)])
    command.extend([str(path), "-"])
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "", "pdftotext_timeout"
    except OSError as exc:
        return "", f"pdftotext_unavailable:{exc}"
    text = completed.stdout.decode("utf-8", errors="ignore").strip()
    if not text:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()
        return "", reason or f"pdftotext_empty:exit_{completed.returncode}"
    page_scope = f"pages_{first_page}_{last_page}" if first_page > 0 or last_page > 0 else "all_pages"
    return text[:max_chars], f"pdftotext:{page_scope}"


def extract_pdf_ocr_text(
    path: Path,
    *,
    first_page: int,
    last_page: int,
    dpi: int,
    lang: str,
    timeout: int,
    max_chars: int,
) -> tuple[str, str]:
    if not path.exists():
        return "", "ocr_missing_file"
    first_page = max(1, first_page)
    last_page = max(first_page, last_page)
    dpi = max(72, min(300, dpi))
    chunks: list[str] = []
    reasons: list[str] = []
    with tempfile.TemporaryDirectory(prefix="research-report-ocr-") as temp_dir:
        temp_root = Path(temp_dir)
        for page in range(first_page, last_page + 1):
            image_prefix = temp_root / f"page_{page}"
            render_cmd = [
                "pdftoppm",
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                str(dpi),
                "-png",
                "-singlefile",
                str(path),
                str(image_prefix),
            ]
            try:
                rendered = subprocess.run(render_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
            except subprocess.TimeoutExpired:
                reasons.append(f"page_{page}:pdftoppm_timeout")
                continue
            except OSError as exc:
                return "", f"ocr_render_unavailable:{exc}"
            image_path = Path(f"{image_prefix}.png")
            if rendered.returncode != 0 or not image_path.exists():
                detail = rendered.stderr.decode("utf-8", errors="replace").strip()
                reasons.append(f"page_{page}:{detail or f'pdftoppm_exit_{rendered.returncode}'}")
                continue
            ocr_cmd = ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", "6"]
            try:
                ocr = subprocess.run(ocr_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
            except subprocess.TimeoutExpired:
                reasons.append(f"page_{page}:tesseract_timeout")
                continue
            except OSError as exc:
                return "", f"ocr_unavailable:{exc}"
            page_text = ocr.stdout.decode("utf-8", errors="ignore").strip()
            if page_text:
                chunks.append(page_text)
            else:
                detail = ocr.stderr.decode("utf-8", errors="replace").strip()
                reasons.append(f"page_{page}:{detail or f'tesseract_exit_{ocr.returncode}'}")
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
    text = "\n\n".join(chunks).strip()
    if text:
        return text[:max_chars], f"tesseract:pages_{first_page}_{last_page}:dpi_{dpi}"
    return "", "; ".join(reasons)[:500] or "ocr_empty"


def load_reports(client: ApiClient, *, status: str, limit: int) -> dict[str, Any]:
    return client.request("POST", "/api/research-reports", {"status": status, "limit": limit})


def ensure_fallback_issuer(client: ApiClient, issuer_id: str) -> None:
    payload = {
        "issuer_id": issuer_id,
        "legal_name": "Local Research Report Reference Pool",
        "aliases": ["本地研报参考池", "local research report reference pool"],
        "market": ["LOCAL_REFERENCE"],
        "country": "CN",
        "status": "reference_only",
        "sector": "Research",
        "industry": "Local research reports",
        "data_sources": ["local_research_reports"],
    }
    try:
        client.request("POST", "/api/issuers", payload)
    except RuntimeError as exc:
        if "already exists" not in str(exc):
            raise


def ensure_fallback_issuer_direct(store: PostgreSQLStore, issuer_id: str) -> None:
    if issuer_id in store.issuers:
        return
    store.issuers[issuer_id] = Issuer(
        issuer_id=issuer_id,
        legal_name="Local Research Report Reference Pool",
        aliases=["本地研报参考池", "local research report reference pool"],
        market=["LOCAL_REFERENCE"],
        country="CN",
        status="reference_only",
        sector="Research",
        industry="Local research reports",
        data_sources=["local_research_reports"],
    )


def manual_review_id(document_id: str, issue_type: str) -> str:
    raw = f"mrev_{document_id}_{issue_type}"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_").lower()


def citation_limited_text(source_text: str, char_limit: int) -> tuple[str, bool]:
    if len(source_text) <= char_limit:
        return source_text, False
    clipped = source_text[:char_limit].rstrip()
    return f"{clipped}\n[TRUNCATED_FOR_CITATION_BOUNDARY]", True


def mask_sensitive_contact(match: re.Match[str], *, finding_type: str) -> str:
    value = match.group(0)
    if finding_type == "secret_literal":
        key = match.group(1) if match.lastindex else "secret"
        return f"{key}=***REDACTED***"
    if finding_type == "email" and "@" in value:
        local, domain = value.split("@", 1)
        local_mask = f"{local[:1]}***" if local else "***"
        if "." in domain:
            domain_head, domain_tail = domain.rsplit(".", 1)
            domain = f"{domain_head[:1]}***.{domain_tail}"
        else:
            domain = "***"
        return f"{local_mask}@{domain}"
    if finding_type == "cn_mobile" and len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    if finding_type == "cn_id" and len(value) >= 8:
        return f"{value[:4]}**********{value[-4:]}"
    return "***REDACTED***"


def redact_sensitive_contacts(text: str) -> str:
    redacted = text
    for finding_type, pattern in SENSITIVE_CONTACT_PATTERNS:
        redacted = pattern.sub(lambda item, finding_type=finding_type: mask_sensitive_contact(item, finding_type=finding_type), redacted)
    return redacted


def research_report_evidence(document_id: str, text: str) -> list[Evidence]:
    evidence: list[Evidence] = []
    for index, chunk in enumerate(chunk_text(text)[:20]):
        evidence.append(
            Evidence(
                evidence_id=f"evi_{document_id}_research_{index}",
                document_id=document_id,
                section="research_report_citation",
                page_no=index + 1,
                bbox=f"research_report://{document_id};chunk={index}",
                span_text=chunk,
                canonical_text=chunk,
                confidence=0.72,
            )
        )
    return evidence


def audit_event(actor: str, action: str, resource_type: str, resource_id: str, *, source: str = "local_research_reports", version: str = "", approval_state: str = "") -> AuditEvent:
    return AuditEvent(
        event_id=new_id("evt"),
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        source=source,
        version=version,
        approval_state=approval_state,
    )


def report_value(report: Any, name: str, default: Any = "") -> Any:
    if isinstance(report, dict):
        return report.get(name, default)
    return getattr(report, name, default)


def extract_local_text(report: dict[str, Any], *, args: argparse.Namespace) -> tuple[str, str, str]:
    file_type = str(report.get("file_type", "")).lower().lstrip(".")
    host_path = map_api_path_to_host(str(report.get("file_path", "")), api_root=args.api_root, host_root=args.host_root)
    text = ""
    text_source = ""
    if file_type == "pdf" and host_path is not None:
        text, text_source = extract_pdf_text(
            host_path,
            timeout=args.pdftotext_timeout,
            max_chars=args.max_text_chars,
            first_page=args.pdf_first_page,
            last_page=args.pdf_last_page,
        )
        if not text and args.ocr_fallback:
            text, text_source = extract_pdf_ocr_text(
                host_path,
                first_page=args.ocr_first_page,
                last_page=args.ocr_last_page,
                dpi=args.ocr_dpi,
                lang=args.ocr_lang,
                timeout=args.ocr_timeout,
                max_chars=args.max_text_chars,
            )
    elif file_type in {"txt", "md"} and host_path is not None and host_path.exists():
        text = host_path.read_text(encoding="utf-8", errors="ignore")[: args.max_text_chars].strip()
        text_source = "local_text_file" if text else "empty_text_file"
    return text, text_source, str(host_path or "")


def process_report_direct(store: PostgreSQLStore, report: Any, *, args: argparse.Namespace) -> dict[str, Any]:
    document_id = report.document_id or f"doc_{report.report_id}"
    report_dict = {
        "file_type": report.file_type,
        "file_path": report.file_path,
    }
    text, text_source, host_path = extract_local_text(report_dict, args=args)
    if args.dry_run:
        return {
            "report_id": report.report_id,
            "file_name": report.file_name,
            "file_type": report.file_type,
            "host_path": host_path,
            "text_source": text_source,
            "text_chars": len(text),
            "dry_run": True,
        }
    document = store.documents.get(document_id)
    if document is None:
        document = Document(
            document_id=document_id,
            issuer_id=report.issuer_id or args.fallback_issuer_id,
            security_id=report.security_id,
            source_id=report.source_id,
            source_type="local_reference",
            document_type="research",
            source_uri=f"research-report://{report.report_id}",
            object_uri=report.file_path,
            content_sha256=report.content_sha256,
            body="",
            title=report.title,
            rights_tag=report.rights_tag,
            language=args.language,
            version=args.parser_version,
        )
        store.documents[document_id] = document
        ingest_created = True
    else:
        ingest_created = False
    report.document_id = document_id
    report.issuer_id = document.issuer_id
    report.security_id = document.security_id
    if text:
        limited_text, truncated = citation_limited_text(text, args.citation_char_limit)
        limited_text = redact_sensitive_contacts(limited_text)
        document.body = limited_text
        for item in research_report_evidence(document.document_id, limited_text):
            store.evidence[item.evidence_id] = item
        report.status = "text_indexed"
        issue_type = "research_report_text_extraction_required"
        manual_id = manual_review_id(document.document_id, issue_type)
        existing_review = store.manual_reviews.get(manual_id)
        if existing_review:
            existing_review.status = "resolved"
            existing_review.updated_at = utcnow()
        else:
            manual_id = ""
        evidence_count = len(research_report_evidence(document.document_id, limited_text))
    else:
        issue_type = "research_report_text_extraction_required"
        manual_id = manual_review_id(document.document_id, issue_type)
        existing = store.manual_reviews.get(manual_id)
        if existing:
            existing.status = "open"
            existing.severity = "medium"
            existing.parser_version = args.parser_version
            existing.message = "No extractable local research report text is available for citation indexing."
            existing.suggested_action = "Run OCR/text extraction before citing this local research report."
            existing.updated_at = utcnow()
        else:
            store.manual_reviews[manual_id] = ManualReviewItem(
                review_id=manual_id,
                document_id=document.document_id,
                issue_type=issue_type,
                severity="medium",
                parser_version=args.parser_version,
                message="No extractable local research report text is available for citation indexing.",
                suggested_action="Run OCR/text extraction before citing this local research report.",
            )
        report.status = "needs_text_review"
        truncated = False
        evidence_count = 0
    store.research_reports[report.report_id] = report
    store.audit_log.append(audit_event(args.actor, "batch_ingest_research_report", "research_report", report.report_id, version=args.parser_version, approval_state="ingested"))
    store.audit_log.append(audit_event(args.actor, "batch_extract_research_report_text", "research_report", report.report_id, version=args.parser_version, approval_state=report.status))
    return {
        "report_id": report.report_id,
        "file_name": report.file_name,
        "file_type": report.file_type,
        "host_path": host_path,
        "text_source": text_source,
        "text_chars": len(text),
        "ingest_created": ingest_created,
        "status": report.status,
        "evidence_count": evidence_count,
        "manual_review_id": manual_id,
        "citation_truncated": truncated,
    }


def process_report(
    client: ApiClient,
    report: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    report_id = str(report["report_id"])
    file_type = str(report.get("file_type", "")).lower().lstrip(".")
    host_path = map_api_path_to_host(str(report.get("file_path", "")), api_root=args.api_root, host_root=args.host_root)
    text = ""
    text_source = ""
    text_chars = 0
    if file_type == "pdf" and host_path is not None:
        text, text_source = extract_pdf_text(
            host_path,
            timeout=args.pdftotext_timeout,
            max_chars=args.max_text_chars,
            first_page=args.pdf_first_page,
            last_page=args.pdf_last_page,
        )
        text_chars = len(text)
    elif file_type in {"txt", "md"} and host_path is not None and host_path.exists():
        text = host_path.read_text(encoding="utf-8", errors="ignore")[: args.max_text_chars].strip()
        text_source = "local_text_file" if text else "empty_text_file"
        text_chars = len(text)

    if args.dry_run:
        return {
            "report_id": report_id,
            "file_name": report.get("file_name", ""),
            "file_type": file_type,
            "host_path": str(host_path or ""),
            "text_source": text_source,
            "text_chars": text_chars,
            "dry_run": True,
        }

    ingest_payload = {
        "issuer_id": str(report.get("issuer_id") or args.fallback_issuer_id),
        "security_id": str(report.get("security_id") or ""),
        "document_id": str(report.get("document_id") or f"doc_{report_id}"),
        "language": args.language,
        "version": args.parser_version,
    }
    ingest = client.request("POST", f"/api/research-reports/{report_id}/ingest", ingest_payload)
    extract_payload: dict[str, Any] = {
        "citation_char_limit": args.citation_char_limit,
        "parser_version": args.parser_version,
    }
    if text:
        text = redact_sensitive_contacts(text)
        extract_payload["text"] = text
    extract = client.request("POST", f"/api/research-reports/{report_id}/extract", extract_payload)
    return {
        "report_id": report_id,
        "file_name": report.get("file_name", ""),
        "file_type": file_type,
        "host_path": str(host_path or ""),
        "text_source": text_source,
        "text_chars": text_chars,
        "ingest_created": bool(ingest.get("created")),
        "status": extract.get("status"),
        "evidence_count": len(extract.get("evidence", [])),
        "manual_review_id": (extract.get("manual_review") or {}).get("review_id", ""),
    }


def main() -> int:
    args = parse_args()
    client = ApiClient(args.base_url, role=args.role, actor=args.actor, timeout=args.request_timeout)
    store = PostgreSQLStore(args.dsn) if args.mode == "direct" else None
    if not args.dry_run:
        if store is not None:
            ensure_fallback_issuer_direct(store, args.fallback_issuer_id)
        else:
            ensure_fallback_issuer(client, args.fallback_issuer_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    processed = 0
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "status_filter": args.status,
        "api_root": args.api_root,
        "host_root": args.host_root,
        "dry_run": args.dry_run,
        "batches": [],
        "totals": {
            "processed": 0,
            "text_indexed": 0,
            "needs_text_review": 0,
            "errors": 0,
            "text_extracted": 0,
            "manual_review": 0,
        },
    }
    for batch_index in range(1, args.max_batches + 1):
        if args.max_reports and processed >= args.max_reports:
            break
        remaining_limit = args.batch_size
        if args.max_reports:
            remaining_limit = min(remaining_limit, args.max_reports - processed)
        if store is not None:
            reports = [item for item in store.research_reports.values() if item.status == args.status]
            reports.sort(key=lambda item: (item.status, item.year, item.month, item.broker, item.file_name), reverse=True)
            reports = reports[:remaining_limit]
        else:
            payload = load_reports(client, status=args.status, limit=remaining_limit)
            reports = list(payload.get("reports", []))
        if not reports:
            break
        batch = {"batch": batch_index, "input_count": len(reports), "results": [], "errors": []}
        for report in reports:
            try:
                result = process_report_direct(store, report, args=args) if store is not None else process_report(client, report, args=args)
                batch["results"].append(result)
                processed += 1
                manifest["totals"]["processed"] += 1
                if result.get("text_chars", 0) > 0:
                    manifest["totals"]["text_extracted"] += 1
                if result.get("status") == "text_indexed":
                    manifest["totals"]["text_indexed"] += 1
                if result.get("status") == "needs_text_review":
                    manifest["totals"]["needs_text_review"] += 1
                if result.get("manual_review_id"):
                    manifest["totals"]["manual_review"] += 1
                print(
                    json.dumps(
                        {
                            "report": report_value(report, "report_id", ""),
                            "status": result.get("status", "dry_run"),
                            "text_chars": result.get("text_chars", 0),
                            "source": result.get("text_source", ""),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 - batch artifact must preserve per-report failures
                manifest["totals"]["errors"] += 1
                batch["errors"].append({"report_id": report_value(report, "report_id", ""), "error": str(exc)})
        manifest["batches"].append(batch)
        output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(
            json.dumps(
                {
                    "batch": batch_index,
                    "processed_total": manifest["totals"]["processed"],
                    "text_indexed": manifest["totals"]["text_indexed"],
                    "needs_text_review": manifest["totals"]["needs_text_review"],
                    "errors": manifest["totals"]["errors"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if batch["errors"] and len(batch["errors"]) == len(reports):
            break
    if store is not None and not args.dry_run:
        store.commit()
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 1 if manifest["totals"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
