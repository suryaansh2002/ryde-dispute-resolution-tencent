"""Traffic events layering (data sources doc §4 step 5) — fully synthetic, not a live
feed (data sources doc §2 decision #2). Deliberately includes both justified (matching
event present) and unjustified (no matching event) Route Deviation trips so the full
policy branch gets exercised.
"""

import random
from datetime import timedelta

TRAFFIC_EVENT_TYPES = ("road_closure", "accident", "construction")


def maybe_generate_traffic_event(
    pickup: tuple[float, float], scheduled_at, completed_at, rng: random.Random, *, justified: bool,
) -> dict | None:
    """Returns a traffic_events row dict near the trip's pickup point and time window if
    `justified`, else None (the driver's claimed justification won't be backed by a real
    row — the unsupported-assertion branch, Policy doc §2)."""
    if not justified:
        return None
    lat, lng = pickup
    window_start = scheduled_at - timedelta(minutes=rng.randint(5, 20))
    window_end = completed_at + timedelta(minutes=rng.randint(5, 20))
    return {
        "near_lat": lat + rng.uniform(-0.01, 0.01),
        "near_lng": lng + rng.uniform(-0.01, 0.01),
        "time_window_start": window_start,
        "time_window_end": window_end,
        "type": rng.choice(TRAFFIC_EVENT_TYPES),
        "description": "Generated for synthetic dataset — justified route deviation.",
    }
