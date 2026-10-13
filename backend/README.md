# backend

Python + FastAPI, single service on Render owning orchestration, deterministic rules, and all five `pydantic-ai` agents behind one REST+SSE API surface. See `docs/RydeResolve-System-Design.md` §4, §6.

- `app/api/` — FastAPI routes, split into per-owner router modules (roadmap v3 §0) so Dev A and Dev B never edit the same file: `cases.py` + `evidence.py` (Dev A), `decisions.py` + `l2.py` + `events.py` (Dev B)
- `app/orchestrator/` — case state machine (plain code, not an agent). Genuinely shared, built incrementally: Dev A drafts the front-half transitions Day 2, Dev B extends it with the back-half states Day 5 (roadmap v3 §0)
- `app/rules/` — Prevention Rules, the two-phase escalation gate, compliance check (all deterministic, no model calls)
- `app/agents/` — one subfolder per `pydantic_ai.Agent`: `triage/`, `evidence_collection/`, `rider_advocate/`, `driver_advocate/`, `judge/`
- `app/tools/` — DB Query, Object Storage Fetch, Policy RAG, Evidence Lookup, Image Analysis, Prevention-Rule Bucket, Escalate-to-L2
- `app/schemas/` — `CaseFile`, `Argument`, `DecisionObject`, `TriageResult` (pydantic models — the locked contract, System Design §7)
- `app/data/` — Postgres access layer + Neon Object Storage (S3-compatible) client
- `app/sse/` — trace event bus + SSE broadcaster
- `migrations/` — Postgres schema migrations
- `tests/`
- `data_generation/` — the synthetic dataset generation pipeline (see its own README)

Local dev runs against a local Postgres with pgvector via `docker-compose`, same image as prod (System Design §9). **For now** (no docker-compose set up yet), dev runs directly against a Neon branch declared in `neon-infra/` — `DATABASE_URL` in the repo-root `.env` already points there. With two developers now, prefer a branch-per-dev workflow (`neon checkout <name>`, TTL policy already in `neon-infra/neon.ts`) over both hitting the same default branch, so one dev's test data/migrations don't clobber the other's.

## Running locally

Uses [`uv`](https://docs.astral.sh/uv/) for dependency management — everything below runs from `backend/`.

```bash
uv sync                              # install deps (already done once)
uv run pytest                        # run tests
uv run ruff check .                  # lint
uv run uvicorn app.main:app --reload # dev server, http://localhost:8000/health
```

End-to-end smoke test (real Neon + Groq, ~3–5 min, cleans up after itself; needs the server running):

```bash
uv run uvicorn app.main:app --port 8000 &
uv run python -m scripts.smoke_e2e --base-url http://localhost:8000
```

Apply `migrations/0001_init.sql` against the Neon branch with `psql "$DATABASE_URL" -f migrations/0001_init.sql` (or via the `neon-postgres` skill/CLI) before running anything that touches the DB.
Then apply `migrations/0002_llm_usage.sql` the same way. It adds `llm_usage`, one row per model call (every agent run and every Image Analysis call) with the case, agent, model, input/output tokens, requests, tool calls and latency. There's no cost column on purpose: cost is tokens × the provider's current price, so compute it at query time, e.g. `SELECT case_id, sum(input_tokens), sum(output_tokens) FROM llm_usage GROUP BY case_id`.

## Deploying (Render)

**Full handoff with checklist: [`docs/RydeResolve-Deploy-Backend.md`](../docs/RydeResolve-Deploy-Backend.md).** Summary:

The backend ships as a Docker image (`Dockerfile`), described by the Render Blueprint at the repo root (`render.yaml`): free plan, Ohio region (same AWS region as the Neon database), health check on `/health`, auto-deploy on changes under `backend/`.

1. Render dashboard → **New → Blueprint** → connect GitHub and pick this repo. A private repo needs the Render GitHub app granted access to it.
2. Render prompts for each secret. Paste the values from the root `.env` **without the surrounding quotes**: `OPENROUTER_API_KEY`, `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, `LOGFIRE_TOKEN`.
3. After the first deploy is live, verify it from `backend/` (real Groq calls, about 3–5 min, cleans up after itself):

```bash
uv run python -m scripts.smoke_e2e --base-url https://<your-service>.onrender.com
```

The free tier sleeps after 15 idle minutes, and the first request after that takes about a minute. Hit `/health` before a demo.

To run the same image locally, use `docker build -t ryde-resolve-api .`, then `docker run -p 8001:8000 --env-file <env file> ryde-resolve-api`. Docker's `--env-file` keeps quotes as part of the value, so the env file must have none.
