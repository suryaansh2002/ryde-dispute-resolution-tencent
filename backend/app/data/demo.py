"""Read-only queries behind the demo endpoints: who the personas are, their trips, and
their cases. These are for the human using the UI to navigate. No agent ever reads
them, so they may show `trips.category_hint`, which agents must never see."""

from decimal import Decimal
from typing import Any

import asyncpg


def _plain(row: asyncpg.Record) -> dict[str, Any]:
    """Postgres NUMERIC arrives as Decimal, which JSON-encodes as a string; send floats."""
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}

# Trips designed to exercise a dispute come first, so the persona picker leads with
# users who have something interesting to file.
_PERSONAS = """
SELECT u.id, u.role, u.display_name, u.rating,
       COALESCE(bp.dispute_count_30d, 0) AS dispute_count_30d,
       count(t.id) AS trips,
       count(t.id) FILTER (WHERE t.category_hint NOT IN ('clean', 'smoke')) AS scenario_trips,
       count(c.id) FILTER (WHERE c.state = 'awaiting_response' AND c.complainee_id = u.id)
           AS awaiting_my_response
FROM users u
LEFT JOIN behavior_profiles bp ON bp.user_id = u.id
LEFT JOIN trips t ON t.rider_id = u.id OR t.driver_id = u.id
LEFT JOIN cases c ON c.trip_id = t.id
WHERE ($1::text IS NULL OR u.role = $1)
GROUP BY u.id, bp.dispute_count_30d
ORDER BY awaiting_my_response DESC, scenario_trips DESC, u.display_name
LIMIT $2
"""

_TRIPS = """
SELECT t.id, t.pickup_lat, t.pickup_lng, t.dropoff_lat, t.dropoff_lng,
       t.scheduled_at, t.completed_at, t.category_hint AS scenario_hint,
       CASE WHEN t.rider_id = $1 THEN 'rider' ELSE 'driver' END AS my_role,
       other.id AS other_party_id, other.display_name AS other_party_name,
       p.total_fare, p.add_on_fees,
       c.id AS case_id, c.state AS case_state
FROM trips t
JOIN users other ON other.id = CASE WHEN t.rider_id = $1 THEN t.driver_id ELSE t.rider_id END
LEFT JOIN payments p ON p.trip_id = t.id
LEFT JOIN cases c ON c.trip_id = t.id
WHERE t.rider_id = $1 OR t.driver_id = $1
ORDER BY (t.category_hint IN ('clean', 'smoke')), t.completed_at DESC
"""

_CASES = """
SELECT c.id, c.state, c.category, c.trip_id, c.created_at, c.updated_at,
       CASE WHEN c.complainer_id = $1 THEN 'complainer' ELSE 'complainee' END AS my_side,
       other.id AS other_party_id, other.display_name AS other_party_name,
       (c.state = 'awaiting_response' AND c.complainee_id = $1) AS needs_my_response
FROM cases c
JOIN users other
  ON other.id = CASE WHEN c.complainer_id = $1 THEN c.complainee_id ELSE c.complainer_id END
WHERE c.complainer_id = $1 OR c.complainee_id = $1
ORDER BY needs_my_response DESC, c.updated_at DESC
"""


async def list_personas(
    conn: asyncpg.Connection, role: str | None, limit: int
) -> list[dict[str, Any]]:
    return [_plain(r) for r in await conn.fetch(_PERSONAS, role, limit)]


async def list_user_trips(conn: asyncpg.Connection, user_id: str) -> list[dict[str, Any]]:
    return [_plain(r) for r in await conn.fetch(_TRIPS, user_id)]


async def list_user_cases(conn: asyncpg.Connection, user_id: str) -> list[dict[str, Any]]:
    return [_plain(r) for r in await conn.fetch(_CASES, user_id)]
