from __future__ import annotations

import csv
import io
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zipfile import ZipFile


USER_AGENT = "ai-quant-local-research/1.0"


@dataclass(frozen=True, slots=True)
class RawPoint:
    observation_date: date
    value: float


Downloader = Callable[[str], bytes]


def download(url: str, *, timeout: float = 60.0) -> bytes:
    cache_root = Path(os.getenv(
        "AI_QUANT_DYNAMIC_ALLOCATION_CACHE",
        str(Path(__file__).resolve().parents[3] / "data" / "local" / "dynamic-allocation-cache"),
    ))
    cache_material = f"{datetime.now(timezone.utc).date().isoformat()}|{url}"
    cache_path = cache_root / f"{hashlib.sha256(cache_material.encode()).hexdigest()}.bin"
    if cache_path.exists():
        return cache_path.read_bytes()
    try:
        payload: bytes
        curl_bin = (
            shutil.which("curl")
            if url.startswith("https://fred.stlouisfed.org/")
            else None
        )
        if curl_bin:
            try:
                completed = subprocess.run(
                    [
                        curl_bin, "--fail", "--location", "--silent", "--show-error",
                        "--max-time", str(int(timeout)), "--retry", "2", "--retry-delay", "2",
                        url,
                    ],
                    check=True,
                    capture_output=True,
                    timeout=timeout * 3 + 10,
                )
                payload = completed.stdout
            except (OSError, subprocess.SubprocessError, TimeoutError):
                # FRED's edge currently stalls for this custom User-Agent on
                # some routes while accepting urllib's default request.
                with urlopen(url, timeout=timeout) as response:
                    payload = response.read()
        elif url.startswith("https://fred.stlouisfed.org/"):
            with urlopen(url, timeout=timeout) as response:
                payload = response.read()
        else:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            with urlopen(request, timeout=timeout) as response:
                payload = response.read()
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(payload)
        return payload
    except (OSError, subprocess.SubprocessError, TimeoutError):
        if cache_path.exists():
            return cache_path.read_bytes()
        raise


class PublicSourceClient:
    """Small no-key clients for the governed public sources used by T-589."""

    def __init__(self, downloader: Downloader = download):
        self.downloader = downloader
        self.source_errors: dict[str, str] = {}

    def fred(self, series_id: str) -> list[RawPoint]:
        # FRED's graph endpoint intermittently stalls behind some network paths
        # when cosd/coed are present. The full public CSV is small, cached once
        # per day, and downstream collection already applies the as-of cutoff.
        query = urlencode({"id": series_id})
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}"
        rows = csv.DictReader(io.StringIO(self.downloader(url).decode("utf-8-sig")))
        result = []
        for row in rows:
            raw = row.get(series_id)
            if raw in (None, "", "."):
                continue
            result.append(RawPoint(date.fromisoformat(str(row["observation_date"])), float(raw)))
        return result

    def fred_batch(self, series_ids: list[str]) -> dict[str, list[RawPoint]]:
        result: dict[str, list[RawPoint]] = {}
        for series_id in series_ids:
            try:
                result[series_id] = self.fred(series_id)
            except Exception as exc:
                result[series_id] = []
                self.source_errors[series_id] = f"{type(exc).__name__}: {exc}"
        return result

    def cboe(self, index_id: str) -> list[RawPoint]:
        url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{index_id}_History.csv"
        rows = csv.DictReader(io.StringIO(self.downloader(url).decode("utf-8-sig")))
        result = []
        for row in rows:
            raw_date = str(row.get("DATE", "")).strip()
            raw_close = str(row.get("CLOSE", "")).strip()
            if not raw_date or not raw_close:
                continue
            result.append(RawPoint(datetime.strptime(raw_date, "%m/%d/%Y").date(), float(raw_close)))
        return sorted(result, key=lambda item: item.observation_date)

    def yahoo_adjusted_close(self, ticker: str, start: date, end: date) -> list[RawPoint]:
        period1 = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
        period2 = int(datetime.combine(end, datetime.min.time(), timezone.utc).timestamp()) + 86400
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            f"?period1={period1}&period2={period2}&interval=1d&events=history&includeAdjustedClose=true"
        )
        payload = json.loads(self.downloader(url).decode("utf-8"))
        error = payload.get("chart", {}).get("error")
        if error:
            raise RuntimeError(f"Yahoo chart error for {ticker}: {error}")
        chart = (payload.get("chart", {}).get("result") or [None])[0]
        if not chart:
            raise RuntimeError(f"Yahoo chart returned no data for {ticker}")
        timestamps = chart.get("timestamp") or []
        indicators = chart.get("indicators") or {}
        adjusted = ((indicators.get("adjclose") or [{}])[0].get("adjclose") or [])
        closes = ((indicators.get("quote") or [{}])[0].get("close") or [])
        values = adjusted if adjusted else closes
        return [
            RawPoint(datetime.fromtimestamp(int(timestamp), timezone.utc).date(), float(value))
            for timestamp, value in zip(timestamps, values)
            if value is not None
        ]

    def finra_margin_debt(self) -> list[RawPoint]:
        url = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
        return _finra_xlsx_points(self.downloader(url))


def _finra_xlsx_points(payload: bytes) -> list[RawPoint]:
    """Parse the first FINRA XLSX sheet without adding an Excel runtime dependency."""
    namespaces = {
        "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "p": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with ZipFile(io.BytesIO(payload)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root.findall("a:si", namespaces)]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in rels.findall("p:Relationship", namespaces)}
        first = workbook.find("a:sheets/a:sheet", namespaces)
        if first is None:
            return []
        rel_id = first.attrib[f"{{{namespaces['r']}}}id"]
        target = targets[rel_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        sheet = ElementTree.fromstring(archive.read(sheet_path))
        records: list[list[str]] = []
        for row in sheet.findall(".//a:sheetData/a:row", namespaces):
            values: list[str] = []
            for cell in row.findall("a:c", namespaces):
                node = cell.find("a:v", namespaces)
                inline = cell.find("a:is", namespaces)
                text = "" if node is None or node.text is None else node.text
                if inline is not None:
                    text = "".join(inline.itertext())
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values.append(text)
            records.append(values)
    result = []
    for row in records[1:]:
        if len(row) < 2 or len(row[0]) != 7 or row[0][4:5] != "-":
            continue
        try:
            year, month = (int(item) for item in row[0].split("-"))
            result.append(RawPoint(date(year, month, 1), float(row[1])))
        except ValueError:
            continue
    return sorted(result, key=lambda item: item.observation_date)


def http_last_modified(headers: dict[str, str]) -> datetime | None:
    """Kept public for callers that persist raw-cache metadata."""
    value = headers.get("last-modified")
    return parsedate_to_datetime(value) if value else None
