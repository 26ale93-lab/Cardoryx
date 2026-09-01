#!/usr/bin/env python3
# CARDORYX — BSA DEEP AUDIT V4
# Read-only diagnostic.
# Focus:
#   1) special BSA labels rejected by the production variant parser
#   2) promo-style card numbers (SVP/SWSH/MEP/SVE/etc.)
# Never modifies retail_prices.json and never touches Cardmarket.

import json
import re
import runpy
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "bsa_store_matching_audit.json"

print("=== CARDORYX - BSA DEEP MATCHING AUDIT V4 ===")

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
ANOMALOUS = {
    round(float(x), 2)
    for x in (ns.get("BSA_STORE_REJECTED_FUSION_STRIKE_PRICES") or {1181.0, 1184.0})
}

with RETAIL.open("r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards") or {}
if not isinstance(cards, dict):
    raise SystemExit("Formato retail non valido")

def stores_for(card):
    return {
        str(o.get("store") or "").strip()
        for o in (card.get("offers") or [])
        if str(o.get("store") or "").strip()
    }

# ------------------------------------------------------------------
# Existing Cardoryx indexes
# ------------------------------------------------------------------

exact = defaultdict(list)
same_card_any_variant = defaultdict(list)
by_set_number = defaultdict(list)
by_number_only = defaultdict(list)

for key, card in cards.items():
    set_n = norm(card.get("set"))
    num_n = norm_number(card.get("number"))
    name_n = norm(card.get("name"))
    var_n = norm(card.get("variant"))

    exact[(set_n, num_n, name_n, var_n)].append(key)
    same_card_any_variant[(set_n, num_n, name_n)].append(key)
    by_set_number[(set_n, num_n)].append(key)
    by_number_only[num_n].append(key)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

SEALED_WORDS = (
    "box display", "collezione con", "collezione pokemon", "collezione premium",
    "mazzo lotte", "mazzo ", "display ", "bustine", "bundle", "tin ",
    "etb", "elite trainer", "raccoglitore", "poster "
)

SPECIAL_LABELS = [
    "Trainer Gallery",
    "Galleria di Galar",
    "Illustrazione Speciale Alternativa Art",
    "Illustrazione",
    "Ultra",
    "Segreta Oro",
    "Oro",
    "Segreta",
    "Asso Tattico",
]

RARITY_RE = re.compile(
    r"\b(?:Non\s+Comune|Comune|Rara\s+Doppia|Rara\s+Ultra|"
    r"Rara\s+Illustrazione\s+Speciale|Rara\s+Illustrazione|"
    r"Rara\s+Segreta|Rara\s+Iper|Rara\s+Allenatore|"
    r"Rara\s+ACE\s+SPEC|Rara)\b",
    re.I,
)

STANDARD_RE = re.compile(
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

# Promo patterns:
#   "Eevee SVP 173 Illustrazione Rara - ITA - Near Mint - Promo Scarlatto e Violetto - Carta Pokemon"
#   "Lucario V Astro SWSH291 - ITA - Near Mint - Promo Spada e Scudo - Carta Pokemon"
PROMO_RE = re.compile(
    r"^\s*(?P<name>.+?)\s+"
    r"(?P<number>(?:SVP|SWSH|MEP|SVE)\s*\d{1,4})"
    r"(?P<finish>.*?)"
    r"\s*-\s*(?P<language>ITA|ITALIANO)\s*"
    r"-\s*(?P<condition>Near\s+Mint|Mint|NM|Mint\s+Sigillata)\s*"
    r"-\s*(?P<set>Promo(?:\s+Scarlatto\s+e\s+Violetto|\s+Spada\s+e\s+Scudo|\s+Megaevoluzione)?)"
    r"\s*-\s*Carta\s+Pokemon\s*$",
    re.I,
)

def clean_spaces(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def normalize_promo_number(value):
    s = clean_spaces(value).upper().replace(" ", "")
    m = re.match(r"^(SVP|SWSH|MEP|SVE)(\d{1,4})$", s)
    if not m:
        return norm_number(value)
    return f"{m.group(1)}{int(m.group(2))}"

def strip_rarity(finish):
    return clean_spaces(RARITY_RE.sub(" ", finish or "")).strip(" -")

def is_sealed(title):
    t = norm(title)
    return any(norm(word) in t for word in SEALED_WORDS)

def source_variant_from_finish(finish):
    """
    Conservative diagnostic mapping.
    Only map when the source label itself is an explicit known physical finish/variant.
    Special rarity/subset labels are NOT auto-mapped.
    """
    f = clean_spaces(finish)
    fn = norm(f)

    # Explicit finishes Cardoryx production already understands.
    v = detect_variant(f)
    if v != "Normal":
        return v, "production_detect_variant"

    # Only explicit normal synonyms can become Normal.
    if fn in {"normal", "non holo", "nonholo"}:
        return "Normal", "explicit_normal"

    # Everything else stays unresolved.
    return None, "special_label_not_mapped"

def exact_candidate(key, title, price, reason, extra=None):
    card = cards[key]
    stores = stores_for(card)

    if "BSA Store" in stores:
        return None, "already_present"

    if price is None:
        return None, "price_unavailable"

    if (
        norm(card.get("set")) == norm("Colpo Fusione")
        and round(float(price), 2) in ANOMALOUS
    ):
        return None, "known_anomaly"

    item = {
        "reason": reason,
        "cardKey": key,
        "name": card.get("name"),
        "set": card.get("set"),
        "number": card.get("number"),
        "variant": card.get("variant"),
        "price": round(float(price), 2),
        "currentStores": sorted(stores),
        "wouldBecomeThirdStore": len(stores) == 2,
        "title": title,
    }
    if extra:
        item.update(extra)
    return item, None

stats = Counter()
safe = []
special_label_diagnostics = []
promo_diagnostics = []
special_label_counts = Counter()
promo_number_prefixes = Counter()

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

        # Production-supported cards are not the target of V4.
        if parse_bsa_title(title):
            stats["productionTitleAccepted"] += 1
            continue

        stats["productionTitleRejected"] += 1

        # ----------------------------------------------------------
        # A) Standard number but special finish/subset label
        # ----------------------------------------------------------
        sm = STANDARD_RE.match(title)
        if sm:
            stats["specialFormatAccepted"] += 1

            name = clean_spaces(sm.group("name"))
            number = norm_number(sm.group("number"))
            set_name = clean_set_name(clean_spaces(sm.group("set")))
            finish_raw = clean_spaces(sm.group("finish")).strip(" -")
            finish_clean = strip_rarity(finish_raw)

            special_label_counts[finish_clean or "<EMPTY>"] += 1

            # First: can this source finish be mapped EXACTLY without inference?
            variant, evidence = source_variant_from_finish(finish_clean)

            if variant is not None:
                matches = exact.get(
                    (norm(set_name), number, norm(name), norm(variant)),
                    []
                )

                if len(matches) == 1:
                    item, reject = exact_candidate(
                        matches[0], title, price,
                        "V4_explicit_finish_exact_existing_identity",
                        {
                            "finishSource": finish_raw,
                            "finishNormalized": finish_clean,
                            "variantEvidence": evidence,
                        },
                    )
                    if item:
                        safe.append(item)
                        stats["safeSpecialFinishCandidates"] += 1
                        if item["wouldBecomeThirdStore"]:
                            stats["specialFinishPotentialTwoToThree"] += 1
                    else:
                        stats[f"specialExactRejected_{reject}"] += 1
                elif len(matches) > 1:
                    stats["specialExactAmbiguous"] += 1
                else:
                    stats["specialExplicitVariantNoExactIdentity"] += 1
            else:
                stats["specialLabelUnmapped"] += 1

                # Diagnostic only: same set+number+name already in Cardoryx?
                same = same_card_any_variant.get(
                    (norm(set_name), number, norm(name)),
                    []
                )

                if len(same) == 1:
                    key = same[0]
                    card = cards[key]
                    stats["specialLabelSingleExistingCardDiagnostic"] += 1
                    if len(special_label_diagnostics) < 200:
                        special_label_diagnostics.append({
                            "accepted": False,
                            "reason": "special_label_requires_taxonomy_decision",
                            "title": title,
                            "source": {
                                "name": name,
                                "set": set_name,
                                "number": number,
                                "finishRaw": finish_raw,
                                "finishNormalized": finish_clean,
                            },
                            "cardoryx": {
                                "cardKey": key,
                                "variant": card.get("variant"),
                                "stores": sorted(stores_for(card)),
                            },
                        })
                elif len(same) > 1:
                    stats["specialLabelMultipleExistingVariantsDiagnostic"] += 1
                else:
                    stats["specialLabelNoExistingCard"] += 1

            continue

        # ----------------------------------------------------------
        # B) Promo-style numbers
        # ----------------------------------------------------------
        pm = PROMO_RE.match(title)
        if pm and not is_sealed(title):
            stats["promoCardFormatAccepted"] += 1

            name = clean_spaces(pm.group("name"))
            number = normalize_promo_number(pm.group("number"))
            finish_raw = clean_spaces(pm.group("finish")).strip(" -")
            set_source = clean_spaces(pm.group("set"))
            condition = clean_spaces(pm.group("condition"))

            prefix = re.match(r"^[A-Z]+", number)
            if prefix:
                promo_number_prefixes[prefix.group(0)] += 1

            variant, evidence = source_variant_from_finish(strip_rarity(finish_raw))

            # Promo set naming may differ inside Cardoryx. We therefore NEVER
            # infer set aliases. We first look for exact number+name candidates,
            # then inspect whether exactly one current identity exists.
            number_matches = [
                key for key in by_number_only.get(number, [])
                if norm(cards[key].get("name")) == norm(name)
            ]

            if len(number_matches) == 1:
                key = number_matches[0]
                card = cards[key]
                stats["promoUniqueNumberNameDiagnostic"] += 1

                # Safe only if variant is explicit and matches Cardoryx exactly.
                if variant is not None and norm(card.get("variant")) == norm(variant):
                    item, reject = exact_candidate(
                        key, title, price,
                        "V4_promo_unique_number_name_explicit_variant",
                        {
                            "promoNumberSource": pm.group("number"),
                            "promoSetSource": set_source,
                            "conditionSource": condition,
                            "finishSource": finish_raw,
                            "variantEvidence": evidence,
                        },
                    )
                    if item:
                        safe.append(item)
                        stats["safePromoCandidates"] += 1
                        if item["wouldBecomeThirdStore"]:
                            stats["promoPotentialTwoToThree"] += 1
                    else:
                        stats[f"promoExactRejected_{reject}"] += 1
                else:
                    stats["promoVariantNotSafe"] += 1
                    if len(promo_diagnostics) < 200:
                        promo_diagnostics.append({
                            "accepted": False,
                            "reason": "promo_unique_number_name_but_variant_not_explicit_or_not_equal",
                            "title": title,
                            "source": {
                                "number": number,
                                "set": set_source,
                                "finish": finish_raw,
                                "condition": condition,
                                "detectedVariant": variant,
                            },
                            "cardoryx": {
                                "cardKey": key,
                                "set": card.get("set"),
                                "number": card.get("number"),
                                "variant": card.get("variant"),
                                "stores": sorted(stores_for(card)),
                            },
                        })

            elif len(number_matches) > 1:
                stats["promoNumberNameAmbiguous"] += 1
            else:
                stats["promoNoExistingNumberName"] += 1

            continue

        if is_sealed(title):
            stats["sealedProductRejected"] += 1
        else:
            stats["otherRejectedFormat"] += 1

# Dedupe safe candidates
dedup = []
seen = set()
for item in safe:
    token = (item["cardKey"], item["price"], item["reason"], item["title"])
    if token not in seen:
        seen.add(token)
        dedup.append(item)
safe = dedup

report = {
    "schema": 2,
    "source": "BSA Store",
    "mode": "read-only deep conservative availability audit V4",
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
        "specialLabelsNotAutoMapped": True,
        "promoSetAliasNotInferred": True,
        "sealedProductsRejected": True,
        "knownFusionStrikeAnomalyRejected": True,
        "priority": "special BSA labels and promo-style card numbers",
    },
    "stats": dict(stats),
    "topSpecialLabels": special_label_counts.most_common(100),
    "promoNumberPrefixes": promo_number_prefixes.most_common(20),
    "safeCandidates": safe,
    "specialLabelDiagnostics": special_label_diagnostics,
    "promoDiagnostics": promo_diagnostics,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print(f"SAFE CANDIDATES: {len(safe)}")
print(f"REPORT GENERATED: {REPORT}")
