#!/usr/bin/env python3
"""Regression test for independent retail-store references.

Read-only: imports the production builder and tests only calculate_stats().
Does not fetch stores, does not write retail_prices.json and does not touch
Cardmarket data.
"""
from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"

spec = importlib.util.spec_from_file_location("retail_builder", BUILDER)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def offer(store, price):
    return {
        "store": store,
        "price": price,
        "url": "https://example.invalid/",
        "language": "IT",
        "condition": "NM/MINT",
        "variant": "Normal",
        "checkedAt": "2026-09-23T00:00:00Z",
        "sourceType": "retail-store",
    }


def check(label, offers, expected):
    got = module.calculate_stats(offers)
    for key, value in expected.items():
        assert got.get(key) == value, (
            f"{label}: {key} expected {value!r}, got {got.get(key)!r}; full={got!r}"
        )
    print(label, got)


check(
    "zero",
    [],
    {
        "reliable": False,
        "hasReference": False,
        "count": 0,
        "stores": 0,
        "min": None,
        "max": None,
        "median": None,
    },
)

check(
    "one-store",
    [offer("Card Passion", 0.50)],
    {
        "reliable": True,
        "hasReference": True,
        "count": 1,
        "stores": 1,
        "min": 0.50,
        "max": 0.50,
        "median": 0.50,
    },
)

check(
    "two-stores",
    [offer("Card Passion", 0.50), offer("Warcard", 0.70)],
    {
        "reliable": True,
        "hasReference": True,
        "count": 2,
        "stores": 2,
        "min": 0.50,
        "max": 0.70,
        "median": 0.60,
    },
)

check(
    "three-stores",
    [
        offer("Card Passion", 0.50),
        offer("Warcard", 0.70),
        offer("GS-Gameon", 1.10),
    ],
    {
        "reliable": True,
        "hasReference": True,
        "count": 3,
        "stores": 3,
        "min": 0.50,
        "max": 1.10,
        "median": 0.70,
    },
)

# Invalid prices must never create a reference.
check(
    "invalid-price",
    [offer("Card Passion", 0)],
    {
        "reliable": False,
        "hasReference": False,
        "count": 0,
        "stores": 0,
    },
)

assert module.MIN_OFFERS_FOR_STATS == 1
assert module.MIN_STORES_FOR_STATS == 1
assert module.SCHEMA_VERSION == 2

print("PASS: independent retail-store reference model")
