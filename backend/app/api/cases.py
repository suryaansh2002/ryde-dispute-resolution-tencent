"""Dev A (Intake & Evidence) owns this router: claim filing, case fetch, respondent
answers, and evidence upload (system design §4). Split into its own module (roadmap v3)
so Dev A and Dev B never edit the same routes file."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.data.cases import get_case_row
from app.data.db import get_connection
from app.orchestrator import pipeline
from app.schemas import CaseFile, DisputeCategory
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
    return case


@router.post("/cases/{case_id}/response")
async def submit_response(case_id: str) -> dict:
    """Respondent's answer to an allegation."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
