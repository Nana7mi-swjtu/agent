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
    confidence = min(0.98, max(0.35, (impact / 100) + (0.08 if direct and (industry or market) else 0.0)))
    label = "机会" if direction == "opportunity" else "风险"
    digest = sha1("|".join([direction, dimension, *source_ids]).encode("utf-8")).hexdigest()[:8]
    return InsightSignal(
        id=f"sig_{direction}_{digest}",
        type=direction,
        category=dimension,
        title=f"{profile.name}{dimension}{label}信号",
        impact_score=impact,
        confidence=round(confidence, 2),
        reasoning=_reasoning(direction=direction, dimension=dimension, direct=direct, industry=industry, market=market, profile=profile),
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
    return f"该判断基于{'、'.join(basis)}，结合{profile.name}的{', '.join(profile.segments)}画像，{dimension}因素{verb}企业后续经营表现。"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
