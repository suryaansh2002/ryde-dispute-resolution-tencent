from pydantic import BaseModel

from app.schemas.common import EscalationBucket, RemedyType


class Remedy(BaseModel):
    type: RemedyType
    amount: float | None = None
    destination: str | None = None


class Finding(BaseModel):
    finding: str
    cites: list[str]


class Escalation(BaseModel):
    """Populated by the deterministic escalation gate (system design §6.1), not the Judge
    model itself — except `judge_requested_escalation`, which reflects whether the Judge's
    own `escalate_to_l2` tool was called mid-run."""

    bucket: EscalationBucket
    bucket_escalate: bool
    confidence_escalate: bool
    judge_requested_escalation: bool


class DecisionObject(BaseModel):
    case_id: str
    outcome: str
    remedy: Remedy
    reasoning: list[Finding]
    policy_applied: str | None
    confidence: float
    escalation: Escalation
    human_ratified: bool = False
    ratified_by: str | None = None
