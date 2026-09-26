# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This is a monorepo. `backend/` has a real `uv`-managed Python project now (FastAPI skeleton, locked `app/schemas/`, `app/rules/prevention.py` with unit tests, `migrations/0001_init.sql`) — see `backend/README.md` for run commands. `frontend/` is still an empty scaffold. This covers the Day 1 joint schema lock plus part of Dev A's Day 2 (Prevention Rules) — see "Team split" below for the actual two-developer split and what's next for each side.

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
4. [`docs/RydeResolve-Development-Roadmap.md`](docs/RydeResolve-Development-Roadmap.md) — day-by-day build plan and ownership split (useful for sequencing work, not for architecture facts).

Each doc has a "Status" line at the top noting its version — the System Design doc is the source of truth on any conflict.

## What this system does

RydeResolve is a multi-agent dispute-resolution system for a ride-hailing platform (built for a Tencent hackathon). It investigates rider/driver disputes in three categories — **Route Deviation, No-Show Charge, Property Damage** — and produces evidence-grounded, symmetric decision recommendations. **Safety Incidents** are a fourth category that is always hard-routed to a human reviewer and never auto-decided by any agent.

## Architecture

- **Frontend:** React (Vite) + TypeScript, static bundle on Vercel. One app with persona-scoped routes (rider, driver, trace, L2 console), not four separate apps — all driven by one shared SSE stream keyed on `case_id`.
- **Backend:** Python + FastAPI on Render. A single service owning orchestration (state machine), deterministic rules, and all agent calls behind one REST+SSE API surface.
- **Agents:** five `pydantic-ai` agents (`Triage`, `Evidence Collection`, `Rider Advocate`, `Driver Advocate`, `Judge`), model string `groq:qwen/qwen3.8-27b` (Groq's currently supported Qwen chat model — 131K context, tool use + JSON mode), instrumented end-to-end with Pydantic Logfire (`logfire.instrument_pydantic_ai()` — no per-agent logging code needed).
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

### Deterministic vs. agentic — don't blur this

Prevention rules, the escalation gate, and the compliance check are plain Python, not agents — no model call, no `pydantic_ai.Agent`, so prevented/rejected cases are free and fully unit-testable. Only Triage, Evidence Collection, Rider Advocate, Driver Advocate, and Judge are `pydantic_ai.Agent` instances. Don't introduce a "Fraud & Bad-Faith Detection Agent" — it was deliberately dropped from the roster; repeat-filer detection is covered by Prevention Rule 5 alone.

## Policy figures — real vs. invented (must stay labeled, don't silently treat as equally authoritative)

The Policy doc (`docs/RydeResolve-Policy-and-Prevention-Rules.md`) is explicit about which numbers are real Ryde-sourced figures and which are invented placeholders needed to make a category adjudicable. When touching policy logic or `policy_chunks` content, preserve that distinction (e.g. in comments/docs), don't merge them into one undifferentiated ruleset:

- **Real, sourced:** No-Show fee ($4.50), grace periods (3 min / 15 min), dispute window (30 days), Property Damage fee caps ($40/$120/$200 "up to"), Route Deviation's $3.00 destination-change fee (a different flow, not this dispute type).
- **Invented, no real Ryde source exists:** Route Deviation's 10%/25% tolerance thresholds and refund formula, the No-Show 100m GPS-arrival radius, Property Damage's 2-hour photo-submission window, Prevention Rule 5's 3-disputes/30-days threshold, and the escalation risk-bucket table contents (System Design §6.1).

## Open architecture decisions (not yet resolved — see System Design §6.2)

- Whether verified evidence is shown to the complainee once L2 ratifies a case, or only the outcome.
- Whether any Prevention Rule needs LLM assistance (current default: fully deterministic).

Both panels/schemas are already designed to be server-driven and data-shaped so implementation isn't blocked on these, but don't hardcode an assumed answer without flagging it.

## Team split

Two developers, split along the pipeline's natural data seam — each owns a full-stack vertical slice (agent/rules logic, the schema it needs, and the frontend surface built on it), not one dev on backend and the other on frontend/data/infra. See [`docs/RydeResolve-Development-Roadmap.md`](docs/RydeResolve-Development-Roadmap.md) §0 for the full breakdown.

- **Dev A — Intake & Evidence** (everything up to and including the `CaseFile`): Triage Agent, Prevention Rules (done), Evidence Collection Agent + tools, `trips`/`payments`/`chat_messages`/`traffic_events` schema (done — `migrations/0001_init.sql`), synthetic data pipeline, Rider/Driver panels' claim-filing and evidence-upload flows, Neon Object Storage upload wiring.
- **Dev B — Adjudication & Delivery** (everything from the advocates onward): Rider/Driver Advocates + Judge agents + tools, the two-phase escalation gate, compliance check, decision-document rendering, `policy_chunks`/Policy RAG, golden-case suite + dashboard, System Trace Panel + SSE broadcaster + trace event bus, L2 console, Logfire, deployment/infra (Vercel, Render, Neon).
- **Shared:** orchestrator/state-machine skeleton (heads-up before touching it either way), the locked API/schema contract (done — `app/schemas/`), CodeBuddy/WorkBuddy proof capture (both devs capture their own sessions), demo video, submission checklist.

**De-risking the cross-dependency (roadmap §0a):** Dev B's Advocates need Dev A's real `CaseFile`; Dev A's panels need Dev B's real `DecisionObject`/trace events. Built sequentially, each side blocks on the other. Instead: schemas lock Day 1 (done), each dev hand-writes 2–3 fixtures matching the locked contract on Day 2 and exchanges them, both halves get built and tested in parallel against those fixtures on Day 3–4, and the real wiring replaces the fixtures at the Day 5 integration gate. Check whether a fixture already exists before assuming the other dev's real component must be done first.

## Mandatory hackathon constraint

The project must be built using CodeBuddy or WorkBuddy with proof captured continuously (screenshots/API logs) — this is a hard submission gate per the hackathon handbook, not optional tooling preference (System Design §8). Both devs capture their own CodeBuddy/WorkBuddy sessions on their own slice as they go, rather than reconstructing proof at the end.
