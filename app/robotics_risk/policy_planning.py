from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .schemas import EnterpriseProfile, RoboticsInsightRequest

DEFAULT_POLICY_SOURCE_SCOPES: tuple[str, ...] = ("state_council", "department")

POLICY_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "标准规范": ("标准", "规范", "质量监督", "产品安全"),
    "政府采购": ("政府采购", "采购", "招标"),
    "设备更新": ("设备更新", "智能制造", "数字化改造"),
    "场景开放": ("场景", "应用场景", "场景开放"),
    "财政税收": ("补贴", "税收", "专项资金"),
    "人工智能+": ("人工智能", "人工智能+", "具身智能"),
    "产业升级": ("产业升级", "先进制造", "新质生产力"),
    "数据安全": ("数据安全", "网络安全", "隐私保护"),
}

SCENARIO_TERMS: tuple[str, ...] = (
    "养老",
    "医疗",
    "教育",
    "物流",
    "仓储",
    "清洁",
    "智能制造",
)

GENERAL_POLICY_TERMS: tuple[str, ...] = (
    "机器人",
    "人工智能 机器人",
    "智能制造 机器人",
)


@dataclass(frozen=True)
class PolicyQueryTerm:
    keyword: str
    source: str
    matched_segment: str = ""
    policy_domain: str = ""
    priority: int = 50

    def to_metadata(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "source": self.source,
            "matchedSegment": self.matched_segment,
            "policyDomain": self.policy_domain,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class PolicySearchPlan:
    query_terms: tuple[PolicyQueryTerm, ...]
    source_scopes: tuple[str, ...] = DEFAULT_POLICY_SOURCE_SCOPES
    start_date: str = ""
    end_date: str = ""
    max_pages: int = 1
    detail_fetch_limit: int = 8
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def keywords(self) -> list[str]:
        return [term.keyword for term in self.query_terms]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "keywords": self.keywords,
            "queryTerms": [term.to_metadata() for term in self.query_terms],
            "sourceScopes": list(self.source_scopes),
            "startDate": self.start_date,
            "endDate": self.end_date,
            "maxPages": self.max_pages,
            "detailFetchLimit": self.detail_fetch_limit,
            "limitations": list(self.limitations),
        }


def build_policy_search_plan(
    *,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
    max_queries: int = 8,
    max_pages: int = 1,
    detail_fetch_limit: int = 8,
    source_scopes: tuple[str, ...] | None = None,
) -> PolicySearchPlan:
    limitations: list[str] = []
    scopes = tuple(_clean_values(list(source_scopes or DEFAULT_POLICY_SOURCE_SCOPES))) or DEFAULT_POLICY_SOURCE_SCOPES
    start_date, end_date, date_limitations = _date_window(request.time_range)
    limitations.extend(date_limitations)

    segments = [item for item in _clean_values(profile.segments) if item != "机器人行业"]
    keywords = _clean_values([*profile.keywords, *profile.segments])
    terms: list[PolicyQueryTerm] = []

    for keyword in GENERAL_POLICY_TERMS:
        terms.append(PolicyQueryTerm(keyword=keyword, source="general", priority=90))

    if not segments:
        limitations.append("政策搜索计划未识别到确定机器人细分赛道，已使用通用机器人政策关键词。")
    for segment in segments[:4]:
        terms.append(PolicyQueryTerm(keyword=f"{segment} 政策", source="segment", matched_segment=segment, priority=100))
        terms.append(PolicyQueryTerm(keyword=f"{segment} 应用场景", source="segment", matched_segment=segment, priority=88))

    for domain, domain_keywords in POLICY_DOMAIN_TERMS.items():
        base = _first_profile_keyword(keywords, domain_keywords)
        keyword = f"{base} {domain_keywords[0]}" if base else f"机器人 {domain_keywords[0]}"
        terms.append(PolicyQueryTerm(keyword=keyword, source="policy_domain", policy_domain=domain, priority=78))

    for scenario in SCENARIO_TERMS:
        if scenario in keywords or scenario in request.context:
            terms.append(PolicyQueryTerm(keyword=f"机器人 {scenario}", source="scenario", policy_domain="场景开放", priority=82))

    ordered = sorted(_dedupe_query_terms(terms), key=lambda item: (-item.priority, item.keyword))
    if len(ordered) > max_queries:
        limitations.append(f"政策搜索计划生成 {len(ordered)} 个候选关键词，已截断为 {max_queries} 个。")
    bounded = tuple(ordered[: max(1, int(max_queries))])
    return PolicySearchPlan(
        query_terms=bounded,
        source_scopes=scopes,
        start_date=start_date,
        end_date=end_date,
        max_pages=max(1, int(max_pages)),
        detail_fetch_limit=max(1, int(detail_fetch_limit)),
        limitations=tuple(_dedupe_text(limitations)),
    )


def _date_window(time_range: str) -> tuple[str, str, list[str]]:
    now = datetime.utcnow().date()
    raw = str(time_range or "").strip()
    match = re.search(r"近\s*(\d+)\s*天", raw)
    if match:
        days = max(1, int(match.group(1)))
        return (now - timedelta(days=days)).isoformat(), now.isoformat(), []
    if not raw:
        return "", "", []
    return "", "", [f"政策搜索计划暂未能将时间范围“{raw}”转换为 gov.cn 日期筛选，已仅记录该范围。"]


def _first_profile_keyword(profile_keywords: list[str], domain_keywords: tuple[str, ...]) -> str:
    for keyword in profile_keywords:
        if any(item in keyword or keyword in item for item in domain_keywords):
            return keyword
    for keyword in profile_keywords:
        if keyword and keyword not in {"机器人", "机器人行业"}:
            return keyword
    return ""


def _dedupe_query_terms(terms: list[PolicyQueryTerm]) -> list[PolicyQueryTerm]:
    seen: dict[str, PolicyQueryTerm] = {}
    for term in terms:
        clean = " ".join(str(term.keyword or "").split())
        if not clean:
            continue
        normalized = PolicyQueryTerm(
            keyword=clean,
            source=term.source,
            matched_segment=term.matched_segment,
            policy_domain=term.policy_domain,
            priority=term.priority,
        )
        existing = seen.get(clean)
        if existing is None or normalized.priority > existing.priority:
            seen[clean] = normalized
    return list(seen.values())


def _clean_values(values: list[str]) -> list[str]:
    return _dedupe_text([str(value or "").strip() for value in values])


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
