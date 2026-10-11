"""End-to-end smoke test: real Postgres, real Groq, real HTTP.

Seeds three controlled scenarios, one per category, then drives each through the live
API: file the claim, have the other party respond, fetch the decision. Prints the result.
Deletes everything it created unless --keep is passed.

Scenarios and what the policy says should happen:
  route_deviation  ~19% extra distance, no traffic event   -> upheld, partial refund
                   (10–25% tier, merit 0.5)
  no_show_charge   driver never within 100m of pickup,       -> upheld (fee waived), but the
                   driver is a repeat filer (3 disputes)        repeat-filer bucket escalates it
  property_damage  driver's spill photo, minor tier          -> upheld, $40 cleaning fee

Run from backend/ with the server up:
  uv run uvicorn app.main:app --port 8000 &
  uv run python -m scripts.smoke_e2e --base-url http://localhost:8000
"""

import argparse
import asyncio
import json
import random
from datetime import UTC, datetime, timedelta

import httpx

import app.config  # noqa: F401 — loads .env
from app.config import settings
from app.data.db import get_connection
from app.tools.object_storage import _client, upload_object
from data_generation.pipeline.geo import interpolate_gps_trace, perturb_route

START = (1.3521, 103.8198)
END = (1.3721, 103.8468)
OPTIMAL = {"type": "LineString", "coordinates": [[START[1], START[0]], [END[1], END[0]]]}
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000100ffff03000006000557bfabd4000000"
    "0049454e44ae426082"
)


async def _user(conn, role, name, disputes_30d=0):
    uid = await conn.fetchval(
        "INSERT INTO users (role, display_name, rating, rating_trend) "
        "VALUES ($1,$2,4.7,0.0) RETURNING id", role, name,
    )
    await conn.execute(
        "INSERT INTO behavior_profiles (user_id, dispute_count_30d, upheld_count, "
        "denied_count, rating_trend, account_age_days) VALUES ($1,$2,0,0,0.0,400)",
        uid, disputes_30d,
    )
    return uid


async def _trip(conn, rider, driver, *, actual, gps, pickup=START, add_on=None,
                fare=(14.50, 1.25, 1.10)):
    completed = datetime.now(UTC) - timedelta(hours=2)
    scheduled = completed - timedelta(minutes=22)
    trip_id = await conn.fetchval(
        """INSERT INTO trips (rider_id, driver_id, pickup_lat, pickup_lng, dropoff_lat,
               dropoff_lng, optimal_route_geometry, actual_route_geometry, gps_trace,
               scheduled_at, completed_at, category_hint)
           VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb,$10,$11,'smoke')
           RETURNING id""",
        rider, driver, pickup[0], pickup[1], END[0], END[1], json.dumps(OPTIMAL),
        json.dumps(actual), json.dumps(gps(scheduled, completed)), scheduled, completed,
    )
    base, platform, taxes = fare
    add_on = add_on or []
    total = round(base + platform + taxes + sum(f["amount"] for f in add_on), 2)
    await conn.execute(
        "INSERT INTO payments (trip_id, base_fare, platform_fee, taxes, total_fare, "
        "add_on_fees) VALUES ($1,$2,$3,$4,$5,$6::jsonb)",
        trip_id, base, platform, taxes, total, json.dumps(add_on),
    )
    return trip_id, scheduled


async def _chat(conn, trip_id, at, lines):
    for i, (role, text) in enumerate(lines):
        await conn.execute(
            "INSERT INTO chat_messages (trip_id, sender_role, timestamp, text) "
            "VALUES ($1,$2,$3,$4)", trip_id, role, at + timedelta(minutes=2 + i), text,
        )


async def seed() -> tuple[list[dict], dict]:
    created: dict = {"users": [], "trips": [], "objects": []}
    scenarios = []
    rng = random.Random(7)
    conn = await get_connection()
    try:
        # 1. Route deviation: perturbation param 0.35 measures ~19% extra; no traffic
        #    event; rider files.
        rider = await _user(conn, "rider", "Smoke Rider A")
        driver = await _user(conn, "driver", "Smoke Driver A")
        actual = perturb_route(OPTIMAL, 0.35, rng)
        trip, at = await _trip(conn, rider, driver, actual=actual,
                               gps=lambda s, e: interpolate_gps_trace(actual, s, e, 120))
        await _chat(conn, trip, at, [
            ("rider", "Why are we going this way? This is much longer than the app route."),
            ("driver", "There was a road closure, had to go around."),
        ])
        created["users"] += [rider, driver]
        created["trips"].append(trip)
        scenarios.append({
            "name": "route_deviation", "trip_id": str(trip), "complainer": str(rider),
            "respondent": str(driver), "category": "route_deviation",
            "claim": "The driver took a much longer route than necessary and I was charged "
                     "extra. There was no reason for the detour.",
            "response": "There was a road closure on the normal route, so I went around.",
            "evidence": [],
        })

        # 2. No-show: driver's GPS never comes within 100m of pickup; driver is a repeat
        #    filer (3 disputes in 30 days) -> repeat-filer bucket.
        rider = await _user(conn, "rider", "Smoke Rider B")
        driver = await _user(conn, "driver", "Smoke Driver B", disputes_30d=3)
        away = (START[0] + 0.006, START[1] + 0.006)  # ~940m away
        trip, at = await _trip(
            conn, rider, driver, actual=OPTIMAL,
            gps=lambda s, e: [{"lat": away[0], "lng": away[1],
                               "t": (s + timedelta(minutes=m)).isoformat()} for m in (0, 4, 8)],
            add_on=[{"type": "no_show_fee", "amount": 4.50}], fare=(0.0, 0.0, 0.0),
        )
        await _chat(conn, trip, at, [
            ("driver", "I'm here"),
            ("rider", "I'm standing at the pickup pin and I don't see you anywhere."),
        ])
        created["users"] += [rider, driver]
        created["trips"].append(trip)
        scenarios.append({
            "name": "no_show_charge", "trip_id": str(trip), "complainer": str(rider),
            "respondent": str(driver), "category": "no_show_charge",
            "claim": "The driver never came to the pickup point. I waited and was still "
                     "charged a no-show fee.",
            "response": "I was at the pickup and waited, the rider never came out.",
            "evidence": [],
        })

        # 3. Property damage: driver files with a spill photo (minor tier).
        rider = await _user(conn, "rider", "Smoke Rider C")
        driver = await _user(conn, "driver", "Smoke Driver C")
        trip, at = await _trip(conn, rider, driver, actual=OPTIMAL,
                               gps=lambda s, e: interpolate_gps_trace(OPTIMAL, s, e, 120))
        await _chat(conn, trip, at, [
            ("driver", "You spilled your drink all over the back seat."),
            ("rider", "Sorry, it was an accident."),
        ])
        key = f"evidence/smoke-{trip}/spill.png"
        hash_ = upload_object(key, _PLACEHOLDER_PNG, "image/png")
        created["users"] += [rider, driver]
        created["trips"].append(trip)
        created["objects"].append(key)
        scenarios.append({
            "name": "property_damage", "trip_id": str(trip), "complainer": str(driver),
            "respondent": str(rider), "category": "property_damage",
            "claim": "The rider spilled a drink on the back seat and it needs cleaning. "
                     "Photo attached.",
            "response": "It was a small spill from my coffee, I apologised.",
            "evidence": [{"kind": "photo", "hash": hash_, "object_key": key}],
        })
    finally:
        await conn.close()
    return scenarios, created


async def leftover_smoke_data() -> dict:
    """Everything a previous run left behind (crashed, or run with --keep)."""
    conn = await get_connection()
    try:
        rows = await conn.fetch(
            "SELECT id, rider_id, driver_id FROM trips WHERE category_hint = 'smoke'")
    finally:
        await conn.close()
    keys = [o["Key"] for o in _client().list_objects_v2(
        Bucket=settings.object_storage_bucket, Prefix="evidence/smoke-").get("Contents", [])]
    return {
        "trips": [r["id"] for r in rows],
        "users": list({u for r in rows for u in (r["rider_id"], r["driver_id"])}),
        "objects": keys,
    }


async def cleanup(created: dict) -> None:
    conn = await get_connection()
    try:
        trips = created["trips"]
        case_ids = [r["id"] for r in await conn.fetch(
            "SELECT id FROM cases WHERE trip_id = ANY($1::uuid[])", trips)]
        for table in ("trace_events", "decisions", "responses", "evidence"):
            await conn.execute(f"DELETE FROM {table} WHERE case_id = ANY($1::text[])", case_ids)
        await conn.execute("DELETE FROM cases WHERE id = ANY($1::text[])", case_ids)
        for table in ("chat_messages", "payments"):
            await conn.execute(f"DELETE FROM {table} WHERE trip_id = ANY($1::uuid[])", trips)
        await conn.execute("DELETE FROM trips WHERE id = ANY($1::uuid[])", trips)
        await conn.execute(
            "DELETE FROM behavior_profiles WHERE user_id = ANY($1::uuid[])", created["users"])
        await conn.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", created["users"])
    finally:
        await conn.close()
    for key in created["objects"]:
        _client().delete_object(Bucket=settings.object_storage_bucket, Key=key)


def run_scenario(client: httpx.Client, s: dict) -> dict:
    filed = client.post("/cases", json={
        "trip_id": s["trip_id"], "complainer_id": s["complainer"], "category": s["category"],
        "claim_text": s["claim"], "evidence": s["evidence"],
    })
    filed.raise_for_status()
    case_id, state = filed.json()["case_id"], filed.json()["state"]
    if state != "awaiting_response":
        return {"case_id": case_id, "state": state, "detail": filed.json()["detail"]}
    resp = client.post(f"/cases/{case_id}/response",
                       json={"respondent_id": s["respondent"], "text": s["response"]})
    resp.raise_for_status()
    decision = client.get(f"/cases/{case_id}/decision")
    decision.raise_for_status()
    return {**resp.json(), "fetched": decision.json()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--keep", action="store_true", help="don't delete the seeded data")
    parser.add_argument("--cleanup-only", action="store_true",
                        help="delete data left by earlier --keep or crashed runs, then exit")
    args = parser.parse_args()

    if args.cleanup_only:
        leftovers = asyncio.run(leftover_smoke_data())
        asyncio.run(cleanup(leftovers))
        trips, objects = len(leftovers["trips"]), len(leftovers["objects"])
        print(f"removed {trips} smoke trips and {objects} objects")
        return

    scenarios, created = asyncio.run(seed())
    ok = True
    try:
        with httpx.Client(base_url=args.base_url, timeout=300) as client:
            for s in scenarios:
                print(f"\n=== {s['name']} ===")
                try:
                    r = run_scenario(client, s)
                except httpx.HTTPError as exc:
                    ok = False
                    body = getattr(getattr(exc, "response", None), "text", "")
                    print(f"FAILED: {exc} {body[:500]}")
                    continue
                if "decision" not in r:
                    ok = False
                    print(f"stopped at {r['state']}: {r.get('detail')}")
                    continue
                d = r["decision"]
                print(f"case {r['case_id']} -> {r['state']}")
                print(f"outcome={d['outcome']} remedy={d['remedy']} "
                      f"confidence={d['confidence']} policy={d['policy_applied']}")
                print(f"escalation={d['escalation']}")
                print(f"rider advocate ({r['rider_argument']['confidence']}): "
                      f"{r['rider_argument']['text']}")
                print(f"driver advocate ({r['driver_argument']['confidence']}): "
                      f"{r['driver_argument']['text']}")
                print(r["document"])
                assert r["fetched"]["decision"] == d, "GET /decision disagrees with response"
    finally:
        if not args.keep:
            asyncio.run(cleanup(created))
            print("cleaned up seeded data")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
