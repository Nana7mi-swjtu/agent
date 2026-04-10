from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from ..models import BankruptcyAnalysisRecord
from .errors import BankruptcyAuthorizationError, BankruptcyNotFoundError, BankruptcyValidationError

ALLOWED_RECORD_STATUSES = {"uploaded", "analyzed", "failed", "deleted"}


def create_record(
    *,
    db,
    user_id: int,
    workspace_id: str,
    source_name: str,
    file_name: str,
    file_extension: str,
    mime_type: str,
    storage_path: str,
    enterprise_name: str | None = None,
) -> BankruptcyAnalysisRecord:
    record = BankruptcyAnalysisRecord(
        user_id=user_id,
        workspace_id=workspace_id,
        source_name=source_name,
        file_name=file_name,
        file_extension=file_extension.lower(),
        mime_type=mime_type,
        storage_path=storage_path,
        enterprise_name=enterprise_name or None,
        status="uploaded",
    )
    db.add(record)
    db.flush()
    return record


def get_record_for_scope(
    *,
    db,
    record_id: int,
    user_id: int,
    workspace_id: str,
    include_deleted: bool = False,
) -> BankruptcyAnalysisRecord:
    record = db.execute(select(BankruptcyAnalysisRecord).where(BankruptcyAnalysisRecord.id == record_id)).scalar_one_or_none()
    if record is None:
        raise BankruptcyNotFoundError("bankruptcy record not found")
    if record.user_id != user_id or record.workspace_id != workspace_id:
        raise BankruptcyAuthorizationError("bankruptcy record is outside authorized scope")
    if not include_deleted and (record.status == "deleted" or record.deleted_at is not None):
        raise BankruptcyNotFoundError("bankruptcy record not found")
    return record


def list_records_for_scope(*, db, user_id: int, workspace_id: str) -> list[BankruptcyAnalysisRecord]:
    stmt = (
        select(BankruptcyAnalysisRecord)
        .where(
            BankruptcyAnalysisRecord.user_id == user_id,
            BankruptcyAnalysisRecord.workspace_id == workspace_id,
            BankruptcyAnalysisRecord.status != "deleted",
            BankruptcyAnalysisRecord.deleted_at.is_(None),
        )
        .order_by(BankruptcyAnalysisRecord.updated_at.desc(), BankruptcyAnalysisRecord.id.desc())
    )
    return list(db.execute(stmt).scalars().all())


def set_record_status(
    *,
    record: BankruptcyAnalysisRecord,
    status: str,
    error_message: str | None = None,
    probability: float | None = None,
    threshold: float | None = None,
    risk_level: str | None = None,
    result_json: dict | None = None,
    plot_path: str | None = None,
    analyzed_at: datetime | None = None,
) -> None:
    if status not in ALLOWED_RECORD_STATUSES:
        raise BankruptcyValidationError("invalid bankruptcy record status")
    if record.status == "deleted" and status != "deleted":
        raise BankruptcyValidationError("deleted bankruptcy record cannot transition to active state")
    record.status = status
    record.error_message = error_message
    if probability is not None:
        record.probability = probability
    if threshold is not None:
        record.threshold = threshold
    if risk_level is not None:
        record.risk_level = risk_level
    if result_json is not None:
        record.result_json = result_json
    if plot_path is not None:
        record.plot_path = plot_path
    if status == "analyzed":
        record.analyzed_at = analyzed_at or datetime.utcnow()
        record.deleted_at = None
    if status == "failed":
        record.analyzed_at = analyzed_at or datetime.utcnow()
        record.probability = None
        record.threshold = None
        record.risk_level = None
        record.result_json = None
        record.plot_path = None
    if status == "deleted":
        record.deleted_at = datetime.utcnow()
