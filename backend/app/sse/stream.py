"""Live trace streaming over SSE (system design §3, §4, §7).

`trace_events` in Postgres is the source of truth; the stream is a live view of it, never
the other way round. Each open stream:
  1. replays every event after the client's Last-Event-ID (the trace row id), so a
     dropped connection resumes exactly where it left off;
  2. LISTENs on the `trace_events` channel. `record_trace_event` NOTIFYs on every
     insert, so new events arrive within a round trip;
  3. re-reads at least every few seconds anyway, so a missed notification only delays
     an event and never loses it.

The system design sketched an in-process asyncio.Queue instead. This version also works
across multiple workers or instances, and replay needs no extra code.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import asyncpg

from app.data.cases import TRACE_CHANNEL
from app.data.db import connect_direct

RECHECK_SECONDS = 5.0

Fetch = Callable[[asyncpg.Connection, int], Awaitable[list[dict[str, Any]]]]


def _event_row(row: asyncpg.Record) -> dict[str, Any]:
    event = dict(row)
    if isinstance(event.get("output"), str):
        event["output"] = json.loads(event["output"])
    event["t"] = event["t"].isoformat()
    return event


async def fetch_case_events(
    conn: asyncpg.Connection, case_id: str, after_id: int
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """SELECT id, case_id, t, kind, agent, detail, latency_ms, output
           FROM trace_events WHERE case_id = $1 AND id > $2 ORDER BY id""",
        case_id, after_id,
    )
    return [_event_row(r) for r in rows]


async def fetch_l2_events(conn: asyncpg.Connection, after_id: int) -> list[dict[str, Any]]:
    """Cases arriving in the L2 queue: escalated by the gate, or safety-bypassed at intake."""
    rows = await conn.fetch(
        """SELECT e.id, e.case_id, e.t, e.kind, e.detail, c.state, c.category, c.is_safety
           FROM trace_events e JOIN cases c ON c.id = e.case_id
           WHERE e.id > $1
             AND (e.kind = 'escalation'
                  OR (e.kind = 'state_transition' AND e.detail LIKE '%-> safety_bypassed'))
           ORDER BY e.id""",
        after_id,
    )
    return [_event_row(r) for r in rows]


async def tail(fetch: Fetch, after_id: int) -> AsyncIterator[dict[str, Any]]:
    """Yields sse-starlette event dicts: replay first, then live."""
    conn = await connect_direct()
    wake = asyncio.Event()

    def on_notify(*_: object) -> None:
        wake.set()

    await conn.add_listener(TRACE_CHANNEL, on_notify)
    last_id = after_id
    try:
        while True:
            # Clear before reading: a NOTIFY that lands while we read re-arms the wait.
            wake.clear()
            for event in await fetch(conn, last_id):
                last_id = event["id"]
                yield {"id": str(event["id"]), "data": json.dumps(event, default=str)}
            try:
                await asyncio.wait_for(wake.wait(), timeout=RECHECK_SECONDS)
            except TimeoutError:
                pass
    finally:
        await conn.remove_listener(TRACE_CHANNEL, on_notify)
        await conn.close()
