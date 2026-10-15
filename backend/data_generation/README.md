# data_generation

The synthetic dataset generation pipeline. See `docs/RydeResolve-Data-Sources-and-Strategy.md` §4 for the full 11-step pipeline this implements (trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation, chat/claim text, user & behavior-profile generation, Property Damage photo assignment, golden-case labeling).

- `pipeline/` — the generation scripts, one per pipeline step: `geo.py` (Singapore sampling, haversine, route perturbation, GPS interpolation), `onemap.py` (real OneMap routing with a synthetic straight-line fallback), `categories.py`, `traffic_events.py`, `fares.py` (real Ryde fee figures), `chat.py` (template claim/chat text), `users.py`, `photo_render.py` + `photos.py` (synthetic rear-seat photos per damage tier: coffee spill, mud, vomit, or clean), `golden_cases.py` (step 11 labeling), `generate.py` (orchestrates steps 1-9 + 11), `ingest_policy.py` (chunks the Policy doc into `policy_chunks.json`)
- `fixtures/` — generated output (`policy_chunks.json`) and hand-built `CaseFile`/`DecisionObject`/trace-event fixtures, validated against the real schemas by `tests/test_fixtures.py`
- `assets/` — reserved for a real Property Damage photo set (real/stock, per severity tier) if one gets sourced later. Until then `photo_render.py` draws a synthetic photo per tier, deterministic per (tier, seed) and labelled `synthetic` in the object key. Image Analysis grades these like any uploaded photo (32/32 correct across 8 seeds per tier). `uv run python -m data_generation.pipeline.photos` re-renders and re-uploads the golden cases' photos.

Not part of the FastAPI request path — this is offline tooling that populates Postgres/Neon Object Storage ahead of a demo run.

## Running it

From `backend/`, with the root `.env` present:

```bash
uv run python -m data_generation.pipeline.generate --count 200 --seed 42
```

Generates trips/payments/chat/traffic-events/users/behavior-profiles directly into Postgres, uploads a synthetic Property Damage photo to Neon Object Storage where a golden case needs one, and labels ~20% of the generated dispute trips as golden cases (`golden_cases`, keyed by `trip_id`) with a deterministically-computed `expected_outcome` and (for Property Damage) `prepared_evidence` ready to pass straight into `POST /cases`' `evidence` field.

**Makes no model calls and files no claims** — it only produces the underlying data. Actually filing a claim against any trip (golden or ad hoc) goes through the real `POST /cases` API. `POST /golden-run` (`app/orchestrator/golden_run.py`) does exactly that for every golden trip: it files the claim for real, scores the verdict against `expected_outcome`, and writes `last_run_result`. Results show on the frontend's Accuracy page.

**OneMap routing** uses `ONEMAP_ACCESS_TOKEN` if valid, or self-refreshes via `ONEMAP_EMAIL`/`ONEMAP_PASSWORD` if set (tokens expire every ~3 days — a pasted token will not survive a multi-week build). Falls back to a synthetic straight-line route, clearly labeled `"source": "synthetic"`, when neither works — the pipeline still runs, just without real road geometry. The current dataset uses real OneMap road routes.

**Dates:** trips are dated relative to generation day, and claims are only allowed within 30 days. `uv run python -m scripts.shift_dates` moves the whole timeline forward consistently (trips, GPS fixes, chat, traffic events) so the dataset stays usable.
