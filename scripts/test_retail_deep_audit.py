#!/usr/bin/env python3
# CARDORYX — DEEP RETAIL AUDIT
# Read-only diagnostic framework.
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
    "gs_gameon_parse_title",
    "gs_gameon_variant",
    "warcard_parse_title",
    "warcard_variant",
    "http_get_json",
]

missing = [
    name
    for name in REQUIRED_BUILDER_FUNCTIONS
    if not callable(ns.get(name))
]

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
    raise SystemExit(
        "Safety check fallito: retail.rules.cardmarketExcluded != true"
    )

cards = retail.get("cards")

if not isinstance(cards, dict) or not cards:
    raise SystemExit("Indice retail mancante o vuoto")


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


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


# Exact existing identity indexes.
# Diagnostic only: no new identities are created.
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
        "mode": "deep-read-only-gs-promo-fail-closed-test",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_two_to_three,
        "safeMissingStoreCandidates": safe_missing_store_candidates,
        "exactIdentityButFailedMetadata": exact_identity_but_failed_metadata,
        "titleFormatManualReview": title_format_review,
    }


def audit_gs_gameon():
    """Deep read-only audit mirroring current GS-Gameon V17 production logic."""
    stats = Counter()
    rejection_examples = defaultdict(list)
    safe_missing_store_candidates = []
    priority_two_to_three = []
    ambiguous_name_review = []

    identity_index = defaultdict(list)
    for key, card in cards.items():
        number = norm_number(card.get("number", ""))
        base = number.split("/")[0].lstrip("0") or "0"
        identity_index[(norm(card.get("set", "")), base)].append((key, card))

    def example(reason, payload):
        if len(rejection_examples[reason]) < 30:
            rejection_examples[reason].append(payload)

    def candidates_for(parsed):
        target_set = norm(parsed["set"])
        target_number = parsed["localNumber"]
        found = list(identity_index.get((target_set, target_number), []))
        reconciliation = "exact-set"

        if not found:
            compact_target = target_set.replace(" supplementi", "").replace(":", " ")
            compact_target = " ".join(compact_target.split())
            possible = []

            for (set_key, number_key), values in identity_index.items():
                if number_key != target_number:
                    continue

                compact_set = set_key.replace(" supplementi", "").replace(":", " ")
                compact_set = " ".join(compact_set.split())

                if compact_set == compact_target:
                    possible.extend(values)

            found = possible
            reconciliation = "supplementi-normalized" if found else "none"

        return found, reconciliation

    for page in range(1, 41):
        url = ns["GS_GAMEON_COLLECTION_URL"].format(page=page)
        payload = ns["http_get_json"](url)
        products = payload.get("products", []) if isinstance(payload, dict) else []

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

            if not parsed:
                stats["invalidTitle"] += 1
                example(
                    "invalidTitle",
                    {
                        "title": title,
                        "url": product_url,
                    },
                )
                continue

            candidates, reconciliation = candidates_for(parsed)

            if not candidates:
                stats["noExistingSetNumberIdentity"] += 1

            for shop_variant in (product.get("variants", []) or []):
                stats["variants"] += 1

                context = {
                    "title": title,
                    "url": product_url,
                    "set": parsed.get("set"),
                    "localNumber": parsed.get("localNumber"),
                    "rarity": parsed.get("rarity"),
                    "language": str(
                        shop_variant.get("option1", "")
                    ).strip(),
                    "condition": str(
                        shop_variant.get("option2", "")
                    ).strip(),
                    "edition": str(
                        shop_variant.get("option3", "")
                    ).strip(),
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

                # FAIL CLOSED:
                # la rarità commerciale "Promo" NON può essere
                # automaticamente interpretata come variante fisica Normal
                # quando l'edizione è soltanto Regolare/Regular/vuota.
                #
                # Questo evita falsi positivi su carte che possono esistere
                # anche come Cosmos Holo, Reverse, stamp speciali, ecc.
                #
                # Se invece la finitura fisica è esplicitamente indicata,
                # ad esempio Reverse-Holo, il normale parser può continuare.

                edition_n = norm(context["edition"])
                rarity_n = norm(parsed["rarity"])

                if (
                    "promo" in rarity_n
                    and edition_n in (
                        "regolare",
                        "regular",
                        "",
                    )
                ):
                    stats["promoAmbiguousRejected"] += 1
                    example(
                        "promoAmbiguousRejected",
                        context,
                    )
                    continue

                variant = ns["gs_gameon_variant"](
                    context["edition"],
                    parsed["rarity"],
                )

                context["mappedVariant"] = variant

                if variant is None:
                    stats["editionRejected"] += 1
                    example(
                        "editionRejected",
                        context,
                    )
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
                        stats[
                            "ambiguousResolvedByExactNameDiagnostic"
                        ] += 1

                        key, card = name_matching[0]

                        if len(ambiguous_name_review) < 200:
                            ambiguous_name_review.append(
                                {
                                    **context,
                                    "existingIdentity": compact_card(
                                        key,
                                        card,
                                    ),
                                    "status": "manual-review-only",
                                    "reason": (
                                        "production set/number/variant "
                                        "ambiguous; exact normalized name "
                                        "leaves one existing identity"
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

                key, card = matching[0]

                raw_price = shop_variant.get("price")

                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    stats["priceUnavailable"] += 1
                    example(
                        "priceUnavailable",
                        context,
                    )
                    continue

                if isinstance(raw_price, int):
                    price = price / 100.0

                price = round(price, 2)

                if price <= 0:
                    stats["priceUnavailable"] += 1
                    example(
                        "priceUnavailable",
                        context,
                    )
                    continue

                stats["productionEligible"] += 1

                stores = store_names(card)

                if "GS-Gameon" in stores:
                    stats["alreadyPresentInRetail"] += 1
                    continue

                stats["safeMissingStoreCandidates"] += 1

                candidate = {
                    **context,
                    "price": price,
                    "existingIdentity": compact_card(
                        key,
                        card,
                    ),
                    "impact": (
                        "2->3"
                        if len(stores) == 2
                        else "1->2"
                        if len(stores) == 1
                        else f"{len(stores)}->{len(stores)+1}"
                    ),
                    "status": "safe-diagnostic-candidate",
                }

                if len(safe_missing_store_candidates) < 300:
                    safe_missing_store_candidates.append(
                        candidate
                    )

                if len(stores) == 2:
                    stats["potentialTwoToThree"] += 1

                    if len(priority_two_to_three) < 150:
                        priority_two_to_three.append(
                            candidate
                        )

                elif len(stores) == 1:
                    stats["potentialOneToTwo"] += 1

        if len(products) < 250:
            break

    return {
        "source": "GS-Gameon",
        "ok": True,
        "mode": "deep-read-only",
        "stats": dict(stats),
        "rejectionExamples": dict(rejection_examples),
        "priorityTwoToThree": priority_two_to_three,
        "safeMissingStoreCandidates": safe_missing_store_candidates,
        "ambiguousResolvedByExactNameDiagnostic": ambiguous_name_review,
    }


# ============================================================
# WARCARD — DEEP READ-ONLY AUDIT
# ============================================================

def audit_warcard():
    """
    Deep read-only audit mirroring current Warcard production matching:

    - existing set
    - local collector number
    - exact mapped physical variant
    - exact normalized card name
    - Italian
    - Near Mint
    - available
    - positive unambiguous price
    - exactly one existing physical identity

    This audit NEVER writes offers into retail_prices.json.
    """

    stats = Counter()
    rejection_examples = defaultdict(list)

    safe_missing_store_candidates = []
    priority_two_to_three = []
    name_mismatch_review = []

    identity_index = defaultdict(list)

    for key, card in cards.items():
        number = norm_number(
            card.get("number", "")
        )

        base = (
            number
            .split("/")[0]
            .lstrip("0")
            or "0"
        )

        identity_index[
            (
                norm(card.get("set", "")),
                base,
            )
        ].append(
            (
                key,
                card,
            )
        )

    def example(reason, payload):
        if len(rejection_examples[reason]) < 40:
            rejection_examples[reason].append(
                payload
            )

    def candidates_for(parsed):
        target_set = norm(
            parsed["set"]
        )

        target_number = parsed[
            "localNumber"
        ]

        found = list(
            identity_index.get(
                (
                    target_set,
                    target_number,
                ),
                [],
            )
        )

        reconciliation = "exact-set"

        if not found:
            compact_target = (
                target_set
                .replace(
                    " supplementi",
                    "",
                )
                .replace(
                    ":",
                    " ",
                )
            )

            compact_target = " ".join(
                compact_target.split()
            )

            possible = []

            for (
                set_key,
                number_key,
            ), values in identity_index.items():

                if (
                    number_key
                    != target_number
                ):
                    continue

                compact_set = (
                    set_key
                    .replace(
                        " supplementi",
                        "",
                    )
                    .replace(
                        ":",
                        " ",
                    )
                )

                compact_set = " ".join(
                    compact_set.split()
                )

                if (
                    compact_set
                    == compact_target
                ):
                    possible.extend(
                        values
                    )

            found = possible

            reconciliation = (
                "supplementi-normalized"
                if found
                else "none"
            )

        return (
            found,
            reconciliation,
        )

    try:
        for page in range(1, 61):

            url = ns[
                "WARCARD_COLLECTION_URL"
            ].format(
                page=page
            )
               payload = ns["http_get_json"](url)

            products = (
                payload.get("products", [])
                if isinstance(payload, dict)
                else []
            )

            if not products:
                break

            for product in products:
                stats["products"] += 1

                title = str(
                    product.get("title") or ""
                ).strip()

                handle = str(
                    product.get("handle") or ""
                ).strip()

                product_url = (
                    "https://www.warcard.it/products/"
                    + handle
                    if handle
                    else None
                )

                parsed = ns[
                    "warcard_parse_title"
                ](title)

                if not parsed:
                    stats["invalidTitle"] += 1

                    example(
                        "invalidTitle",
                        {
                            "title": title,
                            "url": product_url,
                        },
                    )
                    continue

                candidates, reconciliation = (
                    candidates_for(parsed)
                )

                if not candidates:
                    stats[
                        "noExistingSetNumberIdentity"
                    ] += 1

                for shop_variant in (
                    product.get(
                        "variants",
                        [],
                    )
                    or []
                ):
                    stats["variants"] += 1

                    context = {
                        "title": title,
                        "url": product_url,
                        "set": parsed.get(
                            "set"
                        ),
                        "localNumber": parsed.get(
                            "localNumber"
                        ),
                        "code": parsed.get(
                            "code"
                        ),
                        "name": parsed.get(
                            "name"
                        ),
                        "rarity": parsed.get(
                            "rarity"
                        ),
                        "language": str(
                            shop_variant.get(
                                "option1",
                                "",
                            )
                        ).strip(),
                        "condition": str(
                            shop_variant.get(
                                "option2",
                                "",
                            )
                        ).strip(),
                        "edition": str(
                            shop_variant.get(
                                "option3",
                                "",
                            )
                        ).strip(),
                        "reconciliation": (
                            reconciliation
                        ),
                    }

                    if not shop_variant.get(
                        "available"
                    ):
                        stats[
                            "unavailable"
                        ] += 1

                        example(
                            "unavailable",
                            context,
                        )
                        continue

                    if (
                        norm(
                            context[
                                "language"
                            ]
                        )
                        != "italiano"
                    ):
                        stats[
                            "languageRejected"
                        ] += 1

                        example(
                            "languageRejected",
                            context,
                        )
                        continue

                    if (
                        norm(
                            context[
                                "condition"
                            ]
                        )
                        != "near mint"
                    ):
                        stats[
                            "conditionRejected"
                        ] += 1

                        example(
                            "conditionRejected",
                            context,
                        )
                        continue

                    variant = ns[
                        "warcard_variant"
                    ](
                        context["edition"],
                        parsed["rarity"],
                    )

                    context[
                        "mappedVariant"
                    ] = variant

                    if variant is None:
                        stats[
                            "editionRejected"
                        ] += 1

                        example(
                            "editionRejected",
                            context,
                        )
                        continue

                    variant_candidates = [
                        (
                            key,
                            card,
                        )
                        for key, card
                        in candidates
                        if card.get(
                            "variant"
                        )
                        == variant
                    ]

                    matching = [
                        (
                            key,
                            card,
                        )
                        for key, card
                        in variant_candidates
                        if norm(
                            card.get(
                                "name",
                                "",
                            )
                        )
                        == norm(
                            parsed.get(
                                "name",
                                "",
                            )
                        )
                    ]

                    if len(matching) != 1:
                        stats[
                            "identityAmbiguous"
                        ] += 1

                        if (
                            variant_candidates
                            and not matching
                        ):
                            stats[
                                "exactNameMismatch"
                            ] += 1

                            review = {
                                **context,
                                "variantCandidateCount": (
                                    len(
                                        variant_candidates
                                    )
                                ),
                                "variantCandidateIdentities": [
                                    compact_card(
                                        key,
                                        card,
                                    )
                                    for key, card
                                    in (
                                        variant_candidates[
                                            :8
                                        ]
                                    )
                                ],
                                "status": (
                                    "manual-review-only"
                                ),
                                "reason": (
                                    "set/number/variant "
                                    "esistono ma il nome "
                                    "normalizzato non coincide; "
                                    "nessun allentamento "
                                    "automatico"
                                ),
                            }

                            if (
                                len(
                                    name_mismatch_review
                                )
                                < 250
                            ):
                                name_mismatch_review.append(
                                    review
                                )

                            example(
                                "exactNameMismatch",
                                review,
                            )

                        else:
                            example(
                                "identityAmbiguous",
                                {
                                    **context,
                                    "setNumberCandidateCount": (
                                        len(
                                            candidates
                                        )
                                    ),
                                    "variantCandidateCount": (
                                        len(
                                            variant_candidates
                                        )
                                    ),
                                    "exactNameMatchCount": (
                                        len(
                                            matching
                                        )
                                    ),
                                },
                            )

                        continue

                    key, card = matching[0]

                    raw_price = (
                        shop_variant.get(
                            "price"
                        )
                    )

                    try:
                        price = float(
                            raw_price
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        stats[
                            "priceUnavailable"
                        ] += 1

                        example(
                            "priceUnavailable",
                            context,
                        )
                        continue

                    if isinstance(
                        raw_price,
                        int,
                    ):
                        price = (
                            price / 100.0
                        )

                    price = round(
                        price,
                        2,
                    )

                    if price <= 0:
                        stats[
                            "priceUnavailable"
                        ] += 1

                        example(
                            "priceUnavailable",
                            context,
                        )
                        continue

                    stats[
                        "productionEligible"
                    ] += 1

                    stores = store_names(
                        card
                    )

                    if "Warcard" in stores:
                        stats[
                            "alreadyPresentInRetail"
                        ] += 1
                        continue

                    stats[
                        "safeMissingStoreCandidates"
                    ] += 1

                    candidate = {
                        **context,
                        "price": price,
                        "existingIdentity": (
                            compact_card(
                                key,
                                card,
                            )
                        ),
                        "impact": (
                            "2->3"
                            if len(stores) == 2
                            else "1->2"
                            if len(stores) == 1
                            else (
                                f"{len(stores)}"
                                f"->{len(stores)+1}"
                            )
                        ),
                        "status": (
                            "safe-diagnostic-candidate"
                        ),
                    }

                    if (
                        len(
                            safe_missing_store_candidates
                        )
                        < 400
                    ):
                        safe_missing_store_candidates.append(
                            candidate
                        )

                    if len(stores) == 2:
                        stats[
                            "potentialTwoToThree"
                        ] += 1

                        if (
                            len(
                                priority_two_to_three
                            )
                            < 200
                        ):
                            priority_two_to_three.append(
                                candidate
                            )

                    elif len(stores) == 1:
                        stats[
                            "potentialOneToTwo"
                        ] += 1

                    elif len(stores) >= 3:
                        stats[
                            "potentialAlreadyReliablePlusOne"
                        ] += 1

            if len(products) < 250:
                break

    except Exception as exc:
        stats["errors"] += 1

        return {
            "source": "Warcard",
            "ok": False,
            "mode": "deep-read-only",
            "error": str(exc),
            "stats": dict(stats),
            "rejectionExamples": dict(
                rejection_examples
            ),
            "priorityTwoToThree": (
                priority_two_to_three
            ),
            "safeMissingStoreCandidates": (
                safe_missing_store_candidates
            ),
            "exactNameMismatchReview": (
                name_mismatch_review
            ),
        }

    return {
        "source": "Warcard",
        "ok": True,
        "mode": "deep-read-only",
        "stats": dict(stats),
        "rejectionExamples": dict(
            rejection_examples
        ),
        "priorityTwoToThree": (
            priority_two_to_three
        ),
        "safeMissingStoreCandidates": (
            safe_missing_store_candidates
        ),
        "exactNameMismatchReview": (
            name_mismatch_review
        ),
    }


# ============================================================
# AUDIT CONFIGURATION
# ============================================================

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


# ============================================================
# RUN AUDITS
# ============================================================

source_reports = [
    audit_card_passion(),
    audit_gs_gameon(),
    audit_warcard(),
]


# ============================================================
# FINAL READ-ONLY REPORT
# ============================================================

report = {
    "schema": 1,
    "generatedAt": utc_now(),
    "name": "Cardoryx Deep Retail Audit",
    "auditVersion": (
        "warcard-deep-audit-v1-2026-09-01"
    ),
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

    "referenceOnly": [
        "BSA Store",
    ],

    "retailSnapshot": {
        "generatedAt": (
            retail.get(
                "generatedAt"
            )
        ),
        "cards": (
            retail.get(
                "stats",
                {},
            ).get(
                "cards"
            )
        ),
        "offers": (
            retail.get(
                "stats",
                {},
            ).get(
                "offers"
            )
        ),
        "multiStoreCards": (
            retail.get(
                "stats",
                {},
            ).get(
                "multiStoreCards"
            )
        ),
        "reliableCards": (
            retail.get(
                "stats",
                {},
            ).get(
                "reliableCards"
            )
        ),
        "threeStoreCards": (
            retail.get(
                "stats",
                {},
            ).get(
                "threeStoreCards"
            )
        ),
    },

    "sources": source_reports,
}


# ============================================================
# WRITE DIAGNOSTIC REPORT ONLY
# ============================================================

REPORT.parent.mkdir(
    parents=True,
    exist_ok=True,
)

REPORT.write_text(
    json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# ============================================================
# CONSOLE SUMMARY
# ============================================================

print(
    "=== CARDORYX DEEP RETAIL AUDIT ==="
)

print(
    json.dumps(
        {
            "implementedAdapters": (
                report[
                    "implementedAdapters"
                ]
            ),
            "pendingAdapters": (
                report[
                    "pendingAdapters"
                ]
            ),
            "cardPassionStats": (
                source_reports[0][
                    "stats"
                ]
            ),
            "gsGameonStats": (
                source_reports[1][
                    "stats"
                ]
            ),
            "warcardStats": (
                source_reports[2][
                    "stats"
                ]
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
)

print(
    f"Report: {REPORT}"
)
