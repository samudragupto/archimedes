"""documents router — solicitation/org-profile ingestion.

Accepts either a multipart upload (file) or JSON ``{source_url, kind}``.
Both paths parse IMMEDIATELY (the wizard shows the extracted-text preview on
the next screen), persist the raw file to the private storage bucket, and
replace the project's document of that kind (one per kind, per schema).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from .. import db
from ..auth import User, get_current_user
from ..models.schemas import DocumentKind, ParsedDocument
from ..services import storage
from ..services.document_parser import DocumentParseError, DocumentParser
from ..services.storage import StorageError
from .projects import require_project

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — generous for grant PDFs
PREVIEW_CHARS = 1500


class UrlDocumentRequest(BaseModel):
    source_url: HttpUrl
    kind: DocumentKind = DocumentKind.solicitation


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(
    project_id: str,
    user: User = Depends(get_current_user),
    kind: DocumentKind = Form(DocumentKind.solicitation),
    file: UploadFile | None = File(default=None),
) -> dict:
    require_project(project_id, user)

    if kind == DocumentKind.supporting:
        raise HTTPException(status_code=400, detail="kind must be solicitation or organization")

    if file is None:
        raise HTTPException(status_code=400, detail="multipart 'file' is required")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds the 20 MB limit")

    parser = DocumentParser()
    try:
        parsed = await parser.parse_bytes(file.filename, data)
    except DocumentParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _persist(project_id, user, kind, parsed, filename=file.filename, raw=data)


@router.post("/projects/{project_id}/documents/url", status_code=201)
async def ingest_url(
    project_id: str,
    body: UrlDocumentRequest,
    user: User = Depends(get_current_user),
) -> dict:
    require_project(project_id, user)
    parser = DocumentParser()
    try:
        parsed = await parser.parse_url(str(body.source_url))
    except DocumentParseError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _persist(project_id, user, body.kind, parsed, filename=None, raw=None)


def _persist(
    project_id: str,
    user: User,
    kind: DocumentKind,
    parsed: ParsedDocument,
    *,
    filename: str | None,
    raw: bytes | None,
) -> dict:
    if not parsed.text.strip():
        raise HTTPException(
            status_code=422,
            detail="no extractable text — scanned PDFs are not supported yet; paste the text instead",
        )
    storage_path = None
    if raw is not None:
        try:
            storage_path = storage.upload_document(user.id, project_id, kind.value, filename, raw)
        except StorageError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    row = db.upsert_document(
        project_id,
        kind.value,
        {
            "filename": filename or parsed.filename,
            "storage_path": storage_path,
            "source_url": parsed.source_url,
            "extracted_text": parsed.text,
            "page_count": parsed.page_count,
        },
    )
    return {
        "document": row,
        "preview": parsed.text[:PREVIEW_CHARS],
        "total_chars": len(parsed.text),
        "chunks": len(parsed.chunks),
    }
