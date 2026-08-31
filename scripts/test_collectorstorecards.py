#!/usr/bin/env python3
# Cardoryx — Collector Store Cards isolated diagnostic V6
# Read-only test: does not modify retail_prices.json and never touches Cardmarket.

import json
import re
import runpy
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "collector_store_cards_v6_report.json"

if not BUILDER.exists():
    raise SystemExit(f"Builder non trovato: {BUILDER}")
if not RETAIL.exists():
    raise SystemExit(f"Retail non trovato: {RETAIL}")

ns = runpy.run_path(str(BUILDER))

def norm(s):
    fn = ns.get("norm")
    return fn(s) if callable(fn) else re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def fetch_json(url):
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 Cardoryx-Collector-V6"})
    with urlopen(req, timeout=30) as r:
        return json.load(r)

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards", {})
existing = {}
two_store = set()

for key, card in cards.items():
    base = (
        norm(card.get("set")),
        str(card.get("number") or "").strip().lower(),
        norm(card.get("name")),
        norm(card.get("variant")),
    )
    existing.setdefault(base, []).append(key)
    stats = card.get("stats") or {}
    if stats.get("stores") == 2:
        two_store.add(key)

# Conservative title signals only. No rarity -> variant broad mapping.
EXPLICIT_VARIANT_PATTERNS = [
    ("Master Ball", re.compile(r"\bmaster\s*ball\b", re.I)),
    ("Reverse Holo", re.compile(r"\breverse(?:\s*holo)?\b", re.I)),
    ("Cosmo Holo", re.compile(r"\bcosmo(?:s)?\s*holo\b", re.I)),
    ("Galaxy Holo", re.compile(r"\bgalaxy\s*holo\b", re.I)),
    ("Holo", re.compile(r"\bholo\b", re.I)),
    ("Full Art", re.compile(r"\bfull\s*art\b", re.I)),
    ("Radiant", re.compile(r"\b(?:radiant|lucente)\b", re.I)),
]

def explicit_variant(title):
    for label, rx in EXPLICIT_VARIANT_PATTERNS:
        if rx.search(title or ""):
            return label
    return None

def extract_number(text):
    m = re.search(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b", text or "")
    return f"{int(m.group(1)):03d}/{int(m.group(2)):03d}" if m else None

def title_name(title):
    # only the leading card name before collector number
    if not title:
        return None
    m = re.search(r"\b\d{1,3}\s*/\s*\d{1,3}\b", title)
    head = title[:m.start()] if m else title
    head = re.sub(r"(?i)\b(reverse(?: holo)?|cosmo(?:s)? holo|galaxy holo|holo|full art|master ball|radiant|lucente|ita|italiano|near mint|nm|mint)\b", " ", head)
    head = re.sub(r"\s+", " ", head).strip(" -–—|")
    return head or None

stats = Counter()
examples = defaultdict(list)
safe_candidates = []

page = 1
while True:
    url = f"https://collectorstorecards.it/collections/carte-singole-pokemon/products.json?limit=250&page={page}"
    try:
        payload = fetch_json(url)
    except Exception as e:
        stats["errors"] += 1
        examples["errors"].append({"page":page,"error":str(e)})
        break

    products = payload.get("products") or []
    if not products:
        break

    stats["catalogPagesFetched"] += 1
    stats["products"] += len(products)

    for p in products:
        title = p.get("title") or ""
        variants = p.get("variants") or []
        available = [v for v in variants if v.get("available") is True]
        if not available:
            stats["unavailable"] += 1
            continue

        text = " ".join([
            title,
            str(p.get("body_html") or ""),
            " ".join(str(x) for x in p.get("tags") or []),
        ])

        if not re.search(r"\b(?:ITA|Italiano|Italian)\b", text, re.I):
            stats["languageRejected"] += 1
            continue
        if not re.search(r"\b(?:Near\s*Mint|NM|Mint)\b", text, re.I):
            stats["conditionRejected"] += 1
            continue

        number = extract_number(text)
        if not number:
            stats["numberMissing"] += 1
            continue

        variant = explicit_variant(title + " " + text)
        if not variant:
            stats["rarityWithoutExplicitVariant"] += 1
            continue
        stats["explicitVariantConfirmed"] += 1

        name = title_name(title)
        if not name:
            stats["nameRejected"] += 1
            continue

        # Require a set label from text to match existing exact identity.
        matched_keys = []
        n_name = norm(name)
        n_variant = norm(variant)
        for base, keys in existing.items():
            b_set, b_num, b_name, b_var = base
            if b_num != number.lower():
                continue
            if b_name != n_name:
                continue
            if b_var != n_variant:
                continue
            # Conservative: existing set name must appear in product text.
            if b_set and b_set not in norm(text):
                continue
            matched_keys.extend(keys)

        if len(matched_keys) != 1:
            stats["identityRejected"] += 1
            if len(matched_keys) > 1:
                stats["identityAmbiguous"] += 1
            continue

        key = matched_keys[0]
        stores = {o.get("store") for o in (cards[key].get("offers") or [])}
        if "Collector Store Cards" in stores:
            stats["duplicateStore"] += 1
            continue

        price_vals = []
        for v in available:
            try:
                price = float(v.get("price"))
            except Exception:
                continue
            if 0 < price < 100000:
                price_vals.append(price)

        if len(set(price_vals)) != 1:
            stats["priceAmbiguous"] += 1
            continue

        candidate = {
            "cardKey": key,
            "set": cards[key].get("set"),
            "number": cards[key].get("number"),
            "name": cards[key].get("name"),
            "variant": cards[key].get("variant"),
            "price": price_vals[0],
            "url": "https://collectorstorecards.it/products/" + str(p.get("handle") or ""),
            "currentStores": sorted(stores),
            "wouldBecomeThirdStore": key in two_store,
        }
        safe_candidates.append(candidate)
        stats["safeExactMatches"] += 1
        if key in two_store:
            stats["potentialTwoToThreeStoreUpgrade"] += 1
        if cards[key].get("stats", {}).get("reliable") is True:
            stats["safeAlreadyReliable"] += 1
        else:
            stats["safeCurrentlyNotReliable"] += 1

    page += 1
    if page > 40:
        stats["pageSafetyStop"] += 1
        break

report = {
    "schema": 6,
    "source": "Collector Store Cards",
    "mode": "read-only conservative exact-existing-identity diagnostic",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "broadRarityToVariantMapping": False,
        "exactExistingIdentityOnly": True,
        "duplicateStoreRejected": True,
        "priority": "cards currently at exactly two stores",
    },
    "stats": dict(stats),
    "safeCandidates": safe_candidates,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
with REPORT.open("w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"Report: {REPORT}")
