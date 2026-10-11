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
