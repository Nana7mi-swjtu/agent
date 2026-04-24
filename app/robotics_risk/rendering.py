from __future__ import annotations

from typing import Any

from .reader import build_reader_packet, render_reader_brief
from .tabular_artifacts import build_robotics_tabular_artifacts
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
    fact_tables, chart_candidates, rendered_assets = build_robotics_tabular_artifacts(
        target_company=target_company,
        analysis_scope=analysis_scope,
        profile=profile,
        reader_packet=reader_packet,
        events=events,
        sources=sources,
        limitations=limitations,
    )
    reader_packet.fact_table_refs = [str(item.get("tableId")) for item in fact_tables if isinstance(item, dict) and item.get("tableId")]
    reader_packet.chart_candidate_refs = [
        str(item.get("chartId")) for item in chart_candidates if isinstance(item, dict) and item.get("chartId")
    ]
    reader_packet.rendered_asset_refs = [
        str(item.get("assetId")) for item in rendered_assets if isinstance(item, dict) and item.get("assetId")
    ]
    reader_packet.interpretation_boundaries = [
        str(item.get("interpretationBoundary"))
        for item in [*chart_candidates, *rendered_assets]
        if isinstance(item, dict) and str(item.get("interpretationBoundary") or "").strip()
    ]
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
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
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
        fact_tables=fact_tables,
        chart_candidates=chart_candidates,
        rendered_assets=rendered_assets,
        source_diagnostics=list(source_diagnostics or []),
    )
