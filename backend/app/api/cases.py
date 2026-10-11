"""Claim filing, case views, and the respondent's answer (system design §4).

Filing and responding both kick off tens of seconds of agent calls. With
`?background=true` they return 202 with the case id as soon as the fast part is done
(validation, the case row, the stored response), and the rest runs in the background.
The browser watches it happen on `/events/cases/{id}`. Without the flag they block and
return the full result, which is what scripts and tests use.
"""

import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.data.cases import get_case_row, get_case_view, list_recent_cases, load_case_file
from app.data.db import get_connection
from app.orchestrator import adjudication, pipeline
from app.schemas import Argument, CaseFile, DecisionObject, DisputeCategory
from app.schemas.triage import TriageResult

router = APIRouter(tags=["cases"])
log = logging.getLogger(__name__)


class EvidenceRefIn(BaseModel):
    kind: str
    hash: str
    object_key: str


class FileClaimRequest(BaseModel):
    trip_id: str
    complainer_id: str
    category: DisputeCategory
    claim_text: str
    evidence: list[EvidenceRefIn] = []


class FileClaimResponse(BaseModel):
    case_id: str
    state: str
    triage: TriageResult
    velocity_flagged: bool
    case_file: CaseFile | None = None
    detail: str = ""


class Accepted(BaseModel):
    """202 body for background mode: watch /events/cases/{case_id} for the rest."""

    case_id: str
    state: str
    events: str


def _accepted(case_id: str, state: str) -> Accepted:
    return Accepted(case_id=case_id, state=state, events=f"/events/cases/{case_id}")


async def _run_quietly(fn: Callable[..., Awaitable], *args) -> None:
    # The pipeline already wrote an `error` trace event for the UI; this is for the logs.
    try:
        await fn(*args)
    except Exception:
        log.exception("background %s failed for %s", fn.__name__, args)


@router.get("/cases")
async def recent_cases(limit: int = Query(30, ge=1, le=200)) -> list[dict]:
    """Most recently active cases, for the trace panel's case picker."""
    conn = await get_connection()
    try:
        return await list_recent_cases(conn, limit)
    finally:
        await conn.close()


@router.post(
    "/cases", status_code=status.HTTP_201_CREATED, response_model=FileClaimResponse | Accepted
)
async def file_claim(
    body: FileClaimRequest, background_tasks: BackgroundTasks, response: Response,
    background: bool = False,
) -> FileClaimResponse | Accepted:
    """File a new claim: Prevention rules → Triage → Evidence Collection, ending at
    `awaiting_response` (or a safety/decline branch)."""
    evidence = [
        pipeline.EvidenceInput(kind=e.kind, hash=e.hash, object_key=e.object_key)
        for e in body.evidence
    ]
    try:
        opened = await pipeline.open_claim(
            body.trip_id, body.complainer_id, body.category, body.claim_text, evidence
        )
    except pipeline.ClaimRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    if background:
        background_tasks.add_task(_run_quietly, pipeline.process_claim, opened)
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted(opened.case_id, "opened")

    result = await pipeline.process_claim(opened)
    return FileClaimResponse(
        case_id=result.case_id, state=result.state.value, triage=result.triage,
        velocity_flagged=result.velocity_flagged, case_file=result.case_file,
        detail=result.detail,
    )


@router.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    """Raw case snapshot, including the assembled case file."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
    finally:
        await conn.close()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    case_file = load_case_file(case)
    return {**case, "case_file": case_file.model_dump(mode="json") if case_file else None}


@router.get("/cases/{case_id}/view")
async def get_case_summary(case_id: str) -> dict:
    """What the Rider/Driver panels show: state, parties, the claim and the response."""
    conn = await get_connection()
    try:
        view = await get_case_view(conn, case_id)
    finally:
        await conn.close()
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    return view


class ResponseRequest(BaseModel):
    respondent_id: str
    text: str


class AdjudicationResponse(BaseModel):
    case_id: str
    state: str
    decision: DecisionObject
    rider_argument: Argument
    driver_argument: Argument
    document: str


def adjudication_response(result: adjudication.AdjudicationResult) -> AdjudicationResponse:
    return AdjudicationResponse(
        case_id=result.case_id, state=result.state.value, decision=result.decision,
        rider_argument=result.rider_argument, driver_argument=result.driver_argument,
        document=result.document,
    )


@router.post("/cases/{case_id}/response", response_model=AdjudicationResponse | Accepted)
async def submit_response(
    case_id: str, body: ResponseRequest, background_tasks: BackgroundTasks,
    response: Response, background: bool = False,
) -> AdjudicationResponse | Accepted:
    """The party the claim was filed against answers it. This triggers adjudication
    (both advocates → Judge → escalation gate → compliance check)."""
    try:
        await adjudication.store_response(case_id, body.respondent_id, body.text)
    except adjudication.CaseNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}") from exc
    except adjudication.AdjudicationRejected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    if background:
        background_tasks.add_task(_run_quietly, adjudication.adjudicate, case_id)
        response.status_code = status.HTTP_202_ACCEPTED
        return _accepted(case_id, "awaiting_response")
    return adjudication_response(await adjudication.adjudicate(case_id))
