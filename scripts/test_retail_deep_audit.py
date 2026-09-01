#!/usr/bin/env python3
# CARDORYX — DEEP RETAIL AUDIT
# Read-only diagnostic framework.
# V1: Card Passion deep audit. Other working stores will be added here
# without changing filename or workflow.
#
# SAFETY:
# - does not modify data/retail_prices.json
# - never reads/writes Cardmarket files
# - never creates production identities
# - never injects offers into production data
# - candidates are diagnostic only

import json
import re
import runpy
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "retail_deep_audit_report.json"

if not BUILDER.exists():
    raise SystemExit(f"Builder non trovato: {BUILDER}")
if not RETAIL.exists():
    raise SystemExit(f"Retail non trovato: {RETAIL}")

ns = runpy.run_path(str(BUILDER))

REQUIRED_BUILDER_FUNCTIONS = [
    "norm",
    "norm_number",
    "strip_html",
    "parse_cardpassion_title",
    "cardpassion_excluded",
    "cardpassion_language",
    "cardpassion_condition",
    "cardpassion_price",
    "get_cardpassion_products",
]
missing = [name for name in REQUIRED_BUILDER_FUNCTIONS if not callable(ns.get(name))]
if missing:
    raise SystemExit(
        "Builder incompatibile con Deep Retail Audit. Mancano: "
        + ", ".join(missing)
    )

norm = ns["norm"]
norm_number = ns["norm_number"]
strip_html = ns["strip_html"]

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

if retail.get("rules", {}).get("cardmarketExcluded") is not True:
    raise SystemExit("Safety check fallito: retail.rules.cardmarketExcluded != true")

cards = retail.get("cards")
if not isinstance(cards, dict) or not cards:
    raise SystemExit("Indice retail mancante o vuoto")

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def store_names(card):
    return {
        str(o.get("store") or "").strip()
        for o in (card.get("offers") or [])
        if str(o.get("store") or "").strip()
    }

def compact_card(key, card):
    return {
        "cardKey": key,
        "set": card.get("set"),
        "number": card.get("number"),
        "name": card.get("name"),
        "variant": card.get("variant"),
        "stores": sorted(store_names(card)),
        "storeCount": len(store_names(card)),
    }

# Exact existing identity indexes. These indexes are used only to classify
# diagnostic candidates; they do not create or modify cards.
exact_identity = defaultdict(list)
set_number = defaultdict(list)
name_number = defaultdict(list)

for key, card in cards.items():
    exact_identity[
        (
            norm(card.get("set")),
            norm_number(card.get("number")),
            norm(card.get("name")),
            norm(card.get("variant")),
        )
    ].append((key, card))

    set_number[
        (
            norm(card.get("set")),
            norm_number(card.get("number")),
        )
    ].append((key, card))

    name_number[
        (
            norm(card.get("name")),
            norm_number(card.get("number")),
        )
    ].append((key, card))


def audit_card_passion():
    products = ns["get_cardpassion_products"]()
    stats = Counter()
    stats["products"] = len(products)

    rejection_examples = defaultdict(list)
    safe_missing_store_candidates = []
    priority_two_to_three = []
    exact_identity_but_failed_metadata = []
    title_format_review = []

    for product in products:
        if not isinstance(product, dict):
            stats["invalidProductObject"] += 1
            continue

        title = str(product.get("title") or "").strip()
        handle = str(product.get("handle") or "").strip()
        body = strip_html(product.get("body_html"))

        tags = product.get("tags")
        tags_text = " ".join(str(x) for x in tags) if isinstance(tags, list) else str(tags or "")

        url = (
            f"{ns.get('CARDPASSION_BASE_URL', 'https://cardpassion.it')}"
            f"/products/{handle}"
            if handle else None
        )

        # Mirror production rejection order exactly.
        if ns["cardpassion_excluded"](title, body, tags_text):
            reason = "excludedProduct"
            stats[reason] += 1
            if len(rejection_examples[reason]) < 20:
                rejection_examples[reason].append({"title": title, "url": url})
            continue

        parsed = ns["parse_cardpassion_title"](title)

        if not parsed:
            reason = "invalidTitle"
            stats[reason] += 1

            # Read-only relaxed diagnostics:
            # only detect whether title contains a collector number and whether
            # name+number has exactly one existing identity. No automatic match.
            number_match = re.search(
                r"\b([A-Za-z]{0,5}\d{1,4})\s*[/\-]\s*([A-Za-z]{0,5}\d{1,4})\b",
                title,
                flags=re.I,
            )
            if number_match:
                raw_number = f"{number_match.group(1)}/{number_match.group(2)}"
                number = norm_number(raw_number)
                candidates = [
                    (k, c)
                    for (n_name, n_num), values in name_number.items()
                    if n_num == number
                    for (k, c) in values
                    if norm(c.get("name")) in norm(title)
                ]
                # Deduplicate by key.
                dedup = {k: c for k, c in candidates}
                if len(dedup) == 1:
                    k, c = next(iter(dedup.items()))
                    stats["invalidTitleSingleExistingIdentity"] += 1
                    if len(title_format_review) < 100:
                        title_format_review.append({
                            "title": title,
                            "url": url,
                            "existingIdentity": compact_card(k, c),
                            "status": "manual-review-only",
                            "reason": "production title parser rejected; identity signal is not enough for integration",
                        })

            if len(rejection_examples[reason]) < 20:
                rejection_examples[reason].append({"title": title, "url": url})
            continue

        identity_key = (
            norm(parsed.get("set")),
            norm_number(parsed.get("number")),
            norm(parsed.get("name")),
            norm(parsed.get("variant")),
        )
        exact = exact_identity.get(identity_key, [])

        language = ns["cardpassion_language"](
            title, body, tags_text, parsed["set"]
        )
        if language != "IT":
            reason = "languageUnknown"
            stats[reason] += 1
            if len(exact) == 1 and len(exact_identity_but_failed_metadata) < 100:
                k, c = exact[0]
                exact_identity_but_failed_metadata.append({
                    "reason": reason,
                    "title": title,
                    "url": url,
                    "existingIdentity": compact_card(k, c),
                })
            if len(rejection_examples[reason]) < 20:
                rejection_examples[reason].append({"title": title, "url": url})
            continue

        condition = ns["cardpassion_condition"](title, body, tags_text)
        if condition != "NM/MINT":
            reason = "conditionUnknown"
            stats[reason] += 1
            if len(exact) == 1 and len(exact_identity_but_failed_metadata) < 100:
                k, c = exact[0]
                exact_identity_but_failed_metadata.append({
                    "reason": reason,
                    "title": title,
                    "url": url,
                    "existingIdentity": compact_card(k, c),
                })
            if len(rejection_examples[reason]) < 20:
                rejection_examples[reason].append({"title": title, "url": url})
            continue

        price = ns["cardpassion_price"](product)
        if price is None:
            reason = "priceUnavailable"
            stats[reason] += 1
            if len(exact) == 1 and len(exact_identity_but_failed_metadata) < 100:
                k, c = exact[0]
                exact_identity_but_failed_metadata.append({
                    "reason": reason,
                    "title": title,
                    "url": url,
                    "existingIdentity": compact_card(k, c),
                })
            if len(rejection_examples[reason]) < 20:
                rejection_examples[reason].append({"title": title, "url": url})
            continue

        stats["productionEligible"] += 1

        if len(exact) != 1:
            stats["productionEligibleNoUniqueExistingIdentity"] += 1
            continue

        key, card = exact[0]
        stores = store_names(card)

        if "Card Passion" in stores:
            stats["alreadyPresentInRetail"] += 1
            continue

        # This is the strongest diagnostic class:
        # production metadata passes and an exact identity already exists,
        # but current retail does not contain Card Passion for it.
        stats["safeMissingStoreCandidates"] += 1
        candidate = {
            "title": title,
            "url": url,
            "price": price,
            "existingIdentity": compact_card(key, card),
            "impact": (
                "2->3" if len(stores) == 2
                else "1->2" if len(stores) == 1
                else f"{len(stores)}->{len(stores)+1}"
            ),
            "status": "safe-diagnostic-candidate",
        }

        if len(safe_missing_store_candidates) < 200:
            safe_missing_store_candidates.append(candidate)

        if len(stores) == 2:
            stats["potentialTwoToThree"] += 1
            if len(priority_two_to_three) < 100:
                priority_two_to_three.append(candidate)
        elif len(stores) == 1:
            stats["potentialOneToTwo"] += 1

    return {
        "source": "Card Passion",
        "ok": True,
        "mode": "deep-read-only",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_two_to_three,
        "safeMissingStoreCandidates": safe_missing_store_candidates,
        "exactIdentityButFailedMetadata": exact_identity_but_failed_metadata,
        "titleFormatManualReview": title_format_review,
    }


ACTIVE_STORES = [
    "Card Passion",
    "BSA Store",
    "GS-Gameon",
    "Warcard",
    "DanyStore",
    "CardPioneer",
    "TimeTwister Games",
]

EXCLUDED_STORES = [
    "MyComics",
    "Federicstore",
    "Card Game Corner",
    "CarteMagic",
    "Centro del Fumetto",
    "LPPCollecting",
    "L'Antro dei Fumetti",
]

# V1 audits Card Passion deeply. The framework and workflow filename remain
# unchanged when the next active-store adapters are added.
source_reports = [audit_card_passion()]

report = {
    "schema": 1,
    "generatedAt": utc_now(),
    "name": "Cardoryx Deep Retail Audit",
    "mode": "read-only unified framework",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "productionDataModified": False,
        "exactExistingIdentityPreferred": True,
        "priorityTwoToThree": True,
        "failClosed": True,
        "disabledStoresNotAudited": True,
    },
    "activeStores": ACTIVE_STORES,
    "excludedStores": EXCLUDED_STORES,
    "implementedAdapters": ["Card Passion"],
    "pendingAdapters": [
        "GS-Gameon",
        "Warcard",
        "DanyStore",
        "CardPioneer",
        "TimeTwister Games",
    ],
    "referenceOnly": ["BSA Store"],
    "retailSnapshot": {
        "generatedAt": retail.get("generatedAt"),
        "cards": retail.get("stats", {}).get("cards"),
        "offers": retail.get("stats", {}).get("offers"),
        "multiStoreCards": retail.get("stats", {}).get("multiStoreCards"),
        "reliableCards": retail.get("stats", {}).get("reliableCards"),
        "threeStoreCards": retail.get("stats", {}).get("threeStoreCards"),
    },
    "sources": source_reports,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("=== CARDORYX DEEP RETAIL AUDIT ===")
print(json.dumps({
    "implementedAdapters": report["implementedAdapters"],
    "pendingAdapters": report["pendingAdapters"],
    "cardPassionStats": source_reports[0]["stats"],
}, ensure_ascii=False, indent=2))
print(f"Report: {REPORT}")
