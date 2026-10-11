"""Judge wiring + citation validator, against the CaseFile fixtures. Scripted
FunctionModel responses, no Groq calls."""

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.agents.judge.agent import judge_agent, render_judge_input, run_judge
from app.schemas import Argument, CaseFile, CaseRole, JudgeVerdict

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


def load_case(name: str) -> CaseFile:
    return CaseFile.model_validate_json((CASE_FILES / f"{name}.json").read_text())


def argument(role):
    return Argument(role=role, text="arg", cites=["PAYMENT"], policy_cites=["POL-02"],
                    confidence=0.6)


RIDER, DRIVER = argument(CaseRole.RIDER), argument(CaseRole.DRIVER)


def scripted(*steps):
    remaining = list(steps)

    def fn(messages, info: AgentInfo) -> ModelResponse:
        assert remaining, "model called more times than scripted"
        return remaining.pop(0)(info)

    return FunctionModel(fn)


def call_tool(name, **args):
    return lambda info: ModelResponse(parts=[ToolCallPart(name, args)])


def answer(cites=("ROUTE-COMPARISON",), policy="POL-02", confidence=0.8, extra_findings=()):
    findings = [{"finding": "route under 10% extra", "cites": list(cites)}, *extra_findings]
    return lambda info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "outcome": "claim_denied", "remedy": {"type": "no_action"},
        "reasoning": findings, "policy_applied": policy, "confidence": confidence,
    })])


async def run_with(model, case="route_deviation"):
    with judge_agent.override(model=model):
        return await run_judge(load_case(case), RIDER, DRIVER)


async def test_valid_verdict_passes_unflagged():
    run = await run_with(scripted(answer()))
    assert run.verdict.reasoning[0].cites == ["ROUTE-COMPARISON"]
    assert run.verdict.policy_applied == "POL-02"  # in the fixture's policy_tags
    assert not run.flagged and not run.requested_escalation


async def test_bad_cite_gets_one_correction():
    run = await run_with(scripted(answer(cites=["EV-9999"]), answer()))
    assert run.verdict.reasoning[0].cites == ["ROUTE-COMPARISON"]
    assert not run.flagged


async def test_persistent_bad_refs_are_stripped_and_flagged():
    bad = answer(
        cites=["ROUTE-COMPARISON", "EV-9999"], policy="POL-99", confidence=1.7,
        extra_findings=[{"finding": "invented", "cites": ["EV-0000"]}],
    )
    run = await run_with(scripted(bad, bad))
    assert [f.cites for f in run.verdict.reasoning] == [["ROUTE-COMPARISON"]]
    assert run.verdict.policy_applied is None
    assert run.verdict.confidence == 1.0
    assert run.stripped_cites == ["EV-0000", "EV-9999"]
    assert run.flagged


async def test_policy_only_valid_after_policy_rag_returned_it():
    # POL-08 isn't in the route_deviation fixture's policy_tags; it becomes valid once the
    # Judge retrieves it itself.
    run = await run_with(scripted(
        call_tool("policy_rag", query="escalation triggers human review confidence"),
        answer(policy="POL-08"),
    ))
    assert run.verdict.policy_applied == "POL-08"
    assert not run.flagged


async def test_escalate_tool_records_request_and_reason():
    run = await run_with(scripted(
        call_tool("escalation_bucket_lookup"),
        call_tool("escalate_to_l2", reason="evidence conflicts"),
        answer(confidence=0.5),
    ))
    assert run.requested_escalation
    assert run.escalation_reason == "evidence conflicts"


def test_judge_input_never_includes_party_statements():
    text = render_judge_input(load_case("no_show_charge"), RIDER, DRIVER)
    assert "Party statements" not in text
    assert "PICKUP-PROXIMITY" in text  # derived evidence is inlined


@pytest.mark.parametrize("case", ["route_deviation", "no_show_charge", "property_damage"])
async def test_judge_runs_against_every_fixture(case):
    with judge_agent.override(model=TestModel(call_tools=[])):
        run = await run_judge(load_case(case), RIDER, DRIVER)
    assert isinstance(run.verdict, JudgeVerdict)


async def test_clause_id_is_reduced_to_its_policy_id():
    run = await run_with(scripted(answer(policy="POL-02-03")))
    assert run.verdict.policy_applied == "POL-02"
    assert not run.flagged


def upheld_waiver(amount):
    return lambda info: ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
        "outcome": "claim_upheld",
        "remedy": {"type": "no_show_fee_waiver", "amount": amount},
        "reasoning": [{"finding": "driver never arrived", "cites": ["PICKUP-PROXIMITY"]}],
        "policy_applied": "POL-03", "confidence": 0.9,
    })])


async def test_upheld_remedy_without_amount_gets_a_correction():
    run = await run_with(scripted(upheld_waiver(None), upheld_waiver(4.50)), case="no_show_charge")
    assert run.verdict.remedy.amount == 4.50
