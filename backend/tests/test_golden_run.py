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


async def test_one_case_failing_doesnt_abort_the_run(monkeypatch):
    import app.orchestrator.golden_run as gr

    goldens = [
        {"id": f"G{i}", "case_id": None, "trip_id": f"T{i}", "category_hint": "route_deviation",
         "expected_outcome": DENIED}
        for i in range(3)
    ]

    class Conn:
        async def execute(self, *args):
            pass

        async def fetch(self, *args):
            return []

        async def close(self):
            pass

    async def connect():
        return Conn()

    async def load(conn):
        return goldens

    async def delete(conn, ids):
        pass

    async def run_one(golden):
        if golden["id"] == "G1":
            raise OSError("nodename nor servname provided")
        return {"case_id": "CASE-1", "passed": True, "actual": {}}

    monkeypatch.setattr(gr, "get_connection", connect)
    monkeypatch.setattr(gr, "_load_golden", load)
    monkeypatch.setattr(gr, "_delete_cases", delete)
    monkeypatch.setattr(gr, "_run_one", run_one)
    results = await gr.run_golden()
    assert [r["passed"] for r in results] == [True, False, True]
    assert "nodename" in results[1]["actual"]["error"]
    assert gr.state.done == 3 and not gr.state.running


async def test_only_reruns_the_named_cases(monkeypatch):
    import app.orchestrator.golden_run as gr

    goldens = [
        {"id": f"G{i}", "case_id": None, "trip_id": f"T{i}", "category_hint": "route_deviation",
         "expected_outcome": DENIED}
        for i in range(3)
    ]
    cleaned, ran = [], []

    class Conn:
        async def execute(self, *args):
            pass

        async def fetch(self, sql, trips):
            cleaned.extend(trips)
            return []

        async def close(self):
            pass

    async def connect():
        return Conn()

    async def load(conn):
        return goldens

    async def run_one(golden):
        ran.append(golden["id"])
        return {"case_id": "CASE-1", "passed": True, "actual": {}}

    monkeypatch.setattr(gr, "get_connection", connect)
    monkeypatch.setattr(gr, "_load_golden", load)
    monkeypatch.setattr(gr, "_run_one", run_one)
    await gr.run_golden(only=["G2"])
    assert ran == ["G2"]
    assert cleaned == ["T2"]  # the other cases' results are left alone
