"""Triage Agent (system design §6, §7). Runs first, before Prevention rules — its
`is_safety` output feeds the mandatory safety hard-stop (Prevention Rule 3). No tools:
reads only the raw claim submission, before a `CaseFile` exists.
"""

from pydantic_ai import Agent

from app.agents.retry import run_agent
from app.config import settings
from app.schemas.triage import TriageResult

SYSTEM_PROMPT = """\
You are the Triage Agent for RydeResolve, a ride-hailing dispute resolution system.

Given a rider's or driver's raw claim text and trip ID, classify it:

- category: one of route_deviation, no_show_charge, property_damage, safety_incident.
  - route_deviation: the driver took an unrequested, materially longer route.
  - no_show_charge: a dispute over a cancellation or waiting-time fee (driver never
    arrived, or rider never showed).
  - property_damage: a claim of mess/damage to the vehicle (spills, stains, odor,
    physical damage).
  - safety_incident: anything involving physical safety — assault, threats, unsafe
    driving, weapons, or any language suggesting a person was put in danger. When in
    doubt between safety_incident and another category, prefer safety_incident — it
    only routes the case to a human, it never blocks a legitimate claim.
- tier: a short free-text severity/fee-tier hint for this category (e.g. "minor",
  "severe") to help downstream policy lookup — best guess from the claim text alone.
- is_safety: true if and only if category is safety_incident. This is read directly by
  the mandatory safety hard-stop, which bypasses all further agent reasoning and routes
  straight to a human reviewer — err toward true on any ambiguous safety language.

Only the three named non-safety categories are handled by this system's own policy
today (Route Deviation, No-Show Charge, Property Damage). If a claim doesn't clearly
fit any of them and isn't a safety matter, pick the closest of the three rather than
inventing a new category.
"""

triage_agent = Agent(
    settings.agent_model,
    output_type=TriageResult,
    system_prompt=SYSTEM_PROMPT,
)


async def run_triage(claim_text: str, trip_id: str) -> TriageResult:
    """`triage_result = await run_triage(claim_text, trip_id)` (system design §6 step 2)."""
    result = await run_agent(triage_agent, f"trip_id: {trip_id}\n\nclaim:\n{claim_text}")
    return result.output
