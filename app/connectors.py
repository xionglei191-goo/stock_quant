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


# ---------------------------------------------------------------------------
# A-share supplemental connectors (T-416)
# ---------------------------------------------------------------------------
# All supplemental connectors are for PUBLIC web API / page access only.
# Results are annotated with rights_tag=candidate_astock_reference,
# allowed_use=["manual_reference", "supplemental_research"], and must NOT
# enter the fact/truth layer or automated decision chain without explicit
# source governance review and verification.
# ---------------------------------------------------------------------------


class AStockSupplementalConnector(BaseConnector):
    """Base class for A-share supplemental public web connectors."""

    source_type = "third_party_connector"
    language = "zh"
    rights_tag_class = "candidate_astock_reference"
    allowed_use: list[str] = ["manual_reference", "supplemental_research"]

    def fetch_samples(
        self,
        *,
        user_agent: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[ConnectorDocument]:
        """Fetch sample rows from the public endpoint.

        Subclasses override this method. All returned documents carry
        ``source_uri`` sanitised to remove tokens/secrets and are annotated
        with ``allowed_use`` metadata.
        """
        raise NotImplementedError

    def _sanitize_uri(self, uri: str) -> str:
        """Strip known secret query parameters from a URI."""
        import re as _re
        secret_params = re.compile(
            r"[?&](?:token|api_key|access_token|signature|secret|apikey|key)=[^&]*",
            flags=re.IGNORECASE,
        )
        return secret_params.sub("", uri).rstrip("?&")

    def _get_json(self, url: str, *, user_agent: str, headers: dict[str, str] | None = None) -> Any:
        req_headers = {"User-Agent": user_agent, "Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        request = Request(url, headers=req_headers)
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))

    def _get_text(self, url: str, *, user_agent: str, headers: dict[str, str] | None = None) -> str:
        req_headers = {"User-Agent": user_agent}
        if headers:
            req_headers.update(headers)
        request = Request(url, headers=req_headers)
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")


class EastMoneyResearchConnector(AStockSupplementalConnector):
    """East Money (东方财富) public research report discovery.

    Uses the publicly accessible research report search API.
    Endpoint: https://reportapi.eastmoney.com/report/list
    Rights: public web, manual_reference only, no redistribution.
    """

    source_id = "eastmoney_research"
    base_url = "https://reportapi.eastmoney.com/report/list"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        report_id = str(raw.get("infoCode") or raw.get("id") or "")
        title = str(raw.get("title") or "")
        published_at = str(raw.get("publishDate") or raw.get("time") or "")
        org_name = str(raw.get("orgName") or raw.get("orgSName") or "")
        stock_code = str(raw.get("stockCode") or raw.get("scode") or "")
        source_uri = self._sanitize_uri(
            raw.get("encryptUrl") or raw.get("pdfUrl") or
            f"https://data.eastmoney.com/report/{report_id}.html"
        )
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type="research",
            source_uri=source_uri,
            language=self.language,
            title=title,
            body="",
            published_at=published_at,
            metadata={
                "report_id": report_id,
                "org_name": org_name,
                "stock_code": stock_code,
                "rating": raw.get("emRatingName") or raw.get("rating"),
                "industry": raw.get("industryName"),
                "allowed_use": self.allowed_use,
                "rights_tag_class": self.rights_tag_class,
                "automation_allowed": False,
                "source_boundary": "manual_reference_or_supplemental_research_only",
            },
        )

    def fetch_samples(
        self,
        *,
        user_agent: str,
        limit: int = 10,
        stock_code: str = "",
        industry: str = "",
        report_type: str = "",
        **kwargs: Any,
    ) -> list[ConnectorDocument]:
        limit = max(1, min(50, int(limit)))
        params: dict[str, Any] = {
            "pageSize": limit,
            "pageNo": 1,
            "fields": "",
        }
        if stock_code:
            params["scode"] = stock_code
        if industry:
            params["industryCode"] = industry
        if report_type:
            params["reportType"] = report_type
        url = f"{self.base_url}?{urlencode(params)}"
        try:
            data = self._get_json(url, user_agent=user_agent, headers={
                "Referer": "https://data.eastmoney.com/report/",
            })
        except Exception as exc:
            return [ConnectorDocument(
                source_id=self.source_id,
                source_type=self.source_type,
                document_type="research",
                source_uri=self._sanitize_uri(url),
                language=self.language,
                title=f"[fetch_error] {exc}",
                body="",
                metadata={
                    "error": str(exc),
                    "allowed_use": self.allowed_use,
                    "automation_allowed": False,
                    "source_boundary": "manual_reference_or_supplemental_research_only",
                },
            )]
        rows = data if isinstance(data, list) else (
            data.get("data", {}).get("list") or
            data.get("data") or
            data.get("result") or []
        )
        if isinstance(rows, dict):
            rows = rows.get("list") or rows.get("data") or []
        documents: list[ConnectorDocument] = []
        for item in rows[:limit]:
            if isinstance(item, dict):
                documents.append(self.normalize(item))
        return documents


class CninfoAnnouncementConnector(AStockSupplementalConnector):
    """Cninfo / 巨潮资讯 supplemental announcement discovery.

    Uses the publicly accessible announcement query API.
    Endpoint: https://www.cninfo.com.cn/new/hisAnnouncement/query
    Rights: public web, manual_reference only.
    """

    source_id = "cninfo_announcements"
    query_url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        ann_id = str(raw.get("announcementId") or "")
        title = str(raw.get("announcementTitle") or "")
        published_at = str(raw.get("announcementTime") or raw.get("publishTime") or "")
        # Parse epoch ms to ISO date if numeric
        if published_at.isdigit() and len(published_at) > 8:
            try:
                from datetime import timezone as _tz
                ts = datetime.fromtimestamp(int(published_at) / 1000, tz=_tz.utc)
                published_at = ts.date().isoformat()
            except Exception:
                pass
        security_code = str(raw.get("secCode") or raw.get("stockCode") or "")
        source_uri = self._sanitize_uri(
            raw.get("adjunctUrl") or
            f"https://www.cninfo.com.cn/new/disclosure/detail?announcementId={ann_id}&orgId="
        )
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type="announcement",
            source_uri=source_uri,
            language=self.language,
            title=title,
            body="",
            published_at=published_at,
            metadata={
                "announcement_id": ann_id,
                "security_code": security_code,
                "security_name": raw.get("secName"),
                "orgId": raw.get("orgId"),
                "allowed_use": self.allowed_use,
                "automation_allowed": False,
                "source_boundary": "manual_reference_or_supplemental_research_only",
            },
        )

    def fetch_samples(
        self,
        *,
        user_agent: str,
        limit: int = 10,
        stock_code: str = "",
        start_date: str = "",
        end_date: str = "",
        category: str = "",
        **kwargs: Any,
    ) -> list[ConnectorDocument]:
        limit = max(1, min(50, int(limit)))
        body_parts = [
            f"pageNum=1&pageSize={limit}&tabName=fulltext&column=szse&category=",
            f"plate=&seDate={start_date}%7E{end_date}",
        ]
        if stock_code:
            body_parts.append(f"&stock={stock_code}%2C")
        if category:
            body_parts.append(f"&category={category}")
        form_body = "&".join(body_parts).encode("utf-8")
        request = Request(
            self.query_url,
            data=form_body,
            headers={
                "User-Agent": user_agent,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=data/sse/disclosure",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            return [ConnectorDocument(
                source_id=self.source_id,
                source_type=self.source_type,
                document_type="announcement",
                source_uri=self.query_url,
                language=self.language,
                title=f"[fetch_error] {exc}",
                body="",
                metadata={
                    "error": str(exc),
                    "allowed_use": self.allowed_use,
                    "automation_allowed": False,
                    "source_boundary": "manual_reference_or_supplemental_research_only",
                },
            )]
        rows = (
            data.get("announcements") or
            data.get("data", {}).get("list") or
            data.get("result") or []
        )
        documents: list[ConnectorDocument] = []
        for item in rows[:limit]:
            if isinstance(item, dict):
                documents.append(self.normalize(item))
        return documents


class TencentValuationConnector(AStockSupplementalConnector):
    """Tencent Stock (腾讯股票) public valuation snapshot connector.

    Endpoint: https://qt.gtimg.cn/q={symbol_list}
    Returns basic valuation fields: PE/PB/market_cap, close, etc.
    Rights: public web, manual_reference only, no redistribution.
    """

    source_id = "tencent_valuation_snapshot"
    base_url = "https://qt.gtimg.cn/q="

    _FIELD_MAP = {
        1: "security_name",
        2: "open",
        3: "close_prev",
        4: "close",
        5: "high",
        6: "low",
        7: "bid",
        8: "ask",
        9: "volume",
        10: "turnover",
        38: "pe_ttm",
        39: "market_cap_b",   # 亿元
        40: "pb",
        41: "total_market_cap_b",
    }

    def normalize(self, raw: dict[str, Any]) -> ConnectorDocument:
        symbol = str(raw.get("symbol") or "")
        security_name = str(raw.get("security_name") or "")
        source_uri = self._sanitize_uri(
            f"https://gu.qq.com/{symbol}/gp"
        )
        return ConnectorDocument(
            source_id=self.source_id,
            source_type=self.source_type,
            document_type="valuation_snapshot",
            source_uri=source_uri,
            language=self.language,
            title=f"{security_name}（{symbol}）估值快照",
            body="",
            published_at=str(raw.get("update_time") or ""),
            metadata={
                "symbol": symbol,
                "security_name": security_name,
                "close": raw.get("close"),
                "pe_ttm": raw.get("pe_ttm"),
                "pb": raw.get("pb"),
                "market_cap_b": raw.get("market_cap_b"),
                "total_market_cap_b": raw.get("total_market_cap_b"),
                "allowed_use": self.allowed_use,
                "automation_allowed": False,
                "source_boundary": "manual_reference_or_supplemental_research_only",
            },
        )

    def fetch_samples(
        self,
        *,
        user_agent: str,
        limit: int = 10,
        symbols: list[str] | None = None,
        **kwargs: Any,
    ) -> list[ConnectorDocument]:
        limit = max(1, min(20, int(limit)))
        symbols = list(symbols or [])[:limit]
        if not symbols:
            return []
        # Tencent symbols use prefixes: sz000001, sh600000
        normalized: list[str] = []
        for sym in symbols:
            s = sym.strip().lower()
            if not s:
                continue
            if not s.startswith(("sh", "sz", "bj")):
                bare = re.sub(r"\D", "", s)
                if bare.startswith(("5", "6", "9")):
                    s = f"sh{bare}"
                elif bare.startswith(("8", "4")):
                    s = f"bj{bare}"
                else:
                    s = f"sz{bare}"
            normalized.append(s)
        if not normalized:
            return []
        url = self.base_url + ",".join(normalized)
        try:
            text = self._get_text(url, user_agent=user_agent, headers={
                "Referer": "https://gu.qq.com/",
            })
        except Exception as exc:
            return [ConnectorDocument(
                source_id=self.source_id,
                source_type=self.source_type,
                document_type="valuation_snapshot",
                source_uri=self._sanitize_uri(url),
                language=self.language,
                title=f"[fetch_error] {exc}",
                body="",
                metadata={
                    "error": str(exc),
                    "allowed_use": self.allowed_use,
                    "automation_allowed": False,
                    "source_boundary": "manual_reference_or_supplemental_research_only",
                },
            )]
        documents: list[ConnectorDocument] = []
        # Parse lines: v_sz000001="44~平安银行~000001~..." semicolon-terminated
        for line in text.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            sym_key, _, value_raw = line.partition("=")
            sym_key = sym_key.strip().removeprefix("v_")
            value = value_raw.strip().strip("\"").rstrip(";")
            if not value:
                continue
            fields = value.split("~")
            parsed: dict[str, Any] = {"symbol": sym_key}
            for idx, field_name in self._FIELD_MAP.items():
                if idx < len(fields) and fields[idx]:
                    try:
                        parsed[field_name] = float(fields[idx]) if any(
                            k in field_name for k in ("pe", "pb", "cap", "close", "high", "low", "open", "vol", "turn")
                        ) else fields[idx]
                    except ValueError:
                        parsed[field_name] = fields[idx]
            if len(fields) > 30:
                # field 30/31 usually contains date/time
                parsed["update_time"] = fields[30] if 30 < len(fields) else ""
            documents.append(self.normalize(parsed))
        return documents[:limit]


class AStockSupplementalRegistry:
    """Registry of A-share supplemental public connectors (T-416).

    These connectors provide PUBLIC web data only and are classified as
    manual_reference / supplemental_research boundary. They must NOT be
    used in automated decision chains without explicit source governance
    approval and verification.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, AStockSupplementalConnector] = {
            "eastmoney_research": EastMoneyResearchConnector(),
            "cninfo_announcements": CninfoAnnouncementConnector(),
            "tencent_valuation_snapshot": TencentValuationConnector(),
        }

    def get(self, connector_id: str) -> AStockSupplementalConnector | None:
        return self._connectors.get(connector_id)

    def list_ids(self) -> list[str]:
        return list(self._connectors)

    def fetch_samples(
        self,
        connector_id: str,
        *,
        user_agent: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[ConnectorDocument]:
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise KeyError(f"supplemental connector not found: {connector_id}")
        return connector.fetch_samples(user_agent=user_agent, limit=limit, **kwargs)
