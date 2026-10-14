"""Upload handling and file storage.

``STORAGE_BACKEND=local`` writes under ``UPLOAD_DIR``; the ``gcs``/``s3``
branches are the seam where the reference stack's Google Cloud Storage service
plugs in. Everything above this module deals in opaque relative paths, so
swapping backends does not touch the services.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.config.settings import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class StoredFile:
    #: Path relative to the storage root - what gets persisted in the DB.
    path: str
    filename: str
    size: int
    content_type: str | None


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    cleaned = _SAFE_NAME_RE.sub("_", base).strip("._") or "file"
    return cleaned[:120]


def extension_of(name: str) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def validate_upload(file: UploadFile, allowed: set[str] | None = None) -> None:
    ext = extension_of(file.filename or "")
    permitted = allowed or settings.allowed_upload_extensions_set
    if ext not in permitted:
        raise ValidationError(
            f"File type '.{ext or '?'}' is not allowed. Permitted: "
            + ", ".join(sorted(permitted))
        )


async def save_upload(
    file: UploadFile,
    folder: str = "misc",
    allowed: set[str] | None = None,
) -> StoredFile:
    """Persist one upload and return its storage-relative path."""
    validate_upload(file, allowed)

    contents = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(contents) > max_bytes:
        raise ValidationError(f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    if not contents:
        raise ValidationError("Uploaded file is empty.")

    stored_name = f"{uuid.uuid4().hex}_{safe_filename(file.filename or 'file')}"
    relative = f"{folder.strip('/')}/{stored_name}"

    if settings.STORAGE_BACKEND == "local":
        target = Path(settings.UPLOAD_DIR) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
    else:  # pragma: no cover - exercised only with cloud credentials present
        _put_object(relative, contents, file.content_type)

    logger.info("Stored upload %s (%d bytes)", relative, len(contents))
    return StoredFile(
        path=relative,
        filename=file.filename or stored_name,
        size=len(contents),
        content_type=file.content_type,
    )


def read_file(relative_path: str) -> bytes:
    if settings.STORAGE_BACKEND == "local":
        target = Path(settings.UPLOAD_DIR) / relative_path
        if not target.exists():
            raise ValidationError("File not found.")
        # Reject traversal outside the upload root.
        root = Path(settings.UPLOAD_DIR).resolve()
        if not target.resolve().is_relative_to(root):
            raise ValidationError("Invalid file path.")
        return target.read_bytes()
    return _get_object(relative_path)  # pragma: no cover


def delete_file(relative_path: str) -> bool:
    if settings.STORAGE_BACKEND == "local":
        target = Path(settings.UPLOAD_DIR) / relative_path
        root = Path(settings.UPLOAD_DIR).resolve()
        if target.exists() and target.resolve().is_relative_to(root):
            target.unlink()
            return True
        return False
    return _delete_object(relative_path)  # pragma: no cover


def public_url(relative_path: str | None) -> str | None:
    """URL the frontend can render an asset from."""
    if not relative_path:
        return None
    if relative_path.startswith(("http://", "https://")):
        return relative_path
    if settings.STORAGE_BACKEND == "local":
        return f"{settings.API_PREFIX}/files/{relative_path.lstrip('/')}"
    if settings.STORAGE_BUCKET:  # pragma: no cover
        return (
            f"https://storage.googleapis.com/{settings.STORAGE_BUCKET}/{relative_path}"
        )
    return relative_path


# ----------------------------------------------------- cloud backend stubs
def _client():  # pragma: no cover - requires cloud credentials
    if settings.STORAGE_BACKEND == "gcs":
        from google.cloud import storage  # type: ignore[import-not-found]

        return storage.Client().bucket(settings.STORAGE_BUCKET)
    raise ValidationError(
        f"Storage backend '{settings.STORAGE_BACKEND}' is not configured."
    )


def _put_object(path: str, data: bytes, content_type: str | None):  # pragma: no cover
    blob = _client().blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return path


def _get_object(path: str) -> bytes:  # pragma: no cover
    return _client().blob(path).download_as_bytes()


def _delete_object(path: str) -> bool:  # pragma: no cover
    _client().blob(path).delete()
    return True
