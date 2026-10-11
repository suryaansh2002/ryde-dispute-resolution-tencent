"""Evidence Lookup (system design §6): read-only access to one `CaseFile`'s
already-assembled data — never raw DB access.

Every citable item gets a stable ref ID. Items that carry their own ID keep it (chat
`MSG-*`, photo `EV-*`, traffic events with an `id`); everything else gets a fixed ref.
`ROUTE-COMPARISON` is derived from the two route geometries so no agent estimates
distances itself. This index is also what the citation validators check `cites` against.
"""

from dataclasses import dataclass
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


def evidence_index(case_file: CaseFile) -> dict[str, EvidenceItem]:
    index: dict[str, EvidenceItem] = {}
    for msg in case_file.chat_log:
        index[msg.id] = EvidenceItem("chat_message", msg.model_dump(mode="json"))
    for photo in case_file.photos:
        index[photo.evidence_id] = EvidenceItem("photo", photo.model_dump(mode="json"))
    for i, event in enumerate(case_file.traffic_events, start=1):
        index[str(event.get("id") or f"TRAFFIC-{i:02d}")] = EvidenceItem("traffic_event", event)

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
        })
    return index
