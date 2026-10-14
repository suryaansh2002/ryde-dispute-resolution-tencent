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


TRIP = "b6ab642c-f0b5-438f-9e97-9d84b7a1c9ae"


def test_trip_detail_and_its_404s(client, monkeypatch):
    detail = {"id": TRIP, "payment": None, "case_id": None}
    monkeypatch.setattr(demo_api, "get_trip_detail", _async(detail))
    assert client.get(f"/trips/{TRIP}").json() == detail
    assert client.get("/trips/not-a-uuid").status_code == 404
    monkeypatch.setattr(demo_api, "get_trip_detail", _async(None))
    assert client.get(f"/trips/{TRIP}").status_code == 404


async def test_trip_detail_shape_hides_generation_labels_and_raw_gps():
    from decimal import Decimal

    from app.data.demo import get_trip_detail

    line = {"type": "LineString", "coordinates": [[103.8, 1.3], [103.9, 1.4]]}
    row = {
        "id": TRIP, "scheduled_at": None, "completed_at": None, "pickup_lat": 1.3,
        "pickup_lng": 103.8, "dropoff_lat": 1.4, "dropoff_lng": 103.9,
        "optimal_route_geometry": '{"type": "LineString", "coordinates": [[103.8, 1.3], '
                                  '[103.9, 1.4]]}',
        "actual_route_geometry": None, "rider_id": USER, "rider_name": "Shu Fen Wong",
        "driver_id": USER, "driver_name": "Wei Jie Nair", "case_id": None, "case_state": None,
    }
    payment = {"base_fare": Decimal("10.09"), "platform_fee": Decimal("1.25"),
               "taxes": Decimal("0.91"), "total_fare": Decimal("16.75"),
               "add_on_fees": '[{"type": "no_show_fee", "amount": 4.5}]'}

    class Conn:
        async def fetchrow(self, query, *args):
            return payment if "FROM payments" in query else row

    trip = await get_trip_detail(Conn(), TRIP)
    assert set(trip) == {"id", "scheduled_at", "completed_at", "pickup", "dropoff", "rider",
                         "driver", "payment", "optimal_route", "actual_route", "case_id",
                         "case_state"}
    assert trip["pickup"] == {"lat": 1.3, "lng": 103.8}
    assert trip["rider"] == {"id": USER, "name": "Shu Fen Wong"}
    assert trip["payment"] == {"base_fare": 10.09, "platform_fee": 1.25, "taxes": 0.91,
                               "total_fare": 16.75,
                               "add_on_fees": [{"type": "no_show_fee", "amount": 4.5}]}
    assert trip["optimal_route"] == line and trip["actual_route"] is None


def test_featured_case_or_null(client, monkeypatch):
    monkeypatch.setattr(demo_api, "featured_case_id", _async("CASE-0153"))
    assert client.get("/demo/featured").json() == {"case_id": "CASE-0153"}
    monkeypatch.setattr(demo_api, "featured_case_id", _async(None))
    assert client.get("/demo/featured").json() == {"case_id": None}


def test_scenario_role_overrides_the_usual_filer(client, monkeypatch):
    seen = []

    async def pick(conn, category, role=None):
        seen.append(role)
        return {"trip_id": "t", "role": role or "rider", "category": category}

    monkeypatch.setattr(demo_api, "pick_scenario", pick)
    assert client.get("/demo/scenario?category=no_show_charge&role=driver").json()["role"] \
        == "driver"
    assert client.get("/demo/scenario?category=no_show_charge").json()["role"] == "rider"
    assert client.get("/demo/scenario?category=no_show_charge&role=admin").status_code == 422
    assert seen == ["driver", None]


async def test_pick_scenario_uses_the_role_and_sends_a_float_fare():
    from decimal import Decimal

    from app.data.demo import pick_scenario

    queries = []

    class Conn:
        async def fetchrow(self, query, *args):
            queries.append(query)
            return {"trip_id": "t", "user_id": USER, "completed_at": None,
                    "total_fare": Decimal("33.50")}

    scenario = await pick_scenario(Conn(), "no_show_charge", "driver")
    assert scenario["role"] == "driver" and scenario["total_fare"] == 33.5
    assert "t.driver_id AS user_id" in queries[0]
    default = await pick_scenario(Conn(), "no_show_charge")
    assert default["role"] == "rider"
