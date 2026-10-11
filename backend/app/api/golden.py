"""Golden run (data sources doc §4 step 11): score the pipeline against labelled cases."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.orchestrator import golden_run

router = APIRouter(tags=["golden"])


@router.post("/golden-run", status_code=status.HTTP_202_ACCEPTED)
async def start_golden_run(
    background: BackgroundTasks, limit: int | None = Query(None, ge=1, le=100)
) -> dict:
    """Files every golden case for real (real model calls, a few minutes) and scores each
    verdict against its label. Returns at once; poll GET /golden-run for progress."""
    if golden_run.state.running:
        raise HTTPException(status.HTTP_409_CONFLICT, "a golden run is already in progress")
    background.add_task(golden_run.run_golden, limit)
    return {"status": "started"}


@router.get("/golden-run")
async def golden_report() -> dict:
    """Last run's pass rate, overall and per category, plus every case's result."""
    return await golden_run.golden_report()
