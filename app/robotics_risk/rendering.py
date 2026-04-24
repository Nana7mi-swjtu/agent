from __future__ import annotations

from typing import Any

from .reader import build_reader_packet, render_reader_brief
from .schemas import (
    AnalysisScope,
    EnterpriseProfile,
    InsightEvent,
    InsightSignal,
    RoboticsInsightResult,
    SourceDocument,
    SourceRetrievalDiagnostic,
)

MODULE_ID = "robotics_enterprise_risk_opportunity"


def build_result(
    *,
    target_company: dict,
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    opportunities: list[InsightSignal],
    risks: list[InsightSignal],
    events: list[InsightEvent],
    sources: list[SourceDocument],
    limitations: list[str],
    source_diagnostics: list[SourceRetrievalDiagnostic] | None = None,
    reader_writer: Any | None = None,
) -> RoboticsInsightResult:
    reader_packet = build_reader_packet(
        target_company=target_company,
        analysis_scope=analysis_scope,
        profile=profile,
        opportunities=opportunities,
        risks=risks,
        events=events,
        sources=sources,
        limitations=limitations,
    )
    summary = {
        "opportunity": reader_packet.executive_summary.get("opportunity", ""),
        "risk": reader_packet.executive_summary.get("risk", ""),
    }
    brief = render_reader_brief(
        target_company=target_company,
        analysis_scope=analysis_scope,
        profile=profile,
        reader_packet=reader_packet,
        reader_writer=reader_writer,
    )
    return RoboticsInsightResult(
        module=MODULE_ID,
        status="no_evidence" if not sources else "done",
        target_company=target_company,
        analysis_scope=analysis_scope,
        enterprise_profile=profile,
        summary=summary,
        opportunities=opportunities,
        risks=risks,
        events=events,
        sources=sources,
        limitations=limitations,
        brief_markdown=brief,
        reader_packet=reader_packet,
        source_diagnostics=list(source_diagnostics or []),
    )
