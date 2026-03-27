from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app.rag.errors import RAGConfigurationError, RAGContractError
from app.rag.pipeline.indexer import parse_and_chunk_document
from app.rag.providers.semantic_chunking_provider import OpenAICompatibleSemanticChunkingProvider
from app.rag.providers.registry import get_chunker, get_embedder, get_reranker, get_semantic_chunking_provider
from app.rag.providers.registry import get_vector_store
from app.rag.schemas import ChunkingRequest, RetrievalHit
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

    documents_response = client.get("/api/rag/documents?workspaceId=ws-flow", headers=headers)
    assert documents_response.status_code == 200
    docs = documents_response.get_json()["data"]["documents"]
    assert docs
    assert docs[0]["chunkingApplied"]["strategy"] == "paragraph"


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


def test_semantic_chunking_fallback_execution(client, app, db_session):
    app.config["RAG_ENABLED"] = True
    app.config["RAG_AUTO_INDEX_ON_UPLOAD"] = False
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
    assert chunking["strategy"] == "paragraph"
    assert chunking["fallbackUsed"] is True
    assert isinstance(chunking["fallbackReason"], str) and chunking["fallbackReason"]


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
