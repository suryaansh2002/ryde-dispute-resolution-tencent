"""Shared geo helpers for the generation pipeline (data sources doc §4)."""

import random
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

_EARTH_RADIUS_KM = 6371.0088

# A spread of real Singapore neighborhoods (lat, lng) for route variety (data sources
# doc §4 step 1) — not an exhaustive list, just real places, not randomly generated
# coordinates that might land in the sea or on a highway median.
SINGAPORE_NEIGHBORHOODS: list[tuple[str, float, float]] = [
    ("Orchard", 1.3048, 103.8318),
    ("Raffles Place", 1.2840, 103.8514),
    ("Tampines", 1.3496, 103.9568),
    ("Jurong East", 1.3329, 103.7436),
    ("Woodlands", 1.4382, 103.7890),
    ("Bishan", 1.3526, 103.8352),
    ("Tiong Bahru", 1.2847, 103.8265),
    ("Bugis", 1.3006, 103.8559),
    ("Clementi", 1.3151, 103.7654),
    ("Punggol", 1.4051, 103.9024),
    ("Bedok", 1.3236, 103.9273),
    ("Ang Mo Kio", 1.3691, 103.8454),
    ("Sentosa", 1.2494, 103.8303),
    ("Changi", 1.3644, 103.9915),
    ("Novena", 1.3200, 103.8438),
    ("Holland Village", 1.3111, 103.7963),
]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lng1), (lat2, lng2) = a, b
    h = (
        sin(radians(lat2 - lat1) / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lng2 - lng1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(h))


def sample_pickup_dropoff(rng: random.Random) -> tuple[tuple[float, float], tuple[float, float]]:
    """Two distinct real neighborhoods, jittered slightly so trips don't all start/end
    at the exact same point."""
    a, b = rng.sample(SINGAPORE_NEIGHBORHOODS, 2)

    def jitter(lat: float, lng: float) -> tuple[float, float]:
        return (lat + rng.uniform(-0.003, 0.003), lng + rng.uniform(-0.003, 0.003))

    return jitter(a[1], a[2]), jitter(b[1], b[2])


def route_length_km(geometry: dict) -> float:
    coords = geometry["coordinates"]
    return sum(
        haversine_km((coords[i][1], coords[i][0]), (coords[i + 1][1], coords[i + 1][0]))
        for i in range(len(coords) - 1)
    )


def interpolate_gps_trace(
    geometry: dict, started_at: datetime, ended_at: datetime, interval_seconds: int = 30
) -> list[dict]:
    """Timestamped points along a route's geometry at a fixed sampling interval
    (data sources doc §4 step 6)."""
    coords = geometry["coordinates"]
    duration = (ended_at - started_at).total_seconds()
    n_samples = max(2, int(duration // interval_seconds) + 1)
    trace = []
    for i in range(n_samples):
        frac = i / (n_samples - 1)
        seg_pos = frac * (len(coords) - 1)
        idx = min(int(seg_pos), len(coords) - 2)
        local_frac = seg_pos - idx
        lng = coords[idx][0] + (coords[idx + 1][0] - coords[idx][0]) * local_frac
        lat = coords[idx][1] + (coords[idx + 1][1] - coords[idx][1]) * local_frac
        t = started_at + timedelta(seconds=frac * duration)
        trace.append({"lat": round(lat, 6), "lng": round(lng, 6), "t": t.isoformat()})
    return trace


def perturb_route(geometry: dict, extra_fraction: float, rng: random.Random) -> dict:
    """A deliberately detoured version of `geometry` for Route Deviation trips
    (data sources doc §4 step 4) — displaces the route's midpoint outward so the
    resulting path is longer by roughly `extra_fraction` of the original distance.
    Perturbation magnitude is a tunable generation parameter, not a policy fact
    (data sources doc §5 — no real tolerance threshold exists to calibrate against)."""
    coords = [list(c) for c in geometry["coordinates"]]
    if len(coords) < 2:
        return geometry
    mid = len(coords) // 2
    original_km = route_length_km(geometry)
    target_extra_km = original_km * extra_fraction
    # Displace perpendicular to the start->end direction, roughly proportional to the
    # desired extra distance (a round trip out-and-back through the detour point).
    lng1, lat1 = coords[0]
    lng2, lat2 = coords[-1]
    dx, dy = lng2 - lng1, lat2 - lat1
    length = max(sqrt(dx * dx + dy * dy), 1e-9)
    perp = (-dy / length, dx / length)
    offset_deg = (target_extra_km / 2) / 111.0  # ~111km per degree, good enough locally
    sign = rng.choice([-1, 1])
    detour_point = [
        coords[mid][0] + sign * perp[0] * offset_deg,
        coords[mid][1] + sign * perp[1] * offset_deg,
    ]
    new_coords = coords[:mid] + [detour_point] + coords[mid:]
    return {
        "type": "LineString", "coordinates": new_coords,
        "properties": {"source": "synthetic_perturbation"},
    }


def detour_waypoint(
    start: tuple[float, float], end: tuple[float, float], extra_fraction: float, side: int,
) -> tuple[float, float]:
    """A point off to one side of the straight start→end line, far enough that going
    through it adds roughly `extra_fraction` to the trip. Routing pickup → waypoint →
    dropoff on real roads then gives a detour a real driver could have taken. `side` (±1)
    picks which side of the line."""
    (lat1, lng1), (lat2, lng2) = start, end
    dx, dy = lng2 - lng1, lat2 - lat1
    length = max(sqrt(dx * dx + dy * dy), 1e-9)
    # Two legs of a triangle with half-base L/2 and height h are 2*sqrt((L/2)^2 + h^2),
    # so h = (L/2) * sqrt((1 + e)^2 - 1) adds a fraction e of the straight-line length.
    h = (length / 2) * sqrt((1 + extra_fraction) ** 2 - 1)
    return (
        (lat1 + lat2) / 2 + side * (dx / length) * h,
        (lng1 + lng2) / 2 - side * (dy / length) * h,
    )
