"""Shared enums used across the locked schema contract (system design §7)."""

from enum import StrEnum


class DisputeCategory(StrEnum):
    ROUTE_DEVIATION = "route_deviation"
    NO_SHOW_CHARGE = "no_show_charge"
    PROPERTY_DAMAGE = "property_damage"
    SAFETY_INCIDENT = "safety_incident"


class CaseRole(StrEnum):
    RIDER = "rider"
    DRIVER = "driver"


class CaseState(StrEnum):
    OPENED = "opened"
    TRIAGE = "triage"
    ASSEMBLING = "assembling"
    AWAITING_RESPONSE = "awaiting_response"
    ADJUDICATING = "adjudicating"
    DECIDED = "decided"
    # Gate, compliance veto, or the Judge sent it to the L2 human queue; a decision object
    # exists but isn't final until ratified (system design §6.1).
    ESCALATED = "escalated"
    SAFETY_BYPASSED = "safety_bypassed"
    DECLINED_INSUFFICIENT_EVIDENCE = "declined_insufficient_evidence"


class EscalationBucket(StrEnum):
    AGENT_DECIDABLE = "agent_decidable"
    ALWAYS_ESCALATE = "always_escalate"


class DecisionOutcome(StrEnum):
    CLAIM_UPHELD = "claim_upheld"
    CLAIM_UPHELD_PARTIAL = "claim_upheld_partial"
    CLAIM_DENIED = "claim_denied"
    # Declined, not denied: the claimant can refile with better evidence (Policy doc §6).
    DECLINED_INSUFFICIENT_EVIDENCE = "declined_insufficient_evidence"


class RemedyType(StrEnum):
    FULL_REFUND = "full_refund"
    PARTIAL_REFUND = "partial_refund"
    COMPENSATION_CREDIT = "compensation_credit"
    CLEANING_REPAIR_FEE = "cleaning_repair_fee"
    NO_SHOW_FEE_WAIVER = "no_show_fee_waiver"
    NO_ACTION = "no_action"
