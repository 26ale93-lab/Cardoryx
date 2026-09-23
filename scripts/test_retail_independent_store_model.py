#!/usr/bin/env python3
"""Regression test for independent retail-store references.

Read-only: tests production calculate_stats(), the committed retail dataset and
the UI wiring. Does not fetch stores, does not write retail_prices.json and
does not touch Cardmarket data.
"""
from pathlib import Path
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
INDEX = ROOT / "index.html"
RETAIL = ROOT / "data" / "retail_prices.json"

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


check("zero", [], {
    "reliable": False, "hasReference": False, "count": 0, "stores": 0,
    "min": None, "max": None, "median": None,
})
check("one-store", [offer("Card Passion", 0.50)], {
    "reliable": True, "hasReference": True, "count": 1, "stores": 1,
    "min": 0.50, "max": 0.50, "median": 0.50,
})
check("two-stores", [offer("Card Passion", 0.50), offer("Warcard", 0.70)], {
    "reliable": True, "hasReference": True, "count": 2, "stores": 2,
    "min": 0.50, "max": 0.70, "median": 0.60,
})
check("three-stores", [
    offer("Card Passion", 0.50), offer("Warcard", 0.70), offer("GS-Gameon", 1.10)
], {
    "reliable": True, "hasReference": True, "count": 3, "stores": 3,
    "min": 0.50, "max": 1.10, "median": 0.70,
})
check("invalid-price", [offer("Card Passion", 0)], {
    "reliable": False, "hasReference": False, "count": 0, "stores": 0,
})

assert module.MIN_OFFERS_FOR_STATS == 1
assert module.MIN_STORES_FOR_STATS == 1
assert module.SCHEMA_VERSION == 2

# A single unavailable store must no longer block valid independent stores.
previous = {
    "sources": [
        {"source": "LPP Collecting", "accepted": 957},
        {"source": "Warcard", "accepted": 986},
    ]
}
current = [
    {"source": "LPP Collecting", "accepted": 0, "ok": False},
    {"source": "Warcard", "accepted": 900, "ok": True},
]
guard = module.validate_source_collapse(previous, current)
assert guard.get("blocking") is False, guard
assert guard.get("collapsedSources") == ["LPP Collecting (957 -> 0)"], guard

# Existing production index proves that 1-store and 2-store observations are
# material, so the UI must not hide them.
data = json.loads(RETAIL.read_text(encoding="utf-8"))
cards = list((data.get("cards") or {}).values())
distribution = {}
for card in cards:
    stores = {
        str(o.get("store") or "").strip().casefold()
        for o in card.get("offers", [])
        if o.get("store")
    }
    distribution[len(stores)] = distribution.get(len(stores), 0) + 1

assert distribution.get(1, 0) > 0, distribution
assert distribution.get(2, 0) > 0, distribution

html = INDEX.read_text(encoding="utf-8")
required_ui_markers = (
    "function loadRetailIndex()",
    "fetch('./data/retail_prices.json',{cache:'no-store'})",
    "function buildRetailLookup(",
    "function retailReferenceForCard(",
    "Ogni negozio è un riferimento indipendente.",
    "r.count===1",
    "async function openCardDetail(key)",
    "await loadRetailIndex();",
)
for marker in required_ui_markers:
    assert marker in html, f"UI marker missing: {marker}"

# Cardmarket stays explicitly separated in both data and code.
assert data.get("rules", {}).get("cardmarketExcluded") is True
builder_text = BUILDER.read_text(encoding="utf-8")
assert '"cardmarketExcluded":\n                True' in builder_text
assert '"sourceFailurePolicy":' in builder_text
assert "pagine raggiunte ma nessuna riga carta riconoscibile" in builder_text
assert "renderCardmarketReference(c)" in html

print("Retail store-count distribution:", distribution)
print("PASS: independent retail-store model and UI wiring")
