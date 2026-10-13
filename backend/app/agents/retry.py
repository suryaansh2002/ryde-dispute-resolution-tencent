"""Retry an agent run on provider rate limits and transient server errors.

Provider rate limits cap requests and tokens per minute; parallel cases (two advocates
at once, or several cases filed together, or a golden run) can saturate them for a minute
at a time, so the backoff runs to about two minutes in total before giving up. 529 is
Anthropic's "overloaded".
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

RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
MAX_ATTEMPTS = 8


def _daily_quota_exhausted(exc: ModelHTTPError) -> bool:
    """A per-day quota (e.g. OpenRouter's free tier: 50 requests a day) won't clear in the
    next two minutes, so backing off only makes the request look hung. Fail at once."""
    return exc.status_code == 429 and "per-day" in str(exc.body or "")


async def run_agent(agent: Agent[Any, Any], *args: Any, **kwargs: Any) -> Any:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        try:
            result = await agent.run(*args, **kwargs)
        except ModelHTTPError as exc:
            if (
                exc.status_code not in RETRY_STATUSES
                or attempt == MAX_ATTEMPTS
                or _daily_quota_exhausted(exc)
            ):
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
    # The model that actually answered: with OpenRouter fallbacks it may not be the
    # configured one.
    response = getattr(result, "response", None)
    await record_usage(
        agent.name or "agent",
        model=getattr(response, "model_name", None),
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        requests=usage.requests or 1,
        tool_calls=usage.tool_calls or 0,
        latency_ms=latency_ms,
    )
