from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class TraceEventKind(StrEnum):
    STATE_TRANSITION = "state_transition"
    RULE_EVALUATION = "rule_evaluation"
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_OUTPUT = "agent_output"
    ESCALATION = "escalation"
    L2_REVIEW = "l2_review"


class AgentName(StrEnum):
    TRIAGE = "triage"
    EVIDENCE_COLLECTION = "evidence_collection"
    RIDER_ADVOCATE = "rider_advocate"
    DRIVER_ADVOCATE = "driver_advocate"
    JUDGE = "judge"


class TraceEvent(BaseModel):
    """One row of `trace_events`, and one SSE `data:` message (system design §7).

    `agent_complete` is the lightweight timeline event; `agent_output` carries the typed
    output an agent produced (an `Argument`, a `DecisionObject`, ...) in `output`, which
    is what the trace panel renders as argument cards.
    """

    id: int | None = None  # DB-assigned; doubles as the SSE event id for Last-Event-ID replay
    t: datetime
    kind: TraceEventKind
    case_id: str
    agent: AgentName | None = None
    detail: str | None = None
    latency_ms: int | None = None
    output: dict | None = None
