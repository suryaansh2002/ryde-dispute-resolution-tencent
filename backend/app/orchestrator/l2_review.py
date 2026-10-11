"""L2 human review (system design §6, step 10): ratify or override an escalated
decision, or decide a safety-bypassed case that no agent ever saw.

The reviewer's decision is final (`human_ratified`). A human doesn't go through the
escalation gate, but an override still has to pass the compliance check where a case
file exists: a reviewer can't award a $500 cleaning fee either. Safety cases have no
case file (they stop before evidence collection), so there's nothing to check against.
"""

from dataclasses import dataclass
from typing import Literal

from app.data.cases import (
    get_case_row,
    get_latest_decision,
    insert_decision,
    load_case_file,
    record_trace_event,
    trace_emitter,
    update_case,
)
from app.data.db import get_connection
from app.orchestrator.adjudication import AdjudicationRejected, CaseNotFound
from app.orchestrator.state_machine import CaseStateMachine
from app.rules.compliance import compliance_check
from app.schemas import (
    CaseState,
    DecisionObject,
    DecisionOutcome,
    Escalation,
    EscalationBucket,
    Finding,
    JudgeVerdict,
    Remedy,
)
from app.schemas.trace import TraceEventKind


class ReviewInvalid(Exception):
    """The reviewer's override fails the compliance check, or is incomplete."""


@dataclass
class ReviewRequest:
    reviewer: str
    action: Literal["ratify", "override"]
    note: str
    outcome: DecisionOutcome | None = None
    remedy: Remedy | None = None
    policy_applied: str | None = None


def _note(review: ReviewRequest) -> Finding:
    verb = "ratified" if review.action == "ratify" else "overrode"
    return Finding(finding=f"L2 reviewer {review.reviewer} {verb}: {review.note}", cites=[])


async def review_case(case_id: str, review: ReviewRequest) -> DecisionObject:
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        if case is None:
            raise CaseNotFound(case_id)
        state = CaseState(case["state"])
        if state not in (CaseState.ESCALATED, CaseState.SAFETY_BYPASSED):
            raise AdjudicationRejected(f"case is {state}, not waiting for L2 review")
        previous = await get_latest_decision(conn, case_id)

        if review.action == "ratify":
            if previous is None:
                raise ReviewInvalid("nothing to ratify: no agent decision exists for this case")
            decision = previous.model_copy(update={
                "reasoning": [*previous.reasoning, _note(review)],
                "human_ratified": True, "ratified_by": review.reviewer,
            })
        else:
            if review.outcome is None or review.remedy is None:
                raise ReviewInvalid("an override needs an outcome and a remedy")
            policy = review.policy_applied or (previous.policy_applied if previous else None)
            case_file = load_case_file(case)
            if case_file is not None:
                veto = compliance_check(case_file, JudgeVerdict(
                    outcome=review.outcome, remedy=review.remedy,
                    reasoning=[_note(review)], policy_applied=policy, confidence=1.0,
                ))
                if veto:
                    raise ReviewInvalid(veto)
            escalation = previous.escalation if previous else Escalation(
                bucket=EscalationBucket.ALWAYS_ESCALATE, bucket_escalate=True,
                confidence_escalate=False, judge_requested_escalation=False,
                reasons=["safety incident: human review only (Prevention Rule 3)"],
            )
            decision = DecisionObject(
                case_id=case_id, outcome=review.outcome.value, remedy=review.remedy,
                reasoning=[*(previous.reasoning if previous else []), _note(review)],
                policy_applied=policy, confidence=1.0, escalation=escalation,
                human_ratified=True, ratified_by=review.reviewer,
            )

        await insert_decision(conn, decision)
        await record_trace_event(
            conn, case_id, TraceEventKind.L2_REVIEW,
            detail=f"{review.reviewer} {review.action}: {review.note}",
            output=decision.model_dump(mode="json"),
        )
        sm = CaseStateMachine(case_id=case_id, state=state, emit=trace_emitter(conn))
        await sm.transition(CaseState.DECIDED)
        await update_case(conn, case_id, state=CaseState.DECIDED.value)
        return decision
    finally:
        await conn.close()
