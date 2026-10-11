"""Navigation endpoints for the demo UI: pick a persona, see their trips, see their
cases. There's no real auth, just a persona picker (system design §3)."""

import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, status

from app.data.db import get_connection
from app.data.demo import list_personas, list_user_cases, list_user_trips, system_stats
from app.rules.prevention import CLAIM_WINDOW_DAYS

router = APIRouter(tags=["demo"])


def _user_id(user_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no user {user_id!r}") from exc


@router.get("/demo/personas")
async def personas(
    role: str | None = Query(None, pattern="^(rider|driver)$"),
    limit: int = Query(20, ge=1, le=200),
) -> list[dict]:
    conn = await get_connection()
    try:
        return await list_personas(conn, role, limit)
    finally:
        await conn.close()


@router.get("/users/{user_id}/trips")
async def user_trips(user_id: str) -> list[dict]:
    uid = _user_id(user_id)
    conn = await get_connection()
    try:
        trips = await list_user_trips(conn, uid)
    finally:
        await conn.close()
    window_start = datetime.now(UTC) - timedelta(days=CLAIM_WINDOW_DAYS)
    for t in trips:
        if isinstance(t["add_on_fees"], str):
            t["add_on_fees"] = json.loads(t["add_on_fees"])
        t["total_fare"] = float(t["total_fare"]) if t["total_fare"] is not None else None
        completed = t["completed_at"]
        t["claimable"] = t["case_id"] is None and (completed is None or completed >= window_start)
    return trips


@router.get("/users/{user_id}/cases")
async def user_cases(user_id: str) -> list[dict]:
    uid = _user_id(user_id)
    conn = await get_connection()
    try:
        return await list_user_cases(conn, uid)
    finally:
        await conn.close()


@router.get("/stats")
async def stats() -> dict:
    """What the system has done so far: cases, automation rate, time to decision,
    escalation reasons. Computed from the case and trace tables, not estimated."""
    conn = await get_connection()
    try:
        return await system_stats(conn)
    finally:
        await conn.close()
