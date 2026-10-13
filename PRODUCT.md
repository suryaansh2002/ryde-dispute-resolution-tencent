# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript, moving to Tailwind CSS + shadcn/ui (Radix). The user decided this on 2026-10-13. Static bundle on Vercel; FastAPI + SSE backend on Render. Before the React rebuild, an interactive HTML prototype is made and signed off.

## Users

- **Hackathon judges (primary).** They evaluate the Tencent hackathon (Ryde track) submission through a recorded demo video, a live presentation, and their own exploration of the live URL. Their job is to judge whether the AI agents reason fairly and transparently from evidence, and whether the product is real. They need to understand it within minutes.
- **Riders and drivers** (the story's protagonists). They file a dispute about a trip, or answer one filed against them, then see the outcome. They use a phone.
- **Support reviewers (L2).** They work a queue of cases the system escalated (low confidence, high-value fees, repeat filers, compliance vetoes) and every safety report. They ratify or override the AI recommendation with a reason.

## Product Purpose

RydeResolve investigates ride-hailing disputes in three categories: Route Deviation, No-Show Charge and Property Damage. It produces evidence-grounded, symmetric decisions. Safety reports always go to a person and are never decided by AI. Success means each dispute gets a fair, explainable outcome quickly, routine cases need no human, and anything uncertain, high-value, repeated or safety-related reaches a person.

## Positioning

An adversarial hearing rather than a single model's opinion:
- Two AI advocates, one per party, argue from the identical evidence file.
- A Judge rules without ever seeing the complaint text.
- Plain-code gates (prevention rules, escalation gate, compliance check) decide what an AI may finalise.
- Every finding cites a real evidence item, and policy amounts are computed in code, not by the model.

## Operating Context

- **Filing a dispute:** filed against a specific trip, with the trip's GPS trace, planned vs driven route, fare breakdown, in-app chat and photos as evidence.
- **The other party:** gets to respond before the hearing.
- **The live trace:** pipeline events stream live over SSE, in this order: Triage → Prevention rules → Evidence Collection (+ Image Analysis) → Rider and Driver Advocates in parallel → Judge → escalation gate → compliance → decided, or human review.
- **The golden run:** a 22-case labelled suite scores accuracy (latest 22/22).
- **Demo formats:** a recorded video (5–8 min), a live presentation, and judges exploring alone.

## Capabilities and Constraints

- Roles are separate apps: a landing page, a Rider app and a Driver app (phone frame), a Support console (desktop) and an AI trace view for judges (desktop).
- Outcomes:
  - claim upheld (incl. partial);
  - claim denied;
  - declined for insufficient evidence (distinct from denied; the claimant can refile);
  - sent to human review;
  - safety: routed to a person at triage.
- Refunds are paid to the original payment method; cleaning fees go to the driver's payout.
- Evidence refs are citable IDs: `MSG-0459`, `EV-0035`, `TRAFFIC-01`, `PAYMENT`, `GPS-TRACE`, `ROUTE-COMPARISON`, `PICKUP-PROXIMITY`, `PROFILE-*`, and policy `POL-02` to `POL-04`.
- Riders and drivers must not see the other party's behaviour profile.
- Policy figures must stay labelled as real Ryde-sourced or our own:
  - **Real, Ryde-sourced:** the $4.50 no-show fee, the $40/$120/$200 cleaning tiers, and the 30-day window.
  - **Our own:** the 10%/25% route tiers, the 100 m arrival radius and the 2 km traffic match.
- Open decision: whether the complainee sees verified evidence after L2 review, or only the outcome.

## Brand Commitments

- **Name:** "RydeResolve", its own brand, positioned as "a dispute resolution system for Ryde".
- **No Ryde marks:** no Ryde logo, colours or app styling, so it can never be mistaken for an official Ryde product.
- **Voice:** plain, calm and respectful, including when a claim is denied. Never accusatory, and no legal or AI jargon in rider or driver views.

## Evidence on Hand

- Real pipeline output in the Neon DB for 22 golden-run cases (`CASE-0137` to `CASE-0158`), including claims, responses, advocate arguments, Judge findings, escalation reasons, trace events, token usage and Image Analysis findings.
- 200 synthetic trips with route geometry, GPS fixes, fares and chat.
- Synthetic damage photos (`backend/data_generation/pipeline/photo_render.py`).
- Golden-run accuracy: 22/22. Token usage baseline: about 70–110K input tokens per fully argued case.
- **Absent, never to be fabricated:** real users, testimonials, customers, partners, production traffic, real Ryde data, and cost-savings figures.

## Product Principles

1. **Show the work.** Every step, citation and rule is visible to the people evaluating the system; nothing is a black box.
2. **Fair before fast.** Both sides are heard before any decision, and losing parties see why, with the rule applied.
3. **People handle what matters.** Uncertainty, high stakes, repeat patterns and safety go to a human, and the interface makes that hand-off obvious.
4. **Plain language for parties, full depth for experts.** The same facts are told at different depths per role.
5. **Demo-proof.** Every screen reads at video resolution, works without waiting on a live model, and never dead-ends.

## Accessibility & Inclusion

- WCAG 2.2 AA contrast.
- Status is never conveyed by colour alone.
- Respects `prefers-reduced-motion`.
- Full keyboard operation (the reviewer console is keyboard-first).
