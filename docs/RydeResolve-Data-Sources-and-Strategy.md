# RydeResolve — Data Sources & Generation Strategy (v2 — finalized)

**Status note, stated plainly:** this discussion happened earlier but was never committed to a file — the conversation converged on four sourcing decisions and a generation pipeline, then moved on before it got written up. v1 was that write-up, updated for the finalized agentic flow (system design doc §6) and the real Ryde figures gathered since (`RydeResolve-Real-Source-Reference.md`). This v2 closes the one real inconsistency v1 flagged and left open: the Policy & Prevention Rules doc's Part 1 has now been reconciled to the same real figures this document already used, so the `policy_chunks` corpus and the generated dataset agree with each other. Nothing else in this document has changed in substance. **Post-v2 patch:** the evidence-photo storage backend in §1's inventory table now reads Neon Object Storage rather than Cloudflare R2, following the system design doc's swap (§9) — a naming update only, no change to this document's sourcing decisions or pipeline.

---

## 0. Scope

This covers: which data points the finalized architecture actually needs (per system design §5's forward-pointer note), where each one comes from (real API, fully synthetic, or semi-dummy), the new Postgres tables required beyond what system design §5 already defines, and the pipeline that turns all of this into a demo-ready dataset. It does not cover application code (orchestrator, agents, frontend) — that's the development roadmap — and it does not re-litigate the dispute policy content itself, which lives in the Policy & Prevention Rules doc.

---

## 1. Data inventory — what the architecture actually needs

| Data point | Used by | Where it lives |
|---|---|---|
| GPS points / telemetry | Evidence Collection Agent (system design §6); Route Deviation and No-Show adjudication | **New:** `trips` |
| Fare / payment breakdown | Evidence Collection Agent; Route Deviation refund math | **New:** `payments` |
| Chat / call logs | Evidence Collection Agent; advocates' Evidence Lookup tool | **New:** `chat_messages` |
| Traffic events (closures, incidents) | Route Deviation "justified deviation" exceptions | **New:** `traffic_events` |
| User / account records | Identifies complainer vs. complainee; anchors `behavior_profiles` | **New:** `users` |
| Historical behavior profiles | Evidence Collection Agent; Judge; Prevention Rule 5 (velocity/repeat-filer) | Already exists — `behavior_profiles` (system design §5) |
| Evidence photos | Property Damage claims; the advocates' Image Analysis tool | Already exists — `evidence` (metadata) + Neon Object Storage (bytes) |
| Policy corpus | Policy RAG tool (advocates + Judge) | Already exists — `policy_chunks`; content is the Policy doc's Part 1 |
| Golden cases | Golden-case suite, dashboard pass-rate | Already exists — `golden_cases` |

Everything in the "New" column is what this document actually needs to specify; the rest is already defined.

---

## 2. The four sourcing decisions

| # | Data type | Decision | Why |
|---|---|---|---|
| 1 | Route geometry (what a real trip's road path looks like) | **Real** — Singapore's **OneMap** API (government-run, free, no card required) computes actual road-network routes between real lat/lng pairs | Gives geographically real, driveable routes without needing actual Ryde trip data, which we don't have access to |
| 2 | Traffic events (closures/incidents used to justify a route deviation) | **Fully synthetic** — a simple probabilistic generator, not a live feed | LTA DataMall (Singapore's real transport open-data API) was considered and rejected: it's real-time-traffic-shaped infrastructure that's unnecessary complexity for a fixed, reproducible demo dataset. A synthetic generator gives full control over which deviations are "justified" and which aren't — exactly the mix the policy logic needs to be exercised against |
| 3 | Property Damage photos | **Mixed** — real creative-commons/stock photos of messy or damaged car interiors where available, supplemented with AI-generated images for severity tiers not otherwise covered | Needs to match the real Ryde fee tiers (spill/crumbs, bodily-fluid/stains, vomit — see §4 below) with visually plausible evidence, without needing actual Ryde-submitted photos |
| 4 | Chat logs, claim text, user/trip metadata | **Semi-dummy** — template-based generation with randomized parameters, not hand-written per case and not fully random either | Cheap to generate at the volume needed, structurally realistic (references the same GPS/fare/timestamp facts generated for that trip), and never implies it's real Ryde user data |

---

## 3. New Postgres tables

These sit alongside the tables system design §5 already defines, in the same Neon/pgvector instance.

**`users`** — `id`, `role` (rider / driver), `display_name`, `created_at` (account age), `rating`, `rating_trend`

**`trips`** — `id`, `rider_id`, `driver_id`, `pickup_lat/lng`, `dropoff_lat/lng`, `optimal_route_geometry` (from OneMap), `actual_route_geometry`, `gps_trace` (timestamped point array), `scheduled_at`, `completed_at`, `category_hint` (a generation-time label of which dispute type this trip is designed to exercise, if any — never visible to any agent, purely for building a balanced dataset)

**`payments`** — `id`, `trip_id`, `base_fare`, `platform_fee`, `taxes`, `total_fare`, `add_on_fees` (destination-change, cancellation, waiting — see §4), `payment_method`

**`chat_messages`** — `id`, `trip_id`, `sender_role`, `timestamp`, `text`

**`traffic_events`** — `id`, `near_lat/lng`, `time_window_start/end`, `type` (road_closure / accident / construction), `description`

`payments` is kept separate from `trips` rather than folded in, since a single trip can carry more than one fee event (base fare plus an add-on fee charged later), and keeping them separate makes the Route Deviation refund math (fare-at-optimal vs. fare-at-actual) a clean query rather than a set of nullable columns on `trips`.

---

## 4. Generation pipeline

1. **Trip population.** Generate roughly 200 trips using real Singapore-area pickup/dropoff coordinate pairs (sampled across a spread of neighborhoods for route variety).
2. **Route geometry.** Call the OneMap routing API per trip to compute the optimal route.
3. **Category assignment.** Label each trip, at generation time only, with a target category so the dataset is balanced — suggested starting split: ~40% clean (no dispute), ~20% each across Route Deviation, No-Show, Property Damage. Tunable once real usage patterns (or judge expectations) are clearer.
4. **Actual-route perturbation.** For trips labeled Route Deviation, generate a perturbed "actual route" that deviates from the optimal one by a configurable extra-distance amount. **Note:** the actual tolerance thresholds for what counts as a meritorious deviation are still an open, unresourced design question (flagged in the Policy & Prevention Rules doc — no real Ryde source gives a number here). This pipeline treats the perturbation magnitude as a tunable generation parameter, not a fixed fact, so it can be adjusted once that policy question is settled.
5. **Traffic events layering.** Probabilistically insert `traffic_events` correlated with deviated trips — deliberately including both cases where a deviation has a matching event (a justified deviation) and cases where it doesn't (unjustified), so the full policy branch gets exercised.
6. **GPS trace generation.** Interpolate timestamped points along each trip's actual route geometry at a fixed sampling interval, producing the `gps_trace` stored on `trips`.
7. **Fare/payment generation.** Compute `base_fare` from distance/time, plus the **real** Platform Fee tiers ($1.25 including GST for fares ≤$18, $1.47 above $18, per Ryde's actual fee schedule), plus taxes. Layer in add-on fees on trips designed to exercise them, using Ryde's real figures: a $3.00 destination-change fee, and $4.50 cancellation/waiting-time fees.
8. **Chat & claim text generation.** Template-based per category — for Route Deviation, some chat logs correctly reference a real `traffic_events` entry and some falsely claim one that doesn't exist (to exercise the "unsupported assertion" policy branch); for No-Show, messages reflect wait-time and contact-attempt patterns; for Property Damage, messages describe the mess/damage claimed.
9. **User & behavior-profile generation.** Create `users` with account age and rating; derive `behavior_profiles` rolling stats from the generated trip/dispute history. Deliberately seed a handful of repeat-filer profiles (3+ disputes in 30 days) to exercise Prevention Rule 5, and a few adverse-rating profiles to give the Judge something to reason about.
10. **Property Damage photo assignment.** Attach real or AI-generated photos matching Ryde's real fee tiers ($40 spill/crumbs, $120 bodily-fluid/stains, $200 vomit) to the relevant trips. *As built:* no real or AI-generated photo set was sourced, so each tier gets a procedurally rendered rear-seat photo (`photo_render.py`: coffee spill, mud, vomit, or clean). It's labelled synthetic, and Image Analysis grades it like any upload. Include a few deliberately insufficient cases — a missing photo, or one that fails the freshness/duplicate check — to exercise Prevention Rule 4 and the Image Analysis tool's rejection path.
11. **Golden-case labeling.** *As built:* 22 cases labelled automatically from the generator's ground truth. `POST /golden-run` scores the pipeline against them. Originally planned: hand-label 30–50 of the generated cases with an agreed correct outcome, spanning all three categories plus a few safety-flagged trips, populating `golden_cases` for the golden-case suite (system design §5).

---

## 5. Known open items

- **Resolved as of v2:** the Policy doc's Part 1 previously disagreed with the real figures already used here ($20/$60/$150 invented damage tiers vs. this doc's real $40/$120/$200; a 7-day invented claim window vs. the real 30-day one). Part 1 has now been reconciled — both documents use the same real figures, so `policy_chunks` and the generated dataset agree. See the Policy & Prevention Rules doc's v3 changelog for the specifics.
- **Route Deviation perturbation magnitude and the escalation-bucket contents** (system design §6.1) are both still open design questions with no real Ryde number behind them — and, per the now-reconciled Policy doc §2, this isn't a research gap, it's confirmed that no such number exists in any real Ryde source. This pipeline treats both as tunable configuration, not settled facts — don't read a specific number choice here as a policy decision.
- **The No-Show GPS-arrival radius (100m)** (the Property Damage 2-hour photo window was dropped 2026-10-11, Policy doc §4) used implicitly by this pipeline's generation logic (steps 6 and 10) are likewise our own invented design choices, not Ryde facts — confirmed unsourced by the same reconciliation pass. Fine as tunable generation parameters; just not to be read as policy.
- **OneMap API access details** (auth method, rate limits at this data volume) haven't been independently re-verified for this write-up — worth a quick check at build time rather than assuming the earlier discussion's read of it is still current.
