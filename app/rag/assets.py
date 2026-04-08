from __future__ import annotations

import re
import secrets
from pathlib import Path

from flask import current_app

from .errors import RAGValidationError


def _project_root() -> Path:
    return Path(current_app.root_path).parent


def _resolve_directory(raw_path: str) -> Path:
    candidate = Path(str(raw_path).strip())
    if not candidate.is_absolute():
        candidate = _project_root() / candidate
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def sanitize_workspace_id(workspace_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(workspace_id or "").strip())
    return normalized.strip("._-") or "default"


def uploads_root() -> Path:
    return _resolve_directory(str(current_app.config.get("RAG_UPLOAD_DIR", "uploads/rag")))


def originals_root() -> Path:
    directory = uploads_root() / "originals"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def derived_root() -> Path:
    directory = uploads_root() / "derived"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _workspace_dir(root: Path, *, user_id: int, workspace_id: str) -> Path:
    directory = root / f"user-{int(user_id)}" / f"workspace-{sanitize_workspace_id(workspace_id)}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def create_original_asset(*, user_id: int, workspace_id: str, original_name: str) -> Path:
    suffix = Path(str(original_name or "").strip()).suffix.lower() or ".bin"
    filename = f"{secrets.token_hex(16)}{suffix}"
    return _workspace_dir(originals_root(), user_id=user_id, workspace_id=workspace_id) / filename


def create_derived_asset(*, user_id: int, workspace_id: str, document_id: int) -> Path:
    filename = f"document-{int(document_id)}-canonical.txt"
    return _workspace_dir(derived_root(), user_id=user_id, workspace_id=workspace_id) / filename


def cleanup_artifact(path_str: str | None, *, expected_root: Path | None = None) -> None:
    if not path_str:
        return
    candidate = Path(str(path_str)).resolve(strict=False)
    if expected_root is not None:
        root = Path(expected_root).resolve(strict=False)
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise RAGValidationError("artifact path is outside managed rag storage") from exc
    candidate.unlink(missing_ok=True)
