#!/usr/bin/env python3
# CARDORYX — BSA TRAINER GALLERY AUDIT V5
# Read-only. Verifica solo le identità Trainer Gallery/Galleria di Galar
# già presenti in retail_prices.json e confronta le offerte esistenti.
# Non modifica retail_prices.json. Non legge/tocca Cardmarket.

import json
import re
import runpy
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "bsa_store_matching_audit.json"

print("=== CARDORYX - BSA TRAINER GALLERY AUDIT V5 ===")

ns = runpy.run_path(str(BUILDER))

required = [
    "norm", "norm_number", "clean_set_name",
    "bsa_products_url", "bsa_available_price", "http_get_json"
]
missing = [x for x in required if not callable(ns.get(x))]
if missing:
    raise SystemExit("Funzioni BSA mancanti: " + ", ".join(missing))

norm = ns["norm"]
norm_number = ns["norm_number"]
clean_set_name = ns["clean_set_name"]
bsa_products_url = ns["bsa_products_url"]
bsa_available_price = ns["bsa_available_price"]
http_get_json = ns["http_get_json"]

PAGE_LIMIT = int(ns.get("BSA_STORE_PAGE_LIMIT") or 250)
MAX_PAGES = int(ns.get("BSA_STORE_MAX_PAGES") or 40)

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards") or {}

def stores_for(card):
    return sorted({
        str(o.get("store") or "").strip()
        for o in (card.get("offers") or [])
        if str(o.get("store") or "").strip()
    })

def compact_offer(o):
    return {
        "store": o.get("store"),
        "price": o.get("price"),
        "url": o.get("url"),
        "title": o.get("title"),
        "variant": o.get("variant"),
        "condition": o.get("condition"),
        "language": o.get("language"),
    }

# Existing identity: set + number + name. Variant is intentionally inspected,
# never overridden.
by_identity = defaultdict(list)
for key, card in cards.items():
    by_identity[(
        norm(card.get("set")),
        norm_number(card.get("number")),
        norm(card.get("name")),
    )].append(key)

TG_RE = re.compile(
    r"^\s*(?P<name>.+?)\s+"
    r"(?P<number>(?:TG\d{1,3}/TG\d{1,3}|GG\d{1,3}/GG\d{1,3}))\s+"
    r"(?P<label>"
        r"Trainer\s+Gallery(?:\s+Oro\s+Nera)?|"
        r"Galleria\s+di\s+Galar(?:\s+Oro)?"
    r")\s*"
    r"-\s*(?P<language>ITA|ITALIANO)\s*"
    r"-\s*(?P<condition>Near\s+Mint|Mint|NM)\s*"
    r"-\s*(?:Spada\s+e\s+Scudo\s*-\s*)?"
    r"(?P<set>.+?)"
    r"\s*-\s*Carta\s+Pokemon\s*$",
    re.I,
)

stats = Counter()
rows = []

for page in range(1, MAX_PAGES + 1):
    payload = http_get_json(bsa_products_url(page))
    products = payload.get("products") or []
    if not products:
        break

    stats["catalogPagesFetched"] += 1
    stats["products"] += len(products)

    for product in products:
        title = str(product.get("title") or "").strip()
        m = TG_RE.match(title)
        if not m:
            continue

        stats["galleryProducts"] += 1

        name = re.sub(r"\s+", " ", m.group("name")).strip()
        number = norm_number(m.group("number"))
        label = re.sub(r"\s+", " ", m.group("label")).strip()
        set_name = clean_set_name(re.sub(r"\s+", " ", m.group("set")).strip())
        condition = re.sub(r"\s+", " ", m.group("condition")).strip()
        price = bsa_available_price(product)

        matches = by_identity.get((norm(set_name), number, norm(name)), [])

        if len(matches) != 1:
            if len(matches) == 0:
                stats["noUniqueExistingIdentity"] += 1
            else:
                stats["ambiguousExistingIdentity"] += 1
            continue

        key = matches[0]
        card = cards[key]
        stores = stores_for(card)
        offers = [compact_offer(o) for o in (card.get("offers") or [])]

        row = {
            "cardKey": key,
            "name": card.get("name"),
            "set": card.get("set"),
            "number": card.get("number"),
            "cardoryxVariant": card.get("variant"),
            "bsaLabel": label,
            "bsaCondition": condition,
            "bsaPrice": price,
            "currentStores": stores,
            "currentStoreCount": len(stores),
            "wouldBecomeThirdStore": (
                len(stores) == 2 and "BSA Store" not in stores and price is not None
            ),
            "existingOffers": offers,
            "bsaTitle": title,
            "bsaHandle": product.get("handle"),
            "accepted": False,
            "decision": "manual_taxonomy_verification_required",
        }

        stats["uniqueExistingIdentity"] += 1

        if "BSA Store" in stores:
            stats["alreadyHasBsa"] += 1
            row["decision"] = "already_has_bsa"
        elif price is None:
            stats["priceUnavailable"] += 1
            row["decision"] = "bsa_price_unavailable"
        elif len(stores) == 2:
            stats["potentialTwoToThree"] += 1
        elif len(stores) == 1:
            stats["potentialOneToTwo"] += 1
        elif len(stores) >= 3:
            stats["alreadyReliableWithoutBsa"] += 1

        # Strong diagnostic only:
        # Check whether all existing offers point to the same Cardoryx identity
        # and whether any offer metadata contradicts it.
        contradictory = []
        for offer in offers:
            ov = offer.get("variant")
            if ov and norm(ov) != norm(card.get("variant")):
                contradictory.append({
                    "store": offer.get("store"),
                    "field": "variant",
                    "offerValue": ov,
                    "cardoryxValue": card.get("variant"),
                })

        row["offerMetadataContradictions"] = contradictory
        if contradictory:
            stats["offerMetadataContradiction"] += 1
            row["decision"] = "reject_metadata_contradiction"
        else:
            stats["noOfferMetadataContradiction"] += 1

        rows.append(row)

# Focus list: candidates that could immediately become 3-store references.
upgrade = [
    x for x in rows
    if x["wouldBecomeThirdStore"] and not x["offerMetadataContradictions"]
]

report = {
    "schema": 2,
    "source": "BSA Store",
    "mode": "read-only Trainer Gallery / Galar Gallery identity audit V5",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "exactExistingIdentityOnly": True,
        "explicitVariantRequired": True,
        "duplicateStoreRejected": True,
        "galleryLabelAutoMappedToVariant": False,
        "normalVariantAutoAssumed": False,
        "manualTaxonomyVerificationRequired": True,
        "priority": "cards that could move from exactly two stores to three",
    },
    "stats": dict(stats),
    "potentialTwoToThree": upgrade,
    "allUniqueGalleryMatches": rows,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"POTENTIAL 2->3: {len(upgrade)}")
for x in upgrade:
    print(
        f"- {x['name']} {x['number']} | {x['set']} | "
        f"Cardoryx={x['cardoryxVariant']} | BSA={x['bsaLabel']} | "
        f"stores={','.join(x['currentStores'])}"
    )
print(f"REPORT GENERATED: {REPORT}")
