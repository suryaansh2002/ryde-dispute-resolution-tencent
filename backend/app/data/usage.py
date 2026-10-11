"""LLM usage accounting: one `llm_usage` row per model call (migrations/0002).

Which case a call belongs to comes from a context variable the orchestrator sets, so
agent code doesn't thread a case id through. Recording never breaks a case: a failed
write is logged and dropped.
"""

import contextvars
import logging

from app.config import settings
from app.data.db import get_connection

log = logging.getLogger(__name__)

current_case_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_case_id", default=None
)


def model_name() -> str:
    return settings.agent_model.removeprefix("groq:")


async def record_usage(
    agent: str,
    *,
    input_tokens: int,
    output_tokens: int,
    requests: int = 1,
    tool_calls: int = 0,
    latency_ms: int | None = None,
) -> None:
    case_id = current_case_id.get()
    if case_id is None:  # not inside a case (tests, ad-hoc calls): nothing to attribute
        return
    try:
        conn = await get_connection()
        try:
            await conn.execute(
                """INSERT INTO llm_usage (case_id, agent, model, input_tokens, output_tokens,
                                          requests, tool_calls, latency_ms)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                case_id, agent, model_name(), input_tokens, output_tokens, requests,
                tool_calls, latency_ms,
            )
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001 — accounting must never fail a case
        log.exception("failed to record LLM usage for %s/%s", case_id, agent)
