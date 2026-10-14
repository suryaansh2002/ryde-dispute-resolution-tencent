"""What the rider and the driver are told about their case, in plain words.

Pure code, no model call: the copy is built from the case state, the latest decision and
the case file's evidence index (the same computed items the agents cite), so every
number in it is one the evidence actually holds. A fact the evidence can't support is
left out rather than guessed. The voice follows the approved prototype: short
sentences, second person to the viewer, first names for the other party, no jargon.

Which policy figures are Ryde's own and which are this project's is kept as it is in
the Policy doc; see the comments next to each figure below.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.rules.escalation import HIGH_VALUE_PROPERTY_DAMAGE
from app.rules.policy_math import (
    PROPERTY_DAMAGE_TIERS,
    ROUTE_FULL_MERIT_ABOVE_PCT,
    ROUTE_NO_MERIT_BELOW_PCT,
    no_show_fees,
)
from app.rules.prevention import CLAIM_WINDOW_DAYS, VELOCITY_THRESHOLD
from app.schemas import CaseFile, CaseState, DecisionObject, DecisionOutcome, DisputeCategory
from app.schemas.case_file import EvidencePhoto
from app.tools.evidence_lookup import (
    PICKUP_ARRIVAL_RADIUS_M,
    PICKUP_PROXIMITY,
    ROUTE_COMPARISON,
    evidence_index,
)

ICONS = {
    "route", "alert", "msg", "info", "pin", "camera", "scale", "clock", "shield", "receipt",
    "user",
}

_IN_PROGRESS = {
    CaseState.OPENED, CaseState.TRIAGE, CaseState.ASSEMBLING, CaseState.ADJUDICATING,
}
_UPHELD = {DecisionOutcome.CLAIM_UPHELD, DecisionOutcome.CLAIM_UPHELD_PARTIAL}

# Words a driver uses in chat to claim a closure, or to say they'd arrived. Only used to
# decide whether "the driver mentioned..." is true; never to infer anything else.
_CLOSURE_WORDS = ("closure", "closed")
_ARRIVED_WORDS = ("i'm here", "im here", "i am here", "waiting outside", "arrived", "outside")

_TRAFFIC_NOUN = {
    "construction": ("Construction", "roadworks explain"),
    "road_closure": ("A road closure", "a road closure explains"),
    "accident": ("An accident", "an accident explains"),
}

_MESS = {
    "drink_spill": "a drink spill", "food_crumbs": "food crumbs", "mud_dirt": "mud and dirt",
    "stain": "a stain", "vomit": "vomit", "bodily_fluid_other": "bodily fluids",
    "other_damage": "damage",
}
# The vision prompt grades extent as how much of the seat or floor the mess covers.
_EXTENT = {
    "small": "in one spot", "medium": "over part of the seat or floor",
    "large": "across much of the seat or floor",
}
_TIER_ORDER = ["unclear", "none", "minor", "moderate", "severe"]


@dataclass
class OutcomeInput:
    case_id: str
    state: str
    category: str | None
    complainer_role: str  # rider | driver
    complainer_name: str
    complainee_name: str
    viewer: str  # rider | driver
    decision: DecisionObject | None = None
    case_file: CaseFile | None = None
    has_response: bool = False  # the other party answered the claim
    filed_at: datetime | None = None
    trip_completed_at: datetime | None = None


@dataclass
class _Copy:
    tone: str
    head: str
    sub: str
    facts: list[tuple[str, str]] = field(default_factory=list)
    rule: str | None = None
    money: str | None = None
    can_refile: bool = False


def first_name(display_name: str) -> str:
    """Given names first, surname last ("Shu Fen Wong" -> "Shu Fen")."""
    parts = display_name.split()
    return " ".join(parts[:-1]) if len(parts) > 1 else display_name


def money(amount: float) -> str:
    return f"${amount:.0f}" if round(amount, 2) == int(amount) else f"${amount:.2f}"


def distance_m(metres: float) -> str:
    if metres >= 1000:
        return f"{metres / 1000:.1f} km"
    return f"{round(metres) if metres < 100 else round(metres, -1):.0f} m"


class _Case:
    """The input plus what every copy function needs: whose side the viewer is on, the
    other party's first name, and the evidence index."""

    def __init__(self, inp: OutcomeInput):
        self.inp = inp
        self.state = CaseState(inp.state)
        self.category = DisputeCategory(inp.category) if inp.category else None
        self.complainer = inp.viewer == inp.complainer_role
        self.side = "complainer" if self.complainer else "complainee"
        other = inp.complainee_name if self.complainer else inp.complainer_name
        self.other = first_name(other)
        self.rider_view = inp.viewer == "rider"
        self.decision = inp.decision
        self.ev = (
            {ref: item.data for ref, item in evidence_index(inp.case_file).items()}
            if inp.case_file else {}
        )

    @property
    def outcome(self) -> DecisionOutcome | None:
        return DecisionOutcome(self.decision.outcome) if self.decision else None

    @property
    def upheld(self) -> bool:
        return self.outcome in _UPHELD

    def amount(self) -> float | None:
        if self.decision and self.decision.remedy.amount:
            return self.decision.remedy.amount
        return None

    def chat(self, sender: str) -> list[str]:
        return [
            d["text"].lower() for d in self.ev.values()
            if isinstance(d, dict) and d.get("sender_role") == sender and "text" in d
        ]


def party_outcome(inp: OutcomeInput) -> dict:
    c = _Case(inp)
    copy = _copy_for(c)
    for icon, _ in copy.facts:
        assert icon in ICONS, icon
    return {
        "case_id": inp.case_id, "state": inp.state, "viewer": inp.viewer,
        "viewer_side": c.side, "tone": copy.tone, "head": copy.head, "sub": copy.sub,
        "facts": [{"icon": icon, "text": text} for icon, text in copy.facts],
        "rule": copy.rule, "money": copy.money, "can_refile": copy.can_refile,
        "reviewed_by_person": bool(c.decision and c.decision.human_ratified),
    }


def _copy_for(c: _Case) -> _Copy:
    if c.category == DisputeCategory.SAFETY_INCIDENT or c.state == CaseState.SAFETY_BYPASSED:
        return _safety(c)
    if c.state in _IN_PROGRESS:
        return _in_progress(c)
    if c.state == CaseState.AWAITING_RESPONSE:
        return _awaiting(c)
    if c.state == CaseState.ESCALATED:
        return _escalated(c)
    if c.state == CaseState.DECLINED_INSUFFICIENT_EVIDENCE:
        return _declined(c)
    if c.decision is None:
        return _Copy("neutral", "A decision has been made", "The details aren't available yet.")
    if c.outcome == DecisionOutcome.DECLINED_INSUFFICIENT_EVIDENCE:
        return _declined(c)
    builder = {
        DisputeCategory.ROUTE_DEVIATION: _route,
        DisputeCategory.NO_SHOW_CHARGE: _no_show,
        DisputeCategory.PROPERTY_DAMAGE: _damage,
    }.get(c.category)
    if builder is None:
        return _Copy("neutral", "A decision has been made", "")
    copy = builder(c)
    copy.facts += _hearing_facts(c)
    return copy


# --- before a decision -------------------------------------------------------------


def _what_was_reported(c: _Case) -> str | None:
    who = "You" if c.complainer else c.other
    if c.category == DisputeCategory.ROUTE_DEVIATION:
        return f"{who} reported that the route was longer than it should have been."
    if c.category == DisputeCategory.NO_SHOW_CHARGE:
        if c.inp.complainer_role == "rider":
            return f"{who} disputed the no-show fee on this trip."
        if c.complainer:
            return "You reported that the rider didn't show up."
        return f"{who} reported that you didn't show up for the pickup."
    if c.category == DisputeCategory.PROPERTY_DAMAGE:
        return f"{who} reported a mess in the car after this trip."
    return None


def _in_progress(c: _Case) -> _Copy:
    weighing = c.state == CaseState.ADJUDICATING
    reported = _what_was_reported(c)
    facts = [("info", reported)] if reported else []
    if c.complainer:
        sub = (
            "Both sides are being weighed now. You'll see the result here."
            if weighing else "We're gathering the trip records. You'll see the result here."
        )
        return _Copy("neutral", "We're looking into your report", sub, facts)
    sub = (
        "Both sides are being weighed now. You'll see the result here."
        if weighing else "We're gathering the trip records. You'll be able to reply."
    )
    return _Copy("neutral", f"{c.other} reported a problem with this trip", sub, facts)


def _awaiting(c: _Case) -> _Copy:
    reported = _what_was_reported(c)
    facts = [("info", reported)] if reported else []
    if c.complainer:
        return _Copy(
            "neutral", f"Waiting for {c.other}'s reply",
            f"The trip records are ready. {c.other} can reply before a decision is made.", facts,
        )
    return _Copy(
        "neutral", "Your reply is needed",
        "Tell us your side of what happened before a decision is made.", facts,
    )


def _escalated(c: _Case) -> _Copy:
    facts = _evidence_facts(c)
    if c.inp.has_response:
        facts.append(("msg", (
            f"{c.other} has replied. The specialist will weigh both sides." if c.complainer
            else "Your reply is part of the case. The specialist will weigh both sides."
        )))
    return _Copy("warn", "A specialist is checking this one", _escalation_reason(c), facts)


def _escalation_reason(c: _Case) -> str:
    later = "so a person will review it before anything changes."
    esc = c.decision.escalation if c.decision else None
    if esc is None:
        return "A person will review this case before anything changes."
    buckets = {r.split(" ")[1] for r in esc.reasons if r.startswith("bucket: ")}
    if "high_value_property_damage" in buckets:
        return (
            f"Cleaning fees of {money(HIGH_VALUE_PROPERTY_DAMAGE)} or more always get a "
            "person's review before anyone is charged."
        )
    if "repeat_filer" in buckets:
        return (
            f"When either side has {VELOCITY_THRESHOLD} or more disputes in 30 days, "
            "a person reviews the case before anything changes."
        )
    if esc.compliance_veto:
        return f"An automatic check on the decision didn't pass, {later}"
    if esc.judge_requested_escalation:
        return f"This case needs a closer look, {later}"
    if esc.confidence_escalate:
        return f"The evidence didn't point clearly one way, {later}"
    return "A person will review this case before anything changes."


def _evidence_facts(c: _Case) -> list[tuple[str, str]]:
    """The neutral evidence facts for a case still waiting on a person: what the records
    show, nothing about how it will turn out."""
    if c.category == DisputeCategory.ROUTE_DEVIATION:
        return _route_distance_fact(c, upheld=False)
    if c.category == DisputeCategory.NO_SHOW_CHARGE:
        return _pickup_facts(c)[:1]
    if c.category == DisputeCategory.PROPERTY_DAMAGE:
        return _photo_facts(c)
    return []


# --- safety and declined -----------------------------------------------------------


def _safety(c: _Case) -> _Copy:
    # Nothing about the other party, ever: a safety report is a person's job.
    if c.state == CaseState.DECIDED:
        copy = _Copy(
            "bad", "Our safety team has finished its review",
            "A safety specialist reviewed what happened.",
            [("shield", "A person handled this report, not an automated system.")],
        )
        copy.money = _money_line(c, receiving=c.complainer)
        return copy
    if c.complainer:
        return _Copy(
            "bad", "Our safety team has your report",
            "A safety specialist will review what happened and contact you.",
            [("shield", "No automated system decides safety reports. A person handles yours."),
             ("alert", "If you're in danger right now, call 999.")],
        )
    return _Copy(
        "bad", "Our safety team is looking into this trip",
        "A safety specialist is reviewing a report about this trip and may contact you.",
        [("shield", "A person handles safety reports, not an automated system.")],
    )


def _declined(c: _Case) -> _Copy:
    # The 30-day window is Ryde-sourced for No-Show only; applying it to every category
    # is this project's own consistency choice (Prevention Rule 6).
    days_late = None
    if c.decision is None and c.inp.filed_at and c.inp.trip_completed_at:
        age = c.inp.filed_at - c.inp.trip_completed_at
        if age > timedelta(days=CLAIM_WINDOW_DAYS):
            days_late = age.days
    no_photo = c.category == DisputeCategory.PROPERTY_DAMAGE and not (
        c.inp.case_file and c.inp.case_file.photos
    )
    if not c.complainer:
        sub = (
            f"The report was filed more than {CLAIM_WINDOW_DAYS} days after the trip, "
            "so it wasn't reviewed." if days_late is not None
            else "The report didn't include a photo, so nothing changes for you." if no_photo
            else "The report didn't have enough evidence, so nothing changes for you."
        )
        return _Copy("neutral", "No action on this report", sub)
    if days_late is not None:
        return _Copy(
            "neutral", "This trip is too old to dispute",
            f"Reports need to be filed within {CLAIM_WINDOW_DAYS} days of the trip.",
            [("clock", f"This report was filed {days_late} days after the trip ended.")],
            rule=f"Disputes can be filed up to {CLAIM_WINDOW_DAYS} days after a trip.",
        )
    rule = (
        "When the evidence a report needs is missing, it's declined rather than decided, "
        "so it can be sent again with that evidence."
    )
    if no_photo:
        fact = (
            "No photo was attached to this report, so it couldn't be reviewed."
            if c.inp.case_file is None
            else "The photo attached to this report couldn't be found, so it couldn't be reviewed."
        )
        return _Copy(
            "neutral", "We need a photo to continue",
            "Cleaning fees need at least one photo of the mess. This isn't a decision "
            "against you.", [("camera", fact)], rule=rule, can_refile=True,
        )
    return _Copy(
        "neutral", "We need more evidence to continue",
        "This isn't a decision against you. You can send the report again with more evidence.",
        rule=rule, can_refile=True,
    )


# --- decided: route deviation --------------------------------------------------------


def _route(c: _Case) -> _Copy:
    cmp = c.ev.get(ROUTE_COMPARISON)
    matching = _matching_traffic(c)
    facts = _route_distance_fact(c, upheld=c.upheld)
    if c.upheld:
        amount = c.amount() or (cmp or {}).get("refund_if_unjustified") or None
        facts += _no_closure_fact(c) if not matching else []
        if c.rider_view:
            head = f"You'll get {money(amount)} back" if amount else "You'll get a refund"
            copy = _Copy("good", head, "Refund approved for the extra distance on your trip.",
                         facts)
            copy.money = _money_line(c, receiving=True)
        else:
            head = f"{c.other} gets {money(amount)} back" if amount else f"{c.other} gets a refund"
            copy = _Copy("neutral", head,
                         "The refund covers only the extra distance on this trip.", facts)
        copy.rule = _route_rule(cmp, upheld=True)
        return copy

    under = cmp is not None and cmp["extra_pct"] < ROUTE_NO_MERIT_BELOW_PCT
    if under:
        facts.append(("info", (
            f"Routes up to {ROUTE_NO_MERIT_BELOW_PCT:.0f}% longer count as normal variation, "
            "so no refund applies."
        )))
    if matching:
        noun = _TRAFFIC_NOUN.get(matching, ("A traffic incident",))[0]
        trip = "your trip" if c.rider_view else "the trip"
        facts.append(("alert", (
            f"{noun} was recorded near the planned route during {trip}, which explains "
            "the detour."
        )))
    head = "No refund for this trip" if c.rider_view else "No refund on this trip"
    return _Copy("neutral", head, _route_denial_reason(under, matching), facts,
                 rule=_route_rule(cmp, upheld=False, matching=bool(matching)))


def _route_distance_fact(c: _Case, *, upheld: bool) -> list[tuple[str, str]]:
    cmp = c.ev.get(ROUTE_COMPARISON)
    if cmp is None:
        return []
    if cmp["extra_km"] <= 0:
        return [("route", "Your trip followed the fastest route." if c.rider_view
                 else "The route driven matched the fastest route.")]
    digits = 2 if cmp["extra_km"] < 1 else 1
    actual, optimal, extra = (f"{cmp[k]:.{digits}f} km" for k in
                              ("actual_km", "optimal_km", "extra_km"))
    pct = f"{cmp['extra_pct']:.0f}%"
    if not c.rider_view:
        return [("route", f"The route driven was {extra} ({pct}) longer than the fastest route.")]
    tail = (f"so you travelled {extra} ({pct}) further." if upheld
            else f"so the extra distance was {extra} ({pct}).")
    return [("route", f"Your trip was {actual}. The fastest route was {optimal}, {tail}")]


def _matching_traffic(c: _Case) -> str | None:
    """The type of the first traffic event that explains a detour, if any."""
    cmp = c.ev.get(ROUTE_COMPARISON) or {}
    for ref in cmp.get("matching_traffic_events", []):
        return c.ev.get(ref, {}).get("type") or "unknown"
    return None


def _no_closure_fact(c: _Case) -> list[tuple[str, str]]:
    if not c.rider_view:
        return [("alert", "No road closure was recorded on that road at the time, so the "
                          "detour couldn't be confirmed.")]
    if any(w in text for text in c.chat("driver") for w in _CLOSURE_WORDS):
        return [("alert", "The driver mentioned a road closure, but no closure was recorded "
                          "on that road at the time.")]
    return [("alert", "No road closure or roadworks were recorded on the route at the time.")]


def _route_denial_reason(under: bool, matching: str | None) -> str:
    explains = _TRAFFIC_NOUN.get(matching or "", (None, "a recorded incident explains"))[1]
    if under and matching:
        return f"The route was within the normal range, and {explains} the detour."
    if under:
        return "The route was within the normal range."
    if matching:
        return f"{explains[0].upper()}{explains[1:]} the detour."
    return "The evidence didn't show an unexplained detour."


def _route_rule(cmp: dict | None, *, upheld: bool, matching: bool = False) -> str | None:
    # The 10% / 25% tiers and the refund formula are this project's own rule (Policy doc
    # §2), not Ryde-sourced: no real Ryde threshold exists.
    low, high = f"{ROUTE_NO_MERIT_BELOW_PCT:.0f}%", f"{ROUTE_FULL_MERIT_ABOVE_PCT:.0f}%"
    if cmp is None:
        return None
    if upheld:
        if cmp["extra_pct"] > ROUTE_FULL_MERIT_ABOVE_PCT:
            return (f"When a trip is more than {high} longer than the fastest route and nothing "
                    "on record explains it, the fare for the extra distance is refunded in full.")
        if cmp["extra_pct"] >= ROUTE_NO_MERIT_BELOW_PCT:
            return (f"When a trip is {low} to {high} longer than the fastest route and nothing "
                    "on record explains it, half the fare for the extra distance is refunded.")
        return None
    if cmp["extra_pct"] < ROUTE_NO_MERIT_BELOW_PCT:
        return (f"Detours under {low} longer aren't refunded. A recorded closure or roadworks "
                "on the route also justifies a detour.")
    if matching:
        return ("A recorded closure or roadworks on the route justifies a detour, so the extra "
                "distance isn't refunded.")
    return (f"The extra distance is refunded only when a trip is at least {low} longer than "
            "the fastest route and nothing on record explains it.")


# --- decided: no-show ----------------------------------------------------------------


def _no_show(c: _Case) -> _Copy:
    # The $4.50 fee and the grace periods are Ryde-sourced; the 100 m arrival radius is
    # this project's own test for "the driver arrived" (Policy doc §3).
    prox = c.ev.get(PICKUP_PROXIMITY)
    reached = prox["reached_pickup"] if prox else None
    fee = c.amount() or no_show_fees((c.ev.get("PAYMENT") or {}).get("add_on_fees") or [])
    fee_s = f"{money(fee)} " if fee else ""
    rider_filed = c.inp.complainer_role == "rider"
    waived = c.upheld == rider_filed  # a rider wins a waiver; a driver loses the fee
    facts = _pickup_facts(c)
    rule = (
        f"A no-show fee only applies if the driver arrived within {PICKUP_ARRIVAL_RADIUS_M} m "
        "of the pickup, waited the required time, and tried to reach "
        + ("you." if c.rider_view else "the rider.")
    )
    if waived:
        not_met = "The conditions for a no-show fee weren't met."
        if c.rider_view:
            sub = "The driver never reached your pickup point." if reached is False else not_met
            copy = _Copy("good", f"Your {fee_s}no-show fee is waived", sub, facts, rule)
            copy.money = _money_line(c, receiving=True, amount=fee or None)
            return copy
        sub = "Your GPS shows you hadn't reached the pickup point." if reached is False else not_met
        return _Copy("neutral", "The no-show fee can't be charged", sub, facts, rule)
    head = f"The {fee_s}no-show fee stands"
    if c.rider_view:
        sub = ("The driver reached your pickup point, so the fee applies." if reached
               else "The evidence supports the fee.")
        return _Copy("neutral", head, sub, facts, rule)
    sub = ("Your GPS shows you reached the pickup point." if reached
           else "The evidence supports the fee.")
    return _Copy("good", head, sub, facts, rule)


def _pickup_facts(c: _Case) -> list[tuple[str, str]]:
    prox = c.ev.get(PICKUP_PROXIMITY)
    if prox is None:
        return []
    radius = prox["arrival_radius_m"]
    if prox["reached_pickup"]:
        return [("pin", "The driver's GPS shows they reached your pickup point." if c.rider_view
                 else "Your GPS shows you reached the pickup point.")]
    gap = distance_m(prox["closest_approach_m"])
    facts = [
        ("pin", f"The driver's GPS never came closer than {gap} to your pickup point."
         if c.rider_view else f"Your closest position was {gap} from the pickup point."),
        ("info", f"A driver has to arrive within {radius} m of the pickup before a no-show "
                 "fee can apply." if c.rider_view
         else f"A no-show fee applies only after arriving within {radius} m and waiting the "
              "required time."),
    ]
    if any(w in text for text in c.chat("driver") for w in _ARRIVED_WORDS):
        facts.append(("msg", "The driver's message saying they'd arrived doesn't match their GPS."
                      if c.rider_view else "Your message saying you'd arrived doesn't match "
                                           "your GPS."))
    return facts


# --- decided: property damage --------------------------------------------------------


def _damage(c: _Case) -> _Copy:
    facts = _photo_facts(c)
    # The $40 / $120 / $200 tiers are Ryde's real "up to" caps; charging the scheduled
    # amount on a photo alone is this project's own rule (Policy doc §4).
    rule = (
        "A cleaning fee needs at least one photo, and the fee follows what it shows: "
        f"{money(PROPERTY_DAMAGE_TIERS['minor'])} for a spill or crumbs, "
        f"{money(PROPERTY_DAMAGE_TIERS['moderate'])} for mud, dirt or stains, "
        f"{money(PROPERTY_DAMAGE_TIERS['severe'])} for vomit."
    )
    amount = c.amount()
    fee_s = f"{money(amount)} " if amount else ""
    driver_filed = c.inp.complainer_role == "driver"
    fee_awarded = c.upheld == driver_filed
    if fee_awarded:
        if c.rider_view:
            sub = (f"{c.other}'s photo shows a mess that needs cleaning." if driver_filed
                   else "The evidence supports the cleaning fee.")
            return _Copy("neutral", f"A {fee_s}cleaning fee applies", sub, facts, rule)
        copy = _Copy("good", f"You'll receive a {fee_s}cleaning fee",
                     "Your photo supports the cleaning fee.", facts, rule)
        copy.money = _money_line(c, receiving=True)
        return copy
    sub = "The evidence didn't support a cleaning fee."
    if c.rider_view:
        return _Copy("good", "You won't be charged a cleaning fee", sub, facts, rule)
    return _Copy("neutral", "No cleaning fee for this trip", sub, facts, rule)


def _photo_facts(c: _Case) -> list[tuple[str, str]]:
    photos = c.inp.case_file.photos if c.inp.case_file else []
    if not photos:
        return []
    whose = "Your photo" if c.complainer else f"{c.other}'s photo"
    if len(photos) > 1:
        whose += "s"
    best = _best_photo(photos)
    if best is None:
        return [("camera", f"{whose} couldn't be checked automatically, so a person will look.")]
    a = best.analysis
    verb = "show" if len(photos) > 1 else "shows"
    if a.tier in PROPERTY_DAMAGE_TIERS:
        mess = _MESS.get(a.mess_type, "a mess")
        extent = _EXTENT.get(a.extent, "")
        return [("camera", f"{whose} {verb} {mess} {extent}. That's the {a.tier} tier: "
                           f"{money(PROPERTY_DAMAGE_TIERS[a.tier])}.".replace("  ", " "))]
    if a.tier == "none":
        return [("camera", f"{whose} {'don' if len(photos) > 1 else 'doesn'}'t show a mess "
                           "that needs cleaning.")]
    if not a.shows_vehicle_interior:
        return [("camera", f"{whose} {'don' if len(photos) > 1 else 'doesn'}'t clearly show the "
                           "inside of the car.")]
    return [("camera", f"{whose} couldn't be matched to a cleaning tier.")]


def _best_photo(photos: list[EvidencePhoto]) -> EvidencePhoto | None:
    analysed = [p for p in photos if p.analysis]
    if not analysed:
        return None
    return max(analysed, key=lambda p: _TIER_ORDER.index(p.analysis.tier))


# --- shared lines --------------------------------------------------------------------


def _hearing_facts(c: _Case) -> list[tuple[str, str]]:
    """Who was heard, and whether a person signed off."""
    facts: list[tuple[str, str]] = []
    if c.complainer and c.inp.has_response:
        facts.append(("msg", f"{c.other} replied, and both sides were weighed before the "
                             "decision."))
    elif not c.complainer:
        facts.append(("scale", "Your reply was argued by an advocate on your side before the "
                               "decision." if c.inp.has_response
                      else "You didn't reply, so the case was decided on the trip records."))
    if c.decision and c.decision.human_ratified:
        facts.append(("user", "A specialist reviewed this case and made the final decision."))
    return facts


def _money_line(c: _Case, *, receiving: bool, amount: float | None = None) -> str | None:
    """Where the money goes, for the party receiving it. None if nothing moves."""
    amount = amount or c.amount()
    if not receiving or not amount or c.decision is None:
        return None
    remedy = c.decision.remedy
    if remedy.type == "compensation_credit" or remedy.destination == "ryde_credit":
        return f"The {money(amount)} is added to your account as credit."
    if remedy.destination == "driver_payout":
        return f"The {money(amount)} is added to your payout."
    return f"The {money(amount)} goes back to your original payment method."
