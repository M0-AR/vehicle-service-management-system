"""DVI photo storage: local filesystem, tenant-scoped, content-validated.

Files live at `<storage_dir>/<tenant_id>/<inspection_id>/<random>.<ext>`.
Only the relative path is stored in the database; serving goes through an
authenticated (or token-scoped public) endpoint, never a static mount.
"""

from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

settings = get_settings()

# magic bytes -> (extension, mime)
_SIGNATURES = (
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"RIFF", "webp", "image/webp"),
)


def _detect(head: bytes) -> tuple[str, str] | None:
    for magic, ext, mime in _SIGNATURES:
        if head.startswith(magic):
            if ext == "webp" and head[8:12] != b"WEBP":
                continue
            return ext, mime
    return None


def storage_root() -> Path:
    return Path(settings.storage_dir)


async def save_photo(
    tenant_id: uuid.UUID, inspection_id: uuid.UUID, upload: UploadFile
) -> dict:
    """Validate and persist one photo; returns metadata for the JSONB column."""
    head = await upload.read(16)
    detected = _detect(head)
    if detected is None:
        raise HTTPException(
            status_code=422,
            detail="Only JPEG, PNG or WebP images are supported",
        )
    ext, mime = detected
    if upload.content_type and upload.content_type not in (
        mime,
        "application/octet-stream",
        "image/jpg",
    ):
        raise HTTPException(status_code=422, detail="File type does not match its content")

    directory = storage_root() / str(tenant_id) / str(inspection_id)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{ext}"
    target = directory / name

    size = len(head)
    with open(target, "wb") as out:
        out.write(head)
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > settings.upload_max_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Photo is too large (max "
                        f"{settings.upload_max_bytes // (1024 * 1024)} MB)"
                    ),
                )
            out.write(chunk)

    return {
        "path": f"{tenant_id}/{inspection_id}/{name}",
        "mime": mime,
        "size": size,
        "name": upload.filename or name,
    }


def resolve_path(tenant_id: uuid.UUID, photo_path: str) -> Path:
    """Resolve a stored path, refusing traversal outside the tenant directory."""
    root = (storage_root() / str(tenant_id)).resolve()
    target = (storage_root() / photo_path).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return target


def delete_path(photo_path: str) -> None:
    try:
        (storage_root() / photo_path).unlink(missing_ok=True)
    except OSError:
        pass


def ensure_root() -> None:
    os.makedirs(storage_root(), exist_ok=True)
