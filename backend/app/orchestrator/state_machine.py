"""Case state machine (system design §4, §6; roadmap v3 §0).

Genuinely shared code — it calls into both devs' agents in sequence — but built
incrementally instead of left as an unowned "Shared" line item: Dev A drafts the
front-half transitions here on Day 2 (`opened -> triage -> assembling`), stubbed
against the locked schemas before the real agents exist. Dev B extends this on Day 5
with the back-half states once the Judge and escalation gate are in place. Either side
flags the other before changing a transition the other's stage depends on.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.schemas.common import CaseState

# Front half (Dev A, Day 2): opened -> triage -> assembling, plus Prevention Rules'
# hard-stop branches out of triage. Back half (Dev B, Day 5): assembling onward.
TRANSITIONS: dict[CaseState, set[CaseState]] = {
    CaseState.OPENED: {CaseState.TRIAGE},
    CaseState.TRIAGE: {
        CaseState.ASSEMBLING,
        CaseState.SAFETY_BYPASSED,
        CaseState.DECLINED_INSUFFICIENT_EVIDENCE,
    },
    CaseState.ASSEMBLING: {CaseState.AWAITING_RESPONSE, CaseState.ADJUDICATING},
    CaseState.AWAITING_RESPONSE: {CaseState.ADJUDICATING},
    CaseState.ADJUDICATING: {CaseState.DECIDED},
    CaseState.DECIDED: set(),
    CaseState.SAFETY_BYPASSED: set(),
    CaseState.DECLINED_INSUFFICIENT_EVIDENCE: set(),
}


class InvalidTransition(Exception):
    pass


@dataclass
class TraceEvent:
    """Minimal shape matching system design §7's `agent_complete` event."""

    case_id: str
    kind: str
    agent: str | None = None
    detail: str | None = None


TraceEmitter = Callable[[TraceEvent], Awaitable[None]]


async def _noop_emit(event: TraceEvent) -> None:
    """Default emitter — a no-op until Dev B's SSE trace-event bus (Day 3-4) replaces
    it, so orchestrator logic is testable before that exists."""


@dataclass
class CaseStateMachine:
    case_id: str
    state: CaseState = CaseState.OPENED
    emit: TraceEmitter = field(default=_noop_emit)

    async def transition(self, to: CaseState) -> None:
        allowed = TRANSITIONS.get(self.state, set())
        if to not in allowed:
            raise InvalidTransition(f"{self.state} -> {to} is not a valid transition")
        detail = f"{self.state} -> {to}"
        await self.emit(TraceEvent(case_id=self.case_id, kind="state_transition", detail=detail))
        self.state = to
