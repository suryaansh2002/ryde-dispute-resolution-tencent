"""Image Analysis: the tier mapping and the compliance rule built on it are plain code;
the vision call itself is monkeypatched (no network)."""

from pathlib import Path

import pytest

import app.tools.image_analysis as ia
from app.rules.compliance import compliance_check
from app.schemas import CaseFile, DamageFinding, DecisionOutcome, JudgeVerdict, Remedy
from app.schemas.common import RemedyType

CASE_FILES = Path(__file__).resolve().parents[1] / "data_generation" / "fixtures" / "case_files"


def damage_case(*tiers: str | None) -> CaseFile:
    case = CaseFile.model_validate_json((CASE_FILES / "property_damage.json").read_text())
    base = case.photos[0]
    photos = [
        base.model_copy(update={
            "evidence_id": f"EV-{i:04d}",
            "hash": f"sha256:{i}",
            "analysis": None if t is None else finding(t),
        })
        for i, t in enumerate(tiers, start=1)
    ]
    return case.model_copy(update={"photos": photos})


def finding(tier: str) -> DamageFinding:
    return DamageFinding(
        shows_vehicle_interior=True, mess_type="vomit", extent="large",
        description="d", confidence=0.9, tier=tier,
    )


def fee(amount: float) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=DecisionOutcome.CLAIM_UPHELD,
        remedy=Remedy(type=RemedyType.CLEANING_REPAIR_FEE, amount=amount),
        reasoning=[{"finding": "f", "cites": ["EV-0001"]}], policy_applied="POL-04",
        confidence=0.9,
    )


@pytest.mark.parametrize(
    ("mess", "tier"),
    [
        ("none", "none"),
        ("drink_spill", "minor"),
        ("food_crumbs", "minor"),
        ("mud_dirt", "moderate"),
        ("stain", "moderate"),
        ("bodily_fluid_other", "moderate"),
        ("vomit", "severe"),
        ("other_damage", "unclear"),
        ("made_up", "unclear"),
    ],
)
def test_mess_type_maps_to_the_policy_tier(mess, tier):
    assert ia.map_tier(True, mess, 0.9) == tier


def test_low_confidence_or_not_a_vehicle_supports_no_tier():
    assert ia.map_tier(True, "vomit", ia.MIN_CONFIDENCE - 0.01) == "unclear"
    assert ia.map_tier(False, "vomit", 0.99) == "unclear"


def test_supported_tier_is_the_highest_usable_finding():
    assert ia.supported_tier(damage_case("minor", "severe", "unclear").photos) == "severe"
    assert ia.supported_tier(damage_case("none", "none").photos) == "none"
    assert ia.supported_tier(damage_case("unclear", None).photos) is None


def test_fee_above_what_the_photo_shows_is_vetoed():
    veto = compliance_check(damage_case("minor"), fee(200.0))
    assert veto and "above the minor tier ($40)" in veto
    assert compliance_check(damage_case("minor"), fee(40.0)) is None
    assert compliance_check(damage_case("severe"), fee(200.0)) is None


def test_clean_photo_supports_no_fee_and_unanalysed_photos_defer_to_people():
    assert "show no mess" in compliance_check(damage_case("none"), fee(40.0))
    # Nothing usable from Image Analysis: the tier check is skipped, the rest still apply.
    assert compliance_check(damage_case(None), fee(200.0)) is None


async def test_analysis_is_attached_cached_and_failures_dont_block(monkeypatch):
    calls = []

    async def fake_vision(image: bytes) -> dict:
        calls.append(image)
        if image == b"broken":
            raise RuntimeError("vision down")
        return {"shows_vehicle_interior": True, "mess_type": "drink_spill", "extent": "small",
                "description": "coffee", "confidence": 0.9}

    monkeypatch.setattr(ia, "_vision_call", fake_vision)
    monkeypatch.setattr(ia, "get_object_bytes", lambda key: b"broken" if "bad" in key else b"ok")
    monkeypatch.setattr(ia, "_cache", {})
    case = damage_case(None, None)
    bad = case.photos[1].model_copy(update={"r2_object_key": "bad.jpg"})
    case = case.model_copy(update={"photos": [case.photos[0], bad]})

    analysed, errors = await ia.analyze_case_photos(case)
    assert analysed.photos[0].analysis.tier == "minor"
    assert analysed.photos[1].analysis is None and "EV-0002" in errors[0]

    await ia.analyze_case_photos(case)  # same hashes: the good photo is served from cache
    assert calls.count(b"ok") == 1


async def test_out_of_vocabulary_answer_becomes_unclear(monkeypatch):
    async def fake_vision(image: bytes) -> dict:
        return {"shows_vehicle_interior": True, "mess_type": "glitter", "extent": "huge",
                "description": "sparkly", "confidence": 0.9}

    monkeypatch.setattr(ia, "_vision_call", fake_vision)
    monkeypatch.setattr(ia, "get_object_bytes", lambda key: b"x")
    monkeypatch.setattr(ia, "_cache", {})
    result = await ia.analyze_photo(damage_case(None).photos[0])
    assert result.tier == "unclear" and result.confidence == 0.0
