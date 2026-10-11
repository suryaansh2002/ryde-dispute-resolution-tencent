# RydeResolve — Development Roadmap (v3)

> **Superseded for sequencing** by [the Execution Plan](RydeResolve-Execution-Plan.md) (2026-10-11): the Dev A / Dev B split is suspended, and everything except the deploy and the CodeBuddy/WorkBuddy proof is built. This document is kept as the original plan.

**v3 change, stated plainly:** a review of v2 surfaced several places where the day-by-day plan (§2) didn't match the ownership split it claimed (§0), or left genuinely shared work with no assigned day or owner — not new scope, just closing gaps that would otherwise surface as merge conflicts or a Day 5 scramble. Specifically: the orchestrator/state-machine skeleton now has assigned days and an owner per stage instead of floating as an unscheduled "Shared" line item; the API route layer is explicitly split into per-domain router modules matching each dev's ownership instead of one shared file; Rider/Driver panel work is corrected to match §0a's actual intent (Dev A builds it end-to-end against Dev B's fixtures, not a Dev B start + Dev A finish handoff the day-by-day table previously implied); the escalation gate now has an explicit contract requiring it to read bucket contents from a lookup rather than hardcoding them, so Dev A's Day 10 task is a data change, not a code change to Dev B's gate; Property Damage's photo/`DamageFinding` evidence shape gets frozen jointly before Day 6 instead of being assumed compatible; and a Day 4 evening check-in is added ahead of the Day 5 integration gate, since that gate is bidirectionally blocking — either side slipping delays both. See §0, §0a, and §2 for the specific changes.

**Assumes:** 2 developers, ~14 calendar days, AI coding assistants used as a pair-programming force multiplier throughout (proof capture for the mandatory CodeBuddy/WorkBuddy requirement — system design §8 — is a running task, not a last-day scramble). Built directly against the three now-finalized documents: the System Design doc, the Policy & Prevention Rules doc (v3 — Part 1 reconciled against real Ryde figures), and the Data Sources & Strategy doc (v2 — finalized). Section references below point back to those. **Post-v2 patch:** references to R2/Cloudflare R2 below now read Neon Object Storage, following the system design doc's storage-provider swap (§9) — no change to ownership split, phasing, or day-by-day plan.

**v2 change, stated plainly:** v1 split ownership by architecture *layer* — one dev owned all agent/backend logic, the other owned all data, all four frontend panels, and all infra/deployment. That's not an even split (the second dev's slice was strictly larger) and it isn't a full-stack split (neither dev touched both backend and frontend). v2 replaces this with a split along the **pipeline's natural data seam**: each dev owns a full-stack half — backend logic, the schema/data it needs, and the frontend surface that consumes it — for one contiguous stage of the flow. See §0 for the split and §1a for how the resulting cross-dependency (Dev B's Advocates need Dev A's `CaseFile`, and vice versa for decision output) is de-risked so neither dev blocks on the other.

---

## 0. Ownership split

> **Current work distribution (2026-10-11):** see [Execution Plan §0](RydeResolve-Execution-Plan.md#0-who-does-what-now-work-distribution).
> - **Dev A** built the entire codebase: both halves of the original split below, plus Image Analysis, the golden run and the UI overhaul. Dev A now owns the key rotation and public repo, the demo video and the submission form.
> - **Dev B** owns:
>   - the CodeBuddy/WorkBuddy proof (the hard gate);
>   - the Render and Vercel deploys;
>   - the WorkBuddy-drafted submission copy and demo script;
>   - the cover image;
>   - re-pointing the deploys at the public repo.
>
> The table below is the original plan, kept for context.

Two developers, split by **pipeline stage**, each owning a full-stack vertical slice — backend agent/rules logic, the schema it needs, and the frontend surface built on top of it — rather than one dev owning all backend and the other all frontend/data/infra.

| Owner | Owns | Source doc |
|---|---|---|
| **Dev A — "Intake & Evidence"** (everything up to and including the `CaseFile`) | Triage Agent, Prevention Rules, Evidence Collection Agent + its tools; `trips`/`payments`/`chat_messages`/`traffic_events` schema; the synthetic data generation pipeline; Rider & Driver panels' claim-filing and evidence-upload flows; Neon Object Storage upload wiring | System Design §4, §6 (Triage, Evidence Collection); Data Sources doc |
| **Dev B — "Adjudication & Delivery"** (everything from the advocates onward) | Rider/Driver Advocates + their tools, Judge + its tools, the two-phase escalation gate, compliance check, decision-document rendering; `policy_chunks` ingestion + Policy RAG; golden-case suite + dashboard; System Trace Panel + SSE broadcaster + trace event bus; L2 console; Logfire instrumentation; deployment/infra (Vercel, Render, Neon — Postgres + Object Storage) | System Design §4, §6 (Advocates, Judge), §6.1, §6.3, §9 |
| **Shared** | API contract and `CaseFile`/`Argument`/`DecisionObject`/`TriageResult` schemas (locked Day 1); CodeBuddy/WorkBuddy proof capture (ongoing, both devs capture their own sessions); demo video; submission checklist | System Design §4, §7, §10 |

This mirrors the actual data flow: Dev A owns everything that produces a `CaseFile`, Dev B owns everything that consumes it and turns it into a decision. Both halves are naturally full-stack — each stage has its own agent(s)/rules, its own schema slice, and its own UI surface — instead of one dev being backend-only and the other doing backend, all frontend, all data, and all infra.

**The orchestrator/state-machine is no longer an unowned "Shared" line item (v3 fix)** — it's genuinely shared code (it calls into both devs' agents in sequence), but "shared" without an assigned day meant nobody had scheduled time to write it, despite Day 5's gate depending on it working. It's built incrementally by whoever needs the next stage of it: **Dev A drafts the skeleton on Day 2** — the `CaseState` transitions and trace-event emission hook, stubbed against the Day-1 locked schemas, covering `opened → triage → assembling` — since Dev A owns the API's claim-filing entry point that kicks the state machine off. **Dev B extends it on Day 5** to add the back-half states (`awaiting_response → adjudicating → decided`, plus the `safety_bypassed`/`declined_insufficient_evidence` branches) when wiring in the Judge and escalation gate. Either dev flags the other before changing a transition the other side's stage depends on.

**The API route layer is split into per-domain router modules, not one shared file (v3 fix):** `app/api/cases.py` + `app/api/evidence.py` (Dev A — claim filing, evidence upload, response submission) and `app/api/decisions.py` + `app/api/l2.py` + `app/api/events.py` (Dev B — decision fetch, L2 queue/ratification, SSE streams), each mounted onto the FastAPI app separately. Structurally prevents both devs editing the same routes file in the same days.

Nobody touches the other's core files without a heads-up, to avoid merge conflicts in a two-week sprint.

### 0a. De-risking the cross-dependency: contract-first + fixtures

Splitting at the `CaseFile` seam creates an obvious risk: Dev B's Advocates need a real `CaseFile` that only Dev A's Evidence Collection Agent produces, and symmetrically Dev A's Rider/Driver panels need a real `DecisionObject`/trace events that only Dev B's Judge/SSE layer produces. Built naively and sequentially, each dev spends days blocked waiting on the other's half to exist. The fix is contract-first development, not sequential handoff:

- **Day 1 (joint):** lock the `CaseFile`, `Argument`, `DecisionObject`, and `TriageResult` schemas, plus the REST/SSE API contract. This is the seam — once it's fixed, neither dev needs the other's actual implementation to start building against it.
- **Day 2:** Dev A hand-writes 2–3 `CaseFile` fixtures (JSON, one per category) matching the locked schema. Dev B hand-writes fixture `DecisionObject`s and `agent_output`/`agent_complete` trace events matching the same contract.
- **Day 3–4:** Dev B builds and tests the Advocates and (from Day 5) the Judge against Dev A's fixtures — fully decoupled from whether the real Evidence Collection Agent is done. In parallel, Dev A builds and tests the real Evidence Collection Agent, and builds the Rider/Driver panels' redacted-view and decision-document rendering against Dev B's fixture `DecisionObject`s and trace events — decoupled from whether the real Judge/SSE layer is done.
- **Day 4, evening (v3 addition) — 15-minute joint check-in:** confirm both sides are actually ready for the Day 5 swap before Day 5 morning arrives. This gate is bidirectionally blocking — Dev B's Advocates need Dev A's real Evidence Collection Agent, and Dev A's panels need Dev B's real Judge/SSE output, at the same time — so if either side is going to slip, it needs to surface the evening before, not be discovered mid-swap.
- **Day 5 (integration gate):** swap fixtures for the real upstream/downstream calls on both sides. Some schema drift between what a fixture assumed and what the real implementation actually produces is expected here — it's a small reconciliation at this point, not a multi-day blocking dependency, because both sides have already been built and tested independently against the shared contract.

This is what makes the existing Day 5 "critical gate" milestone below load-bearing: it's not just "first time everything runs," it's specifically the point where fixture-based parallel work gets reconciled into one real pipeline.

**Fixture-validity check (v3 addition):** each side's hand-written fixtures should be checked against the actual pydantic schema, not just eyeballed — a one-line test (`CaseFile.model_validate_json(fixture)` / `DecisionObject.model_validate_json(fixture)`) run from Day 2 onward catches schema drift the moment either side changes a schema, instead of at the Day 5 reconciliation.

---

## 1. Phasing overview

| Phase | Days | Goal |
|---|---|---|
| 1. Foundation | 1–2 | Repo, infra, schemas locked, Prevention Rules working standalone |
| 2. Core pipeline | 3–5 | Full baseline flow working end-to-end on at least one category |
| 3. Full roster + all categories | 6–8 | All three categories runnable; Image Analysis, observability, golden-case suite in place |
| 4. Frontend + polish | 9–10 | All four panels feature-complete; escalation bucket table decided and wired |
| 5. Hardening | 11 | Bug bash, full regression against golden cases |
| 6. Deployment + submission | 12–14 | Live, stable, demo recorded, submitted |

The single most important gate is the end of Phase 2 (Day 5): a claim going in one end and a decision document coming out the other, for real, on live infrastructure. If that slips, cut scope from Phase 3 (drop Image Analysis or one category) rather than compressing Phases 5–6 — a working three-category demo with weaker polish beats a broken five-agent one.

---

## 2. Day-by-day plan

| Day(s) | Dev A (intake & evidence) | Dev B (adjudication & delivery) | Exit milestone |
|---|---|---|---|
| **1** | Stand up Neon (pgvector on); write initial migration for `cases`, `evidence`, `trips`, `payments`, `chat_messages`, `traffic_events`, `behavior_profiles`; scaffold `app/api/cases.py` + `app/api/evidence.py` routers | Stand up Vercel project + Render Docker skeleton; hello-world backend on Render + hello-world frontend on Vercel, both reachable; scaffold `app/api/decisions.py` + `app/api/l2.py` + `app/api/events.py` routers | **Joint first:** lock `CaseFile`, `Argument`, `DecisionObject`, `TriageResult`, and the API surface (system design §4, §7) before either dev writes real logic |
| **2** | Implement all 6 Prevention Rules (Policy doc Part 2) with unit tests per rule; stub Triage Agent (`TriageResult` output, no real logic yet), including the safety hard-stop; hand-write 2–3 `CaseFile` fixtures (one per category, matching the Day-1 schema, with a validity test against the real schema — v3) for Dev B to build against; **draft the orchestrator skeleton** (`CaseState` transitions + trace-event emission hook for `opened → triage → assembling`, stubbed against Day-1 schemas — v3) | Start `policy_chunks` ingestion from Policy doc Part 1; scaffold Advocate + Judge agent files with typed signatures against the locked schemas; hand-write fixture `DecisionObject`s and `agent_output`/`agent_complete` trace events (with a validity test against the real schema — v3) for Dev A to build against | A raw claim POSTed to `/cases` gets triaged and either hard-stopped or passed through (API only, no UI yet); fixtures exchanged both ways so Day 3 onward is unblocked for both devs (§0a) |
| **3–4** | Implement Evidence Collection Agent (assembles `CaseFile` via its DB Query / Object Storage Fetch / Policy RAG tools, with the output validator confirming every evidence reference resolves to a real Postgres row or Neon Object Storage object — system design §4 rule 6); build the synthetic data generation pipeline steps 1–7 (Data Sources doc §4): trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation; **build the Rider/Driver panel shells (redacted view, decision-document display) against Dev B's Day-2 fixture `DecisionObject`s/trace events** (v3 — moved from Dev B's row to match §0a and avoid a mid-project handoff on the same component) | Implement Rider + Driver Advocate agents with Evidence Lookup tool and the citation-validity output validator, built and tested against Dev A's Day-2 `CaseFile` fixtures — not yet wired to the real Evidence Collection Agent; implement the SSE broadcaster (`/events/cases/{id}`, `/events/l2`) and trace event bus | Given one seeded trip, Dev A's real Evidence Collection Agent produces a `CaseFile`; independently, Dev B's advocates produce a policy-cited `Argument` from the fixture `CaseFile` — not yet wired together |
| **4, evening** | **Joint 15-min check-in (v3):** confirm both sides are actually ready for tomorrow's fixture swap — surface any slip now, not mid-integration | | Go/no-go on Day 5 proceeding as planned |
| **5** | Wire Dev B's Advocates to consume the *real* `CaseFile` (swap fixture for live Evidence Collection output); complete Rider/Driver panel claim-filing and evidence-upload flows against the real API, and wire the panels' decision-document rendering to the *real* `DecisionObject`/trace events (swap fixtures for live output) | Implement Judge agent (Policy RAG + Prevention-Rule Bucket + Escalate-to-L2 tools, `DecisionObject` schema + validator); implement the two-phase escalation gate as deterministic orchestrator code — **reading bucket contents from an external lookup table/config, not hardcoded** (v3 — so Day 10's bucket-table decision is a data change, not a code change back into this gate); implement `compliance_check()` and `render_decision_document()`; **extend the orchestrator** with the back-half states (`awaiting_response → adjudicating → decided`, plus `safety_bypassed`/`declined_insufficient_evidence` branches — v3) | **Critical gate, and the fixture-integration point (§0a):** first full end-to-end run — claim → Triage → Prevention → Evidence Collection → Advocates → Judge → Escalation gate → decision document — on Route Deviation or No-Show (simpler than Property Damage since no photo evidence needed yet) |
| **6–7** | **Joint, first thing (v3):** freeze the Property Damage photo/`DamageFinding` evidence shape together before either side builds against it — a smaller version of the Day-5 cross-dependency, scoped to one category. Then: photo upload → Neon Object Storage pipeline; generate/source the Property Damage photo set (Data Sources doc §4 steps 8–10); wire the Property Damage evidence path into Evidence Collection Agent; harden the Evidence Collection output validator and its retry behavior | Implement the Image Analysis tool (vision call → `DamageFinding`, shape frozen jointly per the above) and wire it into the Property Damage advocate/Judge reasoning path; build the L2 console (queue view, ratification action); harden the advocates'/Judge's output validators and retry behavior | All three categories runnable end-to-end; L2 console can view and ratify an escalated case |
| **8** | Hand-label 30–50 golden cases across all three categories plus a few safety-flagged trips (Data Sources doc §4 step 11), using the now-real data pipeline | Add Logfire instrumentation (`logfire.configure()`, `instrument_pydantic_ai()`); verify tool-call spans show up correctly for both advocates and the Judge; build the `/golden-run` endpoint and dashboard widgets (golden-case pass rate, throughput, category breakdown) | Logfire dashboard live with real spans; golden-case suite runs and reports a real pass-rate number |
| **9** | Decide and implement the evidence-disclosure-to-complainee behavior (system design §6.2 — still open; default to "outcome only, no evidence shown" as the more conservative choice unless decided otherwise) and apply it to the Rider/Driver panels (already feature-complete against real data since Day 5 — v3); persona picker | Complete the System Trace Panel (readable argument cards) against real trace events; CodeBuddy/WorkBuddy proof capture checkpoint | Frontend feature-complete against all four views (system design §3) |
| **10** | Decide and wire the escalation bucket table contents (system design §6.1 — still open; start with a conservative default like "everything agent-decidable except anything already safety-flagged or fraud-flagged by Prevention Rule 5" and tune from there); re-check Prevention Rule 5's threshold now that it has no Fraud Agent backstop | Data quality pass on synthetic data (sanity-check GPS traces, fare consistency, photo-tier matching); deployment/infra double-check prep (Vercel/Render/Neon config — Postgres + Object Storage) | Escalation gate fully deterministic and tested on both phases independently |
| **11** | **Joint bug bash** — run the golden-case suite, manually test each category through the actual UI, fix what breaks | **Joint bug bash** — same day, paired testing; verify SSE reconnect behavior and that Render's free-tier spin-down doesn't break a judge's first click | No known critical bugs; golden-case pass rate recorded for submission materials |
| **12** | Production deployment double-check: env vars, secrets, Groq rate-limit headroom, error/fallback states, for the agent/backend side | Finalize infra deployment (Vercel/Render/Neon — Postgres + Object Storage); draft submission form content (title, blurb, description) from the architecture docs; export the mermaid diagrams as the architecture-diagram deliverable; prepare cover image | Live URL stable and reachable exactly as a judge would hit it |
| **13** | **Joint** — record the demo video (5–8 min: overview, agent features, build-approach reflection) | **Joint** — same day; do a full dry run of the live demo end to end before recording locks in | Demo video recorded and edited |
| **14** | Final bug fixes only — no new features | Compile final CodeBuddy/WorkBuddy proof; verify GitHub repo is public/accessible; submit both the general form and the Ryde-track-specific deliverables (system design §10) | **Submitted** |

---

## 3. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Dev B's Advocates/Judge depend on Dev A's `CaseFile`, and Dev A's panels depend on Dev B's `DecisionObject`/trace events — a naive sequential build blocks each dev on the other's half | Contract-first + fixtures (§0a): lock schemas Day 1, exchange hand-built fixtures Day 2, build both halves in parallel against the fixtures Day 3–4, reconcile at the Day 5 integration gate. Neither dev sits idle waiting on the other's real implementation |
| Render free-tier backend spins down after 15 min idle, first click looks slow to a judge | An open SSE connection counts as activity (system design §9) — send a low-frequency keep-alive ping in the days before the demo, or warm it manually right before a judge is expected to click |
| Groq free-tier rate limits get hit during dev/testing, not just the real demo | Run the golden-case suite sparingly during development, add basic backoff/retry around agent calls early rather than after a limit is hit |
| pydantic-ai output-validator retries add latency/cost when a citation check fails | Budget for this from Day 3 — test the validator's retry path deliberately, don't assume happy-path timing |
| Two developers, no redundancy per component | A short daily sync (15 min) plus these three documents as the single source of truth — if one dev is blocked, the docs (not tribal knowledge) are enough for the other to unblock them |
| Escalation bucket table (§6.1) and evidence-disclosure decision (§6.2) are still genuinely undecided | Both get a stated conservative default in the Day 9–10 rows above, chosen specifically because they're cheap to change later — the goal is not blocking the schedule on a decision that isn't ready, not pretending the decision has been made |
| ~~Policy doc Part 1's numbers didn't match the real figures used in the Data Sources doc~~ — **resolved:** Part 1 has been reconciled to the real figures (Policy doc v3); no longer a Day 2 risk | Kept as a row, struck through, so it's visible that this was caught and closed rather than silently dropped from the list |

---

## 4. Definition of done (demo-ready checklist)

Pulled directly from system design §10, restated as a pre-submission gate:

- [ ] Working prototype, end-to-end, for all three in-scope categories (exceeds the two-category minimum)
- [ ] Architecture diagrams captured (already produced — system design §2, §4, §6)
- [ ] Demo walkthrough video recorded, showing a dispute processed and resolved autonomously
- [ ] Public/judge-accessible GitHub repository link
- [ ] CodeBuddy conversation history (min. 3 screenshots) and, if used, WorkBuddy board export
- [ ] Golden-case pass rate available as a real, computed number for the dashboard
- [ ] Live URL confirmed reachable from a cold start (not just from a machine that's been actively developing against it)
