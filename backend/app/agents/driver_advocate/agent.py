"""Driver Advocate (system design §6): argues the driver's side from the shared `CaseFile`."""

from app.agents.advocate import (
    AdvocateRun,
    PartyStatements,
    build_advocate_agent,
    run_advocate,
)
from app.schemas import CaseFile, CaseRole

driver_advocate_agent = build_advocate_agent(CaseRole.DRIVER)


async def run_driver_advocate(
    case_file: CaseFile, statements: PartyStatements | None = None
) -> AdvocateRun:
    return await run_advocate(driver_advocate_agent, CaseRole.DRIVER, case_file, statements)
