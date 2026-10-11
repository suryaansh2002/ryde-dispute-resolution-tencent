"""Claim intake (system design §6 steps 1–4): Prevention Rules 1/2 (pre-case), the
Triage Agent, Prevention Rules 3/5/6 (post-triage), and the Evidence Collection Agent,
ending at `awaiting_response`. `app/orchestrator/adjudication.py` takes it from there.

Split in two so the API can answer quickly: `open_claim` validates and creates the case
row (fast, no model calls), and `process_claim` runs everything else (tens of seconds
of agent calls). `file_claim` runs both back to back; the API's background mode
returns the case id after `open_claim` and lets the browser watch the rest over SSE.

Deliberately *not* wrapped in one DB transaction across the whole pipeline: a Triage/
Evidence Collection agent call can take seconds, and holding a transaction open across
an external API call for that long is the wrong tradeoff for a request path. Each step
commits its own state as it completes, so a mid-pipeline failure leaves the case
visibly stuck at its last real state rather than silently rolled back.
"""

import time
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
    save_case_file,
    trace_emitter,
    trip_party_role,
    update_case,
)
from app.data.db import get_connection
from app.data.usage import current_case_id
from app.orchestrator.state_machine import CaseStateMachine
from app.rules.prevention import PreventionAction, PreventionContext, run_prevention_rules
from app.schemas import CaseFile, CaseRole, CaseState, DisputeCategory, TriageResult
from app.schemas.trace import AgentName, TraceEventKind
from app.tools.image_analysis import analyze_case_photos


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


@dataclass
class OpenedClaim:
    case_id: str
    trip: dict
    trip_id: str
    complainer_id: str
    complainer_role: CaseRole
    complainee_id: str
    claim_text: str


async def open_claim(
    trip_id: str,
    complainer_id: str,
    category: DisputeCategory,
    claim_text: str,
    evidence: list[EvidenceInput] | None = None,
) -> OpenedClaim:
    """Prevention Rules 1/2, then the case row and any evidence filed with the claim."""
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
        case_id = await create_case(
            conn, trip_id, complainer_id, complainee_id, category, claim_text
        )
        for item in evidence or []:
            await insert_evidence(
                conn, case_id, item.kind, item.hash, item.object_key, complainer_id
            )
        return OpenedClaim(
            case_id, trip, trip_id, complainer_id, complainer_role, complainee_id, claim_text
        )
    finally:
        await conn.close()


async def process_claim(opened: OpenedClaim) -> FileClaimResult:
    """Triage → Prevention Rules 3/5/6 → Evidence Collection → `awaiting_response`."""
    case_id, trip_id, trip = opened.case_id, opened.trip_id, opened.trip
    current_case_id.set(case_id)  # attributes every model call below to this case
    conn = await get_connection()
    try:
        sm = CaseStateMachine(case_id=case_id, emit=trace_emitter(conn))
        await sm.transition(CaseState.TRIAGE)
        triage_result = await run_triage(opened.claim_text, trip_id)
        await update_case(
            conn, case_id, state=CaseState.TRIAGE.value, category=triage_result.category.value,
            tier=triage_result.tier, is_safety=triage_result.is_safety,
        )
        await record_trace_event(
            conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=AgentName.TRIAGE,
            output=triage_result.model_dump(mode="json"),
        )

        ctx = PreventionContext(
            trip_id=trip_id, category=triage_result.category, claimant_id=opened.complainer_id,
            trip_exists=True, claimant_is_party_to_trip=True,
            has_open_or_decided_case_for_trip=False, is_safety=triage_result.is_safety,
            has_required_evidence=await has_evidence(conn, case_id),
            claimant_dispute_count_30d=await dispute_count_30d(conn, opened.complainer_id),
            trip_completed_at=trip["completed_at"],
        )
        outcome = run_prevention_rules(ctx)
        await record_trace_event(
            conn, case_id, TraceEventKind.RULE_EVALUATION,
            detail=f"prevention: {outcome.action.value}"
            + (f" — {outcome.detail}" if outcome.detail else "")
            + (" (repeat filer flagged)" if outcome.velocity_flagged else ""),
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
            complainer_role=opened.complainer_role, complainer_id=opened.complainer_id,
            complainee_id=opened.complainee_id,
        )
        await save_case_file(conn, case_id, case_file)
        await record_trace_event(
            conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=AgentName.EVIDENCE_COLLECTION,
            output=case_file.model_dump(mode="json"),
        )
        if case_file.photos:
            case_file = await _analyze_photos(conn, case_id, case_file)

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
    except Exception as exc:
        await record_trace_event(
            conn, case_id, TraceEventKind.ERROR, detail=f"intake failed: {exc!r}"[:500]
        )
        raise
    finally:
        await conn.close()


async def file_claim(
    trip_id: str,
    complainer_id: str,
    category: DisputeCategory,
    claim_text: str,
    evidence: list[EvidenceInput] | None = None,
) -> FileClaimResult:
    opened = await open_claim(trip_id, complainer_id, category, claim_text, evidence)
    return await process_claim(opened)


async def _analyze_photos(conn, case_id: str, case_file: CaseFile) -> CaseFile:
    """Image Analysis on every photo the Evidence Collection step verified; the findings
    ride along in the CaseFile so both advocates, the Judge and the compliance check all
    see the same thing. A failure leaves that photo unanalysed, never blocks the case."""
    started = time.perf_counter()
    case_file, errors = await analyze_case_photos(case_file)
    findings = {p.evidence_id: p.analysis.model_dump() for p in case_file.photos if p.analysis}
    await save_case_file(conn, case_id, case_file)
    summary = ", ".join(
        f"{ref}: {f['mess_type'].replace('_', ' ')} → {f['tier']}" for ref, f in findings.items()
    )
    await record_trace_event(
        conn, case_id, TraceEventKind.TOOL_CALL, agent=AgentName.EVIDENCE_COLLECTION,
        latency_ms=int((time.perf_counter() - started) * 1000),
        detail=f"image analysis: {summary or 'no findings'}"
        + (f"; failed: {'; '.join(errors)}" if errors else ""),
        output={"tool": "image_analysis", "findings": findings},
    )
    return case_file
