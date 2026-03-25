from __future__ import annotations

import io
import time

import pytest
from werkzeug.security import generate_password_hash

from app.rag.errors import RAGConfigurationError, RAGContractError
from app.rag.providers.registry import get_vector_store
from app.models import User


def _auth_headers(client, user_id: int) -> dict[str, str]:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "test-csrf-token"
    return {"X-CSRF-Token": "test-csrf-token"}


def _create_user(db_session, email: str) -> User:
    user = User(email=email, nickname="RAG Tester", password_hash=generate_password_hash("password123"))
    db_session.add(user)
    db_session.commit()
    return user


def test_rag_endpoints_feature_flag_disabled(client, db_session):
    user = _create_user(db_session, "rag-disabled@example.com")
    headers = _auth_headers(client, user.id)
    response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-a", "query": "test", "topK": 3, "filters": {}},
        headers=headers,
    )
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "rag feature is disabled"


def test_rag_upload_index_and_search_flow(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -1.0

    user = _create_user(db_session, "rag-flow@example.com")
    headers = _auth_headers(client, user.id)

    upload_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-flow",
            "file": (io.BytesIO("这是测试知识文档，包含合同条款。".encode("utf-8")), "contract.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.get_json()["data"]
    assert upload_payload["status"] == "uploaded"
    document_id = upload_payload["id"]

    index_response = client.post(
        "/api/rag/index",
        json={"workspaceId": "ws-flow", "documentId": document_id},
        headers=headers,
    )
    assert index_response.status_code == 200
    job_id = index_response.get_json()["data"]["jobId"]

    last_status = None
    for _ in range(20):
        job_response = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-flow", headers=headers)
        assert job_response.status_code == 200
        last_status = job_response.get_json()["data"]["status"]
        if last_status in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert last_status == "done"

    search_response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-flow", "query": "根据文档说明合同条款", "topK": 3, "filters": {}},
        headers=headers,
    )
    assert search_response.status_code == 200
    chunks = search_response.get_json()["data"]["chunks"]
    assert chunks
    assert chunks[0]["source"] == "contract.txt"


def test_rag_search_rejects_unauthorized_scope_filter(client, app, db_session):
    app.config["RAG_ENABLED"] = True

    user = _create_user(db_session, "rag-auth@example.com")
    headers = _auth_headers(client, user.id)
    response = client.post(
        "/api/rag/search",
        json={
            "workspaceId": "ws-auth",
            "query": "test",
            "topK": 3,
            "filters": {"user_id": user.id + 99},
        },
        headers=headers,
    )
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False


def test_rag_provider_configuration_rejects_unknown(app):
    app.config["RAG_VECTOR_PROVIDER"] = "unknown-provider"
    with app.app_context():
        with pytest.raises(RAGConfigurationError):
            get_vector_store()


def test_rag_graph_decision_and_citation_contract():
    from app.agent.graph.nodes import answer_with_citations_node, decide_rag_node

    decision = decide_rag_node({"user_message": "请根据文档回答", "rag_enabled": True})
    assert decision["rag_decision"] == "retrieve"

    with pytest.raises(RAGContractError):
        answer_with_citations_node(
            {
                "rag_chunks": [{"chunk_id": "abc123", "source": "", "score": 0.9}],
                "rag_decision": "retrieve",
                "reply": "placeholder",
            }
        )
