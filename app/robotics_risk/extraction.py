from __future__ import annotations

import re

from .schemas import InsightEvent, SourceDocument

_POLICY_RULES: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    ("policy_support", ("支持", "鼓励", "推动", "促进", "补贴", "培育"), "opportunity", "政策支持", "政策支持带来行业扩张机会"),
    ("regulatory_constraint", ("监管", "规范", "准入", "标准", "安全要求", "合规"), "risk", "政策监管", "监管和标准要求可能提高合规成本"),
    ("equipment_upgrade", ("设备更新", "智能制造", "自动化", "数字化改造"), "opportunity", "设备更新", "设备更新政策可能提升机器人需求"),
    ("application_scenario", ("养老", "医疗", "教育", "仓储", "物流", "清洁"), "opportunity", "应用场景", "机器人应用场景扩展"),
)

_ANNOUNCEMENT_RULES: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    ("major_contract", ("重大合同", "签订合同", "中标", "订单"), "opportunity", "订单", "企业订单或合同带来收入机会"),
    ("capacity_expansion", ("扩产", "产能", "募投项目", "投资建设"), "opportunity", "产能", "产能扩张可能增强供给能力"),
    ("new_product", ("新品", "新产品", "发布", "研发", "技术突破"), "opportunity", "产品研发", "产品或研发进展增强竞争力"),
    ("earnings_growth", ("预增", "增长", "盈利增加", "业绩增长"), "opportunity", "经营表现", "业绩改善增强基本面"),
    ("earnings_decline", ("预亏", "下降", "亏损", "业绩下滑"), "risk", "经营表现", "业绩压力构成经营风险"),
    ("litigation", ("诉讼", "仲裁", "处罚", "问询函", "监管函"), "risk", "治理合规", "诉讼或监管事项构成合规风险"),
    ("shareholder_reduction", ("减持", "质押", "解除质押"), "risk", "资本市场", "股东变动可能影响市场预期"),
    ("impairment", ("减值", "存货跌价", "坏账"), "risk", "资产质量", "资产或存货减值可能影响利润"),
)

_BIDDING_RULES: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    ("procurement_demand", ("采购", "招标", "需求", "项目"), "opportunity", "市场需求", "机器人相关采购体现市场需求"),
    ("winning_bid", ("中标", "成交", "中标候选"), "opportunity", "订单机会", "中标或成交信息体现订单机会"),
    ("smart_manufacturing_project", ("智能制造", "自动化产线", "仓储", "物流", "清洁", "医疗", "养老", "教育"), "opportunity", "应用场景", "下游场景项目释放需求信号"),
)


def extract_events(documents: list[SourceDocument]) -> list[InsightEvent]:
    events: list[InsightEvent] = []
    for document in documents:
        rules = _rules_for_source(document.source_type)
        text = f"{document.title}\n{document.content}"
        for event_type, keywords, direction, dimension, summary in rules:
            if not any(keyword in text for keyword in keywords):
                continue
            events.append(
                InsightEvent(
                    id=f"evt_{len(events) + 1:03d}",
                    source_document_id=document.id,
                    source_type=document.source_type,
                    event_type=event_type,
                    title=document.title,
                    summary=summary,
                    direction=direction,
                    dimension=dimension,
                    evidence_sentence=_evidence_sentence(text, keywords),
                    published_at=document.published_at,
                )
            )
    return events


def _rules_for_source(source_type: str) -> tuple[tuple[str, tuple[str, ...], str, str, str], ...]:
    if source_type == "gov_policy":
        return _POLICY_RULES
    if source_type == "cninfo_announcement":
        return _ANNOUNCEMENT_RULES
    if source_type == "bidding_procurement":
        return _BIDDING_RULES
    return _POLICY_RULES + _ANNOUNCEMENT_RULES + _BIDDING_RULES


def _evidence_sentence(text: str, keywords: tuple[str, ...]) -> str:
    sentences = [item.strip() for item in re.split(r"[。！？!?\n]", str(text or "")) if item.strip()]
    for sentence in sentences:
        if any(keyword in sentence for keyword in keywords):
            return sentence[:240]
    return (sentences[0] if sentences else str(text or "").strip())[:240]
