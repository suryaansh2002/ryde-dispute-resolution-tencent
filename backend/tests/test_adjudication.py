"""Adjudication orchestration + its endpoints. DB and agent calls are monkeypatched at
the names `app.orchestrator.adjudication` imported, so these check sequencing and
routing only — no Postgres, no Groq."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.orchestrator.adjudication as adj
from app.agents.advocate import AdvocateRun
from app.agents.judge.agent import JudgeRun
from app.main import app
from app.schemas import Argument, CaseRole, CaseState, DecisionOutcome, JudgeVerdict, Remedy
from app.schemas.common import RemedyType

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


class FakeConn:
    async def close(self):
        pass


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


def case_row(name="route_deviation", state="awaiting_response"):
    return {
        "id": "CASE-0001", "state": state, "complainee_id": "USER-0002",
        "claim_text": "the driver took a long detour",
        "case_file": (CASE_FILES / f"{name}.json").read_text(),
    }


def advocate_run(role):
    arg = Argument(role=role, text="arg", cites=["PAYMENT"], policy_cites=["POL-02"],
                   confidence=0.6)
    return AdvocateRun(arg, [], [])


def judge_run(outcome=DecisionOutcome.CLAIM_DENIED, remedy=RemedyType.NO_ACTION, amount=None,
              confidence=0.85, requested=False, policy="POL-02"):
    v = JudgeVerdict(
        outcome=outcome, remedy=Remedy(type=remedy, amount=amount),
        reasoning=[{"finding": "f", "cites": ["ROUTE-COMPARISON"]}],
        policy_applied=policy, confidence=confidence,
    )
    return JudgeRun(v, requested, "unsure" if requested else None, [], None)


@pytest.fixture
def wired(monkeypatch):
    calls = {"states": [], "decisions": [], "responses": [], "statements": []}

    async def update_case(conn, case_id, *, state, **kw):
        calls["states"].append(state)

    async def insert_decision(conn, decision):
        calls["decisions"].append(decision)

    async def insert_response(conn, case_id, respondent_id, text):
        calls["responses"].append((respondent_id, text))

    def advocate(role):
        async def run(case_file, statements=None):
            calls["statements"].append(statements)
            return advocate_run(role)
        return run

    monkeypatch.setattr(adj, "get_connection", _async(FakeConn()))
    monkeypatch.setattr(adj, "get_case_row", _async(case_row()))
    monkeypatch.setattr(adj, "get_latest_response", _async({"text": "road was closed"}))
    monkeypatch.setattr(adj, "insert_response", insert_response)
    monkeypatch.setattr(adj, "insert_decision", insert_decision)
    monkeypatch.setattr(adj, "update_case", update_case)
    monkeypatch.setattr(adj, "record_trace_event", _async(None))
    monkeypatch.setattr(adj, "trace_emitter", lambda conn: _async(None))
    monkeypatch.setattr(adj, "run_rider_advocate", advocate(CaseRole.RIDER))
    monkeypatch.setattr(adj, "run_driver_advocate", advocate(CaseRole.DRIVER))
    monkeypatch.setattr(adj, "run_judge", _async(judge_run()))
    return calls


async def test_confident_compliant_decision_is_final(wired):
    result = await adj.adjudicate("CASE-0001")
    assert result.state == CaseState.DECIDED
    assert wired["states"] == ["adjudicating", "decided"]
    assert len(wired["decisions"]) == 1
    assert not result.decision.escalation.routes_to_l2
    assert "**Final**" in result.document


async def test_low_confidence_escalates(wired, monkeypatch):
    monkeypatch.setattr(adj, "run_judge", _async(judge_run(confidence=0.4)))
    result = await adj.adjudicate("CASE-0001")
    assert result.state == CaseState.ESCALATED
    assert result.decision.escalation.confidence_escalate
    assert "Pending human review" in result.document


async def test_judge_request_escalates(wired, monkeypatch):
    monkeypatch.setattr(adj, "run_judge", _async(judge_run(requested=True)))
    result = await adj.adjudicate("CASE-0001")
    assert result.state == CaseState.ESCALATED
    assert result.decision.escalation.judge_requested_escalation


async def test_compliance_veto_escalates_without_changing_the_outcome(wired, monkeypatch):
    # Denied claim carrying a refund: compliance vetoes, never edits.
    bad = judge_run(DecisionOutcome.CLAIM_DENIED, RemedyType.PARTIAL_REFUND, 3.0)
    monkeypatch.setattr(adj, "run_judge", _async(bad))
    result = await adj.adjudicate("CASE-0001")
    assert result.state == CaseState.ESCALATED
    assert result.decision.escalation.compliance_veto
    assert result.decision.outcome == "claim_denied"
    assert result.decision.remedy.type == RemedyType.PARTIAL_REFUND


async def test_advocates_get_both_statements(wired):
    await adj.adjudicate("CASE-0001")
    statements = wired["statements"]
    assert len(statements) == 2
    assert statements[0].claim_text == "the driver took a long detour"
    assert statements[0].response_text == "road was closed"


async def test_rerun_from_adjudicating_skips_the_entry_transition(wired, monkeypatch):
    monkeypatch.setattr(adj, "get_case_row", _async(case_row(state="adjudicating")))
    result = await adj.adjudicate("CASE-0001")
    assert result.state == CaseState.DECIDED
    assert wired["states"] == ["decided"]


async def test_decided_case_cannot_be_readjudicated(wired, monkeypatch):
    monkeypatch.setattr(adj, "get_case_row", _async(case_row(state="decided")))
    with pytest.raises(adj.AdjudicationRejected):
        await adj.adjudicate("CASE-0001")


async def test_only_the_complainee_can_respond(wired):
    with pytest.raises(adj.AdjudicationRejected):
        await adj.submit_response("CASE-0001", "USER-0001", "it wasn't me")
    assert wired["responses"] == []


async def test_response_is_stored_then_adjudicated(wired):
    result = await adj.submit_response("CASE-0001", "USER-0002", "road was closed")
    assert wired["responses"] == [("USER-0002", "road was closed")]
    assert result.state == CaseState.DECIDED


def test_response_endpoint_maps_errors(wired, monkeypatch):
    client = TestClient(app)
    ok = client.post("/cases/CASE-0001/response",
                     json={"respondent_id": "USER-0002", "text": "road was closed"})
    assert ok.status_code == 200
    assert ok.json()["state"] == "decided"
    assert "document" in ok.json()

    wrong = client.post("/cases/CASE-0001/response",
                        json={"respondent_id": "USER-0001", "text": "x"})
    assert wrong.status_code == 409

    monkeypatch.setattr(adj, "get_case_row", _async(None))
    missing = client.post("/cases/CASE-9/response", json={"respondent_id": "x", "text": "x"})
    assert missing.status_code == 404
