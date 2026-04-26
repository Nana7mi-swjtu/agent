from __future__ import annotations

from typing import Any

from .schemas import (
    InsightEvent,
    InsightSignal,
    RoboticsInsightResult,
    RoboticsReaderEvidenceReference,
    RoboticsReaderTheme,
    RoboticsReaderVisual,
    SourceDocument,
)

DISPLAY_HANDOFF_SCHEMA_VERSION = "robotics_display_handoff.v1"
DOCUMENT_TYPE = "robotics_risk_opportunity_brief"


def build_display_handoff(result: RoboticsInsightResult) -> dict[str, Any]:
    reader_packet = result.reader_packet
    fact_tables = [dict(item) for item in result.fact_tables if isinstance(item, dict)]
    chart_candidates = [dict(item) for item in result.chart_candidates if isinstance(item, dict)]
    rendered_assets = [dict(item) for item in result.rendered_assets if isinstance(item, dict)]
    opportunity_items = (
        [_theme_entry(item) for item in reader_packet.opportunities]
        if reader_packet is not None
        else [_signal_entry(signal) for signal in result.opportunities]
    )
    risk_items = (
        [_theme_entry(item) for item in reader_packet.risks]
        if reader_packet is not None
        else [_signal_entry(signal) for signal in result.risks]
    )
    evidence_rows = _evidence_rows(result.sources, result.events)
    evidence_references = (
        [_reader_evidence_reference(item) for item in reader_packet.evidence_references]
        if reader_packet is not None
        else []
    )
    visual_summaries = (
        [_visual_summary(item) for item in reader_packet.visual_summaries]
        if reader_packet is not None
        else []
    )
    section_resources = _section_resources(fact_tables=fact_tables, rendered_assets=rendered_assets)
    citation_map = _citation_map(
        opportunities=result.opportunities,
        risks=result.risks,
        events=result.events,
        theme_sections=[*opportunity_items, *risk_items],
        evidence_references=evidence_references,
        visual_summaries=visual_summaries,
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
    )
    limitations = list(result.limitations)
    company_name = str(result.target_company.get("name") or result.enterprise_profile.name or "目标企业").strip()
    executive_summary = {
        "headline": reader_packet.executive_summary.get("headline", "") if reader_packet is not None else "",
        "opportunity": result.summary.get("opportunity", ""),
        "risk": result.summary.get("risk", ""),
        "sourceCount": len(result.sources),
        "eventCount": len(result.events),
        "limitationCount": len(limitations),
        "opportunityThemeCount": len(opportunity_items),
        "riskThemeCount": len(risk_items),
    }

    return _drop_empty(
        {
            "schemaVersion": DISPLAY_HANDOFF_SCHEMA_VERSION,
            "documentType": DOCUMENT_TYPE,
            "recommendedFormat": "markdown",
            "title": f"{company_name}风险与机会洞察简报",
            "targetCompany": dict(result.target_company),
            "analysisScope": result.analysis_scope.to_dict(),
            "enterpriseProfile": result.enterprise_profile.to_dict(),
            "executiveSummary": executive_summary,
            "recommendedSections": [
                {
                    "id": "executive_summary",
                    "order": 1,
                    "title": "执行摘要",
                    "content": [
                        executive_summary.get("headline", ""),
                        executive_summary.get("opportunity", ""),
                        executive_summary.get("risk", ""),
                    ],
                    "resourceRefs": section_resources.get("executive_summary", {}),
                },
                {
                    "id": "opportunities",
                    "order": 2,
                    "title": "机会信号",
                    "items": opportunity_items,
                    "emptyState": "" if opportunity_items else "未发现高置信度机会信号。",
                    "resourceRefs": section_resources.get("opportunities", {}),
                },
                {
                    "id": "risks",
                    "order": 3,
                    "title": "风险信号",
                    "items": risk_items,
                    "emptyState": "" if risk_items else "未发现高置信度风险信号。",
                    "resourceRefs": section_resources.get("risks", {}),
                },
                {
                    "id": "visuals",
                    "order": 4,
                    "title": "图表摘要",
                    "items": visual_summaries,
                    "emptyState": "" if visual_summaries else "暂无可展示图表摘要。",
                    "resourceRefs": section_resources.get("key_visuals", {}),
                },
                {
                    "id": "evidence",
                    "order": 5,
                    "title": "证据与引用",
                    "items": evidence_references or evidence_rows,
                    "emptyState": "" if evidence_references or evidence_rows else "暂无可引用证据。",
                    "resourceRefs": section_resources.get("evidence", {}),
                },
                {
                    "id": "limitations",
                    "order": 6,
                    "title": "限制说明",
                    "items": limitations or ["暂无额外限制。"],
                },
            ],
            "readerPacket": reader_packet.to_dict() if reader_packet is not None else {},
            "opportunitySections": opportunity_items,
            "riskSections": risk_items,
            "factTables": fact_tables,
            "chartCandidates": chart_candidates,
            "renderedAssets": rendered_assets,
            "evidenceTable": evidence_rows,
            "evidenceReferences": evidence_references,
            "visualSummaries": visual_summaries,
            "sectionResources": section_resources,
            "citationMap": citation_map,
            "limitations": limitations,
            "sourceDiagnostics": [item.to_dict() for item in result.source_diagnostics],
        }
    )


def _signal_entry(signal: InsightSignal) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": signal.id,
            "type": signal.type,
            "category": signal.category,
            "title": signal.title,
            "impactScore": signal.impact_score,
            "confidence": signal.confidence,
            "reasoning": signal.reasoning,
            "relatedEventIds": list(signal.event_ids),
            "sourceIds": list(signal.source_ids),
        }
    )


def _theme_entry(theme: RoboticsReaderTheme) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": theme.id,
            "type": theme.type,
            "title": theme.title,
            "summary": theme.summary,
            "basisSummary": theme.basis_summary,
            "interpretationBoundary": theme.interpretation_boundary,
            "impactScore": theme.impact_score,
            "confidence": theme.confidence,
            "categories": list(theme.categories),
            "sourceIds": list(theme.source_ids),
            "eventIds": list(theme.event_ids),
            "relatedEventIds": list(theme.event_ids),
            "signalIds": list(theme.signal_ids),
        }
    )


def _reader_evidence_reference(reference: RoboticsReaderEvidenceReference) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": reference.id,
            "title": reference.title,
            "sourceType": reference.source_type,
            "sourceName": reference.source_name,
            "readerSummary": reference.reader_summary,
            "publishedAt": reference.published_at,
            "url": reference.url,
            "locator": reference.locator,
            "relevanceScope": reference.relevance_scope,
            "verificationStatus": reference.verification_status,
            "sourceIds": list(reference.source_ids),
            "eventIds": list(reference.event_ids),
        }
    )


def _visual_summary(visual: RoboticsReaderVisual) -> dict[str, Any]:
    return _drop_empty(
        {
            "id": visual.id,
            "type": visual.type,
            "title": visual.title,
            "caption": visual.caption,
            "interpretationBoundary": visual.interpretation_boundary,
            "renderPayload": dict(visual.render_payload or {}),
            "sourceIds": list(visual.source_ids),
            "eventIds": list(visual.event_ids),
            "signalIds": list(visual.signal_ids),
        }
    )


def _evidence_rows(sources: list[SourceDocument], events: list[InsightEvent]) -> list[dict[str, Any]]:
    events_by_source: dict[str, list[InsightEvent]] = {}
    for event in events:
        events_by_source.setdefault(event.source_document_id, []).append(event)

    rows: list[dict[str, Any]] = []
    for index, source in enumerate(sources, start=1):
        source_events = events_by_source.get(source.id, [])
        metadata = dict(source.metadata or {})
        rows.append(
            _drop_empty(
                {
                    "id": f"evidence_{index}",
                    "sourceId": source.id,
                    "sourceType": source.source_type,
                    "sourceName": source.source_name,
                    "title": source.title,
                    "publishedAt": source.published_at,
                    "url": source.url,
                    "locator": metadata.get("pdfUrl")
                    or metadata.get("adjunctUrl")
                    or metadata.get("policyId")
                    or metadata.get("noticeId")
                    or source.url,
                    "relevanceScope": source.relevance_scope,
                    "evidenceText": _evidence_text(source, source_events),
                    "eventIds": [event.id for event in source_events],
                    "metadataStatus": metadata.get("status") or metadata.get("parseStatus"),
                    "metadataOnlyNote": _metadata_only_note(metadata),
                }
            )
        )
    return rows


def _section_resources(
    *,
    fact_tables: list[dict[str, Any]],
    rendered_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    table_ids = {
        _clean_text(item.get("tableId"))
        for item in fact_tables
        if _clean_text(item.get("tableId"))
    }
    assets_by_table: dict[str, list[str]] = {}
    unassigned_assets: list[str] = []
    for item in rendered_assets:
        if not isinstance(item, dict):
            continue
        asset_id = _clean_text(item.get("assetId"))
        if not asset_id:
            continue
        table_id = _clean_text(item.get("sourceTableId") or item.get("fallbackTableId"))
        if table_id:
            assets_by_table.setdefault(table_id, [])
            if asset_id not in assets_by_table[table_id]:
                assets_by_table[table_id].append(asset_id)
            continue
        if asset_id not in unassigned_assets:
            unassigned_assets.append(asset_id)

    def _resource_refs(*resource_table_ids: str) -> dict[str, Any]:
        clean_table_ids = [table_id for table_id in resource_table_ids if table_id in table_ids]
        clean_asset_ids: list[str] = []
        for table_id in clean_table_ids:
            for asset_id in assets_by_table.get(table_id, []):
                if asset_id not in clean_asset_ids:
                    clean_asset_ids.append(asset_id)
        return _drop_empty({"tableIds": clean_table_ids, "assetIds": clean_asset_ids})

    return _drop_empty(
        {
            "executive_summary": _resource_refs("enterprise_snapshot"),
            "opportunities": _resource_refs("opportunity_themes"),
            "risks": _resource_refs("risk_themes"),
            "evidence": _resource_refs("evidence_references", "event_timeline", "source_composition"),
            "key_visuals": {"assetIds": unassigned_assets} if unassigned_assets else {},
        }
    )


def _citation_map(
    *,
    opportunities: list[InsightSignal],
    risks: list[InsightSignal],
    events: list[InsightEvent],
    theme_sections: list[dict[str, Any]],
    evidence_references: list[dict[str, Any]],
    visual_summaries: list[dict[str, Any]],
    fact_tables: list[dict[str, Any]],
    chart_candidates: list[dict[str, Any]],
    rendered_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    signals = [*opportunities, *risks]
    return _drop_empty(
        {
            "signals": {
                signal.id: {
                    "sourceIds": list(signal.source_ids),
                    "eventIds": list(signal.event_ids),
                }
                for signal in signals
            },
            "events": {
                event.id: {
                    "sourceId": event.source_document_id,
                    "sourceType": event.source_type,
                }
                for event in events
            },
            "themes": {
                _clean_text(item.get("id")): {
                    "sourceIds": list(item.get("sourceIds") or []),
                    "eventIds": list(item.get("eventIds") or item.get("relatedEventIds") or []),
                    "signalIds": list(item.get("signalIds") or []),
                }
                for item in theme_sections
                if _clean_text(item.get("id"))
            },
            "evidenceReferences": {
                _clean_text(item.get("id")): {
                    "sourceIds": list(item.get("sourceIds") or []),
                    "eventIds": list(item.get("eventIds") or []),
                }
                for item in evidence_references
                if _clean_text(item.get("id"))
            },
            "visuals": {
                _clean_text(item.get("id")): {
                    "sourceIds": list(item.get("sourceIds") or []),
                    "eventIds": list(item.get("eventIds") or []),
                    "signalIds": list(item.get("signalIds") or []),
                }
                for item in visual_summaries
                if _clean_text(item.get("id"))
            },
            "factTables": {
                _clean_text(item.get("tableId")): {
                    "sourceIds": _trace_list(item, "sourceIds"),
                    "eventIds": _trace_list(item, "eventIds"),
                    "signalIds": _trace_list(item, "signalIds"),
                }
                for item in fact_tables
                if _clean_text(item.get("tableId"))
            },
            "chartCandidates": {
                _clean_text(item.get("chartId")): {
                    "sourceIds": _trace_list(item, "sourceIds"),
                    "eventIds": _trace_list(item, "eventIds"),
                    "signalIds": _trace_list(item, "signalIds"),
                    "sourceTableId": _clean_text(item.get("sourceTableId")),
                }
                for item in chart_candidates
                if _clean_text(item.get("chartId"))
            },
            "renderedAssets": {
                _clean_text(item.get("assetId")): {
                    "sourceIds": _trace_list(item, "sourceIds"),
                    "eventIds": _trace_list(item, "eventIds"),
                    "signalIds": _trace_list(item, "signalIds"),
                    "chartId": _clean_text(item.get("chartId")),
                    "sourceTableId": _clean_text(item.get("sourceTableId")),
                }
                for item in rendered_assets
                if _clean_text(item.get("assetId"))
            },
            "sections": {
                "opportunities": sorted(
                    {
                        source_id
                        for item in theme_sections
                        if str(item.get("type", "")).strip() == "opportunity"
                        for source_id in list(item.get("sourceIds") or [])
                    }
                ),
                "risks": sorted(
                    {
                        source_id
                        for item in theme_sections
                        if str(item.get("type", "")).strip() == "risk"
                        for source_id in list(item.get("sourceIds") or [])
                    }
                ),
                "visuals": sorted(
                    {
                        source_id
                        for item in visual_summaries
                        for source_id in list(item.get("sourceIds") or [])
                    }
                ),
            },
        }
    )


def _evidence_text(source: SourceDocument, events: list[InsightEvent]) -> str:
    for event in events:
        if event.evidence_sentence.strip():
            return _compact_text(event.evidence_sentence, limit=180)
    return _compact_text(source.content or source.title, limit=180)


def _metadata_only_note(metadata: dict[str, Any]) -> str:
    status = str(metadata.get("status") or metadata.get("parseStatus") or "")
    if status in {"metadata_limited", "metadata_only", "pending", "failed"}:
        message = metadata.get("errorMessage") or metadata.get("parseError") or "正文不可用，仅保留元数据。"
        return str(message)
    return ""

def _compact_text(value: str, *, limit: int) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _drop_empty(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _drop_empty(item)
            for key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_drop_empty(item) for item in value]
    return value


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _trace_list(item: dict[str, Any], key: str) -> list[str]:
    trace_refs = item.get("traceRefs") if isinstance(item.get("traceRefs"), dict) else {}
    values = trace_refs.get(key) if isinstance(trace_refs.get(key), list) else item.get(key, [])
    return [str(value).strip() for value in values if str(value or "").strip()]
