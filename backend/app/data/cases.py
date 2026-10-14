"""Case-level Postgres access for the orchestrator (plain deterministic code, not an
agent — the "Orchestrator -> PG" edge in system design §2, distinct from
`app/data/db.py`'s `TripBundle`, which only the Evidence Collection Agent touches).
"""

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from app.schemas import CaseFile, DecisionObject
from app.schemas.common import CaseRole, DisputeCategory
from app.schemas.trace import AgentName, TraceEvent, TraceEventKind

TRACE_CHANNEL = "trace_events"


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
    claim_text: str | None = None,
) -> str:
    case_id = await conn.fetchval(
        """INSERT INTO cases (trip_id, complainer_id, complainee_id, category, state, claim_text)
           VALUES ($1, $2, $3, $4, 'opened', $5) RETURNING id""",
        trip_id, complainer_id, complainee_id, category.value, claim_text,
    )
    return case_id


async def save_case_file(conn: asyncpg.Connection, case_id: str, case_file: CaseFile) -> None:
    await conn.execute(
        "UPDATE cases SET case_file = $2::jsonb, updated_at = now() WHERE id = $1",
        case_id, case_file.model_dump_json(),
    )


async def save_case_file_if_absent(
    conn: asyncpg.Connection, case_id: str, case_file: CaseFile
) -> bool:
    """Stores the case file only if the case has none yet; False if one was already there
    (two reviewers pressing "Prepare case file" at once keep the first). Leaves
    `updated_at` alone: preparing evidence isn't case activity, so the L2 queue order holds."""
    row = await conn.fetchval(
        """UPDATE cases SET case_file = $2::jsonb
           WHERE id = $1 AND case_file IS NULL RETURNING id""",
        case_id, case_file.model_dump_json(),
    )
    return row is not None


def load_case_file(case_row: dict[str, Any]) -> CaseFile | None:
    raw = case_row.get("case_file")
    if raw is None:
        return None
    if isinstance(raw, str):
        return CaseFile.model_validate_json(raw)
    return CaseFile.model_validate(raw)


async def insert_response(
    conn: asyncpg.Connection, case_id: str, respondent_id: str, text: str
) -> str:
    return str(await conn.fetchval(
        """INSERT INTO responses (case_id, respondent_id, text)
           VALUES ($1, $2, $3) RETURNING id""",
        case_id, respondent_id, text,
    ))


async def get_latest_response(conn: asyncpg.Connection, case_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        "SELECT * FROM responses WHERE case_id = $1 ORDER BY submitted_at DESC LIMIT 1", case_id
    )
    return dict(row) if row else None


async def insert_decision(conn: asyncpg.Connection, decision: DecisionObject) -> None:
    await conn.execute(
        """INSERT INTO decisions (case_id, outcome, remedy, reasoning, policy_applied,
               confidence, escalation, human_ratified, ratified_by)
           VALUES ($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7::jsonb, $8, $9)""",
        decision.case_id, decision.outcome, decision.remedy.model_dump_json(),
        json.dumps([f.model_dump(mode="json") for f in decision.reasoning]),
        decision.policy_applied, decision.confidence, decision.escalation.model_dump_json(),
        decision.human_ratified, decision.ratified_by,
    )


async def get_latest_decision(conn: asyncpg.Connection, case_id: str) -> DecisionObject | None:
    row = await conn.fetchrow(
        "SELECT * FROM decisions WHERE case_id = $1 ORDER BY created_at DESC LIMIT 1", case_id
    )
    if row is None:
        return None

    def _j(v):
        return json.loads(v) if isinstance(v, str) else v

    return DecisionObject(
        case_id=row["case_id"], outcome=row["outcome"], remedy=_j(row["remedy"]),
        reasoning=_j(row["reasoning"]), policy_applied=row["policy_applied"],
        confidence=float(row["confidence"]), escalation=_j(row["escalation"]),
        human_ratified=row["human_ratified"], ratified_by=row["ratified_by"],
    )


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
    # Wakes any open SSE stream (app/sse/stream.py). The stream re-reads from the table,
    # so the payload is just a hint and a missed notification costs only a short delay.
    await conn.execute("SELECT pg_notify($1, $2)", TRACE_CHANNEL, f"{case_id}:{row_id}")
    return event.model_copy(update={"id": row_id})


def trace_emitter(conn: asyncpg.Connection):
    """State-machine emit hook that writes each transition to `trace_events`."""
    async def emit(event: TraceEvent) -> None:
        await record_trace_event(conn, event.case_id, event.kind, detail=event.detail)
    return emit


async def list_l2_queue(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """Cases waiting on a human: escalated by the gate, or safety-bypassed at intake.
    Safety first, then oldest first."""
    rows = await conn.fetch(
        """SELECT c.id, c.state, c.category, c.tier, c.is_safety, c.created_at, c.updated_at,
                  c.claim_text,
                  complainer.display_name AS complainer_name, complainer.role AS complainer_role,
                  complainee.display_name AS complainee_name,
                  d.outcome, d.remedy, d.confidence, d.escalation, d.policy_applied
           FROM cases c
           JOIN users complainer ON complainer.id = c.complainer_id
           JOIN users complainee ON complainee.id = c.complainee_id
           LEFT JOIN LATERAL (
               SELECT * FROM decisions WHERE case_id = c.id ORDER BY created_at DESC LIMIT 1
           ) d ON true
           WHERE c.state IN ('escalated', 'safety_bypassed')
           ORDER BY (c.state = 'safety_bypassed') DESC, c.updated_at"""
    )
    queue = []
    for r in rows:
        item = dict(r)
        for key in ("remedy", "escalation"):
            if isinstance(item[key], str):
                item[key] = json.loads(item[key])
        if item["confidence"] is not None:
            item["confidence"] = float(item["confidence"])
        queue.append(item)
    return queue


_CASE_SUMMARY = """
SELECT c.id, c.trip_id, c.state, c.category, c.tier, c.is_safety, c.created_at, c.updated_at,
       c.complainer_id, complainer.display_name AS complainer_name,
       complainer.role AS complainer_role,
       c.complainee_id, complainee.display_name AS complainee_name
FROM cases c
JOIN users complainer ON complainer.id = c.complainer_id
JOIN users complainee ON complainee.id = c.complainee_id
"""


async def list_recent_cases(conn: asyncpg.Connection, limit: int) -> list[dict[str, Any]]:
    rows = await conn.fetch(_CASE_SUMMARY + " ORDER BY c.updated_at DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


async def get_case_view(conn: asyncpg.Connection, case_id: str) -> dict[str, Any] | None:
    """Case summary + names + claim text + the latest response, for the UI. The raw
    case row (with the full case file) stays behind GET /cases/{id}."""
    row = await conn.fetchrow(
        _CASE_SUMMARY.replace("SELECT c.id,", "SELECT c.claim_text, c.id,") + " WHERE c.id = $1",
        case_id,
    )
    if row is None:
        return None
    view = dict(row)
    response = await get_latest_response(conn, case_id)
    view["response"] = (
        {"text": response["text"], "submitted_at": response["submitted_at"]} if response else None
    )
    extra = await conn.fetchrow(_CASE_VIEW_TRIP, case_id)
    view["trip"] = {
        "scheduled_at": extra["scheduled_at"], "completed_at": extra["completed_at"],
        "total_fare": float(extra["total_fare"]) if extra["total_fare"] is not None else None,
    }
    view["has_case_file"] = extra["has_case_file"]
    return view


# The trip times and fare the party screens show next to the case, and whether evidence
# has been assembled yet (safety cases have none until a reviewer prepares it).
_CASE_VIEW_TRIP = """
SELECT t.scheduled_at, t.completed_at, (c.case_file IS NOT NULL) AS has_case_file,
       (SELECT p.total_fare FROM payments p WHERE p.trip_id = t.id ORDER BY p.id LIMIT 1)
           AS total_fare
FROM cases c JOIN trips t ON t.id = c.trip_id
WHERE c.id = $1
"""


async def first_trace_time(
    conn: asyncpg.Connection, case_id: str, kind: TraceEventKind, detail_prefix: str
) -> datetime | None:
    """When a given trace event was first recorded for a case, or None."""
    return await conn.fetchval(
        """SELECT t FROM trace_events
           WHERE case_id = $1 AND kind = $2 AND detail LIKE $3 || '%'
           ORDER BY id LIMIT 1""",
        case_id, kind.value, detail_prefix,
    )
