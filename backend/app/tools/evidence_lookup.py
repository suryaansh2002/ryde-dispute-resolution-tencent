"""Evidence Lookup (system design §6): read-only access to one `CaseFile`'s
already-assembled data — never raw DB access.

Every citable item gets a stable ref ID. Chat messages and photos keep their own
IDs (`MSG-*`, `EV-*`); everything else gets a fixed ref (traffic events: `TRAFFIC-01`...).
`ROUTE-COMPARISON` is derived from the two route geometries so no agent estimates
distances itself. This index is also what the citation validators check `cites` against.
"""

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

from app.rules.policy_math import route_refund, route_tier
from app.schemas import CaseFile

PAYMENT = "PAYMENT"
GPS_TRACE = "GPS-TRACE"
ROUTE_OPTIMAL = "ROUTE-OPTIMAL"
ROUTE_ACTUAL = "ROUTE-ACTUAL"
ROUTE_COMPARISON = "ROUTE-COMPARISON"
PROFILE_COMPLAINER = "PROFILE-COMPLAINER"
PROFILE_COMPLAINEE = "PROFILE-COMPLAINEE"
PICKUP_PROXIMITY = "PICKUP-PROXIMITY"

# Not Ryde-sourced: our own proximity test for "the driver arrived" (Policy doc §3).
PICKUP_ARRIVAL_RADIUS_M = 100
# Not Ryde-sourced: our own test for a traffic incident "along the optimal route" (Policy
# doc §2): active during the trip and within this distance of the planned route.
TRAFFIC_MATCH_RADIUS_M = 2000

_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class EvidenceItem:
    kind: str
    data: Any  # JSON-serializable


def _haversine_km(a: list[float], b: list[float]) -> float:
    (lng1, lat1), (lng2, lat2) = a[:2], b[:2]
    h = (sin(radians(lat2 - lat1) / 2) ** 2
         + cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lng2 - lng1) / 2) ** 2)
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(h))


def route_length_km(geometry: dict | None) -> float | None:
    """Length of a GeoJSON LineString ([lng, lat] coordinates), or None if unusable."""
    coords = (geometry or {}).get("coordinates") or []
    if (geometry or {}).get("type") != "LineString" or len(coords) < 2:
        return None
    return sum(_haversine_km(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def _distance_to_route_m(point: list[float], geometry: dict | None) -> float | None:
    """Shortest distance from a [lng, lat] point to a LineString, in metres (local
    equirectangular projection; fine at city scale)."""
    coords = (geometry or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    k = cos(radians(point[1]))
    m_per_deg = _EARTH_RADIUS_KM * 1000 * radians(1)

    def xy(c: list[float]) -> tuple[float, float]:
        return ((c[0] - point[0]) * k * m_per_deg, (c[1] - point[1]) * m_per_deg)

    best = float("inf")
    for a, b in zip(coords, coords[1:], strict=False):
        (ax, ay), (bx, by) = xy(a), xy(b)
        dx, dy = bx - ax, by - ay
        seg = dx * dx + dy * dy
        t = 0.0 if seg == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg))
        best = min(best, sqrt((ax + t * dx) ** 2 + (ay + t * dy) ** 2))
    return best


def _when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _traffic_facts(event: dict, case_file: CaseFile) -> dict:
    """Policy-test facts about one traffic event, computed in code like ROUTE-COMPARISON."""
    facts: dict[str, Any] = {}
    lat, lng = event.get("near_lat"), event.get("near_lng")
    if lat is not None and lng is not None:
        dist = _distance_to_route_m([lng, lat], case_file.optimal_route_geometry)
        if dist is not None:
            facts["distance_to_planned_route_m"] = round(dist)
    start, end = _when(event.get("time_window_start")), _when(event.get("time_window_end"))
    trip_start = case_file.trip_started_at or case_file.trip_completed_at
    trip_end = case_file.trip_completed_at
    if start and end and trip_start and trip_end:
        facts["during_trip"] = start <= trip_end and end >= trip_start
    if "distance_to_planned_route_m" in facts and "during_trip" in facts:
        facts["matches_route"] = (
            facts["during_trip"] and facts["distance_to_planned_route_m"] <= TRAFFIC_MATCH_RADIUS_M
        )
        facts["match_radius_m"] = TRAFFIC_MATCH_RADIUS_M
    return facts


def evidence_index(case_file: CaseFile) -> dict[str, EvidenceItem]:
    index: dict[str, EvidenceItem] = {}
    for msg in case_file.chat_log:
        index[msg.id] = EvidenceItem("chat_message", msg.model_dump(mode="json"))
    for photo in case_file.photos:
        index[photo.evidence_id] = EvidenceItem("photo", photo.model_dump(mode="json"))
    # Traffic events are cited as TRAFFIC-01, TRAFFIC-02... in case-file order, like every
    # other non-message ref, not by their database UUID, which is unreadable in a citation.
    for i, event in enumerate(case_file.traffic_events, start=1):
        index[f"TRAFFIC-{i:02d}"] = EvidenceItem(
            "traffic_event", {**event, **_traffic_facts(event, case_file)}
        )

    index[PAYMENT] = EvidenceItem("payment", case_file.payment.model_dump(mode="json"))
    if case_file.gps_trace:
        trace = [p.model_dump(mode="json") for p in case_file.gps_trace]
        index[GPS_TRACE] = EvidenceItem("gps_trace", trace)
    index[PROFILE_COMPLAINER] = EvidenceItem(
        "behavior_profile", case_file.complainer_profile.model_dump(mode="json"))
    index[PROFILE_COMPLAINEE] = EvidenceItem(
        "behavior_profile", case_file.complainee_profile.model_dump(mode="json"))

    if case_file.gps_trace:
        pickup = [case_file.pickup_lng, case_file.pickup_lat]
        nearest = min(
            case_file.gps_trace, key=lambda p: _haversine_km([p.lng, p.lat], pickup)
        )
        min_m = _haversine_km([nearest.lng, nearest.lat], pickup) * 1000
        index[PICKUP_PROXIMITY] = EvidenceItem("pickup_proximity", {
            "pickup": {"lat": case_file.pickup_lat, "lng": case_file.pickup_lng},
            "closest_approach_m": round(min_m, 1),
            "closest_approach_at": nearest.t.isoformat(),
            "arrival_radius_m": PICKUP_ARRIVAL_RADIUS_M,
            "reached_pickup": min_m <= PICKUP_ARRIVAL_RADIUS_M,
        })

    optimal_km = route_length_km(case_file.optimal_route_geometry)
    actual_km = route_length_km(case_file.actual_route_geometry)
    if optimal_km is not None:
        index[ROUTE_OPTIMAL] = EvidenceItem("route", {
            "geometry": case_file.optimal_route_geometry, "length_km": round(optimal_km, 3)})
    if actual_km is not None:
        index[ROUTE_ACTUAL] = EvidenceItem("route", {
            "geometry": case_file.actual_route_geometry, "length_km": round(actual_km, 3)})
    if optimal_km and actual_km is not None:
        extra_km = actual_km - optimal_km
        extra_pct = (actual_km / optimal_km - 1) * 100
        index[ROUTE_COMPARISON] = EvidenceItem("route_comparison", {
            "optimal_km": round(optimal_km, 3),
            "actual_km": round(actual_km, 3),
            "extra_km": round(extra_km, 3),
            "extra_pct": round(extra_pct, 2),
            "policy_tier": route_tier(extra_pct),
            "refund_if_unjustified": route_refund(
                case_file.payment.base_fare, extra_km, actual_km, extra_pct
            ),
            # Traffic events active during the trip and near the planned route: the
            # "matching traffic event" that justifies a deviation (Policy doc §2).
            "matching_traffic_events": [
                ref for ref, item in index.items()
                if item.kind == "traffic_event" and item.data.get("matches_route")
            ],
        })
    return index
