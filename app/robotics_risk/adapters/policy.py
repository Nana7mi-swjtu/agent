from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib import parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..policy_planning import PolicyQueryTerm, PolicySearchPlan, build_policy_search_plan
from ..schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument
from .base import SourceCollectionResult, SourceUnavailableError


@dataclass(frozen=True)
class GovPolicyCandidate:
    title: str
    url: str
    published_at: str = ""
    source_scope: str = ""
    policy_id: str = ""
    document_number: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovPolicyDetail:
    title: str
    url: str
    content: str = ""
    published_at: str = ""
    policy_id: str = ""
    issuing_agency: str = ""
    document_number: str = ""
    source_scope: str = ""
    attachments: tuple[dict[str, str], ...] = field(default_factory=tuple)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GovPolicyPage:
    url: str
    html: str


class GovPolicyClient(Protocol):
    def fetch_search_page(self, *, query: str, scope: str, page: int) -> GovPolicyPage:
        ...

    def fetch_list_page(self, *, scope: str, page: int) -> GovPolicyPage:
        ...

    def fetch_detail_page(self, url: str) -> GovPolicyPage:
        ...


class UrlopenGovPolicyClient:
    search_endpoint = "https://www.gov.cn/zhengce/zhengcewenjianku/index.htm"
    list_urls = {
        "state_council": "https://www.gov.cn/zhengce/zhengceku/gwywj/index.htm",
        "department": "https://www.gov.cn/zhengce/zhengceku/bmwj/index.htm",
    }

    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        retry_count: int = 1,
        search_endpoint: str | None = None,
        list_urls: dict[str, str] | None = None,
    ) -> None:
        self.timeout_seconds = int(timeout_seconds)
        self.retry_count = max(0, int(retry_count))
        self.search_endpoint = search_endpoint or self.search_endpoint
        self.list_urls = {**self.list_urls, **(list_urls or {})}

    def fetch_search_page(self, *, query: str, scope: str, page: int) -> GovPolicyPage:
        params = {
            "searchword": query,
            "qt": query,
            "tab": _scope_tab(scope),
            "page": str(max(1, int(page))),
        }
        url = f"{self.search_endpoint}?{parse.urlencode(params)}"
        return GovPolicyPage(url=url, html=self._get(url))

    def fetch_list_page(self, *, scope: str, page: int) -> GovPolicyPage:
        base_url = self.list_urls.get(scope) or self.list_urls["state_council"]
        url = base_url if page <= 1 else parse.urljoin(base_url, f"home_{page}.htm")
        return GovPolicyPage(url=url, html=self._get(url))

    def fetch_detail_page(self, url: str) -> GovPolicyPage:
        return GovPolicyPage(url=url, html=self._get(url))

    def _get(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.gov.cn/zhengce/zhengcewenjianku/",
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
        raise SourceUnavailableError("gov_policy", f"gov.cn request failed: {last_error}")


class GovPolicyAdapter:
    source_type = "gov_policy"
    source_name = "国务院政策文件库"

    def __init__(
        self,
        documents: list[SourceDocument] | None = None,
        *,
        client: GovPolicyClient | None = None,
        planner=None,
        timeout_seconds: int = 15,
        retry_count: int = 1,
        max_queries: int = 8,
        max_pages: int = 1,
        detail_fetch_limit: int = 8,
        enable_list_fallback: bool = True,
    ) -> None:
        self._documents = list(documents or [])
        self._client = client or UrlopenGovPolicyClient(timeout_seconds=timeout_seconds, retry_count=retry_count)
        self._planner = planner or build_policy_search_plan
        self._max_queries = max(1, int(max_queries))
        self._max_pages = max(1, int(max_pages))
        self._detail_fetch_limit = max(1, int(detail_fetch_limit))
        self._enable_list_fallback = bool(enable_list_fallback)

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> SourceCollectionResult:
        if self._documents:
            return SourceCollectionResult(documents=[_normalize_policy_document(item) for item in self._documents])

        plan = self._planner(
            request=request,
            profile=profile,
            max_queries=self._max_queries,
            max_pages=self._max_pages,
            detail_fetch_limit=self._detail_fetch_limit,
        )
        limitations = list(getattr(plan, "limitations", []) or [])
        candidates, search_limitations = self._collect_candidates(plan)
        limitations.extend(search_limitations)
        if not candidates:
            limitations.append("国务院政策文件库未返回可用于该企业机器人行业分析的政策证据。")
            return SourceCollectionResult(documents=[], limitations=_dedupe(limitations))

        documents: list[SourceDocument] = []
        for candidate in candidates[: plan.detail_fetch_limit]:
            query_term = _candidate_query_term(candidate, plan)
            try:
                page = self._client.fetch_detail_page(candidate.url)
                detail = parse_policy_detail_page(page.html, page.url, candidate=candidate)
            except SourceUnavailableError as exc:
                limitations.append(f"国务院政策文件库详情页不可用：{candidate.title}：{exc}")
                continue
            except Exception as exc:
                limitations.append(f"国务院政策文件库详情页解析失败：{candidate.title}：{exc}")
                detail = GovPolicyDetail(
                    title=candidate.title,
                    url=candidate.url,
                    published_at=candidate.published_at,
                    policy_id=candidate.policy_id,
                    document_number=candidate.document_number,
                    source_scope=candidate.source_scope,
                    raw_metadata={"status": "metadata_limited", "errorMessage": str(exc)},
                )
            if not detail.content.strip():
                limitations.append(f"国务院政策文件库政策正文提取受限：{detail.title}")
            documents.append(_detail_to_document(detail, plan=plan, query_term=query_term, candidate=candidate))
        if not documents:
            limitations.append("国务院政策文件库候选政策详情页均未能形成可用证据。")
        return SourceCollectionResult(documents=documents, limitations=_dedupe(limitations))

    def _collect_candidates(self, plan: PolicySearchPlan) -> tuple[list[GovPolicyCandidate], list[str]]:
        candidates: list[GovPolicyCandidate] = []
        limitations: list[str] = []
        for term in plan.query_terms:
            for scope in plan.source_scopes:
                for page_num in range(1, plan.max_pages + 1):
                    try:
                        page = self._client.fetch_search_page(query=term.keyword, scope=scope, page=page_num)
                    except SourceUnavailableError as exc:
                        limitations.append(f"国务院政策文件库搜索不可用：{term.keyword}：{exc}")
                        break
                    except Exception as exc:
                        limitations.append(f"国务院政策文件库搜索失败：{term.keyword}：{exc}")
                        break
                    page_candidates = parse_policy_candidates_page(
                        page.html,
                        page.url,
                        default_scope=scope,
                        query_term=term,
                    )
                    candidates.extend(page_candidates)
                    if not page_candidates:
                        break
        candidates = _dedupe_candidates(candidates)
        if candidates or not self._enable_list_fallback:
            return candidates, limitations

        for scope in plan.source_scopes:
            for page_num in range(1, plan.max_pages + 1):
                try:
                    page = self._client.fetch_list_page(scope=scope, page=page_num)
                except SourceUnavailableError as exc:
                    limitations.append(f"国务院政策文件库列表页不可用：{scope}：{exc}")
                    break
                except Exception as exc:
                    limitations.append(f"国务院政策文件库列表页失败：{scope}：{exc}")
                    break
                candidates.extend(
                    parse_policy_candidates_page(
                        page.html,
                        page.url,
                        default_scope=scope,
                        query_term=None,
                    )
                )
        return _dedupe_candidates(candidates), limitations


def parse_policy_candidates_page(
    raw_html: str,
    page_url: str,
    *,
    default_scope: str = "",
    query_term: PolicyQueryTerm | None = None,
) -> list[GovPolicyCandidate]:
    base_url = page_url or "https://www.gov.cn/"
    candidates: list[GovPolicyCandidate] = []
    for match in re.finditer(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", raw_html or "", flags=re.I | re.S):
        attrs = match.group("attrs") or ""
        href_match = re.search(r"href\s*=\s*['\"](?P<href>[^'\"]+)['\"]", attrs, flags=re.I)
        if not href_match:
            continue
        href = html.unescape(href_match.group("href")).strip()
        url = parse.urljoin(base_url, href)
        title = _clean_text(match.group("body"))
        if not _looks_like_policy_link(title, url):
            continue
        window = (raw_html or "")[match.end() : match.end() + 220]
        published_at = _extract_date(window) or _extract_date(match.group(0))
        scope = _infer_scope(url) or default_scope
        metadata = {
            "resultPageUrl": page_url,
            "searchKeyword": query_term.keyword if query_term else "",
            "matchedSegment": query_term.matched_segment if query_term else "",
            "policyDomain": query_term.policy_domain if query_term else "",
            "queryTerm": query_term.to_metadata() if query_term else {},
        }
        candidates.append(
            GovPolicyCandidate(
                title=title,
                url=url,
                published_at=published_at,
                source_scope=scope,
                policy_id=_policy_id_from_url(url),
                metadata=metadata,
            )
        )
    return _dedupe_candidates(candidates)


def parse_policy_detail_page(raw_html: str, page_url: str, *, candidate: GovPolicyCandidate | None = None) -> GovPolicyDetail:
    metadata = _meta_values(raw_html)
    clean_title = (
        metadata.get("article_title")
        or metadata.get("title")
        or metadata.get("og:title")
        or _first_tag_text(raw_html, "h1")
        or _html_title(raw_html)
        or (candidate.title if candidate else "")
        or "未命名政策"
    )
    content_html = _content_html(raw_html)
    content = _clean_text(content_html)
    url = page_url or (candidate.url if candidate else "")
    published_at = (
        _normalize_date(metadata.get("publishdate") or metadata.get("pubdate") or metadata.get("date"))
        or _extract_labeled_value(raw_html, ("发布日期", "发布时间"))
        or (candidate.published_at if candidate else "")
    )
    issuing_agency = (
        metadata.get("author")
        or _extract_labeled_value(raw_html, ("发文机关", "发布机构", "发布单位", "来源"))
        or ""
    )
    document_number = _extract_labeled_value(raw_html, ("文号", "发文字号"))
    scope = _infer_scope(url) or (candidate.source_scope if candidate else "")
    attachments = tuple(_extract_attachments(raw_html, base_url=url))
    policy_id = (
        metadata.get("contentid")
        or metadata.get("articleid")
        or (candidate.policy_id if candidate else "")
        or document_number
        or _policy_id_from_url(url)
        or _hash_text(f"{clean_title}:{url}")
    )
    raw_metadata = {
        **metadata,
        "sourceScope": scope,
        "detailUrl": url,
        "status": "fetched" if content else "metadata_limited",
    }
    return GovPolicyDetail(
        title=clean_title,
        url=url,
        content=content,
        published_at=published_at,
        policy_id=str(policy_id),
        issuing_agency=issuing_agency,
        document_number=document_number,
        source_scope=scope,
        attachments=attachments,
        raw_metadata=raw_metadata,
    )


def _normalize_policy_document(document: SourceDocument) -> SourceDocument:
    return SourceDocument(
        id=document.id,
        source_type="gov_policy",
        source_name=document.source_name or GovPolicyAdapter.source_name,
        title=document.title,
        content=document.content,
        url=document.url,
        published_at=document.published_at,
        authority_score=float(document.authority_score or 0.95),
        relevance_scope=document.relevance_scope or "industry",
        metadata=document.metadata,
    )


def _detail_to_document(
    detail: GovPolicyDetail,
    *,
    plan: PolicySearchPlan,
    query_term: PolicyQueryTerm | None,
    candidate: GovPolicyCandidate,
) -> SourceDocument:
    source_scope = detail.source_scope or candidate.source_scope or "unknown"
    policy_id = detail.policy_id or candidate.policy_id or _hash_text(detail.url or detail.title)
    matched_keywords = _dedupe([detail.title, *(plan.keywords if query_term is None else [query_term.keyword])])
    matched_segments = _dedupe(
        [
            query_term.matched_segment if query_term else "",
            str(candidate.metadata.get("matchedSegment") or ""),
        ]
    )
    metadata = {
        **candidate.metadata,
        **detail.raw_metadata,
        "policyId": policy_id,
        "sourceDocumentId": policy_id,
        "sourceScope": source_scope,
        "issuingAgency": detail.issuing_agency,
        "documentNumber": detail.document_number,
        "matchedKeywords": matched_keywords,
        "relevanceSegments": matched_segments,
        "matchedSegments": matched_segments,
        "matchedPolicyDomains": _dedupe(
            [
                query_term.policy_domain if query_term else "",
                str(candidate.metadata.get("policyDomain") or ""),
            ]
        ),
        "searchKeyword": query_term.keyword if query_term else str(candidate.metadata.get("searchKeyword") or ""),
        "attachments": list(detail.attachments),
        "attachmentFullTextParsed": False,
        "policySearchPlan": plan.to_metadata(),
        "status": "fetched" if detail.content.strip() else "metadata_limited",
    }
    return SourceDocument(
        id=f"policy:{policy_id}",
        source_type="gov_policy",
        source_name=GovPolicyAdapter.source_name,
        title=detail.title or candidate.title,
        content=detail.content,
        url=detail.url or candidate.url,
        published_at=detail.published_at or candidate.published_at,
        authority_score=0.96 if source_scope == "state_council" else 0.92,
        relevance_scope="industry",
        metadata=metadata,
    )


def _candidate_query_term(candidate: GovPolicyCandidate, plan: PolicySearchPlan) -> PolicyQueryTerm | None:
    keyword = str(candidate.metadata.get("searchKeyword") or "")
    for term in plan.query_terms:
        if term.keyword == keyword:
            return term
    return plan.query_terms[0] if plan.query_terms else None


def _dedupe_candidates(candidates: list[GovPolicyCandidate]) -> list[GovPolicyCandidate]:
    seen: set[str] = set()
    result: list[GovPolicyCandidate] = []
    for candidate in candidates:
        key = candidate.policy_id or candidate.document_number or candidate.url or candidate.title
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _looks_like_policy_link(title: str, url: str) -> bool:
    if not title or len(title) < 4:
        return False
    lowered = url.lower()
    if "gov.cn" not in lowered and not lowered.startswith("https://www.gov.cn/"):
        return False
    if "/zhengce/" not in lowered and "/xinwen/" not in lowered:
        return False
    if any(skip in title for skip in ("首页", "登录", "邮箱", "客户端", "微博", "微信", "无障碍")):
        return False
    return True


def _content_html(raw_html: str) -> str:
    patterns = [
        r"<div[^>]+id=['\"]UCAP-CONTENT['\"][^>]*>(?P<body>.*?)</div>\s*</div>",
        r"<div[^>]+class=['\"][^'\"]*pages_content[^'\"]*['\"][^>]*>(?P<body>.*?)</div>",
        r"<div[^>]+class=['\"][^'\"]*article[^'\"]*['\"][^>]*>(?P<body>.*?)</div>",
        r"<article[^>]*>(?P<body>.*?)</article>",
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
        ext_match = re.search(r"\.(pdf|docx?|xlsx?|zip)(?:$|[?#])", href, flags=re.I)
        if not ext_match:
            continue
        title = _clean_text(match.group("body")) or parse.unquote(href.rsplit("/", 1)[-1])
        attachments.append(
            {
                "title": title,
                "url": parse.urljoin(base_url, href),
                "fileType": ext_match.group(1).lower(),
            }
        )
    return attachments


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
    return re.sub(r"[_\-].*?(中国政府网|国务院).*", "", title).strip()


def _extract_labeled_value(raw_html: str, labels: tuple[str, ...]) -> str:
    text = _clean_text(raw_html)
    for label in labels:
        pattern = rf"{re.escape(label)}\s*[:：]\s*(?P<value>.{{1,80}}?)(?:\s{{2,}}|发布日期|发布时间|发文机关|发布机构|文号|$)"
        match = re.search(pattern, text)
        if match:
            value = match.group("value").strip()
            return _normalize_date(value) if "日期" in label or "时间" in label else value
    return ""


def _extract_date(value: str) -> str:
    match = re.search(r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})", html.unescape(value or ""))
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _normalize_date(value: str) -> str:
    return _extract_date(value) or str(value or "").strip()


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


def _policy_id_from_url(url: str) -> str:
    parsed = parse.urlparse(url or "")
    path = parsed.path.rsplit("/", 1)[-1]
    match = re.search(r"([A-Za-z0-9_-]{4,})(?:\.html?|\.shtml)?$", path)
    if match:
        return match.group(1)
    return _hash_text(url) if url else ""


def _infer_scope(url: str) -> str:
    lowered = (url or "").lower()
    if "/gwywj/" in lowered:
        return "state_council"
    if "/bmwj/" in lowered or "/zhengceku/" in lowered and "department" in lowered:
        return "department"
    return ""


def _scope_tab(scope: str) -> str:
    if scope == "state_council":
        return "gwywj"
    if scope == "department":
        return "bmwj"
    return "all"


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


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
