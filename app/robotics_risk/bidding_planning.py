from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .schemas import EnterpriseProfile, RoboticsInsightRequest

DEFAULT_BIDDING_NOTICE_CATEGORIES: tuple[str, ...] = (
    "tender_announcement",
    "prequalification_announcement",
    "winning_candidate",
    "winning_result",
    "change_notice",
)

BIDDING_CATEGORY_LABELS: dict[str, str] = {
    "tender_announcement": "招标公告",
    "prequalification_announcement": "资格预审公告",
    "winning_candidate": "中标候选人公示",
    "winning_result": "中标结果公告",
    "change_notice": "变更公告",
}

GENERAL_BIDDING_TERMS: tuple[str, ...] = (
    "机器人 采购",
    "机器人 招标",
    "智能机器人 项目",
)

SCENARIO_TERMS: tuple[str, ...] = (
    "养老",
    "医疗",
    "教育",
    "物流",
    "仓储",
    "清洁",
    "巡检",
    "智能制造",
)

SUPPLY_CHAIN_TERMS: tuple[str, ...] = (
    "减速器",
    "伺服",
    "控制器",
    "传感器",
    "机器视觉",
    "自动化产线",
)


@dataclass(frozen=True)
class BiddingQueryTerm:
    keyword: str
    source: str
    matched_segment: str = ""
    matched_scenario: str = ""
    chain_position: str = ""
    priority: int = 50

    def to_metadata(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "source": self.source,
            "matchedSegment": self.matched_segment,
            "matchedScenario": self.matched_scenario,
            "chainPosition": self.chain_position,
            "priority": self.priority,
        }


@dataclass(frozen=True)
class BiddingSearchPlan:
    query_terms: tuple[BiddingQueryTerm, ...]
    notice_categories: tuple[str, ...] = DEFAULT_BIDDING_NOTICE_CATEGORIES
    start_date: str = ""
    end_date: str = ""
    region_hints: tuple[str, ...] = field(default_factory=tuple)
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
            "noticeCategories": list(self.notice_categories),
            "noticeCategoryLabels": [BIDDING_CATEGORY_LABELS.get(item, item) for item in self.notice_categories],
            "startDate": self.start_date,
            "endDate": self.end_date,
            "regionHints": list(self.region_hints),
            "maxPages": self.max_pages,
            "detailFetchLimit": self.detail_fetch_limit,
            "limitations": list(self.limitations),
        }


def build_bidding_search_plan(
    *,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
    resolution_metadata: dict[str, Any] | None = None,
    max_queries: int = 10,
    max_pages: int = 1,
    detail_fetch_limit: int = 8,
    notice_categories: tuple[str, ...] | None = None,
) -> BiddingSearchPlan:
    limitations: list[str] = []
    start_date, end_date, date_limitations = _date_window(request.time_range)
    limitations.extend(date_limitations)

    categories = tuple(_clean_values(list(notice_categories or DEFAULT_BIDDING_NOTICE_CATEGORIES)))
    if not categories:
        categories = DEFAULT_BIDDING_NOTICE_CATEGORIES

    terms: list[BiddingQueryTerm] = []
    enterprise_terms = _enterprise_terms(request=request, profile=profile, resolution_metadata=resolution_metadata)
    for enterprise in enterprise_terms:
        terms.append(BiddingQueryTerm(keyword=f"{enterprise} 中标", source="enterprise", priority=115))
        terms.append(BiddingQueryTerm(keyword=f"{enterprise} 投标", source="enterprise", priority=106))

    for keyword in GENERAL_BIDDING_TERMS:
        terms.append(BiddingQueryTerm(keyword=keyword, source="general", priority=82))

    segments = [item for item in _clean_values(profile.segments) if item != "机器人行业"]
    if not segments:
        limitations.append("招投标搜索计划未识别到确定机器人细分赛道，已使用通用机器人采购关键词。")
    for segment in segments[:4]:
        terms.append(BiddingQueryTerm(keyword=f"{segment} 采购", source="segment", matched_segment=segment, priority=100))
        terms.append(BiddingQueryTerm(keyword=f"{segment} 招标", source="segment", matched_segment=segment, priority=98))
        terms.append(BiddingQueryTerm(keyword=f"{segment} 中标", source="segment", matched_segment=segment, priority=94))

    chain_positions = _clean_values(profile.chain_positions)
    for chain in chain_positions[:3]:
        if chain and chain not in {"待验证", "整机", "应用"}:
            terms.append(BiddingQueryTerm(keyword=f"{chain} 机器人 招标", source="chain_position", chain_position=chain, priority=86))

    context = " ".join([request.context, " ".join(profile.keywords), " ".join(profile.segments)])
    for scenario in SCENARIO_TERMS:
        if scenario in context:
            terms.append(BiddingQueryTerm(keyword=f"{scenario} 机器人 采购", source="scenario", matched_scenario=scenario, priority=92))
    for supply_term in SUPPLY_CHAIN_TERMS:
        if supply_term in context:
            terms.append(BiddingQueryTerm(keyword=f"{supply_term} 采购", source="supply_chain", chain_position=supply_term, priority=84))

    for optional in _optional_terms(resolution_metadata):
        terms.append(BiddingQueryTerm(keyword=f"{optional} 机器人 中标", source="optional_peer", priority=72))

    ordered = sorted(_dedupe_query_terms(terms), key=lambda item: (-item.priority, item.keyword))
    if len(ordered) > max_queries:
        limitations.append(f"招投标搜索计划生成 {len(ordered)} 个候选关键词，已截断为 {max_queries} 个。")

    region_hints = tuple(_extract_regions(request.context))
    return BiddingSearchPlan(
        query_terms=tuple(ordered[: max(1, int(max_queries))]),
        notice_categories=categories,
        start_date=start_date,
        end_date=end_date,
        region_hints=region_hints,
        max_pages=max(1, int(max_pages)),
        detail_fetch_limit=max(1, int(detail_fetch_limit)),
        limitations=tuple(_dedupe_text(limitations)),
    )


def _enterprise_terms(
    *,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
    resolution_metadata: dict[str, Any] | None,
) -> list[str]:
    metadata = dict(resolution_metadata or {})
    aliases: list[str] = []
    raw_aliases = metadata.get("aliases") or metadata.get("alias")
    if isinstance(raw_aliases, list):
        aliases = [str(item) for item in raw_aliases]
    return _dedupe_text(
        [
            request.enterprise_name,
            profile.name,
            metadata.get("securityName", ""),
            metadata.get("companyName", ""),
            *aliases,
        ]
    )


def _optional_terms(metadata: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    for key in ("competitors", "suppliers", "customers"):
        raw = (metadata or {}).get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
    return _dedupe_text(values)


def _date_window(time_range: str) -> tuple[str, str, list[str]]:
    now = datetime.utcnow().date()
    raw = str(time_range or "").strip()
    match = re.search(r"近\s*(\d+)\s*天", raw)
    if match:
        days = max(1, int(match.group(1)))
        return (now - timedelta(days=days)).isoformat(), now.isoformat(), []
    if not raw:
        return "", "", []
    return "", "", [f"招投标搜索计划暂未能将时间范围“{raw}”转换为平台日期筛选，已仅记录该范围。"]


def _extract_regions(text: str) -> list[str]:
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
    return [region for region in regions if region in text]


def _dedupe_query_terms(terms: list[BiddingQueryTerm]) -> list[BiddingQueryTerm]:
    seen: dict[str, BiddingQueryTerm] = {}
    for term in terms:
        clean = " ".join(str(term.keyword or "").split())
        if not clean:
            continue
        normalized = BiddingQueryTerm(
            keyword=clean,
            source=term.source,
            matched_segment=term.matched_segment,
            matched_scenario=term.matched_scenario,
            chain_position=term.chain_position,
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
