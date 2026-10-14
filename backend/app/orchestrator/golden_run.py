"""Golden run (data sources doc §4 step 11): file every labelled golden case for real,
through the whole pipeline with real model calls, and score the result against the
label the synthetic generator wrote from ground truth.

What is scored is the *verdict* (the Judge's outcome, remedy and amount), not whether
the case also went to a human: routing depends on live state such as how many disputes
a user has open, which a run itself changes. Routing is reported next to the score
("decided automatically" vs "sent to a person"), not folded into it.

Each run first deletes the cases the previous run created, so the duplicate-claim rule
doesn't block re-filing and old runs don't count towards anyone's 30-day dispute total.
Cases run a few at a time to stay under Groq's tokens-per-minute limit.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.data.db import get_connection
from app.orchestrator import adjudication, pipeline
from app.schemas import CaseState, DisputeCategory
from app.tools.evidence_lookup import ROUTE_COMPARISON, evidence_index

CONCURRENCY = 2
_UPHELD = {"claim_upheld", "claim_upheld_partial"}
_REFUNDS = {"partial_refund", "full_refund"}


@dataclass
class RunState:
    running: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    total: int = 0
    done: int = 0
    errors: list[str] = field(default_factory=list)


state = RunState()


def score(expected: dict, actual: dict) -> tuple[bool, str]:
    """(passed, why). `actual` has: state, outcome, remedy {type, amount}, and for route
    cases route_refund (the policy formula's amount for this trip)."""
    exp_outcome = expected["outcome"]
    if actual.get("error"):
        return False, f"pipeline error: {actual['error']}"
    if exp_outcome == "escalated_to_l2":  # safety: must never reach an agent verdict
        ok = actual["state"] == CaseState.SAFETY_BYPASSED.value
        return ok, "routed to a person at triage" if ok else f"ended {actual['state']}"
    if exp_outcome == "declined_insufficient_evidence":
        ok = (
            actual["state"] == CaseState.DECLINED_INSUFFICIENT_EVIDENCE.value
            or actual.get("outcome") == exp_outcome
        )
        got = actual.get("outcome") or actual["state"]
        return ok, "declined" if ok else f"expected declined, got {got}"

    outcome = actual.get("outcome")
    if outcome is None:
        return False, f"no verdict (ended {actual['state']})"
    if exp_outcome in _UPHELD:
        if outcome not in _UPHELD:
            return False, f"expected upheld, got {outcome}"
    elif outcome != exp_outcome:
        return False, f"expected {exp_outcome}, got {outcome}"

    exp_remedy, remedy = expected.get("remedy") or {}, actual.get("remedy") or {}
    exp_type, got_type = exp_remedy.get("type"), remedy.get("type")
    if exp_type == "no_action":
        return (got_type == "no_action"), "" if got_type == "no_action" else f"remedy {got_type}"
    if exp_type in _REFUNDS:
        if got_type not in _REFUNDS:
            return False, f"expected a refund, got {got_type}"
        want = actual.get("route_refund")
    else:
        if got_type != exp_type:
            return False, f"expected {exp_type}, got {got_type}"
        want = exp_remedy.get("amount")
    got = remedy.get("amount")
    if want is not None and (got is None or abs(got - want) > 0.01):
        return False, f"amount ${got} ≠ expected ${want}"
    return True, ""


async def _load_golden(conn) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT g.id, g.trip_id, g.case_id, g.expected_outcome, g.prepared_evidence,
                  t.rider_id, t.driver_id, t.category_hint
           FROM golden_cases g JOIN trips t ON t.id = g.trip_id
           ORDER BY t.category_hint, g.id"""
    )
    out = []
    for r in rows:
        row = dict(r)
        for key in ("expected_outcome", "prepared_evidence"):
            if isinstance(row[key], str):
                row[key] = json.loads(row[key])
        out.append(row)
    return out


async def _delete_cases(conn, case_ids: list[str]) -> None:
    if not case_ids:
        return
    await conn.execute(
        "UPDATE golden_cases SET case_id = NULL WHERE case_id = ANY($1::text[])", case_ids
    )
    for table in ("trace_events", "decisions", "evidence", "responses"):
        await conn.execute(f"DELETE FROM {table} WHERE case_id = ANY($1::text[])", case_ids)
    await conn.execute("DELETE FROM cases WHERE id = ANY($1::text[])", case_ids)


async def _run_one(golden: dict) -> dict:
    expected = golden["expected_outcome"]
    role = expected.get("complainer_role", "rider")
    complainer = golden["rider_id"] if role == "rider" else golden["driver_id"]
    evidence = [
        pipeline.EvidenceInput(kind=e["kind"], hash=e["hash"], object_key=e["object_key"])
        for e in golden["prepared_evidence"]
    ]
    started = time.perf_counter()
    actual: dict[str, Any] = {"state": None}
    case_id = None
    try:
        opened = await pipeline.open_claim(
            str(golden["trip_id"]), str(complainer), DisputeCategory(golden["category_hint"]),
            expected.get("claim_text", ""), evidence,
        )
        case_id = opened.case_id
        filed = await pipeline.process_claim(opened)
        actual["state"] = filed.state.value
        if filed.state == CaseState.AWAITING_RESPONSE:
            result = await adjudication.adjudicate(case_id)
            decision = result.decision
            actual.update(
                state=result.state.value,
                outcome=decision.outcome,
                remedy=decision.remedy.model_dump(mode="json"),
                confidence=decision.confidence,
                escalation_reasons=decision.escalation.reasons
                + ([f"compliance veto: {decision.escalation.compliance_veto}"]
                   if decision.escalation.compliance_veto else []),
            )
            comparison = evidence_index(filed.case_file).get(ROUTE_COMPARISON)
            if comparison:
                actual["route_refund"] = comparison.data["refund_if_unjustified"]
    except Exception as exc:  # noqa: BLE001 — a failed case is a failed test, not a crash
        actual["error"] = repr(exc)[:300]
    passed, why = score(expected, actual)
    return {
        "case_id": case_id,
        "category": golden["category_hint"],
        "expected": {k: v for k, v in expected.items() if k != "claim_text"},
        "actual": actual,
        "passed": passed,
        "why": why,
        "seconds": round(time.perf_counter() - started, 1),
        "ran_at": datetime.now(UTC).isoformat(),
    }


async def run_golden(limit: int | None = None) -> list[dict]:
    if state.running:
        raise RuntimeError("a golden run is already in progress")
    state.running, state.errors = True, []
    state.started_at, state.finished_at = datetime.now(UTC).isoformat(), None
    try:
        conn = await get_connection()
        try:
            goldens = await _load_golden(conn)
            await _delete_cases(conn, [g["case_id"] for g in goldens if g["case_id"]])
        finally:
            await conn.close()
        goldens = goldens[:limit] if limit else goldens
        state.total, state.done = len(goldens), 0
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(golden: dict) -> dict:
            # One case's failure (a network blip, a dropped connection) is that case's
            # error, recorded like any other; it never aborts the rest of the run.
            try:
                async with gate:
                    result = await _run_one(golden)
                conn = await get_connection()
                try:
                    await conn.execute(
                        "UPDATE golden_cases SET case_id = $2, last_run_result = $3 WHERE id = $1",
                        golden["id"], result["case_id"], json.dumps(result),
                    )
                finally:
                    await conn.close()
            except Exception as exc:  # noqa: BLE001 — reported per case, not raised
                expected = golden["expected_outcome"]
                result = {
                    "case_id": None, "category": golden["category_hint"],
                    "expected": {k: v for k, v in expected.items() if k != "claim_text"},
                    "actual": {"state": None, "error": f"run failed: {exc!r}"[:300]},
                    "passed": False, "why": "the run failed before a verdict", "seconds": 0.0,
                    "ran_at": datetime.now(UTC).isoformat(),
                }
            state.done += 1
            if result["actual"].get("error"):
                state.errors.append(f"{golden['id']}: {result['actual']['error']}")
            return result

        return await asyncio.gather(*(one(g) for g in goldens))
    finally:
        state.running = False
        state.finished_at = datetime.now(UTC).isoformat()


async def golden_report() -> dict:
    """Pass rate overall and per category, routing, and every case's last result."""
    conn = await get_connection()
    try:
        goldens = await _load_golden(conn)
        rows = await conn.fetch("SELECT id, last_run_result FROM golden_cases")
    finally:
        await conn.close()
    results = {
        r["id"]: (json.loads(r["last_run_result"]) if isinstance(r["last_run_result"], str)
                  else r["last_run_result"])
        for r in rows
    }
    cases, by_category = [], {}
    for g in goldens:
        res = results.get(g["id"])
        cases.append({"golden_id": str(g["id"]), "category": g["category_hint"],
                      "expected": {k: v for k, v in g["expected_outcome"].items()
                                   if k != "claim_text"},
                      "claim_text": g["expected_outcome"].get("claim_text"),
                      "result": res})
        bucket = by_category.setdefault(g["category_hint"], {"total": 0, "run": 0, "passed": 0})
        bucket["total"] += 1
        if res:
            bucket["run"] += 1
            bucket["passed"] += int(res["passed"])
    ran = [c["result"] for c in cases if c["result"]]
    auto = sum(1 for r in ran if r["actual"].get("state") == CaseState.DECIDED.value)
    return {
        "total": len(cases),
        "run": len(ran),
        "passed": sum(int(r["passed"]) for r in ran),
        "decided_automatically": auto,
        "sent_to_a_person": len(ran) - auto,
        "median_seconds": sorted(r["seconds"] for r in ran)[len(ran) // 2] if ran else None,
        "by_category": by_category,
        "cases": cases,
        "status": {
            "running": state.running, "started_at": state.started_at,
            "finished_at": state.finished_at, "total": state.total, "done": state.done,
            "errors": state.errors,
        },
    }
