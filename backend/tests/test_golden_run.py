"""Golden-run scoring: pure function, no DB or model."""

import pytest

from app.orchestrator.golden_run import score

UPHELD_ROUTE = {
    "outcome": "claim_upheld", "remedy": {"type": "partial_refund", "merit_fraction": 1.0}
}
DENIED = {"outcome": "claim_denied", "remedy": {"type": "no_action"}}
FEE_120 = {"outcome": "claim_upheld", "remedy": {"type": "cleaning_repair_fee", "amount": 120.0}}
SAFETY = {"outcome": "escalated_to_l2", "remedy": {"type": "no_action"}}
DECLINED = {"outcome": "declined_insufficient_evidence", "remedy": {"type": "no_action"}}


def verdict(outcome, rtype, amount=None, state="decided", **extra):
    remedy = {"type": rtype, "amount": amount}
    return {"state": state, "outcome": outcome, "remedy": remedy, **extra}


@pytest.mark.parametrize(
    ("expected", "actual", "passed"),
    [
        # route: amount must be the policy formula's refund for this trip
        (UPHELD_ROUTE, verdict("claim_upheld", "partial_refund", 2.5, route_refund=2.5), True),
        (UPHELD_ROUTE, verdict("claim_upheld_partial", "full_refund", 2.5, route_refund=2.5), True),
        (UPHELD_ROUTE, verdict("claim_upheld", "partial_refund", 3.0, route_refund=2.5), False),
        (UPHELD_ROUTE, verdict("claim_denied", "no_action"), False),
        (DENIED, verdict("claim_denied", "no_action"), True),
        (DENIED, verdict("claim_upheld", "no_show_fee_waiver", 4.5), False),
        # damage: exact tier amount
        (FEE_120, verdict("claim_upheld", "cleaning_repair_fee", 120.0), True),
        (FEE_120, verdict("claim_upheld", "cleaning_repair_fee", 40.0), False),
        # the verdict is scored, not the routing: an escalated case with the right verdict passes
        (FEE_120, verdict("claim_upheld", "cleaning_repair_fee", 120.0, state="escalated"), True),
        # safety must never reach a verdict
        (SAFETY, {"state": "safety_bypassed"}, True),
        (SAFETY, verdict("claim_denied", "no_action"), False),
        (DECLINED, {"state": "declined_insufficient_evidence"}, True),
        (DECLINED, verdict("claim_upheld", "cleaning_repair_fee", 40.0), False),
        (DENIED, {"state": None, "error": "boom"}, False),
    ],
)
def test_score(expected, actual, passed):
    assert score(expected, actual)[0] is passed
