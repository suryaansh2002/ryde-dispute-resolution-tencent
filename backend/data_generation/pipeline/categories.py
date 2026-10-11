"""Category assignment (data sources doc §4 step 3) — generation-time label only,
never visible to any agent (`trips.category_hint`). Suggested starting split:
~40% clean, ~20% each across the three in-scope categories, plus a few safety-flagged
trips for the hard-stop path. Tunable, not a policy fact.
"""

import random
from enum import StrEnum


class CategoryHint(StrEnum):
    CLEAN = "clean"
    ROUTE_DEVIATION = "route_deviation"
    NO_SHOW_CHARGE = "no_show_charge"
    PROPERTY_DAMAGE = "property_damage"
    SAFETY_INCIDENT = "safety_incident"


DEFAULT_WEIGHTS: dict[CategoryHint, float] = {
    CategoryHint.CLEAN: 0.40,
    CategoryHint.ROUTE_DEVIATION: 0.18,
    CategoryHint.NO_SHOW_CHARGE: 0.18,
    CategoryHint.PROPERTY_DAMAGE: 0.18,
    CategoryHint.SAFETY_INCIDENT: 0.06,
}

# Route Deviation tolerance tiers (Policy doc §2 — not Ryde-sourced, our own invented
# tiering): assign a roughly even mix of under-10%, 10-25%, and over-25% deviations so
# the full policy branch gets exercised.
ROUTE_DEVIATION_EXTRA_FRACTIONS = [0.05, 0.15, 0.20, 0.30, 0.45]


def assign_category_hints(n: int, rng: random.Random) -> list[CategoryHint]:
    hints = list(DEFAULT_WEIGHTS.keys())
    weights = list(DEFAULT_WEIGHTS.values())
    return rng.choices(hints, weights=weights, k=n)
