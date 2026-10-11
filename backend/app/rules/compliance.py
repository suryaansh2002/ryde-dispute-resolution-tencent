"""Compliance check (system design §4 rule 4) — plain Python, no model call.

It can veto a Judge's decision; it never writes or edits one. A veto doesn't change the
outcome. It sends the case to L2 with the reason attached. The checks enforce the Policy
doc's remedy rules (Part 1 §2–§4, §7) on whatever the Judge produced.
"""

from app.rules.policy_math import PHOTO_ONLY_FEES, PROPERTY_DAMAGE_TIERS, no_show_fees
from app.schemas import (
    CaseFile,
    CaseRole,
    DecisionOutcome,
    DisputeCategory,
    JudgeVerdict,
    RemedyType,
)
from app.tools.evidence_lookup import ROUTE_COMPARISON, evidence_index
from app.tools.image_analysis import supported_tier

PROPERTY_DAMAGE_FEE_CAP = 200.00
"""Real, sourced: Ryde's "up to $200" ceiling (Policy doc §4, Terms of Use Clause 11)."""

_ALLOWED_REMEDIES: dict[DisputeCategory, set[RemedyType]] = {
    DisputeCategory.ROUTE_DEVIATION: {
        RemedyType.PARTIAL_REFUND, RemedyType.FULL_REFUND,
        RemedyType.COMPENSATION_CREDIT, RemedyType.NO_ACTION,
    },
    DisputeCategory.NO_SHOW_CHARGE: {
        RemedyType.NO_SHOW_FEE_WAIVER, RemedyType.FULL_REFUND, RemedyType.NO_ACTION,
    },
    DisputeCategory.PROPERTY_DAMAGE: {RemedyType.CLEANING_REPAIR_FEE, RemedyType.NO_ACTION},
}

_NOT_UPHELD = {DecisionOutcome.CLAIM_DENIED, DecisionOutcome.DECLINED_INSUFFICIENT_EVIDENCE}


def compliance_violations(case_file: CaseFile, verdict: JudgeVerdict) -> list[str]:
    remedy, amount = verdict.remedy, verdict.remedy.amount
    violations: list[str] = []

    if verdict.outcome in _NOT_UPHELD and remedy.type != RemedyType.NO_ACTION:
        violations.append(f"outcome {verdict.outcome} cannot carry a {remedy.type} remedy")
    if verdict.outcome not in _NOT_UPHELD and remedy.type == RemedyType.NO_ACTION:
        violations.append(f"outcome {verdict.outcome} needs a remedy, got no_action")
    if verdict.outcome not in _NOT_UPHELD and not verdict.policy_applied:
        violations.append("an upheld claim must name the policy it applied")

    if (
        case_file.complainer_role == CaseRole.DRIVER
        and verdict.outcome not in _NOT_UPHELD
        and remedy.type == RemedyType.NO_SHOW_FEE_WAIVER
    ):
        # A waiver returns the rider's fee: it's what the rider wins, never the remedy for
        # a driver's upheld claim. The Judge has the winner and the outcome reversed.
        violations.append(
            "a no-show fee waiver favours the rider, so it can't be the remedy for an "
            "upheld claim the driver filed"
        )

    allowed = _ALLOWED_REMEDIES.get(case_file.category, {RemedyType.NO_ACTION})
    if remedy.type not in allowed:
        violations.append(f"{remedy.type} is not a valid remedy for {case_file.category}")

    if remedy.type != RemedyType.NO_ACTION:
        if amount is None or amount <= 0:
            violations.append(f"{remedy.type} needs a positive amount")
        elif remedy.type == RemedyType.CLEANING_REPAIR_FEE:
            if amount > PROPERTY_DAMAGE_FEE_CAP:
                violations.append(
                    f"cleaning fee ${amount:.2f} exceeds the ${PROPERTY_DAMAGE_FEE_CAP:.0f} cap"
                )
            if not case_file.photos:
                violations.append("a cleaning fee needs at least one verified photo (Policy §4)")
            if round(amount, 2) not in PHOTO_ONLY_FEES:
                violations.append(
                    f"cleaning fee ${amount:.2f} isn't a scheduled tier amount "
                    f"({sorted(PHOTO_ONLY_FEES)}) — no receipt to justify another figure"
                )
            # The fee can't exceed what the photos show (Image Analysis tier, mapped in
            # code). Skipped when no photo has a usable finding: then a person decides.
            tier = supported_tier(case_file.photos)
            if tier == "none":
                violations.append("the photos show no mess, so no cleaning fee is supported")
            elif tier is not None and amount > PROPERTY_DAMAGE_TIERS[tier] + 0.005:
                violations.append(
                    f"cleaning fee ${amount:.2f} is above the {tier} tier "
                    f"(${PROPERTY_DAMAGE_TIERS[tier]:.0f}) the photos show"
                )
        elif remedy.type == RemedyType.NO_SHOW_FEE_WAIVER:
            fees = no_show_fees(case_file.payment.add_on_fees)
            if fees == 0:
                violations.append("no cancellation/waiting fee on this trip to waive")
            elif amount > fees + 0.005:
                violations.append(f"waiver ${amount:.2f} exceeds the ${fees:.2f} fee charged")
        else:
            if amount > case_file.payment.total_fare + 0.005:
                # Policy §7: every remedy except cleaning fees is capped at the trip's fare.
                violations.append(
                    f"{remedy.type} ${amount:.2f} exceeds the trip fare "
                    f"${case_file.payment.total_fare:.2f}"
                )
            expected = _expected_route_refund(case_file)
            if (
                case_file.category == DisputeCategory.ROUTE_DEVIATION
                and remedy.type in (RemedyType.PARTIAL_REFUND, RemedyType.FULL_REFUND)
                and expected is not None
                and abs(amount - expected) > 0.01
            ):
                violations.append(
                    f"route refund ${amount:.2f} doesn't match the policy formula's "
                    f"${expected:.2f}"
                )
    return violations


def _expected_route_refund(case_file: CaseFile) -> float | None:
    comparison = evidence_index(case_file).get(ROUTE_COMPARISON)
    return comparison.data["refund_if_unjustified"] if comparison else None


def compliance_check(case_file: CaseFile, verdict: JudgeVerdict) -> str | None:
    """Returns the veto reason, or None if the decision passes."""
    violations = compliance_violations(case_file, verdict)
    return "; ".join(violations) if violations else None
