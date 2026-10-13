"""Evidence Collection Agent (system design §4 rule 6, §6). Runs right after Prevention
rules, before either advocate — the only agent in the roster with direct Postgres/Neon
Object Storage access (via its DB Query / Object Storage Fetch tools). Assembles one
canonical `CaseFile` per case.

Design choice, stated plainly: rather than trusting the model to transcribe raw DB rows
into `CaseFile`'s output fields byte-for-byte (expensive, and the only way a free-form
LLM output could introduce drift from the real data), every raw-data field is
reconstructed directly from the `TripBundle` the DB Query tool fetched this run. That
makes "every evidence reference resolves to a real Postgres row" true by construction,
not just by validation. The model's actual judgment call is `policy_tags` — deciding
what to search for and when — mirroring how `policy_rag` works for the advocates
(system design §4 rule 1 validates that the same way: every tag must trace to an actual
`policy_rag` call this run).

The agent's own `output_type` is deliberately just the small `policy_tags` list, not the
full `CaseFile` — asking the model to also echo a (potentially 100+ point) `gps_trace`
back through its own tool-call output just to have it discarded wastes tokens and, at
realistic trace sizes, occasionally breaks the model's own tool-call formatting (seen in
practice against generated data: Groq's qwen3 mangled its structured output once traces
got past ~50 points). Reconstruction into the real `CaseFile` happens in
`run_evidence_collection`, after the agent returns, not inside pydantic-ai's output
validation — the public contract (`run_evidence_collection` returns a `CaseFile`) is
unchanged.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext

from app.agents.llm import agent_model, agent_model_settings, output_spec
from app.agents.retry import run_agent
from app.data.db import TripBundle, fetch_trip_bundle, get_connection
from app.schemas import (
    BehaviorProfile,
    CaseFile,
    CaseRole,
    ChatMessage,
    DisputeCategory,
    EvidencePhoto,
    GPSPoint,
    PaymentBreakdown,
    PolicyTag,
)
from app.schemas.triage import TriageResult
from app.tools.object_storage import object_exists
from app.tools.policy_rag import search_policy

SYSTEM_PROMPT = """\
You are the Evidence Collection Agent for RydeResolve. You assemble one canonical case
file for a dispute, before either side's advocate sees anything.

Steps:
1. Call db_query once to pull this case's trip, payment, chat log, evidence, and both
   parties' behavior profiles. Every raw field in your output gets reconstructed from
   this real data regardless of what you write there, so there is no benefit to
   transcribing it yourself — call it once and move on.
2. Decide what policy clauses this case will need, based on its category and what the
   chat log / evidence actually describe, and call policy_rag with focused queries (not
   one query for the whole case). Only tags you actually retrieve this way can appear in
   your final `policy_tags` — do not invent a tag's chunk_id or excerpt.
3. Output `policy_tags`: the chunk_id/policy_id/excerpt of every clause you decided is
   relevant, copied exactly from what policy_rag returned. That's the only output you
   produce — the rest of the case file is assembled separately from step 1's data.
"""


class PolicyTags(BaseModel):
    policy_tags: list[PolicyTag] = []


@dataclass
class EvidenceCollectionDeps:
    trip_id: str
    case_id: str
    category: DisputeCategory
    complainer_role: CaseRole
    complainer_id: str
    complainee_id: str
    bundle: TripBundle | None = None
    retrieved_tags: dict[str, PolicyTag] = field(default_factory=dict)


def _profile(
    user_id: str, role: CaseRole, user_row: dict, profile_row: dict | None
) -> BehaviorProfile:
    if profile_row is None:
        return BehaviorProfile(
            user_id=user_id, role=role, dispute_count_30d=0, upheld_denied_ratio=None,
            rating_trend=float(user_row.get("rating_trend") or 0.0),
            account_age_days=0,
        )
    upheld, denied = profile_row["upheld_count"], profile_row["denied_count"]
    ratio = upheld / (upheld + denied) if (upheld + denied) else None
    return BehaviorProfile(
        user_id=user_id, role=role,
        dispute_count_30d=profile_row["dispute_count_30d"],
        upheld_denied_ratio=ratio,
        rating_trend=(
            float(profile_row["rating_trend"])
            if profile_row["rating_trend"] is not None else None
        ),
        account_age_days=profile_row["account_age_days"],
    )


def _reconstruct(deps: EvidenceCollectionDeps, model_tags: list[PolicyTag]) -> CaseFile:
    b = deps.bundle
    assert b is not None
    trip = b.trip

    chat_log = [
        ChatMessage(
            id=m["id"], sender_role=CaseRole(m["sender_role"]),
            timestamp=m["timestamp"], text=m["text"],
        )
        for m in b.chat_messages
    ]
    photos = [
        EvidencePhoto(evidence_id=e["id"], r2_object_key=e["object_key"], hash=e["hash"],
                      submitted_at=e["submitted_at"])
        for e in b.evidence
        if object_exists(e["object_key"])
    ]
    payment = (
        PaymentBreakdown(
            base_fare=float(b.payment["base_fare"]), platform_fee=float(b.payment["platform_fee"]),
            taxes=float(b.payment["taxes"]), total_fare=float(b.payment["total_fare"]),
            add_on_fees=b.payment["add_on_fees"] or [],
        )
        if b.payment else PaymentBreakdown(base_fare=0, platform_fee=0, taxes=0, total_fare=0)
    )
    gps_trace = [GPSPoint(**p) for p in (trip.get("gps_trace") or [])]

    valid_tags = {t.chunk_id: t for t in model_tags if t.chunk_id in deps.retrieved_tags}

    return CaseFile(
        case_id=deps.case_id,
        trip_id=deps.trip_id,
        category=deps.category,
        complainer_role=deps.complainer_role,
        complainer_id=deps.complainer_id,
        complainee_id=deps.complainee_id,
        trip_started_at=trip.get("scheduled_at"),
        trip_completed_at=trip.get("completed_at"),
        chat_log=chat_log,
        pickup_lat=trip["pickup_lat"],
        pickup_lng=trip["pickup_lng"],
        gps_trace=gps_trace,
        optimal_route_geometry=trip.get("optimal_route_geometry"),
        actual_route_geometry=trip.get("actual_route_geometry"),
        payment=payment,
        photos=photos,
        traffic_events=b.traffic_events,
        complainer_profile=_profile(
            deps.complainer_id, deps.complainer_role, b.complainer, b.complainer_profile
        ),
        complainee_profile=_profile(
            deps.complainee_id,
            CaseRole.DRIVER if deps.complainer_role == CaseRole.RIDER else CaseRole.RIDER,
            b.complainee, b.complainee_profile,
        ),
        policy_tags=list(valid_tags.values()),
    )


evidence_collection_agent = Agent(
    agent_model(),
    output_type=output_spec(PolicyTags),
    deps_type=EvidenceCollectionDeps,
    system_prompt=SYSTEM_PROMPT,
    model_settings=agent_model_settings(),
    defer_model_check=True,
    name="evidence_collection",
)


@evidence_collection_agent.tool
async def db_query(
    ctx: RunContext[EvidenceCollectionDeps], case_id: str | None = None
) -> str:
    """Fetch this case's trip, payment, chat log, evidence, and behavior profile data."""
    # `case_id` is ignored (the case comes from deps); it's accepted because some models
    # (e.g. OpenRouter's free Nemotron) won't call a zero-argument tool without one.
    conn = await get_connection()
    try:
        ctx.deps.bundle = await fetch_trip_bundle(
            conn, ctx.deps.trip_id, ctx.deps.case_id, ctx.deps.complainer_id, ctx.deps.complainee_id
        )
    finally:
        await conn.close()
    b = ctx.deps.bundle
    return (
        f"trip={b.trip}\npayment={b.payment}\nchat_messages={b.chat_messages}\n"
        f"traffic_events={b.traffic_events}\nevidence={b.evidence}\n"
        f"complainer_profile={b.complainer_profile}\ncomplainee_profile={b.complainee_profile}"
    )


@evidence_collection_agent.tool
async def policy_rag(ctx: RunContext[EvidenceCollectionDeps], query: str) -> list[dict]:
    """Search the dispute resolution policy. Returns the most relevant clauses, which
    you may then attach in `policy_tags`."""
    hits = search_policy(query)
    for h in hits:
        ctx.deps.retrieved_tags[h.chunk_id] = h
    return [h.model_dump() for h in hits]


@evidence_collection_agent.output_validator
async def validate_db_query_was_called(
    ctx: RunContext[EvidenceCollectionDeps], out: PolicyTags
) -> PolicyTags:
    if ctx.deps.bundle is None:
        if ctx.retry < ctx.max_retries:
            raise ModelRetry("Call db_query before producing policy_tags.")
        raise ModelRetry("db_query was never called — cannot assemble a case file without it.")
    return out


async def run_evidence_collection(
    trip_id: str,
    case_id: str,
    triage_result: TriageResult,
    complainer_role: CaseRole,
    complainer_id: str,
    complainee_id: str,
) -> CaseFile:
    deps = EvidenceCollectionDeps(
        # str()'d defensively — trips.rider_id/driver_id are UUID columns upstream, and
        # it's easy for a caller to forget to stringify before this contract's `str` type.
        trip_id=str(trip_id), case_id=str(case_id), category=triage_result.category,
        complainer_role=complainer_role, complainer_id=str(complainer_id),
        complainee_id=str(complainee_id),
    )
    result = await run_agent(
        evidence_collection_agent,
        f"case_id: {case_id}\ntrip_id: {trip_id}\ncategory: {triage_result.category}\n"
        f"tier: {triage_result.tier}",
        deps=deps,
    )
    return _reconstruct(deps, result.output.policy_tags)
