"""Dev A (Intake & Evidence) owns this router: evidence attachment against a case
(system design §4). Split out from cases.py since Neon Object Storage upload wiring is
its own concern."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["evidence"])


@router.post("/cases/{case_id}/evidence", status_code=status.HTTP_201_CREATED)
async def attach_evidence(case_id: str) -> dict:
    """Attach evidence (photo/audio) — bytes go to Neon Object Storage, metadata to
    Postgres (system design §5)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
