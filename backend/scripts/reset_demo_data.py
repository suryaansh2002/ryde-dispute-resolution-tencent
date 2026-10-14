"""Wipe the demo dataset so it can be regenerated: every user, trip, case, decision,
trace event, golden case and usage row. Keeps `policy_chunks` (the policy corpus).
Restarts the CASE-/EV-/MSG- id sequences, so new ids start at 0001.

The database is shared: everyone on this Neon branch (both devs, the Render deploy) loses
their cases. Evidence files in object storage are left alone (unreferenced, harmless).

Run from backend/, then regenerate:
  uv run python -m scripts.reset_demo_data --yes
  uv run python -m data_generation.pipeline.generate --count 200 --seed 42
"""

import argparse
import asyncio

import app.config  # noqa: F401 — loads .env
from app.data.db import connect_direct

TABLES = [
    "llm_usage", "trace_events", "decisions", "responses", "evidence", "golden_cases", "cases",
    "chat_messages", "payments", "traffic_events", "behavior_profiles", "trips", "users",
]
SEQUENCES = ["case_id_seq", "evidence_id_seq", "chat_message_id_seq"]


async def reset() -> None:
    conn = await connect_direct()
    try:
        counts = {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in TABLES}
        print("deleting:", counts)
        async with conn.transaction():
            await conn.execute(f"TRUNCATE {', '.join(TABLES)} CASCADE")
            for seq in SEQUENCES:
                await conn.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1")
        kept = await conn.fetchval("SELECT count(*) FROM policy_chunks")
        print(f"done; policy_chunks kept: {kept}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm the wipe")
    if not parser.parse_args().yes:
        raise SystemExit("refusing to wipe without --yes (see the module docstring)")
    asyncio.run(reset())


if __name__ == "__main__":
    main()
