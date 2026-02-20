import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:123456@127.0.0.1:3306/app")

    SESSION_TYPE = os.getenv("SESSION_TYPE", "filesystem")
    SESSION_FILE_DIR = os.getenv("SESSION_FILE_DIR", "sessions")
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    CODE_TTL_SECONDS = int(os.getenv("CODE_TTL_SECONDS", "600"))
    CODE_RESEND_COOLDOWN_SECONDS = int(os.getenv("CODE_RESEND_COOLDOWN_SECONDS", "60"))
    CODE_LOCKOUT_SECONDS = int(os.getenv("CODE_LOCKOUT_SECONDS", "600"))
    CODE_MAX_ATTEMPTS = int(os.getenv("CODE_MAX_ATTEMPTS", "5"))
    MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))

    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")  # console | smtp | memory
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@example.com")

    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"
