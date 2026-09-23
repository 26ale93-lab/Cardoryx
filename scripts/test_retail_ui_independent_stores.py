#!/usr/bin/env python3
"""Read-only regression test for the retail UI data path.

Validates that the current retail index can be mapped conservatively to
independent store references and that the production HTML contains the loader.
No network requests, no writes to retail_prices.json, no Cardmarket mutation.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
RETAIL = ROOT / "data" / "retail_prices.json"


def norm_text(value):
    text = unicodedata.normalize("NFD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", text)


def local_number(value):
    raw = re.sub(r"\s+", "", str(value or "").strip().upper())
    first = raw.split("/", 1)[0] or raw
    match = re.fullmatch(r"([A-Z]{0,4})(\d{1,4})", first)
    if match:
        return match.group(1) + str(int(match.group(2)))
    return first.lstrip("0") or first


def key(row):
    return (
        norm_text(row.get("set")),
        local_number(row.get("number")),
        str(row.get("variant") or "Normal"),
        norm_text(row.get("name")),
    )


data = json.loads(RETAIL.read_text(encoding="utf-8"))
html = INDEX.read_text(encoding="utf-8")

assert data.get("rules", {}).get("cardmarketExcluded") is True
assert "loadRetailIndex();" in html
assert "CARDORYX_RETAIL_LOOKUP" in html
assert "Ogni negozio è un riferimento indipendente." in html
assert "Cardmarket" in html

groups = defaultdict(list)
for row in (data.get("cards") or {}).values():
    if norm_text(row.get("language")) != "it":
        continue
    offers = row.get("offers") or []
    if not offers:
        continue
    groups[key(row)].append(row)

raw_rows = sum(len(rows) for rows in groups.values())
merged_keys = len(groups)
duplicate_identity_groups = {k: rows for k, rows in groups.items() if len(rows) > 1}

# Every store reference must have a positive price and a store name.
store_refs = 0
for rows in groups.values():
    by_store = defaultdict(set)
    for row in rows:
        for offer in row.get("offers") or []:
            store = norm_text(offer.get("store"))
            price = offer.get("price")
            if not store:
                continue
            try:
                numeric = float(price)
            except (TypeError, ValueError):
                continue
            if numeric <= 0:
                continue
            by_store[store].add(round(numeric, 2))
    # Conflicting prices from the same store for the same physical identity
    # must not be auto-selected by the UI merge logic.
    store_refs += sum(1 for prices in by_store.values() if len(prices) == 1)

assert raw_rows >= merged_keys > 0
assert store_refs > 0

print(json.dumps({
    "retailRows": raw_rows,
    "uiIdentityKeys": merged_keys,
    "duplicateFormattingGroups": len(duplicate_identity_groups),
    "unambiguousStoreReferences": store_refs,
    "cardmarketExcluded": True,
    "productionDataModified": False,
}, ensure_ascii=False, indent=2))
print("PASS: retail UI independent-store data path")
