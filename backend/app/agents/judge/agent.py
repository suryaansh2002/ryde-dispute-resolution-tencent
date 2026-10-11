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

from app.config import settings
from app.rules.escalation import CONFIDENCE_THRESHOLD, matching_bucket_rules
from app.schemas import Argument, CaseFile, JudgeVerdict, RemedyType
from app.tools.evidence_lookup import evidence_index
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
      deviation regardless of size. An unsupported justification counts for nothing.
    - If unjustified and the tier has merit, the remedy is a partial_refund of exactly
      ROUTE-COMPARISON's refund_if_unjustified. It's already computed from the policy
      formula; don't recompute it.
  - No-Show (POL-03), using PICKUP-PROXIMITY's reached_pickup:
    - If the driver never came within the arrival radius, a rider's dispute is upheld
      (no_show_fee_waiver for the fee charged) and a driver's fee claim fails.
    - If the driver did arrive, the minimum wait applies and the fee stands only if the
      driver also tried to reach the rider.
  - Property Damage (POL-04): the claimant needs at least one photo. Tiers: minor $40
    (food/drink spill, crumbs), moderate $120 (bodily fluids, stains), severe $200
    (vomit). This system collects photos but no cleaning receipts, so the fee is exactly
    the scheduled amount for the tier the evidence supports, as a cleaning_repair_fee
    with outcome "claim_upheld". Pick the tier; don't pick a figure inside it.
  - Required evidence missing: outcome "declined_insufficient_evidence" with remedy
    no_action. That's distinct from denying the claim on its merits.
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
    retries=2,
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


# Where the money goes follows from the remedy type; it isn't the model's call.
_DESTINATIONS = {
    RemedyType.FULL_REFUND: "original_payment_method",
    RemedyType.PARTIAL_REFUND: "original_payment_method",
    RemedyType.NO_SHOW_FEE_WAIVER: "original_payment_method",
    RemedyType.COMPENSATION_CREDIT: "rider_account_credit",
    RemedyType.CLEANING_REPAIR_FEE: "driver_payout",
}


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
    valid_policies = {t.policy_id for t in deps.case_file.policy_tags} | deps.retrieved_policy_ids
    out = out.model_copy(update={
        "policy_applied": _policy_id(out.policy_applied),
        "remedy": out.remedy.model_copy(
            update={"destination": _DESTINATIONS.get(out.remedy.type)}
        ),
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
    deps = JudgeDeps(case_file=case_file)
    result = await judge_agent.run(
        render_judge_input(case_file, rider_argument, driver_argument), deps=deps
    )
    return JudgeRun(
        result.output, deps.requested_escalation, deps.escalation_reason,
        deps.stripped_cites, deps.stripped_policy,
    )
