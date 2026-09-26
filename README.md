# RydeResolve

A multi-agent dispute resolution system for Ryde's ride-hailing platform, built for the Tencent hackathon. RydeResolve automatically investigates and recommends fair, evidence-grounded, symmetric resolutions for rider/driver disputes — instead of the usual all-or-nothing pipeline where cheap claims get rubber-stamped and consequential ones get decided without a real hearing.

**Scope:** three of Ryde's four dispute categories — Route Deviation, No-Show Charge, and Property Damage. Safety Incidents are always routed straight to a human reviewer, never auto-decided.

## How it works

A claim flows through five `pydantic-ai` agents, wired together by deterministic orchestrator code and gates:

1. **Triage Agent** — categorizes the claim and flags safety incidents.
2. **Prevention rules** (deterministic) — duplicate/malformed/safety/evidence/velocity/claim-window checks; can hard-stop a case before any further reasoning.
3. **Evidence Collection Agent** — assembles one canonical `CaseFile` (chat logs, photos, GPS/telemetry, payment data, behavior profiles) from Postgres and Neon Object Storage, with an output validator confirming every reference is real.
4. **Rider Advocate & Driver Advocate** (parallel) — each builds and cites its side's case against the identical `CaseFile`.
5. **Judge** — weighs both arguments and produces a `DecisionObject` with a confidence score.

That decision passes a two-phase deterministic escalation gate (confidence threshold + risk-bucket classification) and a compliance check before becoming a final decision document. Anything that fails escalation, or is flagged safety-related upfront, goes to a human (L2) reviewer instead.

## Architecture at a glance

- **Frontend:** React (Vite) + TypeScript, static bundle on Vercel — rider panel, driver panel, live system trace panel, and an L2 console, all driven by one shared SSE stream per case.
- **Backend:** Python + FastAPI on Render — one service owning orchestration, deterministic rules, and all five agents.
- **Agents:** built on `pydantic-ai` (model: `groq:qwen/qwen3.8-27b`), model calls via Groq, fully instrumented with Pydantic Logfire (auto-captured spans for every agent run and tool call).
- **Data:** Postgres + pgvector (Neon) for structured data and policy-clause retrieval; Neon Object Storage — same Neon project/branch, an S3-compatible bucket (`ryde-resolve`) — for evidence photos/audio and decision-document exports.
- **Transport:** REST for request/response actions, Server-Sent Events for everything live (trace updates, status changes, new-case alerts).

Full diagrams and rationale live in [`docs/RydeResolve-System-Design.md`](docs/RydeResolve-System-Design.md).

## Documentation

| Document | Covers |
|---|---|
| [System Design & Architecture](docs/RydeResolve-System-Design.md) | Client/backend/data-layer design, the five-agent roster, escalation gates, deployment architecture, and submission-requirements mapping |
| [Data Sources & Generation Strategy](docs/RydeResolve-Data-Sources-and-Strategy.md) | Which data the architecture needs, where it comes from (real API, synthetic, or semi-dummy), new Postgres tables, and the synthetic-dataset generation pipeline |
| [Dispute Resolution Policy & Prevention Rules](docs/RydeResolve-Policy-and-Prevention-Rules.md) | The actual policy corpus used for Policy RAG, and the six deterministic Prevention Rules, each labeled as either real-Ryde-sourced or an invented design choice |

## Deployment (all free tier)

Vercel (frontend) + Render (backend) + Neon (Postgres/pgvector + Object Storage, one project) + Pydantic Logfire (observability), targeting effectively-zero-cost hosting reachable by hackathon judges. Neon covers both the database and evidence object storage, so there's no separate object-storage provider (previously Cloudflare R2) to run.

## Status

Foundation phase (roadmap v3 §1, Days 1–2). Done: the `CaseFile`/`Argument`/`DecisionObject`/`TriageResult` schema contract (`backend/app/schemas/`), the initial Postgres migration (`backend/migrations/0001_init.sql`), the six Prevention Rules with full unit tests, the API route layer split by owner (`backend/app/api/`), an orchestrator state-machine skeleton, and backend CI. Two developers: **Dev A** (Intake & Evidence) is building Triage, Evidence Collection, and the data pipeline; **Dev B** (Adjudication & Delivery) is building the Advocates, Judge, and frontend/delivery.
