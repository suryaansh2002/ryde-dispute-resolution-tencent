from pydantic import BaseModel

from app.schemas.common import DecisionOutcome, EscalationBucket, RemedyType
from app.schemas.model_output import ModelOutput


class Remedy(BaseModel):
    type: RemedyType
    amount: float | None = None
    destination: str | None = None


class Finding(BaseModel):
    finding: str
    cites: list[str]


class JudgeVerdict(ModelOutput):
    """What the Judge model itself produces. The orchestrator wraps it into a
    `DecisionObject` once the deterministic escalation gate and compliance check have run —
    the model never authors `escalation` or `human_ratified` (system design §6.1, §7)."""

    outcome: DecisionOutcome
    remedy: Remedy
    reasoning: list[Finding]
    policy_applied: str | None
    confidence: float


class Escalation(BaseModel):
    """Populated by the deterministic escalation gate (system design §6.1), not the Judge
    model itself — except `judge_requested_escalation`, which reflects whether the Judge's
    own `escalate_to_l2` tool was called mid-run."""

    bucket: EscalationBucket
    bucket_escalate: bool
    confidence_escalate: bool
    judge_requested_escalation: bool
    # Set when the compliance check vetoed the Judge's decision (system design §4 rule 4);
    # a veto always routes to L2.
    compliance_veto: str | None = None
    # Human-readable why: which bucket rules fired, the threshold that was missed, etc.
    reasons: list[str] = []

    @property
    def routes_to_l2(self) -> bool:
        return (
            self.bucket_escalate or self.confidence_escalate
            or self.judge_requested_escalation or self.compliance_veto is not None
        )


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
