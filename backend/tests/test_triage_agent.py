"""Wiring test only — uses pydantic-ai's TestModel so CI/local runs don't burn Groq's
shared rate limit on every test iteration (roadmap v3 risk table). Real-model behavior
gets checked manually / via the golden-case suite, not per-commit here.
"""

from pydantic_ai.models.test import TestModel

from app.agents.triage.agent import run_triage, triage_agent
from app.schemas.triage import TriageResult


async def test_triage_agent_produces_a_valid_triage_result():
    with triage_agent.override(model=TestModel()):
        result = await run_triage("The driver took a route 3km longer than expected.", "trip-1")
    assert isinstance(result, TriageResult)
