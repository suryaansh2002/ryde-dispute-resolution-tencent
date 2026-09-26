"""Dev A (Intake & Evidence) owns this router: claim filing, case fetch, respondent
answers, and evidence upload (system design §4). Split into its own module (roadmap v3)
so Dev A and Dev B never edit the same routes file."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["cases"])


@router.post("/cases", status_code=status.HTTP_201_CREATED)
async def file_claim() -> dict:
    """File a new claim -> creates case, triggers triage."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)


@router.get("/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    """Fetch current case snapshot."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)


@router.post("/cases/{case_id}/response")
async def submit_response(case_id: str) -> dict:
    """Respondent's answer to an allegation."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
