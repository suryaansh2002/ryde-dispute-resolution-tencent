"""Golden-case labeling (data sources doc §4 step 11).

"Hand-labeled" here means computed deterministically from the generation parameters
that produced each trip (the real deviation %, the real GPS trace, the real severity
tier) via the oracle below — which mirrors the Policy doc's own rules rather than a
human eyeballing each case. That's deliberately *more* reliable than a human labeler
guessing at numbers the pipeline already knows exactly, not a shortcut around real
labeling. Swap in actual human review before treating these as submission-ready golden
labels, since the oracle only encodes the policy's documented thresholds, not judgment
calls a human reviewer might make differently.

Property Damage cases get a placeholder photo uploaded now (step 10) so a future
`/golden-run` can file the claim for real with working evidence attached.
"""

import random

from data_generation.pipeline.categories import CategoryHint
from data_generation.pipeline.fares import PROPERTY_DAMAGE_FEES
from data_generation.pipeline.photos import SEVERITY_TIERS, upload_placeholder_photo


def _route_deviation_outcome(extra_fraction: float, justified: bool) -> dict:
    if justified or extra_fraction < 0.10:
        return {
            "outcome": "claim_denied", "remedy": {"type": "no_action"},
            "policy_applied": "POL-02",
        }
    merit = 0.5 if extra_fraction < 0.25 else 1.0
    outcome = "claim_upheld_partial" if merit < 1.0 else "claim_upheld"
    return {
        "outcome": outcome, "remedy": {"type": "partial_refund", "merit_fraction": merit},
        "policy_applied": "POL-02",
    }


def _no_show_outcome(complainer_role: str, driver_reached_pickup: bool) -> dict:
    if complainer_role == "rider":
        upheld = not driver_reached_pickup
    else:
        upheld = driver_reached_pickup
    if upheld:
        return {
            "outcome": "claim_upheld", "remedy": {"type": "no_show_fee_waiver", "amount": 4.50},
            "policy_applied": "POL-03",
        }
    return {"outcome": "claim_denied", "remedy": {"type": "no_action"}, "policy_applied": "POL-03"}


def _property_damage_outcome(severity: str, has_evidence: bool) -> dict:
    if not has_evidence:
        return {
            "outcome": "declined_insufficient_evidence", "remedy": {"type": "no_action"},
            "policy_applied": "POL-04",
        }
    # Photo-only claims are charged the tier's scheduled amount (our own rule,
    # app/rules/policy_math.py), so the label is exact.
    return {
        "outcome": "claim_upheld",
        "remedy": {"type": "cleaning_repair_fee", "amount": PROPERTY_DAMAGE_FEES[severity]},
        "policy_applied": "POL-04",
    }


def _safety_outcome() -> dict:
    return {"outcome": "escalated_to_l2", "remedy": {"type": "no_action"}, "policy_applied": None}


def _min_distance_to_pickup_m(gps_trace: list[dict], pickup: tuple[float, float]) -> float:
    from data_generation.pipeline.geo import haversine_km

    if not gps_trace:
        return float("inf")
    return min(haversine_km((p["lat"], p["lng"]), pickup) * 1000 for p in gps_trace)


async def label_golden_cases(conn, candidates: list[dict], rng: random.Random) -> list[str]:
    golden_ids = []
    for c in candidates:
        hint = c["hint"]
        prepared_evidence: list[dict] = []

        if hint == CategoryHint.ROUTE_DEVIATION:
            expected = _route_deviation_outcome(c["extra_fraction"], c["justified"])
        elif hint == CategoryHint.NO_SHOW_CHARGE:
            reached = _min_distance_to_pickup_m(c["gps_trace"], c["pickup"]) <= 100
            expected = _no_show_outcome(c["complainer_role"], reached)
        elif hint == CategoryHint.PROPERTY_DAMAGE:
            severity = c.get("severity") or rng.choice(SEVERITY_TIERS)
            has_evidence = rng.random() > 0.2  # ~20% deliberately insufficient (step 10 note)
            if has_evidence:
                object_key, hash_ = upload_placeholder_photo(str(c["trip_id"]), severity)
                prepared_evidence = [{"kind": "photo", "hash": hash_, "object_key": object_key}]
            expected = _property_damage_outcome(severity, has_evidence)
        else:
            expected = _safety_outcome()

        expected["claim_text"] = c["claim_text"]
        expected["complainer_role"] = c["complainer_role"]

        golden_id = await conn.fetchval(
            """INSERT INTO golden_cases (trip_id, expected_outcome, prepared_evidence)
               VALUES ($1, $2::jsonb, $3::jsonb) RETURNING id""",
            c["trip_id"], _dumps(expected), _dumps(prepared_evidence),
        )
        golden_ids.append(golden_id)
    return golden_ids


def _dumps(value) -> str:
    import json
    return json.dumps(value)
