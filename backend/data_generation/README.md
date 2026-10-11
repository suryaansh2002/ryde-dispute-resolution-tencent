# data_generation

The synthetic dataset generation pipeline. See `docs/RydeResolve-Data-Sources-and-Strategy.md` §4 for the full 11-step pipeline this implements (trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation, chat/claim text, user & behavior-profile generation, Property Damage photo assignment, golden-case labeling).

- `pipeline/` — the generation scripts, one per pipeline step: `geo.py` (Singapore sampling, haversine, route perturbation, GPS interpolation), `onemap.py` (real OneMap routing with a synthetic straight-line fallback), `categories.py`, `traffic_events.py`, `fares.py` (real Ryde fee figures), `chat.py` (template claim/chat text), `users.py`, `photos.py` (Property Damage placeholder images), `golden_cases.py` (step 11 labeling), `generate.py` (orchestrates steps 1-9 + 11), `ingest_policy.py` (chunks the Policy doc into `policy_chunks.json`)
- `fixtures/` — generated output (`policy_chunks.json`) and the hand-built `CaseFile`/`DecisionObject`/trace-event fixtures used for Dev A/Dev B parallel development (roadmap §0a)
- `assets/` — reserved for a real Property Damage photo set (real/stock + AI-generated, per severity tier) if one gets sourced later; `photos.py` uploads a placeholder image per tier in the meantime (see its docstring)

Not part of the FastAPI request path — this is offline tooling that populates Postgres/Neon Object Storage ahead of a demo run.

## Running it

From `backend/`, with the root `.env` present:

```bash
uv run python -m data_generation.pipeline.generate --count 200 --seed 42
```

Generates trips/payments/chat/traffic-events/users/behavior-profiles directly into Postgres, uploads Property Damage placeholder photos to Neon Object Storage where a golden case needs one, and labels ~20% of the generated dispute trips as golden cases (`golden_cases`, keyed by `trip_id`) with a deterministically-computed `expected_outcome` and (for Property Damage) `prepared_evidence` ready to pass straight into `POST /cases`' `evidence` field.

**Does not call Groq or file any real claims** — it only produces the underlying data. Actually filing a claim against any trip (golden or ad hoc) goes through the real `POST /cases` API, which is what a future `/golden-run` endpoint (Dev B) is for: file each golden trip for real, compare the resulting decision against `expected_outcome`, and write `last_run_result`/`last_run_at`.

**OneMap routing** uses `ONEMAP_ACCESS_TOKEN` if valid, or self-refreshes via `ONEMAP_EMAIL`/`ONEMAP_PASSWORD` if set (tokens expire every ~3 days — a pasted token will not survive a multi-week build). Falls back to a synthetic straight-line route, clearly labeled `"source": "synthetic"`, when neither works — the pipeline still runs, just without real road geometry.
