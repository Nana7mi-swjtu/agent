from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.email_service import get_email_sender
from app.models import User


def _auth_headers(client, user_id: int) -> dict[str, str]:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


def _read_json_lines(path: str | Path) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    return [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _find_events(records: list[dict], event: str) -> list[dict]:
    return [record for record in records if record.get("event") == event]


def _latest_event(records: list[dict], event: str) -> dict:
    matches = _find_events(records, event)
    assert matches, f"missing event {event}"
    return matches[-1]


def _single_sample_csv_bytes() -> bytes:
    sample_path = Path(__file__).resolve().parent.parent / "assets" / "bankruptcy" / "samples" / "taiwan_data.csv"
    with sample_path.open("r", encoding="utf-8") as handle:
        header = handle.readline().strip()
        row = handle.readline().strip()
    return f"{header}\n{row}\n".encode("utf-8")


def test_logging_bootstrap_configures_expected_handlers(app):
    logging_paths = app.extensions["logging"]
    assert Path(logging_paths["log_dir"]).exists()

    root_handlers = logging.getLogger().handlers
    assert any(isinstance(handler, logging.StreamHandler) for handler in root_handlers)
    assert any(handler.__class__.__name__ == "RotatingFileHandler" for handler in root_handlers)

    access_handlers = logging.getLogger("access").handlers
    audit_handlers = logging.getLogger("audit").handlers
    assert any(handler.__class__.__name__ == "RotatingFileHandler" for handler in access_handlers)
    assert any(handler.__class__.__name__ == "RotatingFileHandler" for handler in audit_handlers)


def test_console_email_sender_logs_masked_email_without_code(app):
    app.config["EMAIL_BACKEND"] = "console"
    with app.app_context():
        get_email_sender().send_code("visible@example.com", "123456", "register")

    records = _read_json_lines(app.extensions["logging"]["app_log"])
    event = _latest_event(records, "email.code.generated")
    assert event["email"] == "v***e@example.com"
    assert "123456" not in json.dumps(event, ensure_ascii=False)
    assert "验证码是" not in json.dumps(event, ensure_ascii=False)


def test_request_id_header_is_propagated_and_access_logged(client, app):
    response = client.get("/health", headers={"X-Request-ID": "req-health-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-health-1"

    response_2 = client.get("/health")
    assert response_2.status_code == 200
    assert response_2.headers["X-Request-ID"]
    assert response_2.headers["X-Request-ID"] != "req-health-1"

    records = _read_json_lines(app.extensions["logging"]["access_log"])
    first = _find_events(records, "http.request.completed")[-2]
    second = _find_events(records, "http.request.completed")[-1]
    assert first["request_id"] == "req-health-1"
    assert first["path"] == "/health"
    assert first["method"] == "GET"
    assert first["status_code"] == 200
    assert second["request_id"] == response_2.headers["X-Request-ID"]


def test_unhandled_exception_logs_app_and_access_records(app, client):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    response = client.get("/boom", headers={"X-Request-ID": "req-boom-1"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-boom-1"

    app_records = _read_json_lines(app.extensions["logging"]["app_log"])
    access_records = _read_json_lines(app.extensions["logging"]["access_log"])
    app_event = _latest_event(app_records, "http.request.unhandled_exception")
    access_event = _latest_event(access_records, "http.request.completed")
    assert app_event["request_id"] == "req-boom-1"
    assert app_event["path"] == "/boom"
    assert access_event["request_id"] == "req-boom-1"
    assert access_event["status_code"] == 500


def test_auth_and_workspace_audit_events_are_recorded(client, app, db_session, monkeypatch):
    user = User(email="audit-login@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()

    failed = client.post("/auth/login", json={"email": "audit-login@example.com", "password": "bad-password"})
    assert failed.status_code == 401

    login_response = client.post("/auth/login", json={"email": "audit-login@example.com", "password": "password123"})
    assert login_response.status_code == 200
    csrf_token = login_response.get_json()["csrfToken"]

    patch_headers = {"X-CSRF-Token": csrf_token}
    client.patch("/api/workspace/context", json={"role": "investor"}, headers=patch_headers)
    monkeypatch.setattr(
        "app.workspace.routes.generate_reply_payload",
        lambda **kwargs: {"reply": "ok", "citations": [], "noEvidence": False},
    )
    chat_response = client.post("/api/workspace/chat", json={"message": "hello"}, headers=patch_headers)
    assert chat_response.status_code == 200

    records = _read_json_lines(app.extensions["logging"]["audit_log"])
    assert _latest_event(records, "auth.login.failed")["operation_status"] == "failed"
    assert _latest_event(records, "auth.login.succeeded")["operation_status"] == "succeeded"
    requested = _latest_event(records, "workspace.chat.requested")
    completed = _latest_event(records, "workspace.chat.completed")
    assert requested["request_id"] == chat_response.headers["X-Request-ID"]
    assert completed["request_id"] == chat_response.headers["X-Request-ID"]
    assert completed["resource_id"].startswith("user-")


def test_rag_index_logs_preserve_request_and_job_context(client, app, db_session):
    user = User(email="audit-rag@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    upload_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-logging",
            "chunking": '{"strategy":"paragraph"}',
            "file": (io.BytesIO("hello world".encode("utf-8")), "logging.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    document_id = upload_response.get_json()["data"]["id"]

    index_response = client.post(
        "/api/rag/index",
        json={"workspaceId": "ws-logging", "documentId": document_id},
        headers=headers,
    )
    assert index_response.status_code == 200
    payload = index_response.get_json()["data"]
    request_id = index_response.headers["X-Request-ID"]
    job_id = payload["jobId"]

    audit_records = _read_json_lines(app.extensions["logging"]["audit_log"])
    app_records = _read_json_lines(app.extensions["logging"]["app_log"])
    enqueued = _latest_event(audit_records, "rag.index.enqueued")
    started = _latest_event(app_records, "rag.index.started")
    finished = _latest_event(app_records, "rag.index.finished")
    assert enqueued["request_id"] == request_id
    assert enqueued["job_id"] == job_id
    assert started["request_id"] == request_id
    assert started["job_id"] == job_id
    assert finished["request_id"] == request_id
    assert finished["job_id"] == job_id
    assert finished["document_id"] == document_id


def test_bankruptcy_audit_event_is_recorded(client, app, db_session):
    user = User(email="audit-bankruptcy@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "enterpriseName": "ACME Holdings",
            "file": (io.BytesIO(_single_sample_csv_bytes()), "sample.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200

    records = _read_json_lines(app.extensions["logging"]["audit_log"])
    event = _latest_event(records, "bankruptcy.predict.completed")
    assert event["operation_status"] == "succeeded"
    assert event["workspace_id"] == "ws-risk"
