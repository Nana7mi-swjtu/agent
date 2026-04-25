from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from app.models import (
    RoboticsBiddingDocument,
    RoboticsCninfoAnnouncement,
    RoboticsListedCompanyProfile,
    RoboticsPolicyDocument,
)

from .pdf_text import PdfTextExtractionResult
from .schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument

SOURCE_POLICY = "gov_policy"
SOURCE_CNINFO = "cninfo_announcement"
SOURCE_BIDDING = "bidding_procurement"
NEGATIVE_STATUSES = {"failed", "empty"}
RETRIEVAL_STRATEGY_VERSIONS = {
    SOURCE_POLICY: "gov_policy.json_list.v1",
    SOURCE_CNINFO: "cninfo.multi_strategy.v1",
    SOURCE_BIDDING: "cebpubservice.live_entrypoint.v1",
}


def build_cache_key(
    *,
    source_type: str,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
) -> str:
    parts = [
        source_type,
        retrieval_strategy_version(source_type),
        request.enterprise_name.strip(),
        request.stock_code.strip(),
        request.time_range.strip(),
        "|".join(sorted(_clean_values(profile.keywords))),
    ]
    return _hash_text("\n".join(parts))


def retrieval_strategy_version(source_type: str) -> str:
    return RETRIEVAL_STRATEGY_VERSIONS.get(source_type, f"{source_type}.default.v1")


class RoboticsEvidenceRepository:
    def __init__(self, db) -> None:
        self.db = db

    def query_policy_documents(
        self,
        *,
        cache_key: str,
        source_scopes: list[str] | None = None,
        matched_segments: list[str] | None = None,
        policy_domains: list[str] | None = None,
        published_since: datetime | None,
    ) -> list[RoboticsPolicyDocument]:
        stmt = select(RoboticsPolicyDocument).where(RoboticsPolicyDocument.status.notin_(NEGATIVE_STATUSES))
        stmt = stmt.where(RoboticsPolicyDocument.cache_key == cache_key)
        if published_since is not None:
            stmt = stmt.where(
                or_(
                    RoboticsPolicyDocument.published_at.is_(None),
                    RoboticsPolicyDocument.published_at >= published_since,
                )
            )
        rows = list(self.db.execute(stmt.order_by(RoboticsPolicyDocument.published_at.desc())).scalars().all())
        return [
            row
            for row in rows
            if _policy_row_matches_metadata(
                row,
                source_scopes=source_scopes or [],
                matched_segments=matched_segments or [],
                policy_domains=policy_domains or [],
            )
        ]

    def query_cninfo_announcements(
        self,
        *,
        cache_key: str,
        request: RoboticsInsightRequest,
        keywords: list[str],
        published_since: datetime | None,
    ) -> list[RoboticsCninfoAnnouncement]:
        stmt = select(RoboticsCninfoAnnouncement).where(RoboticsCninfoAnnouncement.status.notin_(NEGATIVE_STATUSES))
        stmt = stmt.where(_cninfo_lookup_filter(cache_key=cache_key, request=request, keywords=keywords))
        if published_since is not None:
            stmt = stmt.where(
                or_(
                    RoboticsCninfoAnnouncement.announcement_time.is_(None),
                    RoboticsCninfoAnnouncement.announcement_time >= published_since,
                )
            )
        return list(self.db.execute(stmt.order_by(RoboticsCninfoAnnouncement.announcement_time.desc())).scalars().all())

    def query_bidding_documents(
        self,
        *,
        cache_key: str,
        request: RoboticsInsightRequest,
        keywords: list[str],
        notice_categories: list[str] | None = None,
        regions: list[str] | None = None,
        matched_enterprises: list[str] | None = None,
        published_since: datetime | None,
    ) -> list[RoboticsBiddingDocument]:
        stmt = select(RoboticsBiddingDocument).where(RoboticsBiddingDocument.status.notin_(NEGATIVE_STATUSES))
        stmt = stmt.where(_bidding_lookup_filter(cache_key=cache_key, request=request, keywords=keywords))
        if published_since is not None:
            stmt = stmt.where(
                or_(
                    RoboticsBiddingDocument.published_at.is_(None),
                    RoboticsBiddingDocument.published_at >= published_since,
                )
            )
        rows = list(self.db.execute(stmt.order_by(RoboticsBiddingDocument.published_at.desc())).scalars().all())
        return [
            row
            for row in rows
            if _bidding_row_matches_metadata(
                row,
                notice_categories=notice_categories or [],
                regions=regions or [],
                matched_enterprises=matched_enterprises or [],
            )
        ]

    def query_negative_records(self, *, source_type: str, cache_key: str, now: datetime) -> list[Any]:
        model = _model_for_source(source_type)
        stmt = (
            select(model)
            .where(model.cache_key == cache_key)
            .where(model.status.in_(NEGATIVE_STATUSES))
            .where(or_(model.expires_at.is_(None), model.expires_at > now))
        )
        return list(self.db.execute(stmt.order_by(model.fetched_at.desc())).scalars().all())

    def upsert_source_document(
        self,
        document: SourceDocument,
        *,
        cache_key: str,
        fetched_at: datetime,
        expires_at: datetime | None,
    ) -> Any:
        if document.source_type == SOURCE_POLICY:
            return self.upsert_policy_document(document, cache_key=cache_key, fetched_at=fetched_at, expires_at=expires_at)
        if document.source_type == SOURCE_CNINFO:
            return self.upsert_cninfo_announcement(document, cache_key=cache_key, fetched_at=fetched_at, expires_at=expires_at)
        if document.source_type == SOURCE_BIDDING:
            return self.upsert_bidding_document(document, cache_key=cache_key, fetched_at=fetched_at, expires_at=expires_at)
        raise ValueError(f"unsupported robotics evidence source type: {document.source_type}")

    def record_source_state(
        self,
        *,
        source_type: str,
        cache_key: str,
        status: str,
        message: str,
        fetched_at: datetime,
        expires_at: datetime | None,
    ) -> Any:
        synthetic = SourceDocument(
            id=f"{source_type}:negative:{cache_key}",
            source_type=source_type,
            source_name=_source_name(source_type),
            title="来源暂无可用证据" if status == "empty" else "来源不可用",
            content="",
            metadata={"status": status, "errorMessage": message, "retrievalStrategy": retrieval_strategy_version(source_type)},
        )
        return self.upsert_source_document(synthetic, cache_key=cache_key, fetched_at=fetched_at, expires_at=expires_at)

    def persist_cninfo_pdf_result(
        self,
        *,
        announcement_id: str,
        title: str,
        pdf_url: str,
        result: PdfTextExtractionResult,
        cache_key: str = "",
        fetched_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> RoboticsCninfoAnnouncement:
        now = fetched_at or datetime.utcnow()
        document = SourceDocument(
            id=f"cninfo:{announcement_id}",
            source_type=SOURCE_CNINFO,
            source_name="巨潮资讯网",
            title=title,
            content=result.text,
            url=pdf_url,
            authority_score=0.95,
            relevance_scope="enterprise",
            metadata={
                "announcementId": announcement_id,
                "pdfUrl": pdf_url,
                "pageCount": result.page_count,
                "extractionMethod": result.extraction_method,
                "ocrUsed": result.ocr_used,
                "ocrProvider": result.ocr_provider,
                "parseStatus": result.parse_status,
                "parseError": result.parse_error,
                "status": "parsed" if result.succeeded else "failed",
                "errorMessage": result.parse_error,
            },
        )
        return self.upsert_cninfo_announcement(
            document,
            cache_key=cache_key,
            fetched_at=now,
            expires_at=expires_at,
        )

    def upsert_policy_document(
        self,
        document: SourceDocument,
        *,
        cache_key: str,
        fetched_at: datetime,
        expires_at: datetime | None,
    ) -> RoboticsPolicyDocument:
        metadata = dict(document.metadata or {})
        metadata.setdefault("retrievalStrategy", retrieval_strategy_version(SOURCE_POLICY))
        policy_id = _first_text(metadata, "policyId", "policy_id", "sourceDocumentId") or _stable_id(
            prefix="policy",
            document=document,
        )
        row = _one_or_none(self.db, select(RoboticsPolicyDocument).where(RoboticsPolicyDocument.policy_id == policy_id))
        if row is None:
            row = RoboticsPolicyDocument(policy_id=policy_id, title=document.title or "未命名政策")
            self.db.add(row)
        row.cache_key = cache_key
        row.title = document.title or row.title
        row.url = document.url or row.url
        row.url_hash = _hash_text(document.url) if document.url else row.url_hash
        row.issuing_agency = _first_text(metadata, "issuingAgency", "issuing_agency")
        row.document_number = _first_text(metadata, "documentNumber", "document_number")
        row.published_at = _parse_datetime(document.published_at)
        row.fetched_at = fetched_at
        row.expires_at = expires_at
        if document.content:
            row.content_text = document.content
            row.content_hash = _hash_text(document.content)
        row.matched_keywords_json = {"keywords": _clean_values(metadata.get("matchedKeywords") or [])}
        row.relevance_segments_json = {
            "segments": _clean_values(
                metadata.get("relevanceSegments")
                or metadata.get("matchedSegments")
                or []
            )
        }
        row.metadata_json = metadata
        row.status = str(metadata.get("status") or "fetched")
        row.error_message = _first_text(metadata, "errorMessage", "error_message")
        self.db.flush()
        return row

    def upsert_cninfo_announcement(
        self,
        document: SourceDocument,
        *,
        cache_key: str,
        fetched_at: datetime,
        expires_at: datetime | None,
    ) -> RoboticsCninfoAnnouncement:
        metadata = dict(document.metadata or {})
        metadata.setdefault("retrievalStrategy", retrieval_strategy_version(SOURCE_CNINFO))
        announcement_id = _first_text(metadata, "announcementId", "announcement_id", "sourceDocumentId") or _stable_id(
            prefix="cninfo",
            document=document,
        )
        row = _one_or_none(
            self.db,
            select(RoboticsCninfoAnnouncement).where(RoboticsCninfoAnnouncement.announcement_id == announcement_id),
        )
        if row is None:
            row = RoboticsCninfoAnnouncement(announcement_id=announcement_id, title=document.title or "未命名公告")
            self.db.add(row)
        adjunct_url = _first_text(metadata, "adjunctUrl", "adjunct_url")
        pdf_url = _first_text(metadata, "pdfUrl", "pdf_url") or document.url
        row.cache_key = cache_key
        row.sec_code = _first_text(metadata, "secCode", "sec_code", "stockCode")
        row.sec_name = _first_text(metadata, "secName", "sec_name")
        row.org_id = _first_text(metadata, "orgId", "org_id")
        row.title = document.title or row.title
        row.announcement_type = _first_text(metadata, "announcementType", "announcement_type")
        row.announcement_time = _parse_datetime(document.published_at) or _parse_datetime(
            _first_text(metadata, "announcementTime", "announcement_time")
        )
        row.adjunct_url = adjunct_url
        row.adjunct_url_hash = _hash_text(adjunct_url) if adjunct_url else row.adjunct_url_hash
        row.pdf_url = pdf_url
        row.pdf_url_hash = _hash_text(pdf_url) if pdf_url else row.pdf_url_hash
        row.pdf_storage_path = _first_text(metadata, "pdfStoragePath", "pdf_storage_path")
        row.fetched_at = fetched_at
        row.expires_at = expires_at
        row.content_text = document.content
        row.content_hash = _hash_text(document.content) if document.content else row.content_hash
        row.matched_keywords_json = {"keywords": _clean_values(metadata.get("matchedKeywords") or [])}
        row.metadata_json = metadata
        row.status = str(metadata.get("status") or ("parsed" if document.content else row.status or "fetched"))
        row.error_message = _first_text(metadata, "errorMessage", "error_message")
        row.page_count = _coerce_int(metadata.get("pageCount") or metadata.get("page_count")) or row.page_count
        row.extraction_method = _first_text(metadata, "extractionMethod", "extraction_method") or row.extraction_method
        row.ocr_used = 1 if bool(metadata.get("ocrUsed") or metadata.get("ocr_used")) else row.ocr_used
        row.parse_status = (
            _first_text(metadata, "parseStatus", "parse_status")
            or ("parsed" if document.content else row.parse_status or "pending")
        )
        row.parse_error = _first_text(metadata, "parseError", "parse_error") or row.parse_error
        self.db.flush()
        return row

    def upsert_bidding_document(
        self,
        document: SourceDocument,
        *,
        cache_key: str,
        fetched_at: datetime,
        expires_at: datetime | None,
    ) -> RoboticsBiddingDocument:
        metadata = dict(document.metadata or {})
        metadata.setdefault("retrievalStrategy", retrieval_strategy_version(SOURCE_BIDDING))
        notice_id = _first_text(metadata, "noticeId", "notice_id", "sourceDocumentId") or _stable_id(
            prefix="bidding",
            document=document,
        )
        row = _one_or_none(self.db, select(RoboticsBiddingDocument).where(RoboticsBiddingDocument.notice_id == notice_id))
        if row is None:
            row = RoboticsBiddingDocument(notice_id=notice_id, title=document.title or "未命名招采公告")
            self.db.add(row)
        row.cache_key = cache_key
        row.title = document.title or row.title
        row.url = document.url or row.url
        row.url_hash = _hash_text(document.url) if document.url else row.url_hash
        row.notice_type = _first_text(metadata, "noticeType", "notice_type")
        row.project_name = _first_text(metadata, "projectName", "project_name")
        row.project_code = _first_text(metadata, "projectCode", "project_code")
        row.buyer_name = _first_text(metadata, "buyerName", "buyer_name")
        row.winning_bidder = _first_text(metadata, "winningBidder", "winning_bidder")
        row.amount = _first_text(metadata, "amount")
        row.currency = _first_text(metadata, "currency")
        row.region = _first_text(metadata, "region")
        row.published_at = _parse_datetime(document.published_at)
        row.fetched_at = fetched_at
        row.expires_at = expires_at
        row.content_text = document.content
        row.content_hash = _hash_text(document.content) if document.content else row.content_hash
        row.matched_enterprise_name = _first_text(metadata, "matchedEnterpriseName", "matched_enterprise_name")
        row.matched_keywords_json = {"keywords": _clean_values(metadata.get("matchedKeywords") or [])}
        row.metadata_json = metadata
        row.status = str(metadata.get("status") or "fetched")
        row.error_message = _first_text(metadata, "errorMessage", "error_message")
        self.db.flush()
        return row

    def upsert_listed_company_profile(self, payload: dict[str, Any]) -> RoboticsListedCompanyProfile:
        profile_key = _profile_key(payload)
        stock_code = _normalize_stock_code(_payload_text(payload, "stock_code", "stockCode"))
        row = _one_or_none(
            self.db,
            select(RoboticsListedCompanyProfile).where(RoboticsListedCompanyProfile.profile_key == profile_key),
        )
        if row is None and stock_code:
            row = _one_or_none(
                self.db,
                select(RoboticsListedCompanyProfile).where(RoboticsListedCompanyProfile.stock_code == stock_code),
            )
        if row is None:
            row = RoboticsListedCompanyProfile(
                profile_key=profile_key,
                company_name=str(payload.get("company_name") or payload.get("companyName") or "").strip(),
            )
            self.db.add(row)

        row.stock_code = stock_code or row.stock_code
        row.exchange = _payload_text(payload, "exchange") or row.exchange
        row.market = _payload_text(payload, "market") or row.market
        row.security_name = _payload_text(payload, "security_name", "securityName") or row.security_name
        row.company_name = _payload_text(payload, "company_name", "companyName") or row.company_name
        row.aliases_json = {"aliases": _clean_values(payload.get("aliases") or [])}
        row.industry_segments_json = {"segments": _clean_values(payload.get("industry_segments") or payload.get("industrySegments") or [])}
        row.robotics_keywords_json = {"keywords": _clean_values(payload.get("robotics_keywords") or payload.get("roboticsKeywords") or [])}
        row.cninfo_column = _payload_text(payload, "cninfo_column", "cninfoColumn") or row.cninfo_column
        row.cninfo_org_id = _payload_text(payload, "cninfo_org_id", "cninfoOrgId") or row.cninfo_org_id
        row.is_supported = 1 if bool(payload.get("is_supported", payload.get("isSupported", True))) else 0
        row.unsupported_reason = _payload_text(payload, "unsupported_reason", "unsupportedReason")
        row.source = _payload_text(payload, "source") or row.source
        row.metadata_json = dict(payload.get("metadata") or payload.get("metadata_json") or {})
        self.db.flush()
        return row

    def get_listed_company_profile_by_stock_code(self, stock_code: str) -> RoboticsListedCompanyProfile | None:
        clean = _normalize_stock_code(stock_code)
        if not clean:
            return None
        stmt = select(RoboticsListedCompanyProfile).where(RoboticsListedCompanyProfile.stock_code == clean)
        return _one_or_none(self.db, stmt)

    def list_listed_company_profiles(self) -> list[RoboticsListedCompanyProfile]:
        stmt = select(RoboticsListedCompanyProfile).order_by(
            RoboticsListedCompanyProfile.is_supported.desc(),
            RoboticsListedCompanyProfile.stock_code.asc(),
            RoboticsListedCompanyProfile.company_name.asc(),
        )
        return list(self.db.execute(stmt).scalars().all())


def rows_to_source_documents(rows: list[Any]) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for row in rows:
        if isinstance(row, RoboticsPolicyDocument):
            documents.append(policy_row_to_source_document(row))
        elif isinstance(row, RoboticsCninfoAnnouncement):
            documents.append(cninfo_row_to_source_document(row))
        elif isinstance(row, RoboticsBiddingDocument):
            documents.append(bidding_row_to_source_document(row))
    return documents


def policy_row_to_source_document(row: RoboticsPolicyDocument) -> SourceDocument:
    metadata = dict(row.metadata_json or {})
    metadata.update(
        {
            "policyId": row.policy_id,
            "cacheKey": row.cache_key,
            "issuingAgency": row.issuing_agency,
            "documentNumber": row.document_number,
            "matchedKeywords": (row.matched_keywords_json or {}).get("keywords", []),
            "relevanceSegments": (row.relevance_segments_json or {}).get("segments", []),
            "fetchedAt": _format_datetime(row.fetched_at),
            "expiresAt": _format_datetime(row.expires_at),
            "status": row.status,
        }
    )
    return SourceDocument(
        id=f"policy:{row.policy_id}",
        source_type=SOURCE_POLICY,
        source_name="国务院政策文件库",
        title=row.title,
        content=row.content_text or "",
        url=row.url or "",
        published_at=_format_datetime(row.published_at),
        authority_score=0.95,
        relevance_scope="industry",
        metadata=metadata,
    )


def cninfo_row_to_source_document(row: RoboticsCninfoAnnouncement) -> SourceDocument:
    metadata = dict(row.metadata_json or {})
    metadata.update(
        {
            "announcementId": row.announcement_id,
            "cacheKey": row.cache_key,
            "secCode": row.sec_code,
            "secName": row.sec_name,
            "adjunctUrl": row.adjunct_url,
            "pdfUrl": row.pdf_url,
            "fetchedAt": _format_datetime(row.fetched_at),
            "expiresAt": _format_datetime(row.expires_at),
            "pageCount": row.page_count,
            "extractionMethod": row.extraction_method,
            "ocrUsed": bool(row.ocr_used),
            "parseStatus": row.parse_status,
            "parseError": row.parse_error,
            "status": row.status,
        }
    )
    return SourceDocument(
        id=f"cninfo:{row.announcement_id}",
        source_type=SOURCE_CNINFO,
        source_name="巨潮资讯网",
        title=row.title,
        content=row.content_text or row.title,
        url=row.pdf_url or row.adjunct_url or "",
        published_at=_format_datetime(row.announcement_time),
        authority_score=0.95,
        relevance_scope="enterprise",
        metadata=metadata,
    )


def bidding_row_to_source_document(row: RoboticsBiddingDocument) -> SourceDocument:
    metadata = dict(row.metadata_json or {})
    relevance_scope = str(metadata.get("relevanceScope") or metadata.get("inferenceLevel") or "").strip()
    if relevance_scope == "direct":
        relevance_scope = "enterprise"
    if relevance_scope not in {"enterprise", "market_demand", "industry"}:
        relevance_scope = "enterprise" if row.matched_enterprise_name else "market_demand"
    metadata.update(
        {
            "noticeId": row.notice_id,
            "cacheKey": row.cache_key,
            "noticeType": row.notice_type,
            "projectName": row.project_name,
            "projectCode": row.project_code,
            "buyerName": row.buyer_name,
            "winningBidder": row.winning_bidder,
            "amount": row.amount,
            "currency": row.currency,
            "region": row.region,
            "matchedEnterpriseName": row.matched_enterprise_name,
            "matchedKeywords": (row.matched_keywords_json or {}).get("keywords", []),
            "fetchedAt": _format_datetime(row.fetched_at),
            "expiresAt": _format_datetime(row.expires_at),
            "status": row.status,
        }
    )
    return SourceDocument(
        id=f"bidding:{row.notice_id}",
        source_type=SOURCE_BIDDING,
        source_name="中国招标投标公共服务平台",
        title=row.title,
        content=row.content_text or row.title,
        url=row.url or "",
        published_at=_format_datetime(row.published_at),
        authority_score=0.9 if relevance_scope == "enterprise" else 0.82,
        relevance_scope=relevance_scope,
        metadata=metadata,
    )


def _policy_row_matches_metadata(
    row: RoboticsPolicyDocument,
    *,
    source_scopes: list[str],
    matched_segments: list[str],
    policy_domains: list[str],
) -> bool:
    metadata = dict(row.metadata_json or {})
    if source_scopes:
        scope = str(metadata.get("sourceScope") or "").strip()
        if scope and scope not in set(source_scopes):
            return False
    wanted_segments = set(_clean_values(matched_segments))
    if wanted_segments:
        row_segments = set(
            _clean_values(
                (row.relevance_segments_json or {}).get("segments", [])
                or metadata.get("matchedSegments")
                or metadata.get("relevanceSegments")
                or []
            )
        )
        if row_segments and row_segments.isdisjoint(wanted_segments):
            return False
    wanted_domains = set(_clean_values(policy_domains))
    if wanted_domains:
        row_domains = set(_clean_values(metadata.get("matchedPolicyDomains") or []))
        if row_domains and row_domains.isdisjoint(wanted_domains):
            return False
    return True


def _cninfo_lookup_filter(*, cache_key: str, request: RoboticsInsightRequest, keywords: list[str]):
    clauses = [RoboticsCninfoAnnouncement.cache_key == cache_key]
    if request.stock_code.strip():
        clauses.append(RoboticsCninfoAnnouncement.sec_code == request.stock_code.strip())
    if request.enterprise_name.strip():
        clauses.append(RoboticsCninfoAnnouncement.sec_name.like(f"%{request.enterprise_name.strip()}%"))
    for keyword in _clean_values(keywords):
        pattern = f"%{keyword}%"
        clauses.append(RoboticsCninfoAnnouncement.title.like(pattern))
        clauses.append(RoboticsCninfoAnnouncement.content_text.like(pattern))
    return or_(*clauses)


def _bidding_lookup_filter(*, cache_key: str, request: RoboticsInsightRequest, keywords: list[str]):
    clauses = [RoboticsBiddingDocument.cache_key == cache_key]
    if request.enterprise_name.strip():
        pattern = f"%{request.enterprise_name.strip()}%"
        clauses.append(RoboticsBiddingDocument.matched_enterprise_name.like(pattern))
        clauses.append(RoboticsBiddingDocument.buyer_name.like(pattern))
        clauses.append(RoboticsBiddingDocument.winning_bidder.like(pattern))
    for keyword in _clean_values(keywords):
        pattern = f"%{keyword}%"
        clauses.append(RoboticsBiddingDocument.title.like(pattern))
        clauses.append(RoboticsBiddingDocument.content_text.like(pattern))
        clauses.append(RoboticsBiddingDocument.project_name.like(pattern))
    return or_(*clauses)


def _bidding_row_matches_metadata(
    row: RoboticsBiddingDocument,
    *,
    notice_categories: list[str],
    regions: list[str],
    matched_enterprises: list[str],
) -> bool:
    metadata = dict(row.metadata_json or {})
    wanted_categories = set(_clean_values(notice_categories))
    if wanted_categories:
        row_category = str(metadata.get("noticeCategory") or "").strip()
        if row_category and row_category not in wanted_categories:
            return False
    wanted_regions = set(_clean_values(regions))
    if wanted_regions:
        row_region = str(row.region or metadata.get("region") or "").strip()
        if row_region and row_region not in wanted_regions:
            return False
    wanted_enterprises = set(_clean_values(matched_enterprises))
    if wanted_enterprises:
        text = " ".join(
            _clean_values(
                [
                    row.matched_enterprise_name or "",
                    row.buyer_name or "",
                    row.winning_bidder or "",
                    str(metadata.get("buyerName") or ""),
                    str(metadata.get("winningBidder") or ""),
                    " ".join(str(item) for item in metadata.get("candidates") or []),
                ]
            )
        )
        if text and not any(item in text for item in wanted_enterprises):
            return False
    return True


def _model_for_source(source_type: str):
    if source_type == SOURCE_POLICY:
        return RoboticsPolicyDocument
    if source_type == SOURCE_CNINFO:
        return RoboticsCninfoAnnouncement
    if source_type == SOURCE_BIDDING:
        return RoboticsBiddingDocument
    raise ValueError(f"unsupported robotics evidence source type: {source_type}")


def _source_name(source_type: str) -> str:
    if source_type == SOURCE_POLICY:
        return "国务院政策文件库"
    if source_type == SOURCE_CNINFO:
        return "巨潮资讯网"
    if source_type == SOURCE_BIDDING:
        return "中国招标投标公共服务平台"
    return "未知来源"


def _one_or_none(db, stmt):
    return db.execute(stmt).scalar_one_or_none()


def _stable_id(*, prefix: str, document: SourceDocument) -> str:
    raw = document.id or document.url or f"{document.source_type}:{document.title}:{document.content}"
    return f"{prefix}:{_hash_text(raw)}"


def _hash_text(value: str | None) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()


def _clean_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _first_text(metadata: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace("/", "-")
    raw = re.sub(r"\.\d+$", "", raw)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.hour == 0 and value.minute == 0 and value.second == 0:
        return value.date().isoformat()
    return value.isoformat()


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _profile_key(payload: dict[str, Any]) -> str:
    explicit = _payload_text(payload, "profile_key", "profileKey")
    if explicit:
        return explicit
    stock_code = _normalize_stock_code(_payload_text(payload, "stock_code", "stockCode"))
    if stock_code:
        exchange = _payload_text(payload, "exchange") or _payload_text(payload, "market")
        return f"{exchange.lower()}:{stock_code}" if exchange else stock_code
    company_name = _payload_text(payload, "company_name", "companyName")
    return f"name:{_hash_text(company_name)[:24]}"


def _normalize_stock_code(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    match = re.search(r"(\d{5,6})", raw)
    return match.group(1) if match else raw
