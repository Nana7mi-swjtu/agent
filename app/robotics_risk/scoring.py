from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from hashlib import sha1
from typing import Iterable

from .schemas import EnterpriseProfile, InsightEvent, InsightSignal, SourceDocument

_EVENT_STRENGTH = {
    "major_contract": 0.92,
    "winning_bid": 0.88,
    "policy_support": 0.84,
    "equipment_upgrade": 0.82,
    "government_procurement": 0.84,
    "standardization": 0.78,
    "subsidy_tax_support": 0.82,
    "ai_plus_policy": 0.84,
    "industrial_upgrading": 0.8,
    "data_security": 0.82,
    "quality_supervision": 0.8,
    "capacity_expansion": 0.78,
    "new_product": 0.76,
    "earnings_growth": 0.82,
    "earnings_decline": 0.86,
    "litigation": 0.84,
    "regulatory_constraint": 0.8,
    "shareholder_reduction": 0.72,
    "impairment": 0.76,
}

_SCOPE_RELEVANCE = {
    "enterprise": 0.95,
    "market_demand": 0.78,
    "industry": 0.7,
}


def build_signals(
    *,
    events: list[InsightEvent],
    sources: list[SourceDocument],
    profile: EnterpriseProfile,
) -> tuple[list[InsightSignal], list[InsightSignal]]:
    source_map = {item.id: item for item in sources}
    grouped: dict[tuple[str, str], list[InsightEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.direction, event.dimension)].append(event)

    opportunities: list[InsightSignal] = []
    risks: list[InsightSignal] = []
    for (direction, dimension), items in grouped.items():
        signal = _build_signal(direction=direction, dimension=dimension, events=items, source_map=source_map, profile=profile)
        if direction == "risk":
            risks.append(signal)
        elif direction == "opportunity":
            opportunities.append(signal)

    opportunities.sort(key=lambda item: item.impact_score, reverse=True)
    risks.sort(key=lambda item: item.impact_score, reverse=True)
    return opportunities[:5], risks[:5]


def _build_signal(
    *,
    direction: str,
    dimension: str,
    events: list[InsightEvent],
    source_map: dict[str, SourceDocument],
    profile: EnterpriseProfile,
) -> InsightSignal:
    source_ids = _dedupe([event.source_document_id for event in events])
    source_docs = [source_map[source_id] for source_id in source_ids if source_id in source_map]
    score_components = [_event_score(event, source_map.get(event.source_document_id), profile) for event in events]
    impact = int(round(max(score_components or [0.5]) * 100))
    direct = any(item.relevance_scope == "enterprise" for item in source_docs)
    industry = any(item.relevance_scope == "industry" for item in source_docs)
    market = any(item.relevance_scope == "market_demand" for item in source_docs)
    reinforced = direct and (industry or market)
    confidence = min(0.98, max(0.35, (impact / 100) + (0.08 if reinforced else 0.0)))
    label = "机会" if direction == "opportunity" else "风险"
    digest = sha1("|".join([direction, dimension, *source_ids]).encode("utf-8")).hexdigest()[:8]
    return InsightSignal(
        id=f"sig_{direction}_{digest}",
        type=direction,
        category=dimension,
        title=f"{profile.name}{dimension}{label}信号",
        impact_score=impact,
        confidence=round(confidence, 2),
        reasoning=_reasoning(
            direction=direction,
            dimension=dimension,
            direct=direct,
            industry=industry,
            market=market,
            source_docs=source_docs,
            profile=profile,
        ),
        event_ids=[event.id for event in events],
        source_ids=source_ids,
    )


def _event_score(event: InsightEvent, source: SourceDocument | None, profile: EnterpriseProfile) -> float:
    authority = float(source.authority_score if source else 0.6)
    relevance = _SCOPE_RELEVANCE.get(str(source.relevance_scope if source else "industry"), 0.65)
    strength = _EVENT_STRENGTH.get(event.event_type, 0.68)
    freshness = _freshness_score(event.published_at)
    profile_match = 0.08 if source and _matches_profile(source, profile) else 0.0
    return min(1.0, authority * 0.25 + relevance * 0.25 + strength * 0.3 + freshness * 0.2 + profile_match)


def _freshness_score(value: str) -> float:
    if not value:
        return 0.6
    try:
        parsed = datetime.fromisoformat(str(value).replace("/", "-")[:10]).date()
    except ValueError:
        return 0.6
    age_days = max(0, (date.today() - parsed).days)
    if age_days <= 30:
        return 1.0
    if age_days <= 90:
        return 0.82
    if age_days <= 180:
        return 0.68
    return 0.5


def _matches_profile(source: SourceDocument, profile: EnterpriseProfile) -> bool:
    text = f"{source.title}\n{source.content}"
    return any(keyword and keyword in text for keyword in profile.keywords)


def _reasoning(
    *,
    direction: str,
    dimension: str,
    direct: bool,
    industry: bool,
    market: bool,
    source_docs: list[SourceDocument],
    profile: EnterpriseProfile,
) -> str:
    basis: list[str] = []
    if direct:
        basis.append("企业直接公告")
    if industry:
        basis.append("机器人行业政策/环境证据")
    if market:
        basis.append("招中标/采购需求证据")
    if not basis:
        basis.append("公开来源证据")
    verb = "利好" if direction == "opportunity" else "可能冲击"
    matched_terms = _matched_terms(source_docs, profile)
    inference = "直接企业证据与行业政策/市场证据共同支持" if direct and (industry or market) else (
        "直接企业证据支持" if direct else "行业层面证据推断"
    )
    match_text = f"，匹配画像关键词：{', '.join(matched_terms[:5])}" if matched_terms else ""
    industry_limit = "；该信号尚需企业后续公告或经营数据验证" if industry and not direct else ""
    return (
        f"该判断基于{'、'.join(basis)}，证据层级为{inference}，结合{profile.name}的"
        f"{', '.join(profile.segments)}画像{match_text}，{dimension}因素{verb}企业后续经营表现{industry_limit}。"
    )


def _matched_terms(source_docs: list[SourceDocument], profile: EnterpriseProfile) -> list[str]:
    terms = [*profile.segments, *profile.keywords]
    seen: set[str] = set()
    result: list[str] = []
    text = "\n".join(f"{source.title}\n{source.content}" for source in source_docs)
    for term in terms:
        clean = str(term or "").strip()
        if clean and clean not in seen and clean in text:
            seen.add(clean)
            result.append(clean)
    for source in source_docs:
        metadata = source.metadata or {}
        for value in metadata.get("matchedSegments") or metadata.get("relevanceSegments") or []:
            clean = str(value or "").strip()
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)
    return result


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
