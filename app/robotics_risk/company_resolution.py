from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.models import RoboticsListedCompanyProfile

from .repository import RoboticsEvidenceRepository


@dataclass(frozen=True)
class ListedCompanyProfileData:
    stock_code: str = ""
    exchange: str = ""
    market: str = ""
    security_name: str = ""
    company_name: str = ""
    aliases: list[str] = field(default_factory=list)
    industry_segments: list[str] = field(default_factory=list)
    robotics_keywords: list[str] = field(default_factory=list)
    cninfo_column: str = ""
    cninfo_org_id: str = ""
    is_supported: bool = True
    unsupported_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompanyResolutionResult:
    query: str
    profile: ListedCompanyProfileData | None = None
    match_type: str = "unresolved"
    confidence: float = 0.0
    candidate_count: int = 0
    limitations: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.profile is not None and self.match_type not in {"unresolved", "ambiguous"}

    @property
    def supported(self) -> bool:
        return bool(self.profile and self.profile.is_supported)

    @property
    def stock_code(self) -> str:
        return self.profile.stock_code if self.profile else ""

    def to_metadata(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": self.query,
            "matchType": self.match_type,
            "confidence": self.confidence,
            "candidateCount": self.candidate_count,
            "limitations": list(self.limitations),
        }
        if self.profile is not None:
            payload.update(
                {
                    "stockCode": self.profile.stock_code,
                    "exchange": self.profile.exchange,
                    "market": self.profile.market,
                    "securityName": self.profile.security_name,
                    "companyName": self.profile.company_name,
                    "cninfoColumn": self.profile.cninfo_column,
                    "cninfoOrgId": self.profile.cninfo_org_id,
                    "isSupported": self.profile.is_supported,
                    "unsupportedReason": self.profile.unsupported_reason,
                }
            )
        return payload


class ListedCompanyResolver:
    def __init__(self, repository: RoboticsEvidenceRepository, *, fuzzy_threshold: float = 0.78) -> None:
        self.repository = repository
        self.fuzzy_threshold = float(fuzzy_threshold)

    def resolve(self, enterprise_name: str, *, stock_code: str = "") -> CompanyResolutionResult:
        query = str(enterprise_name or "").strip()
        explicit_code = _normalize_stock_code(stock_code) or _normalize_stock_code(query)
        profiles = [profile_to_data(item) for item in self.repository.list_listed_company_profiles()]

        if explicit_code:
            matches = [item for item in profiles if item.stock_code == explicit_code]
            if matches:
                return _result(query=query, profile=matches[0], match_type="stock_code", confidence=1.0)

        normalized_query = _normalize_name(query)
        if not normalized_query:
            return CompanyResolutionResult(query=query, limitations=["未提供可用于上市公司本地解析的企业名称。"])

        exact_matches: list[tuple[ListedCompanyProfileData, str]] = []
        for profile in profiles:
            names = [
                ("company_name", profile.company_name),
                ("security_name", profile.security_name),
                *[("alias", alias) for alias in profile.aliases],
            ]
            for match_type, name in names:
                if _normalize_name(name) == normalized_query:
                    exact_matches.append((profile, match_type))
                    break
        if len(exact_matches) == 1:
            profile, match_type = exact_matches[0]
            return _result(query=query, profile=profile, match_type=match_type, confidence=0.98)
        if len(exact_matches) > 1:
            return CompanyResolutionResult(
                query=query,
                match_type="ambiguous",
                confidence=0.0,
                candidate_count=len(exact_matches),
                limitations=[f"企业名称本地解析存在 {len(exact_matches)} 个精确候选，已跳过股票代码自动选择。"],
            )

        scored: list[tuple[float, ListedCompanyProfileData]] = []
        for profile in profiles:
            best = max((_similarity(normalized_query, _normalize_name(name)) for name in _all_names(profile)), default=0.0)
            if best >= self.fuzzy_threshold:
                scored.append((best, profile))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return CompanyResolutionResult(
                query=query,
                match_type="unresolved",
                confidence=0.0,
                limitations=["未在本地机器人上市公司映射表中找到可靠匹配，巨潮资讯网将无法使用股票代码优先检索。"],
            )

        top_score, top_profile = scored[0]
        if len(scored) > 1 and top_score - scored[1][0] < 0.08:
            return CompanyResolutionResult(
                query=query,
                match_type="ambiguous",
                confidence=round(top_score, 3),
                candidate_count=len(scored),
                limitations=[f"企业名称本地模糊解析存在 {len(scored)} 个相近候选，已跳过股票代码自动选择。"],
            )
        return _result(query=query, profile=top_profile, match_type="fuzzy", confidence=round(top_score, 3))


def profile_to_data(row: RoboticsListedCompanyProfile) -> ListedCompanyProfileData:
    return ListedCompanyProfileData(
        stock_code=str(row.stock_code or ""),
        exchange=str(row.exchange or ""),
        market=str(row.market or ""),
        security_name=str(row.security_name or ""),
        company_name=str(row.company_name or ""),
        aliases=_json_list(row.aliases_json, "aliases"),
        industry_segments=_json_list(row.industry_segments_json, "segments"),
        robotics_keywords=_json_list(row.robotics_keywords_json, "keywords"),
        cninfo_column=str(row.cninfo_column or ""),
        cninfo_org_id=str(row.cninfo_org_id or ""),
        is_supported=bool(row.is_supported),
        unsupported_reason=str(row.unsupported_reason or ""),
        metadata=dict(row.metadata_json or {}),
    )


def _result(
    *,
    query: str,
    profile: ListedCompanyProfileData,
    match_type: str,
    confidence: float,
) -> CompanyResolutionResult:
    limitations: list[str] = []
    if not profile.is_supported:
        limitations.append(profile.unsupported_reason or "该上市公司不属于本阶段支持的 CNINFO A 股公告查询范围。")
    return CompanyResolutionResult(
        query=query,
        profile=profile,
        match_type=match_type,
        confidence=confidence,
        candidate_count=1,
        limitations=limitations,
    )


def _all_names(profile: ListedCompanyProfileData) -> list[str]:
    return [profile.company_name, profile.security_name, *profile.aliases]


def _json_list(value: Any, key: str) -> list[str]:
    if isinstance(value, dict):
        values = value.get(key) or []
    else:
        values = []
    return [str(item).strip() for item in values if str(item or "").strip()]


def _normalize_name(value: str | None) -> str:
    text = str(value or "").lower().strip()
    text = re.sub(r"[()\[\]（）【】\s·,，.。:：;；_\-]+", "", text)
    for suffix in ("股份有限公司", "有限责任公司", "有限公司", "集团股份", "集团"):
        text = text.replace(suffix, "")
    return text


def _normalize_stock_code(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    match = re.search(r"(\d{5,6})", raw)
    return match.group(1) if match else ""


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left in right or right in left:
        return min(0.95, min(len(left), len(right)) / max(len(left), len(right), 1))
    return SequenceMatcher(None, left, right).ratio()
