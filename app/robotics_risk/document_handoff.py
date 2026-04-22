from __future__ import annotations

from typing import Any

from .schemas import InsightEvent, InsightSignal, RoboticsInsightResult, SourceDocument

HANDOFF_SCHEMA_VERSION = "robotics_document_handoff.v1"
DOCUMENT_TYPE = "robotics_risk_opportunity_brief"


def build_document_handoff(result: RoboticsInsightResult) -> dict[str, Any]:
    opportunity_items = [_signal_entry(signal) for signal in result.opportunities]
    risk_items = [_signal_entry(signal) for signal in result.risks]
    evidence_rows = _evidence_rows(result.sources, result.events)
    citation_map = _citation_map(result.opportunities, result.risks, result.events)
    limitations = list(result.limitations)
    company_name = str(result.target_company.get("name") or result.enterprise_profile.name or "目标企业").strip()

    return _drop_empty(
        {
            "schemaVersion": HANDOFF_SCHEMA_VERSION,
            "documentType": DOCUMENT_TYPE,
            "recommendedFormat": "markdown",
            "title": f"{company_name}风险与机会洞察简报",
            "targetCompany": dict(result.target_company),
            "analysisScope": result.analysis_scope.to_dict(),
            "enterpriseProfile": result.enterprise_profile.to_dict(),
            "executiveSummary": {
                "opportunity": result.summary.get("opportunity", ""),
                "risk": result.summary.get("risk", ""),
                "sourceCount": len(result.sources),
                "eventCount": len(result.events),
                "limitationCount": len(limitations),
            },
            "recommendedSections": [
                {
                    "id": "executive_summary",
                    "order": 1,
                    "title": "执行摘要",
                    "content": [result.summary.get("opportunity", ""), result.summary.get("risk", "")],
                },
                {
                    "id": "opportunities",
                    "order": 2,
                    "title": "机会分析",
                    "items": opportunity_items,
                    "emptyState": "" if opportunity_items else "未发现高置信度机会信号。",
                },
                {
                    "id": "risks",
                    "order": 3,
                    "title": "风险分析",
                    "items": risk_items,
                    "emptyState": "" if risk_items else "未发现高置信度风险信号。",
                },
                {
                    "id": "evidence",
                    "order": 4,
                    "title": "证据与引用",
                    "items": evidence_rows,
                    "emptyState": "" if evidence_rows else "暂无可引用证据。",
                },
                {
                    "id": "limitations",
                    "order": 5,
                    "title": "限制说明",
                    "items": limitations or ["暂无额外限制。"],
                },
            ],
            "opportunitySections": opportunity_items,
            "riskSections": risk_items,
            "evidenceTable": evidence_rows,
            "citationMap": citation_map,
            "limitations": limitations,
            "sourceDiagnostics": [item.to_dict() for item in result.source_diagnostics],
            "compactMarkdown": _compact_markdown(result.brief_markdown),
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


def _citation_map(
    opportunities: list[InsightSignal],
    risks: list[InsightSignal],
    events: list[InsightEvent],
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
            "sections": {
                "opportunities": sorted({source_id for signal in opportunities for source_id in signal.source_ids}),
                "risks": sorted({source_id for signal in risks for source_id in signal.source_ids}),
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


def _compact_markdown(markdown: str) -> str:
    lines = [line.rstrip() for line in str(markdown or "").splitlines()]
    compact = "\n".join(line for line in lines if line.strip())
    return _compact_text(compact, limit=6000)


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
