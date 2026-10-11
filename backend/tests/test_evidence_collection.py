"""Evidence Collection Agent tests. No real DB or object-storage calls here: `db_query`
and `object_exists` are monkeypatched, same spirit as scripting the model itself with
FunctionModel — nothing in this file touches the network (roadmap v3 risk table).
"""

from datetime import UTC, datetime

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import app.agents.evidence_collection.agent as ec
from app.data.db import TripBundle
from app.schemas import CaseRole, DisputeCategory
from app.schemas.triage import TriageResult

GOOD_TAG = {"chunk_id": "POL-02-01", "policy_id": "POL-02", "excerpt": "real excerpt"}
HALLUCINATED_TAG = {"chunk_id": "POL-99-01", "policy_id": "POL-99", "excerpt": "made up"}


def make_bundle() -> TripBundle:
    now = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    return TripBundle(
        trip={
            "id": "TRIP-0001", "pickup_lat": 1.35, "pickup_lng": 103.82,
            "gps_trace": [{"lat": 1.35, "lng": 103.82, "t": now.isoformat()}],
            "optimal_route_geometry": {
                "type": "LineString", "coordinates": [[103.82, 1.35], [103.83, 1.36]]
            },
            "actual_route_geometry": {
                "type": "LineString", "coordinates": [[103.82, 1.35], [103.83, 1.36]]
            },
        },
        payment={
            "base_fare": 10.0, "platform_fee": 1.25, "taxes": 0.5,
            "total_fare": 11.75, "add_on_fees": [],
        },
        chat_messages=[{"id": "MSG-0001", "sender_role": "rider", "timestamp": now, "text": "hi"}],
        traffic_events=[],
        evidence=[{"id": "EV-0001", "object_key": "evidence/CASE-0001/a.jpg", "hash": "sha256:abc",
                   "submitted_at": now}],
        complainer={"id": "USER-0001", "rating_trend": 0.0},
        complainee={"id": "USER-0002", "rating_trend": 0.0},
        complainer_profile={"dispute_count_30d": 0, "upheld_count": 0, "denied_count": 0,
                             "rating_trend": 0.0, "account_age_days": 100},
        complainee_profile=None,
    )


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    async def fake_fetch(*args, **kwargs):
        return make_bundle()

    monkeypatch.setattr(ec, "fetch_trip_bundle", fake_fetch)
    monkeypatch.setattr(ec, "object_exists", lambda key: True)


def scripted(*steps):
    remaining = list(steps)

    def fn(messages, info: AgentInfo) -> ModelResponse:
        assert remaining, "model called more times than scripted"
        return remaining.pop(0)(info)

    return FunctionModel(fn)


def call_tool(name: str, **args):
    return lambda info: ModelResponse(parts=[ToolCallPart(name, args)])


def answer(policy_tags):
    return lambda info: ModelResponse(parts=[
        ToolCallPart(info.output_tools[0].name, {"policy_tags": policy_tags})
    ])


async def run_it(model):
    triage = TriageResult(
        category=DisputeCategory.ROUTE_DEVIATION, tier="moderate", is_safety=False
    )
    with ec.evidence_collection_agent.override(model=model):
        return await ec.run_evidence_collection(
            trip_id="TRIP-0001", case_id="CASE-0001", triage_result=triage,
            complainer_role=CaseRole.RIDER, complainer_id="USER-0001", complainee_id="USER-0002",
        )


async def test_raw_fields_are_reconstructed_from_the_bundle_not_the_model():
    model = scripted(
        call_tool("db_query"),
        call_tool("policy_rag", query="route deviation tolerance"),
        answer([GOOD_TAG]),
    )
    case_file = await run_it(model)
    # None of these came from the model at all — it only ever produces policy_tags.
    assert case_file.case_id == "CASE-0001"
    assert case_file.trip_id == "TRIP-0001"
    assert case_file.category == DisputeCategory.ROUTE_DEVIATION
    assert case_file.complainer_role == CaseRole.RIDER
    assert case_file.complainer_id == "USER-0001"
    assert case_file.complainee_id == "USER-0002"
    assert case_file.pickup_lat == 1.35
    assert len(case_file.chat_log) == 1
    assert case_file.payment.total_fare == 11.75
    assert len(case_file.photos) == 1


async def test_hallucinated_policy_tag_is_stripped():
    model = scripted(
        call_tool("db_query"),
        call_tool("policy_rag", query="route deviation tolerance"),
        answer([GOOD_TAG, HALLUCINATED_TAG]),
    )
    case_file = await run_it(model)
    assert [t.chunk_id for t in case_file.policy_tags] == ["POL-02-01"]


async def test_object_storage_filters_missing_photos(monkeypatch):
    monkeypatch.setattr(ec, "object_exists", lambda key: False)
    model = scripted(call_tool("db_query"), answer([]))
    case_file = await run_it(model)
    assert case_file.photos == []


async def test_db_query_never_called_forces_retry_then_fails():
    model = scripted(answer([]), answer([]), answer([]))
    with pytest.raises(Exception):  # noqa: B017 — UnexpectedModelBehavior after exhausting retries
        await run_it(model)
