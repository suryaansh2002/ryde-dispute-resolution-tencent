"""Policy arithmetic, computed in code rather than by a model (Policy doc Part 1).

The Judge decides *which* rule applies (justified deviation or not, which damage tier).
Every dollar amount that follows from that choice is computed here, deterministically.
The compliance check then holds the Judge's remedy to these numbers. Run against real
Groq, the model's own refund arithmetic varied between runs on identical evidence.
"""

# Route Deviation tolerance tiers (Policy doc §2). NOT Ryde-sourced: our own invented
# tiering, since no real Ryde threshold or refund formula exists.
ROUTE_NO_MERIT_BELOW_PCT = 10.0
ROUTE_FULL_MERIT_ABOVE_PCT = 25.0
ROUTE_MERIT = {"under_10_pct": 0.0, "10_to_25_pct": 0.5, "over_25_pct": 1.0}

# Property Damage fee schedule (Policy doc §4). Real, sourced "up to" caps.
PROPERTY_DAMAGE_TIERS = {"minor": 40.00, "moderate": 120.00, "severe": 200.00}
# NOT Ryde-sourced, our own rule: with a photo but no cleaning receipt (our data has no
# receipts), the fee is the tier's scheduled amount. Ryde's real process sets an amount
# "within applicable caps" from receipts, which this system doesn't collect.
PHOTO_ONLY_FEES = set(PROPERTY_DAMAGE_TIERS.values())


def route_tier(extra_pct: float) -> str:
    if extra_pct < ROUTE_NO_MERIT_BELOW_PCT:
        return "under_10_pct"
    if extra_pct <= ROUTE_FULL_MERIT_ABOVE_PCT:
        return "10_to_25_pct"
    return "over_25_pct"


def route_refund(base_fare: float, extra_km: float, actual_km: float, extra_pct: float) -> float:
    """refund = fare attributable to the extra distance × merit (Policy doc §2), where the
    attributable fare is base_fare × extra_km / actual_km."""
    if actual_km <= 0 or extra_km <= 0:
        return 0.0
    merit = ROUTE_MERIT[route_tier(extra_pct)]
    return round(base_fare * extra_km / actual_km * merit, 2)
