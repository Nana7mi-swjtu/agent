from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .adapters import EvidenceSourceAdapter, SourceCollectionResult, SourceUnavailableError
from .repository import (
    SOURCE_BIDDING,
    SOURCE_CNINFO,
    SOURCE_POLICY,
    RoboticsEvidenceRepository,
    build_cache_key,
    rows_to_source_documents,
)
from .schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument


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
    ) -> None:
        self.repository = RoboticsEvidenceRepository(db)
        self._now_factory = now_factory or datetime.utcnow
        self._policies = {**DEFAULT_FRESHNESS_POLICIES, **(policies or {})}

    def collect(
        self,
        *,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
        adapters: Iterable[EvidenceSourceAdapter],
    ) -> SourceCollectionResult:
        documents: list[SourceDocument] = []
        limitations: list[str] = []
        for adapter in adapters:
            source_type = str(getattr(adapter, "source_type", "unknown"))
            if source_type not in self._policies:
                adapter_documents, adapter_limitations = self._collect_uncached_adapter(
                    adapter=adapter,
                    request=request,
                    profile=profile,
                )
                documents.extend(adapter_documents)
                limitations.extend(adapter_limitations)
                continue
            source_documents, source_limitations = self._collect_source(
                source_type=source_type,
                adapter=adapter,
                request=request,
                profile=profile,
            )
            documents.extend(source_documents)
            limitations.extend(source_limitations)
        return SourceCollectionResult(documents=documents, limitations=_dedupe(limitations))

    def _collect_source(
        self,
        *,
        source_type: str,
        adapter: EvidenceSourceAdapter,
        request: RoboticsInsightRequest,
        profile: EnterpriseProfile,
    ) -> tuple[list[SourceDocument], list[str]]:
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
            return rows_to_source_documents(fresh_rows), []

        negative_rows = self.repository.query_negative_records(source_type=source_type, cache_key=cache_key, now=now)
        if negative_rows and not cached_rows:
            return [], [_negative_limitation(source_type, negative_rows[0])]

        limitations: list[str] = []
        if cached_rows:
            limitations.append(f"{_source_label(source_type)}缓存已过期或覆盖不足，已尝试刷新。")
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            message = f"{exc.source_type}来源不可用：{exc}"
            self._record_negative(source_type, cache_key, "failed", message, now, policy.negative_ttl)
            return rows_to_source_documents(cached_rows), [*limitations, message]
        except Exception as exc:
            message = f"{source_type}来源不可用：{exc}"
            self._record_negative(source_type, cache_key, "failed", message, now, policy.negative_ttl)
            return rows_to_source_documents(cached_rows), [*limitations, message]

        limitations.extend(result.limitations)
        if not result.documents:
            message = result.limitations[0] if result.limitations else f"{_source_label(source_type)}未返回可用证据。"
            self._record_negative(source_type, cache_key, "empty", message, now, policy.negative_ttl)
            return rows_to_source_documents(cached_rows), limitations

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
        return rows_to_source_documents(rows), limitations

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
            return self.repository.query_policy_documents(
                cache_key=cache_key,
                keywords=profile.keywords,
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
            return self.repository.query_bidding_documents(
                cache_key=cache_key,
                request=request,
                keywords=profile.keywords,
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
    ) -> tuple[list[SourceDocument], list[str]]:
        source_type = str(getattr(adapter, "source_type", "unknown"))
        try:
            result = adapter.collect(request=request, profile=profile)
        except SourceUnavailableError as exc:
            return [], [f"{exc.source_type}来源不可用：{exc}"]
        except Exception as exc:
            return [], [f"{source_type}来源不可用：{exc}"]
        return result.documents, result.limitations


def _published_since(time_range: str, *, now: datetime) -> datetime | None:
    match = re.search(r"近\s*(\d+)\s*天", str(time_range or ""))
    if match:
        return now - timedelta(days=max(1, int(match.group(1))))
    return None


def _negative_limitation(source_type: str, row) -> str:
    error = str(getattr(row, "error_message", "") or "").strip()
    if error:
        return error
    return f"{_source_label(source_type)}近期不可用，已使用短期负缓存跳过重复请求。"


def _source_label(source_type: str) -> str:
    if source_type == SOURCE_POLICY:
        return "国务院政策文件库"
    if source_type == SOURCE_CNINFO:
        return "巨潮资讯网"
    if source_type == SOURCE_BIDDING:
        return "招中标/采购来源"
    return source_type


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result
