from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib import parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..bidding_planning import (
    BIDDING_CATEGORY_LABELS,
    BiddingQueryTerm,
    BiddingSearchPlan,
    build_bidding_search_plan,
)
from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument, SourceRetrievalDiagnostic
from .base import SourceCollectionResult, SourceUnavailableError


@dataclass(frozen=True)
class BiddingNoticeCandidate:
    title: str
    url: str
    published_at: str = ""
    notice_id: str = ""
    notice_type: str = ""
    notice_category: str = ""
    project_code: str = ""
    project_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BiddingNoticeDetail:
    title: str
    url: str
    content: str = ""
    published_at: str = ""
    notice_id: str = ""
    notice_type: str = ""
    project_name: str = ""
    project_code: str = ""
    buyer_name: str = ""
    tenderer: str = ""
    agency: str = ""
    winning_bidder: str = ""
    candidates: tuple[str, ...] = field(default_factory=tuple)
    amount: str = ""
    currency: str = ""
    region: str = ""
    source_channel: str = "cebpubservice"
    attachments: tuple[dict[str, str], ...] = field(default_factory=tuple)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BiddingPage:
    url: str
    html: str


class CebBiddingClient(Protocol):
    def fetch_search_page(self, *, query: str, notice_category: str, page: int) -> BiddingPage:
        ...

    def fetch_detail_page(self, url: str) -> BiddingPage:
        ...


class UrlopenCebBiddingClient:
    base_url = "http://www.cebpubservice.com"
    search_path = "/ctpsp_iiss/searchbusinesstypebeforedooraction/getSearch.do"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        search_path: str | None = None,
        timeout_seconds: int = 15,
        retry_count: int = 1,
    ) -> None:
        self.base_url = (base_url or self.base_url).rstrip("/")
        self.search_path = search_path or self.search_path
        self.timeout_seconds = int(timeout_seconds)
        self.retry_count = max(0, int(retry_count))

    def fetch_search_page(self, *, query: str, notice_category: str, page: int) -> BiddingPage:
        params = {
            "keyword": query,
            "searchName": query,
            "pageNo": str(max(1, int(page))),
            "page": str(max(1, int(page))),
            "businessType": _category_param(notice_category),
            "category": notice_category,
        }
        url = f"{self.base_url}{self.search_path}?{parse.urlencode(params)}"
        return BiddingPage(url=url, html=self._get(url))

    def fetch_detail_page(self, url: str) -> BiddingPage:
        return BiddingPage(url=url, html=self._get(url))

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Referer": self.base_url + "/",
        }
        last_error: Exception | None = None
        for _attempt in range(self.retry_count + 1):
            try:
                request = Request(url, headers=headers, method="GET")
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
                return raw.decode(_encoding_from_headers(getattr(response, "headers", None)) or "utf-8", errors="replace")
            except (HTTPError, URLError, TimeoutError, UnicodeError) as exc:
                last_error = exc
        raise SourceUnavailableError("bidding_procurement", f"CEB request failed: {last_error}")


class BiddingProcurementAdapter:
    source_type = "bidding_procurement"
    source_name = "中国招标投标公共服务平台"

    def __init__(
        self,
        documents: list[SourceDocument] | None = None,
        *,
        client: CebBiddingClient | None = None,
        planner=None,
        timeout_seconds: int = 15,
        retry_count: int = 1,
        max_queries: int = 10,
        max_pages: int = 1,
        detail_fetch_limit: int = 8,
    ) -> None:
        self._documents = list(documents or [])
        self._client = client or UrlopenCebBiddingClient(timeout_seconds=timeout_seconds, retry_count=retry_count)
        self._planner = planner or build_bidding_search_plan
        self._max_queries = max(1, int(max_queries))
        self._max_pages = max(1, int(max_pages))
        self._detail_fetch_limit = max(1, int(detail_fetch_limit))

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        started_at = _now_iso()
        if self._documents:
            documents = [_normalize_bidding_document(item) for item in self._documents]
            return SourceCollectionResult(
                documents=documents,
                diagnostics=[
                    SourceRetrievalDiagnostic(
                        source_type=self.source_type,
                        status="done",
                        query_strategy="cebpubservice.injected.v1",
                        cache_decision="cache_bypass",
                        raw_count=len(documents),
                        filtered_count=len(documents),
                        document_count=len(documents),
                        started_at=started_at,
                        completed_at=_now_iso(),
                    )
                ],
            )

        plan = self._planner(
            request=request,
            profile=profile,
            max_queries=self._max_queries,
            max_pages=self._max_pages,
            detail_fetch_limit=self._detail_fetch_limit,
        )
        limitations = list(getattr(plan, "limitations", []) or [])
        candidates, source_limitations, stats = self._collect_candidates(plan)
        limitations.extend(source_limitations)
        if not candidates:
            message = "中国招标投标公共服务平台未返回可用于该企业机器人行业分析的招投标证据。"
            limitations.append(message)
            status = "blocked" if stats.get("blocked") else "unavailable" if stats.get("unavailable") else "empty"
            return SourceCollectionResult(
                documents=[],
                limitations=_dedupe(limitations),
                diagnostics=[
                    SourceRetrievalDiagnostic(
                        source_type=self.source_type,
                        status=status,
                        query_strategy="cebpubservice.live_entrypoint.v1",
                        cache_decision="live_fetch",
                        raw_count=int(stats.get("raw_count") or 0),
                        filtered_count=0,
                        document_count=0,
                        failure_reason=message if status == "empty" else "; ".join(source_limitations),
                        started_at=started_at,
                        completed_at=_now_iso(),
                    )
                ],
            )

        documents: list[SourceDocument] = []
        target_terms = _target_terms(request=request, profile=profile)
        for candidate in candidates[: plan.detail_fetch_limit]:
            query_term = _candidate_query_term(candidate, plan)
            try:
                page = self._client.fetch_detail_page(candidate.url)
                if is_blocked_bidding_page(page.html):
                    limitations.append(f"中国招标投标公共服务平台详情页可能被反爬限制：{candidate.title}")
                    detail = _candidate_to_detail(candidate, status="blocked", error="blocked detail page")
                else:
                    detail = parse_bidding_detail_page(page.html, page.url, candidate=candidate)
            except SourceUnavailableError as exc:
                limitations.append(f"中国招标投标公共服务平台详情页不可用：{candidate.title}：{exc}")
                detail = _candidate_to_detail(candidate, status="detail_failed", error=str(exc))
            except Exception as exc:
                limitations.append(f"中国招标投标公共服务平台详情页解析失败：{candidate.title}：{exc}")
                detail = _candidate_to_detail(candidate, status="metadata_limited", error=str(exc))
            if not detail.content.strip() or detail.raw_metadata.get("status") == "metadata_limited":
                limitations.append(f"中国招标投标公共服务平台公告正文提取受限：{detail.title}")
            documents.append(_detail_to_document(detail, plan=plan, query_term=query_term, candidate=candidate, target_terms=target_terms))

        documents = _dedupe_documents(documents)
        return SourceCollectionResult(
            documents=documents,
            limitations=_dedupe(limitations),
            diagnostics=[
                SourceRetrievalDiagnostic(
                    source_type=self.source_type,
                    status="done" if documents else "parser_error",
                    query_strategy="cebpubservice.live_entrypoint.v1",
                    cache_decision="live_fetch",
                    raw_count=int(stats.get("raw_count") or len(candidates)),
                    filtered_count=len(candidates),
                    document_count=len(documents),
                    started_at=started_at,
                    completed_at=_now_iso(),
                )
            ],
        )

    def _collect_candidates(self, plan: BiddingSearchPlan) -> tuple[list[BiddingNoticeCandidate], list[str], dict[str, Any]]:
        candidates: list[BiddingNoticeCandidate] = []
        limitations: list[str] = []
        stats: dict[str, Any] = {"raw_count": 0, "blocked": False, "unavailable": False}
        for term in plan.query_terms:
            for category in plan.notice_categories:
                for page_num in range(1, plan.max_pages + 1):
                    try:
                        page = self._client.fetch_search_page(query=term.keyword, notice_category=category, page=page_num)
                    except SourceUnavailableError as exc:
                        limitations.append(f"中国招标投标公共服务平台搜索不可用：{term.keyword}：{exc}")
                        stats["unavailable"] = True
                        break
                    except Exception as exc:
                        limitations.append(f"中国招标投标公共服务平台搜索失败：{term.keyword}：{exc}")
                        stats["unavailable"] = True
                        break
                    if is_blocked_bidding_page(page.html):
                        limitations.append(f"中国招标投标公共服务平台搜索可能被反爬限制：{term.keyword}")
                        stats["blocked"] = True
                        break
                    page_candidates = parse_bidding_candidates_page(
                        page.html,
                        page.url,
                        notice_category=category,
                        query_term=term,
                    )
                    stats["raw_count"] += len(page_candidates)
                    candidates.extend(page_candidates)
                    if not page_candidates:
                        break
        return dedupe_bidding_candidates(candidates), limitations, stats


def parse_bidding_candidates_page(
    raw_html: str,
    page_url: str,
    *,
    notice_category: str = "",
    query_term: BiddingQueryTerm | None = None,
) -> list[BiddingNoticeCandidate]:
    candidates = _json_candidates(raw_html, page_url, notice_category=notice_category, query_term=query_term)
    base_url = page_url or UrlopenCebBiddingClient.base_url
    for match in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", raw_html or "", flags=re.I | re.S):
        attrs = match.group("attrs") or ""
        href_match = re.search(r"href\s*=\s*['\"](?P<href>[^'\"]+)['\"]", attrs, flags=re.I)
        if not href_match:
            continue
        href = html.unescape(href_match.group("href")).strip()
        url = parse.urljoin(base_url, href)
        title = _clean_text(match.group("body"))
        if not _looks_like_bidding_link(title, url):
            continue
        window = (raw_html or "")[max(0, match.start() - 180) : match.end() + 260]
        notice_type = _infer_notice_type(f"{title} {window}", fallback=notice_category)
        metadata = {
            "resultPageUrl": page_url,
            "searchKeyword": query_term.keyword if query_term else "",
            "queryTerm": query_term.to_metadata() if query_term else {},
            "noticeCategory": notice_category,
            "noticeCategoryLabel": BIDDING_CATEGORY_LABELS.get(notice_category, notice_category),
        }
        candidates.append(
            BiddingNoticeCandidate(
                title=title,
                url=url,
                published_at=_extract_date(window),
                notice_id=_notice_id_from_url(url),
                notice_type=notice_type,
                notice_category=notice_category,
                project_code=_extract_labeled_value(window, ("项目编号", "招标编号", "采购编号")),
                project_name=_extract_labeled_value(window, ("项目名称",)),
                metadata=metadata,
            )
        )
    return dedupe_bidding_candidates(candidates)


def parse_bidding_detail_page(raw_html: str, page_url: str, *, candidate: BiddingNoticeCandidate | None = None) -> BiddingNoticeDetail:
    metadata = _meta_values(raw_html)
    title = (
        metadata.get("title")
        or metadata.get("og:title")
        or _first_tag_text(raw_html, "h1")
        or _first_tag_text(raw_html, "h2")
        or _html_title(raw_html)
        or (candidate.title if candidate else "")
        or "未命名招采公告"
    )
    content_html = _content_html(raw_html)
    content = _clean_text(content_html or raw_html)
    compact = f"{title}\n{content}"
    url = page_url or (candidate.url if candidate else "")
    notice_type = _infer_notice_type(compact, fallback=(candidate.notice_type if candidate else ""))
    project_name = _extract_labeled_value(compact, ("项目名称", "工程名称")) or (candidate.project_name if candidate else "")
    project_code = _extract_labeled_value(compact, ("项目编号", "招标编号", "采购编号", "项目代码")) or (candidate.project_code if candidate else "")
    buyer = _extract_labeled_value(compact, ("采购人", "招标人", "招标单位", "建设单位"))
    tenderer = _extract_labeled_value(compact, ("投标人", "供应商"))
    agency = _extract_labeled_value(compact, ("代理机构", "招标代理", "采购代理机构"))
    winning_bidder = _extract_labeled_value(compact, ("中标人", "成交供应商", "第一中标候选人", "中标候选人"))
    candidates = tuple(_extract_candidates(compact, winning_bidder=winning_bidder))
    amount = _normalize_amount(_extract_labeled_value(compact, ("中标金额", "成交金额", "投标报价", "预算金额", "合同金额")))
    published_at = (
        _normalize_date(metadata.get("publishdate") or metadata.get("pubdate") or metadata.get("date"))
        or _extract_labeled_value(compact, ("发布日期", "发布时间", "公示时间"))
        or (candidate.published_at if candidate else "")
    )
    attachments = tuple(_extract_attachments(raw_html, base_url=url))
    notice_id = (
        metadata.get("contentid")
        or metadata.get("noticeid")
        or (candidate.notice_id if candidate else "")
        or project_code
        or _notice_id_from_url(url)
        or _hash_text(f"{title}:{url}")
    )
    status = "fetched" if content and len(content) > len(title) + 12 else "metadata_limited"
    raw_metadata = {
        **metadata,
        "detailUrl": url,
        "sourceChannel": "cebpubservice",
        "status": status,
        "extractionDiagnostics": {
            "contentLength": len(content),
            "hasStructuredFields": bool(project_name or buyer or winning_bidder or amount),
        },
    }
    return BiddingNoticeDetail(
        title=title,
        url=url,
        content=content,
        published_at=published_at,
        notice_id=str(notice_id),
        notice_type=notice_type,
        project_name=project_name,
        project_code=project_code,
        buyer_name=buyer,
        tenderer=tenderer,
        agency=agency,
        winning_bidder=winning_bidder,
        candidates=candidates,
        amount=amount,
        currency=_infer_currency(amount),
        region=_infer_region(compact),
        source_channel="cebpubservice",
        attachments=attachments,
        raw_metadata=raw_metadata,
    )


def dedupe_bidding_candidates(candidates: list[BiddingNoticeCandidate]) -> list[BiddingNoticeCandidate]:
    seen: set[str] = set()
    result: list[BiddingNoticeCandidate] = []
    for candidate in candidates:
        key = _candidate_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def is_blocked_bidding_page(raw_html: str) -> bool:
    text = _clean_text(raw_html or "")
    lowered = text.lower()
    if not text:
        return True
    blocked_terms = (
        "captcha",
        "验证码",
        "访问过于频繁",
        "安全验证",
        "禁止访问",
        "forbidden",
        "service unavailable",
        "blocked",
        "anti",
        "waf",
        "eval(function",
        "ctbpsp.com/cutominfoapi",
    )
    if any(term in lowered or term in text for term in blocked_terms):
        return True
    return len(text) < 20 and "<html" in (raw_html or "").lower()


def _detail_to_document(
    detail: BiddingNoticeDetail,
    *,
    plan: BiddingSearchPlan,
    query_term: BiddingQueryTerm | None,
    candidate: BiddingNoticeCandidate,
    target_terms: list[str],
) -> SourceDocument:
    notice_id = detail.notice_id or candidate.notice_id or _hash_text(detail.url or detail.title)
    relevance_scope, direct_role, matched_enterprise = _classify_relevance(detail, target_terms=target_terms)
    matched_keywords = _dedupe(
        [
            query_term.keyword if query_term else "",
            *(plan.keywords[:3] if query_term is None else []),
            detail.project_name,
            detail.notice_type,
        ]
    )
    metadata = {
        **candidate.metadata,
        **detail.raw_metadata,
        "noticeId": notice_id,
        "sourceDocumentId": notice_id,
        "noticeType": detail.notice_type or candidate.notice_type,
        "noticeCategory": candidate.notice_category,
        "noticeCategoryLabel": BIDDING_CATEGORY_LABELS.get(candidate.notice_category, candidate.notice_category),
        "projectName": detail.project_name,
        "projectCode": detail.project_code or candidate.project_code,
        "buyerName": detail.buyer_name,
        "tenderer": detail.tenderer,
        "agency": detail.agency,
        "winningBidder": detail.winning_bidder,
        "candidates": list(detail.candidates),
        "amount": detail.amount,
        "currency": detail.currency,
        "region": detail.region,
        "matchedEnterpriseName": matched_enterprise,
        "directMatchRole": direct_role,
        "matchedKeywords": matched_keywords,
        "matchedSegments": _dedupe([query_term.matched_segment if query_term else ""]),
        "matchedScenario": query_term.matched_scenario if query_term else "",
        "sourceChannel": detail.source_channel,
        "attachments": list(detail.attachments),
        "attachmentFullTextParsed": False,
        "biddingSearchPlan": plan.to_metadata(),
        "inferenceLevel": "direct" if relevance_scope == "enterprise" else "market_demand",
        "status": detail.raw_metadata.get("status") or ("fetched" if detail.content else "metadata_limited"),
    }
    return SourceDocument(
        id=f"bidding:{notice_id}",
        source_type="bidding_procurement",
        source_name=BiddingProcurementAdapter.source_name,
        title=detail.title or candidate.title,
        content=detail.content or " ".join(_dedupe([detail.project_name, detail.buyer_name, detail.winning_bidder, detail.amount])),
        url=detail.url or candidate.url,
        published_at=detail.published_at or candidate.published_at,
        authority_score=0.9 if relevance_scope == "enterprise" else 0.82,
        relevance_scope=relevance_scope,
        metadata=metadata,
    )


def _normalize_bidding_document(document: SourceDocument) -> SourceDocument:
    metadata = dict(document.metadata or {})
    relevance_scope = document.relevance_scope or str(metadata.get("relevanceScope") or "market_demand")
    return SourceDocument(
        id=document.id,
        source_type="bidding_procurement",
        source_name=document.source_name or BiddingProcurementAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or (0.9 if relevance_scope == "enterprise" else 0.82)),
        relevance_scope=relevance_scope,
        metadata=metadata,
    )


def _candidate_to_detail(candidate: BiddingNoticeCandidate, *, status: str, error: str) -> BiddingNoticeDetail:
    return BiddingNoticeDetail(
        title=candidate.title,
        url=candidate.url,
        published_at=candidate.published_at,
        notice_id=candidate.notice_id,
        notice_type=candidate.notice_type,
        project_name=candidate.project_name,
        project_code=candidate.project_code,
        raw_metadata={"status": status, "errorMessage": error, "extractionDiagnostics": {"metadataOnly": True}},
    )


def _classify_relevance(detail: BiddingNoticeDetail, *, target_terms: list[str]) -> tuple[str, str, str]:
    fields = {
        "winner": detail.winning_bidder,
        "candidate": " ".join(detail.candidates),
        "buyer": detail.buyer_name,
        "tenderer": detail.tenderer,
        "content": detail.content,
        "title": detail.title,
    }
    for term in target_terms:
        for role, value in fields.items():
            if term and term in str(value or ""):
                return "enterprise", role, term
    if detail.winning_bidder or detail.candidates:
        return "market_demand", "competitor" if _is_robotics_relevant(detail) else "", ""
    return "market_demand", "", ""


def _target_terms(*, request: RoboticsInsightRequest, profile: EnterpriseProfile) -> list[str]:
    values = [request.enterprise_name, profile.name]
    if request.enterprise_name.endswith("股份有限公司"):
        values.append(request.enterprise_name.removesuffix("股份有限公司"))
    if request.enterprise_name.endswith("有限公司"):
        values.append(request.enterprise_name.removesuffix("有限公司"))
    return [item for item in _dedupe(values) if len(item) >= 2]


def _json_candidates(
    raw_html: str,
    page_url: str,
    *,
    notice_category: str,
    query_term: BiddingQueryTerm | None,
) -> list[BiddingNoticeCandidate]:
    text = raw_html or ""
    candidates: list[BiddingNoticeCandidate] = []
    for block_match in re.finditer(r"\{[^{}]*(?:title|bulletinName|noticeTitle)[^{}]*\}", text, flags=re.I | re.S):
        block = block_match.group(0)
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            payload = _loose_json_values(block)
        title = str(payload.get("title") or payload.get("bulletinName") or payload.get("noticeTitle") or "").strip()
        href = str(payload.get("url") or payload.get("href") or payload.get("bulletinUrl") or payload.get("link") or "").strip()
        if not title:
            continue
        url = parse.urljoin(page_url or UrlopenCebBiddingClient.base_url, href)
        metadata = {
            "resultPageUrl": page_url,
            "searchKeyword": query_term.keyword if query_term else "",
            "queryTerm": query_term.to_metadata() if query_term else {},
            "noticeCategory": notice_category,
            "noticeCategoryLabel": BIDDING_CATEGORY_LABELS.get(notice_category, notice_category),
            "rawCandidate": payload,
        }
        candidates.append(
            BiddingNoticeCandidate(
                title=title,
                url=url,
                published_at=_normalize_date(str(payload.get("publishTime") or payload.get("publishDate") or payload.get("date") or "")),
                notice_id=str(payload.get("id") or payload.get("noticeId") or _notice_id_from_url(url) or "").strip(),
                notice_type=_infer_notice_type(title, fallback=notice_category),
                notice_category=notice_category,
                project_code=str(payload.get("projectCode") or payload.get("code") or "").strip(),
                project_name=str(payload.get("projectName") or "").strip(),
                metadata=metadata,
            )
        )
    return candidates


def _loose_json_values(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in re.finditer(r"['\"]?(?P<key>[A-Za-z_][\w]*)['\"]?\s*:\s*['\"](?P<value>[^'\"]*)['\"]", block):
        values[match.group("key")] = html.unescape(match.group("value")).strip()
    return values


def _candidate_key(candidate: BiddingNoticeCandidate) -> str:
    if candidate.notice_id:
        return f"id:{candidate.notice_id}"
    if candidate.url:
        return f"url:{candidate.url.lower()}"
    if candidate.project_code:
        return f"code:{candidate.project_code}"
    return f"title:{candidate.title}:{candidate.published_at}"


def _candidate_query_term(candidate: BiddingNoticeCandidate, plan: BiddingSearchPlan) -> BiddingQueryTerm | None:
    keyword = str(candidate.metadata.get("searchKeyword") or "")
    for term in plan.query_terms:
        if term.keyword == keyword:
            return term
    return plan.query_terms[0] if plan.query_terms else None


def _looks_like_bidding_link(title: str, url: str) -> bool:
    if not title or len(title) < 4:
        return False
    if any(skip in title for skip in ("首页", "登录", "注册", "帮助", "联系我们", "客户端下载", "信息公开", "公告公示", "政策法规", "服务指南", "交易平台", "平台介绍")):
        return False
    text = f"{title} {url}".lower()
    title_terms = ("招标", "采购", "中标", "成交", "候选", "变更", "澄清", "资格预审")
    if any(term in title for term in title_terms):
        return True
    return bool(re.search(r"/(?:bulletin|notice|result|tender|bid)[/\-_]", url, flags=re.I))


def _content_html(raw_html: str) -> str:
    patterns = [
        r"<div[^>]+class=['\"][^'\"]*(?:article|content|detail|news_content)[^'\"]*['\"][^>]*>(?P<body>.*?)</div>\s*</div>",
        r"<div[^>]+id=['\"][^'\"]*(?:content|detail|article)[^'\"]*['\"][^>]*>(?P<body>.*?)</div>",
        r"<article[^>]*>(?P<body>.*?)</article>",
        r"<body[^>]*>(?P<body>.*?)</body>",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_html or "", flags=re.I | re.S)
        if match:
            return match.group("body")
    return ""


def _extract_attachments(raw_html: str, *, base_url: str) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    for match in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", raw_html or "", flags=re.I | re.S):
        href_match = re.search(r"href\s*=\s*['\"](?P<href>[^'\"]+)['\"]", match.group("attrs") or "", flags=re.I)
        if not href_match:
            continue
        href = html.unescape(href_match.group("href")).strip()
        ext_match = re.search(r"\.(pdf|docx?|xlsx?|zip|rar)(?:$|[?#])", href, flags=re.I)
        if not ext_match:
            continue
        title = _clean_text(match.group("body")) or parse.unquote(href.rsplit("/", 1)[-1])
        attachments.append({"title": title, "url": parse.urljoin(base_url, href), "fileType": ext_match.group(1).lower()})
    return attachments


def _extract_candidates(text: str, *, winning_bidder: str) -> list[str]:
    values = [winning_bidder]
    for label in ("第一中标候选人", "第二中标候选人", "第三中标候选人", "候选人名称", "供应商名称"):
        value = _extract_labeled_value(text, (label,))
        if value:
            values.append(value)
    return _dedupe(values)


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str:
    clean = _clean_text(text)
    stop_labels = "项目名称|项目编号|招标编号|采购编号|采购人|招标人|招标单位|建设单位|投标人|供应商|代理机构|招标代理|中标人|成交供应商|第一中标候选人|第二中标候选人|第三中标候选人|中标候选人|中标金额|成交金额|投标报价|预算金额|合同金额|发布日期|发布时间|公示时间"
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*(?P<value>.{{1,120}}?)(?:\s{{2,}}|(?:{stop_labels})\s*[:：]|$)"
        match = re.search(pattern, clean, flags=re.S)
        if match:
            value = re.sub(r"\s+", " ", match.group("value")).strip(" ：:，,;；")
            return _normalize_date(value) if "日期" in label or "时间" in label else value[:120]
    return ""


def _infer_notice_type(text: str, *, fallback: str = "") -> str:
    if "中标候选" in text:
        return "中标候选人公示"
    if "中标结果" in text or "中标公告" in text or "成交公告" in text:
        return "中标结果公告"
    if "资格预审" in text:
        return "资格预审公告"
    if any(term in text for term in ("变更", "澄清", "更正")):
        return "变更公告"
    if "招标" in text or "采购" in text:
        return "招标公告"
    return BIDDING_CATEGORY_LABELS.get(fallback, fallback)


def _infer_currency(amount: str) -> str:
    if "美元" in amount or "USD" in amount.upper():
        return "USD"
    if amount:
        return "CNY"
    return ""


def _normalize_amount(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.search(r"([0-9]+(?:\.[0-9]+)?\s*(?:万元|亿元|元|万|亿|人民币|CNY|USD|美元))", raw, flags=re.I)
    if match:
        return re.sub(r"\s+", "", match.group(1))
    return raw[:80]


def _infer_region(text: str) -> str:
    regions = (
        "北京",
        "上海",
        "天津",
        "重庆",
        "广东",
        "江苏",
        "浙江",
        "山东",
        "安徽",
        "湖北",
        "湖南",
        "四川",
        "福建",
        "河南",
        "河北",
        "江西",
        "陕西",
        "辽宁",
    )
    for region in regions:
        if region in text:
            return region
    return ""


def _is_robotics_relevant(detail: BiddingNoticeDetail) -> bool:
    text = f"{detail.title}\n{detail.project_name}\n{detail.content}"
    return any(term in text for term in ("机器人", "自动化", "智能制造", "机器视觉", "巡检", "清洁", "仓储", "物流"))


def _meta_values(raw_html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in re.finditer(r"<meta\b(?P<attrs>[^>]*)>", raw_html or "", flags=re.I | re.S):
        attrs = match.group("attrs") or ""
        key_match = re.search(r"(?:name|property)\s*=\s*['\"](?P<key>[^'\"]+)['\"]", attrs, flags=re.I)
        content_match = re.search(r"content\s*=\s*['\"](?P<value>[^'\"]*)['\"]", attrs, flags=re.I)
        if key_match and content_match:
            values[key_match.group("key").strip().lower()] = html.unescape(content_match.group("value")).strip()
    return values


def _first_tag_text(raw_html: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(?P<body>.*?)</{tag}>", raw_html or "", flags=re.I | re.S)
    return _clean_text(match.group("body")) if match else ""


def _html_title(raw_html: str) -> str:
    title = _first_tag_text(raw_html, "title")
    return re.sub(r"[_\-].*?(中国招标投标公共服务平台).*", "", title).strip()


def _extract_date(value: str) -> str:
    match = re.search(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})", html.unescape(value or ""))
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _normalize_date(value: str) -> str:
    return _extract_date(value) or str(value or "").replace("/", "-").strip()


def _clean_text(value: str) -> str:
    raw = re.sub(r"<script\b.*?</script>", " ", value or "", flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p\s*>", "\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[\u3000\xa0]+", " ", raw)
    raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
    raw = re.sub(r"\n\s+", "\n", raw)
    return raw.strip()


def _notice_id_from_url(url: str) -> str:
    parsed = parse.urlparse(url or "")
    query = parse.parse_qs(parsed.query)
    for key in ("id", "noticeId", "bulletinId", "guid"):
        if query.get(key):
            return str(query[key][0])
    path = parsed.path.rsplit("/", 1)[-1]
    match = re.search(r"([A-Za-z0-9_-]{5,})(?:\.html?|\.shtml)?$", path)
    if match:
        return match.group(1)
    return _hash_text(url) if url else ""


def _category_param(notice_category: str) -> str:
    mapping = {
        "tender_announcement": "招标公告",
        "prequalification_announcement": "资格预审公告",
        "winning_candidate": "中标候选人公示",
        "winning_result": "中标结果公告",
        "change_notice": "变更公告",
    }
    return mapping.get(notice_category, notice_category)


def _encoding_from_headers(headers: Any) -> str:
    if headers is None:
        return ""
    try:
        content_type = headers.get_content_charset()
        return str(content_type or "")
    except AttributeError:
        return ""


def _hash_text(value: str | None) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()


def _now_iso() -> str:
    from datetime import datetime, UTC

    return datetime.now(UTC).replace(microsecond=0, tzinfo=None).isoformat()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _dedupe_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    seen: set[str] = set()
    result: list[SourceDocument] = []
    for document in documents:
        key = document.id or document.url or f"{document.title}:{document.published_at}"
        if key in seen:
            continue
        seen.add(key)
        result.append(document)
    return result
