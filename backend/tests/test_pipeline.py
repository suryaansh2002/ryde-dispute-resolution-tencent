"""Orchestrator pipeline tests. DB and agent calls are monkeypatched at the names
`app.orchestrator.pipeline` imported into its own namespace — same approach as
test_evidence_collection.py — so these verify sequencing/branching logic without any
real Postgres or Groq call.
"""

from datetime import UTC, datetime, timedelta

import pytest

import app.orchestrator.pipeline as pipeline
from app.schemas import CaseRole, CaseState, DisputeCategory
from app.schemas.triage import TriageResult


class FakeConn:
    async def close(self):
        pass


def make_trip(completed_at=None):
    return {
        "id": "TRIP-0001", "rider_id": "USER-RIDER", "driver_id": "USER-DRIVER",
        "completed_at": completed_at or (datetime.now(UTC) - timedelta(hours=1)),
    }


def minimal_case_file(category=DisputeCategory.ROUTE_DEVIATION, photos=None):
    from app.schemas import BehaviorProfile, CaseFile, PaymentBreakdown

    profile = BehaviorProfile(
        user_id="x", role=CaseRole.RIDER, dispute_count_30d=0,
        upheld_denied_ratio=None, rating_trend=None, account_age_days=0,
    )
    return CaseFile(
        case_id="CASE-0001", trip_id="TRIP-0001", category=category,
        complainer_role=CaseRole.RIDER, complainer_id="USER-RIDER",
        complainee_id="USER-DRIVER", chat_log=[], pickup_lat=1.0, pickup_lng=1.0,
        gps_trace=[], payment=PaymentBreakdown(base_fare=0, platform_fee=0, taxes=0, total_fare=0),
        photos=photos or [],
        complainer_profile=profile, complainee_profile=profile,
    )


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    monkeypatch.setattr(pipeline, "get_connection", _async(FakeConn()))
    monkeypatch.setattr(pipeline, "has_open_or_decided_case", _async(False))
    monkeypatch.setattr(pipeline, "create_case", _async("CASE-0001"))
    monkeypatch.setattr(pipeline, "insert_evidence", _async(None))
    monkeypatch.setattr(pipeline, "update_case", _async(None))
    monkeypatch.setattr(pipeline, "record_trace_event", _async(None))
    monkeypatch.setattr(pipeline, "has_evidence", _async(False))
    monkeypatch.setattr(pipeline, "dispute_count_30d", _async(0))
    monkeypatch.setattr(pipeline, "get_trip", _async(make_trip()))
    monkeypatch.setattr(pipeline, "save_case_file", _async(None))
    monkeypatch.setattr(pipeline, "trace_emitter", lambda conn: _async(None))


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


def _set_triage(monkeypatch, category, is_safety=False, tier="moderate"):
    async def fake_run_triage(claim_text, trip_id):
        return TriageResult(category=category, tier=tier, is_safety=is_safety)
    monkeypatch.setattr(pipeline, "run_triage", fake_run_triage)


async def test_rejects_when_trip_does_not_exist(monkeypatch):
    monkeypatch.setattr(pipeline, "get_trip", _async(None))
    with pytest.raises(pipeline.ClaimRejected):
        await pipeline.file_claim("TRIP-X", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "text")


async def test_rejects_when_claimant_not_a_party(monkeypatch):
    with pytest.raises(pipeline.ClaimRejected):
        await pipeline.file_claim("TRIP-0001", "SOMEONE-ELSE", DisputeCategory.ROUTE_DEVIATION, "t")


async def test_rejects_duplicate_case(monkeypatch):
    monkeypatch.setattr(pipeline, "has_open_or_decided_case", _async(True))
    with pytest.raises(pipeline.ClaimRejected):
        await pipeline.file_claim("TRIP-0001", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "t")


async def test_safety_language_routes_to_safety_bypassed(monkeypatch):
    _set_triage(monkeypatch, DisputeCategory.SAFETY_INCIDENT, is_safety=True)
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "help"
    )
    assert result.state == CaseState.SAFETY_BYPASSED


async def test_stale_claim_declines(monkeypatch):
    _set_triage(monkeypatch, DisputeCategory.ROUTE_DEVIATION)
    monkeypatch.setattr(pipeline, "get_trip", _async(
        make_trip(completed_at=datetime.now(UTC) - timedelta(days=45))
    ))
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "t"
    )
    assert result.state == CaseState.DECLINED_INSUFFICIENT_EVIDENCE


async def test_property_damage_with_no_photos_after_assembly_declines(monkeypatch):
    # has_evidence=True so Prevention Rule 4 passes — this test is specifically for the
    # post-assembly check: a DB evidence row existed, but Evidence Collection's own
    # Object Storage check found the actual object missing, so the CaseFile ends up with
    # zero real photos despite the DB row. Defense in depth beyond trusting a row exists.
    _set_triage(monkeypatch, DisputeCategory.PROPERTY_DAMAGE)
    monkeypatch.setattr(pipeline, "has_evidence", _async(True))
    monkeypatch.setattr(
        pipeline, "run_evidence_collection",
        _async(minimal_case_file(category=DisputeCategory.PROPERTY_DAMAGE, photos=[])),
    )
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.PROPERTY_DAMAGE, "there's a mess"
    )
    assert result.state == CaseState.DECLINED_INSUFFICIENT_EVIDENCE
    assert result.case_file is not None


async def test_clean_claim_reaches_awaiting_response(monkeypatch):
    _set_triage(monkeypatch, DisputeCategory.ROUTE_DEVIATION)
    case_file = minimal_case_file()
    monkeypatch.setattr(pipeline, "run_evidence_collection", _async(case_file))
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "deviation complaint"
    )
    assert result.state == CaseState.AWAITING_RESPONSE
    assert result.case_file is case_file


async def test_velocity_flag_is_non_blocking(monkeypatch):
    _set_triage(monkeypatch, DisputeCategory.ROUTE_DEVIATION)
    monkeypatch.setattr(pipeline, "dispute_count_30d", _async(5))
    monkeypatch.setattr(pipeline, "run_evidence_collection", _async(minimal_case_file()))
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.ROUTE_DEVIATION, "deviation complaint"
    )
    assert result.state == CaseState.AWAITING_RESPONSE
    assert result.velocity_flagged is True


async def test_photos_are_analysed_after_assembly(monkeypatch):
    from app.schemas import DamageFinding, EvidencePhoto

    photo = EvidencePhoto(
        evidence_id="EV-0001", r2_object_key="k", hash="sha256:x", submitted_at=datetime.now(UTC)
    )
    _set_triage(monkeypatch, DisputeCategory.PROPERTY_DAMAGE)
    monkeypatch.setattr(pipeline, "has_evidence", _async(True))
    monkeypatch.setattr(
        pipeline, "run_evidence_collection",
        _async(minimal_case_file(category=DisputeCategory.PROPERTY_DAMAGE, photos=[photo])),
    )
    analysed_photo = photo.model_copy(update={"analysis": DamageFinding(
        shows_vehicle_interior=True, mess_type="vomit", extent="large", description="d",
        confidence=0.9, tier="severe",
    )})

    async def fake_analyze(case_file):
        return case_file.model_copy(update={"photos": [analysed_photo]}), []

    monkeypatch.setattr(pipeline, "analyze_case_photos", fake_analyze)
    result = await pipeline.file_claim(
        "TRIP-0001", "USER-RIDER", DisputeCategory.PROPERTY_DAMAGE, "vomit on the seat"
    )
    assert result.state == CaseState.AWAITING_RESPONSE
    assert result.case_file.photos[0].analysis.tier == "severe"
