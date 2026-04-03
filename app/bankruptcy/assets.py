from __future__ import annotations

import hmac
import re
import secrets
from hashlib import sha256
from pathlib import Path
from typing import Final
from urllib.parse import quote

from flask import current_app

from .errors import BankruptcyAuthorizationError, BankruptcyValidationError

_PLOT_FILENAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.png$")


def _project_root() -> Path:
    return Path(current_app.root_path).parent


def _resolve_directory(raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip())
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def uploads_root() -> Path:
    return _resolve_directory(str(current_app.config.get("BANKRUPTCY_UPLOAD_DIR", "uploads/bankruptcy/csv")))


def plots_root() -> Path:
    return _resolve_directory(str(current_app.config.get("BANKRUPTCY_PLOT_DIR", "uploads/bankruptcy")))


def sanitize_workspace_id(workspace_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(workspace_id or "").strip())
    return normalized.strip("._-") or "default"


def _workspace_dir(root: Path, *, user_id: int, workspace_id: str) -> Path:
    directory = root / f"user-{int(user_id)}" / f"workspace-{sanitize_workspace_id(workspace_id)}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_csv_asset(*, user_id: int, workspace_id: str, original_name: str) -> Path:
    suffix = Path(str(original_name or "").strip()).suffix.lower() or ".csv"
    filename = f"{secrets.token_hex(16)}{suffix}"
    return _workspace_dir(uploads_root(), user_id=user_id, workspace_id=workspace_id) / filename


def create_record_plot_asset(*, user_id: int, workspace_id: str, record_id: int) -> Path:
    filename = f"record-{int(record_id)}-{secrets.token_hex(8)}.png"
    return _workspace_dir(plots_root(), user_id=user_id, workspace_id=workspace_id) / filename


def build_record_plot_url(*, record_id: int, workspace_id: str) -> str:
    workspace_encoded = quote(str(workspace_id), safe="")
    return f"/api/bankruptcy/records/{int(record_id)}/plot?workspaceId={workspace_encoded}"


def _plot_secret() -> bytes:
    return str(current_app.config.get("SECRET_KEY", "dev-secret")).encode("utf-8")


def build_plot_token(*, user_id: int, workspace_id: str, filename: str) -> str:
    message = f"{int(user_id)}:{workspace_id}:{filename}".encode("utf-8")
    return hmac.new(_plot_secret(), message, sha256).hexdigest()


def create_plot_asset(*, user_id: int, workspace_id: str) -> tuple[Path, str]:
    target_dir = _workspace_dir(plots_root(), user_id=user_id, workspace_id=workspace_id)
    filename = f"{secrets.token_hex(16)}.png"
    plot_path = target_dir / filename
    token = build_plot_token(user_id=user_id, workspace_id=workspace_id, filename=filename)
    workspace_encoded = quote(str(workspace_id), safe="")
    plot_url = f"/api/bankruptcy/plots/{filename}?workspaceId={workspace_encoded}&token={token}"
    return plot_path, plot_url


def resolve_plot_asset(*, user_id: int, workspace_id: str, filename: str, token: str) -> Path:
    clean_name = str(filename or "").strip()
    if not _PLOT_FILENAME_RE.match(clean_name):
        raise BankruptcyValidationError("plot filename is invalid")
    expected = build_plot_token(user_id=user_id, workspace_id=workspace_id, filename=clean_name)
    if not token or not hmac.compare_digest(expected, str(token)):
        raise BankruptcyAuthorizationError("plot token is invalid")
    return _workspace_dir(plots_root(), user_id=user_id, workspace_id=workspace_id) / clean_name


def cleanup_artifact(path_str: str | None, *, expected_root: Path | None = None) -> None:
    if not path_str:
        return
    candidate = Path(str(path_str)).resolve(strict=False)
    if expected_root is not None:
        root = Path(expected_root).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError:
            raise BankruptcyValidationError("artifact path is outside managed storage")
    candidate.unlink(missing_ok=True)
