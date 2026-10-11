"""Fare/payment generation (data sources doc §4 step 7) using Ryde's real published
figures (Policy doc Part 1) — never invented placeholders for these specific numbers.
"""

import random

# Real, sourced (Policy doc §2 destination-change / §3 no-show / §4 property damage).
PLATFORM_FEE_LOW = 1.25   # fares <= $18
PLATFORM_FEE_HIGH = 1.47  # fares > $18
PLATFORM_FEE_THRESHOLD = 18.00
NO_SHOW_FEE = 4.50
DESTINATION_CHANGE_FEE = 3.00
PROPERTY_DAMAGE_FEES = {"minor": 40.00, "moderate": 120.00, "severe": 200.00}

BASE_FARE_PER_KM = 1.20
BASE_FARE_MIN = 4.00
TAX_RATE = 0.09  # GST-inclusive-style flat rate for demo purposes — not a cited figure


def generate_fare(distance_km: float, rng: random.Random) -> dict:
    base_fare = max(
        BASE_FARE_MIN, round(distance_km * BASE_FARE_PER_KM * rng.uniform(0.9, 1.15), 2)
    )
    platform_fee = PLATFORM_FEE_LOW if base_fare <= PLATFORM_FEE_THRESHOLD else PLATFORM_FEE_HIGH
    taxes = round(base_fare * TAX_RATE, 2)
    total_fare = round(base_fare + platform_fee + taxes, 2)
    return {
        "base_fare": base_fare, "platform_fee": platform_fee, "taxes": taxes,
        "total_fare": total_fare, "add_on_fees": [],
    }


def apply_no_show_fee(fare: dict) -> dict:
    fare = dict(fare)
    fare["add_on_fees"] = [*fare["add_on_fees"], {"type": "no_show_fee", "amount": NO_SHOW_FEE}]
    fare["total_fare"] = round(fare["total_fare"] + NO_SHOW_FEE, 2)
    return fare


def apply_property_damage_fee(fare: dict, severity: str) -> dict:
    fare = dict(fare)
    amount = PROPERTY_DAMAGE_FEES[severity]
    fare["add_on_fees"] = [*fare["add_on_fees"], {"type": "cleaning_repair_fee", "amount": amount}]
    fare["total_fare"] = round(fare["total_fare"] + amount, 2)
    return fare
