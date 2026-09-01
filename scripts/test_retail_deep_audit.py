#!/usr/bin/env python3
"""CARDORYX — Deep Retail Audit read-only.

Audita Card Passion, GS-Gameon e Warcard senza modificare l'indice retail,
senza creare identita e senza leggere o scrivere dati Cardmarket.
"""

import hashlib
import json
import runpy
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "retail_deep_audit_report.json"


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if not BUILDER.exists():
    raise SystemExit(f"Builder non trovato: {BUILDER}")

if not RETAIL.exists():
    raise SystemExit(f"Retail non trovato: {RETAIL}")

retail_hash_before = file_sha256(RETAIL)

# run_name dedicato: un eventuale blocco `if __name__ == '__main__'` del
# builder non viene eseguito.
ns = runpy.run_path(
    str(BUILDER),
    run_name="__cardoryx_deep_retail_audit__",
)

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
    "gs_gameon_parse_title",
    "gs_gameon_variant",
    "warcard_parse_title",
    "warcard_variant",
    "http_get_json",
]

missing_functions = [
    name
    for name in REQUIRED_BUILDER_FUNCTIONS
    if not callable(ns.get(name))
]

if missing_functions:
    raise SystemExit(
        "Builder incompatibile con Deep Retail Audit. Mancano: "
        + ", ".join(missing_functions)
    )

norm = ns["norm"]
norm_number = ns["norm_number"]
strip_html = ns["strip_html"]

with RETAIL.open("r", encoding="utf-8") as stream:
    retail = json.load(stream)

if retail.get("rules", {}).get("cardmarketExcluded") is not True:
    raise SystemExit(
        "Safety check fallito: retail.rules.cardmarketExcluded != true"
    )

cards = retail.get("cards")
if not isinstance(cards, dict) or not cards:
    raise SystemExit("Indice retail mancante o vuoto")


def store_names(card):
    return {
        str(offer.get("store") or "").strip()
        for offer in (card.get("offers") or [])
        if str(offer.get("store") or "").strip()
    }


def compact_card(key, card):
    stores = store_names(card)
    return {
        "cardKey": key,
        "set": card.get("set"),
        "number": card.get("number"),
        "name": card.get("name"),
        "variant": card.get("variant"),
        "stores": sorted(stores),
        "storeCount": len(stores),
    }


def local_number(value):
    normalized = norm_number(value)
    return normalized.split("/")[0].lstrip("0") or "0"


def compact_set(value):
    # Riconciliazione circoscritta gia usata nel test precedente.
    # Non crea alias generici tra set differenti.
    normalized = norm(value)
    normalized = normalized.replace(" supplementi", "")
    normalized = normalized.replace(":", " ")
    return " ".join(normalized.split())


identity_by_set_number = defaultdict(list)
for card_key, card_value in cards.items():
    identity_by_set_number[
        (
            norm(card_value.get("set", "")),
            local_number(card_value.get("number", "")),
        )
    ].append((card_key, card_value))


def candidates_for(set_name, number):
    target_set = norm(set_name)
    target_number = local_number(number)
    found = list(
        identity_by_set_number.get((target_set, target_number), [])
    )
    if found:
        return found, "exact-set"

    target_compact = compact_set(target_set)
    possible = []
    for (set_key, number_key), values in identity_by_set_number.items():
        if number_key != target_number:
            continue
        if compact_set(set_key) == target_compact:
            possible.extend(values)

    return (
        possible,
        "supplementi-normalized" if possible else "none",
    )


def impact_for(stores):
    count = len(stores)
    if count == 2:
        return "2->3"
    if count == 1:
        return "1->2"
    return f"{count}->{count + 1}"


def add_candidate(
    *,
    stats,
    card_key,
    card,
    context,
    price,
    store,
    safe_candidates,
    priority_candidates,
    safe_limit,
    priority_limit,
):
    stats["productionEligible"] += 1
    stores = store_names(card)

    if store in stores:
        stats["alreadyPresentInRetail"] += 1
        return

    stats["safeMissingStoreCandidates"] += 1
    candidate = {
        **context,
        "price": price,
        "existingIdentity": compact_card(card_key, card),
        "impact": impact_for(stores),
        "status": "safe-diagnostic-candidate",
    }

    if len(safe_candidates) < safe_limit:
        safe_candidates.append(candidate)

    if len(stores) == 2:
        stats["potentialTwoToThree"] += 1
        if len(priority_candidates) < priority_limit:
            priority_candidates.append(candidate)
    elif len(stores) == 1:
        stats["potentialOneToTwo"] += 1
    elif len(stores) >= 3:
        stats["potentialAlreadyReliablePlusOne"] += 1


def normalized_price(raw_price, integer_is_cents=False):
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return None

    if integer_is_cents and isinstance(raw_price, int):
        price /= 100.0

    price = round(price, 2)
    return price if price > 0 else None


def audit_card_passion():
    """Audit conservativo Card Passion basato sulle funzioni del builder."""
    stats = Counter()
    rejection_examples = defaultdict(list)
    safe_candidates = []
    priority_candidates = []
    exact_identity_failed_metadata = []
    title_format_review = []

    def example(reason, payload):
        if len(rejection_examples[reason]) < 30:
            rejection_examples[reason].append(payload)

    try:
        products = ns["get_cardpassion_products"]()
        if not isinstance(products, (list, tuple)):
            raise RuntimeError(
                "get_cardpassion_products non ha restituito una lista"
            )

        for product in products:
            stats["products"] += 1
            if not isinstance(product, dict):
                stats["invalidProduct"] += 1
                example("invalidProduct", {"value": repr(product)[:300]})
                continue

            title = strip_html(
                str(product.get("name") or product.get("title") or "")
            ).strip()
            product_url = (
                product.get("permalink")
                or product.get("url")
                or product.get("link")
            )
            body = strip_html(
                str(product.get("body_html") or "")
            )
            raw_tags = product.get("tags")
            tags_text = (
                " ".join(str(tag) for tag in raw_tags)
                if isinstance(raw_tags, list)
                else str(raw_tags or "")
            )

            if ns["cardpassion_excluded"](title, body, tags_text):
                stats["excluded"] += 1
                example("excluded", {"title": title, "url": product_url})
                continue

            parsed = ns["parse_cardpassion_title"](title)
            if not isinstance(parsed, dict):
                stats["invalidTitle"] += 1
                review = {"title": title, "url": product_url}
                example("invalidTitle", review)
                if len(title_format_review) < 150:
                    title_format_review.append(review)
                continue

            parsed_set = parsed.get("set")
            parsed_number = parsed.get("localNumber") or parsed.get("number")
            parsed_name = parsed.get("name")
            parsed_variant = parsed.get("variant")

            if not all(
                [parsed_set, parsed_number, parsed_name, parsed_variant]
            ):
                stats["incompleteParsedIdentity"] += 1
                review = {
                    "title": title,
                    "url": product_url,
                    "parsed": parsed,
                }
                example("incompleteParsedIdentity", review)
                if len(title_format_review) < 150:
                    title_format_review.append(review)
                continue

            candidates, reconciliation = candidates_for(
                parsed_set, parsed_number
            )
            context = {
                "title": title,
                "url": product_url,
                "set": parsed_set,
                "localNumber": local_number(parsed_number),
                "name": parsed_name,
                "mappedVariant": parsed_variant,
                "reconciliation": reconciliation,
            }

            if not candidates:
                stats["noExistingSetNumberIdentity"] += 1
                example("noExistingSetNumberIdentity", context)
                continue

            matching = [
                (key, card)
                for key, card in candidates
                if norm(card.get("name", "")) == norm(parsed_name)
                and norm(card.get("variant", "")) == norm(parsed_variant)
            ]

            if len(matching) != 1:
                stats["identityAmbiguous"] += 1
                example(
                    "identityAmbiguous",
                    {
                        **context,
                        "setNumberCandidateCount": len(candidates),
                        "exactNameVariantMatchCount": len(matching),
                    },
                )
                continue

            card_key, card = matching[0]
            language = ns["cardpassion_language"](
                title,
                body,
                tags_text,
                parsed_set,
            )
            condition = ns["cardpassion_condition"](
                title,
                body,
                tags_text,
            )
            context.update(
                {
                    "language": language,
                    "condition": condition,
                }
            )

            if language != "IT":
                stats["languageRejected"] += 1
                example("languageRejected", context)
                if len(exact_identity_failed_metadata) < 150:
                    exact_identity_failed_metadata.append(
                        {**context, "reason": "languageRejected"}
                    )
                continue

            if condition != "NM/MINT":
                stats["conditionRejected"] += 1
                example("conditionRejected", context)
                if len(exact_identity_failed_metadata) < 150:
                    exact_identity_failed_metadata.append(
                        {**context, "reason": "conditionRejected"}
                    )
                continue

            # Fail-closed: una disponibilita esplicitamente negativa viene
            # sempre respinta. L'eventuale logica piu specifica resta nella
            # funzione cardpassion_excluded del builder.
            if (
                product.get("stock_status") == "outofstock"
                or product.get("in_stock") is False
                or product.get("available") is False
                or product.get("purchasable") is False
            ):
                stats["unavailable"] += 1
                example("unavailable", context)
                continue

            raw_price = ns["cardpassion_price"](product)
            price = normalized_price(raw_price)
            if price is None:
                stats["priceUnavailable"] += 1
                example("priceUnavailable", context)
                continue

            add_candidate(
                stats=stats,
                card_key=card_key,
                card=card,
                context=context,
                price=price,
                store="Card Passion",
                safe_candidates=safe_candidates,
                priority_candidates=priority_candidates,
                safe_limit=200,
                priority_limit=100,
            )

    except Exception as exc:
        stats["errors"] += 1
        return {
            "source": "Card Passion",
            "ok": False,
            "mode": "deep-read-only",
            "error": f"{type(exc).__name__}: {exc}",
            "stats": dict(stats),
            "rejectionExamples": dict(rejection_examples),
            "priorityTwoToThree": priority_candidates,
            "safeMissingStoreCandidates": safe_candidates,
            "exactIdentityButFailedMetadata": exact_identity_failed_metadata,
            "titleFormatManualReview": title_format_review,
        }

    return {
        "source": "Card Passion",
        "ok": True,
        "mode": "deep-read-only",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_candidates,
        "safeMissingStoreCandidates": safe_candidates,
        "exactIdentityButFailedMetadata": exact_identity_failed_metadata,
        "titleFormatManualReview": title_format_review,
    }


def audit_gs_gameon():
    """Audit GS-Gameon con Promo + Regolare fail-closed."""
    stats = Counter()
    rejection_examples = defaultdict(list)
    safe_candidates = []
    priority_candidates = []
    ambiguous_name_review = []

    def example(reason, payload):
        if len(rejection_examples[reason]) < 30:
            rejection_examples[reason].append(payload)

    try:
        url_template = ns.get("GS_GAMEON_COLLECTION_URL")
        if not isinstance(url_template, str) or "{page}" not in url_template:
            raise RuntimeError("GS_GAMEON_COLLECTION_URL mancante o invalido")

        for page in range(1, 41):
            payload = ns["http_get_json"](url_template.format(page=page))
            products = (
                payload.get("products", [])
                if isinstance(payload, dict)
                else []
            )
            if not products:
                break

            for product in products:
                stats["products"] += 1
                title = str(product.get("title") or "").strip()
                handle = str(product.get("handle") or "").strip()
                product_url = (
                    "https://www.gs-gameon.com/products/" + handle
                    if handle
                    else None
                )
                parsed = ns["gs_gameon_parse_title"](title)
                if not isinstance(parsed, dict):
                    stats["invalidTitle"] += 1
                    example("invalidTitle", {"title": title, "url": product_url})
                    continue

                candidates, reconciliation = candidates_for(
                    parsed.get("set", ""), parsed.get("localNumber", "")
                )
                if not candidates:
                    stats["noExistingSetNumberIdentity"] += 1

                for shop_variant in product.get("variants", []) or []:
                    stats["variants"] += 1
                    context = {
                        "title": title,
                        "url": product_url,
                        "set": parsed.get("set"),
                        "localNumber": parsed.get("localNumber"),
                        "rarity": parsed.get("rarity"),
                        "language": str(shop_variant.get("option1", "")).strip(),
                        "condition": str(shop_variant.get("option2", "")).strip(),
                        "edition": str(shop_variant.get("option3", "")).strip(),
                        "reconciliation": reconciliation,
                    }

                    if not shop_variant.get("available"):
                        stats["unavailable"] += 1
                        example("unavailable", context)
                        continue
                    if norm(context["language"]) != "italiano":
                        stats["languageRejected"] += 1
                        example("languageRejected", context)
                        continue
                    if norm(context["condition"]) != "near mint":
                        stats["conditionRejected"] += 1
                        example("conditionRejected", context)
                        continue

                    edition_n = norm(context["edition"])
                    rarity_n = norm(parsed.get("rarity", ""))
                    if "promo" in rarity_n and edition_n in (
                        "regolare",
                        "regular",
                        "",
                    ):
                        stats["promoAmbiguousRejected"] += 1
                        example("promoAmbiguousRejected", context)
                        continue

                    variant = ns["gs_gameon_variant"](
                        context["edition"], parsed.get("rarity")
                    )
                    context["mappedVariant"] = variant
                    if variant is None:
                        stats["editionRejected"] += 1
                        example("editionRejected", context)
                        continue

                    matching = [
                        (key, card)
                        for key, card in candidates
                        if card.get("variant") == variant
                    ]
                    if len(matching) != 1:
                        stats["identityAmbiguous"] += 1
                        name_matching = [
                            (key, card)
                            for key, card in matching
                            if norm(card.get("name", ""))
                            == norm(parsed.get("name", ""))
                        ]
                        if len(name_matching) == 1:
                            stats["ambiguousResolvedByExactNameDiagnostic"] += 1
                            key, card = name_matching[0]
                            if len(ambiguous_name_review) < 200:
                                ambiguous_name_review.append(
                                    {
                                        **context,
                                        "existingIdentity": compact_card(key, card),
                                        "status": "manual-review-only",
                                        "reason": (
                                            "set/number/variant ambiguo; il nome "
                                            "normalizzato lascia una sola identita"
                                        ),
                                    }
                                )
                        example(
                            "identityAmbiguous",
                            {
                                **context,
                                "candidateCount": len(candidates),
                                "variantCandidateCount": len(matching),
                            },
                        )
                        continue

                    card_key, card = matching[0]
                    price = normalized_price(
                        shop_variant.get("price"), integer_is_cents=True
                    )
                    if price is None:
                        stats["priceUnavailable"] += 1
                        example("priceUnavailable", context)
                        continue

                    add_candidate(
                        stats=stats,
                        card_key=card_key,
                        card=card,
                        context=context,
                        price=price,
                        store="GS-Gameon",
                        safe_candidates=safe_candidates,
                        priority_candidates=priority_candidates,
                        safe_limit=300,
                        priority_limit=150,
                    )

            if len(products) < 250:
                break

    except Exception as exc:
        stats["errors"] += 1
        return {
            "source": "GS-Gameon",
            "ok": False,
            "mode": "deep-read-only-gs-promo-fail-closed",
            "error": f"{type(exc).__name__}: {exc}",
            "stats": dict(stats),
            "rejectionExamples": dict(rejection_examples),
            "priorityTwoToThree": priority_candidates,
            "safeMissingStoreCandidates": safe_candidates,
            "ambiguousResolvedByExactNameDiagnostic": ambiguous_name_review,
        }

    return {
        "source": "GS-Gameon",
        "ok": True,
        "mode": "deep-read-only-gs-promo-fail-closed",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_candidates,
        "safeMissingStoreCandidates": safe_candidates,
        "ambiguousResolvedByExactNameDiagnostic": ambiguous_name_review,
    }


def audit_warcard():
    """Warcard: set + numero + variante + nome esatto, ITA, NM, disponibile."""
    stats = Counter()
    rejection_examples = defaultdict(list)
    safe_candidates = []
    priority_candidates = []
    name_mismatch_review = []

    def example(reason, payload):
        if len(rejection_examples[reason]) < 40:
            rejection_examples[reason].append(payload)

    try:
        url_template = ns.get("WARCARD_COLLECTION_URL")
        if not isinstance(url_template, str) or "{page}" not in url_template:
            raise RuntimeError("WARCARD_COLLECTION_URL mancante o invalido")

        for page in range(1, 61):
            payload = ns["http_get_json"](url_template.format(page=page))
            products = (
                payload.get("products", [])
                if isinstance(payload, dict)
                else []
            )
            if not products:
                break

            for product in products:
                stats["products"] += 1
                title = str(product.get("title") or "").strip()
                handle = str(product.get("handle") or "").strip()
                product_url = (
                    "https://www.warcard.it/products/" + handle
                    if handle
                    else None
                )
                parsed = ns["warcard_parse_title"](title)
                if not isinstance(parsed, dict):
                    stats["invalidTitle"] += 1
                    example("invalidTitle", {"title": title, "url": product_url})
                    continue

                candidates, reconciliation = candidates_for(
                    parsed.get("set", ""), parsed.get("localNumber", "")
                )
                if not candidates:
                    stats["noExistingSetNumberIdentity"] += 1

                for shop_variant in product.get("variants", []) or []:
                    stats["variants"] += 1
                    context = {
                        "title": title,
                        "url": product_url,
                        "set": parsed.get("set"),
                        "localNumber": parsed.get("localNumber"),
                        "code": parsed.get("code"),
                        "name": parsed.get("name"),
                        "rarity": parsed.get("rarity"),
                        "language": str(shop_variant.get("option1", "")).strip(),
                        "condition": str(shop_variant.get("option2", "")).strip(),
                        "edition": str(shop_variant.get("option3", "")).strip(),
                        "reconciliation": reconciliation,
                    }

                    if not shop_variant.get("available"):
                        stats["unavailable"] += 1
                        example("unavailable", context)
                        continue
                    if norm(context["language"]) != "italiano":
                        stats["languageRejected"] += 1
                        example("languageRejected", context)
                        continue
                    if norm(context["condition"]) != "near mint":
                        stats["conditionRejected"] += 1
                        example("conditionRejected", context)
                        continue

                    variant = ns["warcard_variant"](
                        context["edition"], parsed.get("rarity")
                    )
                    context["mappedVariant"] = variant
                    if variant is None:
                        stats["editionRejected"] += 1
                        example("editionRejected", context)
                        continue

                    variant_candidates = [
                        (key, card)
                        for key, card in candidates
                        if card.get("variant") == variant
                    ]
                    matching = [
                        (key, card)
                        for key, card in variant_candidates
                        if norm(card.get("name", ""))
                        == norm(parsed.get("name", ""))
                    ]

                    if len(matching) != 1:
                        stats["identityAmbiguous"] += 1
                        if variant_candidates and not matching:
                            stats["exactNameMismatch"] += 1
                            review = {
                                **context,
                                "variantCandidateCount": len(variant_candidates),
                                "variantCandidateIdentities": [
                                    compact_card(key, card)
                                    for key, card in variant_candidates[:8]
                                ],
                                "status": "manual-review-only",
                                "reason": (
                                    "set/number/variant esistono ma il nome "
                                    "normalizzato non coincide; nessun "
                                    "allentamento automatico"
                                ),
                            }
                            if len(name_mismatch_review) < 250:
                                name_mismatch_review.append(review)
                            example("exactNameMismatch", review)
                        else:
                            example(
                                "identityAmbiguous",
                                {
                                    **context,
                                    "setNumberCandidateCount": len(candidates),
                                    "variantCandidateCount": len(variant_candidates),
                                    "exactNameMatchCount": len(matching),
                                },
                            )
                        continue

                    card_key, card = matching[0]
                    price = normalized_price(
                        shop_variant.get("price"), integer_is_cents=True
                    )
                    if price is None:
                        stats["priceUnavailable"] += 1
                        example("priceUnavailable", context)
                        continue

                    add_candidate(
                        stats=stats,
                        card_key=card_key,
                        card=card,
                        context=context,
                        price=price,
                        store="Warcard",
                        safe_candidates=safe_candidates,
                        priority_candidates=priority_candidates,
                        safe_limit=400,
                        priority_limit=200,
                    )

            if len(products) < 250:
                break

    except Exception as exc:
        stats["errors"] += 1
        return {
            "source": "Warcard",
            "ok": False,
            "mode": "deep-read-only-exact-name",
            "error": f"{type(exc).__name__}: {exc}",
            "stats": dict(stats),
            "rejectionExamples": dict(rejection_examples),
            "priorityTwoToThree": priority_candidates,
            "safeMissingStoreCandidates": safe_candidates,
            "exactNameMismatchReview": name_mismatch_review,
        }

    return {
        "source": "Warcard",
        "ok": True,
        "mode": "deep-read-only-exact-name",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_candidates,
        "safeMissingStoreCandidates": safe_candidates,
        "exactNameMismatchReview": name_mismatch_review,
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

source_reports = [
    audit_card_passion(),
    audit_gs_gameon(),
    audit_warcard(),
]

# Verifica effettiva: l'indice retail deve essere byte-per-byte invariato.
retail_hash_after = file_sha256(RETAIL)
if retail_hash_after != retail_hash_before:
    raise SystemExit(
        "Safety check fallito: retail_prices.json e stato modificato durante "
        "l'audit. Il report non viene scritto."
    )

report = {
    "schema": 1,
    "generatedAt": utc_now(),
    "name": "Cardoryx Deep Retail Audit",
    "auditVersion": "warcard-deep-audit-v1-2026-09-01",
    "mode": "read-only unified framework",
    "rules": {
        "retailPricesModified": False,
        "retailHashBefore": retail_hash_before,
        "retailHashAfter": retail_hash_after,
        "cardmarketTouched": False,
        "newIdentitiesCreated": False,
        "productionDataModified": False,
        "exactExistingIdentityPreferred": True,
        "priorityTwoToThree": True,
        "failClosed": True,
        "disabledStoresNotAudited": True,
        "warcardExactNormalizedNameRequired": True,
        "gsPromoRegularRejected": True,
    },
    "activeStores": ACTIVE_STORES,
    "excludedStores": EXCLUDED_STORES,
    "implementedAdapters": [
        "Card Passion",
        "GS-Gameon",
        "Warcard",
    ],
    "pendingAdapters": [
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

# Unica scrittura consentita: il report diagnostico.
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("=== CARDORYX DEEP RETAIL AUDIT ===")
print(
    json.dumps(
        {
            "implementedAdapters": report["implementedAdapters"],
            "pendingAdapters": report["pendingAdapters"],
            "cardPassionStats": source_reports[0]["stats"],
            "gsGameonStats": source_reports[1]["stats"],
            "warcardStats": source_reports[2]["stats"],
            "retailPricesModified": False,
        },
        ensure_ascii=False,
        indent=2,
    )
)
print(f"Report: {REPORT}")
