"""Rider Advocate (system design §6): argues the rider's side from the shared `CaseFile`."""

from app.agents.advocate import (
    AdvocateRun,
    PartyStatements,
    build_advocate_agent,
    run_advocate,
)
from app.schemas import CaseFile, CaseRole

rider_advocate_agent = build_advocate_agent(CaseRole.RIDER)


async def run_rider_advocate(
    case_file: CaseFile, statements: PartyStatements | None = None
) -> AdvocateRun:
    return await run_advocate(rider_advocate_agent, CaseRole.RIDER, case_file, statements)
