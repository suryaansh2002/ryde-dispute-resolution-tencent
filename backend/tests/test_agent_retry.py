"""run_agent retries rate limits and 5xx, and gives up on anything else."""

import pytest
from pydantic_ai.exceptions import ModelHTTPError

import app.agents.retry as retry


class FlakyAgent:
    def __init__(self, failures: list[int]):
        self.failures = failures
        self.calls = 0

    async def run(self, prompt):
        self.calls += 1
        if self.failures:
            raise ModelHTTPError(self.failures.pop(0), "qwen")
        return f"ok:{prompt}"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_):
        pass
    monkeypatch.setattr(retry.asyncio, "sleep", instant)


async def test_rate_limit_and_server_errors_are_retried():
    agent = FlakyAgent([429, 503])
    assert await retry.run_agent(agent, "x") == "ok:x"
    assert agent.calls == 3


async def test_client_errors_are_not_retried():
    agent = FlakyAgent([400])
    with pytest.raises(ModelHTTPError):
        await retry.run_agent(agent, "x")
    assert agent.calls == 1


async def test_gives_up_after_max_attempts():
    agent = FlakyAgent([429] * retry.MAX_ATTEMPTS)
    with pytest.raises(ModelHTTPError):
        await retry.run_agent(agent, "x")
    assert agent.calls == retry.MAX_ATTEMPTS


async def test_successful_runs_record_token_usage_for_the_current_case(monkeypatch):
    from types import SimpleNamespace

    import app.data.usage as usage

    written = []

    async def fake_execute(*args):
        written.append(args)

    class Conn:
        execute = staticmethod(fake_execute)

        async def close(self):
            pass

    async def conn():
        return Conn()

    monkeypatch.setattr(usage, "get_connection", conn)

    class Agent:
        name = "judge"

        async def run(self, prompt):
            return SimpleNamespace(usage=SimpleNamespace(
                input_tokens=1200, output_tokens=300, requests=2, tool_calls=1))

    await retry.run_agent(Agent(), "x")  # no case in context: nothing recorded
    assert written == []

    token = usage.current_case_id.set("CASE-0001")
    try:
        await retry.run_agent(Agent(), "x")
    finally:
        usage.current_case_id.reset(token)
    _, case_id, agent, _model, inp, out, requests, tools, _ms = written[0]
    assert (case_id, agent, inp, out, requests, tools) == ("CASE-0001", "judge", 1200, 300, 2, 1)


async def test_daily_quota_is_not_retried():
    class Agent:
        name = "judge"
        calls = 0

        async def run(self, prompt):
            Agent.calls += 1
            raise ModelHTTPError(
                429, "nemotron", {"message": "Rate limit exceeded: free-models-per-day."}
            )

    with pytest.raises(ModelHTTPError):
        await retry.run_agent(Agent(), "x")
    assert Agent.calls == 1
