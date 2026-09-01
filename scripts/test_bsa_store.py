#!/usr/bin/env python3
# Cardoryx — BSA Store matching audit
# Read-only diagnostic. Does not modify retail_prices.json or Cardmarket.

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "bsa_store_matching_audit.json"

BSA_URL = "https://www.bsastore.it/collections/pokemon-carte-singole-ita/products.json?limit=250&page={page}"
ANOMALOUS_FUSION_PRICES = {1181.0, 1184.0}

def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

def norm_number(value):
    return str(value or "").strip().upper().replace(" ", "")

def get_json(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 Cardoryx-BSA-Audit"})
    with urlopen(req, timeout=30) as response:
        return json.load(response)

def extract_number(text):
    m = re.search(r"\b(TG\d{1,2})\s*/\s*(TG\d{1,2})\b", text, re.I)
    if m:
        return f"{m.group(1).upper()}/{m.group(2).upper()}"
    m = re.search(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b", text)
    if m:
        return f"{int(m.group(1)):03d}/{int(m.group(2)):03d}"
    return None

def detect_variant(text):
    t = text.lower()

    # Explicit finish only. Ambiguous products are rejected.
    if "reverse masterball" in t or "reverse master ball" in t or "master ball" in t:
        return None

    hits = []
    if re.search(r"\breverse(?:\s+holo)?\b", t):
        hits.append("Reverse")
    if re.search(r"\bholo\b", t) and not re.search(r"\breverse(?:\s+holo)?\b", t):
        hits.append("Holo")
    if re.search(r"\bfull\s*art\b", t):
        hits.append("Full Art")
    if re.search(r"\b(?:alternative|alt)\s*art\b", t):
        hits.append("Alternative Art")
    if re.search(r"\b(?:radiant|lucente)\b", t):
        hits.append("Radiant")

    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None

def clean_name(title):
    s = re.split(
        r"\b(?:TG\d{1,2}|\d{1,3})\s*/\s*(?:TG\d{1,2}|\d{1,3})\b",
        title,
        maxsplit=1,
        flags=re.I,
    )[0]
    s = re.sub(
        r"(?i)\b(reverse(?:\s+holo)?|holo|full\s*art|alternative\s*art|alt\s*art|radiant|lucente|ita|italiano|near\s*mint|nm|mint)\b",
        " ",
        s,
    )
    return re.sub(r"\s+", " ", s).strip(" -–—|") or None

def single_available_price(product):
    prices = []
    for variant in product.get("variants", []):
        if variant.get("available") is not True:
            continue
        try:
            price = float(variant.get("price"))
        except Exception:
            continue
        if 0 < price < 100000:
            prices.append(round(price, 2))
    distinct = sorted(set(prices))
    return distinct[0] if len(distinct) == 1 else None

if not RETAIL.exists():
    raise SystemExit(f"Retail file not found: {RETAIL}")

retail = json.loads(RETAIL.read_text(encoding="utf-8"))
cards = retail.get("cards", {})

existing = defaultdict(list)
for key, card in cards.items():
    identity = (
        norm(card.get("set")),
        norm_number(card.get("number")),
        norm(card.get("name")),
        norm(card.get("variant")),
    )
    existing[identity].append((key, card))

stats = Counter()
safe_candidates = []
rejection_examples = defaultdict(list)

page = 1
while page <= 60:
    payload = get_json(BSA_URL.format(page=page))
    products = payload.get("products") or []
    if not products:
        break

    stats["catalogPagesFetched"] += 1
    stats["products"] += len(products)

    for product in products:
        title = str(product.get("title") or "")
        body = str(product.get("body_html") or "")
        tags = " ".join(str(x) for x in (product.get("tags") or []))
        text = " ".join([title, body, tags])

        # BSA production policy: ITA + Near Mint/Mint.
        if not re.search(r"\b(?:ITA|Italiano|Italian)\b", text, re.I):
            stats["languageRejected"] += 1
            continue
        if not re.search(r"\b(?:Near\s*Mint|NM|Mint)\b", text, re.I):
            stats["conditionRejected"] += 1
            continue

        number = extract_number(text)
        if not number:
            stats["numberRejected"] += 1
            continue

        variant = detect_variant(text)
        if not variant:
            stats["variantUnconfirmed"] += 1
            continue

        name = clean_name(title)
        if not name:
            stats["nameRejected"] += 1
            continue

        n_text = norm(text)
        candidates = []
        for identity, matches in existing.items():
            set_name, card_number, card_name, card_variant = identity
            if card_number != norm_number(number):
                continue
            if card_name != norm(name):
                continue
            if card_variant != norm(variant):
                continue
            if not set_name or set_name not in n_text:
                continue
            candidates.extend(matches)

        if len(candidates) != 1:
            stats["identityRejected"] += 1
            if len(candidates) > 1:
                stats["identityAmbiguous"] += 1
            continue

        key, card = candidates[0]
        stores = {
            o.get("store")
            for o in card.get("offers", [])
            if o.get("store")
        }

        if "BSA Store" in stores:
            stats["alreadyPresentInRetail"] += 1
            continue

        price = single_available_price(product)
        if price is None:
            stats["priceRejected"] += 1
            continue

        if norm(card.get("set")) == norm("Colpo Fusione") and price in ANOMALOUS_FUSION_PRICES:
            stats["knownAnomalousPriceRejected"] += 1
            continue

        handle = str(product.get("handle") or "")
        candidate = {
            "cardKey": key,
            "name": card.get("name"),
            "set": card.get("set"),
            "number": card.get("number"),
            "variant": card.get("variant"),
            "price": price,
            "currentStores": sorted(stores),
            "wouldBecomeThirdStore": len(stores) == 2,
            "url": f"https://www.bsastore.it/products/{handle}" if handle else None,
        }
        safe_candidates.append(candidate)
        stats["safeExactMissingBsaCandidates"] += 1
        if len(stores) == 2:
            stats["potentialTwoToThreeStoreUpgrade"] += 1
        elif len(stores) >= 3:
            stats["alreadyReliableWithoutBsa"] += 1
        else:
            stats["currentlyBelowTwoStores"] += 1

    if len(products) < 250:
        break
    page += 1

report = {
    "schema": 2,
    "source": "BSA Store",
    "mode": "read-only conservative rejected-match audit",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "exactExistingIdentityOnly": True,
        "explicitVariantRequired": True,
        "duplicateStoreRejected": True,
        "knownFusionStrikeAnomalyRejected": True,
    },
    "stats": dict(stats),
    "safeCandidates": safe_candidates,
    "rejectionExamples": dict(rejection_examples),
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print("=== CARDORYX — BSA MATCHING AUDIT ===")
print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"Report generated: {REPORT}")
