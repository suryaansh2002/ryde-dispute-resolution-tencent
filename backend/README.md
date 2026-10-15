# backend

Python + FastAPI: one service that owns orchestration, the deterministic rules and all five `pydantic-ai` agents, behind one REST + SSE API. See `docs/RydeResolve-System-Design.md` §4 and §6.

- `app/api/`: FastAPI routes. `cases.py` and `evidence.py` handle intake; `decisions.py`, `l2.py` (the support console) and `events.py` (SSE) handle the hearing and its delivery; `golden.py` runs the labelled suite; `demo.py` serves demo navigation.
- `app/orchestrator/`: the case state machine and the pipeline that runs each case (plain code, not an agent). Also the golden run, and the outcome text each party sees (`party_outcome.py`, behind `GET /cases/{id}/outcome?for=rider|driver`).
- `app/rules/`: the Prevention Rules, the two-phase escalation gate, the compliance check and the policy maths. All deterministic, no model calls.
- `app/agents/`: one subfolder per `pydantic_ai.Agent`: `triage/`, `evidence_collection/`, `rider_advocate/`, `driver_advocate/` and `judge/`. `llm.py` builds each model from config, with fallbacks.
- `app/tools/`: DB Query, Object Storage Fetch, Policy RAG, Evidence Lookup, Image Analysis, Prevention-Rule Bucket and Escalate-to-L2.
- `app/schemas/`: `CaseFile`, `Argument`, `DecisionObject` and `TriageResult`, the Pydantic contract between the stages (System Design §7).
- `app/data/`: the Postgres access layer and the Neon Object Storage client (S3-compatible).
- `app/sse/`: the trace event bus and the SSE broadcaster.
- `migrations/`: the Postgres schema.
- `scripts/`: the end-to-end smoke test, a date shifter for the synthetic timeline, and a demo-data reset.
- `tests/`: 216 automated tests, no network needed.
- `data_generation/`: the synthetic dataset pipeline (see its own README).

## Running locally

Uses [`uv`](https://docs.astral.sh/uv/). Run everything below from `backend/`, with a filled-in `.env` at the repo root (copy `.env.example`).

```bash
uv sync                              # install dependencies
uv run pytest                        # run the tests
uv run ruff check .                  # lint
uv run uvicorn app.main:app --reload # dev server, http://localhost:8000/health
```

Before anything touches the database, apply the schema:

```bash
psql "$DATABASE_URL" -f migrations/0001_init.sql
psql "$DATABASE_URL" -f migrations/0002_llm_usage.sql
```

`0002_llm_usage.sql` adds `llm_usage`, with one row per model call: every agent run and every Image Analysis call. Each row records the case, agent, model, input and output tokens, requests, tool calls and latency. There's no cost column on purpose: cost is tokens × the provider's current price, so compute it at query time, for example `SELECT case_id, sum(input_tokens), sum(output_tokens) FROM llm_usage GROUP BY case_id`.

The end-to-end smoke test needs the server running. It makes real model calls, takes about 5–10 minutes and cleans up after itself:

```bash
uv run uvicorn app.main:app --port 8000 &
uv run python -m scripts.smoke_e2e --base-url http://localhost:8000
```

## Deploying (Render)

Step by step: [`docs/RydeResolve-Deploy-Backend.md`](../docs/RydeResolve-Deploy-Backend.md). In short:

The backend ships as a Docker image (`Dockerfile`), described by the Render Blueprint at the repo root (`render.yaml`). It runs on the free plan in the Ohio region, the same AWS region as the Neon database. It has a health check on `/health` and auto-deploys on changes under `backend/`.

1. Render dashboard → **New → Blueprint** → connect GitHub and pick this repo.
2. Render prompts for each secret. Paste the values from your `.env` **without the surrounding quotes**:
   - `DEEPINFRA_API_KEY`
   - `GOOGLE_API_KEY`
   - `DATABASE_URL`
   - `DATABASE_URL_UNPOOLED`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_ENDPOINT_URL_S3`
   - `AWS_REGION`
   - `LOGFIRE_TOKEN`
3. Once the first deploy is live, verify it from `backend/`:

```bash
uv run python -m scripts.smoke_e2e --base-url https://<your-service>.onrender.com
```

The free tier sleeps after 15 idle minutes, and the first request after that takes about a minute. Hit `/health` before a demo.

To run the same image locally: `docker build -t ryde-resolve-api .`, then `docker run -p 8001:8000 --env-file <env file> ryde-resolve-api`. Docker's `--env-file` keeps quotes as part of the value, so the env file must have none.
