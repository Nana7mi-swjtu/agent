from __future__ import annotations

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
) -> RoboticsInsightResult:
    summary = {
        "opportunity": _summary_line(opportunities, "机会"),
        "risk": _summary_line(risks, "风险"),
    }
    brief = render_brief(
        target_company=target_company,
        analysis_scope=analysis_scope,
        profile=profile,
        opportunities=opportunities,
        risks=risks,
        limitations=limitations,
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
        source_diagnostics=list(source_diagnostics or []),
    )


def render_brief(
    *,
    target_company: dict,
    analysis_scope: AnalysisScope,
    profile: EnterpriseProfile,
    opportunities: list[InsightSignal],
    risks: list[InsightSignal],
    limitations: list[str],
) -> str:
    lines = [
        f"# {target_company.get('name', profile.name)}风险与机会洞察简报",
        "",
        "## 1. 分析对象",
        f"- 企业：{target_company.get('name', profile.name)}",
        f"- 行业：{profile.industry}",
        f"- 产业链画像：{', '.join(profile.segments)}",
        f"- 时间范围：{analysis_scope.time_range}",
        f"- 分析重点：{analysis_scope.focus}",
        "",
        "## 2. 机会信号",
        *_signal_lines(opportunities),
        "",
        "## 3. 风险信号",
        *_signal_lines(risks),
        "",
        "## 4. 来源与限制",
    ]
    if limitations:
        lines.extend(f"- {item}" for item in limitations)
    else:
        lines.append("- 暂无额外限制。")
    return "\n".join(lines).strip()


def _signal_lines(signals: list[InsightSignal]) -> list[str]:
    if not signals:
        return ["- 未发现高置信度信号。"]
    return [
        f"- {signal.title}：{signal.reasoning}（影响分 {signal.impact_score}，置信度 {signal.confidence:.2f}）"
        for signal in signals[:5]
    ]


def _summary_line(signals: list[InsightSignal], label: str) -> str:
    if not signals:
        return f"未发现明确{label}信号。"
    top = signals[0]
    return f"主要{label}集中在{top.category}，最高影响分为{top.impact_score}。"
