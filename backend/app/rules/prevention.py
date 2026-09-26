"""Prevention Rules — six deterministic gates, run after Triage, before the Evidence
Collection Agent (Policy & Prevention Rules doc, Part 2; system design §4 rule set).

Plain Python, no model call, no `pydantic_ai.Agent` — every check here must stay pure and
unit-testable in isolation. The orchestrator wires real DB lookups into `PreventionContext`;
these functions never touch Postgres themselves.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.schemas.common import DisputeCategory

CLAIM_WINDOW_DAYS = 30
"""Real-sourced for No-Show (30-day RydeHELP window); extended to all three categories as
our own consistency choice, not a Ryde fact for Route Deviation/Property Damage (Policy
doc Part 2, Rule 6)."""

VELOCITY_THRESHOLD = 3
"""3+ disputes in trailing 30 days. Unresearched placeholder — more load-bearing now that
there's no Fraud & Bad-Faith Detection Agent backstop (Policy doc Part 2, Rule 5)."""

# Categories that have a hard evidence requirement at filing time (Rule 4). Route Deviation
# and No-Show are captured automatically by the Evidence Collection Agent, so this gate
# rarely fires for them in practice — Property Damage is the real case it exists for.
CATEGORIES_REQUIRING_EVIDENCE_AT_FILING = {DisputeCategory.PROPERTY_DAMAGE}


class PreventionAction(StrEnum):
    PASS = "pass"
    REJECTED_DUPLICATE = "rejected_duplicate"
    REJECTED_MALFORMED = "rejected_malformed"
    SAFETY_BYPASSED = "safety_bypassed"
    DECLINED_INSUFFICIENT_EVIDENCE = "declined_insufficient_evidence"
    DECLINED_STALE = "declined_stale"


@dataclass
class PreventionContext:
    """Everything the six rules need, pre-fetched by the orchestrator."""

    trip_id: str
    category: DisputeCategory | None
    claimant_id: str
    trip_exists: bool
    claimant_is_party_to_trip: bool
    has_open_or_decided_case_for_trip: bool
    is_safety: bool
    has_required_evidence: bool
    claimant_dispute_count_30d: int
    trip_completed_at: datetime | None
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PreventionOutcome:
    action: PreventionAction
    velocity_flagged: bool = False
    detail: str = ""


def run_prevention_rules(ctx: PreventionContext) -> PreventionOutcome:
    """Runs the six rules in order. The first hard-stop wins; velocity (Rule 5) is a
    non-blocking flag layered onto whatever the other rules decide."""

    # Rule 2 — malformed request. Checked before Rule 1 since a malformed claim (bad
    # trip_id, out-of-scope category, claimant not a party) can't be checked for
    # duplicates against real records.
    if (
        not ctx.trip_exists
        or ctx.category is None
        or not ctx.claimant_is_party_to_trip
    ):
        return PreventionOutcome(
            action=PreventionAction.REJECTED_MALFORMED,
            detail="trip_id unknown, category out of scope, or claimant not a party to the trip",
        )

    # Rule 1 — duplicate claim.
    if ctx.has_open_or_decided_case_for_trip:
        return PreventionOutcome(
            action=PreventionAction.REJECTED_DUPLICATE,
            detail="an open or decided case already exists for this trip_id",
        )

    # Rule 3 — safety hard gate. Reads Triage's `is_safety` output directly.
    if ctx.is_safety:
        return PreventionOutcome(
            action=PreventionAction.SAFETY_BYPASSED,
            detail="Triage flagged is_safety=true; bypassing all agent reasoning",
        )

    # Rule 6 — claim window. Only checkable once the trip's completion time is known.
    if ctx.trip_completed_at is not None:
        age = ctx.now - ctx.trip_completed_at
        if age > timedelta(days=CLAIM_WINDOW_DAYS):
            return PreventionOutcome(
                action=PreventionAction.DECLINED_STALE,
                detail=f"filed {age.days}d after trip completion, exceeds the {CLAIM_WINDOW_DAYS}-day window",
            )

    # Rule 4 — evidence-presence gate.
    if ctx.category in CATEGORIES_REQUIRING_EVIDENCE_AT_FILING and not ctx.has_required_evidence:
        return PreventionOutcome(
            action=PreventionAction.DECLINED_INSUFFICIENT_EVIDENCE,
            detail=f"{ctx.category.value} requires evidence at filing; none present",
        )

    # Rule 5 — velocity / repeat-filer flag. Non-blocking: tags the case, never auto-decides.
    velocity_flagged = ctx.claimant_dispute_count_30d >= VELOCITY_THRESHOLD

    return PreventionOutcome(action=PreventionAction.PASS, velocity_flagged=velocity_flagged)
