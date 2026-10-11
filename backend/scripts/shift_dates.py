"""Shift the whole synthetic timeline forward so the newest trip ended `--hours-ago`
hours ago (default 6).

The dataset is generated relative to the day it was generated, and claims are only
allowed within 30 days of a trip (Prevention Rule 6). Without this, golden cases and demo
trips age out of the window a few weeks after generation. Everything moves by the same
amount, so every relative fact the agents use (wait times, chat vs trip timing, traffic
windows) is unchanged: trips, GPS fixes, chat messages, traffic events.

Run from backend/:  uv run python -m scripts.shift_dates [--hours-ago 6] [--dry-run]
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta

from app.data.db import close_pools, get_connection


def _shift_trace(trace, delta: timedelta):
    out = []
    for p in trace:
        if "t" in p:
            p = {**p, "t": (datetime.fromisoformat(p["t"]) + delta).isoformat()}
        out.append(p)
    return out


async def main(hours_ago: float, dry_run: bool) -> None:
    conn = await get_connection()
    try:
        newest = await conn.fetchval("SELECT max(completed_at) FROM trips")
        delta = datetime.now(UTC) - timedelta(hours=hours_ago) - newest
        print(f"newest trip ended {newest}; shifting everything by {delta}")
        if dry_run or abs(delta) < timedelta(minutes=1):
            return
        async with conn.transaction():
            await conn.execute(
                "UPDATE trips SET scheduled_at = scheduled_at + $1, "
                "completed_at = completed_at + $1", delta,
            )
            await conn.execute("UPDATE chat_messages SET timestamp = timestamp + $1", delta)
            await conn.execute(
                "UPDATE traffic_events SET time_window_start = time_window_start + $1, "
                "time_window_end = time_window_end + $1", delta,
            )
            rows = await conn.fetch("SELECT id, gps_trace FROM trips WHERE gps_trace IS NOT NULL")
            for row in rows:
                trace = row["gps_trace"]
                trace = json.loads(trace) if isinstance(trace, str) else trace
                await conn.execute(
                    "UPDATE trips SET gps_trace = $2 WHERE id = $1",
                    row["id"], json.dumps(_shift_trace(trace, delta)),
                )
        print(f"shifted {len(rows)} trips")
    finally:
        await conn.close()
        await close_pools()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours-ago", type=float, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.hours_ago, args.dry_run))
