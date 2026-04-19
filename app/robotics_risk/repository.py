from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select

from app.models import RoboticsBiddingDocument, RoboticsCninfoAnnouncement, RoboticsPolicyDocument

from .pdf_text import PdfTextExtractionResult
from .schemas import EnterpriseProfile, RoboticsInsightRequest, SourceDocument

SOURCE_POLICY = "gov_policy"
SOURCE_CNINFO = "cninfo_announcement"
SOURCE_BIDDING = "bidding_procurement"
NEGATIVE_STATUSES = {"failed", "empty"}


def build_cache_key(
    *,
    source_type: str,
    request: RoboticsInsightRequest,
    profile: EnterpriseProfile,
) -> str:
    parts = [
        source_type,
        request.enterprise_name.strip(),
        request.stock_code.strip(),
        request.time_range.strip(),
        request.focus.strip(),
        "|".join(sorted(_clean_values([*request.dimensions, *profile.keywords]))),
    ]
    return _hash_text("\n".join(parts))


class RoboticsEvidenceRepository:
    def __init__(self, db) -> None:
        self.db = db

    def query_policy_documents(
        self,
        *,
        cache_key: str,
        keywords: list[str],
        published_since: datetime | None,
    ) -> list[RoboticsPolicyDocument]:
        stmt = select(RoboticsPolicyDocument).where(RoboticsPolicyDocument.status.notin_(NEGATIVE_STATUSES))
        stmt = stmt.where(_policy_lookup_filter(cache_key=cache_key, keywords=keywords))
        if published_since is not None:
            stmt = stmt.where(
                or_(
                    RoboticsPolicyDocument.published_at.is_(None),
                    RoboticsPolicyDocument.published_at >= published_since,
                )
            )
        return list(self.db.execute(stmt.order_by(RoboticsPolicyDocument.published_at.desc())).scalars().all())

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
        return list(self.db.execute(stmt.order_by(RoboticsBiddingDocument.published_at.desc())).scalars().all())

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
            metadata={"status": status, "errorMessage": message},
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
        row.content_text = document.content
        row.content_hash = _hash_text(document.content) if document.content else row.content_hash
        row.matched_keywords_json = {"keywords": _clean_values(metadata.get("matchedKeywords") or [])}
        row.relevance_segments_json = {"segments": _clean_values(metadata.get("relevanceSegments") or [])}
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
        row.status = str(metadata.get("status") or ("parsed" if document.content else "fetched"))
        row.error_message = _first_text(metadata, "errorMessage", "error_message")
        row.page_count = _coerce_int(metadata.get("pageCount") or metadata.get("page_count")) or row.page_count
        row.extraction_method = _first_text(metadata, "extractionMethod", "extraction_method") or row.extraction_method
        row.ocr_used = 1 if bool(metadata.get("ocrUsed") or metadata.get("ocr_used")) else row.ocr_used
        row.parse_status = _first_text(metadata, "parseStatus", "parse_status") or ("parsed" if document.content else "pending")
        row.parse_error = _first_text(metadata, "parseError", "parse_error")
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
            "fetchedAt": _format_datetime(row.fetched_at),
            "expiresAt": _format_datetime(row.expires_at),
            "status": row.status,
        }
    )
    return SourceDocument(
        id=f"bidding:{row.notice_id}",
        source_type=SOURCE_BIDDING,
        source_name="全国公共资源交易/招标采购信息源",
        title=row.title,
        content=row.content_text or "",
        url=row.url or "",
        published_at=_format_datetime(row.published_at),
        authority_score=0.85,
        relevance_scope="market_demand",
        metadata=metadata,
    )


def _policy_lookup_filter(*, cache_key: str, keywords: list[str]):
    clauses = [RoboticsPolicyDocument.cache_key == cache_key]
    for keyword in _clean_values(keywords):
        pattern = f"%{keyword}%"
        clauses.append(RoboticsPolicyDocument.title.like(pattern))
        clauses.append(RoboticsPolicyDocument.content_text.like(pattern))
    return or_(*clauses)


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
        return "全国公共资源交易/招标采购信息源"
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
