"""Dev A (Intake & Evidence) owns this router: evidence attachment against a case
(system design §4). Split out from cases.py since Neon Object Storage upload wiring is
its own concern."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.data.cases import get_case_row, insert_evidence
from app.data.db import get_connection
from app.tools.object_storage import upload_object

router = APIRouter(tags=["evidence"])

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB — plenty for a dispute photo/audio clip


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

        data = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "evidence file too large")

        object_key = f"evidence/{case_id}/{file.filename or 'upload'}"
        content_type = file.content_type or "application/octet-stream"
        hash_ = upload_object(object_key, data, content_type)
        evidence_id = await insert_evidence(conn, case_id, kind, hash_, object_key, submitted_by)
    finally:
        await conn.close()

    return {"evidence_id": evidence_id, "object_key": object_key, "hash": hash_}
