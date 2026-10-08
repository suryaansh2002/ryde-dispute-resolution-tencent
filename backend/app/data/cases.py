"""Case-level Postgres access for the orchestrator (plain deterministic code, not an
agent — the "Orchestrator -> PG" edge in system design §2, distinct from
`app/data/db.py`'s `TripBundle`, which only the Evidence Collection Agent touches).
"""

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.schemas.common import CaseRole, DisputeCategory
from app.schemas.trace import AgentName, TraceEvent, TraceEventKind


async def get_trip(conn: asyncpg.Connection, trip_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM trips WHERE id = $1", trip_id)
    return dict(row) if row else None


def trip_party_role(trip: dict[str, Any], user_id: str) -> CaseRole | None:
    if str(trip["rider_id"]) == user_id:
        return CaseRole.RIDER
    if str(trip["driver_id"]) == user_id:
        return CaseRole.DRIVER
    return None


def other_party_id(trip: dict[str, Any], complainer_role: CaseRole) -> str:
    return str(trip["driver_id"] if complainer_role == CaseRole.RIDER else trip["rider_id"])


async def has_open_or_decided_case(conn: asyncpg.Connection, trip_id: str) -> bool:
    row = await conn.fetchval(
        """SELECT 1 FROM cases
           WHERE trip_id = $1 AND state NOT IN ('declined_insufficient_evidence')
           LIMIT 1""",
        trip_id,
    )
    return row is not None


async def dispute_count_30d(conn: asyncpg.Connection, user_id: str) -> int:
    count = await conn.fetchval(
        """SELECT count(*) FROM cases
           WHERE (complainer_id = $1 OR complainee_id = $1)
             AND created_at >= now() - interval '30 days'""",
        user_id,
    )
    return int(count)


async def create_case(
    conn: asyncpg.Connection,
    trip_id: str,
    complainer_id: str,
    complainee_id: str,
    category: DisputeCategory,
) -> str:
    case_id = await conn.fetchval(
        """INSERT INTO cases (trip_id, complainer_id, complainee_id, category, state)
           VALUES ($1, $2, $3, $4, 'opened') RETURNING id""",
        trip_id, complainer_id, complainee_id, category.value,
    )
    return case_id


async def get_case_row(conn: asyncpg.Connection, case_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow("SELECT * FROM cases WHERE id = $1", case_id)
    return dict(row) if row else None


async def update_case(
    conn: asyncpg.Connection, case_id: str, *, state: str, category: str | None = None,
    tier: str | None = None, is_safety: bool | None = None,
) -> None:
    await conn.execute(
        """UPDATE cases SET state = $2,
               category = COALESCE($3, category),
               tier = COALESCE($4, tier),
               is_safety = COALESCE($5, is_safety),
               updated_at = now()
           WHERE id = $1""",
        case_id, state, category, tier, is_safety,
    )


async def insert_evidence(
    conn: asyncpg.Connection, case_id: str, kind: str, hash_: str, object_key: str,
    submitted_by: str | None,
) -> str:
    return await conn.fetchval(
        """INSERT INTO evidence (case_id, kind, hash, object_key, submitted_by)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        case_id, kind, hash_, object_key, submitted_by,
    )


async def has_evidence(conn: asyncpg.Connection, case_id: str) -> bool:
    row = await conn.fetchval("SELECT 1 FROM evidence WHERE case_id = $1 LIMIT 1", case_id)
    return row is not None


async def record_trace_event(
    conn: asyncpg.Connection,
    case_id: str,
    kind: TraceEventKind,
    *,
    agent: AgentName | None = None,
    detail: str | None = None,
    latency_ms: int | None = None,
    output: dict | None = None,
) -> TraceEvent:
    event = TraceEvent(
        t=datetime.now(UTC), kind=kind, case_id=case_id,
        agent=agent, detail=detail, latency_ms=latency_ms, output=output,
    )
    row_id = await conn.fetchval(
        """INSERT INTO trace_events (case_id, t, kind, agent, detail, latency_ms, output)
           VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) RETURNING id""",
        case_id, event.t, kind.value, agent.value if agent else None, detail, latency_ms,
        json.dumps(output) if output is not None else None,
    )
    return event.model_copy(update={"id": row_id})
