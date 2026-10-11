# RydeResolve — Execution Plan to Submission

**Status:** v1, 2026-10-11. **This replaces the day-by-day plan in the Development Roadmap** from here to submission. The roadmap's 14-day schedule has run out, and its Dev A / Dev B ownership split is suspended: the remaining work is one critical path, done in order, by whoever is free. Architecture facts still come from the System Design doc. This doc only covers sequencing.

**Before starting any item below, push whatever you have, even if it's half-done.** Two people building the same piece on unpushed branches is the most likely way to lose a day.

---

## 1. Where we are (as of this revision)

**Working, on `main`, CI green:**
- Schemas, Postgres migration (applied to the Neon dev branch), Prevention Rules.
- Triage Agent, Evidence Collection Agent, Rider/Driver Advocates, Policy RAG, Evidence Lookup.
- `POST /cases` runs the full intake (duplicate/malformed checks → Triage → safety hard-stop / claim window / repeat-filer flag → Evidence Collection) and stops at `awaiting_response`.
- `GET /cases/{id}` and `POST /cases/{id}/evidence` (upload to Neon Object Storage).
- Synthetic data pipeline with golden-case labelling (built, not yet run at full scale).

**Built since v1 of this doc (step 1):** the respondent's reply, the Judge, the escalation gate, the compliance check, stored decisions with a rendered decision document, and `GET /cases/{id}/decision`.

**Not built:**
- Live updates (SSE), the L2 queue, golden-run and Logfire.
- All of the frontend.
- Deployment.
- All submission materials.

## 2. Where we need to get to

A **live URL** where a judge:
1. picks a rider or driver persona,
2. files a claim,
3. watches the agents argue on the trace panel,
4. sees either a decision document or an escalation to a human reviewer (L2).

The submission also needs:
- a **public repo**,
- **CodeBuddy proof** (a hard gate: without it the project is not scored),
- a **5–8 minute demo video**,
- the **submission form copy** and an **architecture diagram**.

## 3. The path, in order

Each step unblocks the next. Estimates assume one person.

### Step 1 — Finish the decision path in the backend (~1 day) — ✅ DONE 2026-10-11

Verified with `backend/scripts/smoke_e2e.py` against real Neon + Groq. Route deviation → `decided` with the formula refund; repeat-filer no-show → `escalated`; property damage → `decided` with the $40 tier fee.

- `POST /cases/{id}/response`: the other party's reply. Stored, then it triggers adjudication.
- **Judge agent**: reads the case file and both advocates' arguments, never the raw complaint text. Read-only tools: Policy RAG, escalation-bucket lookup, request-L2.
- **Escalation gate** (deterministic): sends a case to L2 if confidence is below the threshold, *or* the case falls in an "always escalate" bucket, *or* the Judge asked for L2. The buckets are read from a lookup table, not hardcoded.
- **Compliance check** (deterministic): can veto a decision, never write one. A vetoed decision goes to L2.
- The decision is saved, a decision document is rendered, and `GET /cases/{id}/decision` returns both.
- Orchestrator: both advocates in parallel → Judge → gate → compliance → `decided` or escalated to L2.
- **Done when:** a real claim filed against the live backend comes back with a decision or an L2 escalation, for all three categories.

### Step 2 — Deploy a bare version early (~0.5 day) — 🟡 READY, needs one manual step

Done: `backend/Dockerfile` + root `render.yaml` Blueprint (Ohio, next to Neon), CORS, demo endpoints (`/demo/personas`, `/users/{id}/trips`, `/users/{id}/cases`), full 200-trip dataset in Neon. The container passes `scripts/smoke_e2e.py` locally. **Remaining, assigned to Dev B (@shiv0112) on his Render account:** follow [RydeResolve-Deploy-Backend.md](RydeResolve-Deploy-Backend.md) (create the service from the Blueprint, set secrets, run the smoke script against the live URL, check the live stream through Render's proxy).

- Dockerfile, backend on Render, CORS, health check confirmed on the live URL.
- Run the data generator at full scale (200 trips) against Neon.
- Small demo endpoints so the UI can list personas and their trips.

### Step 3 — Make it visible (~0.5 day) — ✅ DONE 2026-10-11

Logfire spans every agent run (configured at server startup). SSE: `/events/cases/{id}` replays a case's full trace and then streams live; `/events/l2` streams queue arrivals. Both are resumable via `Last-Event-ID`. Postgres stays the source of truth, woken by `pg_notify`. That's a deliberate change from the in-process queue: it also works across multiple workers. Pulled forward from step 4: the L2 backend (`GET /l2/queue`, `POST /l2/cases/{id}/ratify` with ratify/override; overrides still pass compliance). Verified on a real escalated case: streamed live, ratified, final.

- Logfire (`logfire.configure()` + `instrument_pydantic_ai()`).
- A trace event bus plus SSE endpoints (`/events/cases/{id}`, `/events/l2`). The events are already written to Postgres; they just need streaming.

### Step 4 — Frontend (~1.5 days) — ✅ BUILT 2026-10-11, deploy assigned to Dev B

`frontend/`: React + Vite + TypeScript (strict). Persona picker, Rider/Driver panels (file a claim with photo upload, respond, decision document), case page with live progress, System Trace page (advocates side by side, the Judge's card, every gate) and the L2 console (live queue, ratify/override). Tested in a real browser (Playwright, outside the repo) against the local backend, with zero console errors. Paths covered: route deviation file → respond → decision; property damage with a real photo upload → "decide now"; safety claim → straight to L2 → override; escalated case → ratify. Backend support added for it: `?background=true` filing/response (202 + watch the stream), `POST /uploads`, `GET /cases`, `GET /cases/{id}/view`, a DB connection pool (requests went from ~2 s each to the network round trip). **Vercel deploy: Part 2 of [RydeResolve-Deploy-Backend.md](RydeResolve-Deploy-Backend.md) (Dev B).**

- React + Vite + TypeScript, a persona picker, an API client and the SSE connection.
- **Rider/Driver panels:** pick a trip, file a claim, upload a photo, respond to a claim, see the decision document with the other side's private details hidden.
- **Trace panel:** a live timeline showing each advocate's argument and the Judge's reasoning as cards.
- **L2 console:** the queue of escalated cases and a ratify button.
- Deploy to Vercel and test a cold start the way a judge would hit it.

**UX overhaul (2026-10-11):** the v1 screens were redesigned end to end. Highlights: the landing page has one-click demo cases; the pipeline is drawn as a live route line; every citation opens the evidence (map, chat, fare, photo, policy); decisions are shown as rulings with gate checks and a counterfactual; and L2 gets a queue table with keyboard shortcuts and structured override reasons. There are light and dark themes. See `frontend/README.md`. Agent runs now retry on Groq 429s and 5xx (`backend/app/agents/retry.py`).

### Step 5 — Proof that it works (~0.5 day, can be cut)
- ✅ Golden-run (2026-10-11): `POST /golden-run` files all 22 labelled cases through the full pipeline with real model calls and scores each verdict (outcome, remedy, exact amount) against its label. Routing isn't scored; it's reported alongside. Results are on the frontend's Accuracy page (`/insights`).
- ✅ Tuning, measured by golden runs: **14/22 → 19/22 → 21/22 → 21/22 → 22/22** (run #5, 2026-10-11: 12 decided automatically, 10 to a person, median 39 s). Usage baseline from the same run: 1.77M input / 60K output tokens for 22 cases (`llm_usage`). What changed:
  - Agent calls retry Groq 429s for about two minutes, and the golden run uses concurrency 2.
  - Traffic events get code-computed `distance_to_planned_route_m`, `during_trip` and `matches_route`; ROUTE-COMPARISON lists the matching events. This is our own 2 km test for "along the optimal route".
  - Waiver and route-refund amounts are filled in code.
  - The Judge validator rejects a non-upheld outcome that carries a remedy, and a driver-filed claim "upheld" with a waiver for the rider. Compliance also vetoes the latter.
  - Prompt rules: outcomes are from the filer's side; an upheld no-show always gets a fee waiver, never a fare refund.
- Known label limit: the generator labels every photo-backed damage claim "upheld". When the rider disputes causation in the chat, the Judge sometimes escalates instead, which is defensible. That case flips between runs.
- Image Analysis renders are now deterministic per seed, since Pillow's `effect_noise` was unseeded. With that fixed, vision grades 32/32 across 8 seeds per tier.
- Clerical fills in code: an upheld verdict that names no policy gets its category's section (POL-02/03/04).
- Submission material: architecture diagrams (`docs/diagrams/*.mmd` + PNG), README rewritten with screenshots (`docs/screenshots/`) and results.
- Demo database: 200 trips, 65 users, the 22 golden-run cases (12 decided, 9 with a person, 1 declined); smoke/test cases removed.
- Synthetic trips age out of the 30-day window. Before a demo, run `uv run python -m scripts.shift_dates` from `backend/`.
- ✅ Image Analysis tool for Property Damage photos (2026-10-11). The vision call runs on `qwen/qwen3.8-27b`, which accepts images on Groq. The model reports the kind of mess; code maps it to the Policy §4 tier. Compliance vetoes a fee above the tier the photos show. Seeded and demo photos are synthetic renders per tier (`data_generation/pipeline/photo_render.py`, `GET /demo/sample-photo`); vision grades 15 of 16 correctly, and the miss comes back low-confidence, which means "unclear", so a person decides.

### Step 6 — Submission (runs alongside steps 1–5)
- **Public repo:** `.env` with live keys is in git history. Rotate every key (Groq, Neon, object storage, Logfire), then publish clean history, e.g. a fresh public repo with one squashed commit. The current repo must not be made public as-is.
- **CodeBuddy / WorkBuddy proof:** assigned to Dev B. Real tasks and a capture checklist are in [RydeResolve-CodeBuddy-WorkBuddy-Proof.md](RydeResolve-CodeBuddy-WorkBuddy-Proof.md).
- Architecture diagrams exported, title / short blurb / description, README, demo script, video.

## 4. Decisions taken (defaults; change them in code, not here)

| Decision | Default | Source |
|---|---|---|
| Confidence threshold for L2 | 0.6 | Policy doc §8 |
| Always escalate to L2 | Repeat filer (either party has 3+ disputes in 30 days); Property Damage remedy of $120 or more; compliance veto; Judge requested L2 | Policy doc §8, plus our own choices (not Ryde-sourced) |
| Evidence shown to the person complained about after L2 review | Outcome only | Roadmap Day 9 default |
| Dollar amounts | Computed in code (`app/rules/policy_math.py`), never by the Judge. The Judge picks the rule (justified or not, which damage tier); compliance vetoes any amount that doesn't match. | Added after live runs: the model's own refund arithmetic varied between runs on identical evidence |
| Property Damage fee with a photo but no receipt | Exactly the tier's scheduled amount ($40 / $120 / $200) | Our own rule, not Ryde-sourced: the system collects photos, not cleaning receipts |
| Where Image Analysis runs | Once per photo, right after Evidence Collection assembles the case file; the finding is attached to the photo. Advocates read it with their `image_analysis` tool. | Deviation from System Design §6, where the advocates call vision themselves. This keeps object storage behind Evidence Collection, gives both advocates the identical finding, and lets the Judge and compliance see it |
| Photo → fee tier | The model names the mess (spill, mud, vomit…); code maps it to Ryde's tier table. A low-confidence finding (< 0.5), or a photo that isn't a vehicle interior, supports no tier, and the case goes to a person via the Judge | Tier table is Ryde-sourced; the mapping code and the 0.5 threshold are our own |
| Cut order if time runs out | Image Analysis → golden-run dashboard → L2 console polish → real OneMap routes | — |

## 5. Needs a person, not code

- The exact submission deadline (date and time). It decides how much of step 5 survives.
- Rotating keys and publishing the clean public repo.
- CodeBuddy screenshots, the WorkBuddy board (optional), recording the demo video.
- Optional: `ONEMAP_EMAIL` / `ONEMAP_PASSWORD` in `.env` for real road routes instead of straight-line stand-ins.

## 6. Time vs. reality

Steps 1–5 are roughly **4–4.5 days** for one person. If the deadline is closer, the minimum is steps 1–4, with most of step 5 cut and step 6 running in parallel.
