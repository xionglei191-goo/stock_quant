from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.connectors import ConnectorDocument
from app.services import DEFAULT_SEC_USER_AGENT, SystemService, TERM_LEXICON
from app.utils import pdf_bytes_to_text


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._-")[:120] or "sample"


def _has_supported_terms(text: str) -> bool:
    lowered = text.lower()
    return any(alias.lower() in lowered for aliases in TERM_LEXICON.values() for alias in aliases)


def _to_plain_attachment_text(data: bytes) -> str:
    if data.startswith(b"\x1f\x8b"):
        try:
            data = zlib.decompress(data, zlib.MAX_WBITS | 16)
        except zlib.error:
            pass
    text = pdf_bytes_to_text(data)
    if data.startswith(b"%PDF") and not text.strip():
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "attachment.pdf"
            txt_path = Path(tmpdir) / "attachment.txt"
            pdf_path.write_bytes(data)
            try:
                subprocess.run(["pdftotext", "-layout", str(pdf_path), str(txt_path)], check=True, capture_output=True, timeout=20)
                text = txt_path.read_text(encoding="utf-8", errors="replace")
            except (FileNotFoundError, subprocess.SubprocessError, OSError):
                text = ""
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    if "denied by bot" in text.lower() or "forbidden" in text.lower():
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fetch_attachment_text(
    service: SystemService,
    *,
    market: str,
    source_uri: str,
    user_agent: str,
    max_bytes: int,
) -> str:
    if not source_uri:
        return ""
    data = service.connectors.fetch_document_binary(market, source_uri, user_agent=user_agent, max_bytes=max_bytes)
    return _to_plain_attachment_text(data)


def _write_document(output_dir: Path, prefix: str, key: str, document: Mapping[str, Any], body: str) -> dict[str, Any]:
    language = str(document.get("language", "mixed") or "mixed")
    document_type = str(document.get("document_type", "document") or "document")
    title = str(document.get("title", "") or "")
    source_uri = str(document.get("source_uri", "") or "")
    published_at = str(document.get("published_at", "") or "")
    metadata = document.get("metadata", {})
    text = "\n".join(
        [
            f"Title: {title}",
            f"Document-Type: {document_type}",
            f"Language: {language}",
            f"Published-At: {published_at}",
            f"Source-URI: {source_uri}",
            "",
            body.strip(),
            "",
        ]
    ).strip() + "\n"
    file_name = f"{prefix}_{_slug(key)}.txt"
    path = output_dir / file_name
    _atomic_write_text(path, text)
    return {
        "path": str(path),
        "language": language,
        "document_type": document_type,
        "title": title,
        "source_uri": source_uri,
        "published_at": published_at,
        "char_count": len(body),
        "has_supported_terms": _has_supported_terms(body),
        "metadata": metadata if isinstance(metadata, Mapping) else {},
    }


def _ensure_demo_security(service: SystemService, issuer_id: str, security_id: str, *, ticker: str, market: str, cik: str = "") -> None:
    if issuer_id not in service.store.issuers:
        service.register_issuer(
            {
                "issuer_id": issuer_id,
                "legal_name": f"Benchmark Sample {ticker}",
                "market": [market],
                "cik": cik,
                "country": "US" if market == "U" else "CN",
            },
            actor="benchmark_sample_fetch",
        )
    if security_id not in service.store.securities:
        service.register_security(
            {
                "security_id": security_id,
                "issuer_id": issuer_id,
                "ticker": ticker,
                "market": market,
                "currency": "USD" if market == "U" else "CNY",
            },
            actor="benchmark_sample_fetch",
        )


def fetch_benchmark_samples(
    *,
    output_dir: str | Path,
    sec_ciks: list[str] | None = None,
    ashare_codes: list[str] | None = None,
    hkex_queries: list[str] | None = None,
    sec_document_types: list[str] | None = None,
    ashare_codes_from_tdx: bool = False,
    limit_per_symbol: int = 10,
    include_sec_body: bool = True,
    include_ashare_attachment_text: bool = False,
    max_attachment_bytes: int = 10_000_000,
    min_body_chars: int = 80,
    user_agent: str = DEFAULT_SEC_USER_AGENT,
    service: SystemService | None = None,
) -> dict[str, Any]:
    service = service or SystemService()
    service.seed_default_sources(actor="benchmark_sample_fetch")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    discovered_ashare_codes: list[str] = []

    for cik in sec_ciks or []:
        issuer_id = f"issuer_sec_{_slug(cik)}"
        security_id = f"security_sec_{_slug(cik)}"
        _ensure_demo_security(service, issuer_id, security_id, ticker=f"CIK{_slug(cik)}", market="U", cik=cik)
        try:
            result = service.ingest_sec_recent_filings(
                {
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "cik": cik,
                    "document_types": sec_document_types or ["10-K", "10-Q"],
                    "include_body": include_sec_body,
                    "limit": limit_per_symbol,
                    "user_agent": user_agent,
                    "max_body_bytes": 2_000_000,
                },
                actor="benchmark_sample_fetch",
            )
        except Exception as exc:
            errors.append({"source": "sec", "key": cik, "error": str(exc), "error_type": type(exc).__name__})
            continue
        for document in result.get("created", []):
            body = str(document.get("body", "") or "")
            if len(body.strip()) < min_body_chars or not _has_supported_terms(body):
                skipped.append({"source": "sec", "key": cik, "reason": "body_too_short_or_no_supported_terms", "title": document.get("title", "")})
                continue
            rows.append(_write_document(output_path, "sec", f"{cik}_{document.get('document_id', '')}", document, body))

    if ashare_codes_from_tdx:
        try:
            discovered_ashare_codes = service.tdx_market_data.symbols(limit=100)
        except Exception as exc:
            errors.append({"source": "tdx_symbols", "key": "vipdoc", "error": str(exc), "error_type": type(exc).__name__})

    combined_ashare_codes = list(dict.fromkeys([*(ashare_codes or []), *discovered_ashare_codes]))
    for code in combined_ashare_codes:
        issuer_id = f"issuer_ashare_{_slug(code)}"
        security_id = f"security_ashare_{_slug(code)}"
        _ensure_demo_security(service, issuer_id, security_id, ticker=code, market="A")
        try:
            result = service.ingest_ashare_recent_filings(
                {
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "security_code": code,
                    "limit": limit_per_symbol,
                    "user_agent": user_agent,
                },
                actor="benchmark_sample_fetch",
            )
        except Exception as exc:
            errors.append({"source": "ashare", "key": code, "error": str(exc), "error_type": type(exc).__name__})
            continue
        for document in result.get("created", []):
            body = str(document.get("body", "") or document.get("title", "") or "")
            attachment_attempted = False
            attachment_text_used = False
            attachment_error = ""
            if include_ashare_attachment_text and not _has_supported_terms(body):
                attachment_attempted = True
                try:
                    attachment_text = _fetch_attachment_text(
                        service,
                        market="A",
                        source_uri=str(document.get("source_uri", "") or ""),
                        user_agent=user_agent,
                        max_bytes=max_attachment_bytes,
                    )
                    if _has_supported_terms(attachment_text):
                        body = attachment_text
                        attachment_text_used = True
                except Exception as exc:
                    attachment_error = f"{type(exc).__name__}: {exc}"
            if not _has_supported_terms(body):
                skipped.append(
                    {
                        "source": "ashare",
                        "key": code,
                        "reason": "no_supported_terms",
                        "title": document.get("title", ""),
                        "attachment_attempted": attachment_attempted,
                        "attachment_error": attachment_error,
                    }
                )
                continue
            row = _write_document(output_path, "ashare", f"{code}_{document.get('document_id', '')}", document, body)
            row["attachment_attempted"] = attachment_attempted
            row["attachment_text_used"] = attachment_text_used
            rows.append(row)

    for query in hkex_queries or []:
        issuer_id = f"issuer_hkex_{_slug(query)}"
        security_id = f"security_hkex_{_slug(query)}"
        _ensure_demo_security(service, issuer_id, security_id, ticker=_slug(query), market="H")
        try:
            result = service.ingest_hkex_recent_filings(
                {
                    "issuer_id": issuer_id,
                    "security_id": security_id,
                    "query": query,
                    "limit": limit_per_symbol,
                    "user_agent": user_agent,
                },
                actor="benchmark_sample_fetch",
            )
        except Exception as exc:
            errors.append({"source": "hkex", "key": query, "error": str(exc), "error_type": type(exc).__name__})
            continue
        for document in result.get("created", []):
            body = str(document.get("body", "") or document.get("title", "") or "")
            if not _has_supported_terms(body):
                skipped.append({"source": "hkex", "key": query, "reason": "no_supported_terms", "title": document.get("title", "")})
                continue
            rows.append(_write_document(output_path, "hkex", f"{query}_{document.get('document_id', '')}", document, body))

    manifest = {
        "status": "completed_with_errors" if errors else "completed",
        "output_dir": str(output_path),
        "created_count": len(rows),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "input_counts": {
            "sec_ciks": len(sec_ciks or []),
            "ashare_codes": len(ashare_codes or []),
            "ashare_codes_from_tdx": len(discovered_ashare_codes),
            "hkex_queries": len(hkex_queries or []),
        },
        "rows": rows,
        "skipped": skipped[:200],
        "errors": errors,
        "usage_boundary": "public_disclosure_sample_fetch_for_local_benchmark_only_no_training_no_live_trading",
    }
    _atomic_write_text(output_path / "fetch-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public disclosure samples for the local benchmark quality package.")
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts/benchmark-sample-fetch"))
    parser.add_argument("--sec-ciks", default="", help="Comma-separated SEC CIKs.")
    parser.add_argument("--ashare-codes", default="", help="Comma-separated A-share stock codes.")
    parser.add_argument("--ashare-codes-from-tdx", action="store_true", help="Discover A-share codes from the local TDX vipdoc adapter.")
    parser.add_argument("--hkex-queries", default="", help="Comma-separated HKEX search queries.")
    parser.add_argument("--sec-document-types", default="10-K,10-Q")
    parser.add_argument("--limit-per-symbol", type=int, default=10)
    parser.add_argument("--min-body-chars", type=int, default=80)
    parser.add_argument("--include-ashare-attachment-text", action="store_true", help="Download and parse A-share announcement attachments when list metadata has no benchmark terms.")
    parser.add_argument("--max-attachment-bytes", type=int, default=10_000_000)
    parser.add_argument("--user-agent", default=DEFAULT_SEC_USER_AGENT)
    parser.add_argument("--no-sec-body", action="store_true")
    args = parser.parse_args()

    result = fetch_benchmark_samples(
        output_dir=args.output_dir,
        sec_ciks=_split_csv(args.sec_ciks),
        ashare_codes=_split_csv(args.ashare_codes),
        hkex_queries=_split_csv(args.hkex_queries),
        sec_document_types=_split_csv(args.sec_document_types),
        ashare_codes_from_tdx=args.ashare_codes_from_tdx,
        limit_per_symbol=args.limit_per_symbol,
        include_sec_body=not args.no_sec_body,
        include_ashare_attachment_text=args.include_ashare_attachment_text,
        max_attachment_bytes=args.max_attachment_bytes,
        min_body_chars=args.min_body_chars,
        user_agent=args.user_agent,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["created_count"] == 0 and result["error_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
