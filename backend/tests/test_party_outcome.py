"""Party-facing outcome copy (app/orchestrator/party_outcome.py): a pure function, so
every case here is built in memory. Geometry runs along the equator, where one degree of
longitude is a fixed distance, so the route numbers come out exactly as in the prototype."""

import json
from datetime import UTC, datetime, timedelta
from math import pi
from pathlib import Path

import pytest

from app.orchestrator.party_outcome import (
    ICONS,
    OutcomeInput,
    distance_m,
    first_name,
    money,
    party_outcome,
)
from app.schemas import CaseFile, DecisionObject

FIXTURES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"
KM_PER_DEG = 2 * pi * 6371.0088 / 360  # evidence_lookup's earth radius, at the equator
START = datetime(2026, 9, 19, 23, 17, tzinfo=UTC)
END = START + timedelta(minutes=17)


def line(km: float) -> dict:
    return {"type": "LineString", "coordinates": [[0.0, 0.0], [km / KM_PER_DEG, 0.0]]}


def msg(id_: str, role: str, text: str) -> dict:
    return {"id": id_, "sender_role": role, "timestamp": START.isoformat(), "text": text}


def case_file(fixture: str, **overrides) -> CaseFile:
    data = json.loads((FIXTURES / f"{fixture}.json").read_text())
    data.update(trip_started_at=START.isoformat(), trip_completed_at=END.isoformat())
    data.update(overrides)
    return CaseFile.model_validate(data)


def decision(outcome: str, remedy: str = "no_action", amount: float | None = None,
             destination: str | None = None, **escalation) -> DecisionObject:
    return DecisionObject.model_validate({
        "case_id": "CASE-0001", "outcome": outcome,
        "remedy": {"type": remedy, "amount": amount, "destination": destination},
        "reasoning": [], "policy_applied": "POL-02", "confidence": 0.9,
        "escalation": {"bucket": "agent_decidable", "bucket_escalate": False,
                       "confidence_escalate": False, "judge_requested_escalation": False,
                       **escalation},
    })


def outcome(viewer: str, *, state: str = "decided", category: str = "route_deviation",
            complainer_role: str = "rider", cf: CaseFile | None = None,
            dec: DecisionObject | None = None, **kw) -> dict:
    names = {"rider": "Shu Fen Wong", "driver": "Wei Jie Nair"}
    other = "driver" if complainer_role == "rider" else "rider"
    result = party_outcome(OutcomeInput(
        case_id="CASE-0001", state=state, category=category, complainer_role=complainer_role,
        complainer_name=names[complainer_role], complainee_name=names[other], viewer=viewer,
        decision=dec, case_file=cf, **kw,
    ))
    assert all(f["icon"] in ICONS for f in result["facts"])
    for text in [result["head"], result["sub"], *(f["text"] for f in result["facts"])]:
        assert "—" not in text  # no em dashes
        for word in ("complainee", "L2", "escalat", "agent"):
            assert word not in text
    return result


def facts(result: dict) -> list[tuple[str, str]]:
    return [(f["icon"], f["text"]) for f in result["facts"]]


# --- route deviation -------------------------------------------------------------------

def detour_case(**kw) -> CaseFile:
    return case_file(
        "route_deviation", optimal_route_geometry=line(8.327), actual_route_geometry=line(11.048),
        payment={"base_fare": 10.09, "platform_fee": 1.25, "taxes": 0.91, "total_fare": 12.25},
        **kw,
    )


UPHELD_ROUTE = decision("claim_upheld", "partial_refund", 2.48, "original_payment_method")


def test_route_upheld_rider_matches_the_prototype():
    closure = msg("MSG-1", "driver", "There was a road closure, had to go around.")
    cf = detour_case(chat_log=[closure])
    r = outcome("rider", cf=cf, dec=UPHELD_ROUTE)
    assert (r["viewer_side"], r["tone"]) == ("complainer", "good")
    assert r["head"] == "You'll get $2.48 back"
    assert r["sub"] == "Refund approved for the extra distance on your trip."
    assert facts(r) == [
        ("route", "Your trip was 11.0 km. The fastest route was 8.3 km, so you travelled "
                  "2.7 km (33%) further."),
        ("alert", "The driver mentioned a road closure, but no closure was recorded on that "
                  "road at the time."),
    ]
    assert r["rule"] == (
        "When a trip is more than 25% longer than the fastest route and nothing on record "
        "explains it, the fare for the extra distance is refunded in full."
    )
    assert r["money"] == "The $2.48 goes back to your original payment method."
    assert not r["can_refile"] and not r["reviewed_by_person"]


def test_route_upheld_without_a_driver_mention_says_only_what_was_recorded():
    r = outcome("rider", cf=detour_case(chat_log=[]), dec=UPHELD_ROUTE)
    assert ("alert", "No road closure or roadworks were recorded on the route at the time.") \
        in facts(r)


def test_route_upheld_driver_view():
    r = outcome("driver", cf=detour_case(chat_log=[]), dec=UPHELD_ROUTE, has_response=True)
    assert (r["viewer_side"], r["tone"]) == ("complainee", "neutral")
    assert r["head"] == "Shu Fen gets $2.48 back"
    assert r["sub"] == "The refund covers only the extra distance on this trip."
    assert facts(r) == [
        ("route", "The route driven was 2.7 km (33%) longer than the fastest route."),
        ("alert", "No road closure was recorded on that road at the time, so the detour "
                  "couldn't be confirmed."),
        ("scale", "Your reply was argued by an advocate on your side before the decision."),
    ]
    assert r["money"] is None


def test_route_driver_without_a_reply_is_told_it_was_decided_on_the_records():
    r = outcome("driver", cf=detour_case(chat_log=[]), dec=UPHELD_ROUTE)
    assert facts(r)[-1] == ("scale", "You didn't reply, so the case was decided on the trip "
                                     "records.")


def test_route_partial_tier_rule():
    cf = case_file("route_deviation", optimal_route_geometry=line(10.0),
                   actual_route_geometry=line(11.5))
    r = outcome("rider", cf=cf, dec=decision("claim_upheld_partial", "partial_refund", 0.5))
    assert r["head"] == "You'll get $0.50 back"
    assert r["rule"].startswith("When a trip is 10% to 25% longer")
    assert "half the fare" in r["rule"]


def test_route_denied_under_ten_percent_with_roadworks():
    roadworks = {
        "id": "TE-1", "type": "construction", "near_lat": 0.0, "near_lng": 0.01,
        "time_window_start": (START - timedelta(minutes=10)).isoformat(),
        "time_window_end": (END + timedelta(minutes=10)).isoformat(),
    }
    cf = case_file("route_deviation", optimal_route_geometry=line(2.598),
                   actual_route_geometry=line(2.828), traffic_events=[roadworks])
    r = outcome("rider", cf=cf, dec=decision("claim_denied"))
    assert (r["tone"], r["head"]) == ("neutral", "No refund for this trip")
    assert r["sub"] == "The route was within the normal range, and roadworks explain the detour."
    assert facts(r) == [
        ("route", "Your trip was 2.83 km. The fastest route was 2.60 km, so the extra distance "
                  "was 0.23 km (9%)."),
        ("info", "Routes up to 10% longer count as normal variation, so no refund applies."),
        ("alert", "Construction was recorded near the planned route during your trip, which "
                  "explains the detour."),
    ]
    assert r["rule"] == (
        "Detours under 10% longer aren't refunded. A recorded closure or roadworks on the "
        "route also justifies a detour."
    )
    assert r["money"] is None


def test_route_denied_over_threshold_explained_by_a_closure():
    closure = {
        "id": "TE-1", "type": "road_closure", "near_lat": 0.0, "near_lng": 0.01,
        "time_window_start": START.isoformat(), "time_window_end": END.isoformat(),
    }
    r = outcome("driver", cf=detour_case(traffic_events=[closure]), dec=decision("claim_denied"))
    assert r["head"] == "No refund on this trip"
    assert r["sub"] == "A road closure explains the detour."
    assert "justifies a detour, so the extra distance isn't refunded" in r["rule"]


# --- no-show ---------------------------------------------------------------------------

def no_show_case(reached: bool = False, chat: list | None = None) -> CaseFile:
    gap_deg = 0.0 if reached else 1572.3 / 1000 / KM_PER_DEG
    return case_file(
        "no_show_charge", pickup_lat=0.0, pickup_lng=0.0,
        gps_trace=[{"lat": 0.0, "lng": gap_deg, "t": START.isoformat()}],
        chat_log=chat if chat is not None else [msg("MSG-1", "driver", "Waiting outside")],
    )


WAIVER = decision("claim_upheld", "no_show_fee_waiver", 4.5, "original_payment_method")


def test_no_show_waived_rider_matches_the_prototype():
    r = outcome("rider", category="no_show_charge", cf=no_show_case(), dec=WAIVER)
    assert (r["tone"], r["head"]) == ("good", "Your $4.50 no-show fee is waived")
    assert r["sub"] == "The driver never reached your pickup point."
    assert facts(r) == [
        ("pin", "The driver's GPS never came closer than 1.6 km to your pickup point."),
        ("info", "A driver has to arrive within 100 m of the pickup before a no-show fee can "
                 "apply."),
        ("msg", "The driver's message saying they'd arrived doesn't match their GPS."),
    ]
    assert r["rule"] == (
        "A no-show fee only applies if the driver arrived within 100 m of the pickup, waited "
        "the required time, and tried to reach you."
    )
    assert r["money"] == "The $4.50 goes back to your original payment method."


def test_no_show_waived_driver_view():
    r = outcome("driver", category="no_show_charge", cf=no_show_case(chat=[]), dec=WAIVER)
    assert (r["tone"], r["head"]) == ("neutral", "The no-show fee can't be charged")
    assert r["sub"] == "Your GPS shows you hadn't reached the pickup point."
    assert facts(r)[0] == ("pin", "Your closest position was 1.6 km from the pickup point.")
    assert r["money"] is None


def test_driver_filed_no_show_denied_is_a_waiver_for_the_rider():
    cf = no_show_case().model_copy(update={"complainer_role": "driver"})
    driver = outcome("driver", category="no_show_charge", complainer_role="driver", cf=cf,
                     dec=decision("claim_denied"))
    assert driver["viewer_side"] == "complainer"
    assert driver["head"] == "The no-show fee can't be charged"
    rider = outcome("rider", category="no_show_charge", complainer_role="driver", cf=cf,
                    dec=decision("claim_denied"))
    assert (rider["tone"], rider["head"]) == ("good", "Your $4.50 no-show fee is waived")


def test_no_show_fee_stands_when_the_driver_arrived():
    r = outcome("rider", category="no_show_charge", cf=no_show_case(reached=True, chat=[]),
                dec=decision("claim_denied"))
    assert (r["tone"], r["head"]) == ("neutral", "The $4.50 no-show fee stands")
    assert r["sub"] == "The driver reached your pickup point, so the fee applies."
    d = outcome("driver", category="no_show_charge", cf=no_show_case(reached=True, chat=[]),
                dec=decision("claim_denied"))
    assert d["tone"] == "good"


def test_short_distances_are_in_metres():
    assert distance_m(46.2) == "46 m"
    assert distance_m(348.0) == "350 m"
    assert distance_m(1572.3) == "1.6 km"


# --- property damage -------------------------------------------------------------------

def damage_case(photos: bool = True) -> CaseFile:
    photo = {
        "evidence_id": "EV-0035", "r2_object_key": "evidence/x.jpg", "hash": "sha256:a",
        "submitted_at": END.isoformat(),
        "analysis": {"shows_vehicle_interior": True, "mess_type": "mud_dirt", "extent": "large",
                     "description": "Mud on the floor.", "confidence": 0.9, "tier": "moderate"},
    }
    return case_file("property_damage", photos=[photo] if photos else [])


HIGH_VALUE = decision(
    "claim_upheld", "cleaning_repair_fee", 120.0, "driver_payout", bucket="always_escalate",
    bucket_escalate=True,
    reasons=["bucket: high_value_property_damage — Property Damage fee of $120 or more."],
)


def test_damage_escalated_driver_matches_the_prototype():
    r = outcome("driver", state="escalated", category="property_damage",
                complainer_role="driver", cf=damage_case(), dec=HIGH_VALUE, has_response=True)
    assert (r["tone"], r["head"]) == ("warn", "A specialist is checking this one")
    assert r["sub"] == ("Cleaning fees of $120 or more always get a person's review before "
                        "anyone is charged.")
    assert facts(r) == [
        ("camera", "Your photo shows mud and dirt across much of the seat or floor. That's the "
                   "moderate tier: $120."),
        ("msg", "Shu Fen has replied. The specialist will weigh both sides."),
    ]
    assert r["rule"] is None and r["money"] is None


def test_damage_escalated_rider_sees_the_drivers_photo_by_name():
    r = outcome("rider", state="escalated", category="property_damage",
                complainer_role="driver", cf=damage_case(), dec=HIGH_VALUE)
    assert facts(r)[0][1].startswith("Wei Jie's photo shows mud and dirt")


@pytest.mark.parametrize(("flags", "expected"), [
    ({"bucket_escalate": True, "reasons": ["bucket: repeat_filer — 3+ disputes"]},
     "When either side has 3 or more disputes in 30 days"),
    ({"compliance_veto": "amount too high"}, "An automatic check on the decision didn't pass"),
    ({"judge_requested_escalation": True}, "This case needs a closer look"),
    ({"confidence_escalate": True}, "The evidence didn't point clearly one way"),
])
def test_escalation_reason_in_plain_words(flags, expected):
    r = outcome("rider", state="escalated", cf=detour_case(),
                dec=decision("claim_upheld", "partial_refund", 2.48, **flags))
    assert r["sub"].startswith(expected)
    assert r["tone"] == "warn"


def test_damage_upheld_and_denied():
    fee = decision("claim_upheld", "cleaning_repair_fee", 40.0, "driver_payout")
    driver = outcome("driver", category="property_damage", complainer_role="driver",
                     cf=damage_case(), dec=fee)
    assert (driver["tone"], driver["head"]) == ("good", "You'll receive a $40 cleaning fee")
    assert driver["money"] == "The $40 is added to your payout."
    assert "$40 for a spill or crumbs, $120 for mud, dirt or stains, $200 for vomit" \
        in driver["rule"]
    rider = outcome("rider", category="property_damage", complainer_role="driver",
                    cf=damage_case(), dec=decision("claim_denied"))
    assert (rider["tone"], rider["head"]) == ("good", "You won't be charged a cleaning fee")


def test_damage_declined_without_a_photo_can_be_refiled():
    r = outcome("driver", state="declined_insufficient_evidence", category="property_damage",
                complainer_role="driver", filed_at=END + timedelta(days=1),
                trip_completed_at=END)
    assert r["head"] == "We need a photo to continue"
    assert r["sub"] == ("Cleaning fees need at least one photo of the mess. This isn't a "
                        "decision against you.")
    assert facts(r) == [("camera", "No photo was attached to this report, so it couldn't be "
                                   "reviewed.")]
    assert r["can_refile"] and r["tone"] == "neutral"
    other = outcome("rider", state="declined_insufficient_evidence",
                    category="property_damage", complainer_role="driver")
    assert other["head"] == "No action on this report" and not other["can_refile"]


def test_declined_outside_the_window_cannot_be_refiled():
    r = outcome("rider", state="declined_insufficient_evidence", filed_at=END + timedelta(days=45),
                trip_completed_at=END)
    assert r["head"] == "This trip is too old to dispute"
    assert facts(r) == [("clock", "This report was filed 45 days after the trip ended.")]
    assert not r["can_refile"]


def test_judge_declined_for_insufficient_evidence():
    r = outcome("rider", cf=detour_case(), dec=decision("declined_insufficient_evidence"))
    assert r["head"] == "We need more evidence to continue" and r["can_refile"]


# --- safety, in progress, reviewed ------------------------------------------------------

def test_safety_complainer_and_other_party():
    r = outcome("rider", state="safety_bypassed", category="safety_incident")
    assert (r["tone"], r["head"]) == ("bad", "Our safety team has your report")
    assert r["sub"] == "A safety specialist will review what happened and contact you."
    assert ("alert", "If you're in danger right now, call 999.") in facts(r)
    other = outcome("driver", state="safety_bypassed", category="safety_incident")
    assert other["tone"] == "bad"
    assert all("Shu Fen" not in f["text"] for f in other["facts"])


@pytest.mark.parametrize("state", ["opened", "triage", "assembling", "adjudicating"])
def test_in_progress_states_are_neutral(state):
    r = outcome("rider", state=state, category=None if state == "opened" else "route_deviation")
    assert r["tone"] == "neutral" and r["head"] == "We're looking into your report"
    assert outcome("driver", state=state)["head"] == "Shu Fen reported a problem with this trip"


def test_awaiting_response_asks_the_other_side_to_reply():
    me = outcome("driver", state="awaiting_response", cf=detour_case())
    assert me["head"] == "Your reply is needed"
    assert facts(me) == [("info", "Shu Fen reported that the route was longer than it "
                                  "should have been.")]
    assert outcome("rider", state="awaiting_response")["head"] == "Waiting for Wei Jie's reply"


def test_reviewed_by_person_follows_human_ratified():
    dec = UPHELD_ROUTE.model_copy(update={"human_ratified": True, "ratified_by": "L2-03"})
    r = outcome("rider", cf=detour_case(), dec=dec)
    assert r["reviewed_by_person"]
    assert ("user", "A specialist reviewed this case and made the final decision.") in facts(r)


def test_formatting_helpers():
    assert first_name("Shu Fen Wong") == "Shu Fen" and first_name("Cher") == "Cher"
    assert (money(2.48), money(120.0), money(4.5)) == ("$2.48", "$120", "$4.50")
