from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..pdf_text import PdfTextExtractionResult
from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument, SourceRetrievalDiagnostic
from .base import SourceCollectionResult, SourceUnavailableError

PdfTextExtractor = Callable[[Path], PdfTextExtractionResult | str]


@dataclass(frozen=True)
class CninfoQueryPlan:
    search_key: str
    stock_code: str = ""
    column: str = ""
    org_id: str = ""
    start_date: str = ""
    end_date: str = ""
    page_size: int = 30
    max_pages: int = 2
    query_type: str = "name"


@dataclass(frozen=True)
class CninfoAnnouncementRecord:
    announcement_id: str
    title: str
    announcement_time: str = ""
    sec_code: str = ""
    sec_name: str = ""
    org_id: str = ""
    adjunct_url: str = ""
    pdf_url: str = ""
    announcement_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class CninfoClient(Protocol):
    def query_announcements(self, plan: CninfoQueryPlan) -> list[CninfoAnnouncementRecord]:
        ...


class UrlopenCninfoClient:
    historical_endpoint = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    static_pdf_base_url = "https://static.cninfo.com.cn/"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        static_pdf_base_url: str | None = None,
        timeout_seconds: int = 15,
        retry_count: int = 1,
    ) -> None:
        self.endpoint = endpoint or self.historical_endpoint
        self.static_pdf_base_url = static_pdf_base_url or self.static_pdf_base_url
        self.timeout_seconds = int(timeout_seconds)
        self.retry_count = max(0, int(retry_count))

    def query_announcements(self, plan: CninfoQueryPlan) -> list[CninfoAnnouncementRecord]:
        records: list[CninfoAnnouncementRecord] = []
        for page_num in range(1, max(1, plan.max_pages) + 1):
            payload = self._payload(plan, page_num=page_num)
            data = self._post_form(payload)
            page_records = _records_from_payload(data, static_pdf_base_url=self.static_pdf_base_url)
            records.extend(page_records)
            total_pages = _coerce_int(data.get("totalpages") or data.get("totalPages"))
            if total_pages is not None and page_num >= total_pages:
                break
            if not page_records:
                break
        return records

    def _payload(self, plan: CninfoQueryPlan, *, page_num: int) -> dict[str, str]:
        stock_query_types = {"stock_code", "stock_org"}
        is_stock_query = plan.query_type in stock_query_types
        stock = plan.stock_code.strip() if is_stock_query else ""
        search_key = stock if is_stock_query else plan.search_key.strip()
        payload = {
            "pageNum": str(page_num),
            "pageSize": str(max(1, plan.page_size)),
            "column": plan.column or "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": stock,
            "searchkey": search_key,
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": _date_range(plan),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        if plan.org_id and stock and is_stock_query:
            payload["secid"] = f"{stock},{plan.org_id}"
        return payload

    def _post_form(self, payload: dict[str, str]) -> dict[str, Any]:
        body = parse.urlencode(payload).encode("utf-8")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
            "Origin": "https://www.cninfo.com.cn",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
        }
        last_error: Exception | None = None
        for _attempt in range(self.retry_count + 1):
            try:
                request = Request(self.endpoint, data=body, headers=headers, method="POST")
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
        raise SourceUnavailableError("cninfo_announcement", f"CNINFO query failed: {last_error}")


class CninfoAnnouncementAdapter:
    source_type = "cninfo_announcement"
    source_name = "巨潮资讯网"

    def __init__(
        self,
        documents: list[SourceDocument] | None = None,
        *,
        client: CninfoClient | None = None,
        pdf_text_extractor: PdfTextExtractor | None = None,
        timeout_seconds: int = 15,
        retry_count: int = 1,
        page_size: int = 30,
        max_pages: int = 2,
        pdf_parse_limit: int = 2,
    ) -> None:
        self._documents = list(documents or [])
        self._client = client or UrlopenCninfoClient(timeout_seconds=timeout_seconds, retry_count=retry_count)
        self._pdf_text_extractor = pdf_text_extractor
        self._timeout_seconds = int(timeout_seconds)
        self._page_size = int(page_size)
        self._max_pages = int(max_pages)
        self._pdf_parse_limit = max(0, int(pdf_parse_limit))

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        if self._documents:
            return SourceCollectionResult(documents=[_normalize_cninfo_document(item) for item in self._documents])

        started_at = _now_iso()
        plans, limitations = self._build_query_plans(request=request, profile=profile)
        attempted: list[str] = []
        all_records: list[CninfoAnnouncementRecord] = []
        relevant: list[CninfoAnnouncementRecord] = []
        final_plan = plans[0]
        try:
            for plan in plans:
                attempted.append(_strategy_id(plan))
                records = self._client.query_announcements(plan)
                all_records.extend(records)
                plan_relevant = _filter_relevant(records, request=request, profile=profile)
                if plan_relevant:
                    relevant = plan_relevant
                    final_plan = plan
                    break
        except SourceUnavailableError:
            raise
        except Exception as exc:
            raise SourceUnavailableError(self.source_type, str(exc)) from exc

        if not relevant:
            message = "巨潮资讯网未返回可用于该企业和时间范围的公告证据。"
            limitations.append(message)
            return SourceCollectionResult(
                documents=[],
                limitations=limitations,
                diagnostics=[
                    SourceRetrievalDiagnostic(
                        source_type=self.source_type,
                        status="empty",
                        query_strategy=">".join(attempted),
                        cache_decision="live_fetch",
                        raw_count=len(all_records),
                        filtered_count=0,
                        document_count=0,
                        failure_reason=message,
                        started_at=started_at,
                        completed_at=_now_iso(),
                    )
                ],
            )

        parsed_ids = {record.announcement_id for record in _select_pdf_records(relevant, self._pdf_parse_limit)}
        documents: list[SourceDocument] = []
        for record in relevant:
            parsed_result = self._extract_pdf(record) if record.announcement_id in parsed_ids else None
            if parsed_result is not None and parsed_result.parse_status == "failed":
                limitations.append(f"巨潮资讯网公告 PDF 解析失败：{record.title}：{parsed_result.parse_error}")
            documents.append(
                _record_to_document(
                    record,
                    parsed_result=parsed_result,
                    query_plan=final_plan,
                    attempted_strategies=attempted,
                )
            )
        return SourceCollectionResult(
            documents=documents,
            limitations=limitations,
            diagnostics=[
                SourceRetrievalDiagnostic(
                    source_type=self.source_type,
                    status="done",
                    query_strategy=">".join(attempted),
                    cache_decision="live_fetch",
                    raw_count=len(all_records),
                    filtered_count=len(relevant),
                    document_count=len(documents),
                    started_at=started_at,
                    completed_at=_now_iso(),
                )
            ],
        )

    def extract_pdf_text(self, pdf_url: str) -> str:
        result = self._extract_pdf(CninfoAnnouncementRecord(announcement_id="", title="", pdf_url=pdf_url))
        return result.text

    def _build_query_plans(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> tuple[list[CninfoQueryPlan], list[str]]:
        metadata = getattr(profile, "metadata", {}) if hasattr(profile, "metadata") else {}
        stock_code = request.stock_code.strip() or profile.stock_code.strip()
        limitations: list[str] = []
        if not stock_code:
            limitations.append("未解析到可靠 A 股股票代码，巨潮资讯网公告检索退回企业名称搜索。")
        start_date, end_date = _date_window(request.time_range)
        column = str(metadata.get("cninfoColumn") or _column_for_stock(stock_code) or "szse")
        org_id = str(metadata.get("cninfoOrgId") or "")
        terms = _fallback_terms(request=request, profile=profile, metadata=metadata)
        plans: list[CninfoQueryPlan] = []
        if stock_code:
            plans.append(
                CninfoQueryPlan(
                    search_key=request.enterprise_name.strip(),
                    stock_code=stock_code,
                    column=column,
                    org_id=org_id,
                    start_date=start_date,
                    end_date=end_date,
                    page_size=self._page_size,
                    max_pages=self._max_pages,
                    query_type="stock_org" if org_id else "stock_code",
                )
            )
            if not org_id:
                limitations.append("巨潮资讯网缺少 cninfoOrgId，若股票代码检索为空将尝试企业名称回退搜索。")
        for term in terms:
            plans.append(
                CninfoQueryPlan(
                    search_key=term,
                    stock_code=stock_code,
                    column=column,
                    org_id=org_id,
                    start_date=start_date,
                    end_date=end_date,
                    page_size=self._page_size,
                    max_pages=self._max_pages,
                    query_type="name_fallback" if stock_code else "name",
                )
            )
        if not plans:
            plans.append(
                CninfoQueryPlan(
                    search_key=request.enterprise_name.strip(),
                    column=column,
                    start_date=start_date,
                    end_date=end_date,
                    page_size=self._page_size,
                    max_pages=self._max_pages,
                    query_type="name",
                )
            )
        return plans, limitations

    def _extract_pdf(self, record: CninfoAnnouncementRecord) -> PdfTextExtractionResult:
        if self._pdf_text_extractor is None or not record.pdf_url:
            return PdfTextExtractionResult(parse_status="pending")
        request = Request(
            str(record.pdf_url),
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                data = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            return PdfTextExtractionResult(parse_status="failed", parse_error=str(exc))
        if not data:
            return PdfTextExtractionResult(parse_status="failed", parse_error="CNINFO PDF response was empty")
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(data)
            temp_path = Path(handle.name)
        try:
            result = self._pdf_text_extractor(temp_path)
            if isinstance(result, PdfTextExtractionResult):
                return result
            text = str(result or "")
            return PdfTextExtractionResult(text=text, parse_status="parsed" if text.strip() else "failed")
        except Exception as exc:
            return PdfTextExtractionResult(parse_status="failed", parse_error=str(exc))
        finally:
            temp_path.unlink(missing_ok=True)


def _records_from_payload(payload: dict[str, Any], *, static_pdf_base_url: str) -> list[CninfoAnnouncementRecord]:
    announcements = payload.get("announcements")
    if not isinstance(announcements, list):
        return []
    records: list[CninfoAnnouncementRecord] = []
    for item in announcements:
        if not isinstance(item, dict):
            continue
        adjunct_url = str(item.get("adjunctUrl") or item.get("adjunct_url") or "").strip()
        pdf_url = _pdf_url(adjunct_url, static_pdf_base_url=static_pdf_base_url)
        title = _clean_title(str(item.get("announcementTitle") or item.get("title") or ""))
        announcement_id = str(item.get("announcementId") or item.get("id") or adjunct_url or title).strip()
        if not title and not announcement_id:
            continue
        records.append(
            CninfoAnnouncementRecord(
                announcement_id=announcement_id,
                title=title or "未命名公告",
                announcement_time=_format_cninfo_time(item.get("announcementTime") or item.get("announcement_time")),
                sec_code=str(item.get("secCode") or item.get("sec_code") or "").strip(),
                sec_name=_clean_title(str(item.get("secName") or item.get("sec_name") or "")),
                org_id=str(item.get("orgId") or item.get("org_id") or "").strip(),
                adjunct_url=adjunct_url,
                pdf_url=pdf_url,
                announcement_type=str(item.get("announcementType") or item.get("category") or "").strip(),
                metadata=dict(item),
            )
        )
    return records


def _record_to_document(
    record: CninfoAnnouncementRecord,
    *,
    parsed_result: PdfTextExtractionResult | None,
    query_plan: CninfoQueryPlan,
    attempted_strategies: list[str] | None = None,
) -> SourceDocument:
    parse_metadata: dict[str, Any] = {}
    content = ""
    status = "fetched"
    parse_status = "pending"
    if parsed_result is not None:
        content = parsed_result.text
        status = "parsed" if parsed_result.succeeded else "fetched"
        parse_status = parsed_result.parse_status
        parse_metadata = {
            "pageCount": parsed_result.page_count,
            "extractionMethod": parsed_result.extraction_method,
            "ocrUsed": parsed_result.ocr_used,
            "ocrProvider": parsed_result.ocr_provider,
            "parseStatus": parsed_result.parse_status,
            "parseError": parsed_result.parse_error,
            "status": status if parsed_result.succeeded else "fetched",
            "errorMessage": parsed_result.parse_error,
        }
    metadata = {
        **record.metadata,
        **parse_metadata,
        "announcementId": record.announcement_id,
        "secCode": record.sec_code,
        "secName": _clean_title(record.sec_name),
        "orgId": record.org_id,
        "announcementTime": record.announcement_time,
        "announcementType": record.announcement_type,
        "adjunctUrl": record.adjunct_url,
        "pdfUrl": record.pdf_url,
        "queryType": query_plan.query_type,
        "queryStrategy": _strategy_id(query_plan),
        "attemptedQueryStrategies": list(attempted_strategies or [_strategy_id(query_plan)]),
        "parseStatus": parse_status,
        "status": status,
    }
    return SourceDocument(
        id=f"cninfo:{record.announcement_id}",
        source_type="cninfo_announcement",
        source_name=CninfoAnnouncementAdapter.source_name,
        title=_clean_title(record.title),
        content=content or record.title,
        url=record.pdf_url or record.adjunct_url,
        published_at=record.announcement_time,
        authority_score=0.95 if query_plan.query_type in {"stock_code", "stock_org"} else 0.82,
        relevance_scope="enterprise",
        metadata=metadata,
    )


def _normalize_cninfo_document(document: SourceDocument) -> SourceDocument:
    return SourceDocument(
        id=document.id,
        source_type="cninfo_announcement",
        source_name=document.source_name or CninfoAnnouncementAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or 0.95),
        relevance_scope=document.relevance_scope or "enterprise",
        metadata=document.metadata,
    )


def _filter_relevant(
    records: list[CninfoAnnouncementRecord],
    *,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
) -> list[CninfoAnnouncementRecord]:
    enterprise = request.enterprise_name.strip()
    stock_code = request.stock_code.strip() or profile.stock_code.strip()
    keywords = [enterprise, stock_code, *profile.keywords]
    relevant: list[CninfoAnnouncementRecord] = []
    for record in records:
        haystack = f"{record.title} {record.sec_code} {record.sec_name}"
        if stock_code and record.sec_code and stock_code != record.sec_code:
            continue
        if stock_code:
            relevant.append(record)
            continue
        if any(keyword and keyword in haystack for keyword in keywords):
            relevant.append(record)
    return relevant


def _select_pdf_records(records: list[CninfoAnnouncementRecord], limit: int) -> list[CninfoAnnouncementRecord]:
    if limit <= 0:
        return []
    scored = sorted(records, key=_pdf_relevance_score, reverse=True)
    return [record for record in scored if record.pdf_url][:limit]


def _pdf_relevance_score(record: CninfoAnnouncementRecord) -> tuple[int, str]:
    title = record.title
    score = 0
    for keyword in ("重大合同", "中标", "投资", "研发", "新产品", "问询函", "诉讼", "减持", "业绩预告", "年度报告"):
        if keyword in title:
            score += 3
    if "年度报告" in title:
        score -= 1
    return score, record.announcement_time


def _pdf_url(adjunct_url: str, *, static_pdf_base_url: str) -> str:
    if not adjunct_url:
        return ""
    if adjunct_url.startswith("http://") or adjunct_url.startswith("https://"):
        return adjunct_url
    return parse.urljoin(static_pdf_base_url.rstrip("/") + "/", adjunct_url.lstrip("/"))


def _clean_title(value: str) -> str:
    return re.sub(r"</?em[^>]*>", "", value or "", flags=re.I).strip()


def _fallback_terms(
    *,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
    metadata: dict[str, Any],
) -> list[str]:
    values = [
        str(metadata.get("securityName") or ""),
        str(metadata.get("companyName") or ""),
        request.enterprise_name,
        profile.name,
    ]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _clean_title(str(value or "")).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _strategy_id(plan: CninfoQueryPlan) -> str:
    if plan.query_type == "stock_org":
        return "cninfo.stock_org.v1"
    if plan.query_type == "stock_code":
        return "cninfo.stock_only.v1"
    if plan.query_type == "name_fallback":
        return f"cninfo.name_fallback.v1:{plan.search_key}"
    return f"cninfo.name.v1:{plan.search_key}"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _format_cninfo_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "").replace("/", "-").strip()


def _date_range(plan: CninfoQueryPlan) -> str:
    if plan.start_date and plan.end_date:
        return f"{plan.start_date}~{plan.end_date}"
    return ""


def _date_window(time_range: str) -> tuple[str, str]:
    now = datetime.utcnow().date()
    match = re.search(r"近\s*(\d+)\s*天", str(time_range or ""))
    days = int(match.group(1)) if match else 365
    start = now - timedelta(days=max(1, days))
    return start.isoformat(), now.isoformat()


def _column_for_stock(stock_code: str) -> str:
    if not stock_code:
        return ""
    return "sse" if stock_code.startswith("6") else "szse"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
