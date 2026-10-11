"""Two-phase escalation gate (system design §6.1) — plain Python, no model call.

Phase A: the Judge's confidence against a fixed threshold. Phase B: a category/risk
bucket lookup, independent of confidence. Either one routes the case to L2, as does the
Judge's own `escalate_to_l2` request — an earlier signal that can add an escalation but
never remove one. The gate runs on every adjudicated case, whatever the Judge did.

Bucket contents are data (`ESCALATION_BUCKET_TABLE`), not branches in the gate. Change
what escalates by editing the table. None of these entries are Ryde-sourced: the bucket
contents are an open design detail (system design §6.1), and these are our own
conservative defaults.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.rules.prevention import VELOCITY_THRESHOLD
from app.schemas import (
    CaseFile,
    DisputeCategory,
    Escalation,
    EscalationBucket,
    JudgeVerdict,
    RemedyType,
)

CONFIDENCE_THRESHOLD = 0.6
"""Policy doc §8. Below this, the Judge's decision is never finalized automatically."""

HIGH_VALUE_PROPERTY_DAMAGE = 120.00
"""Not Ryde-sourced: the moderate-tier cap ($120) and above goes to a human."""


@dataclass(frozen=True)
class BucketRule:
    name: str
    description: str
    applies: Callable[[CaseFile, JudgeVerdict | None], bool]
    # False for rules that need the Judge's verdict (e.g. a remedy amount). Those are
    # skipped when the Judge looks the bucket up mid-run, before it has a verdict.
    case_level: bool = True


def _repeat_filer(case_file: CaseFile, _: JudgeVerdict | None) -> bool:
    return max(
        case_file.complainer_profile.dispute_count_30d,
        case_file.complainee_profile.dispute_count_30d,
    ) >= VELOCITY_THRESHOLD


def _high_value_property_damage(case_file: CaseFile, verdict: JudgeVerdict | None) -> bool:
    return (
        verdict is not None
        and case_file.category == DisputeCategory.PROPERTY_DAMAGE
        and verdict.remedy.type == RemedyType.CLEANING_REPAIR_FEE
        and (verdict.remedy.amount or 0) >= HIGH_VALUE_PROPERTY_DAMAGE
    )


def _safety(case_file: CaseFile, _: JudgeVerdict | None) -> bool:
    # Safety claims are hard-stopped by Prevention Rule 3 before any agent runs. This is
    # a defensive backstop in case one ever reaches adjudication.
    return case_file.category == DisputeCategory.SAFETY_INCIDENT


ESCALATION_BUCKET_TABLE: list[BucketRule] = [
    BucketRule(
        "repeat_filer",
        f"Either party has {VELOCITY_THRESHOLD}+ disputes in the trailing 30 days (Policy §8,"
        " Prevention Rule 5) — a pattern a single-case decision can't see.",
        _repeat_filer,
    ),
    BucketRule(
        "high_value_property_damage",
        f"Property Damage fee of ${HIGH_VALUE_PROPERTY_DAMAGE:.0f} or more.",
        _high_value_property_damage,
        case_level=False,
    ),
    BucketRule("safety_incident", "Safety Incident (always human-reviewed).", _safety),
]


def matching_bucket_rules(
    case_file: CaseFile, verdict: JudgeVerdict | None = None
) -> list[BucketRule]:
    return [
        rule for rule in ESCALATION_BUCKET_TABLE
        if (verdict is not None or rule.case_level) and rule.applies(case_file, verdict)
    ]


def run_escalation_gate(
    case_file: CaseFile,
    verdict: JudgeVerdict,
    *,
    judge_requested: bool = False,
    judge_request_reason: str | None = None,
) -> Escalation:
    rules = matching_bucket_rules(case_file, verdict)
    confidence_escalate = verdict.confidence < CONFIDENCE_THRESHOLD
    reasons = [f"bucket: {r.name} — {r.description}" for r in rules]
    if confidence_escalate:
        reasons.append(
            f"confidence {verdict.confidence:.2f} is below the {CONFIDENCE_THRESHOLD} threshold"
        )
    if judge_requested:
        reasons.append(f"Judge requested L2 review: {judge_request_reason or 'no reason given'}")
    return Escalation(
        bucket=EscalationBucket.ALWAYS_ESCALATE if rules else EscalationBucket.AGENT_DECIDABLE,
        bucket_escalate=bool(rules),
        confidence_escalate=confidence_escalate,
        judge_requested_escalation=judge_requested,
        reasons=reasons,
    )
