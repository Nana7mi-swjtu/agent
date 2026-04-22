from __future__ import annotations

import re

from .schemas import InsightEvent, SourceDocument

_POLICY_RULES: tuple[tuple[str, tuple[str, ...], str, str, str], ...] = (
    ("policy_support", ("支持", "鼓励", "推动", "促进", "补贴", "培育"), "opportunity", "政策支持", "政策支持带来行业扩张机会"),
    ("regulatory_constraint", ("监管", "规范", "准入", "合规"), "risk", "政策监管", "监管和准入要求可能提高合规成本"),
    ("standardization", ("标准", "标准化", "规范条件", "认证", "检测"), "risk", "标准合规", "标准化和认证要求可能提高产品与经营门槛"),
    ("government_procurement", ("政府采购", "采购需求", "首台套", "招标采购"), "opportunity", "订单", "政府采购政策可能释放机器人相关订单机会"),
    ("equipment_upgrade", ("设备更新", "智能制造", "自动化", "数字化改造"), "opportunity", "设备更新", "设备更新政策可能提升机器人需求"),
    ("application_scenario", ("养老", "医疗", "教育", "仓储", "物流", "清洁", "场景开放", "应用场景"), "opportunity", "应用场景", "机器人应用场景扩展"),
    ("subsidy_tax_support", ("补助", "补贴", "税收优惠", "专项资金", "财政支持"), "opportunity", "政策支持", "财政税收政策可能改善机器人企业投入回报"),
    ("ai_plus_policy", ("人工智能+", "人工智能", "具身智能", "智能机器人"), "opportunity", "产品研发", "人工智能相关政策可能强化机器人产品和研发机会"),
    ("industrial_upgrading", ("产业升级", "新质生产力", "先进制造", "高端装备"), "opportunity", "产业升级", "产业升级政策可能增强机器人产业需求"),
    ("data_security", ("数据安全", "网络安全", "个人信息", "隐私保护"), "risk", "数据合规", "数据安全要求可能提高机器人产品合规要求"),
    ("quality_supervision", ("质量监督", "产品质量", "安全生产", "缺陷召回"), "risk", "产品质量", "产品质量和安全监管可能提高经营风险"),
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
    ("tender_opportunity", ("招标公告", "公开招标", "采购公告", "资格预审"), "opportunity", "投标机会", "招标或采购公告体现潜在投标机会"),
    ("winning_bid", ("中标", "成交", "中标候选"), "opportunity", "订单机会", "中标或成交信息体现订单机会"),
    ("candidate_award", ("中标候选人", "第一中标候选人", "成交候选"), "opportunity", "订单机会", "中标候选信息体现订单转化机会"),
    ("smart_manufacturing_project", ("智能制造", "自动化产线", "仓储", "物流", "清洁", "医疗", "养老", "教育"), "opportunity", "应用场景", "下游场景项目释放需求信号"),
    ("project_change", ("变更公告", "澄清公告", "更正公告", "延期", "暂停"), "risk", "项目不确定性", "项目变更或延期可能影响采购落地节奏"),
    ("project_cancellation", ("终止公告", "废标", "流标", "取消采购", "采购失败"), "risk", "项目不确定性", "项目取消、废标或流标体现落地不确定性"),
    ("amount_signal", ("中标金额", "成交金额", "预算金额", "合同金额", "万元"), "opportunity", "订单规模", "金额信息体现潜在订单或市场规模"),
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
        if document.source_type == "bidding_procurement":
            events.extend(_metadata_bidding_events(document, start_index=len(events)))
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


def _metadata_bidding_events(document: SourceDocument, *, start_index: int) -> list[InsightEvent]:
    metadata = document.metadata or {}
    events: list[InsightEvent] = []
    direct_role = str(metadata.get("directMatchRole") or "").strip()
    notice_type = str(metadata.get("noticeType") or "").strip()
    amount = str(metadata.get("amount") or "").strip()
    if document.relevance_scope == "enterprise" and direct_role in {"winner", "candidate"}:
        events.append(
            InsightEvent(
                id=f"evt_{start_index + len(events) + 1:03d}",
                source_document_id=document.id,
                source_type=document.source_type,
                event_type="direct_enterprise_award",
                title=document.title,
                summary="目标企业在招投标公告中被直接列为中标人或候选人",
                direction="opportunity",
                dimension="订单机会",
                evidence_sentence=_bidding_metadata_sentence(document),
                published_at=document.published_at,
            )
        )
    if direct_role == "competitor":
        events.append(
            InsightEvent(
                id=f"evt_{start_index + len(events) + 1:03d}",
                source_document_id=document.id,
                source_type=document.source_type,
                event_type="competitor_award_pressure",
                title=document.title,
                summary="机器人相关项目由非目标企业中标或入围，可能带来竞争压力",
                direction="risk",
                dimension="竞争压力",
                evidence_sentence=_bidding_metadata_sentence(document),
                published_at=document.published_at,
            )
        )
    if amount and not any(event.event_type == "amount_signal" for event in events):
        events.append(
            InsightEvent(
                id=f"evt_{start_index + len(events) + 1:03d}",
                source_document_id=document.id,
                source_type=document.source_type,
                event_type="amount_signal",
                title=document.title,
                summary="公告披露金额信息，可用于判断订单或采购需求规模",
                direction="opportunity",
                dimension="订单规模",
                evidence_sentence=_bidding_metadata_sentence(document),
                published_at=document.published_at,
            )
        )
    if any(term in notice_type for term in ("变更", "澄清", "更正")):
        events.append(
            InsightEvent(
                id=f"evt_{start_index + len(events) + 1:03d}",
                source_document_id=document.id,
                source_type=document.source_type,
                event_type="project_change",
                title=document.title,
                summary="公告类型显示项目存在变更或澄清",
                direction="risk",
                dimension="项目不确定性",
                evidence_sentence=_bidding_metadata_sentence(document),
                published_at=document.published_at,
            )
        )
    return events


def _bidding_metadata_sentence(document: SourceDocument) -> str:
    metadata = document.metadata or {}
    parts = [
        str(metadata.get("noticeType") or ""),
        str(metadata.get("projectName") or document.title),
        str(metadata.get("buyerName") or ""),
        str(metadata.get("winningBidder") or ""),
        str(metadata.get("amount") or ""),
        str(metadata.get("directMatchRole") or ""),
    ]
    return "；".join(item for item in parts if item)[:240] or _evidence_sentence(f"{document.title}\n{document.content}", ("采购",))
