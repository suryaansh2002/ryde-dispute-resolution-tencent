"""Adjudication: the back half of the pipeline (system design §6 steps 5–9).

awaiting_response -> adjudicating -> both advocates in parallel -> Judge -> escalation
gate (always runs) -> compliance check (can veto) -> decision saved -> decided, or
escalated to the L2 queue.

Runs on the `CaseFile` saved at intake, so the advocates and the Judge see exactly what
the Evidence Collection Agent assembled. Agents never call each other: this module
sequences them and owns every state transition and trace event.

A case left in `adjudicating` by a crash (e.g. a Groq error) can be re-run: `adjudicate`
accepts `adjudicating` as well as `awaiting_response`.
"""

import asyncio
import time
from dataclasses import dataclass

from app.agents.advocate import PartyStatements
from app.agents.driver_advocate.agent import run_driver_advocate
from app.agents.judge.agent import run_judge
from app.agents.rider_advocate.agent import run_rider_advocate
from app.data.cases import (
    get_case_row,
    get_latest_response,
    insert_decision,
    insert_response,
    load_case_file,
    record_trace_event,
    trace_emitter,
    update_case,
)
from app.data.db import get_connection
from app.data.usage import current_case_id
from app.orchestrator.decision_document import render_decision_document
from app.orchestrator.state_machine import CaseStateMachine
from app.rules.compliance import compliance_check
from app.rules.escalation import run_escalation_gate
from app.schemas import Argument, CaseFile, CaseState, DecisionObject
from app.schemas.trace import AgentName, TraceEventKind

_ADJUDICABLE = {CaseState.AWAITING_RESPONSE, CaseState.ADJUDICATING}


class CaseNotFound(Exception):
    pass


class AdjudicationRejected(Exception):
    """The request doesn't fit the case's current state (wrong state, wrong respondent)."""


@dataclass
class AdjudicationResult:
    case_id: str
    state: CaseState
    decision: DecisionObject
    rider_argument: Argument
    driver_argument: Argument
    document: str


async def submit_response(case_id: str, respondent_id: str, text: str) -> AdjudicationResult:
    """The complainee answers the allegation, which triggers adjudication."""
    await store_response(case_id, respondent_id, text)
    return await adjudicate(case_id)


async def store_response(case_id: str, respondent_id: str, text: str) -> None:
    """Validate and save the complainee's answer; fast, no model calls."""
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        if case is None:
            raise CaseNotFound(case_id)
        if case["state"] != CaseState.AWAITING_RESPONSE:
            raise AdjudicationRejected(f"case is {case['state']}, not awaiting a response")
        if str(case["complainee_id"]) != str(respondent_id):
            raise AdjudicationRejected("only the party the claim was filed against can respond")
        await insert_response(conn, case_id, respondent_id, text)
        await record_trace_event(
            conn, case_id, TraceEventKind.STATE_TRANSITION, detail="response received"
        )
    finally:
        await conn.close()


def _adjudicable(case_id: str, case: dict | None) -> tuple[CaseState, CaseFile]:
    if case is None:
        raise CaseNotFound(case_id)
    state = CaseState(case["state"])
    if state not in _ADJUDICABLE:
        raise AdjudicationRejected(f"case is {state}, which can't be adjudicated")
    case_file = load_case_file(case)
    if case_file is None:
        raise AdjudicationRejected("case has no assembled case file")
    return state, case_file


async def check_adjudicable(case_id: str) -> None:
    """The same preconditions `adjudicate` enforces, checked without running it, so a
    background run can be refused before the request returns."""
    conn = await get_connection()
    try:
        _adjudicable(case_id, await get_case_row(conn, case_id))
    finally:
        await conn.close()


async def adjudicate(case_id: str) -> AdjudicationResult:
    current_case_id.set(case_id)  # attributes every model call below to this case
    conn = await get_connection()
    try:
        case = await get_case_row(conn, case_id)
        state, case_file = _adjudicable(case_id, case)

        sm = CaseStateMachine(case_id=case_id, state=state, emit=trace_emitter(conn))
        if state == CaseState.AWAITING_RESPONSE:
            await sm.transition(CaseState.ADJUDICATING)
            await update_case(conn, case_id, state=CaseState.ADJUDICATING.value)

        try:
            return await _run_adjudication(conn, case_id, case, case_file, sm)
        except Exception as exc:
            await record_trace_event(
                conn, case_id, TraceEventKind.ERROR,
                detail=f"adjudication failed (re-run with POST /cases/{case_id}/adjudicate): "
                       f"{exc!r}"[:500],
            )
            raise
    finally:
        await conn.close()


async def _run_adjudication(
    conn, case_id: str, case: dict, case_file: CaseFile, sm: CaseStateMachine
) -> AdjudicationResult:
    response = await get_latest_response(conn, case_id)
    statements = PartyStatements(
        complainer_role=case_file.complainer_role,
        claim_text=case["claim_text"] or "",
        response_text=response["text"] if response else None,
    )

    started = time.perf_counter()
    rider_run, driver_run = await asyncio.gather(
        run_rider_advocate(case_file, statements), run_driver_advocate(case_file, statements)
    )
    advocates_ms = int((time.perf_counter() - started) * 1000)
    for name, run in (
        (AgentName.RIDER_ADVOCATE, rider_run), (AgentName.DRIVER_ADVOCATE, driver_run)
    ):
        stripped = run.stripped_cites + run.stripped_policy_cites
        await record_trace_event(
            conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=name, latency_ms=advocates_ms,
            detail=f"citations stripped: {stripped}" if stripped else "argument validated",
            output=run.argument.model_dump(mode="json"),
        )

    started = time.perf_counter()
    judge_run = await run_judge(case_file, rider_run.argument, driver_run.argument)
    judge_ms = int((time.perf_counter() - started) * 1000)
    verdict = judge_run.verdict

    escalation = run_escalation_gate(
        case_file, verdict,
        judge_requested=judge_run.requested_escalation,
        judge_request_reason=judge_run.escalation_reason,
    )
    veto = compliance_check(case_file, verdict)
    if veto:
        escalation = escalation.model_copy(update={"compliance_veto": veto})

    decision = DecisionObject(
        case_id=case_id, outcome=verdict.outcome.value, remedy=verdict.remedy,
        reasoning=verdict.reasoning, policy_applied=verdict.policy_applied,
        confidence=verdict.confidence, escalation=escalation,
    )
    await insert_decision(conn, decision)
    judge_detail = "decision object validated"
    if judge_run.flagged:
        judge_detail = (
            f"citations stripped: {judge_run.stripped_cites}, "
            f"policy stripped: {judge_run.stripped_policy}"
        )
    await record_trace_event(
        conn, case_id, TraceEventKind.AGENT_OUTPUT, agent=AgentName.JUDGE,
        latency_ms=judge_ms, detail=judge_detail, output=decision.model_dump(mode="json"),
    )
    await record_trace_event(
        conn, case_id, TraceEventKind.RULE_EVALUATION,
        detail=f"escalation gate: bucket={escalation.bucket.value}, "
               f"confidence_escalate={escalation.confidence_escalate}, "
               f"judge_requested={escalation.judge_requested_escalation}; "
               f"compliance: {'veto — ' + veto if veto else 'pass'}",
    )

    final = CaseState.ESCALATED if escalation.routes_to_l2 else CaseState.DECIDED
    if final == CaseState.ESCALATED:
        await record_trace_event(
            conn, case_id, TraceEventKind.ESCALATION,
            detail="; ".join(
                escalation.reasons + ([f"compliance veto: {veto}"] if veto else [])
            ),
        )
    await sm.transition(final)
    await update_case(conn, case_id, state=final.value)

    return AdjudicationResult(
        case_id=case_id, state=final, decision=decision,
        rider_argument=rider_run.argument, driver_argument=driver_run.argument,
        document=render_decision_document(decision, case_file),
    )
