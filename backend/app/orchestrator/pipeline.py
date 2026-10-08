"""Claim intake pipeline (system design §6 steps 1-4; roadmap v3 Day 3-5).

Wires together everything on Dev A's side of the seam: Prevention Rules 1/2 (pre-case),
the Triage Agent, Prevention Rules 3/5/6 (post-triage), and the Evidence Collection
Agent — ending at `awaiting_response`, which is as far as Dev A's half of the pipeline
goes. Dev B's Day-5 extension picks up from there (response handling -> Advocates ->
Judge -> escalation gate), per `app/orchestrator/state_machine.py`'s back-half states.

Deliberately *not* wrapped in one DB transaction across the whole pipeline: a Triage/
Evidence Collection agent call can take seconds, and holding a transaction open across
an external API call for that long is the wrong tradeoff for a request path. Each step
commits its own state as it completes, so a mid-pipeline failure leaves the case
visibly stuck at its last real state rather than silently rolled back.
"""

from dataclasses import dataclass

from app.agents.evidence_collection.agent import run_evidence_collection
from app.agents.triage.agent import run_triage
from app.data.cases import (
    create_case,
    dispute_count_30d,
    get_trip,
    has_evidence,
    has_open_or_decided_case,
    insert_evidence,
    other_party_id,
    record_trace_event,
    trip_party_role,
    update_case,
)
from app.data.db import get_connection
from app.orchestrator.state_machine import CaseStateMachine
from app.rules.prevention import PreventionAction, PreventionContext, run_prevention_rules
from app.schemas import CaseFile, CaseState, DisputeCategory, TriageResult
from app.schemas.trace import AgentName, TraceEventKind


class ClaimRejected(Exception):
    """Prevention Rule 1 or 2 — rejected before any case row is created."""


@dataclass
class EvidenceInput:
    kind: str
    hash: str
    object_key: str


@dataclass
class FileClaimResult:
    case_id: str
    state: CaseState
    triage: TriageResult
    velocity_flagged: bool
    case_file: CaseFile | None = None
    detail: str = ""


async def file_claim(
    trip_id: str,
    complainer_id: str,
    category: DisputeCategory,
    claim_text: str,
    evidence: list[EvidenceInput] | None = None,
) -> FileClaimResult:
    evidence = evidence or []
    conn = await get_connection()
    try:
        trip = await get_trip(conn, trip_id)
        if trip is None:
            raise ClaimRejected(f"no trip {trip_id!r}")
        complainer_role = trip_party_role(trip, complainer_id)
        if complainer_role is None:
            raise ClaimRejected(f"{complainer_id!r} is not a party to trip {trip_id!r}")
        if await has_open_or_decided_case(conn, trip_id):
            raise ClaimRejected(f"an open or decided case already exists for trip {trip_id!r}")

        complainee_id = other_party_id(trip, complainer_role)
        case_id = await create_case(conn, trip_id, complainer_id, complainee_id, category)
        sm = CaseStateMachine(case_id=case_id)

        for item in evidence:
            await insert_evidence(
                conn, case_id, item.kind, item.hash, item.object_key, complainer_id
            )

        await sm.transition(CaseState.TRIAGE)
        triage_result = await run_triage(claim_text, trip_id)
        await update_case(
            conn, case_id, state=CaseState.TRIAGE.value, category=triage_result.category.value,
            tier=triage_result.tier, is_safety=triage_result.is_safety,
        )
        await record_trace_event(
            conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=AgentName.TRIAGE,
            output=triage_result.model_dump(mode="json"),
        )

        ctx = PreventionContext(
            trip_id=trip_id, category=triage_result.category, claimant_id=complainer_id,
            trip_exists=True, claimant_is_party_to_trip=True,
            has_open_or_decided_case_for_trip=False, is_safety=triage_result.is_safety,
            has_required_evidence=await has_evidence(conn, case_id),
            claimant_dispute_count_30d=await dispute_count_30d(conn, complainer_id),
            trip_completed_at=trip["completed_at"],
        )
        outcome = run_prevention_rules(ctx)
        await record_trace_event(
            conn, case_id, TraceEventKind.RULE_EVALUATION,
            detail=f"prevention: {outcome.action.value} ({outcome.detail})",
        )

        if outcome.action == PreventionAction.SAFETY_BYPASSED:
            await sm.transition(CaseState.SAFETY_BYPASSED)
            await update_case(conn, case_id, state=CaseState.SAFETY_BYPASSED.value)
            return FileClaimResult(
                case_id, CaseState.SAFETY_BYPASSED, triage_result, outcome.velocity_flagged,
                detail=outcome.detail,
            )
        declined_actions = (
            PreventionAction.DECLINED_STALE, PreventionAction.DECLINED_INSUFFICIENT_EVIDENCE
        )
        if outcome.action in declined_actions:
            await sm.transition(CaseState.DECLINED_INSUFFICIENT_EVIDENCE)
            await update_case(conn, case_id, state=CaseState.DECLINED_INSUFFICIENT_EVIDENCE.value)
            return FileClaimResult(
                case_id, CaseState.DECLINED_INSUFFICIENT_EVIDENCE, triage_result,
                outcome.velocity_flagged, detail=outcome.detail,
            )

        await sm.transition(CaseState.ASSEMBLING)
        await update_case(conn, case_id, state=CaseState.ASSEMBLING.value)
        case_file = await run_evidence_collection(
            trip_id=trip_id, case_id=case_id, triage_result=triage_result,
            complainer_role=complainer_role, complainer_id=complainer_id,
            complainee_id=complainee_id,
        )
        await record_trace_event(
            conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=AgentName.EVIDENCE_COLLECTION,
            output=case_file.model_dump(mode="json"),
        )

        if triage_result.category == DisputeCategory.PROPERTY_DAMAGE and not case_file.photos:
            await sm.transition(CaseState.DECLINED_INSUFFICIENT_EVIDENCE)
            await update_case(conn, case_id, state=CaseState.DECLINED_INSUFFICIENT_EVIDENCE.value)
            return FileClaimResult(
                case_id, CaseState.DECLINED_INSUFFICIENT_EVIDENCE, triage_result,
                outcome.velocity_flagged, case_file=case_file,
                detail="property_damage claim has no verified photo evidence after assembly",
            )

        await sm.transition(CaseState.AWAITING_RESPONSE)
        await update_case(conn, case_id, state=CaseState.AWAITING_RESPONSE.value)
        return FileClaimResult(
            case_id, CaseState.AWAITING_RESPONSE, triage_result, outcome.velocity_flagged,
            case_file=case_file,
        )
    finally:
        await conn.close()
