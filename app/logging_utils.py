from __future__ import annotations

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ACCESS_LOGGER_NAME = "access"
AUDIT_LOGGER_NAME = "audit"
APP_LOGGER_NAME = "app"
REQUEST_ID_HEADER = "X-Request-ID"

_context_fields = (
    "request_id",
    "user_id",
    "workspace_id",
    "job_id",
    "document_id",
    "record_id",
    "remote_addr",
    "method",
    "path",
)
_sensitive_field_names = {
    "password",
    "password_hash",
    "old_password",
    "new_password",
    "confirm_password",
    "code",
    "verification_code",
    "reset_code",
    "api_key",
    "authorization",
    "authorization_header",
    "smtp_password",
    "token",
    "csrf_token",
}
_default_log_context: dict[str, Any] = {field: None for field in _context_fields}
_log_context: ContextVar[dict[str, Any]] = ContextVar("app_log_context", default=_default_log_context.copy())
_log_record_reserved = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
    "service",
    "environment",
    "event",
    "exception_type",
    "stacktrace",
}


def bind_log_context(**kwargs: Any) -> dict[str, Any]:
    current = dict(_log_context.get())
    for key, value in kwargs.items():
        if key in _context_fields:
            current[key] = value
    _log_context.set(current)
    return current


def clear_log_context() -> None:
    _log_context.set(_default_log_context.copy())


def get_log_context() -> dict[str, Any]:
    return dict(_log_context.get())


def snapshot_log_context() -> dict[str, Any]:
    return get_log_context()


def run_with_log_context(snapshot: Mapping[str, Any], func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    previous = _log_context.get()
    _log_context.set({field: snapshot.get(field) for field in _context_fields})
    try:
        return func(*args, **kwargs)
    finally:
        _log_context.set(previous)


def mask_email(value: str) -> str:
    raw = str(value or "").strip()
    if "@" not in raw:
        return raw
    local, _, domain = raw.partition("@")
    if not local:
        return f"***@{domain}"
    if len(local) == 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = f"{local[0]}*"
    else:
        masked_local = f"{local[0]}***{local[-1]}"
    return f"{masked_local}@{domain}"


def sanitize_log_data(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(data or {})
    return {str(key): _sanitize_value(str(key), value) for key, value in payload.items()}


def log_audit_event(event: str, *, message: str | None = None, **extra: Any) -> None:
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    payload = sanitize_log_data({"event": event, **extra})
    if payload.get("actor_type") is None:
        payload["actor_type"] = "user"
    if payload.get("actor_id") is None:
        payload["actor_id"] = get_log_context().get("user_id")
    logger.info(message or event, extra=payload)


class ContextFilter(logging.Filter):
    def __init__(self, *, service_name: str, environment: str):
        super().__init__()
        self._service_name = service_name
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_log_context()
        for field in _context_fields:
            if not hasattr(record, field):
                setattr(record, field, context.get(field))
        if not hasattr(record, "event"):
            record.event = ""
        if not hasattr(record, "service"):
            record.service = self._service_name
        if not hasattr(record, "environment"):
            record.environment = self._environment
        return True


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        message = record.getMessage()
        parts = [timestamp, record.levelname, f"[{record.name}]"]
        if getattr(record, "request_id", None):
            parts.append(f"req={record.request_id}")
        if getattr(record, "user_id", None) is not None:
            parts.append(f"user={record.user_id}")
        if getattr(record, "workspace_id", None):
            parts.append(f"ws={record.workspace_id}")
        if getattr(record, "job_id", None) is not None:
            parts.append(f"job={record.job_id}")
        if getattr(record, "event", None):
            parts.append(f"event={record.event}")
        rendered = " ".join(parts) + f" {message}"
        if record.exc_info:
            rendered += "\n" + self.formatException(record.exc_info)
        return rendered


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", "") or "",
            "service": getattr(record, "service", "") or "",
            "environment": getattr(record, "environment", "") or "",
        }
        for field in _context_fields:
            payload[field] = _normalize_value(getattr(record, field, None))
        for key, value in record.__dict__.items():
            if key in _log_record_reserved or key in _context_fields or key.startswith("_"):
                continue
            if key in {"args", "msg", "exc_info", "exc_text", "stack_info"}:
                continue
            if key in logging.makeLogRecord({}).__dict__:
                continue
            payload[key] = _sanitize_value(key, value)
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else ""
            payload["stacktrace"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(config: Mapping[str, Any], *, project_root: Path) -> dict[str, str]:
    raw_log_dir = str(config.get("LOG_DIR", "logs")).strip() or "logs"
    log_dir = Path(raw_log_dir)
    if not log_dir.is_absolute():
        log_dir = project_root / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    service_name = str(config.get("LOG_SERVICE_NAME", "agent")).strip() or "agent"
    environment = str(config.get("LOG_ENVIRONMENT", "development")).strip() or "development"
    log_level = str(config.get("LOG_LEVEL", "INFO")).strip().upper() or "INFO"
    max_bytes = int(config.get("LOG_MAX_BYTES", 10 * 1024 * 1024))
    backup_count = int(config.get("LOG_BACKUP_COUNT", 5))

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "context": {
                    "()": "app.logging_utils.ContextFilter",
                    "service_name": service_name,
                    "environment": environment,
                }
            },
            "formatters": {
                "console": {"()": "app.logging_utils.ConsoleFormatter"},
                "json": {"()": "app.logging_utils.JsonFormatter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": log_level,
                    "formatter": "console",
                    "filters": ["context"],
                    "stream": "ext://sys.stderr",
                },
                "app_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "json",
                    "filters": ["context"],
                    "filename": str(log_dir / "app.log"),
                    "maxBytes": max_bytes,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
                "access_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "json",
                    "filters": ["context"],
                    "filename": str(log_dir / "access.log"),
                    "maxBytes": max_bytes,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
                "audit_file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": log_level,
                    "formatter": "json",
                    "filters": ["context"],
                    "filename": str(log_dir / "audit.log"),
                    "maxBytes": max_bytes,
                    "backupCount": backup_count,
                    "encoding": "utf-8",
                },
            },
            "root": {
                "level": log_level,
                "handlers": ["console", "app_file"],
            },
            "loggers": {
                ACCESS_LOGGER_NAME: {
                    "level": log_level,
                    "handlers": ["console", "access_file"],
                    "propagate": False,
                },
                AUDIT_LOGGER_NAME: {
                    "level": log_level,
                    "handlers": ["console", "audit_file"],
                    "propagate": False,
                },
            },
        }
    )
    return {
        "log_dir": str(log_dir),
        "app_log": str(log_dir / "app.log"),
        "access_log": str(log_dir / "access.log"),
        "audit_log": str(log_dir / "audit.log"),
    }


def _sanitize_value(key: str, value: Any) -> Any:
    key_lower = str(key).strip().lower()
    if key_lower.endswith("email") or key_lower == "email":
        return mask_email(str(value))
    if key_lower in _sensitive_field_names or key_lower.endswith("_api_key") or key_lower.endswith("_password"):
        return "[REDACTED]"
    return _normalize_value(value)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize_value(str(key), item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return str(value)
