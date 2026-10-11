"""Demo navigation endpoints — DB monkeypatched, no network."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api.demo as demo_api
from app.main import app

USER = "8a1f7f3e-1a2b-4c3d-9e8f-001122334455"


class FakeConn:
    async def close(self):
        pass


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


def trip(case_id=None, days_ago=1):
    return {
        "id": "t1", "case_id": case_id, "case_state": None, "total_fare": 16.85,
        "add_on_fees": '[{"type": "no_show_fee", "amount": 4.5}]',
        "completed_at": datetime.now(UTC) - timedelta(days=days_ago),
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(demo_api, "get_connection", _async(FakeConn()))
    return TestClient(app)


def test_trip_is_claimable_only_without_a_case_and_inside_the_window(client, monkeypatch):
    trips = [trip(), trip(case_id="CASE-0001"), trip(days_ago=45)]
    monkeypatch.setattr(demo_api, "list_user_trips", _async(trips))
    body = client.get(f"/users/{USER}/trips").json()
    assert [t["claimable"] for t in body] == [True, False, False]
    assert body[0]["add_on_fees"] == [{"type": "no_show_fee", "amount": 4.5}]


def test_non_uuid_user_is_404(client):
    assert client.get("/users/not-a-uuid/trips").status_code == 404
    assert client.get("/users/not-a-uuid/cases").status_code == 404


def test_persona_role_is_validated(client, monkeypatch):
    monkeypatch.setattr(demo_api, "list_personas", _async([]))
    assert client.get("/demo/personas?role=rider").status_code == 200
    assert client.get("/demo/personas?role=admin").status_code == 422


def test_scenario_category_is_validated_and_404s_when_none_left(client, monkeypatch):
    monkeypatch.setattr(demo_api, "pick_scenario", _async(None))
    assert client.get("/demo/scenario?category=parking").status_code == 422
    assert client.get("/demo/scenario?category=no_show_charge").status_code == 404


def test_stats_passes_the_db_summary_through(client, monkeypatch):
    monkeypatch.setattr(demo_api, "system_stats", _async({"cases": 3, "awaiting_human": 1}))
    assert client.get("/stats").json() == {"cases": 3, "awaiting_human": 1}


def test_policy_returns_every_clause_of_a_section(client):
    clauses = client.get("/policy/POL-02").json()
    assert clauses and all(c["policy_id"] == "POL-02" for c in clauses)
    assert client.get("/policy/POL-99").status_code == 404
