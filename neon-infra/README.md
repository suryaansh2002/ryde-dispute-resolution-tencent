# neon-infra

Neon CLI tooling that provisions this project's cloud resources (Postgres branch + the `ryde-resolve` S3-compatible object storage bucket) as config, not app code for `frontend/` or `backend/`.

- `neon.ts` — declares the buckets/branch policy (`defineConfig`)
- `.neon` — local link file (org/project/branch IDs) written by `neon link`; git-ignored
- `package.json` / `package-lock.json` / `node_modules/` — only `@neon/config` + `@neon/env`, needed to evaluate `neon.ts`
- `skills-lock.json` — tracks which Neon Claude Code skills are installed (see `.claude/skills/`, which stays at repo root — that's a fixed Claude Code location, not Neon's choice)

**Run Neon CLI commands from inside this directory** (`cd neon-infra && neon <command>`), since that's where `neon.ts`/`.neon` live.

**Careful — `.env` targeting is cwd-relative.** `neon deploy`/`neon env pull` write pulled credentials (`DATABASE_URL`, `AWS_*`) to an existing `.env` in the *current directory*, falling back to creating `.env.local` there if none exists — they do **not** search upward to find the repo-root `.env`. Since the root `.env` is the one `backend/` actually loads, either:

- run these commands from the **repo root** with `--config neon-infra/neon.ts` (root `.env` already exists there, so pulls land in the right place), or
- run from inside `neon-infra/` as above, then manually copy any new/changed values into the root `.env`.

Don't run `neon deploy`/`env pull` from inside `neon-infra/` without checking afterward whether it wrote a stray `neon-infra/.env` or `.env.local` — reconcile it into the root `.env` and delete the stray file if so.
