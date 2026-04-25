from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from .adapters import (
    BiddingProcurementAdapter,
    CninfoAnnouncementAdapter,
    EvidenceSourceAdapter,
    GovPolicyAdapter,
    SourceUnavailableError,
)
from .extraction import extract_events
from .profiling import build_enterprise_profile
from .rendering import build_result
from .schemas import AnalysisScope, RoboticsInsightRequest, RoboticsInsightResult, SourceDocument, SourceRetrievalDiagnostic
from .scoring import build_signals


class RoboticsInsightValidationError(ValueError):
    pass


def analyze_robotics_enterprise_risk_opportunity(
    request: RoboticsInsightRequest | dict[str, Any],
    *,
    adapters: Iterable[EvidenceSourceAdapter] | None = None,
    evidence_cache: Any | None = None,
    company_resolver: Any | None = None,
    reader_writer: Any | None = None,
) -> RoboticsInsightResult:
    normalized_request = _normalize_request(request)
    if not normalized_request.enterprise_name.strip():
        raise RoboticsInsightValidationError("enterprise_name is required")

    resolution = _resolve_company(normalized_request, evidence_cache=evidence_cache, company_resolver=company_resolver)
    if resolution is not None and resolution.supported and resolution.stock_code and not normalized_request.stock_code.strip():
        normalized_request = replace(normalized_request, stock_code=resolution.stock_code)

    analysis_scope = AnalysisScope(
        time_range=normalized_request.time_range or "近30天",
    )
    profile = build_enterprise_profile(normalized_request)
    if resolution is not None:
        profile.metadata.update(resolution.to_metadata())
        profile.limitations.extend(resolution.limitations)
        if resolution.profile is not None:
            profile.segments = _dedupe([*profile.segments, *resolution.profile.industry_segments])
            profile.keywords = _dedupe([*profile.keywords, *resolution.profile.robotics_keywords])
    documents, source_limitations, source_diagnostics = _collect_documents(
        request=normalized_request,
        profile=profile,
        adapters=list(adapters) if adapters is not None else _default_adapters(),
        evidence_cache=evidence_cache,
    )
    events = extract_events(documents)
    opportunities, risks = build_signals(events=events, sources=documents, profile=profile)
    limitations = [*profile.limitations, *source_limitations]
    if not documents:
        limitations.append("未检索到可用于风险机会洞察的来源文档。")
    if not events and documents:
        limitations.append("已获取来源文档，但未抽取到明确风险或机会事件。")

    return build_result(
        target_company=_target_company_payload(
            request=normalized_request,
            resolution=resolution,
        ),
        analysis_scope=analysis_scope,
        profile=profile,
        opportunities=opportunities,
        risks=risks,
        events=events,
        sources=documents,
        limitations=_dedupe(limitations),
        source_diagnostics=source_diagnostics,
        reader_writer=reader_writer,
    )


def _normalize_request(request: RoboticsInsightRequest | dict[str, Any]) -> RoboticsInsightRequest:
    if isinstance(request, RoboticsInsightRequest):
        return request
    if isinstance(request, dict):
        return RoboticsInsightRequest.from_dict(request)
    raise RoboticsInsightValidationError("request must be a RoboticsInsightRequest or dict")


def _default_adapters() -> list[EvidenceSourceAdapter]:
    return [
        GovPolicyAdapter(),
        CninfoAnnouncementAdapter(),
        BiddingProcurementAdapter(),
    ]


def _collect_documents(
    *,
    request: RoboticsInsightRequest,
    profile,
    adapters: list[EvidenceSourceAdapter],
    evidence_cache: Any | None = None,
) -> tuple[list[SourceDocument], list[str], list[SourceRetrievalDiagnostic]]:
    if evidence_cache is not None:
        try:
            result = evidence_cache.collect(request=request, profile=profile, adapters=adapters)
        except Exception as exc:
            return [], [f"机器人风险机会证据缓存不可用：{exc}"], [
                SourceRetrievalDiagnostic(
                    source_type="evidence_cache",
                    status="unavailable",
                    cache_decision="cache_bypass",
                    document_count=0,
                    failure_reason=str(exc),
                )
            ]
        return _dedupe_documents(result.documents), _dedupe(result.limitations), list(result.diagnostics)

    documents: list[SourceDocument] = []
    limitations: list[str] = []
    diagnostics: list[SourceRetrievalDiagnostic] = []
    for adapter in adapters:
        source_type = str(getattr(adapter, "source_type", "unknown"))
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            limitations.append(f"{exc.source_type}来源不可用：{exc}")
            diagnostics.append(
                SourceRetrievalDiagnostic(
                    source_type=exc.source_type,
                    status="unavailable",
                    cache_decision="cache_bypass",
                    document_count=0,
                    failure_reason=str(exc),
                )
            )
            continue
        except Exception as exc:
            limitations.append(f"{source_type}来源不可用：{exc}")
            diagnostics.append(
                SourceRetrievalDiagnostic(
                    source_type=source_type,
                    status="unavailable",
                    cache_decision="cache_bypass",
                    document_count=0,
                    failure_reason=str(exc),
                )
            )
            continue
        documents.extend(result.documents)
        limitations.extend(result.limitations)
        diagnostics.extend(result.diagnostics)
    return _dedupe_documents(documents), _dedupe(limitations), diagnostics


def _resolve_company(
    request: RoboticsInsightRequest,
    *,
    evidence_cache: Any | None,
    company_resolver: Any | None,
):
    resolver = company_resolver
    if resolver is None and evidence_cache is not None and hasattr(evidence_cache, "resolve_company"):
        resolver = evidence_cache
    if resolver is None:
        return None
    try:
        if hasattr(resolver, "resolve_company"):
            return resolver.resolve_company(request)
        return resolver.resolve(request.enterprise_name, stock_code=request.stock_code)
    except Exception as exc:
        return type(
            "_ResolutionFailure",
            (),
            {
                "supported": False,
                "stock_code": "",
                "profile": None,
                "limitations": [f"上市公司本地解析不可用：{exc}"],
                "to_metadata": lambda self: {"limitations": self.limitations, "matchType": "failed"},
            },
        )()


def _target_company_payload(*, request: RoboticsInsightRequest, resolution: Any | None) -> dict[str, Any]:
    payload = {
        "name": request.enterprise_name,
        "stockCode": request.stock_code,
    }
    if resolution is None:
        return payload
    metadata = resolution.to_metadata()
    for key in ("securityName", "companyName", "exchange", "market", "matchType", "confidence", "isSupported"):
        value = metadata.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


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


def _dedupe_documents(documents: list[SourceDocument]) -> list[SourceDocument]:
    seen: set[str] = set()
    result: list[SourceDocument] = []
    for document in documents:
        key = document.id or f"{document.source_type}:{document.title}:{document.url}"
        if key in seen:
            continue
        seen.add(key)
        result.append(document)
    return result
