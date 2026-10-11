"""Chat & claim text generation (data sources doc §4 step 8) — template-based per
category, randomized parameters. Never implies it's real Ryde user data.
"""

import random

from app.schemas.common import DisputeCategory

_ROUTE_DEVIATION_DRIVER = [
    "Sorry, the app rerouted me, traffic looked bad on the usual way.",
    "There was a road closure near {detour}, had to go around.",
    "My GPS took me that way, didn't realize it was longer.",
]
_ROUTE_DEVIATION_RIDER_CHAT = [
    "Why did we go through {detour}? That's way out of the way.",
    "This route doesn't match what the app showed me at pickup.",
]
_ROUTE_DEVIATION_CLAIM = [
    "The driver took a route that was much longer than necessary and I was charged "
    "extra for it. The detour through {detour} doesn't make sense for this trip.",
]

_NO_SHOW_DRIVER = ["I'm here", "Arrived at pickup point", "Waiting outside"]
_NO_SHOW_RIDER_CHAT = [
    "I don't see you anywhere, I've been waiting outside for {minutes} minutes",
    "Where are you? This doesn't match the pin location at all.",
]
_NO_SHOW_CLAIM_RIDER = [
    "The driver never showed up at the pickup location. I waited {minutes} minutes "
    "and had to cancel, but I was still charged a fee.",
]
_NO_SHOW_CLAIM_DRIVER = [
    "I waited at the pickup point for over the required time and the rider never "
    "came out. I should be able to charge the no-show fee.",
]

_PROPERTY_DAMAGE_DRIVER = [
    "You spilled a drink all over the back seat, I'm filing a cleaning fee claim.",
    "There's vomit on the seat, this needs a full cleaning.",
    "Found mud and dirt all over the floor mats after your trip.",
]
_PROPERTY_DAMAGE_RIDER_CHAT = [
    "That was already there before I got in.",
    "I didn't do anything, the car was already like that.",
]
_PROPERTY_DAMAGE_CLAIM = [
    "The rider left a mess in my vehicle that needs professional cleaning. "
    "I've attached a photo as evidence.",
]

_SAFETY_CLAIM = [
    "The driver was driving recklessly and ran two red lights, I felt unsafe the "
    "entire trip.",
    "The rider became aggressive and threatened me when I asked them to wear a seatbelt.",
]


def generate_chat_and_claim(
    category: DisputeCategory, complainer_role: str, rng: random.Random,
    traffic_event_exists: bool = False,
) -> tuple[list[dict], str]:
    """Returns (chat_messages_without_ids_or_timestamps, claim_text)."""
    detour = rng.choice(["downtown", "the industrial estate", "the old town loop"])
    minutes = rng.randint(4, 12)

    if category == DisputeCategory.ROUTE_DEVIATION:
        driver_line = rng.choice(_ROUTE_DEVIATION_DRIVER).format(detour=detour)
        if not traffic_event_exists:
            # Unsupported-assertion branch: driver claims a justification that isn't
            # backed by a real traffic_events row (data sources doc §4 step 8).
            driver_line = "There was a road closure, had to go around."
        chat = [
            {
                "sender_role": "rider",
                "text": rng.choice(_ROUTE_DEVIATION_RIDER_CHAT).format(detour=detour),
            },
            {"sender_role": "driver", "text": driver_line},
        ]
        claim = rng.choice(_ROUTE_DEVIATION_CLAIM).format(detour=detour)

    elif category == DisputeCategory.NO_SHOW_CHARGE:
        chat = [
            {"sender_role": "driver", "text": rng.choice(_NO_SHOW_DRIVER)},
            {
                "sender_role": "rider",
                "text": rng.choice(_NO_SHOW_RIDER_CHAT).format(minutes=minutes),
            },
        ]
        claim = (
            rng.choice(_NO_SHOW_CLAIM_RIDER).format(minutes=minutes)
            if complainer_role == "rider" else rng.choice(_NO_SHOW_CLAIM_DRIVER)
        )

    elif category == DisputeCategory.PROPERTY_DAMAGE:
        chat = [
            {"sender_role": "driver", "text": rng.choice(_PROPERTY_DAMAGE_DRIVER)},
            {"sender_role": "rider", "text": rng.choice(_PROPERTY_DAMAGE_RIDER_CHAT)},
        ]
        claim = rng.choice(_PROPERTY_DAMAGE_CLAIM)

    else:  # SAFETY_INCIDENT
        chat = [{"sender_role": complainer_role, "text": rng.choice(_SAFETY_CLAIM)}]
        claim = rng.choice(_SAFETY_CLAIM)

    return chat, claim
