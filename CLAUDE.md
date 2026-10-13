# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This is a monorepo. **The backend runs the full pipeline end to end:** `POST /cases` (intake → Triage → Prevention Rules → Evidence Collection → `awaiting_response`), then `POST /cases/{id}/response` (or `/adjudicate` when there's no response) runs both Advocates → Judge → escalation gate (`app/rules/escalation.py`) → compliance check (`app/rules/compliance.py`) → `decided` or `escalated`. `GET /cases/{id}/decision` returns the decision plus a rendered decision document. Live trace streaming over SSE (`/events/cases/{id}`, `/events/l2`; Postgres is the source of truth, woken by NOTIFY, resumable via Last-Event-ID), the L2 queue + ratify/override (`/l2/*`), demo navigation (`/demo/personas`, `/users/{id}/trips|cases`) and Logfire are wired. `POST /golden-run` files all 22 labelled golden cases for real and scores each verdict against its label (`app/orchestrator/golden_run.py`; `GET /golden-run` reports). Property Damage photos go through Image Analysis (`app/tools/image_analysis.py`) right after evidence assembly. `frontend/` is a working React + Vite + TypeScript app: landing page with one-click demo cases, Rider/Driver panels, live System Trace with an evidence drawer, the Human review (L2) console, and an Accuracy page for the golden run. Token usage per model call is recorded in `llm_usage` (`migrations/0002_llm_usage.sql`, `app/data/usage.py`), tagged by case and agent. Synthetic trips age out of the 30-day claim window: `uv run python -m scripts.shift_dates` (from `backend/`) moves the timeline forward. See `frontend/README.md`. **Current sequencing lives in `docs/RydeResolve-Execution-Plan.md`**; the Dev A / Dev B split below is suspended. `backend/scripts/smoke_e2e.py` seeds three scenarios and drives them through the live API (real Postgres + Groq). Run it after any pipeline change.

Backend commands (run from `backend/`): `uv sync`, `uv run pytest`, `uv run ruff check .`, `uv run uvicorn app.main:app --reload`.

```text
frontend/    React (Vite) + TypeScript client — see frontend/README.md
backend/     Python + FastAPI service, incl. backend/data_generation/ — see backend/README.md
docs/        the specification (read order below) — implementation must be built against this
sources/     raw research/reference material backing docs/ figures — see sources/README.md
neon-infra/  Neon CLI tooling (neon.ts, .neon link file) that provisions Postgres + object storage — see neon-infra/README.md, especially its .env-targeting caveat
```

Everything under `docs/` is the specification the implementation must be built against. Read the docs in this order before writing any code:

1. [`docs/RydeResolve-System-Design.md`](docs/RydeResolve-System-Design.md) — architecture, agent roster, API surface, DB schema, escalation logic. This is the primary spec.
2. [`docs/RydeResolve-Policy-and-Prevention-Rules.md`](docs/RydeResolve-Policy-and-Prevention-Rules.md) — the actual policy corpus (for `policy_chunks`/RAG) and the six deterministic Prevention Rules.
3. [`docs/RydeResolve-Data-Sources-and-Strategy.md`](docs/RydeResolve-Data-Sources-and-Strategy.md) — where each data point comes from (real API, synthetic, semi-dummy) and the synthetic-dataset generation pipeline.
4. [`docs/RydeResolve-Development-Roadmap.md`](docs/RydeResolve-Development-Roadmap.md) — original day-by-day plan and ownership split. **Superseded for sequencing by #5.**
5. [`docs/RydeResolve-Execution-Plan.md`](docs/RydeResolve-Execution-Plan.md) — **the current plan to submission.** One critical path in order; the Dev A / Dev B split is suspended. Check it before picking up work.

Each doc has a "Status" line at the top noting its version — the System Design doc is the source of truth on any conflict.

## What this system does

RydeResolve is a multi-agent dispute-resolution system for a ride-hailing platform (built for a Tencent hackathon). It investigates rider/driver disputes in three categories — **Route Deviation, No-Show Charge, Property Damage** — and produces evidence-grounded, symmetric decision recommendations. **Safety Incidents** are a fourth category that is always hard-routed to a human reviewer and never auto-decided by any agent.

## Architecture

- **Frontend:** React (Vite) + TypeScript, static bundle on Vercel. One app with persona-scoped routes (rider, driver, trace, L2 console), not four separate apps — all driven by one shared SSE stream keyed on `case_id`.
- **Backend:** Python + FastAPI on Render. A single service owning orchestration (state machine), deterministic rules, and all agent calls behind one REST+SSE API surface.
- **Agents:** five `pydantic-ai` agents (`Triage`, `Evidence Collection`, `Rider Advocate`, `Driver Advocate`, `Judge`), model and per-call settings from config (`AGENT_MODEL`, default `openrouter:nvidia/nemotron-3-super-120b-a12b:free` with `AGENT_FALLBACK_MODELS`; Image Analysis has its own `VISION_MODEL` chain; `AGENT_OUTPUT_MODE` defaults to `prompted` because free models mangle tool-call output — use `tool` for `anthropic:` models; free tier is 50 requests/day — see `app/config.py` and `app/agents/llm.py`), instrumented end-to-end with Pydantic Logfire (`logfire.instrument_pydantic_ai()` — no per-agent logging code needed).
- **Data:** Postgres + pgvector (Neon) for structured data, `behavior_profiles`, `trace_events`, and policy-clause retrieval; Neon Object Storage (same Neon project/branch, S3-compatible `ryde-resolve` bucket — `neon.ts`) for evidence photos/audio and decision-document exports. Postgres and evidence object storage are both Neon now, sharing one branch lifecycle — no separate object-storage provider (previously Cloudflare R2).
- **Transport:** REST for request/response actions; Server-Sent Events for everything live (trace updates, status changes, new-case alerts) — deliberately not WebSockets, since every server→client push is one-directional.

### The pipeline (deterministic orchestrator code wires agents together — agents never call each other)

```text
claim filed → Triage Agent → Prevention rules (deterministic gate)
  → Evidence Collection Agent (assembles CaseFile from Postgres/Neon Object Storage)
  → Rider Advocate + Driver Advocate (parallel, identical CaseFile)
  → Judge (produces DecisionObject with confidence)
  → two-phase escalation gate (confidence threshold OR risk-bucket, deterministic)
  → compliance check (can veto, never author)
  → decision document
```

Anything safety-flagged (at Triage) or that fails the escalation gate goes to the **L2 human queue** instead of finishing automatically.

Key architectural rules that must not be violated when implementing:

- **Evidence Collection Agent is the only agent with direct Postgres/Neon Object Storage access.** Advocates get a narrower Evidence Lookup tool scoped to the already-assembled `CaseFile`, not raw DB access.
- **The Judge never receives raw feeds or the original complaint text** — only the `CaseFile` and both advocates' `Argument`s. Its tools (Policy RAG, Prevention-Rule Bucket lookup, Escalate-to-L2) are narrow and read-only.
- **Every factual assertion an agent makes must resolve to a real evidence ID** or an actual tool call made that run — enforced via `pydantic-ai` output validators on `Argument` and `CaseFile`, not a regex pass. Unsupported claims get stripped and the case flagged.
- **Escalation is two independent deterministic checks, either one triggers L2**: a confidence threshold on `DecisionObject.confidence`, and a fixed category/risk-bucket classification — this runs unconditionally on every case regardless of whether the Judge's own `escalate_to_l2` tool fired. Never let a tool call substitute for the gate.
- **Compliance checks can veto a decision, never author one.**
- **Absent required evidence → decline the claim** ("declined for insufficient evidence" is a distinct outcome from "denied on the merits" — the claimant can refile).
- **`cases.id`, `evidence.id`, and `chat_messages.id` are app-generated TEXT business keys** (`CASE-0001`, `EV-0001`, `MSG-0001`, via Postgres sequences in `migrations/0001_init.sql`), not UUIDs — these three are the only tables whose IDs get cited directly (`Argument.cites`, `DecisionObject.case_id`, the trace panel), and every fixture uses this convention. Everything else (`users`, `trips`, `payments`, ...) stays UUID. Migration applied against the Neon dev branch as of 2026-10-08.

### Deterministic vs. agentic — don't blur this

Prevention rules, the escalation gate, and the compliance check are plain Python, not agents — no model call, no `pydantic_ai.Agent`, so prevented/rejected cases are free and fully unit-testable. Only Triage, Evidence Collection, Rider Advocate, Driver Advocate, and Judge are `pydantic_ai.Agent` instances. Don't introduce a "Fraud & Bad-Faith Detection Agent" — it was deliberately dropped from the roster; repeat-filer detection is covered by Prevention Rule 5 alone.

## Policy figures — real vs. invented (must stay labeled, don't silently treat as equally authoritative)

The Policy doc (`docs/RydeResolve-Policy-and-Prevention-Rules.md`) is explicit about which numbers are real Ryde-sourced figures and which are invented placeholders needed to make a category adjudicable. When touching policy logic or `policy_chunks` content, preserve that distinction (e.g. in comments/docs), don't merge them into one undifferentiated ruleset:

- **Real, sourced:** No-Show fee ($4.50), grace periods (3 min / 15 min), dispute window (30 days), Property Damage fee caps ($40/$120/$200 "up to"), Route Deviation's $3.00 destination-change fee (a different flow, not this dispute type).
- **Invented, no real Ryde source exists:** Route Deviation's 10%/25% tolerance thresholds and refund formula, the No-Show 100m GPS-arrival radius, the Property Damage photo-only fee rule (upheld photo-only claims are charged the tier's scheduled amount; the old 2-hour photo window was dropped), Prevention Rule 5's 3-disputes/30-days threshold, and the escalation risk-bucket table contents (System Design §6.1).

## Open architecture decisions (not yet resolved — see System Design §6.2)

- Whether verified evidence is shown to the complainee once L2 ratifies a case, or only the outcome.
- Whether any Prevention Rule needs LLM assistance (current default: fully deterministic).

Both panels/schemas are already designed to be server-driven and data-shaped so implementation isn't blocked on these, but don't hardcode an assumed answer without flagging it.

## Team split

Two developers, split along the pipeline's natural data seam — each owns a full-stack vertical slice (agent/rules logic, the schema it needs, and the frontend surface built on it), not one dev on backend and the other on frontend/data/infra. See [`docs/RydeResolve-Development-Roadmap.md`](docs/RydeResolve-Development-Roadmap.md) §0 for the full breakdown. **suryaansh2002 is Dev A**; Dev B is the teammate picking up the adjudication/delivery half.

**The split below is suspended.** The current work distribution, who does what from here to submission, is **[Execution Plan §0](docs/RydeResolve-Execution-Plan.md)**. In practice Dev A (suryaansh2002) built the whole pipeline, frontend, Image Analysis and golden run. Dev B owns the Render/Vercel deploy ([`docs/RydeResolve-Deploy-Backend.md`](docs/RydeResolve-Deploy-Backend.md)) and the CodeBuddy/WorkBuddy proof. The original split is kept here for context:

- **Dev A — Intake & Evidence** (everything up to and including the `CaseFile`): Triage, Prevention Rules, Evidence Collection + tools, the trip-level schema, the synthetic data pipeline, the Rider/Driver panels, and object-storage upload wiring. Owns `app/api/cases.py` + `app/api/evidence.py` and the orchestrator front half (`app/orchestrator/pipeline.py`). All done.
- **Dev B — Adjudication & Delivery** (everything from the advocates onward): Rider/Driver Advocates + Judge agents + tools, the two-phase escalation gate (must read bucket contents from a lookup/config, not hardcode them — Dev A wires the actual bucket table Day 10 as a data change), compliance check, decision-document rendering, `policy_chunks`/Policy RAG, golden-case suite + dashboard, System Trace Panel + SSE broadcaster + trace event bus, L2 console, Logfire, deployment/infra (Vercel, Render, Neon). Owns `app/api/decisions.py` + `app/api/l2.py` + `app/api/events.py`. All of this is now built (the golden run lives in `app/api/golden.py` and `app/orchestrator/golden_run.py`); deploy and proof remain with Dev B.
- **Shared:** the locked API/schema contract (done — `app/schemas/`), CodeBuddy/WorkBuddy proof capture (both devs capture their own sessions), demo video, submission checklist. The orchestrator (`app/orchestrator/state_machine.py`) is genuinely shared code — it calls into both devs' agents — but is no longer an unowned line item; see above for who extends which half and when.

**De-risking the cross-dependency (roadmap v3 §0a):** Dev B's Advocates need Dev A's real `CaseFile`; Dev A's panels need Dev B's real `DecisionObject`/trace events. Built sequentially, each side blocks on the other. Instead: schemas lock Day 1 (done), each dev hand-writes 2–3 fixtures matching the locked contract on Day 2 and exchanges them (validated against the real schema via `tests/test_fixtures.py`, not just eyeballed), both halves get built and tested in parallel against those fixtures on Day 3–4, a 15-minute joint check-in confirms both sides are actually ready on Day 4 evening, and the real wiring replaces the fixtures at the Day 5 integration gate — which is bidirectionally blocking, so a slip on either side delays both. Property Damage's photo/`DamageFinding` shape gets the same fixture-first treatment on a smaller scale: frozen jointly before Day 6, not assumed compatible. Check whether a fixture already exists before assuming the other dev's real component must be done first.

## Mandatory hackathon constraint

The project must be built using CodeBuddy or WorkBuddy with proof captured continuously (screenshots/API logs) — this is a hard submission gate per the hackathon handbook, not optional tooling preference (System Design §8). Dev B owns the proof: real tasks, setup and a capture checklist are in [`docs/RydeResolve-CodeBuddy-WorkBuddy-Proof.md`](docs/RydeResolve-CodeBuddy-WorkBuddy-Proof.md). Proof must come from real work done in those tools, not staged re-creations.
