"""Judge Agent (system design §6).

Inputs are the `CaseFile` and both advocates' `Argument`s only. It never sees raw feeds
or either party's own statement (system design §4 rule 2). Its three tools are narrow
and read-only: Policy RAG, an escalation-bucket lookup, and a request-L2 signal.

It produces a `JudgeVerdict`, not a `DecisionObject`. The escalation gate and compliance
check run after it, unconditionally, and the orchestrator builds the `DecisionObject`
from all three. The model never writes `escalation` (system design §6.1).

Citation handling mirrors the advocates (system design §4 rule 1). Every finding's
`cites` must resolve to the case file's evidence index, and `policy_applied` must have
been seen this run. Bad references get one correction attempt; after that they're
stripped and the run is flagged.
"""

import json
import re
from dataclasses import dataclass, field

from pydantic_ai import Agent, ModelRetry, RunContext

from app.agents.retry import run_agent
from app.config import settings
from app.rules.escalation import CONFIDENCE_THRESHOLD, matching_bucket_rules
from app.rules.policy_math import no_show_fees
from app.schemas import (
    Argument,
    CaseFile,
    CaseRole,
    DecisionOutcome,
    DisputeCategory,
    JudgeVerdict,
    RemedyType,
)
from app.tools.evidence_lookup import ROUTE_COMPARISON, evidence_index
from app.tools.policy_rag import search_policy

CITATION_CORRECTION_ATTEMPTS = 1

_HEAVY_FIELDS = {"gps_trace", "optimal_route_geometry", "actual_route_geometry"}
# Derived refs worth showing inline: they're the numbers the policy tests actually use.
_INLINE_REF_KINDS = {"route_comparison", "pickup_proximity"}

SYSTEM_PROMPT = f"""\
You are the Judge in RydeResolve, a ride-hailing dispute resolution system. You receive
one case file and two arguments built from it: one from the Rider Advocate, one from the
Driver Advocate. Decide the dispute under the dispute resolution policy.

How to decide:
- Evidence over assertion. Weigh what the case file shows, not how forcefully either
  advocate argues. Discount any claim an advocate makes that the case file doesn't
  support. Hold both parties to the same standard of proof.
- Use policy_rag to confirm the clauses you apply. Don't trust an advocate's citation
  blindly. `policy_applied` must be a policy ID (e.g. "POL-02") from the case file's
  policy_tags, an advocate's policy_cites, or your own policy_rag results.
- Every finding in `reasoning` must cite at least one ref from "Citable evidence refs".
- Key policy tests (confirm details with policy_rag):
  - Route Deviation (POL-02), using ROUTE-COMPARISON's extra_pct:
    - Under 10%: no merit.
    - 10–25%: merit 0.5.
    - Over 25%: merit 1.0.
    - A matching traffic event, or a rider-requested detour in the chat, justifies the
      deviation regardless of size. ROUTE-COMPARISON's matching_traffic_events lists the
      events that match, computed in code (active during the trip and near the planned
      route); if it's non-empty, the deviation is justified and the claim is denied.
      An unsupported justification (a claim in chat with no matching event) counts for
      nothing.
    - If unjustified and the tier has merit, the remedy is a partial_refund of exactly
      ROUTE-COMPARISON's refund_if_unjustified. It's already computed from the policy
      formula; don't recompute it.
  - No-Show (POL-03), using PICKUP-PROXIMITY's reached_pickup:
    - If the driver never came within the arrival radius, a rider's dispute is upheld
      and a driver's fee claim fails (claim_denied, no_action).
    - The remedy for an upheld rider dispute is always a no_show_fee_waiver of exactly
      the fee in PAYMENT's add_on_fees, never a fare refund: the fee is what's disputed.
    - If the driver did arrive, the minimum wait applies and the fee stands only if the
      driver also tried to reach the rider.
  - Property Damage (POL-04): the claimant needs at least one photo. Tiers: minor $40
    (food/drink spill, crumbs), moderate $120 (bodily fluids, stains, mud, dirt), severe
    $200 (vomit). Each photo carries `analysis` from Image Analysis: what is visible and
    the `tier` that maps to, computed in code from the policy's tier table. The tier the
    evidence supports is the highest tier among the photos' analyses:
    - Any of minor/moderate/severe: uphold ("claim_upheld") with a cleaning_repair_fee of
      exactly that tier's amount. A bigger claimed mess than the photo shows doesn't
      raise the tier; the photo does.
    - All "none": the photos show no mess, so deny the claim.
    - "unclear" or no analysis: the photo can't establish a tier. Give your best verdict
      but call escalate_to_l2 so a person looks at the photo.
    This system collects photos but no cleaning receipts, so the fee is the scheduled
    amount, never a figure inside a tier. A valid photo is enough: never decline for a
    missing receipt or for when the photo was submitted (POL-04).
  - Required evidence missing: outcome "declined_insufficient_evidence" with remedy
    no_action. That's distinct from denying the claim on its merits.
- Outcomes are about the filer's claim. If the driver filed and the evidence goes
  against the driver, the outcome is "claim_denied", even though that favours the rider.
- Outcomes:
  - "claim_upheld" / "claim_upheld_partial" need a real remedy with a positive amount,
    in dollars. For no_show_fee_waiver, the amount is the fee shown in PAYMENT's
    add_on_fees.
  - "claim_denied" / "declined_insufficient_evidence" need remedy "no_action".
- `policy_applied` is the policy ID (e.g. "POL-03"), not a clause ID like "POL-03-04".
- `confidence` (0.0–1.0) is your honest certainty. Anything below {CONFIDENCE_THRESHOLD}
  goes to a human reviewer, which is the right result for a genuinely unclear case, so
  don't inflate it.
- Call escalation_bucket_lookup to see whether this case is already in an
  always-escalate bucket. Call escalate_to_l2 if the policy doesn't cover the situation
  or the evidence conflicts in a way you can't resolve. Still give your best verdict.
- Refer to the parties as "the rider" and "the driver"; never assume anyone's gender.
"""


@dataclass
class JudgeDeps:
    case_file: CaseFile
    # Policies the advocates cited. Already validated in their own runs (each had to be
    # retrieved there), so the Judge may apply them without re-searching.
    argued_policy_ids: set[str] = field(default_factory=set)
    retrieved_policy_ids: set[str] = field(default_factory=set)
    requested_escalation: bool = False
    escalation_reason: str | None = None
    stripped_cites: list[str] = field(default_factory=list)
    stripped_policy: str | None = None


@dataclass
class JudgeRun:
    verdict: JudgeVerdict
    requested_escalation: bool
    escalation_reason: str | None
    stripped_cites: list[str]
    stripped_policy: str | None

    @property
    def flagged(self) -> bool:
        return bool(self.stripped_cites or self.stripped_policy)


def render_judge_input(
    case_file: CaseFile, rider_argument: Argument, driver_argument: Argument
) -> str:
    body = case_file.model_dump(mode="json", exclude=_HEAVY_FIELDS)
    index = evidence_index(case_file)
    refs = "\n".join(f"- {ref} ({item.kind})" for ref, item in index.items())
    derived = {ref: item.data for ref, item in index.items() if item.kind in _INLINE_REF_KINDS}
    return (
        f"Case file:\n{json.dumps(body, indent=2)}\n\n"
        f"Derived evidence:\n{json.dumps(derived, indent=2)}\n\n"
        f"Citable evidence refs:\n{refs}\n\n"
        f"Rider Advocate argument:\n{rider_argument.model_dump_json(indent=2)}\n\n"
        f"Driver Advocate argument:\n{driver_argument.model_dump_json(indent=2)}"
    )


judge_agent = Agent(
    settings.agent_model,
    output_type=JudgeVerdict,
    deps_type=JudgeDeps,
    system_prompt=SYSTEM_PROMPT,
    retries=3,
    name="judge",
)


@judge_agent.tool
async def policy_rag(ctx: RunContext[JudgeDeps], query: str) -> list[dict]:
    """Search the dispute resolution policy. Returns the most relevant clauses with their
    policy IDs."""
    hits = search_policy(query)
    ctx.deps.retrieved_policy_ids.update(h.policy_id for h in hits)
    return [h.model_dump() for h in hits]


@judge_agent.tool
async def escalation_bucket_lookup(ctx: RunContext[JudgeDeps]) -> dict:
    """Check whether this case is in an always-escalate bucket (read-only). Rules that
    depend on your verdict, like the remedy amount, are applied after you decide."""
    rules = matching_bucket_rules(ctx.deps.case_file)
    return {
        "bucket": "always_escalate" if rules else "agent_decidable",
        "matching_rules": [{"name": r.name, "description": r.description} for r in rules],
    }


@judge_agent.tool
async def escalate_to_l2(ctx: RunContext[JudgeDeps], reason: str) -> str:
    """Flag this case for human (L2) review, with a short reason. You must still return
    your best verdict."""
    ctx.deps.requested_escalation = True
    ctx.deps.escalation_reason = reason
    return "L2 review requested. Now return your best verdict."


_UPHELD = {DecisionOutcome.CLAIM_UPHELD, DecisionOutcome.CLAIM_UPHELD_PARTIAL}

# Where the money goes follows from the remedy type; it isn't the model's call.
_DESTINATIONS = {
    RemedyType.FULL_REFUND: "original_payment_method",
    RemedyType.PARTIAL_REFUND: "original_payment_method",
    RemedyType.NO_SHOW_FEE_WAIVER: "original_payment_method",
    RemedyType.COMPENSATION_CREDIT: "rider_account_credit",
    RemedyType.CLEANING_REPAIR_FEE: "driver_payout",
}


_CATEGORY_POLICY = {
    DisputeCategory.ROUTE_DEVIATION: "POL-02",
    DisputeCategory.NO_SHOW_CHARGE: "POL-03",
    DisputeCategory.PROPERTY_DAMAGE: "POL-04",
}


def _policy_amount(case_file: CaseFile, remedy_type: RemedyType) -> float | None:
    """The amount the policy fixes for this remedy, computed in code (Policy doc §2, §3):
    a waiver returns exactly the fee charged; a route refund is exactly the formula's
    figure. None where the Judge's choice decides it (a cleaning fee's tier)."""
    if remedy_type == RemedyType.NO_SHOW_FEE_WAIVER:
        return no_show_fees(case_file.payment.add_on_fees) or None
    if remedy_type in (RemedyType.PARTIAL_REFUND, RemedyType.FULL_REFUND):
        comparison = evidence_index(case_file).get(ROUTE_COMPARISON)
        if comparison and comparison.data["refund_if_unjustified"] > 0:
            return comparison.data["refund_if_unjustified"]
    return None


def _policy_id(ref: str | None) -> str | None:
    """Clause IDs like "POL-03-04" mean policy POL-03. Reduce them to the policy ID
    rather than rejecting a citation that's right but too specific."""
    if ref and re.fullmatch(r"POL-\d{2}-\d{2}", ref):
        return ref[:6]
    return ref


@judge_agent.output_validator
async def validate_judge_citations(ctx: RunContext[JudgeDeps], out: JudgeVerdict) -> JudgeVerdict:
    deps = ctx.deps
    valid_refs = evidence_index(deps.case_file).keys()
    valid_policies = (
        {t.policy_id for t in deps.case_file.policy_tags}
        | deps.argued_policy_ids | deps.retrieved_policy_ids
        | {p for p in [_CATEGORY_POLICY.get(deps.case_file.category)] if p}
    )
    fixed_amount = _policy_amount(deps.case_file, out.remedy.type)
    # Each category is governed by one policy section; an upheld verdict that forgot to
    # name it gets the category's own (clerical, like the amounts above).
    policy = _policy_id(out.policy_applied) or (
        _CATEGORY_POLICY.get(deps.case_file.category) if out.outcome in _UPHELD else None
    )
    out = out.model_copy(update={
        "policy_applied": policy,
        "remedy": out.remedy.model_copy(update={
            "destination": _DESTINATIONS.get(out.remedy.type),
            **({"amount": fixed_amount} if fixed_amount is not None else {}),
        }),
    })
    bad_cites = sorted({c for f in out.reasoning for c in f.cites if c not in valid_refs})
    bad_policy = out.policy_applied if (
        out.policy_applied and out.policy_applied not in valid_policies
    ) else None
    uncited = [f.finding for f in out.reasoning if not f.cites]
    problems = []
    if bad_cites:
        problems.append(f"cites not in this case file: {bad_cites}; valid: {list(valid_refs)}")
    if bad_policy:
        problems.append(
            f"policy_applied {bad_policy!r} was never retrieved; valid: {sorted(valid_policies)}"
            " (or call policy_rag)"
        )
    if uncited:
        problems.append(f"every finding needs at least one cite: {uncited}")
    if not out.reasoning:
        problems.append("reasoning must contain at least one finding")
    if not 0.0 <= out.confidence <= 1.0:
        problems.append("confidence must be between 0.0 and 1.0")
    if out.remedy.type != RemedyType.NO_ACTION and not (out.remedy.amount or 0) > 0:
        problems.append(f"remedy {out.remedy.type} needs a positive dollar amount")
    if (
        deps.case_file.complainer_role == CaseRole.DRIVER
        and out.outcome in _UPHELD
        and out.remedy.type == RemedyType.NO_SHOW_FEE_WAIVER
    ):
        problems.append(
            "the driver filed this claim, and a no_show_fee_waiver favours the rider. If the "
            "evidence favours the rider, the driver's claim is denied: outcome claim_denied, "
            "remedy no_action"
        )
    if out.outcome in _UPHELD and out.remedy.type == RemedyType.NO_ACTION:
        problems.append(
            f"outcome {out.outcome} needs a remedy. If the filer's claim fails on the evidence, "
            "the outcome is claim_denied"
        )
    if out.outcome not in _UPHELD and out.remedy.type != RemedyType.NO_ACTION:
        problems.append(
            f"outcome {out.outcome} must carry remedy no_action, not {out.remedy.type}: "
            "only an upheld claim has a remedy"
        )
    if out.outcome in _UPHELD and not out.policy_applied:
        problems.append("an upheld claim must name the policy it applies in policy_applied")

    if problems and ctx.retry < min(CITATION_CORRECTION_ATTEMPTS, ctx.max_retries):
        raise ModelRetry("Fix your verdict: " + "; ".join(problems))

    deps.stripped_cites = bad_cites
    deps.stripped_policy = bad_policy
    reasoning = []
    for f in out.reasoning:
        kept = [c for c in f.cites if c in valid_refs]
        if kept:
            reasoning.append(f.model_copy(update={"cites": kept}))
    return out.model_copy(update={
        "reasoning": reasoning,
        "policy_applied": None if bad_policy else out.policy_applied,
        "confidence": min(max(out.confidence, 0.0), 1.0),
    })


async def run_judge(
    case_file: CaseFile, rider_argument: Argument, driver_argument: Argument
) -> JudgeRun:
    deps = JudgeDeps(
        case_file=case_file,
        argued_policy_ids={
            _policy_id(p) for p in rider_argument.policy_cites + driver_argument.policy_cites
        },
    )
    result = await run_agent(
        judge_agent,
        render_judge_input(case_file, rider_argument, driver_argument), deps=deps
    )
    return JudgeRun(
        result.output, deps.requested_escalation, deps.escalation_reason,
        deps.stripped_cites, deps.stripped_policy,
    )
