"""Decision document rendering (system design §6 step 9).

A plain-Markdown rendering of a `DecisionObject`: what was decided, the remedy, each
finding with the evidence refs it rests on, the policy applied, and whether the decision
is final or waiting for L2. It shows evidence ref IDs, never the evidence itself. Whether
the complainee is shown the underlying evidence after L2 is still open (system design
§6.2); the default here is outcome and reasoning only.
"""

from app.schemas import CaseFile, DecisionObject, RemedyType

_OUTCOME_TEXT = {
    "claim_upheld": "Claim upheld",
    "claim_upheld_partial": "Claim partially upheld",
    "claim_denied": "Claim denied",
    "declined_insufficient_evidence": (
        "Declined — insufficient evidence (this is not a ruling on the merits; the claim "
        "can be refiled with better evidence)"
    ),
}

_REMEDY_TEXT = {
    RemedyType.FULL_REFUND: "Full refund",
    RemedyType.PARTIAL_REFUND: "Partial refund",
    RemedyType.COMPENSATION_CREDIT: "Compensation credit",
    RemedyType.CLEANING_REPAIR_FEE: "Cleaning/repair fee charged to the rider",
    RemedyType.NO_SHOW_FEE_WAIVER: "No-show/waiting fee waived",
    RemedyType.NO_ACTION: "No action",
}


def render_decision_document(decision: DecisionObject, case_file: CaseFile) -> str:
    esc = decision.escalation
    if decision.human_ratified:
        status = f"**Final** — ratified by {decision.ratified_by or 'an L2 reviewer'}."
    elif esc.routes_to_l2:
        status = "**Pending human review (L2).** This recommendation is not final."
    else:
        status = (
            "**Final** — decided automatically; it cleared the escalation gate and "
            "compliance check."
        )

    remedy = _REMEDY_TEXT.get(decision.remedy.type, str(decision.remedy.type))
    if decision.remedy.amount:
        remedy += f": ${decision.remedy.amount:.2f}"

    lines = [
        f"# Decision — {decision.case_id}",
        "",
        f"**Category:** {case_file.category.value.replace('_', ' ').title()}  ",
        f"**Filed by:** the {case_file.complainer_role.value}  ",
        f"**Outcome:** {_OUTCOME_TEXT.get(decision.outcome, decision.outcome)}  ",
        f"**Remedy:** {remedy}  ",
        f"**Policy applied:** {decision.policy_applied or 'none'}  ",
        f"**Confidence:** {decision.confidence:.2f}",
        "",
        status,
        "",
        "## Findings",
        "",
    ]
    for i, f in enumerate(decision.reasoning, start=1):
        cites = f" *(evidence: {', '.join(f.cites)})*" if f.cites else ""
        lines.append(f"{i}. {f.finding}{cites}")
    if esc.routes_to_l2 and not decision.human_ratified:
        lines += ["", "## Why this went to human review", ""]
        lines += [f"- {r}" for r in esc.reasons]
        if esc.compliance_veto:
            lines.append(f"- compliance check vetoed the decision: {esc.compliance_veto}")
    return "\n".join(lines) + "\n"
