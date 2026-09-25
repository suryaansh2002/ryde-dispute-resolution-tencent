# RydeResolve — Development Roadmap (v2)

**Assumes:** 2 developers, ~14 calendar days, AI coding assistants used as a pair-programming force multiplier throughout (proof capture for the mandatory CodeBuddy/WorkBuddy requirement — system design §8 — is a running task, not a last-day scramble). Built directly against the three now-finalized documents: the System Design doc, the Policy & Prevention Rules doc (v3 — Part 1 reconciled against real Ryde figures), and the Data Sources & Strategy doc (v2 — finalized). Section references below point back to those.

**v2 change, stated plainly:** v1 split ownership by architecture *layer* — one dev owned all agent/backend logic, the other owned all data, all four frontend panels, and all infra/deployment. That's not an even split (the second dev's slice was strictly larger) and it isn't a full-stack split (neither dev touched both backend and frontend). v2 replaces this with a split along the **pipeline's natural data seam**: each dev owns a full-stack half — backend logic, the schema/data it needs, and the frontend surface that consumes it — for one contiguous stage of the flow. See §0 for the split and §1a for how the resulting cross-dependency (Dev B's Advocates need Dev A's `CaseFile`, and vice versa for decision output) is de-risked so neither dev blocks on the other.

---

## 0. Ownership split

Two developers, split by **pipeline stage**, each owning a full-stack vertical slice — backend agent/rules logic, the schema it needs, and the frontend surface built on top of it — rather than one dev owning all backend and the other all frontend/data/infra.

| Owner | Owns | Source doc |
|---|---|---|
| **Dev A — "Intake & Evidence"** (everything up to and including the `CaseFile`) | Triage Agent, Prevention Rules, Evidence Collection Agent + its tools; `trips`/`payments`/`chat_messages`/`traffic_events` schema; the synthetic data generation pipeline; Rider & Driver panels' claim-filing and evidence-upload flows; R2 upload wiring | System Design §4, §6 (Triage, Evidence Collection); Data Sources doc |
| **Dev B — "Adjudication & Delivery"** (everything from the advocates onward) | Rider/Driver Advocates + their tools, Judge + its tools, the two-phase escalation gate, compliance check, decision-document rendering; `policy_chunks` ingestion + Policy RAG; golden-case suite + dashboard; System Trace Panel + SSE broadcaster + trace event bus; L2 console; Logfire instrumentation; deployment/infra (Vercel, Render, Neon, R2 setup) | System Design §4, §6 (Advocates, Judge), §6.1, §6.3, §9 |
| **Shared** | Orchestrator/state machine skeleton (both halves plug into it — heads-up before touching it either way); API contract and `CaseFile`/`Argument`/`DecisionObject`/`TriageResult` schemas (locked Day 1); CodeBuddy/WorkBuddy proof capture (ongoing, both devs capture their own sessions); demo video; submission checklist | System Design §4, §7, §10 |

This mirrors the actual data flow: Dev A owns everything that produces a `CaseFile`, Dev B owns everything that consumes it and turns it into a decision. Both halves are naturally full-stack — each stage has its own agent(s)/rules, its own schema slice, and its own UI surface — instead of one dev being backend-only and the other doing backend, all frontend, all data, and all infra.

Nobody touches the other's core files without a heads-up, to avoid merge conflicts in a two-week sprint.

### 0a. De-risking the cross-dependency: contract-first + fixtures

Splitting at the `CaseFile` seam creates an obvious risk: Dev B's Advocates need a real `CaseFile` that only Dev A's Evidence Collection Agent produces, and symmetrically Dev A's Rider/Driver panels need a real `DecisionObject`/trace events that only Dev B's Judge/SSE layer produces. Built naively and sequentially, each dev spends days blocked waiting on the other's half to exist. The fix is contract-first development, not sequential handoff:

- **Day 1 (joint):** lock the `CaseFile`, `Argument`, `DecisionObject`, and `TriageResult` schemas, plus the REST/SSE API contract. This is the seam — once it's fixed, neither dev needs the other's actual implementation to start building against it.
- **Day 2:** Dev A hand-writes 2–3 `CaseFile` fixtures (JSON, one per category) matching the locked schema. Dev B hand-writes fixture `DecisionObject`s and `agent_output`/`agent_complete` trace events matching the same contract.
- **Day 3–4:** Dev B builds and tests the Advocates and (from Day 5) the Judge against Dev A's fixtures — fully decoupled from whether the real Evidence Collection Agent is done. In parallel, Dev A builds and tests the real Evidence Collection Agent, and builds the Rider/Driver panels' redacted-view and decision-document rendering against Dev B's fixture `DecisionObject`s and trace events — decoupled from whether the real Judge/SSE layer is done.
- **Day 5 (integration gate):** swap fixtures for the real upstream/downstream calls on both sides. Some schema drift between what a fixture assumed and what the real implementation actually produces is expected here — it's a small reconciliation at this point, not a multi-day blocking dependency, because both sides have already been built and tested independently against the shared contract.

This is what makes the existing Day 5 "critical gate" milestone below load-bearing: it's not just "first time everything runs," it's specifically the point where fixture-based parallel work gets reconciled into one real pipeline.

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
| **1** | Stand up Neon (pgvector on); write initial migration for `cases`, `evidence`, `trips`, `payments`, `chat_messages`, `traffic_events`, `behavior_profiles` | Stand up Vercel project + Render Docker skeleton; hello-world backend on Render + hello-world frontend on Vercel, both reachable | **Joint first:** lock `CaseFile`, `Argument`, `DecisionObject`, `TriageResult`, and the API surface (system design §4, §7) before either dev writes real logic |
| **2** | Implement all 6 Prevention Rules (Policy doc Part 2) with unit tests per rule; stub Triage Agent (`TriageResult` output, no real logic yet), including the safety hard-stop; hand-write 2–3 `CaseFile` fixtures (one per category, matching the Day-1 schema) for Dev B to build against | Start `policy_chunks` ingestion from Policy doc Part 1; scaffold Advocate + Judge agent files with typed signatures against the locked schemas; hand-write fixture `DecisionObject`s and `agent_output`/`agent_complete` trace events for Dev A to build against | A raw claim POSTed to `/cases` gets triaged and either hard-stopped or passed through (API only, no UI yet); fixtures exchanged both ways so Day 3 onward is unblocked for both devs (§0a) |
| **3–4** | Implement Evidence Collection Agent (assembles `CaseFile` via its DB Query / R2 Fetch / Policy RAG tools, with the output validator confirming every evidence reference resolves to a real Postgres row or R2 object — system design §4 rule 6); build the synthetic data generation pipeline steps 1–7 (Data Sources doc §4): trip population, OneMap routing, category assignment, route perturbation, traffic events, GPS trace, fare/payment generation | Implement Rider + Driver Advocate agents with Evidence Lookup tool and the citation-validity output validator, built and tested against Dev A's Day-2 `CaseFile` fixtures — not yet wired to the real Evidence Collection Agent; implement the SSE broadcaster (`/events/cases/{id}`, `/events/l2`) and trace event bus, and start Rider/Driver panel shells (redacted view, decision document display) rendering Dev B's own fixture `DecisionObject`s/trace events | Given one seeded trip, Dev A's real Evidence Collection Agent produces a `CaseFile`; independently, Dev B's advocates produce a policy-cited `Argument` from the fixture `CaseFile` — not yet wired together |
| **5** | Wire Dev B's Advocates to consume the *real* `CaseFile` (swap fixture for live Evidence Collection output); begin Rider/Driver panel claim-filing and evidence-upload flows against the real API | Implement Judge agent (Policy RAG + Prevention-Rule Bucket + Escalate-to-L2 tools, `DecisionObject` schema + validator); implement the two-phase escalation gate as deterministic orchestrator code; implement `compliance_check()` and `render_decision_document()`; wire Rider/Driver panels' decision-document rendering to the *real* `DecisionObject`/trace events (swap fixtures for live output) | **Critical gate, and the fixture-integration point (§0a):** first full end-to-end run — claim → Triage → Prevention → Evidence Collection → Advocates → Judge → Escalation gate → decision document — on Route Deviation or No-Show (simpler than Property Damage since no photo evidence needed yet) |
| **6–7** | Photo upload → R2 pipeline; generate/source the Property Damage photo set (Data Sources doc §4 steps 8–10); wire the Property Damage evidence path into Evidence Collection Agent; harden the Evidence Collection output validator and its retry behavior | Implement the Image Analysis tool (vision call → `DamageFinding`) and wire it into the Property Damage advocate/Judge reasoning path; build the L2 console (queue view, ratification action); harden the advocates'/Judge's output validators and retry behavior | All three categories runnable end-to-end; L2 console can view and ratify an escalated case |
| **8** | Hand-label 30–50 golden cases across all three categories plus a few safety-flagged trips (Data Sources doc §4 step 11), using the now-real data pipeline | Add Logfire instrumentation (`logfire.configure()`, `instrument_pydantic_ai()`); verify tool-call spans show up correctly for both advocates and the Judge; build the `/golden-run` endpoint and dashboard widgets (golden-case pass rate, throughput, category breakdown) | Logfire dashboard live with real spans; golden-case suite runs and reports a real pass-rate number |
| **9** | Decide and implement the evidence-disclosure-to-complainee behavior (system design §6.2 — still open; default to "outcome only, no evidence shown" as the more conservative choice unless decided otherwise); complete Rider/Driver panels (redacted view, decision document display) against real data; persona picker | Complete the System Trace Panel (readable argument cards) against real trace events; CodeBuddy/WorkBuddy proof capture checkpoint | Frontend feature-complete against all four views (system design §3) |
| **10** | Decide and wire the escalation bucket table contents (system design §6.1 — still open; start with a conservative default like "everything agent-decidable except anything already safety-flagged or fraud-flagged by Prevention Rule 5" and tune from there); re-check Prevention Rule 5's threshold now that it has no Fraud Agent backstop | Data quality pass on synthetic data (sanity-check GPS traces, fare consistency, photo-tier matching); deployment/infra double-check prep (Vercel/Render/Neon/R2 config) | Escalation gate fully deterministic and tested on both phases independently |
| **11** | **Joint bug bash** — run the golden-case suite, manually test each category through the actual UI, fix what breaks | **Joint bug bash** — same day, paired testing; verify SSE reconnect behavior and that Render's free-tier spin-down doesn't break a judge's first click | No known critical bugs; golden-case pass rate recorded for submission materials |
| **12** | Production deployment double-check: env vars, secrets, Groq rate-limit headroom, error/fallback states, for the agent/backend side | Finalize infra deployment (Vercel/Render/Neon/R2); draft submission form content (title, blurb, description) from the architecture docs; export the mermaid diagrams as the architecture-diagram deliverable; prepare cover image | Live URL stable and reachable exactly as a judge would hit it |
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
