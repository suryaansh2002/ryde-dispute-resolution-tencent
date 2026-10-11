# frontend

React + Vite + TypeScript. One app with persona-scoped routes, not four separate apps (system design §3). There's no login, just a persona picker over the synthetic users.

| Route | View |
|---|---|
| `/` | Persona picker: riders, drivers, or the L2 console |
| `/:role/:userId` | Rider/Driver panel: cases waiting on you, your cases, your trips (file a claim) |
| `/:role/:userId/file/:tripId` | File a claim (photo upload goes first, then the claim) |
| `/:role/:userId/case/:caseId` | Case: claim, response (or the reply form), live progress, decision document |
| `/trace`, `/trace/:caseId` | System trace: every agent output and gate, live over SSE |
| `/l2`, `/l2/:caseId` | L2 console: live queue, agent recommendation, ratify/override |

- `src/types/api.ts`: hand-kept mirrors of the backend schemas
- `src/lib/api.ts`: REST client. Filing and responding use the backend's `?background=true` mode, so the UI gets the case id at once and watches the rest live.
- `src/lib/useEventStream.ts`: SSE hook; the backend replays history, then streams live, and `EventSource` resumes via `Last-Event-ID`
- `src/components/TraceTimeline.tsx`: renders trace events; the two advocates appear side by side

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
