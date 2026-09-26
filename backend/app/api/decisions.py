"""Dev B (Adjudication & Delivery) owns this router: decision-document fetch and the
golden-case suite endpoint (system design §4). Split into its own module (roadmap v3)
so Dev A and Dev B never edit the same routes file."""

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["decisions"])


@router.get("/cases/{case_id}/decision")
async def get_decision(case_id: str) -> dict:
    """Fetch the decision document."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)


@router.post("/golden-run")
async def run_golden_cases() -> dict:
    """Trigger the golden-case suite, computing real dashboard numbers."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED)
