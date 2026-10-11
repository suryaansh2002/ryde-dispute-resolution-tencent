"""Evidence uploads to Neon Object Storage (system design §4, §5): either before a case
exists (`/uploads`, for evidence filed with the claim) or against an existing case."""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse

from app.data.cases import get_case_row, insert_evidence
from app.data.db import get_connection
from app.tools.object_storage import presigned_url, upload_object

router = APIRouter(tags=["evidence"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — plenty for a dispute photo/audio clip


def _safe_name(filename: str | None) -> str:
    """The client's filename, reduced to something safe inside an object key: no path
    separators, no "..", only [A-Za-z0-9._-]."""
    base = (filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "upload"
    return cleaned[:100]


async def _read_capped(file: UploadFile) -> bytes:
    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "evidence file too large")
    return data


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_before_filing(
    file: Annotated[UploadFile, File()], kind: Annotated[str, Form()] = "photo",
) -> dict:
    """Upload evidence before a case exists, then pass the returned ref in
    `POST /cases`' `evidence` list. Property Damage needs its photo at filing time:
    Prevention Rule 4 checks for it before any agent runs."""
    data = await _read_capped(file)
    object_key = f"evidence/uploads/{uuid.uuid4().hex}/{_safe_name(file.filename)}"
    hash_ = upload_object(object_key, data, file.content_type or "application/octet-stream")
    return {"kind": kind, "hash": hash_, "object_key": object_key}


@router.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
async def attach_evidence(
    case_id: str,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    submitted_by: Annotated[str | None, Form()] = None,
) -> dict:
    """Attach evidence (photo/audio) — bytes go to Neon Object Storage, metadata to
    Postgres (system design §5)."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")

        data = await _read_capped(file)
        object_key = f"evidence/{case_id}/{_safe_name(file.filename)}"
        content_type = file.content_type or "application/octet-stream"
        hash_ = upload_object(object_key, data, content_type)
        evidence_id = await insert_evidence(conn, case_id, kind, hash_, object_key, submitted_by)
    finally:
        await conn.close()

    return {"evidence_id": evidence_id, "object_key": object_key, "hash": hash_}


@router.get("/evidence/{evidence_id}/content")
async def evidence_content(evidence_id: str) -> RedirectResponse:
    """Redirect to a short-lived presigned link for the evidence file (e.g. a photo)."""
    conn = await get_connection()
    try:
        key = await conn.fetchval("SELECT object_key FROM evidence WHERE id = $1", evidence_id)
    finally:
        await conn.close()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no evidence {evidence_id!r}")
    return RedirectResponse(presigned_url(key), status_code=status.HTTP_307_TEMPORARY_REDIRECT)
