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
