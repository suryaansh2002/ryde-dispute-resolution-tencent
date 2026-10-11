# RydeResolve — Deploy the Backend to Render

**Owner:** Dev B (@shiv0112), on your own Render account.
**Status:** ready to deploy. The image builds and passes the end-to-end test locally. This is the only remaining part of step 2 in the [Execution Plan](RydeResolve-Execution-Plan.md).
**Time:** about 15 minutes, plus about 5 minutes for the first build.

When you're done, post the live URL in our chat and tick the checklist at the bottom.

---

## What you're deploying

- **Code:** `backend/` on `main`, built from `backend/Dockerfile` (Python 3.11 + uv, FastAPI on `$PORT`).
- **Service config:** `render.yaml` at the repo root, a Render Blueprint.
  - Free plan, **Ohio** region. That's the same AWS region as our Neon database (us-east-2), so database queries stay local.
  - Health check on `/health`.
  - Auto-deploys when `backend/**` changes on `main`.
- **External services the app talks to:** Neon Postgres, Neon Object Storage, Groq, Logfire. All of them already exist; you're only supplying their credentials.

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
| `GROQ_API_KEY` | `.env` |
| `DATABASE_URL` | `.env` (pooled Neon URL, quotes removed) |
| `DATABASE_URL_UNPOOLED` | `.env` (direct Neon URL, quotes removed). **Required:** the app's connections and the live-update stream use it |
| `AWS_ACCESS_KEY_ID` | `.env` (Neon Object Storage) |
| `AWS_SECRET_ACCESS_KEY` | `.env` |
| `AWS_ENDPOINT_URL_S3` | `.env` |
| `AWS_REGION` | `.env` |
| `LOGFIRE_TOKEN` | `.env` |

`CORS_ORIGINS` is pre-set to `*` by the Blueprint, so leave it. Don't add `GROQ_BASE_URL`; the default is correct, and the `/openai/v1` value in older notes caused 404s.

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

It takes about 3–5 minutes and makes real Groq calls. **Expected:**

| Scenario | State | Remedy |
|---|---|---|
| route_deviation | `decided` | partial refund $1.16 |
| no_show_charge | `escalated` | no-show fee waiver $4.50 (repeat-filer bucket) |
| property_damage | `decided` | cleaning fee $40.00 |

Confidence values vary run to run; states and amounts shouldn't. The script deletes everything it seeded. If it crashes partway, run `uv run python -m scripts.smoke_e2e --cleanup-only`.

### 6. Check the live stream through Render's proxy

```bash
curl -N https://<your-url>/events/l2
```

You should get `: ping` comments every 15 seconds and the connection should stay open. (Stop it with Ctrl-C.) If the connection closes or nothing arrives, Render is buffering the stream; tell @suryaansh2002 before going further, because the frontend's live trace panel depends on it.

## Things to know

- **Cold starts.** The free tier sleeps after 15 idle minutes, and the next request takes about a minute to wake it. Hit `/health` a couple of minutes before any demo or recording. An open live stream keeps it awake.
- **Logs.** Render dashboard → service → Logs. Agent runs and tool calls are also in Logfire (project for `LOGFIRE_TOKEN`), service name `ryde-resolve-api`.
- **The repo will move.** Before submission we rotate every key in `.env` (they're in git history) and publish a fresh public repo. When that happens, this service gets re-pointed to the new repo and its secrets replaced with the new ones. Don't spend time hardening anything tied to the current keys.
- **Later.** Once the frontend exists, set `CORS_ORIGINS` to the Vercel URL. The frontend deploy (Vercel) will get its own handoff doc.

## Done checklist

- [ ] Service `ryde-resolve-api` is Live on Render (Ohio, free)
- [ ] `/health` returns ok and `/demo/personas` returns data
- [ ] `smoke_e2e` passes against the live URL with the expected table above
- [ ] `/events/l2` holds the connection open with pings
- [ ] Live URL shared with @suryaansh2002, and added to the Execution Plan (step 2) and README
