from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import os
import re
import uuid
from typing import Any
import zlib


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime:
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported datetime value: {type(value)!r}")


def env_text(name: str, default: str | None = None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = str(raw).strip()
    if not value:
        return default
    return value


def env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = env_text(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def env_float(name: str, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = env_text(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


class _HTMLTextExtractor(HTMLParser):
    block_tags = {
        "address",
        "article",
        "body",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
    skip_tags = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def html_to_text(text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(text)
    return parser.text()


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"<\s*/?\s*(html|body|div|p|table|tr|td|span|section|ix:)", text, flags=re.IGNORECASE))


def chunk_text(text: str) -> list[str]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []
    if looks_like_html(cleaned):
        cleaned = html_to_text(cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    chunks = re.split(r"\n{2,}|(?<=[。！？.!?])\s+", cleaned)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def chunk_text_by_page(text: str) -> list[tuple[int, int, str]]:
    pages = text.split("\f")
    chunks: list[tuple[int, int, str]] = []
    for page_index, page_text in enumerate(pages, start=1):
        for chunk_index, chunk in enumerate(chunk_text(page_text), start=1):
            chunks.append((page_index, chunk_index, chunk))
    return chunks


def pdf_bytes_to_text(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        return data.decode("utf-8", errors="ignore")
    parts: list[str] = []
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        parts.append(_extract_pdf_stream_text(stream))
    text = "\n".join(part for part in parts if part.strip())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_stream_text(stream: bytes) -> str:
    candidates = [stream]
    try:
        candidates.append(zlib.decompress(stream))
    except zlib.error:
        pass
    for candidate in candidates:
        extracted = _extract_pdf_text_operators(candidate)
        if extracted.strip():
            return extracted
    return ""


def _extract_pdf_text_operators(data: bytes) -> str:
    text = data.decode("latin-1", errors="ignore")
    parts: list[str] = []
    for match in re.finditer(r"\((?:\\.|[^\\()])*\)\s*T[Jj]", text, flags=re.S):
        parts.append(_decode_pdf_literal(match.group(0)))
    for match in re.finditer(r"\[(.*?)\]\s*TJ", text, flags=re.S):
        parts.extend(_decode_pdf_literal(item.group(0)) for item in re.finditer(r"\((?:\\.|[^\\()])*\)", match.group(1), flags=re.S))
    return "\n".join(part for part in parts if part)


def _decode_pdf_literal(token: str) -> str:
    start = token.find("(")
    end = token.rfind(")")
    if start < 0 or end <= start:
        return ""
    value = token[start + 1 : end]
    value = re.sub(r"\\([nrtbf()\\])", lambda match: _PDF_ESCAPES.get(match.group(1), match.group(1)), value)
    value = re.sub(r"\\([0-7]{1,3})", lambda match: chr(int(match.group(1), 8)), value)
    return value


_PDF_ESCAPES = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    "(": "(",
    ")": ")",
    "\\": "\\",
}


def to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_plain(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_plain(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
