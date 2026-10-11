"""Escalation gate and compliance check — both deterministic, no model or DB."""

from pathlib import Path

import pytest

from app.rules.compliance import compliance_check, compliance_violations
from app.rules.escalation import matching_bucket_rules, run_escalation_gate
from app.rules.policy_math import ROUTE_MERIT, route_tier
from app.schemas import CaseFile, DecisionOutcome, EscalationBucket, JudgeVerdict, Remedy
from app.schemas.common import RemedyType
from app.tools.evidence_lookup import evidence_index

UPHELD = DecisionOutcome.CLAIM_UPHELD
FEE = RemedyType.CLEANING_REPAIR_FEE
WAIVE = RemedyType.NO_SHOW_FEE_WAIVER

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


def load_case(name: str) -> CaseFile:
    return CaseFile.model_validate_json((CASE_FILES / f"{name}.json").read_text())


def verdict(outcome=DecisionOutcome.CLAIM_DENIED, remedy_type=RemedyType.NO_ACTION, amount=None,
            confidence=0.85, policy="POL-02"):
    return JudgeVerdict(
        outcome=outcome, remedy=Remedy(type=remedy_type, amount=amount),
        reasoning=[{"finding": "f", "cites": ["PAYMENT"]}], policy_applied=policy,
        confidence=confidence,
    )


# --- escalation gate --------------------------------------------------------------

def test_clean_confident_case_is_agent_decidable():
    esc = run_escalation_gate(load_case("route_deviation"), verdict())
    assert esc.bucket == EscalationBucket.AGENT_DECIDABLE
    assert not esc.routes_to_l2


def test_low_confidence_escalates_independent_of_bucket():
    esc = run_escalation_gate(load_case("route_deviation"), verdict(confidence=0.4))
    assert esc.confidence_escalate and not esc.bucket_escalate
    assert esc.routes_to_l2


def test_repeat_filer_escalates_even_at_high_confidence():
    case = load_case("no_show_charge")  # complainer has 3 disputes in 30 days
    esc = run_escalation_gate(case, verdict(confidence=0.95, policy="POL-03"))
    assert esc.bucket == EscalationBucket.ALWAYS_ESCALATE
    assert esc.bucket_escalate and not esc.confidence_escalate
    assert any("repeat_filer" in r for r in esc.reasons)


def test_high_value_property_damage_escalates():
    case = load_case("property_damage")
    high = verdict(UPHELD, FEE, 200, policy="POL-04")
    low = verdict(UPHELD, FEE, 40, policy="POL-04")
    assert run_escalation_gate(case, high).bucket_escalate
    assert not run_escalation_gate(case, low).bucket_escalate


def test_judge_lookup_mid_run_skips_verdict_dependent_rules():
    # Before the Judge has a verdict, only case-level rules can match.
    assert matching_bucket_rules(load_case("property_damage")) == []


def test_judge_request_routes_to_l2_but_doesnt_change_bucket():
    esc = run_escalation_gate(
        load_case("route_deviation"), verdict(), judge_requested=True,
        judge_request_reason="conflicting evidence",
    )
    assert esc.routes_to_l2 and esc.bucket == EscalationBucket.AGENT_DECIDABLE
    assert any("conflicting evidence" in r for r in esc.reasons)


# --- compliance check -------------------------------------------------------------

def detoured_case() -> CaseFile:
    """The route_deviation fixture with a real detour (~20% extra distance)."""
    case = load_case("route_deviation")
    detour = {"type": "LineString",
              "coordinates": [[103.8198, 1.3521], [103.8420, 1.3500], [103.8468, 1.3721]]}
    return case.model_copy(update={"actual_route_geometry": detour})


def test_route_tier_and_refund_are_computed_in_code():
    comparison = evidence_index(detoured_case())["ROUTE-COMPARISON"].data
    assert comparison["policy_tier"] == route_tier(comparison["extra_pct"]) != "under_10_pct"
    merit = ROUTE_MERIT[comparison["policy_tier"]]
    # base_fare × extra_km / actual_km × merit
    expected = round(14.50 * comparison["extra_km"] / comparison["actual_km"] * merit, 2)
    assert comparison["refund_if_unjustified"] == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize(("pct", "tier"), [
    (9.99, "under_10_pct"), (10.0, "10_to_25_pct"), (25.0, "10_to_25_pct"), (25.01, "over_25_pct"),
])
def test_route_tier_boundaries(pct, tier):
    assert route_tier(pct) == tier


def test_compliant_partial_refund_passes():
    case = detoured_case()
    refund = evidence_index(case)["ROUTE-COMPARISON"].data["refund_if_unjustified"]
    v = verdict(DecisionOutcome.CLAIM_UPHELD_PARTIAL, RemedyType.PARTIAL_REFUND, refund)
    assert compliance_check(case, v) is None


def test_route_refund_must_match_the_policy_formula():
    v = verdict(DecisionOutcome.CLAIM_UPHELD_PARTIAL, RemedyType.PARTIAL_REFUND, 3.72)
    assert "doesn't match the policy formula" in compliance_check(detoured_case(), v)


def test_cleaning_fee_must_be_a_scheduled_tier_amount():
    v = verdict(UPHELD, FEE, 25, policy="POL-04")
    assert "isn't a scheduled tier amount" in compliance_check(load_case("property_damage"), v)


def test_denied_claim_cannot_carry_a_remedy():
    v = verdict(DecisionOutcome.CLAIM_DENIED, RemedyType.PARTIAL_REFUND, 3.20)
    assert "cannot carry" in compliance_check(load_case("route_deviation"), v)


def test_upheld_claim_needs_a_remedy_and_a_policy():
    v = verdict(DecisionOutcome.CLAIM_UPHELD, RemedyType.NO_ACTION, policy=None)
    violations = compliance_violations(load_case("route_deviation"), v)
    assert any("needs a remedy" in x for x in violations)
    assert any("name the policy" in x for x in violations)


def test_refund_cannot_exceed_trip_fare():
    case = load_case("route_deviation")  # total fare 16.85
    v = verdict(DecisionOutcome.CLAIM_UPHELD, RemedyType.FULL_REFUND, 50.0)
    assert "exceeds the trip fare" in compliance_check(case, v)


def test_cleaning_fee_capped_and_needs_photo():
    case = load_case("property_damage")
    over = verdict(UPHELD, FEE, 250, policy="POL-04")
    assert "exceeds the $200 cap" in compliance_check(case, over)
    no_photo = case.model_copy(update={"photos": []})
    ok_amount = verdict(UPHELD, FEE, 40, policy="POL-04")
    assert "verified photo" in compliance_check(no_photo, ok_amount)


def test_no_show_waiver_bounded_by_fee_charged():
    case = load_case("no_show_charge")  # 4.50 no-show fee
    ok = verdict(UPHELD, WAIVE, 4.50, policy="POL-03")
    too_much = verdict(UPHELD, WAIVE, 9.0, policy="POL-03")
    assert compliance_check(case, ok) is None
    assert "exceeds the $4.50 fee" in compliance_check(case, too_much)


def test_remedy_must_fit_category():
    v = verdict(UPHELD, FEE, 40)
    assert "not a valid remedy for route_deviation" in compliance_check(
        load_case("route_deviation"), v
    )


# --- derived evidence -------------------------------------------------------------

def test_pickup_proximity_is_computed_from_the_trace():
    prox = evidence_index(load_case("no_show_charge"))["PICKUP-PROXIMITY"].data
    assert prox["reached_pickup"] is False
    assert 600 < prox["closest_approach_m"] < 700


def test_waiver_cannot_be_the_remedy_for_a_drivers_upheld_claim():
    from app.schemas import CaseRole

    case = load_case("no_show_charge").model_copy(update={"complainer_role": CaseRole.DRIVER})
    v = verdict(UPHELD, WAIVE, 4.5, policy="POL-03")
    assert "favours the rider" in compliance_check(case, v)
    rider_case = case.model_copy(update={"complainer_role": CaseRole.RIDER})
    assert "favours the rider" not in (compliance_check(rider_case, v) or "")
