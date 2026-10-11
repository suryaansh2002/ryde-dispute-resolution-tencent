"""Retry an agent run on provider rate limits and transient server errors.

Groq's on-demand tier caps tokens per minute; parallel cases (two advocates at once, or
several cases filed together, or a golden run) can saturate it for a minute at a time, so
the backoff runs to about two minutes in total before giving up.
Retrying the whole run is safe: agent runs have no side effects outside the run.
"""

import asyncio
import random
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 8


async def run_agent(agent: Agent[Any, Any], *args: Any, **kwargs: Any) -> Any:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return await agent.run(*args, **kwargs)
        except ModelHTTPError as exc:
            if exc.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise
            await asyncio.sleep(min(2 ** attempt, 30) + random.random())
    raise AssertionError("unreachable")
