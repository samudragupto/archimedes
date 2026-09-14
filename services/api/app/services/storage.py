"""Supabase Storage helpers for the private ``documents`` bucket.

Layout: ``<user-id>/<project-id>/<kind>/<short-uuid>-<safe-filename>`` — the
per-user top-level folder matches the bucket's RLS policies (users can only
touch their own folder), while the API/worker use the service role and can
read across projects to run the pipeline.
"""

from __future__ import annotations

import re
from uuid import uuid4

from .. import db

BUCKET = "documents"


class StorageError(RuntimeError):
    """Raised when an upload or download fails."""


def _safe_name(filename: str | None) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "upload.bin").strip("._")
    return (name or "upload.bin")[:120]


def upload_document(
    user_id: str, project_id: str, kind: str, filename: str | None, data: bytes
) -> str:
    """Upload bytes under the user's folder; returns the storage path."""
    path = f"{user_id}/{project_id}/{kind}/{uuid4().hex[:8]}-{_safe_name(filename)}"
    try:
        res = (
            db._client()
            .storage.from_(BUCKET)
            .upload(
                path,
                data,
                {"content-type": "application/octet-stream", "upsert": "false"},
            )
        )
    except Exception as e:  # storage3 raises bare Exceptions on HTTP errors
        raise StorageError(f"upload failed: {e}") from e
    # some client versions return the path, others a dict/None — the path is
    # deterministic either way, so we only surface hard failures above.
    _ = res
    return path


def download_document(path: str) -> bytes:
    """Fetch a stored document (used for re-parses and audits)."""
    try:
        return db._client().storage.from_(BUCKET).download(path)
    except Exception as e:
        raise StorageError(f"download failed: {e}") from e
