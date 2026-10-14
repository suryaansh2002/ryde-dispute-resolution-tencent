"""L2 human review (system design §6, step 10): ratify or override an escalated
decision, or decide a safety-bypassed case that no agent ever saw.

The reviewer's decision is final (`human_ratified`). A human doesn't go through the
escalation gate, but an override still has to pass the compliance check where a case
file exists: a reviewer can't award a $500 cleaning fee either. Safety cases have no
case file (they stop before evidence collection), so there's nothing to check against,
unless the reviewer asks for one with "Prepare case file" (`prepare_safety_case_file`).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.agents.evidence_collection.agent import assemble_case_file
from app.data.cases import (
    first_trace_time,
    get_case_row,
    get_latest_decision,
    insert_decision,
    load_case_file,
    record_trace_event,
    save_case_file_if_absent,
    trace_emitter,
    trip_party_role,
    update_case,
)
from app.data.db import fetch_trip_bundle, get_connection
from app.orchestrator.adjudication import AdjudicationRejected, CaseNotFound
from app.orchestrator.state_machine import CaseStateMachine
from app.rules.compliance import compliance_check
from app.schemas import (
    CaseFile,
    CaseState,
    DecisionObject,
    DecisionOutcome,
    DisputeCategory,
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


PREPARED_DETAIL = "case file prepared for the safety team: evidence only, no model call"


@dataclass
class PreparedCaseFile:
    case_id: str
    prepared_at: datetime
    case_file: CaseFile


async def prepare_safety_case_file(case_id: str) -> PreparedCaseFile:
    """Gathers the trip records for a safety report so a reviewer can see them.

    Safety reports skip every agent (Prevention Rule 3), so nothing assembles a case file
    for them. This builds one in code from the same rows the Evidence Collection Agent
    reads, with the same assembly, but runs no model: no policy tags, no arguments, no
    recommendation. The case state doesn't change; the reviewer still decides. Running it
    twice returns the first case file."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        if case is None:
            raise CaseNotFound(case_id)
        if case["state"] != CaseState.SAFETY_BYPASSED.value:
            raise AdjudicationRejected(
                f"case is {case['state']}; only safety reports are prepared this way"
            )
        existing = load_case_file(case)
        if existing is not None:
            return PreparedCaseFile(case_id, await _prepared_at(conn, case), existing)

        trip_id, complainer_id = str(case["trip_id"]), str(case["complainer_id"])
        complainee_id = str(case["complainee_id"])
        bundle = await fetch_trip_bundle(conn, trip_id, case_id, complainer_id, complainee_id)
        case_file = assemble_case_file(
            bundle, case_id=case_id, trip_id=trip_id,
            category=DisputeCategory(case["category"] or DisputeCategory.SAFETY_INCIDENT),
            complainer_role=trip_party_role(bundle.trip, complainer_id),
            complainer_id=complainer_id, complainee_id=complainee_id, policy_tags=[],
        )
        if not await save_case_file_if_absent(conn, case_id, case_file):
            # Someone else prepared it a moment ago: theirs is the record.
            case = await get_case_row(conn, case_id)
            return PreparedCaseFile(case_id, await _prepared_at(conn, case), load_case_file(case))
        event = await record_trace_event(
            conn, case_id, TraceEventKind.TOOL_CALL, detail=PREPARED_DETAIL,
            output={"tool": "prepare_case_file", "model_calls": 0},
        )
        return PreparedCaseFile(case_id, event.t, case_file)
    finally:
        await conn.close()


async def _prepared_at(conn, case: dict) -> datetime:
    when = await first_trace_time(conn, case["id"], TraceEventKind.TOOL_CALL, PREPARED_DETAIL)
    return when or case.get("updated_at") or datetime.now(UTC)
