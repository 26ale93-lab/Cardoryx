#!/usr/bin/env python3
# Cardoryx — BSA Store conservative matching audit
# Read-only diagnostic: does not modify retail_prices.json and never touches Cardmarket.

import json
import re
import runpy
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "bsa_store_matching_audit.json"

if not BUILDER.exists():
    raise SystemExit(f"Builder non trovato: {BUILDER}")
if not RETAIL.exists():
    raise SystemExit(f"Retail non trovato: {RETAIL}")

ns = runpy.run_path(str(BUILDER))

def norm(s):
    fn = ns.get("norm")
    return fn(s) if callable(fn) else re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def parse_plain_price(v):
    fn = ns.get("parse_plain_price")
    if callable(fn):
        return fn(v)
    try:
        x = float(v)
    except Exception:
        return None
    return x if 0 < x < 100000 else None

def fetch_json(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 Cardoryx-BSA-Audit"})
    with urlopen(req, timeout=30) as r:
        return json.load(r)

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards", {})
two_store_cards = set()
existing_by_identity = defaultdict(list)

for key, card in cards.items():
    stores = {o.get("store") for o in (card.get("offers") or []) if o.get("store")}
    if len(stores) == 2:
        two_store_cards.add(key)

    ident = (
        norm(card.get("set")),
        str(card.get("number") or "").strip().lower(),
        norm(card.get("name")),
        norm(card.get("variant")),
    )
    existing_by_identity[ident].append(key)

NUMBER_PATTERNS = [
    re.compile(r"\b(TG\d{1,2})\s*/\s*(TG\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b"),
]

VARIANT_PATTERNS = [
    ("Reverse", re.compile(r"\breverse\b", re.I)),
    ("Holo", re.compile(r"\bholo\b", re.I)),
    ("Full Art", re.compile(r"\bfull\s*art\b", re.I)),
    ("Alternative Art", re.compile(r"\b(?:alternative|alt)\s*art\b", re.I)),
    ("Radiant", re.compile(r"\b(?:radiant|lucente)\b", re.I)),
]

def extract_number(text):
    for rx in NUMBER_PATTERNS:
        m = rx.search(text or "")
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        if a.upper().startswith("TG"):
            return f"{a.upper()}/{b.upper()}"
        return f"{int(a):03d}/{int(b):03d}"
    return None

def explicit_variant(text):
    hits = []
    for label, rx in VARIANT_PATTERNS:
        if rx.search(text or ""):
            hits.append(label)
    hits = list(dict.fromkeys(hits))
    return hits[0] if len(hits) == 1 else None

def clean_name(title):
    if not title:
        return None
    s = re.split(r"\b(?:TG\d{1,2}|\d{1,3})\s*/\s*(?:TG\d{1,2}|\d{1,3})\b", title, maxsplit=1, flags=re.I)[0]
    s = re.sub(r"(?i)\b(reverse|holo|full\s*art|alternative\s*art|alt\s*art|radiant|lucente|ita|italiano|near\s*mint|nm|mint)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—|")
    return s or None

stats = Counter()
rejection_examples = defaultdict(list)
safe_candidates = []

page = 1
while True:
    url = f"https://bsastore.it/collections/carte-pokemon/products.json?limit=250&page={page}"
    try:
        payload = fetch_json(url)
    except Exception as e:
        stats["errors"] += 1
        rejection_examples["errors"].append({"page": page, "error": str(e)})
        break

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

        if not re.search(r"\b(?:ITA|Italiano|Italian)\b", text, re.I):
            stats["languageRejected"] += 1
            continue
        if not re.search(r"\b(?:Near\s*Mint|NM|Mint)\b", text, re.I):
            stats["conditionRejected"] += 1
            continue

        number = extract_number(text)
        if not number:
            stats["numberRejected"] += 1
            if len(rejection_examples["numberRejected"]) < 30:
                rejection_examples["numberRejected"].append({"title": title})
            continue

        variant = explicit_variant(text)
        if not variant:
            stats["variantUnconfirmed"] += 1
            continue

        name = clean_name(title)
        if not name:
            stats["nameRejected"] += 1
            continue

        candidates = []
        n_name = norm(name)
        n_var = norm(variant)
        n_text = norm(text)

        for ident, keys in existing_by_identity.items():
            set_name, num, card_name, card_var = ident
            if num != number.lower():
                continue
            if card_name != n_name:
                continue
            if card_var != n_var:
                continue
            if not set_name or set_name not in n_text:
                continue
            candidates.extend(keys)

        if len(candidates) != 1:
            stats["identityRejected"] += 1
            if len(candidates) > 1:
                stats["identityAmbiguous"] += 1
            continue

        key = candidates[0]
        card = cards[key]
        stores = {o.get("store") for o in (card.get("offers") or []) if o.get("store")}

        if "BSA Store" in stores:
            stats["duplicateStore"] += 1
            continue

        prices = []
        for v in product.get("variants") or []:
            if v.get("available") is not True:
                continue
            price = parse_plain_price(v.get("price"))
            if price is not None:
                prices.append(round(float(price), 2))

        distinct = sorted(set(prices))
        if len(distinct) != 1:
            stats["priceRejected"] += 1
            continue

        price = distinct[0]

        if norm(card.get("set")) == norm("Colpo Fusione") and price in {1181.0, 1184.0}:
            stats["knownAnomalousPriceRejected"] += 1
            continue

        candidate = {
            "cardKey": key,
            "name": card.get("name"),
            "set": card.get("set"),
            "number": card.get("number"),
            "variant": card.get("variant"),
            "price": price,
            "currentStores": sorted(stores),
            "wouldBecomeThirdStore": key in two_store_cards,
            "url": "https://bsastore.it/products/" + str(product.get("handle") or ""),
        }
        safe_candidates.append(candidate)
        stats["safeExactMatches"] += 1
        if key in two_store_cards:
            stats["potentialTwoToThreeStoreUpgrade"] += 1
        if card.get("stats", {}).get("reliable") is True:
            stats["safeAlreadyReliable"] += 1
        else:
            stats["safeCurrentlyNotReliable"] += 1

    page += 1
    if page > 60:
        stats["pageSafetyStop"] += 1
        break

report = {
    "schema": 1,
    "source": "BSA Store",
    "mode": "read-only conservative rejected-match audit",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "exactExistingIdentityOnly": True,
        "explicitVariantRequired": True,
        "setNameRequiredInSourceText": True,
        "duplicateStoreRejected": True,
        "knownFusionStrikeAnomalyRejected": True,
        "priority": "recover safe false negatives, especially cards currently at exactly two stores",
    },
    "stats": dict(stats),
    "safeCandidates": safe_candidates,
    "rejectionExamples": dict(rejection_examples),
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"Report: {REPORT}")
