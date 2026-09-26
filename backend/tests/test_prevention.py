from datetime import UTC, datetime, timedelta

import pytest

from app.rules.prevention import (
    PreventionAction,
    PreventionContext,
    run_prevention_rules,
)
from app.schemas.common import DisputeCategory


def make_ctx(**overrides) -> PreventionContext:
    defaults = dict(
        trip_id="trip-1",
        category=DisputeCategory.ROUTE_DEVIATION,
        claimant_id="user-1",
        trip_exists=True,
        claimant_is_party_to_trip=True,
        has_open_or_decided_case_for_trip=False,
        is_safety=False,
        has_required_evidence=True,
        claimant_dispute_count_30d=0,
        trip_completed_at=datetime.now(UTC) - timedelta(days=1),
        now=datetime.now(UTC),
    )
    defaults.update(overrides)
    return PreventionContext(**defaults)


def test_clean_claim_passes():
    outcome = run_prevention_rules(make_ctx())
    assert outcome.action == PreventionAction.PASS
    assert outcome.velocity_flagged is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"trip_exists": False},
        {"category": None},
        {"claimant_is_party_to_trip": False},
    ],
)
def test_rule2_malformed_request(overrides):
    outcome = run_prevention_rules(make_ctx(**overrides))
    assert outcome.action == PreventionAction.REJECTED_MALFORMED


def test_rule1_duplicate_claim():
    outcome = run_prevention_rules(make_ctx(has_open_or_decided_case_for_trip=True))
    assert outcome.action == PreventionAction.REJECTED_DUPLICATE


def test_rule3_safety_hard_gate_overrides_everything_else():
    outcome = run_prevention_rules(
        make_ctx(is_safety=True, has_open_or_decided_case_for_trip=False)
    )
    assert outcome.action == PreventionAction.SAFETY_BYPASSED


def test_rule6_claim_window_stale():
    outcome = run_prevention_rules(
        make_ctx(trip_completed_at=datetime.now(UTC) - timedelta(days=31))
    )
    assert outcome.action == PreventionAction.DECLINED_STALE


def test_rule6_claim_window_within_bounds():
    outcome = run_prevention_rules(
        make_ctx(trip_completed_at=datetime.now(UTC) - timedelta(days=29))
    )
    assert outcome.action == PreventionAction.PASS


def test_rule4_evidence_gate_fires_for_property_damage_without_evidence():
    outcome = run_prevention_rules(
        make_ctx(category=DisputeCategory.PROPERTY_DAMAGE, has_required_evidence=False)
    )
    assert outcome.action == PreventionAction.DECLINED_INSUFFICIENT_EVIDENCE


def test_rule4_evidence_gate_does_not_fire_for_route_deviation():
    outcome = run_prevention_rules(
        make_ctx(category=DisputeCategory.ROUTE_DEVIATION, has_required_evidence=False)
    )
    assert outcome.action == PreventionAction.PASS


def test_rule5_velocity_flag_is_non_blocking():
    outcome = run_prevention_rules(make_ctx(claimant_dispute_count_30d=3))
    assert outcome.action == PreventionAction.PASS
    assert outcome.velocity_flagged is True


def test_rule5_velocity_flag_below_threshold():
    outcome = run_prevention_rules(make_ctx(claimant_dispute_count_30d=2))
    assert outcome.velocity_flagged is False
