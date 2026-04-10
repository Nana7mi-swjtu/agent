from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app.agent.graph.search import _search_plan_node
from app.db import get_session
from app.rag.errors import RAGConfigurationError, RAGContractError
from app.rag.fileloaders import load_source_document
from app.rag.fileloaders.canonical import parse_canonical_text
from app.rag.pipeline.indexer import parse_and_chunk_document
from app.rag.providers.semantic_chunking_provider import OpenAICompatibleSemanticChunkingProvider
from app.rag.providers.registry import get_chunker, get_embedder, get_reranker, get_semantic_chunking_provider
from app.rag.providers.registry import get_vector_store
from app.rag.schemas import ChunkingRequest, RetrievalHit
from app.models import RagChunk, RagDocument, RagIndexJob, User


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


def _upload_text_document(client, headers, workspace_id: str, filename: str, content: str) -> dict:
    response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": workspace_id,
            "file": (io.BytesIO(content.encode("utf-8")), filename),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _index_document(client, headers, workspace_id: str, document_id: int, chunking: dict | None = None) -> dict:
    response = client.post(
        "/api/rag/index",
        json={
            "workspaceId": workspace_id,
            "documentId": document_id,
            **({"chunking": chunking} if chunking else {}),
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.get_json()["data"]


def _load_rag_document(app, document_id: int) -> RagDocument | None:
    with app.app_context():
        session = get_session()
        try:
            return session.get(RagDocument, document_id)
        finally:
            session.close()


def _count_document_chunks(app, document_id: int) -> int:
    with app.app_context():
        session = get_session()
        try:
            return session.query(RagChunk).filter(RagChunk.document_id == document_id).count()
        finally:
            session.close()


def _count_document_jobs(app, document_id: int) -> int:
    with app.app_context():
        session = get_session()
        try:
            return session.query(RagIndexJob).filter(RagIndexJob.document_id == document_id).count()
        finally:
            session.close()


def test_rag_endpoints_feature_flag_disabled(client, app, db_session):
    app.config["RAG_ENABLED"] = False
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
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0

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
    assert upload_payload["chunkingApplied"]["strategy"] == "paragraph"
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
    final_job = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-flow", headers=headers).get_json()["data"]
    assert final_job["chunkingApplied"]["strategy"] == "paragraph"
    assert final_job["chunkingApplied"]["fallbackUsed"] is False

    search_response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-flow", "query": "根据文档说明合同条款", "topK": 3, "filters": {}},
        headers=headers,
    )
    assert search_response.status_code == 200
    chunks = search_response.get_json()["data"]["chunks"]
    assert chunks
    assert chunks[0]["source"] == "contract.txt"
    paragraph_meta = chunks[0]["metadata"]
    assert paragraph_meta["chunk_strategy"] == "paragraph"
    assert paragraph_meta["semantic_segment_source"] == "paragraph"
    assert isinstance(paragraph_meta.get("semantic_sentence_index"), int)
    semantic_segment = chunks[0]["semanticSegment"]
    assert isinstance(semantic_segment, dict)
    assert semantic_segment["source"] == "paragraph"
    assert isinstance(semantic_segment["text"], str) and semantic_segment["text"]

    documents_response = client.get("/api/rag/documents?workspaceId=ws-flow", headers=headers)
    assert documents_response.status_code == 200
    docs = documents_response.get_json()["data"]["documents"]
    assert docs
    assert docs[0]["chunkingApplied"]["strategy"] == "paragraph"
    assert docs[0]["loaderType"] == "txt"
    assert docs[0]["extractionMethod"] == "plain_text"
    assert docs[0]["ocrUsed"] is False
    assert isinstance(docs[0]["derivedAt"], str) and docs[0]["derivedAt"]


def test_rag_rejects_removed_html_and_csv_formats(client, app, db_session):
    app.config["RAG_ENABLED"] = True

    user = _create_user(db_session, "rag-removed-formats@example.com")
    headers = _auth_headers(client, user.id)

    html_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-formats",
            "file": (io.BytesIO("<h1>Hello</h1>".encode("utf-8")), "page.html"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert html_response.status_code == 400
    html_error = html_response.get_json()["error"]
    assert "unsupported format" in html_error
    assert "docx" in html_error and "md" in html_error and "pdf" in html_error and "txt" in html_error

    csv_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-formats",
            "file": (io.BytesIO("a,b\n1,2".encode("utf-8")), "sheet.csv"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert csv_response.status_code == 400
    csv_error = csv_response.get_json()["error"]
    assert "unsupported format" in csv_error
    assert "docx" in csv_error and "md" in csv_error and "pdf" in csv_error and "txt" in csv_error


def test_rag_delete_keeps_record_but_clears_active_assets(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0

    user = _create_user(db_session, "rag-delete@example.com")
    headers = _auth_headers(client, user.id)
    upload_payload = _upload_text_document(client, headers, "ws-delete", "delete-me.txt", "需要被删除的知识文档。")
    document_id = int(upload_payload["id"])

    job_payload = _index_document(client, headers, "ws-delete", document_id)
    job_id = int(job_payload["jobId"])
    job_response = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-delete", headers=headers)
    assert job_response.status_code == 200
    assert job_response.get_json()["data"]["status"] == "done"

    search_before_delete = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-delete", "query": "删除前检索", "topK": 5, "filters": {}},
        headers=headers,
    )
    assert search_before_delete.status_code == 200
    assert search_before_delete.get_json()["data"]["chunks"]

    stored_document = db_session.get(RagDocument, document_id)
    assert stored_document is not None
    stored_path = Path(stored_document.storage_path)
    derived_path = Path(str(stored_document.derived_text_path or ""))
    assert stored_path.exists()
    assert derived_path.exists()

    delete_response = client.delete(f"/api/rag/documents/{document_id}?workspaceId=ws-delete", headers=headers)
    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()["data"]
    assert delete_payload["status"] == "deleted"

    documents_response = client.get("/api/rag/documents?workspaceId=ws-delete", headers=headers)
    assert documents_response.status_code == 200
    assert documents_response.get_json()["data"]["documents"] == []

    search_after_delete = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-delete", "query": "删除后检索", "topK": 5, "filters": {}},
        headers=headers,
    )
    assert search_after_delete.status_code == 200
    assert search_after_delete.get_json()["data"]["chunks"] == []

    deleted_document = _load_rag_document(app, document_id)
    assert deleted_document is not None
    assert deleted_document.status == "deleted"
    assert deleted_document.deleted_at is not None
    assert deleted_document.embedding_model is None
    assert _count_document_chunks(app, document_id) == 0
    assert _count_document_jobs(app, document_id) == 1
    assert stored_path.exists() is False
    assert derived_path.exists() is False


def test_rag_delete_rejects_indexing_documents(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False

    user = _create_user(db_session, "rag-delete-indexing@example.com")
    headers = _auth_headers(client, user.id)
    upload_payload = _upload_text_document(client, headers, "ws-indexing", "indexing.txt", "处理中不可删除")
    document_id = int(upload_payload["id"])

    document = db_session.get(RagDocument, document_id)
    assert document is not None
    document.status = "indexing"
    db_session.commit()

    delete_response = client.delete(f"/api/rag/documents/{document_id}?workspaceId=ws-indexing", headers=headers)
    assert delete_response.status_code == 400
    payload = delete_response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "cannot delete document while indexing"

    persisted = _load_rag_document(app, document_id)
    assert persisted is not None
    assert persisted.status == "indexing"


def test_rag_reindex_replaces_active_artifacts_and_retry_recovers(client, app, db_session, monkeypatch):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0

    user = _create_user(db_session, "rag-reindex@example.com")
    headers = _auth_headers(client, user.id)
    upload_payload = _upload_text_document(
        client,
        headers,
        "ws-reindex",
        "reindex.txt",
        "第一段说明。第二段补充。第三段用于重新索引测试。",
    )
    document_id = int(upload_payload["id"])

    first_job = _index_document(client, headers, "ws-reindex", document_id)
    assert int(first_job["documentId"]) == document_id
    first_document = _load_rag_document(app, document_id)
    assert first_document is not None
    first_chunk_count = _count_document_chunks(app, document_id)
    assert first_chunk_count > 0

    from app.rag.pipeline.indexer import chunk_document_blocks

    original_chunking = chunk_document_blocks

    def _broken_chunking(*args, **kwargs):
        raise RuntimeError("forced retry path")

    monkeypatch.setattr("app.rag.service.chunk_document_blocks", _broken_chunking)
    failed_response = client.post(
        f"/api/rag/documents/{document_id}/reindex",
        json={"workspaceId": "ws-reindex", "chunking": {"strategy": "semantic_llm"}},
        headers=headers,
    )
    assert failed_response.status_code == 200
    failed_job_id = failed_response.get_json()["data"]["jobId"]
    failed_job_response = client.get(f"/api/rag/jobs/{failed_job_id}?workspaceId=ws-reindex", headers=headers)
    assert failed_job_response.status_code == 200
    assert failed_job_response.get_json()["data"]["status"] == "failed"

    failed_document = _load_rag_document(app, document_id)
    assert failed_document is not None
    assert failed_document.status == "failed"
    assert _count_document_chunks(app, document_id) == 0

    monkeypatch.setattr("app.rag.service.chunk_document_blocks", original_chunking)
    retry_response = client.post(
        f"/api/rag/documents/{document_id}/reindex",
        json={"workspaceId": "ws-reindex", "chunking": {"strategy": "semantic_llm"}},
        headers=headers,
    )
    assert retry_response.status_code == 200
    retry_job_id = retry_response.get_json()["data"]["jobId"]
    retry_job_response = client.get(f"/api/rag/jobs/{retry_job_id}?workspaceId=ws-reindex", headers=headers)
    assert retry_job_response.status_code == 200
    retry_payload = retry_job_response.get_json()["data"]
    assert retry_payload["status"] == "done"
    assert retry_payload["chunkingApplied"]["requestedStrategy"] == "semantic_llm"

    retried_document = _load_rag_document(app, document_id)
    assert retried_document is not None
    assert retried_document.status == "indexed"
    assert retried_document.chunk_strategy == "semantic_llm"
    retried_chunk_count = _count_document_chunks(app, document_id)
    assert retried_chunk_count > 0
    assert retried_chunk_count != first_chunk_count or retried_document.chunk_strategy == "semantic_llm"

    search_response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-reindex", "query": "重新索引测试", "topK": 5, "filters": {}},
        headers=headers,
    )
    assert search_response.status_code == 200
    chunks = search_response.get_json()["data"]["chunks"]
    assert chunks
    assert all(item["metadata"]["document_id"] == document_id for item in chunks)
    assert all(item["metadata"]["chunk_strategy"] == "semantic_llm" for item in chunks)

    list_response = client.get("/api/rag/documents?workspaceId=ws-reindex", headers=headers)
    assert list_response.status_code == 200
    listed_documents = list_response.get_json()["data"]["documents"]
    assert listed_documents[0]["chunkCount"] == retried_chunk_count


def test_rag_reindex_reuses_derived_canonical_asset(client, app, db_session, monkeypatch):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False

    user = _create_user(db_session, "rag-derived-reuse@example.com")
    headers = _auth_headers(client, user.id)
    upload_payload = _upload_text_document(
        client,
        headers,
        "ws-derived",
        "derived.txt",
        "第一段内容。\n\n第二段内容。",
    )
    document_id = int(upload_payload["id"])

    first_job = _index_document(client, headers, "ws-derived", document_id)
    first_job_response = client.get(f"/api/rag/jobs/{first_job['jobId']}?workspaceId=ws-derived", headers=headers)
    assert first_job_response.status_code == 200
    assert first_job_response.get_json()["data"]["status"] == "done"

    stored_document = _load_rag_document(app, document_id)
    assert stored_document is not None
    assert stored_document.derived_text_path
    derived_path = Path(stored_document.derived_text_path)
    assert derived_path.exists()
    derived_blocks = parse_canonical_text(derived_path.read_text(encoding="utf-8"))
    assert derived_blocks

    def _unexpected_load(*args, **kwargs):
        raise AssertionError("reindex should reuse the persisted canonical asset")

    monkeypatch.setattr("app.rag.service.load_source_document", _unexpected_load)
    reindex_response = client.post(
        f"/api/rag/documents/{document_id}/reindex",
        json={"workspaceId": "ws-derived"},
        headers=headers,
    )
    assert reindex_response.status_code == 200
    reindex_job_id = reindex_response.get_json()["data"]["jobId"]
    reindex_job_response = client.get(f"/api/rag/jobs/{reindex_job_id}?workspaceId=ws-derived", headers=headers)
    assert reindex_job_response.status_code == 200
    assert reindex_job_response.get_json()["data"]["status"] == "done"


def test_rag_embedding_debug_endpoint_returns_chunk_vector(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_DEBUG_VISUALIZATION_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0

    user = _create_user(db_session, "rag-embedding-debug@example.com")
    headers = _auth_headers(client, user.id)

    upload_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-embed",
            "file": (io.BytesIO("向量调试接口测试文本。".encode("utf-8")), "embed.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    document_id = upload_response.get_json()["data"]["id"]

    index_response = client.post(
        "/api/rag/index",
        json={"workspaceId": "ws-embed", "documentId": document_id},
        headers=headers,
    )
    assert index_response.status_code == 200
    job_id = index_response.get_json()["data"]["jobId"]

    status = ""
    for _ in range(20):
        job_response = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-embed", headers=headers)
        assert job_response.status_code == 200
        status = job_response.get_json()["data"]["status"]
        if status in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert status == "done"

    search_response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-embed", "query": "根据文档回答", "topK": 3, "filters": {}},
        headers=headers,
    )
    assert search_response.status_code == 200
    chunks = search_response.get_json()["data"]["chunks"]
    assert chunks
    chunk_id = chunks[0]["chunkId"]

    embedding_response = client.get(
        f"/api/rag/embedding?workspaceId=ws-embed&chunkId={chunk_id}&sampleSize=8",
        headers=headers,
    )
    assert embedding_response.status_code == 200
    payload = embedding_response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["chunkId"] == chunk_id
    assert payload["data"]["vectorDimension"] == 8
    assert len(payload["data"]["vectorSample"]) == 8


def test_rag_embedding_debug_endpoint_requires_debug_flag(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_DEBUG_VISUALIZATION_ENABLED"] = False
    user = _create_user(db_session, "rag-embedding-disabled@example.com")
    headers = _auth_headers(client, user.id)
    response = client.get("/api/rag/embedding?workspaceId=ws-any&chunkId=abc", headers=headers)
    assert response.status_code == 404
    payload = response.get_json()
    assert payload["ok"] is False


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


def test_rag_embedder_requires_explicit_provider(app):
    app.config["RAG_EMBEDDER_PROVIDER"] = ""
    with app.app_context():
        with pytest.raises(RAGConfigurationError):
            get_embedder()


def test_rag_embedder_openai_compatible_requires_base_url(app):
    app.config["RAG_EMBEDDER_PROVIDER"] = "openai-compatible"
    app.config["RAG_EMBEDDING_MODEL"] = "Qwen-Embedding"
    app.config["RAG_EMBEDDING_API_KEY"] = "test-key"
    app.config["RAG_EMBEDDING_DIMENSION"] = 8
    app.config["RAG_EMBEDDING_BASE_URL"] = ""
    with app.app_context():
        with pytest.raises(RAGConfigurationError):
            get_embedder()


def test_rag_reranker_requires_explicit_provider(app):
    app.config["RAG_RERANKER_PROVIDER"] = ""
    with app.app_context():
        with pytest.raises(RAGConfigurationError):
            get_reranker()


def test_rag_reranker_openai_compatible_requires_base_url(app):
    app.config["RAG_RERANKER_PROVIDER"] = "openai-compatible"
    app.config["RAG_RERANKER_MODEL"] = "qwen-reranker-v1"
    app.config["RAG_RERANKER_API_KEY"] = "test-key"
    app.config["RAG_RERANKER_BASE_URL"] = ""
    with app.app_context():
        with pytest.raises(RAGConfigurationError):
            get_reranker()


def test_rag_graph_decision_and_citation_contract():
    from app.agent.graph.nodes import answer_with_citations_node, plan_route_node

    decision = plan_route_node(
        {
            "user_message": "请根据文档回答",
            "rag_enabled": True,
            "web_enabled": False,
            "mcp_enabled": False,
        }
    )
    assert decision["needs_search"] is True

    file_decision = plan_route_node(
        {
            "user_message": "文件里现在全球科技股的情况怎么样",
            "rag_enabled": True,
            "web_enabled": True,
            "mcp_enabled": False,
        }
    )
    assert file_decision["needs_search"] is True

    with pytest.raises(RAGContractError):
        answer_with_citations_node(
            {
                "rag_chunks": [{"chunk_id": "abc123", "source": "", "score": 0.9}],
                "reply": "placeholder",
                "rag_debug_enabled": False,
                "debug": {},
            }
        )


def test_rag_upload_rejects_disallowed_chunking_strategy(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_CHUNK_STRATEGY_ALLOWED"] = ("paragraph",)
    user = _create_user(db_session, "rag-chunk-invalid@example.com")
    headers = _auth_headers(client, user.id)

    response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-invalid",
            "chunking": '{"strategy":"semantic_llm"}',
            "file": (io.BytesIO("text".encode("utf-8")), "invalid.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "allowed" in payload["error"]


def test_semantic_chunking_output_normalization(app, tmp_path: Path):
    app.config["RAG_CHUNK_AI_PROVIDER"] = "noop"
    app.config["RAG_CHUNK_STRATEGY_ALLOWED"] = ("paragraph", "semantic_llm")
    app.config["RAG_CHUNK_STRATEGY_DEFAULT"] = "semantic_llm"
    app.config["RAG_CHUNK_SEMANTIC_MAX_TOKENS"] = 40
    app.config["RAG_CHUNK_SEMANTIC_MIN_TOKENS"] = 4
    app.config["RAG_CHUNK_VERSION"] = "v2"

    sample = tmp_path / "semantic.txt"
    sample.write_text("第一段。第二段。第三段。第四段。第五段。", encoding="utf-8")
    with app.app_context():
        payloads, applied = parse_and_chunk_document(
            file_path=str(sample),
            extension="txt",
            document_id=99,
            source_name="semantic.txt",
            chunker=get_chunker(),
            semantic_provider=get_semantic_chunking_provider(),
            chunking_request=ChunkingRequest(
                strategy="semantic_llm",
                version="v2",
                target_tokens=20,
                max_tokens=40,
                overlap_tokens=0,
                min_tokens=4,
            ),
            chunk_size=1200,
            overlap=150,
        )
    assert applied.strategy == "semantic_llm"
    assert applied.fallback_used is False
    assert payloads
    assert all(item.metadata.get("chunk_strategy") == "semantic_llm" for item in payloads)
    assert all(isinstance(item.metadata.get("token_count"), int) for item in payloads)
    assert all(isinstance(item.metadata.get("semantic_segment_id"), str) for item in payloads)
    assert all(isinstance(item.metadata.get("semantic_sentence_index"), int) for item in payloads)
    assert all(isinstance(item.metadata.get("semantic_segment_text"), str) for item in payloads)


def test_semantic_chunking_fallback_execution(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
    app.config["RAG_RETRIEVAL_SCORE_THRESHOLD"] = -10.0
    app.config["RAG_CHUNK_AI_PROVIDER"] = "openai-compatible"
    app.config["RAG_CHUNK_AI_BASE_URL"] = ""
    app.config["RAG_CHUNK_AI_API_KEY"] = ""
    app.config["RAG_CHUNK_STRATEGY_ALLOWED"] = ("paragraph", "semantic_llm")
    app.config["RAG_CHUNK_FALLBACK_STRATEGY"] = "paragraph"

    user = _create_user(db_session, "rag-chunk-fallback@example.com")
    headers = _auth_headers(client, user.id)

    upload_response = client.post(
        "/api/rag/upload",
        data={
            "workspaceId": "ws-fallback",
            "chunking": '{"strategy":"semantic_llm"}',
            "file": (io.BytesIO("测试语义分块回退路径。".encode("utf-8")), "fallback.txt"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200
    doc_id = upload_response.get_json()["data"]["id"]

    index_response = client.post(
        "/api/rag/index",
        json={"workspaceId": "ws-fallback", "documentId": doc_id, "chunking": {"strategy": "semantic_llm"}},
        headers=headers,
    )
    assert index_response.status_code == 200
    job_id = index_response.get_json()["data"]["jobId"]

    job_response = client.get(f"/api/rag/jobs/{job_id}?workspaceId=ws-fallback", headers=headers)
    assert job_response.status_code == 200
    chunking = job_response.get_json()["data"]["chunkingApplied"]
    assert chunking["requestedStrategy"] == "semantic_llm"
    assert chunking["strategy"] == "semantic_llm"
    assert chunking["fallbackUsed"] is True
    assert isinstance(chunking["fallbackReason"], str) and chunking["fallbackReason"]

    search_response = client.post(
        "/api/rag/search",
        json={"workspaceId": "ws-fallback", "query": "语义分块回退", "topK": 3, "filters": {}},
        headers=headers,
    )
    assert search_response.status_code == 200
    chunks = search_response.get_json()["data"]["chunks"]
    assert chunks
    metadata = chunks[0]["metadata"]
    assert metadata["chunk_strategy"] == "semantic_llm"
    assert metadata["semantic_segment_source"] == "paragraph"
    semantic_segment = chunks[0]["semanticSegment"]
    assert isinstance(semantic_segment, dict)
    assert semantic_segment["source"] == "paragraph"
    assert isinstance(semantic_segment["text"], str) and semantic_segment["text"]


def test_markdown_fileloader_normalizes_structured_text(app, tmp_path: Path):
    sample = tmp_path / "notes.md"
    sample.write_text(
        "# Overview\n"
        "- item A\n"
        "- item B\n\n"
        "| Plan | Price |\n"
        "| --- | --- |\n"
        "| Pro | 20 |\n\n"
        "```python\n"
        "print('hello')\n"
        "```\n",
        encoding="utf-8",
    )

    with app.app_context():
        loaded = load_source_document(path=sample, extension="md", source_name="notes.md")

    assert loaded.loader_type == "markdown"
    assert loaded.extraction_method == "structured_markdown"
    assert loaded.blocks
    rendered = "\n".join(block.text for block in loaded.blocks)
    assert "Section: Overview" in rendered
    assert "- item A" in rendered
    assert "Row: Plan, Price" in rendered
    assert "Row: Pro, 20" in rendered
    assert "Code block: python" in rendered
    assert "# Overview" not in rendered
    assert "| Pro | 20 |" not in rendered


def test_pdf_fileloader_prefers_native_text_and_falls_back_to_ocr(app, tmp_path: Path, monkeypatch):
    class _FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [
                _FakePage("This page has enough native text to skip OCR."),
                _FakePage(""),
            ]

    sample = tmp_path / "native-plus-ocr.pdf"
    sample.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)
    monkeypatch.setattr("app.rag.fileloaders.pdf_loader._render_pdf_page_png", lambda *_args, **_kwargs: b"png")

    with app.app_context():
        loaded = load_source_document(path=sample, extension="pdf", source_name="native-plus-ocr.pdf")

    assert loaded.loader_type == "pdf"
    assert loaded.extraction_method == "mixed"
    assert loaded.ocr_used is True
    assert loaded.ocr_provider == "fake"
    assert len(loaded.blocks) == 2
    assert loaded.blocks[0].metadata["extraction_method"] == "native"
    assert loaded.blocks[1].metadata["extraction_method"] == "ocr"
    assert loaded.blocks[1].text == "OCR text for native-plus-ocr.pdf page 2"


def test_pdf_fileloader_fails_when_ocr_is_required_but_unavailable(app, tmp_path: Path, monkeypatch):
    class _FakePage:
        def extract_text(self) -> str:
            return ""

    class _FakeReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.pages = [_FakePage()]

    sample = tmp_path / "ocr-required.pdf"
    sample.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)
    app.config["RAG_OCR_PROVIDER"] = "disabled"

    with app.app_context():
        with pytest.raises(Exception) as exc_info:
            load_source_document(path=sample, extension="pdf", source_name="ocr-required.pdf")
    assert "ocr required" in str(exc_info.value).lower()


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._raw


def test_openai_compatible_embedder_normalizes_and_sorts_response(app, monkeypatch):
    app.config["RAG_EMBEDDER_PROVIDER"] = "openai-compatible"
    app.config["RAG_EMBEDDING_MODEL"] = "Qwen-Embedding-8B"
    app.config["RAG_EMBEDDING_VERSION"] = "1"
    app.config["RAG_EMBEDDING_DIMENSION"] = 3
    app.config["RAG_EMBEDDING_API_KEY"] = "test-key"
    app.config["RAG_EMBEDDING_BASE_URL"] = "http://example.test/v1"
    app.config["RAG_EMBEDDING_TIMEOUT_SECONDS"] = 5
    payload = {
        "data": [
            {"index": 1, "embedding": [0.0, 0.0, 2.0]},
            {"index": 0, "embedding": [3.0, 4.0, 0.0]},
        ]
    }
    monkeypatch.setattr("app.rag.providers.langchain_embedder.urllib_request.urlopen", lambda *_args, **_kwargs: _FakeHTTPResponse(payload))
    with app.app_context():
        embedder = get_embedder()
        vectors = embedder.embed_documents(["first", "second"])
    assert vectors[0] == [0.6, 0.8, 0.0]
    assert vectors[1] == [0.0, 0.0, 1.0]


def test_openai_compatible_reranker_sorts_hits_by_score(app, monkeypatch):
    app.config["RAG_RERANKER_PROVIDER"] = "openai-compatible"
    app.config["RAG_RERANKER_MODEL"] = "qwen-reranker-v1"
    app.config["RAG_RERANKER_API_KEY"] = "test-key"
    app.config["RAG_RERANKER_BASE_URL"] = "http://example.test/v1"
    app.config["RAG_RERANKER_TIMEOUT_SECONDS"] = 5
    payload = {
        "data": [
            {"index": 1, "relevance_score": 0.91},
            {"index": 0, "relevance_score": 0.22},
        ]
    }
    monkeypatch.setattr("app.rag.providers.langchain_reranker.urllib_request.urlopen", lambda *_args, **_kwargs: _FakeHTTPResponse(payload))
    hits = [
        RetrievalHit(
            chunk_id="c1",
            score=0.1,
            source="a.txt",
            page=None,
            section=None,
            content="doc-1",
            metadata={},
        ),
        RetrievalHit(
            chunk_id="c2",
            score=0.1,
            source="b.txt",
            page=None,
            section=None,
            content="doc-2",
            metadata={},
        ),
    ]
    with app.app_context():
        reranker = get_reranker()
        ranked = reranker.rerank(query="q", hits=hits, top_k=2)
    assert [item.chunk_id for item in ranked] == ["c2", "c1"]


def test_openai_semantic_provider_rejects_non_verbatim_segment(monkeypatch):
    provider = OpenAICompatibleSemanticChunkingProvider(
        model_name="semantic-chunker-v1",
        api_key="test-key",
        base_url="http://example.test",
        timeout_seconds=5,
    )
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "segments": [
                                {
                                    "text": "这是对合同关键条款的总结",
                                    "block_index": 0,
                                    "metadata": {},
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }
    monkeypatch.setattr("app.rag.providers.semantic_chunking_provider.urllib_request.urlopen", lambda *_args, **_kwargs: _FakeHTTPResponse(payload))

    with pytest.raises(Exception) as exc_info:
        provider.segment(
            strategy="semantic_llm",
            source_name="contract.txt",
            blocks=[{"text": "本合同关键条款包括付款周期和违约责任。", "metadata": {"source": "contract.txt"}}],
        )
    assert "verbatim span" in str(exc_info.value)


def test_openai_semantic_provider_aligns_verbatim_segment_with_offsets(monkeypatch):
    provider = OpenAICompatibleSemanticChunkingProvider(
        model_name="semantic-chunker-v1",
        api_key="test-key",
        base_url="http://example.test",
        timeout_seconds=5,
    )
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "segments": [
                                {
                                    "text": "付款周期和违约责任",
                                    "block_index": 0,
                                    "metadata": {"section": "条款摘要"},
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }
    monkeypatch.setattr("app.rag.providers.semantic_chunking_provider.urllib_request.urlopen", lambda *_args, **_kwargs: _FakeHTTPResponse(payload))

    source_text = "本合同关键条款包括付款周期和违约责任。"
    segments = provider.segment(
        strategy="semantic_llm",
        source_name="contract.txt",
        blocks=[{"text": source_text, "metadata": {"source": "contract.txt"}}],
    )
    assert len(segments) == 1
    segment = segments[0]
    assert segment.text == "付款周期和违约责任"
    assert segment.summary is None
    assert segment.metadata["block_index"] == 0
    assert source_text[segment.metadata["offset_start"] : segment.metadata["offset_end"]] == segment.text


def test_search_plan_keeps_rag_when_private_retrieval_is_heuristically_required():
    class _StructuredLLM:
        def invoke(self, messages):
            from types import SimpleNamespace

            return SimpleNamespace(strategy="public_only", use_rag=False, use_web=False)

    class _LLM:
        def with_structured_output(self, schema):
            return _StructuredLLM()

    result = _search_plan_node(
        {
            "llm": _LLM(),
            "query": "根据文档说明结论",
            "rag_enabled": True,
            "preferred_strategy": "private_first",
        }
    )

    assert result["use_rag"] is True
    assert result["strategy"] in {"private_first", "private_only", "hybrid"}


def test_search_plan_avoids_rag_for_explicit_public_web_request():
    class _StructuredLLM:
        def invoke(self, messages):
            from types import SimpleNamespace

            return SimpleNamespace(strategy="hybrid", use_rag=True, use_web=True)

    class _LLM:
        def with_structured_output(self, schema):
            return _StructuredLLM()

    result = _search_plan_node(
        {
            "llm": _LLM(),
            "query": "帮我上网搜索一下京东方这个公司的情况",
            "rag_enabled": True,
            "preferred_strategy": "",
        }
    )

    assert result["strategy"] == "public_only"
    assert result["use_rag"] is False
    assert result["use_web"] is True


def test_search_plan_uses_hybrid_for_explicit_mixed_source_request():
    result = _search_plan_node(
        {
            "llm": object(),
            "query": "结合文档和网上信息总结京东方这个公司的情况",
            "rag_enabled": True,
            "preferred_strategy": "",
        }
    )

    assert result["strategy"] == "hybrid"
    assert result["use_rag"] is True
    assert result["use_web"] is True
