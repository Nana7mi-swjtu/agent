from __future__ import annotations

from .schemas import EnterpriseProfile, RoboticsInsightRequest
from .taxonomy import GENERAL_ROBOTICS_KEYWORDS, KNOWN_ENTERPRISE_HINTS, ROBOTICS_TAXONOMY


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def build_enterprise_profile(request: RoboticsInsightRequest) -> EnterpriseProfile:
    enterprise_name = request.enterprise_name.strip()
    context = " ".join(
        [
            enterprise_name,
            request.stock_code,
            request.context,
        ]
    )
    matched_keywords: list[str] = []
    matched_segments: list[str] = []
    matched_positions: list[str] = []

    for name, hints in KNOWN_ENTERPRISE_HINTS.items():
        if name and name in enterprise_name:
            matched_keywords.extend(hints)

    for entry in ROBOTICS_TAXONOMY:
        if any(keyword.lower() in context.lower() for keyword in entry.keywords):
            matched_segments.append(entry.segment)
            matched_positions.append(entry.chain_position)
            matched_keywords.extend(entry.keywords)
        elif any(keyword in matched_keywords for keyword in entry.keywords):
            matched_segments.append(entry.segment)
            matched_positions.append(entry.chain_position)
            matched_keywords.extend(entry.keywords)

    limitations: list[str] = []
    if not request.stock_code.strip():
        limitations.append("未提供股票代码，上市公司公告检索将优先使用企业名称。")
    if not matched_segments:
        matched_segments = ["机器人行业"]
        matched_positions = ["待验证"]
        matched_keywords = list(GENERAL_ROBOTICS_KEYWORDS)
        limitations.append("未能确定企业在机器人产业链中的具体环节，已使用通用机器人行业画像。")

    return EnterpriseProfile(
        name=enterprise_name,
        stock_code=request.stock_code.strip(),
        segments=_dedupe(matched_segments),
        chain_positions=_dedupe(matched_positions),
        keywords=_dedupe([*matched_keywords, *GENERAL_ROBOTICS_KEYWORDS]),
        limitations=limitations,
    )
