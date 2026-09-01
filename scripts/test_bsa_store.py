#!/usr/bin/env python3
# CARDORYX BSA DEEP AUDIT V3
# Read-only: non modifica retail_prices.json e non usa Cardmarket.

import json
import re
import runpy
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "bsa_store_matching_audit.json"

print("=== CARDORYX - BSA DEEP MATCHING AUDIT V3 ===")

if not BUILDER.exists():
    raise SystemExit(f"Builder non trovato: {BUILDER}")
if not RETAIL.exists():
    raise SystemExit(f"Retail non trovato: {RETAIL}")

ns = runpy.run_path(str(BUILDER))

required = [
    "norm", "norm_number", "clean_set_name", "detect_variant",
    "bsa_products_url", "parse_bsa_title", "bsa_available_price", "http_get_json"
]
missing = [x for x in required if not callable(ns.get(x))]
if missing:
    raise SystemExit("Funzioni BSA mancanti nel builder: " + ", ".join(missing))

norm = ns["norm"]
norm_number = ns["norm_number"]
clean_set_name = ns["clean_set_name"]
detect_variant = ns["detect_variant"]
bsa_products_url = ns["bsa_products_url"]
parse_bsa_title = ns["parse_bsa_title"]
bsa_available_price = ns["bsa_available_price"]
http_get_json = ns["http_get_json"]

PAGE_LIMIT = int(ns.get("BSA_STORE_PAGE_LIMIT") or 250)
MAX_PAGES = int(ns.get("BSA_STORE_MAX_PAGES") or 40)
ANOMALOUS = {round(float(x), 2) for x in (ns.get("BSA_STORE_REJECTED_FUSION_STRIKE_PRICES") or {1181.0, 1184.0})}

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards") or {}

def card_stores(card):
    return {
        str(o.get("store") or "").strip()
        for o in (card.get("offers") or [])
        if str(o.get("store") or "").strip()
    }

exact = defaultdict(list)
loose = defaultdict(list)

for key, card in cards.items():
    exact[(
        norm(card.get("set")),
        norm_number(card.get("number")),
        norm(card.get("name")),
        norm(card.get("variant")),
    )].append(key)

    loose[(
        norm(card.get("set")),
        norm_number(card.get("number")),
        norm(card.get("name")),
    )].append(key)

RARITY_RE = re.compile(
    r"\b(?:Non\s+Comune|Comune|Rara\s+Doppia|Rara\s+Ultra|"
    r"Rara\s+Illustrazione\s+Speciale|Rara\s+Illustrazione|"
    r"Rara\s+Segreta|Rara\s+Iper|Rara\s+Allenatore|"
    r"Rara\s+ACE\s+SPEC|Rara)\b",
    re.I,
)

RELAXED_RE = re.compile(
    r"^\s*(?:POKEMON\s+)?"
    r"(?P<name>.+?)\s+"
    r"(?P<number>[A-Z0-9]{0,6}\d{1,4}/[A-Z0-9]{0,6}\d{1,4})"
    r"(?P<finish>.*?)"
    r"\s*-\s*(?P<language>ITA|ITALIANO)\s*"
    r"-\s*(?P<condition>Near\s+Mint|Mint|NM)\s*"
    r"-\s*(?P<set>.+?)"
    r"\s*-\s*Carta\s+Pokemon\s*$",
    re.I,
)

def relaxed_parse(title):
    m = RELAXED_RE.match(str(title or "").strip())
    if not m:
        return None

    finish_raw = re.sub(r"\s+", " ", m.group("finish") or "").strip(" -")
    finish_clean = re.sub(r"\s+", " ", RARITY_RE.sub(" ", finish_raw)).strip(" -")

    if not finish_clean:
        variant = "Normal"
        evidence = "empty_after_rarity_removal"
    else:
        variant = detect_variant(finish_clean)
        if variant == "Normal" and norm(finish_clean) not in {"normal", "non holo", "nonholo"}:
            variant = None
            evidence = "unknown_finish"
        else:
            evidence = "explicit_finish"

    return {
        "name": re.sub(r"\s+", " ", m.group("name")).strip(),
        "number": norm_number(m.group("number")),
        "set": clean_set_name(re.sub(r"\s+", " ", m.group("set")).strip()),
        "condition": re.sub(r"\s+", " ", m.group("condition")).strip(),
        "language": re.sub(r"\s+", " ", m.group("language")).strip(),
        "finishRaw": finish_raw,
        "finishClean": finish_clean,
        "variant": variant,
        "variantEvidence": evidence,
    }

stats = Counter()
safe = []
diagnostic = []
unknown_finishes = Counter()
unknown_examples = []
format_examples = []

for page in range(1, MAX_PAGES + 1):
    payload = http_get_json(bsa_products_url(page))
    products = payload.get("products") or []
    if not products:
        break

    stats["catalogPagesFetched"] += 1
    stats["products"] += len(products)

    for product in products:
        title = str(product.get("title") or "").strip()
        price = bsa_available_price(product)
        prod = parse_bsa_title(title)

        if prod:
            stats["productionTitleAccepted"] += 1
            ident = (
                norm(prod.get("set")),
                norm_number(prod.get("number")),
                norm(prod.get("name")),
                norm(prod.get("variant")),
            )
            matches = exact.get(ident, [])

            if len(matches) == 1:
                stats["productionExactExistingIdentity"] += 1
                key = matches[0]
                stores = card_stores(cards[key])

                if "BSA Store" in stores:
                    stats["alreadyPresentInRetail"] += 1
                elif price is None:
                    stats["productionExactPriceUnavailable"] += 1
                elif (
                    norm(prod.get("set")) == norm("Colpo Fusione")
                    and round(float(price), 2) in ANOMALOUS
                ):
                    stats["knownFusionStrikeAnomalyRejected"] += 1
                else:
                    stats["productionExactMissingBsa"] += 1
                    if len(stores) == 2:
                        stats["potentialTwoToThreeStoreUpgrade"] += 1
                    safe.append({
                        "reason": "production_exact_identity_missing_BSA",
                        "cardKey": key,
                        "name": cards[key].get("name"),
                        "set": cards[key].get("set"),
                        "number": cards[key].get("number"),
                        "variant": cards[key].get("variant"),
                        "price": round(float(price), 2),
                        "currentStores": sorted(stores),
                        "wouldBecomeThirdStore": len(stores) == 2,
                        "title": title,
                    })
            elif len(matches) > 1:
                stats["productionIdentityAmbiguous"] += 1
            else:
                stats["productionIdentityNotExisting"] += 1
            continue

        stats["productionTitleRejected"] += 1
        rp = relaxed_parse(title)

        if not rp:
            stats["relaxedFormatRejected"] += 1
            if len(format_examples) < 80:
                format_examples.append(title)
            continue

        stats["relaxedFormatAccepted"] += 1

        if rp["variant"] is None:
            stats["unknownExplicitFinish"] += 1
            unknown_finishes[rp["finishClean"] or "<EMPTY>"] += 1
            if len(unknown_examples) < 100:
                unknown_examples.append({
                    "title": title,
                    "finishRaw": rp["finishRaw"],
                    "finishClean": rp["finishClean"],
                })
            continue

        ident = (
            norm(rp["set"]),
            norm_number(rp["number"]),
            norm(rp["name"]),
            norm(rp["variant"]),
        )
        matches = exact.get(ident, [])

        if len(matches) == 1:
            stats["deepExactExistingIdentity"] += 1
            key = matches[0]
            stores = card_stores(cards[key])

            if "BSA Store" in stores:
                stats["deepAlreadyPresentInRetail"] += 1
                continue
            if price is None:
                stats["deepPriceUnavailable"] += 1
                continue
            if (
                norm(rp["set"]) == norm("Colpo Fusione")
                and round(float(price), 2) in ANOMALOUS
            ):
                stats["knownFusionStrikeAnomalyRejected"] += 1
                continue

            stats["safeDeepRecoveryCandidates"] += 1
            if len(stores) == 2:
                stats["deepPotentialTwoToThreeStoreUpgrade"] += 1

            safe.append({
                "reason": "production_reject_but_exact_existing_identity",
                "cardKey": key,
                "name": cards[key].get("name"),
                "set": cards[key].get("set"),
                "number": cards[key].get("number"),
                "variant": cards[key].get("variant"),
                "price": round(float(price), 2),
                "conditionSource": rp["condition"],
                "finishSource": rp["finishRaw"],
                "currentStores": sorted(stores),
                "wouldBecomeThirdStore": len(stores) == 2,
                "title": title,
            })

        elif len(matches) > 1:
            stats["deepIdentityAmbiguous"] += 1
        else:
            stats["deepExactIdentityRejected"] += 1
            lm = loose.get((
                norm(rp["set"]),
                norm_number(rp["number"]),
                norm(rp["name"]),
            ), [])
            if len(lm) == 1:
                stats["singleDifferentVariantDiagnostic"] += 1
                if len(diagnostic) < 100:
                    key = lm[0]
                    diagnostic.append({
                        "accepted": False,
                        "reason": "same_set_number_name_but_different_variant",
                        "source": rp,
                        "title": title,
                        "cardoryx": {
                            "cardKey": key,
                            "variant": cards[key].get("variant"),
                            "stores": sorted(card_stores(cards[key])),
                        },
                    })
            elif len(lm) > 1:
                stats["multipleVariantDiagnostic"] += 1

    if len(products) < PAGE_LIMIT:
        break

report = {
    "schema": 2,
    "source": "BSA Store",
    "mode": "read-only deep conservative availability audit V3",
    "rules": {
        "retailPricesModified": False,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "productionParserReused": True,
        "exactExistingIdentityOnly": True,
        "explicitVariantRequired": True,
        "duplicateStoreRejected": True,
        "rarityNeverUsedAsVariant": True,
        "ambiguousVariantAccepted": False,
        "knownFusionStrikeAnomalyRejected": True,
        "mintAndNmExplicitLabelsInspected": True,
    },
    "stats": dict(stats),
    "topUnknownFinishes": unknown_finishes.most_common(80),
    "safeCandidates": safe,
    "diagnosticOnlyCandidates": diagnostic,
    "unknownFinishExamples": unknown_examples,
    "titleFormatRejectExamples": format_examples,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"SAFE CANDIDATES: {len(safe)}")
print(f"REPORT GENERATED: {REPORT}")
