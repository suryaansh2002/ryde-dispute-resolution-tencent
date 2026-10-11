"""User & behavior-profile generation (data sources doc §4 step 9)."""

import random

FIRST_NAMES = ["Wei Jie", "Siti", "Arjun", "Mei Ling", "Hafiz", "Priya", "Jun Hao", "Nur",
               "Kevin", "Aisyah", "Ryan", "Farah", "Zhi Yang", "Kavya", "Daniel", "Izzah",
               "Marcus", "Hui Min", "Rajesh", "Amirah", "Ethan", "Shu Fen", "Imran", "Divya"]
LAST_NAMES = ["Tan", "Lim", "Ng", "Rahman", "Kumar", "Wong", "Lee", "Ismail", "Chen",
              "Pillai", "Goh", "Osman", "Teo", "Nair", "Koh", "Yusof", "Chua", "Menon"]


def generate_user(role: str, rng: random.Random, taken: set[str]) -> dict:
    """A user with a display name unique within `taken`, which the caller owns, so the
    persona picker never shows two identical names."""
    while True:
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in taken:
            taken.add(name)
            break
    return {
        "role": role,
        "display_name": name,
        "rating": round(rng.uniform(3.8, 5.0), 2),
        "rating_trend": round(rng.uniform(-0.05, 0.05), 3),
    }


def generate_behavior_profile(
    rng: random.Random, *, force_repeat_filer: bool = False, force_adverse_rating: bool = False,
) -> dict:
    """Rolling stats derived from generated dispute history. Deliberately seeds a
    handful of repeat-filer profiles (3+ disputes in 30 days, Prevention Rule 5) and
    adverse-rating profiles for the Judge to reason about."""
    dispute_count_30d = rng.randint(3, 5) if force_repeat_filer else rng.randint(0, 2)
    decided = rng.randint(0, 4)
    upheld = rng.randint(0, decided)
    return {
        "dispute_count_30d": dispute_count_30d,
        "upheld_count": upheld,
        "denied_count": decided - upheld,
        "rating_trend": round(rng.uniform(-0.15, -0.05), 3) if force_adverse_rating
        else round(rng.uniform(-0.02, 0.02), 3),
        "account_age_days": rng.randint(30, 900),
    }
