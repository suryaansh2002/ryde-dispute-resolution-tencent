"""Decision fetch, manual adjudication trigger, and the golden-case suite endpoint
(system design §4)."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.cases import AdjudicationResponse, adjudication_response
from app.data.cases import get_case_row, get_latest_decision, load_case_file
from app.data.db import get_connection
from app.orchestrator import adjudication
from app.orchestrator.decision_document import render_decision_document
from app.schemas import DecisionObject

router = APIRouter(tags=["decisions"])


class DecisionResponse(BaseModel):
    case_id: str
    state: str
    decision: DecisionObject
    document: str


@router.get("/cases/{case_id}/decision", response_model=DecisionResponse)
async def get_decision(case_id: str) -> DecisionResponse:
    """Fetch the decision document. It's final if the case is `decided`, or pending L2
    review if the case is `escalated`."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        decision = await get_latest_decision(conn, case_id) if case else None
    finally:
        await conn.close()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    if decision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"case {case_id!r} has no decision yet")
    case_file = load_case_file(case)
    return DecisionResponse(
        case_id=case_id, state=case["state"], decision=decision,
        document=render_decision_document(decision, case_file) if case_file else "",
    )


@router.post("/cases/{case_id}/adjudicate", response_model=AdjudicationResponse)
async def adjudicate_case(case_id: str) -> AdjudicationResponse:
    """Adjudicate without waiting for a response: the response deadline passed, or a
    previous run crashed mid-way and left the case in `adjudicating`."""
    try:
        result = await adjudication.adjudicate(case_id)
    except adjudication.CaseNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}") from exc
    except adjudication.AdjudicationRejected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return adjudication_response(result)


@router.post("/golden-run")
async def run_golden_cases() -> dict:
    """Trigger the golden-case suite, computing real dashboard numbers."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
