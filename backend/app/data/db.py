"""Postgres access layer (system design §5). The Evidence Collection Agent is the only
agent that reaches this module directly; everyone downstream works off the `CaseFile`
it produces (system design §4 rule 2, §6). The orchestrator and API use it too.

Connections come from a pool. Opening a fresh TLS connection to Neon costs 1–2 s, which
made every page load and live update visibly lag. Callers keep the simple
`conn = await get_connection()` / `await conn.close()` shape; close() returns the
connection to the pool. Long-lived LISTEN streams use `connect_direct()` instead, so an
open browser tab can never starve the pool.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.config import settings

# One pool per event loop: scripts call asyncio.run() more than once, and an asyncpg
# pool is bound to the loop that created it.
_pools: dict[int, asyncpg.Pool] = {}
_pool_lock = asyncio.Lock()


async def _pool() -> asyncpg.Pool:
    key = id(asyncio.get_running_loop())
    if key not in _pools:
        async with _pool_lock:
            if key not in _pools:
                _pools[key] = await asyncpg.create_pool(
                    settings.database_url_unpooled,
                    min_size=1,
                    max_size=10,
                    # Neon suspends idle compute after ~5 min, killing its connections.
                    # Retire idle ones well before that rather than hand out a dead one.
                    max_inactive_connection_lifetime=60,
                )
    return _pools[key]


class PooledConnection:
    """An asyncpg connection whose close() returns it to the pool."""

    def __init__(self, pool: asyncpg.Pool, conn: asyncpg.Connection):
        self._pool = pool
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    async def close(self) -> None:
        await self._pool.release(self._conn)


async def get_connection() -> asyncpg.Connection:
    pool = await _pool()
    return PooledConnection(pool, await pool.acquire())  # type: ignore[return-value]


async def connect_direct() -> asyncpg.Connection:
    """A dedicated, unpooled connection, for long-lived uses like LISTEN."""
    return await asyncpg.connect(settings.database_url_unpooled)


async def close_pools() -> None:
    for pool in list(_pools.values()):
        await pool.close()
    _pools.clear()


def _loads(value: Any) -> Any:
    """asyncpg (at least against Neon's proxy) returns jsonb columns as raw text rather
    than decoding them via `set_type_codec`, for reasons that didn't repro against a
    literal `::jsonb` cast in isolation — not worth chasing further. Decoding explicitly
    here is simpler and doesn't depend on codec/wire-format negotiation behaving the
    same way across environments."""
    if value is None or not isinstance(value, str):
        return value
    return json.loads(value)


@dataclass
class TripBundle:
    """Everything the Evidence Collection Agent needs for one trip, fetched in one pass
    so the agent's output validator can reconstruct `CaseFile`'s raw-data fields from a
    single known-good source rather than trusting the model to copy them verbatim."""

    trip: dict[str, Any]
    payment: dict[str, Any] | None
    chat_messages: list[dict[str, Any]]
    traffic_events: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    complainer: dict[str, Any]
    complainee: dict[str, Any]
    complainer_profile: dict[str, Any] | None
    complainee_profile: dict[str, Any] | None


async def fetch_trip_bundle(
    conn: asyncpg.Connection, trip_id: str, case_id: str, complainer_id: str, complainee_id: str
) -> TripBundle:
    trip = await conn.fetchrow("SELECT * FROM trips WHERE id = $1", trip_id)
    if trip is None:
        raise ValueError(f"no trip {trip_id!r}")

    payment = await conn.fetchrow(
        "SELECT * FROM payments WHERE trip_id = $1 ORDER BY id LIMIT 1", trip_id
    )
    chat_messages = await conn.fetch(
        "SELECT * FROM chat_messages WHERE trip_id = $1 ORDER BY timestamp", trip_id
    )
    traffic_events = await conn.fetch(
        """SELECT * FROM traffic_events
           WHERE time_window_start <= $2 AND time_window_end >= $1
             AND near_lat BETWEEN $3 - 0.05 AND $3 + 0.05
             AND near_lng BETWEEN $4 - 0.05 AND $4 + 0.05""",
        trip["scheduled_at"], trip["completed_at"], trip["pickup_lat"], trip["pickup_lng"],
    )
    evidence = await conn.fetch(
        "SELECT * FROM evidence WHERE case_id = $1 ORDER BY submitted_at", case_id
    )
    complainer = await conn.fetchrow("SELECT * FROM users WHERE id = $1", complainer_id)
    complainee = await conn.fetchrow("SELECT * FROM users WHERE id = $1", complainee_id)
    complainer_profile = await conn.fetchrow(
        "SELECT * FROM behavior_profiles WHERE user_id = $1", complainer_id
    )
    complainee_profile = await conn.fetchrow(
        "SELECT * FROM behavior_profiles WHERE user_id = $1", complainee_id
    )

    trip_dict = dict(trip)
    for key in ("optimal_route_geometry", "actual_route_geometry", "gps_trace"):
        trip_dict[key] = _loads(trip_dict.get(key))

    payment_dict = dict(payment) if payment else None
    if payment_dict is not None:
        payment_dict["add_on_fees"] = _loads(payment_dict.get("add_on_fees")) or []

    return TripBundle(
        trip=trip_dict,
        payment=payment_dict,
        chat_messages=[dict(r) for r in chat_messages],
        traffic_events=[dict(r) for r in traffic_events],
        evidence=[dict(r) for r in evidence],
        complainer=dict(complainer) if complainer else {},
        complainee=dict(complainee) if complainee else {},
        complainer_profile=dict(complainer_profile) if complainer_profile else None,
        complainee_profile=dict(complainee_profile) if complainee_profile else None,
    )
