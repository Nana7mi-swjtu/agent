import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import text

from app import create_app
from app.db import get_session

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


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
    bankruptcy_upload_dir = tmp_path / "bankruptcy_csv"
    bankruptcy_upload_dir.mkdir(parents=True, exist_ok=True)
    bankruptcy_plot_dir = tmp_path / "bankruptcy_plots"
    bankruptcy_plot_dir.mkdir(parents=True, exist_ok=True)
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "DATABASE_URL": test_db_url,
        "AUTO_CREATE_DB": True,
        "TESTING": True,
        "LOG_DIR": str(log_dir),
        "LOG_LEVEL": "INFO",
        "LOG_SERVICE_NAME": "agent-test",
        "LOG_ENVIRONMENT": "test",
        "LOG_MAX_BYTES": 1024 * 1024,
        "LOG_BACKUP_COUNT": 2,
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
        "RAG_ALLOWED_FILE_TYPES": ("pdf", "docx", "md", "txt"),
        "RAG_FILELOADER_VERSION": "v1",
        "RAG_OCR_PROVIDER": "fake",
        "RAG_OCR_MODEL": "fake-ocr",
        "RAG_OCR_API_KEY": "",
        "RAG_OCR_BASE_URL": "",
        "RAG_CHROMADB_PERSIST_DIR": str(rag_chroma_dir),
        "RAG_CHROMADB_COLLECTION_PREFIX": "test_rag",
        "RAG_CHUNK_STRATEGY_DEFAULT": "paragraph",
        "RAG_CHUNK_STRATEGY_ALLOWED": ("paragraph", "semantic_llm"),
        "RAG_CHUNK_FALLBACK_STRATEGY": "paragraph",
        "BANKRUPTCY_ANALYSIS_ENABLED": True,
        "BANKRUPTCY_MODEL_PATH": "assets/bankruptcy/model/xgb_borderline_smote.pkl",
        "BANKRUPTCY_SCALER_PATH": "assets/bankruptcy/model/scaler_borderline_smote.pkl",
        "BANKRUPTCY_UPLOAD_DIR": str(bankruptcy_upload_dir),
        "BANKRUPTCY_PLOT_DIR": str(bankruptcy_plot_dir),
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
            session.execute(text("DELETE FROM agent_chat_jobs"))
            session.execute(text("DELETE FROM agent_conversation_messages"))
            session.execute(text("DELETE FROM agent_conversation_threads"))
            session.execute(text("DELETE FROM analysis_reports"))
            session.execute(text("DELETE FROM analysis_module_artifacts"))
            session.execute(text("DELETE FROM analysis_sessions"))
            session.execute(text("DELETE FROM rag_query_logs"))
            session.execute(text("DELETE FROM rag_index_jobs"))
            session.execute(text("DELETE FROM rag_chunks"))
            session.execute(text("DELETE FROM rag_documents"))
            session.execute(text("DELETE FROM robotics_insight_runs"))
            session.execute(text("DELETE FROM robotics_policy_documents"))
            session.execute(text("DELETE FROM robotics_cninfo_announcements"))
            session.execute(text("DELETE FROM robotics_bidding_documents"))
            session.execute(text("DELETE FROM robotics_listed_company_profiles"))
            session.execute(text("DELETE FROM bankruptcy_analysis_records"))
            session.execute(text("DELETE FROM email_codes"))
            session.execute(text("DELETE FROM users"))
            session.commit()
            yield session
        finally:
            session.close()
