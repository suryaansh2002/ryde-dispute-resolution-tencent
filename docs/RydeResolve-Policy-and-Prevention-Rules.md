# RydeResolve — Dispute Resolution Policy & Prevention Rules (v3 — Part 1 reconciled against real Ryde figures)

> **2026-10-11 additions, all labelled as our own rules:**
> - §2: "along the optimal route" means within 2 km of the planned route, during the trip.
> - §4: the photo, via Image Analysis, sets the fee tier.
> - §4: the photo-only fee rule.
> - The 2-hour photo window was dropped.

**What this is:** the actual content behind two things the system design references but never spelled out — the `policy_chunks` corpus (§5 of the system design doc) that the Rider/Driver Advocates and Judge search via RAG (Part 1, below), and the deterministic "Prevention rules" box that now runs after the Triage Agent and before the Evidence Collection Agent in the finalized flow (Part 2, below).

**Important caveat, stated plainly, per part:** **Part 1 (Policy)** has now been reconciled against the real-Ryde-source research (`RydeResolve-Real-Source-Reference.md`) — every dollar figure, time window, and fee schedule that Ryde actually publishes has been swapped in for the earlier draft's invented placeholders. What hasn't changed, because no real source exists to change it to: Route Deviation has no real Ryde tolerance-threshold or refund formula at all, and the No-Show GPS-arrival radius and Property Damage photo-submission window are also unsourced. Those remain our own design choices, and are labeled as such, inline, everywhere they appear — this document never lets a real figure and an invented one sit side by side looking equally authoritative. **Part 2 (Prevention Rules)** was already reconciled in the previous revision: three of its six rules are grounded in real, sourced Ryde material (linked per-rule below), and the other three remain honestly-labeled system-design choices, not Ryde facts. Nothing below is presented as more authoritative than it actually is.

---

## Part 1 — Ryde Dispute Resolution Policy

*(This is the document that gets chunked by heading into `policy_chunks` for pgvector retrieval — the Policy RAG tool carried by the advocates and the Judge, §6, searches this.)*

### 1. Purpose and General Principles

This policy governs how disputes between riders and drivers are resolved on the Ryde platform. It applies to Route Deviation, No-Show Charge, and Property Damage claims (Safety Incidents are handled separately — see §5 below, they are never resolved under this policy).

Four principles apply across every category:

- **Good faith first.** Claims are assessed on their merits, not on which party filed first or how forcefully a claim is worded.
- **Symmetric treatment.** The same evidentiary standard applies to both riders and drivers making comparable claims — a rider alleging a driver's fault and a driver alleging a rider's fault face the same bar of proof.
- **Evidence over assertion.** A claim is decided on trip data, chat logs, timestamps, photos, and account history — not on the persuasiveness of either party's account alone.
- **Proportionality.** Remedies scale with the severity and certainty of the finding. Minor, ambiguous cases get minor, reversible remedies; only clear-cut, well-evidenced cases justify larger remedies.

### 2. Route Deviation Disputes

**Grounding, stated up front:** this is the weakest-sourced category in the whole policy. Real Ryde sources confirm that fare *recalculates* when a rider requests a destination change mid-trip and the driver accepts it (a **$3.00** add/edit-destination fee applies, shown on the receipt), and that "overcharging riders or manipulating fares" is treated internally as a fraud/account-suspension matter (Driver-Partner Handbook, pp.11–13) — but neither source, nor anything else found, defines a tolerance threshold, a percentage, or a refund formula for the specific case this section actually governs: a driver taking an **unrequested** longer route. That dispute type has no real Ryde-published process at all. Everything below the fee figure is therefore our own invented design, kept because the demo needs an adjudicable rule, not because it reflects Ryde's actual policy — flagged plainly rather than dressed up as sourced.

**Definition:** a claim that the actual route taken differed materially from the optimal route, without the rider's request or the driver's disclosed justification, resulting in an inflated fare, extended trip time, or both. (This is distinct from a rider-requested, driver-accepted destination change mid-trip — that's Ryde's real, documented $3.00 add/edit-destination flow, not a dispute, and isn't adjudicated here.)

**Tolerance thresholds** (not Ryde-sourced — our own invented tiering, since no real threshold exists), measured as extra distance versus the platform's computed optimal route for the same pickup/dropoff pair:

| Deviation | Outcome |
|---|---|
| Under 10% extra distance | No merit — normal route variance (traffic routing, one-way streets). No refund. |
| 10%–25% extra distance | Partial merit — refund the fare difference attributable to the extra distance/time, unless justified (see below). |
| Over 25% extra distance | Full merit — refund the entire deviation-attributable portion of the fare, unless justified. |

**Justified deviation exceptions:** a deviation is justified, and no refund is owed regardless of magnitude, if any of the following is evidenced:

- A recorded road closure or traffic incident along the optimal route during the trip window (checked against `traffic_events`).
  *(Not Ryde-sourced, our own test)*: "along the optimal route" means within 2 km of the planned route geometry, with the incident's time window overlapping the trip. It is computed in code, so no agent judges the distance.
- The rider requested the detour in the chat log (e.g., an added stop, a specific route preference) — note that a *disclosed and accepted* destination change should route through Ryde's real $3.00 add/edit-destination mechanism above rather than reach this dispute flow at all; this exception exists for the case where the request was informal (chat only, no in-app flow used).
- A safety-related detour (construction, accident scene, flagged unsafe area).

If the driver claims a justification but no corresponding evidence exists (no matching `traffic_events` entry, nothing in the chat log), the claim is treated as unjustified — an unsupported assertion doesn't override the evidentiary standard in §1.

**Refund calculation** (not Ryde-sourced — our own formula): `refund = (actual_fare − fare_at_optimal_route) × merit_fraction`, where `merit_fraction` is 0.5 for the 10–25% tier and 1.0 above 25%.

### 3. No-Show Charge Disputes — best-sourced category; real figures throughout except the GPS-radius check

**Definition:** a claim disputing a cancellation or waiting-time fee — either a rider disputing a fee charged when they say the driver never arrived, or a driver disputing a rider's claim when the driver says they waited as required.

**The real fee and grace-period structure**, per Ryde's Cancellation and Waiting Time Policy:

| Trip type | Free cancellation window | Grace period once inside that window | Fee if exceeded |
|---|---|---|---|
| On-Demand | Within 3 minutes of matching | — | **$4.50** |
| Advanced (pre-booked) | More than 15 minutes before pickup | 3 minutes once inside the 15-minute window | **$4.50** |

The same **$4.50** figure applies to both the cancellation fee and the driver's waiting-time fee — a driver may charge it after tapping "I'm Here" and waiting past 3 minutes, whether the rider eventually boards late or never shows at all. These are real, sourced amounts (help.rydesharing.com, Cancellation and Waiting Time Policy) — not illustrative.

**Driver no-show (rider's claim):** a cancellation fee is waived, and any fare charged is refunded in full, if the driver did not come within 100 meters of the pickup GPS coordinates at any point during the trip window — this is checked directly against the GPS trace, not either party's account. *(The 100-meter radius itself is not Ryde-sourced — no real article gives a distance threshold for "arrival." It's our own design choice, kept because the GPS trace needs some concrete proximity test to check against.)*

**Minimum wait time:** a driver may cancel and charge the no-show/waiting fee only after waiting at least **3 minutes** at the pickup point (On-Demand), or, for a pre-booked (Advanced) ride, only once the trip is within 15 minutes of the scheduled pickup and a further 3-minute on-site grace period has elapsed — both real, sourced windows, not invented. If the driver cancelled before the applicable wait elapsed, the fee is waived regardless of whether the rider was actually present — the driver bears the burden of waiting out the window.

**Rider no-show (driver's claim):** the fee stands if the driver's GPS trace shows arrival within 100 meters of pickup (our own proximity test — see above), the applicable minimum wait elapsed, and the chat log or call log shows an attempt to reach the rider.

**Dispute window:** a rider may dispute a cancellation or waiting-time fee within **30 days** of the trip via RydeHELP (real, sourced — Cancellation Fee Waiver Request / Waiting Fee Waiver Request articles); disputes filed after 30 days are not considered. This is also what Part 2's Rule 6 (claim window) is grounded in for this category.

### 4. Property Damage / Mess Disputes

**Definition:** a claim that a rider caused damage or mess (spills, stains, odor, physical damage) requiring a cleaning or repair fee.

**Cleaning/repair fee schedule** — real, sourced caps (help.rydesharing.com, "I made a mess in my driver's vehicle"; matched by Terms of Use Clause 11's $200 ceiling). These are stated as **"up to"** amounts, not fixed prices: Ryde "reviews photos, trip details, and cleaning receipts to determine appropriate amounts within applicable caps" — so the table below is the ceiling per tier, not an automatic charge:

| Severity | Example | Fee (up to) |
|---|---|---|
| Minor | Food/drink spillage or crumbs | $40 |
| Moderate | Bodily fluids or stains (mud, dirt, paint, cement, tar, oil) | $120 |
| Severe | Vomit | $200 |

**Evidence required:** at least one photo showing the damage/mess. A photo is treated as insufficient evidence (claim declined, not denied — see §6) if it's a duplicate of a photo used in a prior claim, or automated image analysis flags it as inconsistent with a genuine, unedited photograph. *(There is no photo-submission deadline. An earlier draft required the photo within 2 hours of trip completion. That was an invented placeholder with no Ryde source, and it was dropped on 2026-10-11 so that a claim filed later, still inside the 30-day claim window, isn't declined automatically. Prevention Rule 6's claim window handles staleness.)*

**Fee for a photo-only claim** *(not Ryde-sourced, our own rule)*: Ryde's real process sets an amount within the cap from photos and cleaning receipts. This system collects photos but not cleaning receipts. An upheld photo-only claim is therefore charged exactly the scheduled amount for the tier the evidence supports: $40 minor, $120 moderate, $200 severe. A missing receipt is not a reason to decline a claim that has a valid photo. Where a cleaning receipt does exist, it can only lower the fee to the receipt amount.

**Which tier the photo supports** *(not Ryde-sourced, our own rule; the tier table itself is Ryde's)*:
- Automated image analysis says what each photo shows: the kind of mess and how much it covers. The tier follows from the table above: food/drink spillage or crumbs is minor; mud, dirt, stains or bodily fluids other than vomit are moderate; vomit is severe.
- The tier is set by what the photos show, not by what the claim says. A larger mess claimed than photographed doesn't raise the fee.
- If the photos show no mess, no cleaning fee is supported.
- If the analysis is unclear, or not confident, a human reviewer decides the tier. Mirroring Ryde's real appeals process for Vehicle Damage Claims, a receipt must state the cleaning company's name, contact details, cleaning date, and an authorized signature.

**Burden of proof:** the party claiming damage bears the burden. A driver's claim with no photo, or a photo that fails the checks above, is declined for insufficient evidence — the default is not "unresolved in the rider's favor," it's "declined, refile with adequate evidence" (§6). Real-world non-payment consequence, for context (not itself part of this system's remedy set): Ryde places the paying party's account on hold until a cleaning fee is settled.

### 5. Safety Incidents (not resolved under this policy)

Any claim flagged as a Safety Incident — by category selection at filing, or by the Triage Agent's classification — is never adjudicated by this policy or by the Rider/Driver Advocate or Judge agents. It routes directly to a human reviewer (the L2 queue) regardless of the evidence available or the system's confidence. This is a structural rule, not a policy judgment call — it's enforced in code (see Part 2, Rule 3), not reasoned about by any agent.

### 6. Evidence Sufficiency Standard

A claim is **declined** — not decided against either party — when the evidence required for its category (per §2–§4 above) isn't present or doesn't meet the stated bar. "Declined for insufficient evidence" is a distinct outcome from "claim denied": it means the claimant can refile with better evidence, not that the claim was heard and rejected on the merits.

### 7. Remedy Types and Caps

Available remedies: full refund, partial refund (fare-difference-based, per §2), compensation credit, cleaning/repair fee charge (per §4), no-show fee waiver, no action. Every remedy is capped at the total fare of the trip in question, except cleaning/repair fees, which follow the schedule in §4 independent of fare size.

### 8. Escalation Triggers

A decision routes to human review (L2) instead of being finalized automatically when:

- The category is Safety Incident (§5 — always, unconditionally).
- The Judge's confidence in its ruling falls below 0.6 (ties to the two-phase escalation gate, §6.1 of the system design).
- Either party involved has 3 or more disputes filed against them in the preceding 30 days (ties to Prevention Rule 5's velocity/repeat-filer flag, Part 2 below — there is no separate Fraud & Bad-Faith Detection Agent in the finalized architecture; this flag is the only mechanism watching for the pattern) — flagged for human review even if the individual case looks clear-cut, since a pattern across cases is a signal an isolated per-case decision can't see.

---

## Part 2 — Prevention Rules (deterministic, run after Triage, before the Evidence Collection Agent)

**Status: finalized against the v9 system architecture.** These are RydeResolve's own deterministic gates — not a leaked or reverse-engineered Ryde ruleset, because no such document is public. What's changed since the v1 draft: three of six rules are now grounded in real, sourced Ryde material (linked below — see `RydeResolve-Real-Source-Reference.md` for the full fetch); the safety gate now explicitly reads the Triage Agent's `is_safety` output per the finalized flow (system design §6), rather than category-selection-at-filing alone; and the Fraud & Bad-Faith Detection Agent has been removed from the architecture entirely, which makes Rule 5 (velocity/repeat-filer) the *only* remaining mechanism catching repeat filers — it used to have a dedicated agent behind it, and now it doesn't.

| # | Rule | Trigger | Action | Grounding |
|---|---|---|---|---|
| 1 | Duplicate claim | A new claim is filed on a `trip_id` that already has an open or decided case | Reject the new filing; point to the existing case | Our own system design — basic claim-integrity check. No real Ryde article covers filing two disputes on the same trip, so this isn't Ryde-sourced |
| 2 | Malformed request | Required fields missing — `trip_id` doesn't exist, category isn't one of the three in-scope values (Route Deviation, No-Show Charge, Property Damage), or the claimant isn't a party to the trip | Reject before a case is opened at all | Our own system design — basic data integrity, not Ryde-sourced |
| 3 | Safety hard gate | The Triage Agent's `is_safety` output is `true` (system design §6) | Bypass all agent reasoning; route straight to `safety_bypassed` → L2 queue | Our own architecture principle — mandatory, not optional. What a rider/driver actually does to report a safety issue *is* real and documented (995 for emergencies, RydeHELP, drivers must report "within 1 hour" per Ryde's real accident-reporting article) — this rule is what guarantees that report gets routed to a human, never an LLM adjudicator |
| 4 | Evidence-presence gate | Category has a hard evidence requirement and it's missing at filing | Immediately return "declined — insufficient evidence" without running any agent | **Real-sourced for Property Damage.** Ryde's actual help-center article ("I made a mess in my driver's vehicle") states Ryde "reviews photos, trip details, and cleaning receipts" before approving a cleaning fee — requiring at least one photo before this claim type reaches an agent reflects Ryde's real process. For Route Deviation and No-Show, the equivalent "evidence" (GPS trace, fare breakdown) is captured automatically by the Evidence Collection Agent rather than submitted by the claimant, so this gate rarely fires for those two categories in practice |
| 5 | Velocity / repeat-filer flag | The same rider or driver has 3+ disputes filed against them in the trailing 30 days | Tag the case for review in `behavior_profiles`; does not auto-decide, only flags | Standard abuse-prevention pattern, not Ryde-sourced. **More load-bearing than in v1**: with Fraud & Bad-Faith Detection removed from the roster, this deterministic flag is now the only thing watching for repeat-filer patterns — the 3-in-30-days threshold is still an unresearched placeholder, worth a deliberate decision now that nothing backs it up |
| 6 | Claim window | Dispute filed more than N days after trip completion | Auto-decline as stale | **Partially real-sourced.** Ryde's actual Cancellation Fee Waiver Request and Waiting Fee Waiver Request articles both give riders **30 days** from the trip to dispute a cancellation/waiting fee via RydeHELP — real, sourced, specific to the No-Show category. No real Ryde article states a filing window for Property Damage or Route Deviation; extending the same 30-day window to those two categories is our own consistency choice, not a sourced fact |

All six still run as plain Python before any agent is invoked — no model call, no `pydantic_ai.Agent` — keeping "prevented" cases free (no model cost, no latency) and fully deterministic to test. Whether any of these six needs LLM assistance instead (semantic duplicate matching, safety-language detection beyond keyword/regex) is an open question carried over from the system design doc (§6.2) — unresolved by design, not by oversight.

---

## Open items for you to weigh in on

**Resolved by this reconciliation pass** (kept here briefly so it's clear what changed, not just asserted): Property Damage's fee tiers now match Ryde's real "up to" caps ($40/$120/$200) instead of the earlier invented $20/$60/$150; No-Show's fee, grace periods, and dispute window are now Ryde's real figures ($4.50, 3-min/15-min grace, 30-day RydeHELP window) instead of the earlier invented 5-min/10-min/7-day numbers; Route Deviation's real $3.00 destination-change fee and its distinction from the (unsourced) unauthorized-deviation dispute are now stated explicitly rather than left implicit.

**Still genuinely open — nothing above resolves these, they're design decisions, not research gaps:**

- Route Deviation's tolerance thresholds (10%/25%) and refund formula have no real Ryde number behind them at all — confirmed by the source research, not just unresearched. They're a necessary invention to make the category adjudicable; worth deciding whether to keep this shape or simplify it, but there's no "real" version to switch to.
- The No-Show GPS-arrival radius (100 meters) is likewise our own invented proximity test — no real source gives a distance.
- ~~Property Damage's photo-submission window (2 hours)~~ — **resolved 2026-10-11: dropped.** A valid photo is sufficient regardless of timing; the 30-day claim window covers staleness. Replaced by the photo-only fee rule in §4 (also our own, labelled as such).
- Rule 5's threshold (3 disputes / 30 days) carries real weight now that Fraud & Bad-Faith Detection isn't in the architecture as a backstop — worth a deliberate decision rather than leaving it as a placeholder.
- The safety keyword/regex list for Rule 3 still isn't drafted — that needs an actual term list (assault, threat, weapon, unsafe driving, etc.) before it's implementable; want me to draft that too, or is Triage's `is_safety` output enough for the demo?
- Rules 1 and 2 have no real Ryde figure to check against (there isn't one) — internally consistent, not researched, same as before.
