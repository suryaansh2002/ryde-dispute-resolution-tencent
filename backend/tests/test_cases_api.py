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


def test_background_task_failure_doesnt_crash_the_request(ran, monkeypatch):
    async def boom(opened):
        raise RuntimeError("groq down")

    monkeypatch.setattr(cases_api.pipeline, "process_claim", boom)
    resp = TestClient(app).post("/cases?background=true", json=CLAIM)
    assert resp.status_code == 202
