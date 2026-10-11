"""Synthetic dataset generation pipeline (data sources doc §4, steps 1-9 + 11).

Run from `backend/`: `uv run python -m data_generation.pipeline.generate --count 200`

Step 10 (Property Damage photos) is handled separately per golden case in
`golden_cases.py`, since real evidence rows need a filed case to attach to — see that
module's docstring for why. This script only produces the underlying trips/payments/
chat/traffic_events/users/behavior_profiles data plus golden-case labels; filing an
actual claim against any of it (golden or ad hoc) goes through the real `POST /cases`
API, not through this offline pipeline.
"""

import argparse
import asyncio
import random
from datetime import UTC, datetime, timedelta

import asyncpg

from app.data.db import get_connection
from data_generation.pipeline.categories import (
    ROUTE_DEVIATION_EXTRA_FRACTIONS,
    CategoryHint,
    assign_category_hints,
)
from data_generation.pipeline.chat import generate_chat_and_claim
from data_generation.pipeline.fares import (
    apply_no_show_fee,
    generate_fare,
)
from data_generation.pipeline.geo import (
    interpolate_gps_trace,
    perturb_route,
    route_length_km,
    sample_pickup_dropoff,
)
from data_generation.pipeline.golden_cases import label_golden_cases
from data_generation.pipeline.onemap import get_route
from data_generation.pipeline.photos import SEVERITY_TIERS
from data_generation.pipeline.traffic_events import maybe_generate_traffic_event
from data_generation.pipeline.users import generate_behavior_profile, generate_user


async def _insert_user(conn: asyncpg.Connection, user: dict) -> str:
    return await conn.fetchval(
        """INSERT INTO users (role, display_name, rating, rating_trend)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        user["role"], user["display_name"], user["rating"], user["rating_trend"],
    )


async def _insert_profile(conn: asyncpg.Connection, user_id: str, profile: dict) -> None:
    await conn.execute(
        """INSERT INTO behavior_profiles
               (user_id, dispute_count_30d, upheld_count, denied_count,
                rating_trend, account_age_days)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        user_id, profile["dispute_count_30d"], profile["upheld_count"], profile["denied_count"],
        profile["rating_trend"], profile["account_age_days"],
    )


async def generate_dataset(
    count: int, *, seed: int | None = None, golden_fraction: float = 0.2
) -> dict:
    rng = random.Random(seed)
    conn = await get_connection()
    try:
        hints = assign_category_hints(count, rng)
        # A fixed pool of riders and drivers who each take several trips, rather than a
        # fresh pair per trip, so personas have trip histories worth clicking through.
        # A handful are deliberate repeat-filers / adverse-rating profiles (data sources
        # doc §4 step 9) so Prevention Rule 5 and the Judge's reasoning have signal.
        taken_names: set[str] = set()
        pools: dict[str, list[str]] = {"rider": [], "driver": []}
        pool_sizes = {"rider": max(8, count // 5), "driver": max(5, count // 8)}
        repeat_rate = {"rider": 0.12, "driver": 0.08}
        for role, size in pool_sizes.items():
            for _ in range(size):
                user_id = await _insert_user(conn, generate_user(role, rng, taken_names))
                await _insert_profile(conn, user_id, generate_behavior_profile(
                    rng, force_repeat_filer=rng.random() < repeat_rate[role],
                    force_adverse_rating=rng.random() < 0.1,
                ))
                pools[role].append(user_id)

        trip_ids: list[str] = []
        golden_candidates: list[dict] = []

        for hint in hints:
            rider_id = rng.choice(pools["rider"])
            driver_id = rng.choice(pools["driver"])

            pickup, dropoff = sample_pickup_dropoff(rng)
            optimal = get_route(pickup, dropoff)
            distance_km = route_length_km(optimal)

            scheduled_at = datetime.now(UTC) - timedelta(
                days=rng.randint(0, 25), hours=rng.randint(0, 23)
            )
            duration_min = max(8, int(distance_km * rng.uniform(2.0, 3.0)))
            completed_at = scheduled_at + timedelta(minutes=duration_min)

            is_route_deviation = hint == CategoryHint.ROUTE_DEVIATION
            justified = is_route_deviation and rng.random() < 0.4
            extra_fraction = (
                rng.choice(ROUTE_DEVIATION_EXTRA_FRACTIONS) if is_route_deviation else 0.0
            )
            actual = perturb_route(optimal, extra_fraction, rng) if is_route_deviation else optimal
            # perturb_route's displacement is approximate (asking for 35% can yield ~19%), so
            # golden labels use the *measured* extra distance — the same number the agents
            # see in ROUTE-COMPARISON — not the requested one.
            measured_extra = (
                route_length_km(actual) / distance_km - 1 if is_route_deviation else 0.0
            )

            traffic_event = maybe_generate_traffic_event(
                pickup, scheduled_at, completed_at, rng, justified=justified
            ) if is_route_deviation else None

            gps_trace = interpolate_gps_trace(actual, scheduled_at, completed_at)

            fare = generate_fare(distance_km, rng)
            if hint == CategoryHint.NO_SHOW_CHARGE:
                fare = apply_no_show_fee(fare)
                # No-show trips: driver's trace never reaches the pickup (data sources
                # doc §4 step 6) — overwrite the trace with points well outside the
                # 100m radius throughout, rather than along the real route at all.
                gps_trace = [
                    {"lat": pickup[0] + 0.01, "lng": pickup[1] + 0.01, "t": p["t"]}
                    for p in gps_trace
                ]

            trip_id = await conn.fetchval(
                """INSERT INTO trips
                       (rider_id, driver_id, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng,
                        optimal_route_geometry, actual_route_geometry, gps_trace,
                        scheduled_at, completed_at, category_hint)
                   VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb,$10,$11,$12)
                   RETURNING id""",
                rider_id, driver_id, pickup[0], pickup[1], dropoff[0], dropoff[1],
                _dumps(optimal), _dumps(actual), _dumps(gps_trace),
                scheduled_at, completed_at, hint.value,
            )
            await conn.execute(
                """INSERT INTO payments
                       (trip_id, base_fare, platform_fee, taxes, total_fare, add_on_fees)
                   VALUES ($1,$2,$3,$4,$5,$6::jsonb)""",
                trip_id, fare["base_fare"], fare["platform_fee"], fare["taxes"], fare["total_fare"],
                _dumps(fare["add_on_fees"]),
            )
            if traffic_event:
                await conn.execute(
                    """INSERT INTO traffic_events (near_lat, near_lng, time_window_start,
                           time_window_end, type, description)
                       VALUES ($1,$2,$3,$4,$5,$6)""",
                    traffic_event["near_lat"], traffic_event["near_lng"],
                    traffic_event["time_window_start"], traffic_event["time_window_end"],
                    traffic_event["type"], traffic_event["description"],
                )

            # Who plausibly files each category: riders dispute routes, drivers claim damage;
            # either side can raise a no-show or a safety incident.
            complainer_role = {
                CategoryHint.ROUTE_DEVIATION: "rider",
                CategoryHint.PROPERTY_DAMAGE: "driver",
            }.get(hint) or rng.choice(["rider", "driver"])  # unused for CLEAN trips
            severity = rng.choice(SEVERITY_TIERS)
            if hint != CategoryHint.CLEAN:
                chat_lines, claim_text = generate_chat_and_claim(
                    _dispute_category(hint), complainer_role, rng,
                    traffic_event_exists=traffic_event is not None, severity=severity,
                )
                for line in chat_lines:
                    await conn.execute(
                        """INSERT INTO chat_messages (trip_id, sender_role, timestamp, text)
                           VALUES ($1,$2,$3,$4)""",
                        trip_id, line["sender_role"],
                        scheduled_at + timedelta(minutes=1), line["text"],
                    )
                complainer_id = rider_id if complainer_role == "rider" else driver_id
                golden_candidates.append({
                    "trip_id": trip_id, "hint": hint, "complainer_id": complainer_id,
                    "complainer_role": complainer_role, "claim_text": claim_text,
                    "extra_fraction": measured_extra, "justified": justified, "severity": severity,
                    "pickup": pickup, "gps_trace": gps_trace,
                })

            trip_ids.append(trip_id)

        n_golden = max(1, int(len(golden_candidates) * golden_fraction))
        golden_selected = rng.sample(golden_candidates, min(n_golden, len(golden_candidates)))
        golden_ids = await label_golden_cases(conn, golden_selected, rng)

        return {
            "trips_generated": len(trip_ids),
            "golden_cases_labeled": len(golden_ids),
            "category_breakdown": {h.value: hints.count(h) for h in CategoryHint},
        }
    finally:
        await conn.close()


def _dumps(value) -> str:
    import json
    return json.dumps(value)


def _dispute_category(hint: CategoryHint):
    from app.schemas.common import DisputeCategory
    return DisputeCategory(hint.value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    result = asyncio.run(generate_dataset(args.count, seed=args.seed))
    print(result)


if __name__ == "__main__":
    main()
