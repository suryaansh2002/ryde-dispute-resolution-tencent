"""L2 ratify/override rules — DB monkeypatched at the names l2_review imported."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.orchestrator.l2_review as l2
from app.main import app
from app.schemas import DecisionObject, DecisionOutcome, Remedy
from app.schemas.common import RemedyType

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"
DECISIONS = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "decisions"


class FakeConn:
    async def close(self):
        pass


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


def escalated_case(state="escalated", with_case_file=True):
    return {
        "id": "CASE-0002", "state": state,
        "case_file": (CASE_FILES / "no_show_charge.json").read_text() if with_case_file else None,
    }


def agent_decision() -> DecisionObject:
    return DecisionObject.model_validate_json(
        (DECISIONS / "no_show_charge_escalated.json").read_text()
    )


@pytest.fixture
def stored(monkeypatch):
    saved = {"decisions": [], "states": []}

    async def insert_decision(conn, decision):
        saved["decisions"].append(decision)

    async def update_case(conn, case_id, *, state, **kw):
        saved["states"].append(state)

    monkeypatch.setattr(l2, "get_connection", _async(FakeConn()))
    monkeypatch.setattr(l2, "get_case_row", _async(escalated_case()))
    monkeypatch.setattr(l2, "get_latest_decision", _async(agent_decision()))
    monkeypatch.setattr(l2, "insert_decision", insert_decision)
    monkeypatch.setattr(l2, "update_case", update_case)
    monkeypatch.setattr(l2, "record_trace_event", _async(None))
    monkeypatch.setattr(l2, "trace_emitter", lambda conn: _async(None))
    return saved


def review(**kw):
    return l2.ReviewRequest(**{"reviewer": "L2-reviewer-03", "action": "ratify",
                               "note": "GPS confirms it", **kw})


async def test_ratify_finalizes_the_agent_decision_unchanged(stored):
    decision = await l2.review_case("CASE-0002", review())
    original = agent_decision()
    assert decision.human_ratified and decision.ratified_by == "L2-reviewer-03"
    assert (decision.outcome, decision.remedy) == (original.outcome, original.remedy)
    assert "ratified: GPS confirms it" in decision.reasoning[-1].finding
    assert stored["states"] == ["decided"]


async def test_override_replaces_outcome_and_remedy(stored):
    decision = await l2.review_case("CASE-0002", review(
        action="override", outcome=DecisionOutcome.CLAIM_DENIED,
        remedy=Remedy(type=RemedyType.NO_ACTION), note="the rider was at the wrong pin",
    ))
    assert decision.outcome == "claim_denied"
    assert decision.remedy.type == RemedyType.NO_ACTION
    assert decision.confidence == 1.0 and decision.human_ratified


async def test_override_still_has_to_pass_compliance(stored):
    with pytest.raises(l2.ReviewInvalid, match="exceeds the \\$4.50 fee"):
        await l2.review_case("CASE-0002", review(
            action="override", outcome=DecisionOutcome.CLAIM_UPHELD,
            remedy=Remedy(type=RemedyType.NO_SHOW_FEE_WAIVER, amount=50.0),
        ))
    assert stored["decisions"] == []


async def test_safety_case_can_only_be_overridden(stored, monkeypatch):
    monkeypatch.setattr(l2, "get_case_row", _async(escalated_case("safety_bypassed", False)))
    monkeypatch.setattr(l2, "get_latest_decision", _async(None))
    with pytest.raises(l2.ReviewInvalid, match="nothing to ratify"):
        await l2.review_case("CASE-0002", review())
    decision = await l2.review_case("CASE-0002", review(
        action="override", outcome=DecisionOutcome.CLAIM_UPHELD,
        remedy=Remedy(type=RemedyType.COMPENSATION_CREDIT, amount=10.0),
        note="driver suspended pending investigation",
    ))
    assert decision.human_ratified
    assert decision.escalation.bucket == "always_escalate"


async def test_decided_case_is_not_in_review(stored, monkeypatch):
    monkeypatch.setattr(l2, "get_case_row", _async(escalated_case("decided")))
    with pytest.raises(l2.AdjudicationRejected):
        await l2.review_case("CASE-0002", review())


def test_ratify_endpoint_maps_errors(stored, monkeypatch):
    client = TestClient(app)
    ok = client.post("/l2/cases/CASE-0002/ratify",
                     json={"reviewer": "L2-reviewer-03", "action": "ratify", "note": "ok"})
    assert ok.status_code == 200 and ok.json()["human_ratified"]

    bad = client.post("/l2/cases/CASE-0002/ratify", json={
        "reviewer": "r", "action": "override", "note": "n", "outcome": "claim_upheld",
        "remedy": {"type": "no_show_fee_waiver", "amount": 50},
    })
    assert bad.status_code == 422


@pytest.fixture
def prep(monkeypatch):
    from datetime import UTC, datetime

    from tests.test_evidence_collection import make_bundle

    record = {"saved": [], "traced": [], "states": []}
    case = {"id": "CASE-0009", "state": "safety_bypassed", "category": "safety_incident",
            "trip_id": "TRIP-0001", "complainer_id": "USER-0001",
            "complainee_id": "USER-0002", "case_file": None, "updated_at": None}
    bundle = make_bundle()
    bundle.trip.update(rider_id="USER-0001", driver_id="USER-0002")
    bundle.evidence = []

    async def save(conn, case_id, case_file):
        record["saved"].append(case_file)
        case["case_file"] = case_file.model_dump_json()
        return True

    async def trace(conn, case_id, kind, **kw):
        record["traced"].append((kind, kw))
        return type("Event", (), {"t": datetime(2026, 10, 14, tzinfo=UTC)})()

    async def update_case(*args, **kw):
        record["states"].append(kw)

    monkeypatch.setattr(l2, "get_connection", _async(FakeConn()))
    monkeypatch.setattr(l2, "get_case_row", lambda conn, cid: _async(dict(case))())
    monkeypatch.setattr(l2, "fetch_trip_bundle", _async(bundle))
    monkeypatch.setattr(l2, "save_case_file_if_absent", save)
    monkeypatch.setattr(l2, "record_trace_event", trace)
    monkeypatch.setattr(l2, "update_case", update_case)
    monkeypatch.setattr(l2, "first_trace_time",
                        _async(datetime(2026, 10, 14, tzinfo=UTC)))
    return case, record


def test_prepare_assembles_evidence_once_without_changing_state(prep):
    case, record = prep
    client = TestClient(app)
    first = client.post("/l2/cases/CASE-0009/prepare")
    assert first.status_code == 200
    body = first.json()
    assert body["case_id"] == "CASE-0009" and body["prepared_at"].startswith("2026-10-14")
    assert {"PAYMENT", "GPS-TRACE", "MSG-0001", "PROFILE-COMPLAINER"} <= set(body["evidence"])
    assert record["saved"][0].category == "safety_incident"
    assert record["saved"][0].policy_tags == []
    (kind, kw), = record["traced"]
    assert kind == "tool_call" and kw["detail"].startswith("case file prepared")
    assert kw.get("agent") is None
    assert record["states"] == [] and case["state"] == "safety_bypassed"

    again = client.post("/l2/cases/CASE-0009/prepare")
    assert again.status_code == 200 and again.json()["evidence"] == body["evidence"]
    assert len(record["saved"]) == 1 and len(record["traced"]) == 1


def test_prepare_is_only_for_safety_reports(prep, monkeypatch):
    case, _ = prep
    case["state"] = "escalated"
    assert TestClient(app).post("/l2/cases/CASE-0009/prepare").status_code == 409
    monkeypatch.setattr(l2, "get_case_row", _async(None))
    assert TestClient(app).post("/l2/cases/CASE-0009/prepare").status_code == 404
