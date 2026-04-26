from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .adapters import EvidenceSourceAdapter, SourceCollectionResult, SourceUnavailableError
from .bidding_planning import build_bidding_search_plan
from .company_resolution import CompanyResolutionResult, ListedCompanyResolver
from .company_seed import seed_robotics_listed_company_profiles
from .policy_planning import build_policy_search_plan
from .repository import (
    SOURCE_BIDDING,
    SOURCE_CNINFO,
    SOURCE_POLICY,
    RoboticsEvidenceRepository,
    build_cache_key,
    retrieval_strategy_version,
    rows_to_source_documents,
)
from .schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument, SourceRetrievalDiagnostic


@dataclass(frozen=True)
class SourceFreshnessPolicy:
    positive_ttl: timedelta
    negative_ttl: timedelta


DEFAULT_FRESHNESS_POLICIES: dict[str, SourceFreshnessPolicy] = {
    SOURCE_POLICY: SourceFreshnessPolicy(positive_ttl=timedelta(days=30), negative_ttl=timedelta(hours=2)),
    SOURCE_CNINFO: SourceFreshnessPolicy(positive_ttl=timedelta(hours=24), negative_ttl=timedelta(hours=1)),
    SOURCE_BIDDING: SourceFreshnessPolicy(positive_ttl=timedelta(days=3), negative_ttl=timedelta(hours=1)),
}


class RoboticsEvidenceCache:
    def __init__(
        self,
        db,
        *,
        now_factory: Callable[[], datetime] | None = None,
        policies: dict[str, SourceFreshnessPolicy] | None = None,
        seed_company_profiles: bool = True,
    ) -> None:
        self.repository = RoboticsEvidenceRepository(db)
        self._now_factory = now_factory or datetime.utcnow
        self._policies = {**DEFAULT_FRESHNESS_POLICIES, **(policies or {})}
        self._seed_company_profiles = bool(seed_company_profiles)
        self._company_profiles_seeded = False

    def resolve_company(self, request: RoboticsInsightRequest) -> CompanyResolutionResult:
        self._ensure_company_profiles_seeded()
        resolver = ListedCompanyResolver(self.repository)
        return resolver.resolve(request.enterprise_name, stock_code=request.stock_code)

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
        adapters: Iterable[EvidenceSourceAdapter],
    ) -> SourceCollectionResult:
        documents: list[SourceDocument] = []
        limitations: list[str] = []
        diagnostics: list[SourceRetrievalDiagnostic] = []
        for adapter in adapters:
            source_type = str(getattr(adapter, "source_type", "unknown"))
            if source_type not in self._policies:
                adapter_documents, adapter_limitations, adapter_diagnostics = self._collect_uncached_adapter(
                    adapter=adapter,
                    request=request,
                    profile=profile,
                )
                documents.extend(adapter_documents)
                limitations.extend(adapter_limitations)
                diagnostics.extend(adapter_diagnostics)
                continue
            source_documents, source_limitations, source_diagnostics = self._collect_source(
                source_type=source_type,
                adapter=adapter,
                request=request,
                profile=profile,
            )
            documents.extend(source_documents)
            limitations.extend(source_limitations)
            diagnostics.extend(source_diagnostics)
        return SourceCollectionResult(documents=documents, limitations=_dedupe(limitations), diagnostics=diagnostics)

    def _collect_source(
        self,
        *,
        source_type: str,
        adapter: EvidenceSourceAdapter,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> tuple[list[SourceDocument], list[str], list[SourceRetrievalDiagnostic]]:
        now = self._now_factory()
        policy = self._policies[source_type]
        cache_key = build_cache_key(source_type=source_type, request=request, profile=profile)
        published_since = _published_since(request.time_range, now=now)
        cached_rows = self._query_rows(
            source_type=source_type,
            cache_key=cache_key,
            request=request,
            profile=profile,
            published_since=published_since,
        )
        fresh_rows = [row for row in cached_rows if self._row_is_fresh(row, now=now, ttl=policy.positive_ttl)]
        if fresh_rows:
            documents = rows_to_source_documents(fresh_rows)
            return documents, [], [
                _diagnostic(
                    source_type=source_type,
                    status="done",
                    cache_decision="fresh_hit",
                    document_count=len(documents),
                    raw_count=len(fresh_rows),
                    filtered_count=len(fresh_rows),
                )
            ]

        negative_rows = self.repository.query_negative_records(source_type=source_type, cache_key=cache_key, now=now)
        if negative_rows and not cached_rows:
            row = negative_rows[0]
            status = "empty" if getattr(row, "status", "") == "empty" else "unavailable"
            return [], [_negative_limitation(source_type, row)], [
                _diagnostic(
                    source_type=source_type,
                    status=status,
                    cache_decision="negative_hit",
                    document_count=0,
                    failure_reason=str(getattr(row, "error_message", "") or ""),
                )
            ]

        limitations: list[str] = []
        if cached_rows:
            limitations.append(f"{_source_label(source_type)}缓存已过期或覆盖不足，已尝试刷新。")
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            message = f"{exc.source_type}来源不可用：{exc}"
            self._record_negative(source_type, cache_key, "failed", message, now, policy.negative_ttl)
            documents = rows_to_source_documents(cached_rows)
            return documents, [*limitations, message], [
                _diagnostic(
                    source_type=source_type,
                    status="unavailable",
                    cache_decision="stale_refresh" if cached_rows else "live_fetch",
                    document_count=len(documents),
                    failure_reason=message,
                )
            ]
        except Exception as exc:
            message = f"{source_type}来源不可用：{exc}"
            self._record_negative(source_type, cache_key, "failed", message, now, policy.negative_ttl)
            documents = rows_to_source_documents(cached_rows)
            return documents, [*limitations, message], [
                _diagnostic(
                    source_type=source_type,
                    status="unavailable",
                    cache_decision="stale_refresh" if cached_rows else "live_fetch",
                    document_count=len(documents),
                    failure_reason=message,
                )
            ]

        limitations.extend(result.limitations)
        cache_decision = "stale_refresh" if cached_rows else "live_fetch"
        if not result.documents:
            message = _empty_result_message(source_type, result.limitations)
            self._record_negative(source_type, cache_key, "empty", message, now, policy.negative_ttl)
            documents = rows_to_source_documents(cached_rows)
            return documents, limitations, _diagnostics_with_cache_decision(
                result.diagnostics,
                source_type=source_type,
                cache_decision=cache_decision,
                fallback_status="empty" if not documents else "partial",
                document_count=len(documents),
                failure_reason=message,
            )

        rows = []
        expires_at = now + policy.positive_ttl
        for document in result.documents:
            rows.append(
                self.repository.upsert_source_document(
                    document,
                    cache_key=cache_key,
                    fetched_at=now,
                    expires_at=expires_at,
                )
            )
        documents = rows_to_source_documents(rows)
        return documents, limitations, _diagnostics_with_cache_decision(
            result.diagnostics,
            source_type=source_type,
            cache_decision=cache_decision,
            fallback_status="done",
            document_count=len(documents),
        )

    def _query_rows(
        self,
        *,
        source_type: str,
        cache_key: str,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
        published_since: datetime | None,
    ):
        if source_type == SOURCE_POLICY:
            plan = build_policy_search_plan(request=request, profile=profile)
            return self.repository.query_policy_documents(
                cache_key=cache_key,
                source_scopes=list(plan.source_scopes),
                matched_segments=profile.segments,
                policy_domains=[
                    item.policy_domain for item in plan.query_terms if item.policy_domain
                ],
                published_since=published_since,
            )
        if source_type == SOURCE_CNINFO:
            return self.repository.query_cninfo_announcements(
                cache_key=cache_key,
                request=request,
                keywords=profile.keywords,
                published_since=published_since,
            )
        if source_type == SOURCE_BIDDING:
            plan = build_bidding_search_plan(request=request, profile=profile)
            return self.repository.query_bidding_documents(
                cache_key=cache_key,
                request=request,
                keywords=_dedupe([*profile.keywords, *plan.keywords]),
                notice_categories=list(plan.notice_categories),
                regions=list(plan.region_hints),
                matched_enterprises=_dedupe([request.enterprise_name, profile.name]),
                published_since=published_since,
            )
        return []

    def _record_negative(
        self,
        source_type: str,
        cache_key: str,
        status: str,
        message: str,
        now: datetime,
        ttl: timedelta,
    ) -> None:
        self.repository.record_source_state(
            source_type=source_type,
            cache_key=cache_key,
            status=status,
            message=message,
            fetched_at=now,
            expires_at=now + ttl,
        )

    def _row_is_fresh(self, row, *, now: datetime, ttl: timedelta) -> bool:
        if getattr(row, "status", "") in {"failed", "empty"}:
            return False
        expires_at = getattr(row, "expires_at", None)
        if expires_at is not None:
            return expires_at > now
        fetched_at = getattr(row, "fetched_at", None)
        return fetched_at is not None and fetched_at >= now - ttl

    def _collect_uncached_adapter(
        self,
        *,
        adapter: EvidenceSourceAdapter,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> tuple[list[SourceDocument], list[str], list[SourceRetrievalDiagnostic]]:
        source_type = str(getattr(adapter, "source_type", "unknown"))
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            message = f"{exc.source_type}来源不可用：{exc}"
            return [], [message], [_diagnostic(source_type=exc.source_type, status="unavailable", cache_decision="cache_bypass", failure_reason=message)]
        except Exception as exc:
            message = f"{source_type}来源不可用：{exc}"
            return [], [message], [_diagnostic(source_type=source_type, status="unavailable", cache_decision="cache_bypass", failure_reason=message)]
        return result.documents, result.limitations, _diagnostics_with_cache_decision(
            result.diagnostics,
            source_type=source_type,
            cache_decision="cache_bypass",
            fallback_status="done" if result.documents else "empty",
            document_count=len(result.documents),
        )

    def _ensure_company_profiles_seeded(self) -> None:
        if not self._seed_company_profiles or self._company_profiles_seeded:
            return
        seed_robotics_listed_company_profiles(self.repository)
        self._company_profiles_seeded = True


def _published_since(time_range: str, *, now: datetime) -> datetime | None:
    match = re.search(r"近\s*(\d+)\s*天", str(time_range or ""))
    if match:
        return now - timedelta(days=max(1, int(match.group(1))))
    return None


def _negative_limitation(source_type: str, row) -> str:
    error = str(getattr(row, "error_message", "") or "").strip()
    status = str(getattr(row, "status", "") or "").strip()
    if error and status == "empty":
        return f"{_source_label(source_type)}未返回可用证据：{error}"
    if error:
        return error
    if status == "empty":
        return f"{_source_label(source_type)}未返回可用证据，已使用短期负缓存跳过重复请求。"
    return f"{_source_label(source_type)}近期不可用，已使用短期负缓存跳过重复请求。"


def _empty_result_message(source_type: str, limitations: list[str]) -> str:
    for limitation in limitations:
        if any(marker in limitation for marker in ("未返回", "不可用", "失败", "反爬", "验证码")):
            return limitation
    if limitations:
        return limitations[-1]
    return f"{_source_label(source_type)}未返回可用证据。"


def _source_label(source_type: str) -> str:
    if source_type == SOURCE_POLICY:
        return "国务院政策文件库"
    if source_type == SOURCE_CNINFO:
        return "巨潮资讯网"
    if source_type == SOURCE_BIDDING:
        return "中国招标投标公共服务平台"
    return source_type


def _diagnostic(
    *,
    source_type: str,
    status: str,
    cache_decision: str,
    document_count: int = 0,
    raw_count: int | None = None,
    filtered_count: int | None = None,
    failure_reason: str = "",
) -> SourceRetrievalDiagnostic:
    return SourceRetrievalDiagnostic(
        source_type=source_type,
        status=status,
        query_strategy=retrieval_strategy_version(source_type),
        cache_decision=cache_decision,
        raw_count=raw_count,
        filtered_count=filtered_count,
        document_count=document_count,
        failure_reason=failure_reason,
    )


def _diagnostics_with_cache_decision(
    diagnostics: list[SourceRetrievalDiagnostic],
    *,
    source_type: str,
    cache_decision: str,
    fallback_status: str,
    document_count: int,
    failure_reason: str = "",
) -> list[SourceRetrievalDiagnostic]:
    if not diagnostics:
        return [
            _diagnostic(
                source_type=source_type,
                status=fallback_status,
                cache_decision=cache_decision,
                document_count=document_count,
                failure_reason=failure_reason,
            )
        ]
    result: list[SourceRetrievalDiagnostic] = []
    for item in diagnostics:
        result.append(
            SourceRetrievalDiagnostic(
                source_type=item.source_type or source_type,
                status=item.status or fallback_status,
                query_strategy=item.query_strategy or retrieval_strategy_version(source_type),
                cache_decision=cache_decision,
                raw_count=item.raw_count,
                filtered_count=item.filtered_count,
                document_count=item.document_count if item.document_count is not None else document_count,
                failure_reason=item.failure_reason or failure_reason,
                started_at=item.started_at,
                completed_at=item.completed_at,
                metadata=dict(item.metadata or {}),
            )
        )
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
