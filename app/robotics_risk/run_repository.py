from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.models import RoboticsInsightRun


class RoboticsInsightRunRepository:
    def __init__(self, db) -> None:
        self.db = db

    def create_run(
        self,
        *,
        run_id: str,
        enterprise_name: str,
        stock_code: str = "",
        request_payload: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> RoboticsInsightRun:
        now = started_at or datetime.utcnow()
        row = RoboticsInsightRun(
            run_id=run_id,
            enterprise_name=enterprise_name,
            stock_code=stock_code or None,
            request_json=request_payload or {},
            status="running",
            created_at=now,
            started_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def complete_run(
        self,
        *,
        run_id: str,
        result_payload: dict[str, Any],
        handoff_payload: dict[str, Any],
        status: str = "done",
        completed_at: datetime | None = None,
    ) -> RoboticsInsightRun:
        row = self._require_run(run_id)
        now = completed_at or datetime.utcnow()
        row.status = status
        row.result_json = result_payload
        row.handoff_json = handoff_payload
        row.error_message = None
        row.completed_at = now
        row.updated_at = now
        self.db.commit()
        self.db.refresh(row)
        return row

    def fail_run(
        self,
        *,
        run_id: str,
        error_message: str,
        result_payload: dict[str, Any] | None = None,
        handoff_payload: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> RoboticsInsightRun:
        row = self._require_run(run_id)
        now = completed_at or datetime.utcnow()
        row.status = "failed"
        row.error_message = str(error_message or "unknown error")[:2048]
        if result_payload is not None:
            row.result_json = result_payload
        if handoff_payload is not None:
            row.handoff_json = handoff_payload
        row.completed_at = now
        row.updated_at = now
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_run(self, run_id: str) -> RoboticsInsightRun | None:
        clean = str(run_id or "").strip()
        if not clean:
            return None
        stmt = select(RoboticsInsightRun).where(RoboticsInsightRun.run_id == clean)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_run_payload(self, run_id: str) -> dict[str, Any] | None:
        row = self.get_run(run_id)
        if row is None:
            return None
        return run_to_payload(row)

    def _require_run(self, run_id: str) -> RoboticsInsightRun:
        row = self.get_run(run_id)
        if row is None:
            raise ValueError(f"robotics insight run not found: {run_id}")
        return row


def run_to_payload(row: RoboticsInsightRun) -> dict[str, Any]:
    return {
        "runId": row.run_id,
        "enterpriseName": row.enterprise_name,
        "stockCode": row.stock_code or "",
        "status": row.status,
        "request": row.request_json or {},
        "result": row.result_json or {},
        "documentHandoff": row.handoff_json or {},
        "errorMessage": row.error_message or "",
        "createdAt": _format_datetime(row.created_at),
        "startedAt": _format_datetime(row.started_at),
        "completedAt": _format_datetime(row.completed_at),
        "updatedAt": _format_datetime(row.updated_at),
    }


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat()
