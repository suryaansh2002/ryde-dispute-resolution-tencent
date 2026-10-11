from pathlib import Path

import pytest

from app.schemas import CaseFile
from app.tools.evidence_lookup import ROUTE_COMPARISON, evidence_index
from app.tools.policy_rag import search_policy

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


def load_case(name: str) -> CaseFile:
    return CaseFile.model_validate_json((CASE_FILES / f"{name}.json").read_text())


def test_route_comparison_is_computed_from_geometry():
    comparison = evidence_index(load_case("route_deviation"))[ROUTE_COMPARISON].data
    assert comparison["optimal_km"] == pytest.approx(3.736, abs=0.001)
    assert comparison["extra_pct"] == pytest.approx(0.09, abs=0.01)


def test_index_covers_every_citable_item_and_skips_missing_routes():
    index = evidence_index(load_case("no_show_charge"))
    assert {"MSG-0003", "MSG-0004", "PAYMENT", "GPS-TRACE",
            "PROFILE-COMPLAINER", "PROFILE-COMPLAINEE"} <= index.keys()
    assert not any(ref.startswith("ROUTE-") for ref in index)
    assert "EV-0001" in evidence_index(load_case("property_damage"))


@pytest.mark.parametrize(
    ("query", "policy_id"),
    [
        ("driver did not come within 100 meters of the pickup GPS coordinates", "POL-03"),
        ("vomit in the vehicle cleaning fee", "POL-04"),
        ("extra distance versus the optimal route refund", "POL-02"),
    ],
)
def test_policy_search_ranks_the_governing_section_first(query, policy_id):
    assert search_policy(query)[0].policy_id == policy_id


def test_policy_search_returns_nothing_for_an_empty_query():
    assert search_policy("") == []


def test_traffic_event_matches_only_near_the_planned_route_during_the_trip():
    from datetime import UTC, datetime, timedelta

    start = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    end = start + timedelta(minutes=25)
    case = load_case("route_deviation").model_copy(
        update={"trip_started_at": start, "trip_completed_at": end}
    )
    lng, lat = case.optimal_route_geometry["coordinates"][1][:2]
    near = {"near_lat": lat + 0.001, "near_lng": lng, "type": "accident",
            "time_window_start": start.isoformat(), "time_window_end": end.isoformat()}
    far = {**near, "near_lat": lat + 0.05}
    earlier = {**near, "time_window_start": "2020-01-01T00:00:00+00:00",
               "time_window_end": "2020-01-01T01:00:00+00:00"}
    index = evidence_index(case.model_copy(update={"traffic_events": [near, far, earlier]}))
    assert index["TRAFFIC-01"].data["distance_to_planned_route_m"] < 150
    assert index["TRAFFIC-01"].data["matches_route"] is True
    assert index["TRAFFIC-02"].data["matches_route"] is False
    assert index["TRAFFIC-03"].data["during_trip"] is False
    assert index[ROUTE_COMPARISON].data["matching_traffic_events"] == ["TRAFFIC-01"]
