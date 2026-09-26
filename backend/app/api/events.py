"""Dev B (Adjudication & Delivery) owns this router: SSE streams backed by the trace
event bus (system design §4, §7)."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/cases/{case_id}")
async def stream_case_events(case_id: str):
    """Live trace + state-transition stream for one case (text/event-stream)."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)


@router.get("/l2")
async def stream_l2_events():
    """New-case alerts for the L2 queue, decoupled from any single case_id."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
