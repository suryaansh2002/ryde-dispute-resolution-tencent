"""OneMap routing (data sources doc §2, §4 step 2) — real Singapore road-network routes
between real lat/lng pairs. OneMap tokens expire roughly every 3 days, so a manually
pasted `ONEMAP_ACCESS_TOKEN` in `.env` WILL go stale mid-build; if `ONEMAP_EMAIL`/
`ONEMAP_PASSWORD` are set, this self-refreshes instead of trusting the static token.

Real sourcing is "best effort, not required": per the hackathon handbook, teams may
mock/simulate external data where real sources are unavailable. When OneMap is
unreachable (no valid token, no credentials, or a network/API error), `get_route` falls
back to a synthetic straight-line route — clearly labeled `"source": "synthetic"` in the
returned geometry's properties, never silently passed off as a real OneMap route.
"""

import time

import httpx

from app.config import settings

ONEMAP_BASE = "https://www.onemap.gov.sg"
_ROUTE_PATH = "/api/public/routingsvc/route"
_AUTH_PATH = "/api/auth/post/getToken"

_cached_token: str | None = None
_cached_token_expiry: float = 0.0


class OneMapUnavailable(Exception):
    pass


def _refresh_token() -> str:
    global _cached_token, _cached_token_expiry
    if not (settings.onemap_email and settings.onemap_password):
        raise OneMapUnavailable("no ONEMAP_EMAIL/ONEMAP_PASSWORD configured to self-refresh")
    resp = httpx.post(
        f"{ONEMAP_BASE}{_AUTH_PATH}",
        json={"email": settings.onemap_email, "password": settings.onemap_password},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _cached_token = data["access_token"]
    # expiry_timestamp is an absolute unix timestamp; refresh 60s early to be safe.
    _cached_token_expiry = int(data.get("expiry_timestamp", 0)) - 60
    return _cached_token


def _get_token() -> str:
    global _cached_token
    if _cached_token and time.time() < _cached_token_expiry:
        return _cached_token
    if settings.onemap_email and settings.onemap_password:
        return _refresh_token()
    if settings.onemap_access_token:
        return settings.onemap_access_token
    raise OneMapUnavailable("no OneMap token or credentials configured")


def _synthetic_route(
    start: tuple[float, float], end: tuple[float, float], n_points: int = 6
) -> dict:
    """A straight-line stand-in when OneMap can't be reached — clearly labeled, never
    presented as a real road-network route."""
    (lat1, lng1), (lat2, lng2) = start, end
    coords = [
        [lng1 + (lng2 - lng1) * i / (n_points - 1), lat1 + (lat2 - lat1) * i / (n_points - 1)]
        for i in range(n_points)
    ]
    return {"type": "LineString", "coordinates": coords, "properties": {"source": "synthetic"}}


def get_route(start: tuple[float, float], end: tuple[float, float]) -> dict:
    """Returns a GeoJSON LineString (lat, lng) -> (lat, lng). Falls back to a synthetic
    straight line, labeled as such, if OneMap can't be reached."""
    try:
        token = _get_token()
        resp = httpx.get(
            f"{ONEMAP_BASE}{_ROUTE_PATH}",
            params={
                "start": f"{start[0]},{start[1]}", "end": f"{end[0]},{end[1]}",
                "routeType": "drive",
            },
            headers={"Authorization": token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        coords = _decode_onemap_geometry(data)
        return {"type": "LineString", "coordinates": coords, "properties": {"source": "onemap"}}
    except (OneMapUnavailable, httpx.HTTPError, KeyError, ValueError):
        return _synthetic_route(start, end)


def _decode_onemap_geometry(data: dict) -> list[list[float]]:
    """OneMap's routing response encodes the route as a Google-style encoded polyline
    string in `route_geometry`. Decodes it to a plain [lng, lat] coordinate list."""
    encoded = (
        data["route_summary"]["route_geometry"] if "route_summary" in data
        else data["route_geometry"]
    )
    coords: list[list[float]] = []
    index = lat = lng = 0
    while index < len(encoded):
        for is_lat in (True, False):
            shift = result = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if is_lat:
                lat += delta
            else:
                lng += delta
        coords.append([lng / 1e5, lat / 1e5])
    return coords
