import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(values)


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


def _default_dev_origins_from_port(port: str) -> str:
    clean_port = port.strip() or "5173"
    return f"http://127.0.0.1:{clean_port},http://localhost:{clean_port}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:123456@127.0.0.1:3306/app")

    SESSION_TYPE = os.getenv("SESSION_TYPE", "filesystem")
    SESSION_FILE_DIR = os.getenv("SESSION_FILE_DIR", "sessions")
    SESSION_PERMANENT = os.getenv("SESSION_PERMANENT", "true").lower() == "true"
    SESSION_LIFETIME_DAYS = int(os.getenv("SESSION_LIFETIME_DAYS", "7"))
    PERMANENT_SESSION_LIFETIME = timedelta(days=SESSION_LIFETIME_DAYS)
    SESSION_REFRESH_EACH_REQUEST = os.getenv("SESSION_REFRESH_EACH_REQUEST", "true").lower() == "true"
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    CSRF_HEADER_NAME = os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token")
    CORS_ENABLED = _bool_env("CORS_ENABLED", True)
    CORS_ALLOW_CREDENTIALS = _bool_env("CORS_ALLOW_CREDENTIALS", True)
    FRONTEND_DEV_PORT = os.getenv("FRONTEND_DEV_PORT", "5173")
    CORS_ALLOWED_ORIGINS = _csv_env(
        "CORS_ALLOWED_ORIGINS",
        _default_dev_origins_from_port(FRONTEND_DEV_PORT),
    )
    CORS_ALLOWED_METHODS = _csv_env(
        "CORS_ALLOWED_METHODS",
        "GET,POST,PUT,PATCH,DELETE,OPTIONS",
    )
    CORS_ALLOWED_HEADERS = _csv_env(
        "CORS_ALLOWED_HEADERS",
        "Content-Type,X-CSRF-Token,Authorization",
    )
    CORS_EXPOSE_HEADERS = _csv_env("CORS_EXPOSE_HEADERS", "")
    CORS_MAX_AGE_SECONDS = int(os.getenv("CORS_MAX_AGE_SECONDS", "600"))

    CODE_TTL_SECONDS = int(os.getenv("CODE_TTL_SECONDS", "600"))
    CODE_RESEND_COOLDOWN_SECONDS = int(os.getenv("CODE_RESEND_COOLDOWN_SECONDS", "60"))
    CODE_LOCKOUT_SECONDS = int(os.getenv("CODE_LOCKOUT_SECONDS", "600"))
    CODE_MAX_ATTEMPTS = int(os.getenv("CODE_MAX_ATTEMPTS", "5"))
    MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))
    NICKNAME_MAX_LENGTH = int(os.getenv("NICKNAME_MAX_LENGTH", "32"))

    AVATAR_UPLOAD_DIR = os.getenv("AVATAR_UPLOAD_DIR", "uploads/avatars")
    AVATAR_BASE_URL = os.getenv("AVATAR_BASE_URL", "/uploads/avatars")
    MAX_AVATAR_BYTES = int(os.getenv("MAX_AVATAR_BYTES", str(2 * 1024 * 1024)))
    ALLOWED_AVATAR_EXTENSIONS = {
        ext.strip().lower()
        for ext in os.getenv("ALLOWED_AVATAR_EXTENSIONS", "jpg,jpeg,png,webp").split(",")
        if ext.strip()
    }

    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")  # console | smtp | memory
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@example.com")
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()  # ssl | starttls | none

    AI_PROVIDER = os.getenv("AI_PROVIDER", "")
    AI_MODEL = os.getenv("AI_MODEL", "")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "")
    AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    AGENT_MAIN_AI_PROVIDER = os.getenv("AGENT_MAIN_AI_PROVIDER", "").strip().lower()
    AGENT_MAIN_AI_MODEL = os.getenv("AGENT_MAIN_AI_MODEL", "").strip()
    AGENT_MAIN_AI_API_KEY = os.getenv("AGENT_MAIN_AI_API_KEY", "").strip()
    AGENT_MAIN_AI_BASE_URL = os.getenv("AGENT_MAIN_AI_BASE_URL", "").strip()
    AGENT_MAIN_AI_TIMEOUT_SECONDS = int(os.getenv("AGENT_MAIN_AI_TIMEOUT_SECONDS", str(AI_TIMEOUT_SECONDS)))
    AGENT_SEARCH_AI_PROVIDER = os.getenv("AGENT_SEARCH_AI_PROVIDER", "").strip().lower()
    AGENT_SEARCH_AI_MODEL = os.getenv("AGENT_SEARCH_AI_MODEL", "").strip()
    AGENT_SEARCH_AI_API_KEY = os.getenv("AGENT_SEARCH_AI_API_KEY", "").strip()
    AGENT_SEARCH_AI_BASE_URL = os.getenv("AGENT_SEARCH_AI_BASE_URL", "").strip()
    AGENT_SEARCH_AI_TIMEOUT_SECONDS = int(os.getenv("AGENT_SEARCH_AI_TIMEOUT_SECONDS", str(AI_TIMEOUT_SECONDS)))
    AGENT_MCP_AI_PROVIDER = os.getenv("AGENT_MCP_AI_PROVIDER", "").strip().lower()
    AGENT_MCP_AI_MODEL = os.getenv("AGENT_MCP_AI_MODEL", "").strip()
    AGENT_MCP_AI_API_KEY = os.getenv("AGENT_MCP_AI_API_KEY", "").strip()
    AGENT_MCP_AI_BASE_URL = os.getenv("AGENT_MCP_AI_BASE_URL", "").strip()
    AGENT_MCP_AI_TIMEOUT_SECONDS = int(os.getenv("AGENT_MCP_AI_TIMEOUT_SECONDS", str(AI_TIMEOUT_SECONDS)))
    AGENT_AUTO_TOOL_SELECTION_ENABLED = _bool_env("AGENT_AUTO_TOOL_SELECTION_ENABLED", True)
    AGENT_TOOL_CALL_MAX_ROUNDS = int(os.getenv("AGENT_TOOL_CALL_MAX_ROUNDS", "4"))
    AGENT_WEBSEARCH_ENABLED = _bool_env("AGENT_WEBSEARCH_ENABLED", False)
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
    TAVILY_BASE_URL = os.getenv("TAVILY_BASE_URL", "https://api.tavily.com/search").strip()
    TAVILY_TIMEOUT_SECONDS = int(os.getenv("TAVILY_TIMEOUT_SECONDS", "15"))
    AGENT_MCP_ENABLED = _bool_env("AGENT_MCP_ENABLED", False)
    AGENT_MCP_SERVERS_JSON = os.getenv("AGENT_MCP_SERVERS_JSON", "").strip()
    AGENT_MCP_TIMEOUT_SECONDS = int(os.getenv("AGENT_MCP_TIMEOUT_SECONDS", "20"))
    AGENT_KNOWLEDGE_GRAPH_ENABLED = _bool_env("AGENT_KNOWLEDGE_GRAPH_ENABLED", False)
    AGENT_KNOWLEDGE_GRAPH_DIRECT_ONLY = _bool_env("AGENT_KNOWLEDGE_GRAPH_DIRECT_ONLY", False)
    AGENT_TRACE_VISUALIZATION_ENABLED = _bool_env("AGENT_TRACE_VISUALIZATION_ENABLED", False)
    AGENT_TRACE_DEBUG_DETAILS_ENABLED = _bool_env("AGENT_TRACE_DEBUG_DETAILS_ENABLED", False)

    BANKRUPTCY_ANALYSIS_ENABLED = _bool_env("BANKRUPTCY_ANALYSIS_ENABLED", False)
    BANKRUPTCY_MODEL_PATH = os.getenv(
        "BANKRUPTCY_MODEL_PATH",
        "assets/bankruptcy/model/xgb_borderline_smote.pkl",
    )
    BANKRUPTCY_SCALER_PATH = os.getenv(
        "BANKRUPTCY_SCALER_PATH",
        "assets/bankruptcy/model/scaler_borderline_smote.pkl",
    )
    BANKRUPTCY_THRESHOLD = _float_env("BANKRUPTCY_THRESHOLD", 0.63)
    BANKRUPTCY_TOP_FEATURE_COUNT = int(os.getenv("BANKRUPTCY_TOP_FEATURE_COUNT", "10"))
    BANKRUPTCY_UPLOAD_DIR = os.getenv("BANKRUPTCY_UPLOAD_DIR", "uploads/bankruptcy/csv")
    BANKRUPTCY_PLOT_DIR = os.getenv("BANKRUPTCY_PLOT_DIR", "uploads/bankruptcy")

    RAG_ENABLED = _bool_env("RAG_ENABLED", False)
    RAG_DEBUG_VISUALIZATION_ENABLED = _bool_env("RAG_DEBUG_VISUALIZATION_ENABLED", False)
    RAG_VECTOR_PROVIDER = os.getenv("RAG_VECTOR_PROVIDER", "chromadb").strip().lower()
    RAG_EMBEDDER_PROVIDER = os.getenv("RAG_EMBEDDER_PROVIDER", "").strip().lower()
    RAG_RERANKER_PROVIDER = os.getenv("RAG_RERANKER_PROVIDER", "").strip().lower()
    RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "")
    RAG_EMBEDDING_VERSION = os.getenv("RAG_EMBEDDING_VERSION", "1")
    RAG_EMBEDDING_DIMENSION = int(os.getenv("RAG_EMBEDDING_DIMENSION", "128"))
    RAG_EMBEDDING_API_KEY = os.getenv("RAG_EMBEDDING_API_KEY", "").strip()
    RAG_EMBEDDING_BASE_URL = os.getenv("RAG_EMBEDDING_BASE_URL", "").strip()
    RAG_EMBEDDING_TIMEOUT_SECONDS = int(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "20"))
    RAG_RERANKER_MODEL = os.getenv("RAG_RERANKER_MODEL", "").strip()
    RAG_RERANKER_API_KEY = os.getenv("RAG_RERANKER_API_KEY", "").strip()
    RAG_RERANKER_BASE_URL = os.getenv("RAG_RERANKER_BASE_URL", "").strip()
    RAG_RERANKER_TIMEOUT_SECONDS = int(os.getenv("RAG_RERANKER_TIMEOUT_SECONDS", "20"))
    RAG_RETRIEVAL_TOP_K = int(os.getenv("RAG_RETRIEVAL_TOP_K", "5"))
    RAG_RETRIEVAL_SCORE_THRESHOLD = _float_env("RAG_RETRIEVAL_SCORE_THRESHOLD", 0.0)
    RAG_ALLOWED_FILE_TYPES = _csv_env("RAG_ALLOWED_FILE_TYPES", "pdf,docx,md,txt")
    RAG_UPLOAD_DIR = os.getenv("RAG_UPLOAD_DIR", "uploads/rag")
    RAG_FILELOADER_VERSION = os.getenv("RAG_FILELOADER_VERSION", "v1").strip()
    RAG_AUTO_INDEX_ON_UPLOAD = _bool_env("RAG_AUTO_INDEX_ON_UPLOAD", True)
    RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1200"))
    RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
    RAG_CHUNK_STRATEGY_DEFAULT = os.getenv("RAG_CHUNK_STRATEGY_DEFAULT", "paragraph").strip().lower()
    RAG_CHUNK_STRATEGY_ALLOWED = _csv_env(
        "RAG_CHUNK_STRATEGY_ALLOWED",
        "paragraph,semantic_llm",
    )
    RAG_CHUNK_FALLBACK_STRATEGY = os.getenv("RAG_CHUNK_FALLBACK_STRATEGY", "paragraph").strip().lower()
    RAG_CHUNK_VERSION = os.getenv("RAG_CHUNK_VERSION", "v1").strip()
    RAG_CHUNK_SEMANTIC_TARGET_TOKENS = int(os.getenv("RAG_CHUNK_SEMANTIC_TARGET_TOKENS", "450"))
    RAG_CHUNK_SEMANTIC_MAX_TOKENS = int(os.getenv("RAG_CHUNK_SEMANTIC_MAX_TOKENS", "700"))
    RAG_CHUNK_SEMANTIC_OVERLAP_TOKENS = int(os.getenv("RAG_CHUNK_SEMANTIC_OVERLAP_TOKENS", "50"))
    RAG_CHUNK_SEMANTIC_MIN_TOKENS = int(os.getenv("RAG_CHUNK_SEMANTIC_MIN_TOKENS", "120"))
    RAG_CHUNK_AI_PROVIDER = os.getenv("RAG_CHUNK_AI_PROVIDER", "noop").strip().lower()
    RAG_CHUNK_AI_MODEL = os.getenv("RAG_CHUNK_AI_MODEL", "semantic-chunker-v1").strip()
    RAG_CHUNK_AI_API_KEY = os.getenv("RAG_CHUNK_AI_API_KEY", "").strip()
    RAG_CHUNK_AI_BASE_URL = os.getenv("RAG_CHUNK_AI_BASE_URL", "").strip()
    RAG_CHUNK_AI_TIMEOUT_SECONDS = int(os.getenv("RAG_CHUNK_AI_TIMEOUT_SECONDS", "20"))
    RAG_OCR_PROVIDER = os.getenv("RAG_OCR_PROVIDER", "openai-compatible").strip().lower()
    RAG_OCR_MODEL = os.getenv("RAG_OCR_MODEL", "").strip()
    RAG_OCR_API_KEY = os.getenv("RAG_OCR_API_KEY", "").strip()
    RAG_OCR_BASE_URL = os.getenv("RAG_OCR_BASE_URL", "").strip()
    RAG_OCR_TIMEOUT_SECONDS = int(os.getenv("RAG_OCR_TIMEOUT_SECONDS", "20"))
    RAG_INDEX_MAX_WORKERS = int(os.getenv("RAG_INDEX_MAX_WORKERS", "2"))
    RAG_CHROMADB_PERSIST_DIR = os.getenv("RAG_CHROMADB_PERSIST_DIR", "uploads/chromadb")
    RAG_CHROMADB_COLLECTION_PREFIX = os.getenv("RAG_CHROMADB_COLLECTION_PREFIX", "rag")

    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"
