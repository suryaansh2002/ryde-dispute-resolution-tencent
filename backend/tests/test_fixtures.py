"""Fixture-validity check (roadmap v3, §0a): every hand-written fixture must validate
against the real locked schema, catching drift the moment either side changes a schema
instead of at the Day 5 integration gate. Dev A drops `CaseFile` fixtures in
`data_generation/fixtures/case_files/`, Dev B drops `DecisionObject` fixtures in
`data_generation/fixtures/decisions/` — this test picks up whatever's there.
"""

import json
from pathlib import Path

import pytest

from app.schemas import AgentName, Argument, CaseFile, DecisionObject, TraceEvent, TraceEventKind

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures"


def _json_fixtures(subdir: str) -> list[Path]:
    return sorted((FIXTURES_ROOT / subdir).glob("*.json"))


@pytest.mark.parametrize("path", _json_fixtures("case_files"), ids=lambda p: p.name)
def test_case_file_fixture_matches_schema(path: Path):
    CaseFile.model_validate_json(path.read_text())


@pytest.mark.parametrize("path", _json_fixtures("decisions"), ids=lambda p: p.name)
def test_decision_fixture_matches_schema(path: Path):
    DecisionObject.model_validate_json(path.read_text())


OUTPUT_SCHEMAS = {
    AgentName.RIDER_ADVOCATE: Argument,
    AgentName.DRIVER_ADVOCATE: Argument,
    AgentName.JUDGE: DecisionObject,
}


@pytest.mark.parametrize("path", _json_fixtures("trace_events"), ids=lambda p: p.name)
def test_trace_event_fixture_matches_schema(path: Path):
    events = [TraceEvent.model_validate(e) for e in json.loads(path.read_text())]
    assert events
    for event in events:
        if event.kind == TraceEventKind.AGENT_OUTPUT:
            OUTPUT_SCHEMAS[event.agent].model_validate(event.output)
