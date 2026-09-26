import pytest

from app.orchestrator.state_machine import CaseStateMachine, InvalidTransition, TraceEvent
from app.schemas.common import CaseState


async def test_valid_transition_updates_state():
    sm = CaseStateMachine(case_id="case-1")
    await sm.transition(CaseState.TRIAGE)
    assert sm.state == CaseState.TRIAGE


async def test_invalid_transition_raises():
    sm = CaseStateMachine(case_id="case-1")
    with pytest.raises(InvalidTransition):
        await sm.transition(CaseState.DECIDED)


async def test_safety_hard_stop_from_triage():
    sm = CaseStateMachine(case_id="case-1", state=CaseState.TRIAGE)
    await sm.transition(CaseState.SAFETY_BYPASSED)
    assert sm.state == CaseState.SAFETY_BYPASSED
    # Terminal — nothing transitions out of a safety bypass.
    with pytest.raises(InvalidTransition):
        await sm.transition(CaseState.ASSEMBLING)


async def test_emit_hook_called_on_transition():
    received: list[TraceEvent] = []

    async def capture(event: TraceEvent) -> None:
        received.append(event)

    sm = CaseStateMachine(case_id="case-1", emit=capture)
    await sm.transition(CaseState.TRIAGE)
    assert len(received) == 1
    assert received[0].case_id == "case-1"
    assert received[0].kind == "state_transition"
