# data_generation

The synthetic dataset generation pipeline. See `docs/RydeResolve-Data-Sources-and-Strategy.md` §4 for the full 11-step pipeline this implements (trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation, chat/claim text, user & behavior-profile generation, Property Damage photo assignment, golden-case labeling).

- `pipeline/` — the generation scripts, one per pipeline step
- `fixtures/` — generated output (seeded trips, golden cases) and the hand-built `CaseFile`/`DecisionObject` fixtures used for Dev A/Dev B parallel development (roadmap §0a)
- `assets/` — Property Damage photo set (real/stock + AI-generated, per severity tier)

Not part of the FastAPI request path — this is offline tooling that populates Postgres/Neon Object Storage ahead of a demo run.
