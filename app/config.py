import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(values)


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
    CORS_ALLOWED_ORIGINS = _csv_env(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:4273,http://127.0.0.1:4273",
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

    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"
