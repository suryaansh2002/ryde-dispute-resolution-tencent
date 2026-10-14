"""The L2 human-review queue (system design §4)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.data.cases import list_l2_queue
from app.data.db import get_connection
from app.orchestrator.adjudication import AdjudicationRejected, CaseNotFound
from app.orchestrator.l2_review import (
    ReviewInvalid,
    ReviewRequest,
    prepare_safety_case_file,
    review_case,
)
from app.schemas import DecisionObject, DecisionOutcome, Remedy
from app.tools.evidence_lookup import evidence_json

router = APIRouter(prefix="/l2", tags=["l2"])


class RatifyBody(BaseModel):
    reviewer: str
    action: Literal["ratify", "override"]
    note: str
    outcome: DecisionOutcome | None = None
    remedy: Remedy | None = None
    policy_applied: str | None = None


@router.get("/queue")
async def get_l2_queue() -> list[dict]:
    """Escalated and safety-bypassed cases awaiting a human, safety first."""
    conn = await get_connection()
    try:
        return await list_l2_queue(conn)
    finally:
        await conn.close()


@router.post("/cases/{case_id}/ratify", response_model=DecisionObject)
async def ratify_case(case_id: str, body: RatifyBody) -> DecisionObject:
    """Ratify the agent decision as-is, or override it with the reviewer's own outcome
    and remedy. Either way the case becomes `decided` and `human_ratified`."""
    try:
        return await review_case(case_id, ReviewRequest(
            reviewer=body.reviewer, action=body.action, note=body.note,
            outcome=body.outcome, remedy=body.remedy, policy_applied=body.policy_applied,
        ))
    except CaseNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}") from exc
    except AdjudicationRejected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ReviewInvalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/cases/{case_id}/prepare")
async def prepare_case(case_id: str) -> dict:
    """"Prepare case file" for a safety report: gathers the trip records in code, with
    no model call and no recommendation, and leaves the case where it is. Idempotent."""
    try:
        prepared = await prepare_safety_case_file(case_id)
    except CaseNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}") from exc
    except AdjudicationRejected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {
        "case_id": prepared.case_id,
        "prepared_at": prepared.prepared_at.isoformat(),
        "evidence": evidence_json(prepared.case_file),
    }
