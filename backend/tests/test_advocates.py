"""Advocate wiring + citation-validator behavior, against Dev A's `CaseFile` fixtures.

Scripted `FunctionModel` responses exercise each validator path deterministically;
no test here calls Groq (roadmap v3 risk table — shared rate limit).
"""

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.agents.driver_advocate.agent import driver_advocate_agent, run_driver_advocate
from app.agents.rider_advocate.agent import rider_advocate_agent, run_rider_advocate
from app.schemas import Argument, CaseFile, CaseRole

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


def load_case(name: str) -> CaseFile:
    return CaseFile.model_validate_json((CASE_FILES / f"{name}.json").read_text())


def scripted(*steps):
    """A FunctionModel that plays back one step per model request; fails if asked for more."""
    remaining = list(steps)

    def fn(messages, info: AgentInfo) -> ModelResponse:
        assert remaining, "model called more times than scripted"
        return remaining.pop(0)(info)

    return FunctionModel(fn)


def answer(**argument):
    return lambda info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, argument)])


def call_tool(name: str, **args):
    return lambda info: ModelResponse(parts=[ToolCallPart(name, args)])


def argument(cites, policy_cites, confidence=0.7, role="rider"):
    return {"role": role, "text": "argument", "cites": cites,
            "policy_cites": policy_cites, "confidence": confidence}


async def test_valid_citations_pass_through_and_role_is_forced():
    wrong_role = argument(["ROUTE-COMPARISON", "MSG-0002"], ["POL-02"], role="driver")
    model = scripted(answer(**wrong_role))
    with rider_advocate_agent.override(model=model):
        run = await run_rider_advocate(load_case("route_deviation"))
    assert run.argument.role == CaseRole.RIDER
    assert run.argument.cites == ["ROUTE-COMPARISON", "MSG-0002"]
    assert not run.flagged


async def test_invalid_cite_gets_one_correction_attempt():
    model = scripted(
        answer(**argument(["EV-9999"], ["POL-02"])),
        answer(**argument(["MSG-0001"], ["POL-02"])),
    )
    with rider_advocate_agent.override(model=model):
        run = await run_rider_advocate(load_case("route_deviation"))
    assert run.argument.cites == ["MSG-0001"]
    assert not run.flagged


async def test_persistent_bad_citations_are_stripped_and_flagged():
    bad = argument(["MSG-0001", "EV-9999"], ["POL-02", "POL-99"], confidence=1.4)
    model = scripted(answer(**bad), answer(**bad))
    with rider_advocate_agent.override(model=model):
        run = await run_rider_advocate(load_case("route_deviation"))
    assert run.argument.cites == ["MSG-0001"]
    assert run.argument.policy_cites == ["POL-02"]
    assert run.argument.confidence == 1.0
    assert run.stripped_cites == ["EV-9999"]
    assert run.stripped_policy_cites == ["POL-99"]
    assert run.flagged


async def test_policy_cite_is_valid_only_once_policy_rag_returned_it():
    model = scripted(
        call_tool("policy_rag", query="escalation to human review for repeat disputes in 30 days"),
        answer(**argument(["PROFILE-COMPLAINER"], ["POL-03", "POL-08"], role="driver")),
    )
    with driver_advocate_agent.override(model=model):
        run = await run_driver_advocate(load_case("no_show_charge"))
    assert run.argument.policy_cites == ["POL-03", "POL-08"]
    assert not run.flagged


@pytest.mark.parametrize("case", ["route_deviation", "no_show_charge", "property_damage"])
@pytest.mark.parametrize(
    ("agent", "run_fn", "role"),
    [
        (rider_advocate_agent, run_rider_advocate, CaseRole.RIDER),
        (driver_advocate_agent, run_driver_advocate, CaseRole.DRIVER),
    ],
    ids=["rider", "driver"],
)
async def test_advocates_run_against_every_case_file_fixture(case, agent, run_fn, role):
    with agent.override(model=TestModel()):
        run = await run_fn(load_case(case))
    assert isinstance(run.argument, Argument)
    assert run.argument.role == role
