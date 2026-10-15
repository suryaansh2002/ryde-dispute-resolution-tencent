# frontend

React + Vite + TypeScript, running on the live API. Each role gets its own app, and all of them run on the same cases. There's no login: each scenario picks a synthetic persona and a trip from the demo data.

| Route | App |
|---|---|
| `/` | Overview: the rider's outcome next to the hearing behind it, both counsel's opening lines with footnoted evidence, who decides what (live queue counts), the golden-run accuracy |
| `/rider` | Rider app in a phone frame. Scenarios file a real report on a fresh trip: Activity → trip (map and receipt) → chat intake → "Before you send" → live progress → outcome. `?case=CASE-0153` opens a case as its rider |
| `/driver` | Driver app. Answer a report filed against you (inbox → their words → your reply), or file a cleaning fee with a photo, without one (declined, then resend), or a no-show. `?start=damage` picks the scenario, `?case=` opens a case |
| `/support`, `/support/:caseId` | Support console: the review queue (safety first, refreshed live over `/events/l2`), evidence first, the AI's recommendation hidden until asked, approve or change with an outcome, amount and reason. Safety reports offer "Prepare case file" (evidence only, no model call). Keys: J/K, A, C |
| `/trace`, `/trace/:caseId` | AI trace: the docket, and each case as a hearing (complaint, intake, clerk's checks, exhibits, photo examined, counsel, the bench, final checks, judgment). Live while a case runs; "Replay the hearing" for finished ones (`?replay=1`) |
| `/accuracy` | The 22 golden cases: pass rate, per category, label vs verdict per case, and a button to run them all again |

Beside each phone, the "Behind the scenes" panel shows the hearing as it happens. The party apps themselves never show the AI. When a rider's report waits for the driver's reply, the panel offers "Answer as <driver>" (opens the driver app on that case) or deciding on the records.

## Design

Apple calm, single light theme for consistent recording: grey ground, white sheets, near-black ink. Colour only does jobs: violet is the rider, teal the driver, green/amber/red are outcome states, blue is links and focus. System font (SF Pro) with Geist as the fallback, Geist Mono for IDs. Every token and component style is in `src/styles.css`, ported unchanged from the prototype. The signature is the citation chip: any claim an agent makes opens the exact evidence it cites (hover previews it, click opens the drawer: chat in context, a map drawn from the trip's own coordinates, the fare, the photo, or the policy clause with a plain summary).

- `src/lib/api.ts`, `src/types/api.ts`: REST client and hand-kept mirrors of the backend schemas
- `src/lib/live.ts`: `useLiveCase`, which fetches a finished case once and streams a running one over SSE (`/events/cases/{id}`), refetching its view, usage and decision as the state moves
- `src/lib/hearing.ts`: derives the hearing's steps from the trace events (drives the demo panel, the trace and its replay)
- `src/components/party.tsx`: chat intake (the bot's reply comes from the real Triage agent via `POST /intake/triage`, with a keyword guess only if that call fails; filing runs Triage again inside the pipeline, so the chat's reading is advisory), live progress stages, and the outcome screen, whose copy comes from `GET /cases/{id}/outcome`
- `src/components/evidence.tsx`: `<Cite>`, the evidence drawer, chat, receipt

## Running

```bash
npm install
npm run dev          # http://localhost:5173 — needs the backend on :8000
npm run build        # type-check + production build
npm run lint
```

Point at another backend with `VITE_API_URL` (see `.env.example`). It's read at build time, so set it in Vercel's project settings before building.

## Deploying (Vercel)

Project root `frontend/`, framework preset Vite, env var `VITE_API_URL=<the Render URL>`. `vercel.json` rewrites every path to `index.html`, so deep links like `/trace/CASE-0031` load.
