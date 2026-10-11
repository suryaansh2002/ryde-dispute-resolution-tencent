"""Dev A (Intake & Evidence) owns this router: claim filing, case fetch, respondent
answers, and evidence upload (system design §4). Split into its own module (roadmap v3)
so Dev A and Dev B never edit the same routes file."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.data.cases import get_case_row, load_case_file
from app.data.db import get_connection
from app.orchestrator import adjudication, pipeline
from app.schemas import Argument, CaseFile, DecisionObject, DisputeCategory
from app.schemas.triage import TriageResult

router = APIRouter(tags=["cases"])


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


@router.post("/cases", status_code=status.HTTP_201_CREATED, response_model=FileClaimResponse)
async def file_claim(body: FileClaimRequest) -> FileClaimResponse:
    """File a new claim -> creates case, triggers triage, Prevention rules, and (if it
    clears them) Evidence Collection. Ends at `awaiting_response`; Dev B's Day-5
    extension carries it from there to a decision."""
    try:
        result = await pipeline.file_claim(
            trip_id=body.trip_id,
            complainer_id=body.complainer_id,
            category=body.category,
            claim_text=body.claim_text,
            evidence=[
                pipeline.EvidenceInput(kind=e.kind, hash=e.hash, object_key=e.object_key)
                for e in body.evidence
            ],
        )
    except pipeline.ClaimRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return FileClaimResponse(
        case_id=result.case_id, state=result.state.value, triage=result.triage,
        velocity_flagged=result.velocity_flagged, case_file=result.case_file,
        detail=result.detail,
    )


@router.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    """Fetch current case snapshot."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
    finally:
        await conn.close()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}")
    case_file = load_case_file(case)
    return {**case, "case_file": case_file.model_dump(mode="json") if case_file else None}


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


@router.post("/cases/{case_id}/response", response_model=AdjudicationResponse)
async def submit_response(case_id: str, body: ResponseRequest) -> AdjudicationResponse:
    """The party the claim was filed against answers it. This triggers adjudication
    (both advocates -> Judge -> escalation gate -> compliance check) and returns the
    resulting decision, whether final or escalated to L2."""
    try:
        result = await adjudication.submit_response(case_id, body.respondent_id, body.text)
    except adjudication.CaseNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no case {case_id!r}") from exc
    except adjudication.AdjudicationRejected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return adjudication_response(result)
