from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app.bankruptcy import service as bankruptcy_service
from app.models import User


def _auth_headers(client, user_id: int) -> dict[str, str]:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


def _sample_lines() -> list[str]:
    sample_path = Path(__file__).resolve().parent.parent / "assets" / "bankruptcy" / "samples" / "taiwan_data.csv"
    with sample_path.open("r", encoding="utf-8") as handle:
        return [handle.readline().strip(), handle.readline().strip()]


def _single_sample_csv_bytes() -> bytes:
    header, row = _sample_lines()
    return f"{header}\n{row}\n".encode("utf-8")


def _missing_column_csv_bytes() -> bytes:
    header, row = _sample_lines()
    header_parts = header.split(",")
    row_parts = row.split(",")
    header_parts.pop()
    row_parts.pop()
    return f"{','.join(header_parts)}\n{','.join(row_parts)}\n".encode("utf-8")


def _upload_record(client, headers: dict[str, str], *, workspace_id: str = "ws-risk", enterprise_name: str = ""):
    data = {
        "workspaceId": workspace_id,
        "file": (io.BytesIO(_single_sample_csv_bytes()), "sample.csv"),
    }
    if enterprise_name:
        data["enterpriseName"] = enterprise_name
    return client.post("/api/bankruptcy/records", data=data, headers=headers, content_type="multipart/form-data")


def test_bankruptcy_predict_requires_auth(client):
    response = client.post(
        "/api/bankruptcy/predict",
        data={"workspaceId": "ws-risk", "file": (io.BytesIO(_single_sample_csv_bytes()), "sample.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication required"


def test_bankruptcy_predict_rejects_multi_row_csv(client, db_session):
    user = User(email="bankruptcy-multi@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    csv_bytes = b"feature_a,feature_b\n1,2\n3,4\n"
    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "file": (io.BytesIO(csv_bytes), "multi.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "single-sample" in response.get_json()["error"]


def test_bankruptcy_predict_rejects_missing_required_columns(client, db_session):
    user = User(email="bankruptcy-missing@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "file": (io.BytesIO(_missing_column_csv_bytes()), "missing.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "missing required feature columns" in response.get_json()["error"]


def test_bankruptcy_predict_rejects_headerless_single_row_csv(client, db_session):
    user = User(email="bankruptcy-headerless@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    _, row = _sample_lines()
    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "file": (io.BytesIO(f"{row}\n".encode("utf-8")), "headerless.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "csv must include a header row with the required feature names and one data row"


def test_bankruptcy_predict_returns_structured_result_and_plot(client, db_session):
    bankruptcy_service.reset_runtime_for_tests()
    user = User(email="bankruptcy-success@example.com", password_hash=generate_password_hash("password123"))
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
    payload = response.get_json()["data"]
    assert payload["companyName"] == "ACME Holdings"
    assert 0.0 <= float(payload["probability"]) <= 1.0
    assert float(payload["threshold"]) == 0.63
    assert payload["riskLevel"] in {"high", "low"}
    assert payload["inputSummary"]["rowCount"] == 1
    assert payload["inputSummary"]["featureCount"] == 95
    assert isinstance(payload["topFeatures"], list)
    assert payload["topFeatures"]
    assert payload["plotUrl"].startswith("/api/bankruptcy/plots/")

    plot_response = client.get(payload["plotUrl"])
    assert plot_response.status_code == 200
    assert plot_response.mimetype == "image/png"


def test_bankruptcy_plot_rejects_invalid_token(client, db_session):
    bankruptcy_service.reset_runtime_for_tests()
    user = User(email="bankruptcy-plot@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "file": (io.BytesIO(_single_sample_csv_bytes()), "sample.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    plot_url = response.get_json()["data"]["plotUrl"]
    parsed = urlparse(plot_url)
    params = parse_qs(parsed.query)
    params["token"] = ["bad-token"]
    tampered = f"{parsed.path}?workspaceId={params['workspaceId'][0]}&token={params['token'][0]}"

    plot_response = client.get(tampered)
    assert plot_response.status_code == 403
    assert plot_response.get_json()["error"] == "plot token is invalid"


def test_bankruptcy_plot_requires_matching_session(client, db_session):
    bankruptcy_service.reset_runtime_for_tests()
    owner = User(email="bankruptcy-owner@example.com", password_hash=generate_password_hash("password123"))
    intruder = User(email="bankruptcy-intruder@example.com", password_hash=generate_password_hash("password123"))
    db_session.add_all([owner, intruder])
    db_session.commit()

    owner_headers = _auth_headers(client, owner.id)
    response = client.post(
        "/api/bankruptcy/predict",
        data={
            "workspaceId": "ws-risk",
            "file": (io.BytesIO(_single_sample_csv_bytes()), "sample.csv"),
        },
        headers=owner_headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    plot_url = response.get_json()["data"]["plotUrl"]

    intruder_headers = _auth_headers(client, intruder.id)
    plot_response = client.get(plot_url, headers=intruder_headers)
    assert plot_response.status_code == 403
    assert plot_response.get_json()["error"] == "plot token is invalid"

    db_session.expire_all()
    users = db_session.execute(select(User).order_by(User.email.asc())).scalars().all()
    assert len(users) == 2


def test_bankruptcy_record_upload_and_reopen_detail(client, db_session):
    user = User(email="bankruptcy-record@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    upload_response = _upload_record(client, headers, enterprise_name="Saved Company")
    assert upload_response.status_code == 200
    payload = upload_response.get_json()["data"]
    assert payload["status"] == "uploaded"
    assert payload["companyName"] == "Saved Company"
    record_id = int(payload["id"])

    list_response = client.get("/api/bankruptcy/records?workspaceId=ws-risk", headers=headers)
    assert list_response.status_code == 200
    records = list_response.get_json()["data"]["records"]
    assert len(records) == 1
    assert records[0]["id"] == record_id
    assert records[0]["status"] == "uploaded"

    detail_response = client.get(f"/api/bankruptcy/records/{record_id}?workspaceId=ws-risk", headers=headers)
    assert detail_response.status_code == 200
    detail = detail_response.get_json()["data"]
    assert detail["status"] == "uploaded"
    assert detail["plotUrl"] == ""
    assert detail["fileName"] == "sample.csv"


def test_bankruptcy_saved_record_can_be_analyzed_and_plot_reopened(client, db_session):
    bankruptcy_service.reset_runtime_for_tests()
    user = User(email="bankruptcy-analyze-record@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    upload_response = _upload_record(client, headers, enterprise_name="Delayed Analysis Co")
    record_id = int(upload_response.get_json()["data"]["id"])

    analyze_response = client.post(
        f"/api/bankruptcy/records/{record_id}/analyze",
        data={"workspaceId": "ws-risk"},
        headers=headers,
    )
    assert analyze_response.status_code == 200
    payload = analyze_response.get_json()["data"]
    assert payload["status"] == "analyzed"
    assert payload["companyName"] == "Delayed Analysis Co"
    assert payload["plotUrl"].startswith(f"/api/bankruptcy/records/{record_id}/plot")
    assert payload["topFeatures"]

    plot_response = client.get(payload["plotUrl"], headers=headers)
    assert plot_response.status_code == 200
    assert plot_response.mimetype == "image/png"

    reopened = client.get(f"/api/bankruptcy/records/{record_id}?workspaceId=ws-risk", headers=headers)
    assert reopened.status_code == 200
    assert reopened.get_json()["data"]["status"] == "analyzed"
    assert reopened.get_json()["data"]["plotUrl"].startswith(f"/api/bankruptcy/records/{record_id}/plot")


def test_bankruptcy_record_delete_removes_record_from_history(client, db_session):
    user = User(email="bankruptcy-delete-record@example.com", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    headers = _auth_headers(client, user.id)

    upload_response = _upload_record(client, headers, enterprise_name="Delete Me")
    record_id = int(upload_response.get_json()["data"]["id"])

    delete_response = client.delete(f"/api/bankruptcy/records/{record_id}?workspaceId=ws-risk", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.get_json()["data"]["status"] == "deleted"

    list_response = client.get("/api/bankruptcy/records?workspaceId=ws-risk", headers=headers)
    assert list_response.status_code == 200
    assert list_response.get_json()["data"]["records"] == []

    detail_response = client.get(f"/api/bankruptcy/records/{record_id}?workspaceId=ws-risk", headers=headers)
    assert detail_response.status_code == 404
    assert detail_response.get_json()["error"] == "bankruptcy record not found"


def test_bankruptcy_record_scope_is_enforced(client, db_session):
    bankruptcy_service.reset_runtime_for_tests()
    owner = User(email="bankruptcy-record-owner@example.com", password_hash=generate_password_hash("password123"))
    intruder = User(email="bankruptcy-record-intruder@example.com", password_hash=generate_password_hash("password123"))
    db_session.add_all([owner, intruder])
    db_session.commit()

    owner_headers = _auth_headers(client, owner.id)
    upload_response = _upload_record(client, owner_headers, enterprise_name="Scoped Co")
    record_id = int(upload_response.get_json()["data"]["id"])

    intruder_headers = _auth_headers(client, intruder.id)
    detail_response = client.get(f"/api/bankruptcy/records/{record_id}?workspaceId=ws-risk", headers=intruder_headers)
    assert detail_response.status_code == 403
    assert detail_response.get_json()["error"] == "bankruptcy record is outside authorized scope"

    analyze_response = client.post(
        f"/api/bankruptcy/records/{record_id}/analyze",
        data={"workspaceId": "ws-risk"},
        headers=intruder_headers,
    )
    assert analyze_response.status_code == 403
    assert analyze_response.get_json()["error"] == "bankruptcy record is outside authorized scope"
