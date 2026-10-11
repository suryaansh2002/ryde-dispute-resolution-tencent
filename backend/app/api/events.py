"""SSE streams over the trace log (system design §4, §7). Each message is one
`trace_events` row as JSON, with the row id as the SSE event id, so the browser's
EventSource resumes from where it left off after a dropped connection."""

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.sse.stream import fetch_case_events, fetch_l2_events, tail

router = APIRouter(prefix="/events", tags=["events"])

# Keep-alive comments every 15s. They also stop Render's free tier counting an open
# stream as idle.
_PING_SECONDS = 15


def _after(request: Request, after: int | None) -> int:
    header = request.headers.get("last-event-id")
    if header and header.isdigit():
        return int(header)
    return after or 0


@router.get("/cases/{case_id}")
async def stream_case_events(
    case_id: str, request: Request, after: int | None = Query(None, ge=0)
) -> EventSourceResponse:
    """Live trace + state transitions for one case. Replays from the start (or from
    Last-Event-ID / ?after=), then streams new events as they happen."""
    events = tail(lambda conn, last: fetch_case_events(conn, case_id, last), _after(request, after))
    return EventSourceResponse(events, ping=_PING_SECONDS, headers={"X-Accel-Buffering": "no"})


@router.get("/l2")
async def stream_l2_events(
    request: Request, after: int | None = Query(None, ge=0)
) -> EventSourceResponse:
    """New arrivals in the L2 queue (escalated or safety-bypassed), not tied to one case."""
    events = tail(fetch_l2_events, _after(request, after))
    return EventSourceResponse(events, ping=_PING_SECONDS, headers={"X-Accel-Buffering": "no"})
