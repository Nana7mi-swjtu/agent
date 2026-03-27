import os

import pytest
from sqlalchemy import text

from app import create_app
from app.db import get_session


@pytest.fixture
def app(tmp_path):
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        pytest.skip("TEST_DATABASE_URL is required for MySQL tests")
    if not test_db_url.startswith("mysql"):
        pytest.skip("TEST_DATABASE_URL must be a MySQL connection string")

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    rag_upload_dir = tmp_path / "rag_uploads"
    rag_upload_dir.mkdir(parents=True, exist_ok=True)
    rag_chroma_dir = tmp_path / "chromadb"
    rag_chroma_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "DATABASE_URL": test_db_url,
        "AUTO_CREATE_DB": True,
        "TESTING": True,
        "EMAIL_BACKEND": "memory",
        "SESSION_TYPE": "filesystem",
        "SESSION_FILE_DIR": str(session_dir),
        "SECRET_KEY": "test-secret",
        "CORS_ENABLED": True,
        "CORS_ALLOWED_ORIGINS": ("http://localhost:4273",),
        "CORS_ALLOW_CREDENTIALS": True,
        "RAG_EMBEDDER_PROVIDER": "fake",
        "RAG_EMBEDDING_MODEL": "fake-embeddings",
        "RAG_EMBEDDING_VERSION": "1",
        "RAG_EMBEDDING_DIMENSION": 8,
        "RAG_EMBEDDING_API_KEY": "",
        "RAG_RERANKER_PROVIDER": "fake",
        "RAG_RERANKER_MODEL": "",
        "RAG_UPLOAD_DIR": str(rag_upload_dir),
        "RAG_CHROMADB_PERSIST_DIR": str(rag_chroma_dir),
        "RAG_CHROMADB_COLLECTION_PREFIX": "test_rag",
        "RAG_CHUNK_STRATEGY_DEFAULT": "paragraph",
        "RAG_CHUNK_STRATEGY_ALLOWED": ("paragraph", "semantic_llm"),
        "RAG_CHUNK_FALLBACK_STRATEGY": "paragraph",
    }
    app = create_app(config)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db_session(app):
    with app.app_context():
        session = get_session()
        try:
            session.execute(text("DELETE FROM rag_query_logs"))
            session.execute(text("DELETE FROM rag_index_jobs"))
            session.execute(text("DELETE FROM rag_chunks"))
            session.execute(text("DELETE FROM rag_documents"))
            session.execute(text("DELETE FROM email_codes"))
            session.execute(text("DELETE FROM users"))
            session.commit()
            yield session
        finally:
            session.close()
