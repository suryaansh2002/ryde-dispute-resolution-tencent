"""Image Analysis (system design §6): a vision call against one photo evidence ID.

Split in two on purpose:
- The vision model says what it sees: whether the photo shows a vehicle interior, the
  kind of mess, how much of the seat or floor it covers, and one factual sentence.
- `tier` is then mapped from the mess type in plain code, following the Policy doc's §4
  tier table (real, Ryde-sourced): minor = food/drink spillage or crumbs; moderate =
  bodily fluids or stains (mud, dirt, paint, oil); severe = vomit. So the fee tier is
  never the model's call, the same way refund amounts are computed in policy_math.

Runs once per photo, when the Evidence Collection Agent has assembled the case file,
and the finding is attached to the photo in the CaseFile. That keeps object storage
behind the Evidence Collection step (the only agent with storage access),
gives both advocates the identical finding (they read it with their own image_analysis
tool), and lets the Judge and the compliance check see it. Results are cached by photo
hash: the same bytes always get the same finding within a process.

Not one of the five pipeline agents: a single structured model call (one tool-free
pydantic_ai.Agent run), wrapped in a Logfire span.
"""

import asyncio
import json

import logfire
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, BinaryContent

from app.agents.llm import output_spec, vision_model, vision_model_settings
from app.agents.retry import run_agent
from app.schemas import CaseFile, DamageFinding, EvidencePhoto
from app.tools.object_storage import get_object_bytes

PROMPT = """\
This photo was submitted as evidence in a ride-hailing cleaning-fee dispute.
Describe only what is visible. Identify the main kind of mess, if any:
- "none": the surface looks clean
- "drink_spill": a single patch of spilled liquid such as coffee, soda or water, \
usually in one spot, often with a cup or bottle nearby
- "food_crumbs": loose dry food bits or wrappers
- "mud_dirt": mud, dirt, soil, muddy footprints or grime, often dry and crusty, \
in several patches or smears
- "stain": a dried stain or discoloration (paint, oil, tar, ink) without loose material
- "vomit": a pool of liquid mixed with lumps or chunks of food, often yellowish or \
orange, sometimes dripping or splattered. Any liquid containing food chunks is vomit.
- "bodily_fluid_other": blood, urine or similar
- "other_damage": tears, burns or broken parts
Also say how much of the seat or floor it covers: "small" (one spot), "medium", or "large".
Give one factual sentence describing the photo, and your confidence from 0 to 1."""


class VisionReading(BaseModel):
    """What the vision model reports; `mess_type` is checked against the vocabulary
    afterwards, so an out-of-vocabulary answer is recorded rather than retried."""

    shows_vehicle_interior: bool
    mess_type: str
    extent: str
    description: str
    confidence: float


vision_agent = Agent(
    vision_model(),
    output_type=output_spec(VisionReading),
    model_settings=vision_model_settings(),
    defer_model_check=True,
    name="image_analysis",
)

# Policy doc §4 tier table (real, Ryde-sourced categories). other_damage (tears, burns)
# isn't a cleaning tier at all, so it maps to "unclear" and leaves the call to a person.
MESS_TIER = {
    "none": "none",
    "drink_spill": "minor",
    "food_crumbs": "minor",
    "mud_dirt": "moderate",
    "stain": "moderate",
    "bodily_fluid_other": "moderate",
    "vomit": "severe",
    "other_damage": "unclear",
}
# Not Ryde-sourced, our own threshold: below this the finding supports no tier.
MIN_CONFIDENCE = 0.5
TIER_ORDER = ["none", "minor", "moderate", "severe"]

_cache: dict[str, DamageFinding] = {}


def map_tier(shows_vehicle_interior: bool, mess_type: str, confidence: float) -> str:
    if not shows_vehicle_interior or confidence < MIN_CONFIDENCE:
        return "unclear"
    return MESS_TIER.get(mess_type, "unclear")


def supported_tier(photos: list[EvidencePhoto]) -> str | None:
    """The highest tier any analysed photo supports, "none" if they all show no mess, or
    None if no photo has a usable finding (not analysed, failed, or unclear)."""
    tiers = [p.analysis.tier for p in photos if p.analysis and p.analysis.tier != "unclear"]
    if not tiers:
        return None
    return max(tiers, key=TIER_ORDER.index)


def _media_type(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


async def _vision_call(image: bytes) -> dict:
    """Retries and token accounting come from `run_agent`, as for every agent."""
    result = await run_agent(
        vision_agent, [PROMPT, BinaryContent(data=image, media_type=_media_type(image))]
    )
    return result.output.model_dump()


async def analyze_photo(photo: EvidencePhoto) -> DamageFinding:
    if photo.hash in _cache:
        return _cache[photo.hash]
    with logfire.span("image_analysis {evidence_id}", evidence_id=photo.evidence_id) as span:
        image = await asyncio.to_thread(get_object_bytes, photo.r2_object_key)
        raw = await _vision_call(image)
        try:
            confidence = min(max(float(raw.get("confidence", 0)), 0.0), 1.0)
            finding = DamageFinding(
                shows_vehicle_interior=bool(raw.get("shows_vehicle_interior", False)),
                mess_type=raw.get("mess_type", "other_damage"),
                extent=raw.get("extent", "small"),
                description=str(raw.get("description", ""))[:400],
                confidence=confidence,
                tier=map_tier(
                    bool(raw.get("shows_vehicle_interior", False)),
                    raw.get("mess_type", ""), confidence,
                ),
            )
        except (ValidationError, TypeError, ValueError):
            # The model answered outside the allowed vocabulary: say so, decide nothing.
            finding = DamageFinding(
                shows_vehicle_interior=False, mess_type="other_damage", extent="small",
                description=f"unreadable analysis: {json.dumps(raw)[:200]}",
                confidence=0.0, tier="unclear",
            )
        span.set_attribute("finding", finding.model_dump())
    _cache[photo.hash] = finding
    return finding


async def analyze_case_photos(case_file: CaseFile) -> tuple[CaseFile, list[str]]:
    """Returns the case file with every photo's finding attached, plus any per-photo
    errors. A failed photo keeps analysis=None; the rest of the case carries on."""
    results = await asyncio.gather(
        *(analyze_photo(p) for p in case_file.photos), return_exceptions=True
    )
    photos, errors = [], []
    for photo, result in zip(case_file.photos, results, strict=True):
        if isinstance(result, BaseException):
            errors.append(f"{photo.evidence_id}: {result!r}"[:200])
            photos.append(photo)
        else:
            photos.append(photo.model_copy(update={"analysis": result}))
    return case_file.model_copy(update={"photos": photos}), errors
