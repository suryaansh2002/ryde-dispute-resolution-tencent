"""Read-only queries behind the demo endpoints: who the personas are, their trips, and
their cases. These are for the human using the UI to navigate. No agent ever reads
them, so they may show `trips.category_hint`, which agents must never see."""

import json
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


async def system_stats(conn: asyncpg.Connection) -> dict[str, Any]:
    """Headline numbers for the landing page: what the system has actually done."""
    by_state = {r["state"]: r["n"] for r in await conn.fetch(
        "SELECT state, count(*) AS n FROM cases GROUP BY state")}
    by_category = {r["category"]: r["n"] for r in await conn.fetch(
        "SELECT category, count(*) AS n FROM cases WHERE category IS NOT NULL GROUP BY category")}
    decided = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE NOT d.human_ratified) AS automatic,
                  count(*) FILTER (WHERE d.human_ratified) AS human
           FROM cases c
           JOIN LATERAL (SELECT human_ratified FROM decisions
                         WHERE case_id = c.id ORDER BY created_at DESC LIMIT 1) d ON true
           WHERE c.state = 'decided'""")
    # Time from claim to first agent decision, from the trace log itself.
    timing = await conn.fetchrow(
        """SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY secs) AS median_s
           FROM (SELECT extract(epoch FROM min(e.t) - c.created_at) AS secs
                 FROM cases c JOIN trace_events e ON e.case_id = c.id
                 WHERE e.kind = 'agent_output' AND e.agent = 'judge'
                 GROUP BY c.id, c.created_at) x""")
    reasons = await conn.fetch(
        """SELECT r AS reason, count(*) AS n FROM (
             SELECT CASE
               WHEN (d.escalation->>'bucket_escalate')::bool THEN 'risk bucket'
               WHEN d.escalation->>'compliance_veto' IS NOT NULL THEN 'compliance veto'
               WHEN (d.escalation->>'confidence_escalate')::bool THEN 'low confidence'
               WHEN (d.escalation->>'judge_requested_escalation')::bool THEN 'judge requested'
             END AS r
             FROM decisions d) x
           WHERE r IS NOT NULL GROUP BY r ORDER BY n DESC""")
    return {
        "cases": sum(by_state.values()),
        "by_state": by_state,
        "by_category": by_category,
        "decided_automatically": decided["automatic"] if decided else 0,
        "decided_by_human": decided["human"] if decided else 0,
        "awaiting_human": by_state.get("escalated", 0) + by_state.get("safety_bypassed", 0),
        "median_seconds_to_decision": (
            round(float(timing["median_s"]), 1) if timing and timing["median_s"] else None),
        "escalation_reasons": {r["reason"]: r["n"] for r in reasons},
        "trips": await conn.fetchval("SELECT count(*) FROM trips"),
        "users": await conn.fetchval("SELECT count(*) FROM users"),
    }


# Who plausibly files each kind of dispute, for the one-click demo scenarios.
_FILER_ROLE = {
    "route_deviation": "rider",
    "no_show_charge": "rider",
    "property_damage": "driver",
    "safety_incident": "rider",
}


async def pick_scenario(
    conn: asyncpg.Connection, category: str, role: str | None = None
) -> dict[str, Any] | None:
    """A recent, unclaimed trip designed for `category`, with the party who'd file it
    (`role` overrides the usual filer, e.g. a driver claiming a no-show fee). Safety
    scenarios fall back to any unclaimed trip: the claim text makes it a safety case,
    not the trip."""
    role = role or _FILER_ROLE[category]
    if role not in ("rider", "driver"):  # interpolated into the SQL below
        raise ValueError(f"unknown role {role!r}")
    row = await conn.fetchrow(
        f"""SELECT t.id AS trip_id, t.{role}_id AS user_id, u.display_name,
                   other.display_name AS other_party_name, t.completed_at,
                   (SELECT p.total_fare FROM payments p WHERE p.trip_id = t.id
                    ORDER BY p.id LIMIT 1) AS total_fare
            FROM trips t
            JOIN users u ON u.id = t.{role}_id
            JOIN users other ON other.id = t.{"driver" if role == "rider" else "rider"}_id
            LEFT JOIN cases c ON c.trip_id = t.id
            WHERE c.id IS NULL
              AND t.completed_at >= now() - interval '29 days'
              AND (t.category_hint = $1 OR ($1 = 'safety_incident' AND t.category_hint = 'clean'))
            ORDER BY random() LIMIT 1""",
        category,
    )
    if row is None:
        return None
    return {**_plain(row), "role": role, "category": category}


# A trip as either party sees it before any dispute. Deliberately leaves out
# `category_hint` (a generation label) and `gps_trace` (the raw feed stays in the case file).
_TRIP_DETAIL = """
SELECT t.id, t.scheduled_at, t.completed_at, t.pickup_lat, t.pickup_lng,
       t.dropoff_lat, t.dropoff_lng, t.optimal_route_geometry, t.actual_route_geometry,
       r.id AS rider_id, r.display_name AS rider_name,
       d.id AS driver_id, d.display_name AS driver_name,
       c.id AS case_id, c.state AS case_state
FROM trips t
JOIN users r ON r.id = t.rider_id
JOIN users d ON d.id = t.driver_id
LEFT JOIN LATERAL (
    SELECT id, state FROM cases WHERE trip_id = t.id ORDER BY created_at DESC LIMIT 1
) c ON true
WHERE t.id = $1
"""


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def get_trip_detail(conn: asyncpg.Connection, trip_id: str) -> dict[str, Any] | None:
    """The trip-detail screen: map geometry, both parties, the receipt, and any case."""
    row = await conn.fetchrow(_TRIP_DETAIL, trip_id)
    if row is None:
        return None
    payment = await conn.fetchrow(
        """SELECT base_fare, platform_fee, taxes, total_fare, add_on_fees
           FROM payments WHERE trip_id = $1 ORDER BY id LIMIT 1""",
        trip_id,
    )
    receipt = None
    if payment is not None:
        receipt = _plain(payment)
        receipt["add_on_fees"] = [
            {"type": f.get("type"), "amount": float(f.get("amount") or 0)}
            for f in _json(payment["add_on_fees"]) or []
        ]
    return {
        "id": str(row["id"]),
        "scheduled_at": row["scheduled_at"],
        "completed_at": row["completed_at"],
        "pickup": {"lat": row["pickup_lat"], "lng": row["pickup_lng"]},
        "dropoff": {"lat": row["dropoff_lat"], "lng": row["dropoff_lng"]},
        "rider": {"id": str(row["rider_id"]), "name": row["rider_name"]},
        "driver": {"id": str(row["driver_id"]), "name": row["driver_name"]},
        "payment": receipt,
        "optimal_route": _json(row["optimal_route_geometry"]),
        "actual_route": _json(row["actual_route_geometry"]),
        "case_id": row["case_id"],
        "case_state": row["case_state"],
    }


# The landing page's featured hearing: a decided case where both advocates actually
# argued. Prefers an automatic Route Deviation decision (the clearest one to watch), then
# falls back to any decided case with both arguments.
_FEATURED = """
SELECT c.id FROM cases c
JOIN LATERAL (
    SELECT human_ratified, outcome FROM decisions WHERE case_id = c.id
    ORDER BY created_at DESC LIMIT 1
) d ON true
WHERE c.state = 'decided'
  AND EXISTS (SELECT 1 FROM trace_events e WHERE e.case_id = c.id
              AND e.kind = 'agent_output' AND e.agent = 'rider_advocate')
  AND EXISTS (SELECT 1 FROM trace_events e WHERE e.case_id = c.id
              AND e.kind = 'agent_output' AND e.agent = 'driver_advocate')
-- An upheld route case shows the hearing best: a measurable detour, a refund, both
-- counsel citing the same route comparison.
ORDER BY (c.category = 'route_deviation' AND NOT d.human_ratified) DESC,
         (d.outcome IN ('claim_upheld', 'claim_upheld_partial')) DESC, c.updated_at DESC
LIMIT 1
"""


async def featured_case_id(conn: asyncpg.Connection) -> str | None:
    return await conn.fetchval(_FEATURED)
