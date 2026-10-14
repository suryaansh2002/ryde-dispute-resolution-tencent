"""POST /cases and /response in background mode: 202 with the case id right away,
the slow part scheduled. Pipeline/adjudication calls are monkeypatched."""

import pytest
from fastapi.testclient import TestClient

import app.api.cases as cases_api
from app.main import app
from app.orchestrator.pipeline import OpenedClaim
from app.schemas import CaseRole


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


@pytest.fixture
def ran(monkeypatch):
    calls = []

    async def process_claim(opened):
        calls.append(("process_claim", opened.case_id))

    async def adjudicate(case_id):
        calls.append(("adjudicate", case_id))

    opened = OpenedClaim("CASE-0042", {}, "trip", "rider", CaseRole.RIDER, "driver", "text")
    monkeypatch.setattr(cases_api.pipeline, "open_claim", _async(opened))
    monkeypatch.setattr(cases_api.pipeline, "process_claim", process_claim)
    monkeypatch.setattr(cases_api.adjudication, "store_response", _async(None))
    monkeypatch.setattr(cases_api.adjudication, "adjudicate", adjudicate)
    return calls


CLAIM = {"trip_id": "t", "complainer_id": "u", "category": "route_deviation",
         "claim_text": "long detour"}


def test_background_filing_returns_202_then_runs_intake(ran):
    resp = TestClient(app).post("/cases?background=true", json=CLAIM)
    assert resp.status_code == 202
    assert resp.json() == {"case_id": "CASE-0042", "state": "opened",
                           "events": "/events/cases/CASE-0042"}
    # TestClient runs background tasks before returning.
    assert ran == [("process_claim", "CASE-0042")]


def test_background_response_returns_202_then_adjudicates(ran):
    resp = TestClient(app).post("/cases/CASE-0042/response?background=true",
                                json={"respondent_id": "driver", "text": "road closed"})
    assert resp.status_code == 202
    assert resp.json()["events"] == "/events/cases/CASE-0042"
    assert ran == [("adjudicate", "CASE-0042")]


def test_background_adjudicate_checks_first_then_runs(ran, monkeypatch):
    monkeypatch.setattr(cases_api.adjudication, "check_adjudicable", _async(None))
    resp = TestClient(app).post("/cases/CASE-0042/adjudicate?background=true")
    assert resp.status_code == 202
    assert resp.json()["state"] == "adjudicating"
    assert ran == [("adjudicate", "CASE-0042")]


def test_background_adjudicate_refuses_up_front(ran, monkeypatch):
    async def refuse(case_id):
        raise cases_api.adjudication.AdjudicationRejected("case is decided")

    monkeypatch.setattr(cases_api.adjudication, "check_adjudicable", refuse)
    resp = TestClient(app).post("/cases/CASE-0042/adjudicate?background=true")
    assert resp.status_code == 409
    assert ran == []


def test_background_task_failure_doesnt_crash_the_request(ran, monkeypatch):
    async def boom(opened):
        raise RuntimeError("groq down")

    monkeypatch.setattr(cases_api.pipeline, "process_claim", boom)
    resp = TestClient(app).post("/cases?background=true", json=CLAIM)
    assert resp.status_code == 202


def test_party_evidence_view_hides_behaviour_profiles(monkeypatch):
    from pathlib import Path

    raw = (
        Path(__file__).resolve().parents[1]
        / "data_generation" / "fixtures" / "case_files" / "no_show_charge.json"
    ).read_text()

    class Conn:
        async def close(self):
            pass

    monkeypatch.setattr(cases_api, "get_connection", _async(Conn()))
    monkeypatch.setattr(cases_api, "get_case_row", _async({"case_file": raw}))
    client = TestClient(app)
    operator = client.get("/cases/CASE-0001/evidence?view=operator").json()
    party = client.get("/cases/CASE-0001/evidence?view=party").json()
    assert "PROFILE-COMPLAINER" in operator and "GPS-TRACE" in operator
    assert not any(item["kind"] == "behavior_profile" for item in party.values())
    assert party.keys() == operator.keys() - {"PROFILE-COMPLAINER", "PROFILE-COMPLAINEE"}
    assert client.get("/cases/CASE-0001/evidence?view=admin").status_code == 422


@pytest.fixture
def fake_db(monkeypatch):
    class Conn:
        async def close(self):
            pass

    monkeypatch.setattr(cases_api, "get_connection", _async(Conn()))
    return monkeypatch


def test_trace_returns_the_stream_shape_and_404s_for_unknown_cases(fake_db):
    event = {"id": 7, "case_id": "CASE-0001", "t": "2026-10-11T05:42:18+00:00",
             "kind": "state_transition", "agent": None, "detail": "opened -> triage",
             "latency_ms": None, "output": None}
    fake_db.setattr(cases_api, "fetch_case_events", _async([event]))
    fake_db.setattr(cases_api, "get_case_row", _async({"id": "CASE-0001"}))
    client = TestClient(app)
    assert client.get("/cases/CASE-0001/trace").json() == [event]
    fake_db.setattr(cases_api, "get_case_row", _async(None))
    assert client.get("/cases/CASE-9999/trace").status_code == 404


def test_usage_lists_rows_or_nothing(fake_db):
    row = {"agent": "judge", "model": "m", "input_tokens": 10, "output_tokens": 2,
           "requests": 1, "tool_calls": 0, "latency_ms": 300,
           "created_at": "2026-10-11T05:42:19Z"}
    fake_db.setattr(cases_api, "list_case_usage", _async([row]))
    assert TestClient(app).get("/cases/CASE-0001/usage").json() == [row]
    fake_db.setattr(cases_api, "list_case_usage", _async([]))
    assert TestClient(app).get("/cases/CASE-0001/usage").json() == []


def _view(state="safety_bypassed"):
    return {
        "id": "CASE-0001", "state": state, "category": "safety_incident",
        "complainer_role": "rider", "complainer_name": "Shu Fen Wong",
        "complainee_name": "Wei Jie Nair", "created_at": None, "response": None,
        "trip": {"scheduled_at": None, "completed_at": None, "total_fare": 12.25},
        "has_case_file": False,
    }


def test_outcome_needs_a_viewer_and_a_real_case(fake_db):
    fake_db.setattr(cases_api, "get_case_view", _async(_view()))
    fake_db.setattr(cases_api, "get_case_row", _async({"case_file": None}))
    fake_db.setattr(cases_api, "get_latest_decision", _async(None))
    client = TestClient(app)
    body = client.get("/cases/CASE-0001/outcome?for=rider").json()
    assert set(body) == {"case_id", "state", "viewer", "viewer_side", "tone", "head", "sub",
                         "facts", "rule", "money", "can_refile", "reviewed_by_person"}
    assert (body["viewer_side"], body["tone"]) == ("complainer", "bad")
    assert client.get("/cases/CASE-0001/outcome?for=admin").status_code == 422
    assert client.get("/cases/CASE-0001/outcome").status_code == 422
    fake_db.setattr(cases_api, "get_case_view", _async(None))
    assert client.get("/cases/CASE-0001/outcome?for=rider").status_code == 404


async def test_case_view_adds_the_trip_and_whether_evidence_exists():
    from datetime import UTC, datetime
    from decimal import Decimal

    from app.data.cases import get_case_view

    when = datetime(2026, 9, 19, 23, 17, tzinfo=UTC)

    class Conn:
        async def fetchrow(self, query, *args):
            if "has_case_file" in query:
                return {"scheduled_at": when, "completed_at": when,
                        "total_fare": Decimal("12.25"), "has_case_file": True}
            if "FROM responses" in query:
                return None
            return {"id": "CASE-0001", "state": "decided"}

    view = await get_case_view(Conn(), "CASE-0001")
    assert view["trip"] == {"scheduled_at": when, "completed_at": when, "total_fare": 12.25}
    assert isinstance(view["trip"]["total_fare"], float)
    assert view["has_case_file"] is True and view["response"] is None


def test_intake_triage_returns_the_agents_reading(monkeypatch):
    from app.schemas.triage import TriageResult

    seen = []

    async def triage(text, trip_id):
        seen.append((text, trip_id))
        return TriageResult(category="safety_incident", tier="severe", is_safety=True)

    monkeypatch.setattr(cases_api, "run_triage", triage)
    body = {"trip_id": "t", "claim_text": "ran red lights"}
    resp = TestClient(app).post("/intake/triage", json=body)
    assert resp.status_code == 200
    assert resp.json()["is_safety"] is True
    assert seen == [("ran red lights", "t")]


def test_intake_triage_failure_is_a_503_not_a_crash(monkeypatch):
    async def down(text, trip_id):
        raise RuntimeError("quota")

    monkeypatch.setattr(cases_api, "run_triage", down)
    resp = TestClient(app).post("/intake/triage", json={"trip_id": "t", "claim_text": "detour"})
    assert resp.status_code == 503
