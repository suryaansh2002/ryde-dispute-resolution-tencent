# RydeResolve — Deploy to Render (backend) and Vercel (frontend)

**Owner:** Dev B (@shiv0112), on your own Render account.
**Status:** ready to deploy, updated 2026-10-11 for the UX overhaul, Image Analysis, the golden run and usage tracking. The image builds and passes the end-to-end test locally. This is the only remaining part of step 2 in the [Execution Plan](RydeResolve-Execution-Plan.md).
**Time:** about 15 minutes for the backend, plus about 5 minutes for its first build; about 10 minutes for the frontend. Do the backend first, because the frontend needs its URL.

When you're done, post the live URL in our chat and tick the checklist at the bottom.

---

## What you're deploying

- **Code:** `backend/` on `main`, built from `backend/Dockerfile` (Python 3.11 + uv, FastAPI on `$PORT`).
- **Service config:** `render.yaml` at the repo root, a Render Blueprint.
  - Free plan, **Ohio** region. That's the same AWS region as our Neon database (us-east-2), so database queries stay local.
  - Health check on `/health`.
  - Auto-deploys when `backend/**` changes on `main`.
- **External services the app talks to:** Neon Postgres, Neon Object Storage, DeepInfra (the agents), Google Gemini (photos), Logfire. All of them already exist; you're only supplying their credentials.
- **Database schema:** `backend/migrations/0001_init.sql` and `0002_llm_usage.sql`. Both are already applied to our Neon branch, so there's nothing to run unless you point the service at a *new* Neon branch or project. In that case, apply both in order first with `psql "$DATABASE_URL" -f ...`.
- **New since the first version of this doc** (no extra setup needed; all of it ships in the image):
  - Pillow, which renders the synthetic damage photos.
  - Image Analysis, which uses Gemini Flash (`GOOGLE_API_KEY`), with DeepInfra's Gemma as fallback.
  - `POST /golden-run`.
  - The `llm_usage` table, written on every model call.

## Steps

### 1. Give Render access to the repo

The repo is private and owned by `suryaansh2002`, and you're a collaborator. Render can only build repos its GitHub app can see. Try these in order:

1. Render dashboard → **New → Blueprint** → connect GitHub. If `suryaansh2002/ryde-dispute-resolution-tencent` shows up in the list, go to step 2.
2. If it doesn't, GitHub won't let you install Render's app on another user's account. Ask @suryaansh2002 to approve the Render GitHub app for this one repo: GitHub → Settings → Applications → Render → Repository access. Then refresh the list in Render.
3. Fallback: fork the repo to your account (forking is enabled) and deploy the fork. You'll then need to keep the fork synced with `main`, so only do this if option 2 isn't possible.

### 2. Create the service from the Blueprint

Pick the repo and branch `main`. Render reads `render.yaml` and proposes one web service, `ryde-resolve-api`. Before applying, confirm the region shows **Ohio** and the plan shows **Free**.

### 3. Fill in the secrets

Render asks for each value marked `sync: false`. Copy each from the root `.env` on `main` (`git show main:.env`).

> **Paste values *without* the surrounding quotes.** `.env` has `DATABASE_URL="postgresql://..."`; Render needs `postgresql://...`. A quoted database URL fails at startup with a confusing connection error.

| Key | Where it comes from |
|---|---|
| `DEEPINFRA_API_KEY` | `.env` (the agents, and the photo fallback) |
| `GOOGLE_API_KEY` | `.env` (Gemini Flash for photos) |
| `DATABASE_URL` | `.env` (pooled Neon URL, quotes removed) |
| `DATABASE_URL_UNPOOLED` | `.env` (direct Neon URL, quotes removed). **Required:** the app's connections and the live-update stream use it |
| `AWS_ACCESS_KEY_ID` | `.env` (Neon Object Storage) |
| `AWS_SECRET_ACCESS_KEY` | `.env` |
| `AWS_ENDPOINT_URL_S3` | `.env` |
| `AWS_REGION` | `.env` |
| `LOGFIRE_TOKEN` | `.env` |

`CORS_ORIGINS` is pre-set to `*` by the Blueprint, so leave it. Model settings have working defaults in `backend/app/config.py`; add any of these as env vars to override them without a code change:

| Variable | Default | Notes |
|---|---|---|
| `AGENT_MODEL` | `deepinfra:Qwen/Qwen3-235B-A22B-Instruct-2507` | the five agents; 22/22 on the golden run. Prefixes: `deepinfra:`, `nvidia:`, `openrouter:`, `google:`, `anthropic:` |
| `AGENT_FALLBACK_MODELS` | `deepinfra:Qwen/Qwen3.6-27B` | full `provider:model` strings, tried in order when the main model errors |
| `VISION_MODEL` / `VISION_FALLBACK_MODELS` | `google:gemini-3.5-flash`, then DeepInfra Gemma 4 turbo, Gemini Flash-Lite | Image Analysis; every model must accept images. Gemini's free tier: 20 requests a day per model |
| `AGENT_OUTPUT_MODE` / `VISION_OUTPUT_MODE` | `tool` / `prompted` | how each returns its typed result |
| `AGENT_MAX_TOKENS` / `AGENT_EFFORT` / `AGENT_TEMPERATURE` | 16000 / `medium` / unset | effort is Anthropic-only; Claude Haiku 5.5 and Opus 5.5 reject a temperature |

DeepInfra is paid per token (about $0.012 a fully argued case on Qwen3-235B) with 200 concurrent requests per model and no daily cap. Set a spending limit on the DeepInfra account. Free tiers tried before it (OpenRouter 50 requests a day, Gemini 20, NVIDIA's queueing) couldn't run the golden suite reliably.

### 4. Wait for the first deploy

Render builds the image and then checks `/health`. When it shows **Live**, note the URL, which looks like `https://ryde-resolve-api-xxxx.onrender.com`.

Quick check:

```bash
curl https://<your-url>/health                       # {"status":"ok"}
curl "https://<your-url>/demo/personas?limit=2"      # two personas from the generated dataset
```

### 5. Run the end-to-end smoke test against it

From `backend/` on your machine, with the root `.env` present (the script seeds its own test data straight into Neon):

```bash
uv sync
uv run python -m scripts.smoke_e2e --base-url https://<your-url>
```

It takes about 5–10 minutes and makes real model calls. **Expected:**

| Scenario | State | Remedy |
|---|---|---|
| route_deviation | `decided` | partial refund $1.16 |
| no_show_charge | `escalated` | no-show fee waiver $4.50 (repeat-filer bucket) |
| property_damage | `decided` | cleaning fee $40.00 (Image Analysis grades the rendered photo a drink spill, the minor tier) |

Confidence values vary run to run; states and amounts shouldn't. The script deletes everything it seeded. If it crashes partway, run `uv run python -m scripts.smoke_e2e --cleanup-only`.

### 6. Check the live stream through Render's proxy

```bash
curl -N https://<your-url>/events/l2
```

You should get `: ping` comments every 15 seconds and the connection should stay open. (Stop it with Ctrl-C.) If the connection closes or nothing arrives, Render is buffering the stream; tell @suryaansh2002 before going further, because the frontend's live trace panel depends on it.

## Things to know

- **Cold starts.** The free tier sleeps after 15 idle minutes, and the next request takes about a minute to wake it. Hit `/health` a couple of minutes before any demo or recording. An open live stream keeps it awake.
- **Logs.** Render dashboard → service → Logs. Agent runs and tool calls are also in Logfire (project for `LOGFIRE_TOKEN`), service name `ryde-resolve-api`.
- **Dates.** The synthetic trips are dated relative to when the data was generated, and claims are only allowed within 30 days of a trip. Before a demo or recording, run `uv run python -m scripts.shift_dates` from `backend/` (with the root `.env`). It moves the whole timeline forward, so every trip is recent again. It writes straight to Neon, so it doesn't matter where the backend runs.
- **Golden run on the free tier.** `POST /golden-run` takes about 8 minutes and runs inside the web process. Keep the Accuracy page open while it runs: its polling keeps the instance awake. A restart mid-run loses the progress counter, but finished cases are already saved.
- **Usage.** Every model call writes a row to `llm_usage` (tokens per case and agent). Nothing to configure.
- **The repo will move.** Before submission we rotate every key in `.env` (they're in git history) and publish a fresh public repo. When that happens, this service gets re-pointed to the new repo and its secrets replaced with the new ones. Don't spend time hardening anything tied to the current keys.

## Part 2 — Frontend on Vercel

The frontend (`frontend/`, React + Vite) is built and was tested end to end in a browser against the local backend. It needs the Render URL from Part 1.

1. Vercel dashboard → **Add New → Project** → import this repo. The same private-repo access question applies: if Vercel can't see it, ask @suryaansh2002 to grant the Vercel GitHub app access to it.
2. **Root Directory:** `frontend`. Framework preset: **Vite** (detected automatically). Build command `npm run build` and output `dist` are the defaults.
3. **Environment variable:** `VITE_API_URL` = the Render URL from Part 1, e.g. `https://ryde-resolve-api-xxxx.onrender.com` with no trailing slash. It's baked in at build time, so if you change it later, redeploy.
4. Deploy. `frontend/vercel.json` already rewrites every path to `index.html`, so deep links like `/trace/CASE-0001` load directly.
5. Back on Render, set `CORS_ORIGINS` to the Vercel URL (e.g. `https://ryde-resolve.vercel.app`) and let it redeploy. Until then `*` works.
6. **Walk the golden path in a browser** on the Vercel URL:
   1. **Overview** → under *Run a demo case*, click **The long way round**. It picks a suitable trip, signs you in as the rider, and pre-fills the report.
   2. **Submit report**. The case page shows a progress stepper; after about 20 seconds it reaches *Awaiting response*.
   3. Under *Both sides*, click **Demo: respond as …** → **Use example text** → **Send my side**.
   4. **Watch the agents →**: the route line fills in live, both advocates appear side by side, then the Judge's ruling. Click any citation chip (e.g. `ROUTE-COMPARISON`); a drawer opens with the map.
   5. Back on the case page, after about 30 seconds you get the decision. Repeat with **A mess in the back seat** (damage, with Image Analysis) and **Something felt unsafe** (goes straight to a person).
   6. **Human review**: escalated and safety cases are listed. Select one with `J`, ratify with `A` or override with `O`.
   7. **Accuracy**: shows the last golden run. Don't start a new one here unless you have 8 minutes.

   If the first page says it's waking the backend, wait for it: that's the free tier's cold start. Theme toggle is top right; check both light and dark.

## Done checklist

- [ ] Service `ryde-resolve-api` is Live on Render (Ohio, free)
- [ ] `/health` returns ok and `/demo/personas` returns data
- [ ] `smoke_e2e` passes against the live URL with the expected table above
- [ ] `/events/l2` holds the connection open with pings
- [ ] Frontend live on Vercel with `VITE_API_URL` set; deep links load
- [ ] `CORS_ORIGINS` on Render set to the Vercel URL
- [ ] Golden path walked on the live URLs (demo case → respond → decision → trace with evidence drawer → human review → Accuracy page)
- [ ] `scripts.shift_dates` run before any demo or recording
- [ ] Both URLs shared with @suryaansh2002, and added to the Execution Plan and README
