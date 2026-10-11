"""Retry an agent run on provider rate limits and transient server errors.

Groq's on-demand tier caps tokens per minute; parallel cases (two advocates at once, or
several cases filed together, or a golden run) can saturate it for a minute at a time, so
the backoff runs to about two minutes in total before giving up.
Retrying the whole run is safe: agent runs have no side effects outside the run.

Every successful run's token usage is recorded to `llm_usage` (app/data/usage.py).
"""

import asyncio
import random
import time
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from app.data.usage import record_usage

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 8


async def run_agent(agent: Agent[Any, Any], *args: Any, **kwargs: Any) -> Any:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            result = await agent.run(*args, **kwargs)
        except ModelHTTPError as exc:
            if exc.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise
            await asyncio.sleep(min(2 ** attempt, 30) + random.random())
            continue
        await _record(agent, result, int((time.perf_counter() - started) * 1000))
        return result
    raise AssertionError("unreachable")


async def _record(agent: Agent[Any, Any], result: Any, latency_ms: int) -> None:
    usage = getattr(result, "usage", None)
    if callable(usage):  # a method in older pydantic-ai, a property in newer
        usage = usage()
    if usage is None:
        return
    await record_usage(
        agent.name or "agent",
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        requests=usage.requests or 1,
        tool_calls=usage.tool_calls or 0,
        latency_ms=latency_ms,
    )
