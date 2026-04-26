from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from flask import Flask

from app.workspace.routes import workspace_bp
import app.workspace.routes as workspace_routes


def _make_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")
    return app


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, user):
        self._user = user

    def execute(self, _query):
        return _FakeScalarResult(self._user)


@contextmanager
def _fake_session_scope(user=None):
    yield _FakeDb(user)


def test_report_write_routes_are_removed(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(workspace_routes, "_current_user_id", lambda: 1)

    client = app.test_client()

    generate = client.post("/api/workspace/reports/generate", json={"moduleArtifactIds": ["artifact-1"]})
    regenerate = client.post("/api/workspace/reports/report-1/regenerate", json={"workspaceId": "default"})

    assert generate.status_code in {404, 405}
    assert regenerate.status_code in {404, 405}


def test_workspace_chat_rejects_legacy_report_action(monkeypatch):
    app = _make_app()
    monkeypatch.setattr(workspace_routes, "_current_user_id", lambda: 1)

    client = app.test_client()
    response = client.post(
        "/api/workspace/chat",
        json={
            "message": "请生成综合报告",
            "conversationId": "conv-1",
            "workspaceId": "default",
            "reportAction": {"action": "generate", "moduleArtifactIds": ["artifact-1"]},
        },
    )

    assert response.status_code == 400
    assert "reportRequest" in response.get_json()["error"]


def test_workspace_chat_passes_report_request_to_agent(monkeypatch):
    app = _make_app()
    user = SimpleNamespace(id=1, preferences={"workspace": {"id": "default", "role": "investor"}})
    captured = {}

    monkeypatch.setattr(workspace_routes, "_current_user_id", lambda: 1)
    monkeypatch.setattr(workspace_routes, "session_scope", lambda: _fake_session_scope(user))
    monkeypatch.setattr(workspace_routes, "_selected_role", lambda _prefs: "investor")
    monkeypatch.setattr(workspace_routes, "load_conversation_history", lambda *args, **kwargs: (None, [], ""))
    monkeypatch.setattr(workspace_routes, "load_analysis_session_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(workspace_routes, "save_analysis_session_state", lambda *args, **kwargs: {})
    monkeypatch.setattr(workspace_routes, "save_conversation_turn", lambda *args, **kwargs: None)
    monkeypatch.setattr(workspace_routes, "delete_legacy_report_rows", lambda *args, **kwargs: [])

    def _fake_generate_reply_payload(**kwargs):
        captured.update(kwargs)
        return {
            "reply": "综合报告已生成。",
            "citations": [],
            "sources": [],
            "noEvidence": False,
            "analysisReport": {
                "reportId": "report-1",
                "title": "综合报告",
                "status": "completed",
                "preview": "预览",
                "availableFormats": ["pdf"],
                "downloadUrls": {"pdf": "/api/workspace/reports/report-1/download?format=pdf"},
                "previewUrl": "/api/workspace/reports/report-1/preview?format=pdf",
            },
            "graph": {},
            "graphMeta": {},
        }

    monkeypatch.setattr(workspace_routes, "generate_reply_payload", _fake_generate_reply_payload)

    client = app.test_client()
    response = client.post(
        "/api/workspace/chat",
        json={
            "message": "请生成综合报告",
            "conversationId": "conv-1",
            "workspaceId": "default",
            "reportRequest": {
                "sourceText": "石头科技近30天订单与政策观察。收入: 120亿元。订单机会增加。",
            },
        },
    )

    assert response.status_code == 200
    assert captured["report_request"]["mode"] == "generate"
    assert captured["report_request"]["documents"][0]["content"] == "石头科技近30天订单与政策观察。收入: 120亿元。订单机会增加。"
    assert response.get_json()["data"]["analysisReport"]["reportId"] == "report-1"


def test_workspace_reports_route_executes_standalone_request(monkeypatch):
    app = _make_app()
    user = SimpleNamespace(id=1, preferences={"workspace": {"id": "default", "role": "investor"}})
    captured = {}

    monkeypatch.setattr(workspace_routes, "_current_user_id", lambda: 1)
    monkeypatch.setattr(workspace_routes, "session_scope", lambda: _fake_session_scope(user))
    monkeypatch.setattr(workspace_routes, "_selected_role", lambda _prefs: "investor")

    def _fake_execute_report_request(db, *, user_id, workspace_id, request, report_writer=None):
        captured["user_id"] = user_id
        captured["workspace_id"] = workspace_id
        captured["request"] = request
        return {"reportId": "report-standalone-1", "title": "综合报告", "status": "completed"}

    monkeypatch.setattr(workspace_routes, "execute_report_request", _fake_execute_report_request)
    monkeypatch.setattr(
        workspace_routes,
        "save_analysis_report_artifact",
        lambda *args, **kwargs: SimpleNamespace(report_id="report-standalone-1", title="综合报告"),
    )
    monkeypatch.setattr(
        workspace_routes,
        "analysis_report_to_payload",
        lambda row, include_body=False: {
            "reportId": row.report_id,
            "title": row.title,
            "status": "completed",
            "previewUrl": "/api/workspace/reports/report-standalone-1/preview?format=pdf",
            "downloadUrls": {"pdf": "/api/workspace/reports/report-standalone-1/download?format=pdf"},
        },
    )

    client = app.test_client()
    response = client.post(
        "/api/workspace/reports",
        json={
            "workspaceId": "default",
            "sourceText": "石头科技近30天订单与政策观察。收入: 120亿元。订单机会增加。",
        },
    )

    assert response.status_code == 200
    assert captured["user_id"] == 1
    assert captured["workspace_id"] == "default"
    assert captured["request"]["mode"] == "generate"
    assert response.get_json()["data"]["reportId"] == "report-standalone-1"


def test_preview_and_download_routes_render_pdf(monkeypatch):
    app = _make_app()
    row = SimpleNamespace(
        report_id="report-1",
        title="Bundle report",
        markdown_body="# Report",
        html_body="<h1>Report</h1>",
        artifact_json={"paginatedReportBundle": {"schemaVersion": "paginated_report_bundle.v1"}},
        visual_assets_json=None,
        attachments_json=None,
    )

    monkeypatch.setattr(workspace_routes, "_current_user_id", lambda: 1)
    monkeypatch.setattr(workspace_routes, "session_scope", lambda: _fake_session_scope(None))
    monkeypatch.setattr(workspace_routes, "get_analysis_report", lambda *args, **kwargs: row)
    monkeypatch.setattr(workspace_routes, "render_report_pdf", lambda *args, **kwargs: b"%PDF-fake")
    monkeypatch.setattr(workspace_routes, "report_row_forbidden_values", lambda _row: [])
    monkeypatch.setattr(workspace_routes, "safe_report_filename", lambda _row, _format: "bundle-report.pdf")

    client = app.test_client()
    preview = client.get("/api/workspace/reports/report-1/preview")
    download = client.get("/api/workspace/reports/report-1/download")

    assert preview.status_code == 200
    assert preview.data.startswith(b"%PDF")
    assert "inline" in preview.headers["Content-Disposition"]
    assert download.status_code == 200
    assert "attachment" in download.headers["Content-Disposition"]
