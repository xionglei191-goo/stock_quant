from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(slots=True)
class ConnectorDocument:
    source_id: str
    source_type: str
    document_type: str
    source_uri: str
    language: str
    title: str = ""
    body: str = ""
    published_at: str = ""
    metadata: dict[str, Any] | None = None


class BaseConnector:
    source_id: str = ""
    source_type: str = ""
    language: str = "mixed"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        raise NotImplementedError

    def fetch_binary(self, source_uri: str, *, user_agent: str, max_bytes: int = 10_000_000) -> bytes:
        request = Request(source_uri, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        with urlopen(request, timeout=30) as response:
            data = response.read(max_bytes + 1)
        return data[:max_bytes] if len(data) > max_bytes else data


class AShareConnector(BaseConnector):
    source_id = "ashare_exchange"
    source_type = "exchange"
    language = "zh"
    sse_search_url = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
    szse_search_url = "https://www.szse.cn/api/disc/announcement/annList"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        code = str(raw.get("code", ""))
        announcement_id = str(raw.get("announcement_id", ""))
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type=str(raw.get("document_type", "announcement")),
            source_uri=f"https://exchange.example.cn/announcement/{code}/{announcement_id}",
            language=self.language,
            title=str(raw.get("title", "")),
            body=str(raw.get("body", "")),
            published_at=str(raw.get("published_at", "")),
        )

    def fetch_recent_filings(
        self,
        *,
        security_code: str,
        user_agent: str,
        limit: int = 10,
        begin_date: str = "",
        end_date: str = "",
        report_type: str = "ALL",
        security_type: str = "0101,120100,020100,020200,120200",
        exchange: str = "auto",
    ) -> list[ConnectorDocument]:
        exchange = self._resolve_exchange(security_code, exchange)
        if exchange == "szse":
            return self._fetch_szse_recent_filings(
                security_code=security_code,
                user_agent=user_agent,
                limit=limit,
                begin_date=begin_date,
                end_date=end_date,
            )
        return self._fetch_sse_recent_filings(
            security_code=security_code,
            user_agent=user_agent,
            limit=limit,
            begin_date=begin_date,
            end_date=end_date,
            report_type=report_type,
            security_type=security_type,
        )

    def _fetch_sse_recent_filings(
        self,
        *,
        security_code: str,
        user_agent: str,
        limit: int,
        begin_date: str,
        end_date: str,
        report_type: str,
        security_type: str,
    ) -> list[ConnectorDocument]:
        params = {
            "jsonCallBack": "jsonpCallback",
            "isPagination": "true",
            "pageHelp.pageSize": max(1, min(50, int(limit))),
            "pageHelp.pageNo": 1,
            "pageHelp.beginPage": 1,
            "pageHelp.cacheSize": 1,
            "productId": security_code,
            "securityType": security_type,
            "reportType": report_type,
            "beginDate": begin_date,
            "endDate": end_date,
        }
        payload = self._get_jsonp(f"{self.sse_search_url}?{urlencode(params)}", user_agent=user_agent)
        page = payload.get("pageHelp", {}) if isinstance(payload, dict) else {}
        documents: list[ConnectorDocument] = []
        for item in page.get("data", []):
            if not isinstance(item, dict):
                continue
            publish_time = str(item.get("SSEDATE") or item.get("ADDDATE") or "")
            title = str(item.get("TITLE", ""))
            url = str(item.get("URL", ""))
            sec_code = str(item.get("SECURITY_CODE", security_code))
            source_uri = self._absolute_sse_url(url)
            document_type = self._ashare_document_type(title=title, report_type=report_type, url=url)
            documents.append(
                ConnectorDocument(
                    source_id=self.source_id,
                    source_type=self.source_type,
                    document_type=document_type,
                    source_uri=source_uri,
                    language=self.language,
                    title=title,
                    body=str(item.get("BULLETIN_HEADING") or item.get("title") or ""),
                    published_at=publish_time,
                    metadata={
                        "security_code": sec_code,
                        "security_name": item.get("SECURITY_NAME"),
                        "bulletin_type": item.get("BULLETIN_TYPE"),
                        "bulletin_heading": item.get("BULLETIN_HEADING"),
                        "bulletin_year": item.get("BULLETIN_YEAR"),
                        "url": url,
                        "attach_format": item.get("attachFormat"),
                        "attach_size": item.get("attachSize"),
                        "announce_count": page.get("total"),
                        "exchange": "sse",
                        "page_no": page.get("pageNo"),
                        "page_size": page.get("pageSize"),
                    },
                )
            )
            if len(documents) >= limit:
                break
        return documents

    def _fetch_szse_recent_filings(
        self,
        *,
        security_code: str,
        user_agent: str,
        limit: int,
        begin_date: str,
        end_date: str,
    ) -> list[ConnectorDocument]:
        body = {
            "stock": [security_code],
            "channelCode": ["listedNotice_disc"],
            "pageSize": max(1, min(50, int(limit))),
            "pageNum": 1,
        }
        if begin_date or end_date:
            body["seDate"] = [begin_date or end_date, end_date or begin_date]
        payload = self._post_json(self.szse_search_url, body, user_agent=user_agent)
        documents: list[ConnectorDocument] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            sec_codes = item.get("secCode") or []
            sec_names = item.get("secName") or []
            title = str(item.get("title", ""))
            attach_path = str(item.get("attachPath", ""))
            source_uri = self._absolute_szse_url(attach_path)
            documents.append(
                ConnectorDocument(
                    source_id=self.source_id,
                    source_type=self.source_type,
                    document_type=self._ashare_document_type(title=title, report_type="ALL", url=attach_path),
                    source_uri=source_uri,
                    language=self.language,
                    title=title,
                    body=str(item.get("content") or ""),
                    published_at=str(item.get("publishTime", "")),
                    metadata={
                        "security_code": sec_codes[0] if sec_codes else security_code,
                        "security_name": sec_names[0] if sec_names else "",
                        "announcement_id": item.get("annId"),
                        "attach_format": item.get("attachFormat"),
                        "attach_size": item.get("attachSize"),
                        "url": attach_path,
                        "announce_count": payload.get("announceCount"),
                        "exchange": "szse",
                        "page_no": body["pageNum"],
                        "page_size": body["pageSize"],
                    },
                )
            )
            if len(documents) >= limit:
                break
        return documents

    def _absolute_sse_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://www.sse.com.cn{url}"

    def _absolute_szse_url(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"https://www.szse.cn{url}"

    def _resolve_exchange(self, security_code: str, exchange: str) -> str:
        exchange = exchange.lower()
        if exchange in {"sse", "szse"}:
            return exchange
        return "sse" if security_code.startswith(("5", "6", "9")) else "szse"

    def _ashare_document_type(self, *, title: str, report_type: str, url: str) -> str:
        haystack = f"{title} {report_type} {url}".lower()
        if "annual" in haystack or "年报" in haystack:
            return "annual_report"
        return "announcement"

    def _get_jsonp(self, url: str, *, user_agent: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "*/*",
                "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            },
        )
        with urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
        match = re.match(r"^jsonpCallback\((.*)\)\s*$", text, flags=re.S)
        if not match:
            raise ValueError("unexpected SSE JSONP payload")
        return json.loads(match.group(1))

    def _post_json(self, url: str, body: dict[str, Any], *, user_agent: str) -> dict[str, Any]:
        request = Request(
            f"{url}?{urlencode({'random': '0.123456'})}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": "https://www.szse.cn/disclosure/listed/bulletinList/index.html",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class HKEXConnector(BaseConnector):
    source_id = "hkexnews"
    source_type = "exchange"
    language = "zh"
    search_url = "https://www3.hkexnews.hk/Search/ServiceWCF/Searchservice.svc/AdvSearch"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        source_uri = str(raw.get("source_uri") or "")
        if not source_uri:
            stock_code = str(raw.get("stock_code", ""))
            release_id = str(raw.get("release_id", ""))
            source_uri = f"https://www1.hkexnews.hk/app/sehk/{stock_code}/{release_id}.htm"
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type=str(raw.get("document_type", "announcement")),
            source_uri=source_uri,
            language=str(raw.get("language", self.language)),
            title=str(raw.get("title", "")),
            body=str(raw.get("body", "")),
            published_at=str(raw.get("published_at", "")),
            metadata=dict(raw.get("metadata", {})) if raw.get("metadata") is not None else None,
        )

    def fetch_recent_filings(
        self,
        query: str,
        *,
        user_agent: str,
        limit: int = 10,
        file_type: str = "pdf",
        language: str = "en-UK",
    ) -> list[ConnectorDocument]:
        params = {
            "category": "EPSSearch",
            "allWord": query,
            "anyWord": "",
            "exactPhrase": "",
            "noneWord": "",
            "fileType": file_type,
            "sortType": "mdate",
            "pageIndex": 1,
            "pageSize": max(1, min(50, int(limit))),
            "sc_lang": language,
        }
        payload = self._get_json(f"{self.search_url}?{urlencode(params)}", user_agent=user_agent)
        results = payload.get("d", [])
        documents: list[ConnectorDocument] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            published_at = self._parse_hkex_date(str(item.get("LastModify", "")))
            title = str(item.get("Title", ""))
            file_path = str(item.get("FilePath", ""))
            highlighted = str(item.get("HighlightedSummary") or item.get("Description") or "")
            document_type = self._hkex_document_type(title=title, file_type=str(item.get("FileType", file_type)), query=query)
            documents.append(
                ConnectorDocument(
                    source_id=self.source_id,
                    source_type=self.source_type,
                    document_type=document_type,
                    source_uri=file_path,
                    language="en" if str(language).lower().startswith("en") else "zh",
                    title=title,
                    body=highlighted,
                    published_at=published_at,
                    metadata={
                        "file_size": item.get("FileSize"),
                        "file_type": item.get("FileType"),
                        "file_extension": item.get("FileExtension"),
                        "rank": item.get("Rank"),
                        "row_no": item.get("RowNo"),
                        "total": item.get("Total"),
                        "total_duplicate": item.get("TotalDuplicate"),
                        "execution_time": item.get("ExecutionTime"),
                    },
                )
            )
            if len(documents) >= limit:
                break
        return documents

    def _parse_hkex_date(self, value: str) -> str:
        if not value:
            return ""
        for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
                return parsed.replace(tzinfo=timezone.utc).date().isoformat()
            except ValueError:
                continue
        return value

    def _hkex_document_type(self, *, title: str, file_type: str, query: str) -> str:
        haystack = f"{title} {query} {file_type}".lower()
        if "annual" in haystack or "annual report" in haystack:
            return "annual_report"
        return "announcement"

    def _get_json(self, url: str, *, user_agent: str) -> dict[str, Any]:
        request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class SecEdgarConnector(BaseConnector):
    source_id = "sec_edgar"
    source_type = "regulatory"
    language = "en"
    submissions_base_url = "https://data.sec.gov/submissions"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        cik = str(raw.get("cik", "")).lstrip("0") or "0"
        accession = str(raw.get("accession_no", "")).replace("-", "")
        primary_doc = str(raw.get("primary_doc", "index.htm"))
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type=str(raw.get("document_type", "10-K")),
            source_uri=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}",
            language=self.language,
            title=str(raw.get("title", "")),
            body=str(raw.get("body", "")),
            published_at=str(raw.get("published_at", "")),
            metadata={
                "cik": cik,
                "accession_no": str(raw.get("accession_no", "")),
                "primary_doc": primary_doc,
            },
        )

    def fetch_recent_filings(
        self,
        cik: str,
        *,
        user_agent: str,
        limit: int = 10,
        document_types: list[str] | None = None,
    ) -> list[ConnectorDocument]:
        padded_cik = str(cik).lstrip("0").zfill(10)
        url = f"{self.submissions_base_url}/CIK{padded_cik}.json"
        data = self._get_json(url, user_agent=user_agent)
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accepted_at = recent.get("acceptanceDateTime", [])
        allowed_types = set(document_types or [])
        documents: list[ConnectorDocument] = []
        for index, form_type in enumerate(forms):
            document_type = str(form_type)
            if allowed_types and document_type not in allowed_types:
                continue
            accession_no = str(accession_numbers[index])
            primary_doc = str(primary_documents[index])
            normalized = self.normalize(
                {
                    "cik": padded_cik,
                    "accession_no": accession_no,
                    "primary_doc": primary_doc,
                    "document_type": document_type,
                    "title": f"{document_type} filing {accession_no}",
                    "published_at": str(filing_dates[index]) if index < len(filing_dates) else "",
                }
            )
            normalized.metadata = {
                "cik": padded_cik,
                "accession_no": accession_no,
                "primary_doc": primary_doc,
                "filing_date": str(filing_dates[index]) if index < len(filing_dates) else "",
                "report_date": str(report_dates[index]) if index < len(report_dates) else "",
                "acceptance_datetime": str(accepted_at[index]) if index < len(accepted_at) else "",
            }
            documents.append(normalized)
            if len(documents) >= limit:
                break
        return documents

    def fetch_document_body(self, source_uri: str, *, user_agent: str, max_bytes: int = 2_000_000) -> str:
        request = Request(source_uri, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
        with urlopen(request, timeout=30) as response:
            body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            body = body[:max_bytes]
        return body.decode("utf-8", errors="replace")

    def _get_json(self, url: str, *, user_agent: str) -> dict[str, Any]:
        request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors = {
            "A": AShareConnector(),
            "H": HKEXConnector(),
            "U": SecEdgarConnector(),
        }

    def normalize(self, market: str, raw: dict[str, Any]) -> ConnectorDocument:
        if market not in self._connectors:
            raise KeyError(f"unsupported market connector: {market}")
        return self._connectors[market].normalize(raw)

    def fetch_ashare_recent_filings(
        self,
        security_code: str,
        *,
        user_agent: str,
        limit: int = 10,
        begin_date: str = "",
        end_date: str = "",
        report_type: str = "ALL",
        security_type: str = "0101,120100,020100,020200,120200",
        exchange: str = "auto",
    ) -> list[ConnectorDocument]:
        connector = self._connectors["A"]
        if not isinstance(connector, AShareConnector):
            raise TypeError("A connector is not A-share exchange")
        return connector.fetch_recent_filings(
            security_code=security_code,
            user_agent=user_agent,
            limit=limit,
            begin_date=begin_date,
            end_date=end_date,
            report_type=report_type,
            security_type=security_type,
            exchange=exchange,
        )

    def fetch_sec_recent_filings(
        self,
        cik: str,
        *,
        user_agent: str,
        limit: int = 10,
        document_types: list[str] | None = None,
    ) -> list[ConnectorDocument]:
        connector = self._connectors["U"]
        if not isinstance(connector, SecEdgarConnector):
            raise TypeError("U connector is not SEC EDGAR")
        return connector.fetch_recent_filings(cik, user_agent=user_agent, limit=limit, document_types=document_types)

    def fetch_sec_document_body(self, source_uri: str, *, user_agent: str, max_bytes: int = 2_000_000) -> str:
        connector = self._connectors["U"]
        if not isinstance(connector, SecEdgarConnector):
            raise TypeError("U connector is not SEC EDGAR")
        return connector.fetch_document_body(source_uri, user_agent=user_agent, max_bytes=max_bytes)

    def fetch_document_binary(self, market: str, source_uri: str, *, user_agent: str, max_bytes: int = 10_000_000) -> bytes:
        connector = self._connectors[market]
        return connector.fetch_binary(source_uri, user_agent=user_agent, max_bytes=max_bytes)

    def fetch_hkex_recent_filings(
        self,
        query: str,
        *,
        user_agent: str,
        limit: int = 10,
        file_type: str = "pdf",
        language: str = "en-UK",
    ) -> list[ConnectorDocument]:
        connector = self._connectors["H"]
        if not isinstance(connector, HKEXConnector):
            raise TypeError("H connector is not HKEX")
        return connector.fetch_recent_filings(
            query,
            user_agent=user_agent,
            limit=limit,
            file_type=file_type,
            language=language,
        )
