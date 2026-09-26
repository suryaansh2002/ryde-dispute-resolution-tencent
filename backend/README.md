# backend

Python + FastAPI, single service on Render owning orchestration, deterministic rules, and all five `pydantic-ai` agents behind one REST+SSE API surface. See `docs/RydeResolve-System-Design.md` §4, §6.

- `app/api/` — FastAPI routes (see System Design §4's endpoint table)
- `app/orchestrator/` — case state machine (plain code, not an agent)
- `app/rules/` — Prevention Rules, the two-phase escalation gate, compliance check (all deterministic, no model calls)
- `app/agents/` — one subfolder per `pydantic_ai.Agent`: `triage/`, `evidence_collection/`, `rider_advocate/`, `driver_advocate/`, `judge/`
- `app/tools/` — DB Query, Object Storage Fetch, Policy RAG, Evidence Lookup, Image Analysis, Prevention-Rule Bucket, Escalate-to-L2
- `app/schemas/` — `CaseFile`, `Argument`, `DecisionObject`, `TriageResult` (pydantic models — the locked contract, System Design §7)
- `app/data/` — Postgres access layer + Neon Object Storage (S3-compatible) client
- `app/sse/` — trace event bus + SSE broadcaster
- `migrations/` — Postgres schema migrations
- `tests/`
- `data_generation/` — the synthetic dataset generation pipeline (see its own README)

Local dev runs against a local Postgres with pgvector via `docker-compose`, same image as prod (System Design §9). **For now** (solo build, no docker-compose set up yet), dev runs directly against the Neon dev branch declared in `neon-infra/` — `DATABASE_URL` in the repo-root `.env` already points there.

## Running locally

Uses [`uv`](https://docs.astral.sh/uv/) for dependency management — everything below runs from `backend/`.

```bash
uv sync                              # install deps (already done once)
uv run pytest                        # run tests
uv run ruff check .                  # lint
uv run uvicorn app.main:app --reload # dev server, http://localhost:8000/health
```

Apply `migrations/0001_init.sql` against the Neon branch with `psql "$DATABASE_URL" -f migrations/0001_init.sql` (or via the `neon-postgres` skill/CLI) before running anything that touches the DB.
