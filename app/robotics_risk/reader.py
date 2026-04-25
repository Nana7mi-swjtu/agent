from __future__ import annotations

import json
import re
from collections import defaultdict
from hashlib import sha1
from typing import Any

from ..analysis_artifacts import normalize_chart_candidate, normalize_fact_table, normalize_rendered_asset
from .schemas import (
    AnalysisScope,
    EnterpriseProfile,
    InsightEvent,
    InsightSignal,
    RoboticsReaderEvidenceReference,
    RoboticsReaderPacket,
    RoboticsReaderTheme,
    RoboticsReaderVisual,
    SourceDocument,
)

READER_PACKET_SCHEMA_VERSION = "robotics_reader_packet.v1"
READER_RENDER_MAX_WORDS_PER_THEME = 80

_THEME_GROUPS = {
    "opportunity": {
        "政策支持": ("policy_upgrade", "政策与设备更新"),
        "设备更新": ("policy_upgrade", "政策与设备更新"),
        "产品研发": ("innovation_upgrade", "研发与产业升级"),
        "产业升级": ("innovation_upgrade", "研发与产业升级"),
        "应用场景": ("scenario_demand", "场景落地与需求释放"),
        "订单": ("scenario_demand", "场景落地与需求释放"),
        "订单机会": ("scenario_demand", "场景落地与需求释放"),
        "订单规模": ("scenario_demand", "场景落地与需求释放"),
        "市场需求": ("scenario_demand", "场景落地与需求释放"),
        "投标机会": ("scenario_demand", "场景落地与需求释放"),
        "经营表现": ("business_momentum", "经营兑现与业绩弹性"),
        "产能": ("business_momentum", "经营兑现与业绩弹性"),
    },
    "risk": {
        "政策监管": ("compliance_pressure", "监管与标准门槛"),
        "标准合规": ("compliance_pressure", "监管与标准门槛"),
        "数据合规": ("compliance_pressure", "监管与标准门槛"),
        "治理合规": ("compliance_pressure", "监管与标准门槛"),
        "产品质量": ("compliance_pressure", "监管与标准门槛"),
        "项目不确定性": ("execution_pressure", "项目兑现与执行不确定性"),
        "竞争压力": ("competition_pressure", "竞争与替代压力"),
        "资本市场": ("market_pressure", "资本市场与外部预期压力"),
        "资产质量": ("market_pressure", "资本市场与外部预期压力"),
        "经营表现": ("market_pressure", "资本市场与外部预期压力"),
    },
}


def build_reader_packet(
    *,
    target_company: dict[str, Any],
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    opportunities: list[InsightSignal],
    risks: list[InsightSignal],
    events: list[InsightEvent],
    sources: list[SourceDocument],
    limitations: list[str],
) -> RoboticsReaderPacket:
    grouped_opportunities = _group_themes(opportunities, direction="opportunity")
    grouped_risks = _group_themes(risks, direction="risk")
    evidence_references = _build_evidence_references(sources=sources, events=events)
    visual_summaries = _build_visual_summaries(
        opportunities=grouped_opportunities,
        risks=grouped_risks,
        evidence_references=evidence_references,
    )
    company_name = str(target_company.get("name") or profile.name or "目标企业").strip() or "目标企业"
    return RoboticsReaderPacket(
        schema_version=READER_PACKET_SCHEMA_VERSION,
        target_company=dict(target_company),
        analysis_scope=analysis_scope.to_dict(),
        enterprise_profile=profile.to_dict(),
        executive_summary={
            "headline": _headline(company_name, grouped_opportunities, grouped_risks),
            "opportunity": _summary_line(grouped_opportunities, "机会"),
            "risk": _summary_line(grouped_risks, "风险"),
        },
        opportunities=grouped_opportunities,
        risks=grouped_risks,
        evidence_references=evidence_references,
        visual_summaries=visual_summaries,
        limitations=list(limitations),
    )


def render_reader_brief(
    *,
    target_company: dict[str, Any],
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    reader_packet: RoboticsReaderPacket,
    reader_writer: Any | None = None,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> str:
    sections = render_reader_sections(
        reader_packet=reader_packet,
        reader_writer=reader_writer,
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
    )
    lines = [
        f"# {target_company.get('name', profile.name)}风险与机会洞察简报",
        "",
        "## 1. 分析对象",
        f"- 企业：{target_company.get('name', profile.name)}",
        f"- 行业：{profile.industry}",
        f"- 产业链画像：{', '.join(profile.segments)}",
        f"- 时间范围：{analysis_scope.time_range}",
    ]
    lines.extend(_sections_to_markdown_lines(sections))
    lines.extend(_fact_tables_to_markdown_lines(fact_tables or []))
    lines.extend(_chart_candidates_to_markdown_lines(chart_candidates or [], rendered_assets or []))
    return "\n".join(lines).strip()


def render_reader_sections(
    *,
    reader_packet: RoboticsReaderPacket,
    reader_writer: Any | None = None,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_tables = _normalized_fact_tables(fact_tables)
    normalized_candidates = _normalized_chart_candidates(chart_candidates)
    normalized_assets = _normalized_rendered_assets(rendered_assets)
    fallback_sections = _fallback_reader_sections(
        reader_packet,
        fact_tables=normalized_tables,
        chart_candidates=normalized_candidates,
        rendered_assets=normalized_assets,
    )
    if reader_writer is None:
        return fallback_sections
    payload = _render_with_writer(
        reader_packet=reader_packet,
        reader_writer=reader_writer,
        fact_tables=normalized_tables,
        chart_candidates=normalized_candidates,
        rendered_assets=normalized_assets,
    )
    if not isinstance(payload, dict):
        return fallback_sections
    sections = _normalize_sections(payload.get("sections"))
    if not sections:
        return fallback_sections
    errors = validate_reader_sections(
        sections,
        reader_packet=reader_packet,
        fact_tables=normalized_tables,
        chart_candidates=normalized_candidates,
        rendered_assets=normalized_assets,
    )
    if errors:
        return fallback_sections
    return sections


def validate_reader_sections(
    sections: list[dict[str, Any]],
    *,
    reader_packet: RoboticsReaderPacket,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> list[str]:
    allowed_ids = {"executive_summary", "opportunities", "risks", "evidence", "limitations", "visuals"}
    context = _reader_render_context(
        reader_packet=reader_packet,
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
    )
    packet_text = json.dumps(context, ensure_ascii=False)
    packet_numbers = {match for match in re.findall(r"\d+(?:\.\d+)?", packet_text)}
    errors: list[str] = []
    if not any(str(section.get("id", "")).strip() == "executive_summary" for section in sections):
        errors.append("missing executive_summary")
    for section in sections:
        section_id = str(section.get("id", "")).strip()
        if section_id not in allowed_ids:
            errors.append(f"invalid section id: {section_id}")
        blocks = section.get("blocks", [])
        if not isinstance(blocks, list):
            errors.append(f"section {section_id} missing blocks")
            continue
        for block in blocks:
            if not isinstance(block, dict):
                errors.append(f"section {section_id} contains non-dict block")
                continue
            block_type = str(block.get("type", "")).strip()
            if block_type not in {"paragraph", "items", "evidence", "visuals", "tables"}:
                errors.append(f"invalid block type: {block_type}")
            block_text = json.dumps(block, ensure_ascii=False)
            if any(token in block_text for token in ("moduleId", "traceRefs", "sourceIds", "eventIds", "runId")):
                errors.append(f"internal token leak in {section_id}")
            for number in re.findall(r"\d+(?:\.\d+)?", block_text):
                if number not in packet_numbers:
                    errors.append(f"unsupported number in {section_id}: {number}")
                    break
            if block_type == "items":
                errors.extend(_validate_reader_item_block(block, section_id=section_id, context=context))
            elif block_type == "evidence":
                errors.extend(_validate_reader_evidence_block(block, context=context))
            elif block_type == "visuals":
                errors.extend(_validate_reader_visual_block(block, context=context))
            elif block_type == "tables":
                errors.extend(_validate_reader_table_block(block, context=context))
    return errors


def _render_with_writer(
    *,
    reader_packet: RoboticsReaderPacket,
    reader_writer: Any,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    prompt = (
        "你是机器人行业模块结果写作器。只根据给定 reader packet 生成用户可读模块输出，"
        "不得新增事实、数字、来源、企业判断或证据结论。"
        "必须保留行业推断与企业直接证据之间的边界，不得输出 moduleId、sourceIds、eventIds、traceRefs、runId 等内部字段。"
        "输出必须是 JSON 对象，格式为 "
        "{\"sections\":[{\"id\":\"executive_summary\",\"title\":\"执行摘要\",\"blocks\":[{\"type\":\"paragraph\",\"text\":\"...\"}]}]}。"
        "允许的 section id: executive_summary, opportunities, risks, evidence, limitations, visuals。"
        "允许的 block type: paragraph, items, evidence, visuals, tables。"
        "opportunities/risks 的 items 必须引用 themeId；evidence 的 items 必须引用 referenceId；"
        "visuals 的 items 必须引用 chartId 或 assetId；tables 的 items 必须引用 tableId。"
        "可以改写 readerSummary，但不得改写已引用对象的标题，也不得引用不存在的 theme/reference/table/chart/asset。"
    )
    payload = _reader_render_context(
        reader_packet=reader_packet,
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
    )
    try:
        response = reader_writer.invoke(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]
        )
    except Exception:
        return None
    content = getattr(response, "content", response)
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match is None:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _normalize_sections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for section in value:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id", "")).strip()
        title = str(section.get("title", "")).strip()
        blocks = section.get("blocks", [])
        if not section_id or not title or not isinstance(blocks, list):
            continue
        normalized_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", "")).strip()
            if block_type == "paragraph":
                text = str(block.get("text", "")).strip()
                if text:
                    normalized_blocks.append({"type": "paragraph", "text": text})
                continue
            if block_type in {"items", "evidence", "visuals", "tables"}:
                items = []
                for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
                    if not isinstance(item, dict):
                        continue
                    cleaned = {
                        key: str(item.get(key, "")).strip()
                        for key in (
                            "title",
                            "summary",
                            "readerSummary",
                            "basisSummary",
                            "caption",
                            "interpretationBoundary",
                            "verificationStatus",
                            "sourceDescription",
                        )
                        if item.get(key) not in (None, "", [], {})
                    }
                    for ref_key in ("themeId", "referenceId", "tableId", "chartId", "assetId"):
                        ref_value = str(item.get(ref_key, "")).strip()
                        if ref_value:
                            cleaned[ref_key] = ref_value
                    if cleaned:
                        items.append(cleaned)
                if items:
                    normalized_blocks.append({"type": block_type, "items": items})
        if normalized_blocks:
            sections.append({"id": section_id, "title": title, "blocks": normalized_blocks})
    return sections


def _fallback_reader_sections(
    reader_packet: RoboticsReaderPacket,
    *,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    fallback_tables = _fallback_table_refs(fact_tables or [])
    fallback_visuals = _fallback_visual_items(
        chart_candidates=chart_candidates or [],
        rendered_assets=rendered_assets or [],
        reader_packet=reader_packet,
    )
    sections = [
        {
            "id": "executive_summary",
            "title": "执行摘要",
            "blocks": [
                {"type": "paragraph", "text": reader_packet.executive_summary.get("headline", "")},
                {"type": "tables", "items": fallback_tables.get("executive_summary", [])},
            ],
        },
        {
            "id": "opportunities",
            "title": "机会信号",
            "blocks": [
                {
                    "type": "items",
                    "items": [
                        {
                            "themeId": item.id,
                            "title": item.title,
                            "readerSummary": item.summary,
                            "basisSummary": item.basis_summary,
                            "interpretationBoundary": item.interpretation_boundary,
                        }
                        for item in reader_packet.opportunities
                    ],
                }
            ]
            + ([{"type": "tables", "items": fallback_tables.get("opportunities", [])}] if fallback_tables.get("opportunities") else []),
        },
        {
            "id": "risks",
            "title": "风险信号",
            "blocks": [
                {
                    "type": "items",
                    "items": [
                        {
                            "themeId": item.id,
                            "title": item.title,
                            "readerSummary": item.summary,
                            "basisSummary": item.basis_summary,
                            "interpretationBoundary": item.interpretation_boundary,
                        }
                        for item in reader_packet.risks
                    ],
                }
            ]
            + ([{"type": "tables", "items": fallback_tables.get("risks", [])}] if fallback_tables.get("risks") else []),
        },
        {
            "id": "evidence",
            "title": "证据来源",
            "blocks": [
                {
                    "type": "evidence",
                    "items": [
                        {
                            "referenceId": item.id,
                            "title": item.title,
                            "readerSummary": item.reader_summary,
                            "verificationStatus": item.verification_status,
                            "sourceDescription": item.source_name,
                        }
                        for item in reader_packet.evidence_references[:5]
                    ],
                }
            ]
            + ([{"type": "tables", "items": fallback_tables.get("evidence", [])}] if fallback_tables.get("evidence") else []),
        },
        {
            "id": "visuals",
            "title": "图表摘要",
            "blocks": [
                {
                    "type": "visuals",
                    "items": fallback_visuals,
                }
            ],
        },
        {
            "id": "limitations",
            "title": "来源与限制",
            "blocks": [
                {
                    "type": "items",
                    "items": [{"title": "限制说明", "readerSummary": item} for item in reader_packet.limitations[:5]],
                }
            ],
        },
    ]
    return [section for section in sections if any(block.get("items") or block.get("text") for block in section["blocks"])]


def _reader_render_context(
    *,
    reader_packet: RoboticsReaderPacket,
    fact_tables: list[dict[str, Any]] | None = None,
    chart_candidates: list[dict[str, Any]] | None = None,
    rendered_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tables = _normalized_fact_tables(fact_tables)
    candidates = _normalized_chart_candidates(chart_candidates)
    assets = _normalized_rendered_assets(rendered_assets)
    return {
        "readerPacket": reader_packet.to_dict(),
        "factTables": tables,
        "chartCandidates": candidates,
        "renderedAssets": assets,
        "allowedReferences": {
            "opportunityThemes": {
                item.id: {"title": item.title}
                for item in reader_packet.opportunities
            },
            "riskThemes": {
                item.id: {"title": item.title}
                for item in reader_packet.risks
            },
            "evidenceReferences": {
                item.id: {"title": item.title}
                for item in reader_packet.evidence_references
            },
            "factTables": {
                str(item.get("tableId")): {"title": str(item.get("title") or item.get("tableId") or "").strip()}
                for item in tables
                if str(item.get("tableId") or "").strip()
            },
            "chartCandidates": {
                str(item.get("chartId")): {
                    "title": str(item.get("title") or item.get("chartId") or "").strip(),
                    "sourceTableId": str(item.get("sourceTableId") or "").strip(),
                }
                for item in candidates
                if str(item.get("chartId") or "").strip()
            },
            "renderedAssets": {
                str(item.get("assetId")): {
                    "title": str(item.get("title") or item.get("assetId") or "").strip(),
                    "chartId": str(item.get("chartId") or "").strip(),
                    "sourceTableId": str(item.get("sourceTableId") or "").strip(),
                }
                for item in assets
                if str(item.get("assetId") or "").strip()
            },
        },
    }


def _validate_reader_item_block(block: dict[str, Any], *, section_id: str, context: dict[str, Any]) -> list[str]:
    if section_id not in {"opportunities", "risks", "limitations"}:
        return []
    items = block.get("items", []) if isinstance(block.get("items"), list) else []
    theme_key = "opportunityThemes" if section_id == "opportunities" else "riskThemes"
    allowed = context.get("allowedReferences", {}).get(theme_key, {})
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if section_id == "limitations":
            continue
        theme_id = str(item.get("themeId") or "").strip()
        if not theme_id or theme_id not in allowed:
            errors.append(f"{section_id} item missing supported themeId")
            continue
        title = str(item.get("title") or "").strip()
        expected = str(allowed.get(theme_id, {}).get("title") or "").strip()
        if title and expected and title != expected:
            errors.append(f"{section_id} item title mismatch for {theme_id}")
    return errors


def _validate_reader_evidence_block(block: dict[str, Any], *, context: dict[str, Any]) -> list[str]:
    items = block.get("items", []) if isinstance(block.get("items"), list) else []
    allowed = context.get("allowedReferences", {}).get("evidenceReferences", {})
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reference_id = str(item.get("referenceId") or "").strip()
        if not reference_id or reference_id not in allowed:
            errors.append("evidence item missing supported referenceId")
            continue
        title = str(item.get("title") or "").strip()
        expected = str(allowed.get(reference_id, {}).get("title") or "").strip()
        if title and expected and title != expected:
            errors.append(f"evidence item title mismatch for {reference_id}")
    return errors


def _validate_reader_visual_block(block: dict[str, Any], *, context: dict[str, Any]) -> list[str]:
    items = block.get("items", []) if isinstance(block.get("items"), list) else []
    allowed_candidates = context.get("allowedReferences", {}).get("chartCandidates", {})
    allowed_assets = context.get("allowedReferences", {}).get("renderedAssets", {})
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("assetId") or "").strip()
        chart_id = str(item.get("chartId") or "").strip()
        if asset_id:
            if asset_id not in allowed_assets:
                errors.append(f"visual item references unknown assetId {asset_id}")
                continue
            expected = str(allowed_assets.get(asset_id, {}).get("title") or "").strip()
        elif chart_id:
            if chart_id not in allowed_candidates:
                errors.append(f"visual item references unknown chartId {chart_id}")
                continue
            expected = str(allowed_candidates.get(chart_id, {}).get("title") or "").strip()
        else:
            errors.append("visual item missing chartId or assetId")
            continue
        title = str(item.get("title") or "").strip()
        if title and expected and title != expected:
            errors.append(f"visual item title mismatch for {asset_id or chart_id}")
    return errors


def _validate_reader_table_block(block: dict[str, Any], *, context: dict[str, Any]) -> list[str]:
    items = block.get("items", []) if isinstance(block.get("items"), list) else []
    allowed = context.get("allowedReferences", {}).get("factTables", {})
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        table_id = str(item.get("tableId") or "").strip()
        if not table_id or table_id not in allowed:
            errors.append("table block item missing supported tableId")
            continue
        title = str(item.get("title") or "").strip()
        expected = str(allowed.get(table_id, {}).get("title") or "").strip()
        if title and expected and title != expected:
            errors.append(f"table block title mismatch for {table_id}")
    return errors


def _normalized_fact_tables(value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [normalize_fact_table(item) for item in value if isinstance(item, dict)]


def _normalized_chart_candidates(value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [normalize_chart_candidate(item) for item in value if isinstance(item, dict)]


def _normalized_rendered_assets(value: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [normalize_rendered_asset(item) for item in value if isinstance(item, dict)]


def _fallback_table_refs(fact_tables: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    table_map = {
        str(item.get("tableId") or "").strip(): item
        for item in fact_tables
        if isinstance(item, dict) and str(item.get("tableId") or "").strip()
    }
    return {
        "executive_summary": _fallback_table_items(table_map, ("enterprise_snapshot",)),
        "opportunities": _fallback_table_items(table_map, ("opportunity_themes",)),
        "risks": _fallback_table_items(table_map, ("risk_themes",)),
        "evidence": _fallback_table_items(table_map, ("evidence_references", "event_timeline")),
    }


def _fallback_table_items(table_map: dict[str, dict[str, Any]], table_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for table_id in table_ids:
        table = table_map.get(table_id)
        if not isinstance(table, dict):
            continue
        title = str(table.get("title") or table_id).strip() or "结构化表格"
        items.append(
            {
                "tableId": table_id,
                "title": title,
                "readerSummary": str(table.get("description") or table.get("emptyText") or "相关事实见下方结构化表格。").strip()
                or "相关事实见下方结构化表格。",
            }
        )
    return items


def _fallback_visual_items(
    *,
    chart_candidates: list[dict[str, Any]],
    rendered_assets: list[dict[str, Any]],
    reader_packet: RoboticsReaderPacket,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for asset in rendered_assets[:3]:
        if not isinstance(asset, dict):
            continue
        items.append(
            {
                "assetId": str(asset.get("assetId") or "").strip(),
                "chartId": str(asset.get("chartId") or "").strip(),
                "title": str(asset.get("title") or "图表").strip() or "图表",
                "caption": str(asset.get("caption") or "").strip(),
                "interpretationBoundary": str(asset.get("interpretationBoundary") or "").strip(),
            }
        )
    if items:
        return items
    for candidate in chart_candidates[:3]:
        if not isinstance(candidate, dict):
            continue
        items.append(
            {
                "chartId": str(candidate.get("chartId") or "").strip(),
                "tableId": str(candidate.get("sourceTableId") or candidate.get("fallbackTableId") or "").strip(),
                "title": str(candidate.get("title") or "图表候选").strip() or "图表候选",
                "caption": str(candidate.get("caption") or "").strip(),
                "interpretationBoundary": str(candidate.get("interpretationBoundary") or "").strip(),
            }
        )
    if items:
        return items
    return [
        {
            "title": item.title,
            "caption": item.caption,
            "interpretationBoundary": item.interpretation_boundary,
        }
        for item in reader_packet.visual_summaries[:3]
    ]


def _sections_to_markdown_lines(sections: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = [""]
    title_map = {
        "executive_summary": "## 2. 执行摘要",
        "opportunities": "## 3. 机会信号",
        "risks": "## 4. 风险信号",
        "evidence": "## 5. 证据来源",
        "visuals": "## 6. 图表摘要",
        "limitations": "## 7. 来源与限制",
    }
    for section in sections:
        header = title_map.get(str(section.get("id", "")).strip(), f"## {str(section.get('title', '')).strip() or '章节'}")
        lines.extend([header, ""])
        for block in section.get("blocks", []) if isinstance(section.get("blocks"), list) else []:
            block_type = str(block.get("type", "")).strip()
            if block_type == "paragraph":
                text = str(block.get("text", "")).strip()
                if text:
                    lines.extend([text, ""])
                continue
            for item in block.get("items", []) if isinstance(block.get("items"), list) else []:
                title = str(item.get("title", "")).strip()
                summary = str(item.get("readerSummary") or item.get("summary") or item.get("caption") or "").strip()
                boundary = str(item.get("interpretationBoundary", "")).strip()
                if title and summary:
                    lines.append(f"- {title}：{summary}")
                elif title:
                    lines.append(f"- {title}")
                elif summary:
                    lines.append(f"- {summary}")
                if boundary:
                    lines.append(f"  解读边界：{boundary}")
            lines.append("")
    return lines


def _fact_tables_to_markdown_lines(fact_tables: list[dict[str, Any]]) -> list[str]:
    tables = [item for item in fact_tables if isinstance(item, dict) and item.get("columns")]
    if not tables:
        return []
    lines: list[str] = ["## 结构化表格", ""]
    for table in tables:
        title = str(table.get("title") or table.get("tableId") or "表格").strip()
        columns = [item for item in table.get("columns", []) if isinstance(item, dict) and str(item.get("label") or item.get("key") or "").strip()]
        rows = [item for item in table.get("rows", []) if isinstance(item, dict)]
        if not columns:
            continue
        lines.extend([f"### {title}", ""])
        header = "| " + " | ".join(_escape_markdown_table_text(item.get("label") or item.get("key")) for item in columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        lines.extend([header, separator])
        for row in rows[:8]:
            cells = row.get("cells", {}) if isinstance(row.get("cells"), dict) else {}
            values = [_escape_markdown_table_text(cells.get(str(item.get("key") or ""))) for item in columns]
            lines.append("| " + " | ".join(values) + " |")
        if not rows and str(table.get("emptyText") or "").strip():
            lines.extend([str(table.get("emptyText")).strip(), ""])
        else:
            lines.append("")
    return lines


def _chart_candidates_to_markdown_lines(
    chart_candidates: list[dict[str, Any]],
    rendered_assets: list[dict[str, Any]],
) -> list[str]:
    candidates = [item for item in chart_candidates if isinstance(item, dict) and str(item.get("title") or "").strip()]
    if not candidates:
        return []
    rendered_ids = {
        str(item.get("chartId")).strip()
        for item in rendered_assets
        if isinstance(item, dict) and str(item.get("chartId") or "").strip()
    }
    lines: list[str] = ["## 图表候选", ""]
    for item in candidates[:6]:
        title = str(item.get("title") or "图表").strip()
        caption = str(item.get("caption") or "").strip()
        boundary = str(item.get("interpretationBoundary") or "").strip()
        render_state = "已生成图像资产" if str(item.get("chartId") or "").strip() in rendered_ids else "当前仅保留候选与表格回退"
        body = caption or "该图表用于辅助比较结构化表格中的可比信息。"
        lines.append(f"- **{title}**：{body}")
        lines.append(f"  - 呈现状态：{render_state}")
        if boundary:
            lines.append(f"  - 解读边界：{boundary}")
    lines.append("")
    return lines


def _group_themes(signals: list[InsightSignal], *, direction: str) -> list[RoboticsReaderTheme]:
    buckets: dict[tuple[str, str], list[InsightSignal]] = defaultdict(list)
    for signal in signals:
        group_id, group_title = _theme_key(signal.category, direction=direction)
        buckets[(group_id, group_title)].append(signal)
    themes: list[RoboticsReaderTheme] = []
    for (group_id, group_title), items in buckets.items():
        items.sort(key=lambda item: item.impact_score, reverse=True)
        source_ids = _dedupe([source_id for item in items for source_id in item.source_ids])
        event_ids = _dedupe([event_id for item in items for event_id in item.event_ids])
        signal_ids = _dedupe([item.id for item in items])
        categories = _dedupe([item.category for item in items])
        top = items[0]
        theme_id = f"theme_{direction}_{sha1('|'.join([group_id, *signal_ids]).encode('utf-8')).hexdigest()[:8]}"
        themes.append(
            RoboticsReaderTheme(
                id=theme_id,
                type=direction,
                title=group_title,
                summary=_theme_summary(items, direction=direction),
                basis_summary=f"归并维度：{', '.join(categories)}。",
                interpretation_boundary=_theme_boundary(items),
                confidence=round(max(item.confidence for item in items), 2),
                impact_score=max(item.impact_score for item in items),
                categories=categories,
                source_ids=source_ids,
                event_ids=event_ids,
                signal_ids=signal_ids,
            )
        )
    themes.sort(key=lambda item: int(item.impact_score or 0), reverse=True)
    return themes


def _theme_key(category: str, *, direction: str) -> tuple[str, str]:
    clean = str(category or "").strip()
    mapped = _THEME_GROUPS.get(direction, {}).get(clean)
    if mapped:
        return mapped
    token = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", clean).strip("_") or direction
    return token.lower(), clean or ("机会主题" if direction == "opportunity" else "风险主题")


def _theme_summary(items: list[InsightSignal], *, direction: str) -> str:
    categories = "、".join(_dedupe(item.category for item in items))
    top_reason = _truncate_sentence(items[0].reasoning)
    if len(items) == 1:
        return top_reason or f"{categories}是当前最需要关注的{'机会' if direction == 'opportunity' else '风险'}方向。"
    if top_reason:
        return f"{categories}共同构成当前需要优先关注的{'机会' if direction == 'opportunity' else '风险'}主线。{top_reason}"
    return f"{categories}共同构成当前需要优先关注的{'机会' if direction == 'opportunity' else '风险'}主线。"


def _theme_boundary(items: list[InsightSignal]) -> str:
    for item in items:
        clean = str(item.reasoning or "").strip()
        if "尚需企业后续公告或经营数据验证" in clean:
            return "当前判断主要来自行业或市场层面证据，仍需企业后续公告或经营数据验证。"
    return "结论基于本轮已采集证据整理，需随后续事实更新持续复核。"


def _headline(company_name: str, opportunities: list[RoboticsReaderTheme], risks: list[RoboticsReaderTheme]) -> str:
    opportunity = opportunities[0].title if opportunities else "未形成明确机会主线"
    risk = risks[0].title if risks else "未形成明确风险主线"
    return f"{company_name}当前最值得关注的机会主线是{opportunity}，主要约束来自{risk}。"


def _summary_line(items: list[RoboticsReaderTheme], label: str) -> str:
    if not items:
        return f"未形成明确{label}主线。"
    top = items[0]
    return f"主要{label}集中在{top.title}，当前最高影响分为{int(top.impact_score or 0)}。"


def _build_evidence_references(
    *,
    sources: list[SourceDocument],
    events: list[InsightEvent],
) -> list[RoboticsReaderEvidenceReference]:
    events_by_source: dict[str, list[InsightEvent]] = defaultdict(list)
    for event in events:
        events_by_source[event.source_document_id].append(event)
    references: list[RoboticsReaderEvidenceReference] = []
    for index, source in enumerate(sources, start=1):
        related = events_by_source.get(source.id, [])
        metadata = dict(source.metadata or {})
        verification = "已纳入本轮结构化分析，仍需结合后续事实更新复核。"
        if str(source.relevance_scope or "").strip() == "enterprise":
            verification = "该来源与目标企业直接相关，可作为企业层证据阅读。"
        elif related:
            verification = "该来源主要用于支撑行业或市场层判断，需结合企业后续兑现情况复核。"
        references.append(
            RoboticsReaderEvidenceReference(
                id=f"reader_evidence_{index}",
                title=str(source.title or source.source_name or "来源").strip() or "来源",
                source_type=str(source.source_type or "").strip(),
                source_name=str(source.source_name or "").strip(),
                reader_summary=_evidence_summary(source=source, events=related),
                published_at=str(source.published_at or "").strip(),
                url=str(source.url or "").strip(),
                locator=str(
                    metadata.get("pdfUrl")
                    or metadata.get("adjunctUrl")
                    or metadata.get("policyId")
                    or metadata.get("noticeId")
                    or source.url
                    or ""
                ).strip(),
                relevance_scope=str(source.relevance_scope or "").strip(),
                verification_status=verification,
                event_ids=[event.id for event in related],
                source_ids=[source.id],
            )
        )
    return references


def _evidence_summary(*, source: SourceDocument, events: list[InsightEvent]) -> str:
    for event in events:
        sentence = str(event.evidence_sentence or "").strip()
        if sentence:
            return _truncate_sentence(sentence)
    content = str(source.content or source.title or "").strip()
    if content:
        return _truncate_sentence(content)
    return "该来源用于支撑本轮模块判断。"


def _build_visual_summaries(
    *,
    opportunities: list[RoboticsReaderTheme],
    risks: list[RoboticsReaderTheme],
    evidence_references: list[RoboticsReaderEvidenceReference],
) -> list[RoboticsReaderVisual]:
    visuals: list[RoboticsReaderVisual] = []
    if opportunities:
        visuals.append(
            RoboticsReaderVisual(
                id="visual_opportunity_theme_strength",
                type="chart",
                title="机会主题强度分布",
                caption="用于比较当前机会主线的相对强弱，帮助读者先看主线再看细节。",
                interpretation_boundary="图中分值用于相对排序，不等同于精确预测结果。",
                render_payload={
                    "chartType": "bar",
                    "series": [
                        {"label": item.title, "value": int(item.impact_score or 0)}
                        for item in opportunities[:5]
                    ],
                },
                source_ids=_dedupe(source_id for item in opportunities for source_id in item.source_ids),
                event_ids=_dedupe(event_id for item in opportunities for event_id in item.event_ids),
                signal_ids=_dedupe(signal_id for item in opportunities for signal_id in item.signal_ids),
            )
        )
    if risks:
        visuals.append(
            RoboticsReaderVisual(
                id="visual_risk_theme_strength",
                type="chart",
                title="风险主题强度分布",
                caption="用于比较当前风险主线的相对强弱，避免把相近风险拆成重复长句。",
                interpretation_boundary="图中分值用于相对排序，不等同于精确预测结果。",
                render_payload={
                    "chartType": "bar",
                    "series": [
                        {"label": item.title, "value": int(item.impact_score or 0)}
                        for item in risks[:5]
                    ],
                },
                source_ids=_dedupe(source_id for item in risks for source_id in item.source_ids),
                event_ids=_dedupe(event_id for item in risks for event_id in item.event_ids),
                signal_ids=_dedupe(signal_id for item in risks for signal_id in item.signal_ids),
            )
        )
    if evidence_references:
        counts: dict[str, int] = defaultdict(int)
        for item in evidence_references:
            counts[item.source_type] += 1
        visuals.append(
            RoboticsReaderVisual(
                id="visual_source_composition",
                type="chart",
                title="证据来源构成",
                caption="展示本轮判断主要来自政策、公告还是招投标来源，帮助读者理解证据层级。",
                interpretation_boundary="来源数量反映覆盖面，不单独代表证据质量高低。",
                render_payload={
                    "chartType": "donut",
                    "series": [{"label": key or "unknown", "value": value} for key, value in sorted(counts.items())],
                },
                source_ids=_dedupe(source_id for item in evidence_references for source_id in item.source_ids),
                event_ids=_dedupe(event_id for item in evidence_references for event_id in item.event_ids),
            )
        )
    return visuals


def _truncate_sentence(value: str) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= 140:
        return clean
    return clean[:137].rstrip() + "..."


def _escape_markdown_table_text(value: Any) -> str:
    text = str(value if value not in (None, [], {}) else "-").strip()
    if not text:
        text = "-"
    return text.replace("|", "\\|").replace("\n", "<br>")


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result
