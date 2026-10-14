"""Navigation endpoints for the demo UI: pick a persona, see their trips, see their
cases. There's no real auth, just a persona picker (system design §3)."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.data.db import get_connection
from app.data.demo import (
    featured_case_id,
    get_trip_detail,
    list_personas,
    list_user_cases,
    list_user_trips,
    pick_scenario,
    system_stats,
)
from app.rules.prevention import CLAIM_WINDOW_DAYS
from app.tools.policy_rag import policy_clauses

router = APIRouter(tags=["demo"])

_CATEGORIES = "^(route_deviation|no_show_charge|property_damage|safety_incident)$"


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no {what} {value!r}") from exc


def _user_id(user_id: str) -> uuid.UUID:
    return _uuid(user_id, "user")


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


@router.get("/trips/{trip_id}")
async def trip_detail(trip_id: str) -> dict:
    """One trip as its rider and driver see it before any dispute: the map, both
    parties, the receipt, and the case on it if there is one."""
    tid = _uuid(trip_id, "trip")
    conn = await get_connection()
    try:
        trip = await get_trip_detail(conn, tid)
    finally:
        await conn.close()
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no trip {trip_id!r}")
    return trip


@router.get("/stats")
async def stats() -> dict:
    """What the system has done so far: cases, automation rate, time to decision,
    escalation reasons. Computed from the case and trace tables, not estimated."""
    conn = await get_connection()
    try:
        return await system_stats(conn)
    finally:
        await conn.close()


@router.get("/demo/scenario")
async def demo_scenario(
    category: str = Query(..., pattern=_CATEGORIES),
    role: str | None = Query(None, pattern="^(rider|driver)$"),
) -> dict:
    """One unclaimed trip that fits `category`, plus who would file it (`role` picks the
    filer instead of the usual one). Backs the landing page's "run a demo case" buttons."""
    conn = await get_connection()
    try:
        scenario = await pick_scenario(conn, category, role)
    finally:
        await conn.close()
    if scenario is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no unclaimed {category} trips left; regenerate the demo data",
        )
    return scenario


@router.get("/demo/featured")
async def featured() -> dict:
    """The case whose hearing the landing page shows, or null if none is ready yet."""
    conn = await get_connection()
    try:
        return {"case_id": await featured_case_id(conn)}
    finally:
        await conn.close()


@router.get("/policy/{policy_id}")
async def policy_text(policy_id: str) -> list[dict]:
    """The clauses of one policy section (e.g. POL-02), from the same corpus Policy RAG
    searches, so a cited policy can be read in full."""
    clauses = policy_clauses(policy_id)
    if not clauses:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no policy {policy_id!r}")
    return [c.model_dump() for c in clauses]


@router.get("/demo/sample-photo")
async def sample_photo(
    tier: str = Query("minor", pattern="^(none|minor|moderate|severe)$"),
    seed: int = Query(0, ge=0, le=10_000),
) -> Response:
    """A synthetic rear-seat photo for demos: clean, a coffee spill, mud, or vomit. Lets
    the claim form attach a photo whose contents Image Analysis can actually grade, and
    show what happens when the photo doesn't match the claim."""
    from data_generation.pipeline.photo_render import render_seat_photo

    data = await asyncio.to_thread(render_seat_photo, tier, seed)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})
