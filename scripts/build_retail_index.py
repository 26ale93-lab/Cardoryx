#!/usr/bin/env python3

import json
import re
import statistics
import unicodedata
import urllib.request
import urllib.parse

from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CARDORYX — RETAIL PRICE INDEX BUILDER
# ============================================================
#
# VERSIONE RETAIL V1
#
# Fonte iniziale:
# - Card Passion
#
# IMPORTANTE:
#
# Questo indice è COMPLETAMENTE SEPARATO da Cardmarket.
#
# NON modifica:
# - data/cardmarket_play_index.json
# - scripts/build_play_index.py
# - il valore totale della collezione
#
# Il retail serve esclusivamente come riferimento informativo.
# ============================================================


SCHEMA_VERSION = 1

MIN_OFFERS_FOR_STATS = 3

OUTPUT_FILE = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "data"
    / "retail_prices.json"
)

CARDPASSION_BASE_URL = "https://cardpassion.it"

CARDPASSION_COLLECTION = "pokemon"

CARDPASSION_PAGE_LIMIT = 250

HTTP_TIMEOUT = 30


# ============================================================
# HTTP
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; CardoryxRetailIndex/1.0; "
    "+https://github.com/)"
)


def http_get_json(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT
    ) as response:

        raw = response.read()

    return json.loads(
        raw.decode("utf-8")
    )


# ============================================================
# NORMALIZZAZIONE
# ============================================================

def norm(value):

    text = unicodedata.normalize(
        "NFKD",
        str(value or "")
    )

    text = (
        text
        .encode(
            "ascii",
            "ignore"
        )
        .decode("ascii")
        .lower()
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    ).strip()


def norm_number(value):

    return str(
        value or ""
    ).strip().upper()


def make_key(
    set_name,
    number,
    variant,
    language,
    condition
):

    return "|".join([
        norm(set_name),
        norm_number(number).lower(),
        norm(variant),
        norm(language),
        norm(condition)
    ])


# ============================================================
# PREZZI
# ============================================================

def valid_price(value):

    try:

        price = float(value)

        return (
            price > 0
            and price < 100000
        )

    except Exception:

        return False


# ============================================================
# OFFERTE
# ============================================================

def normalize_offer(offer):

    if not isinstance(
        offer,
        dict
    ):
        return None

    store = str(
        offer.get("store")
        or ""
    ).strip()

    url = str(
        offer.get("url")
        or ""
    ).strip()

    language = str(
        offer.get("language")
        or ""
    ).strip().upper()

    condition = str(
        offer.get("condition")
        or ""
    ).strip().upper()

    variant = str(
        offer.get("variant")
        or ""
    ).strip()

    price = offer.get(
        "price"
    )

    if not store:
        return None

    if not url:
        return None

    if not valid_price(
        price
    ):
        return None

    if not language:
        return None

    if not condition:
        return None

    if not variant:
        return None

    return {

        "store":
            store,

        "price":
            round(
                float(price),
                2
            ),

        "url":
            url,

        "language":
            language,

        "condition":
            condition,

        "variant":
            variant,

        "checkedAt":
            str(
                offer.get("checkedAt")
                or ""
            ).strip(),

        "sourceType":
            str(
                offer.get("sourceType")
                or "retail-store"
            ).strip()
    }


# ============================================================
# STATISTICHE
# ============================================================

def calculate_stats(offers):

    prices = [

        offer["price"]

        for offer in offers

        if valid_price(
            offer.get("price")
        )
    ]

    stores = {

        norm(
            offer.get("store")
        )

        for offer in offers

        if offer.get("store")
    }

    # ========================================================
    # Servono almeno 3 OFFERTE e almeno 3 FONTI indipendenti.
    #
    # Questo impedisce che più varianti/prezzi dello stesso
    # negozio vengano interpretati come mercato affidabile.
    # ========================================================

    reliable = (
        len(prices) >= MIN_OFFERS_FOR_STATS
        and len(stores) >= MIN_OFFERS_FOR_STATS
    )

    if not reliable:

        return {

            "reliable":
                False,

            "count":
                len(prices),

            "stores":
                len(stores),

            "min":
                None,

            "max":
                None,

            "median":
                None
        }

    return {

        "reliable":
            True,

        "count":
            len(prices),

        "stores":
            len(stores),

        "min":
            round(
                min(prices),
                2
            ),

        "max":
            round(
                max(prices),
                2
            ),

        "median":
            round(
                statistics.median(
                    prices
                ),
                2
            )
    }


# ============================================================
# AGGIUNTA OFFERTA A CARTA
# ============================================================

def add_offer(
    cards,
    *,
    set_name,
    number,
    card_name,
    variant,
    language,
    condition,
    offer
):

    key = make_key(
        set_name,
        number,
        variant,
        language,
        condition
    )

    cleaned_offer = normalize_offer(
        offer
    )

    if not cleaned_offer:
        return False

    if key not in cards:

        cards[key] = {

            "set":
                set_name,

            "number":
                norm_number(
                    number
                ),

            "name":
                card_name,

            "variant":
                variant,

            "language":
                language.upper(),

            "condition":
                condition.upper(),

            "offers":
                []
        }

    existing = cards[
        key
    ]["offers"]

    # Evita duplicati identici della stessa fonte.

    duplicate = any(

        norm(x.get("store"))
        == norm(
            cleaned_offer.get("store")
        )

        and

        x.get("url")
        == cleaned_offer.get("url")

        for x in existing
    )

    if duplicate:
        return False

    existing.append(
        cleaned_offer
    )

    return True


# ============================================================
# CARD PASSION — FILTRI
# ============================================================

GRADED_WORDS = [

    "psa",
    "bgs",
    "cgc",
    "graad",
    "ace grading",
    "graded",
    "gradate",
    "gradato",
    "gradated"
]


SEALED_WORDS = [

    "box",
    "display",
    "blister",
    "bundle",
    "bustina",
    "bustine",
    "tin",
    "mini tin",
    "mazzo",
    "collezione",
    "etb",
    "set allenatore",
    "premium collection",
    "collection box",
    "mystery"
]


FOREIGN_LANGUAGE_WORDS = [

    "(jp)",
    "(jpn)",
    "(en)",
    "(eng)",
    "(cn)",
    "(kr)",
    "(kor)",
    "giapponese",
    "inglese",
    "cinese",
    "coreano"
]


BAD_CONDITION_WORDS = [

    "played",
    "excellent",
    "good",
    "poor",
    "damaged",
    "light played",
    "moderately played",
    "heavily played"
]


def contains_any(text, words):

    normalized = norm(
        text
    )

    for word in words:

        if norm(word) in normalized:
            return True

    return False


# ============================================================
# CARD PASSION — PARSING TITOLO
# ============================================================

NUMBER_RE = re.compile(
    r"^\s*"
    r"([A-Za-z]*\d+[A-Za-z]*"
    r"(?:\s*/\s*[A-Za-z]*\d+[A-Za-z]*)?)"
    r"\s+"
    r"(.+?)"
    r"\s*\|\s*"
    r"(.+?)"
    r"\s*$"
)


def detect_variant(card_text):

    text = norm(
        card_text
    )

    # Ordine importante:
    # le varianti più specifiche devono venire prima.

    if (
        "master ball reverse" in text
        or "masterball reverse" in text
    ):
        return "Master Ball Reverse"

    if (
        "poke ball reverse" in text
        or "pokeball reverse" in text
    ):
        return "Poké Ball Reverse"

    if (
        "energy reverse" in text
        or "energia reverse" in text
    ):
        return "Energy Reverse"

    if "reverse" in text:
        return "Reverse Holo"

    if "holo" in text:
        return "Holo"

    if "shiny" in text:
        return "Shiny"

    if "illustrazione rara speciale" in text:
        return "Special Illustration Rare"

    if (
        "special illustration rare" in text
        or "sar" in text
    ):
        return "Special Illustration Rare"

    if (
        "illustrazione rara" in text
        or "illustration rare" in text
    ):
        return "Illustration Rare"

    if (
        "full art" in text
        or "(fa)" in text
        or text.endswith(" fa")
    ):
        return "Full Art"

    if (
        "alternative art" in text
        or "alternate art" in text
    ):
        return "Alternative Art"

    if "gold" in text:
        return "Gold"

    if (
        "rara segreta" in text
        or "secret rare" in text
    ):
        return "Secret Rare"

    if "lucente" in text:
        return "Radiant"

    # ========================================================
    # VARIANTE NORMALE
    #
    # Solo se NON c'è alcun indicatore speciale.
    # ========================================================

    special_markers = [
        "reverse",
        "holo",
        "shiny",
        "illustrazione",
        "illustration",
        "full art",
        "alternative",
        "alternate",
        "gold",
        "segreta",
        "secret",
        "lucente",
        "promo",
        "vmax",
        "vstar",
        " ex",
        " gx",
        " v "
    ]

    if not any(
        marker in text
        for marker in special_markers
    ):
        return "Normal"

    # ========================================================
    # FAIL CLOSED
    #
    # Se il titolo suggerisce una carta speciale ma non siamo
    # in grado di classificare la variante con sicurezza,
    # la carta viene ignorata.
    # ========================================================

    return None


def clean_card_name(
    card_text,
    variant
):

    text = str(
        card_text
    ).strip()

    removals = [

        "Master Ball Reverse",
        "Masterball Reverse",
        "Poke Ball Reverse",
        "Poké Ball Reverse",
        "Pokeball Reverse",
        "Energy Reverse",
        "Energia Reverse",
        "Reverse",
        "Holo",
        "Shiny",
        "Illustrazione Rara Speciale",
        "Illustrazione Rara",
        "Special Illustration Rare",
        "Illustration Rare",
        "Alternative Art",
        "Alternate Art",
        "Full Art",
        "Gold",
        "Rara Segreta",
        "Secret Rare",
        "Lucente"
    ]

    for word in removals:

        text = re.sub(
            re.escape(word),
            "",
            text,
            flags=re.IGNORECASE
        )

    # rimuove eventuali parentesi vuote

    text = re.sub(
        r"\(\s*\)",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def parse_cardpassion_title(title):

    title = str(
        title or ""
    ).strip()

    if not title:
        return None

    # Esclusione prodotti gradati.

    if contains_any(
        title,
        GRADED_WORDS
    ):
        return None

    # Esclusione prodotti sealed.

    if contains_any(
        title,
        SEALED_WORDS
    ):
        return None

    # Esclusione lingue non italiane.

    if contains_any(
        title,
        FOREIGN_LANGUAGE_WORDS
    ):
        return None

    # Esclusione condizioni inferiori a NM/Mint.

    if contains_any(
        title,
        BAD_CONDITION_WORDS
    ):
        return None

    match = NUMBER_RE.match(
        title
    )

    if not match:
        return None

    number = match.group(
        1
    ).replace(
        " ",
        ""
    ).upper()

    card_text = match.group(
        2
    ).strip()

    set_name = match.group(
        3
    ).strip()

    if not number:
        return None

    if not card_text:
        return None

    if not set_name:
        return None

    variant = detect_variant(
        card_text
    )

    if not variant:
        return None

    card_name = clean_card_name(
        card_text,
        variant
    )

    if not card_name:
        return None

    return {

        "number":
            number,

        "name":
            card_name,

        "set":
            set_name,

        "variant":
            variant
    }


# ============================================================
# CARD PASSION — PREZZO
# ============================================================

def extract_variant_price(product):

    variants = product.get(
        "variants"
    )

    if not isinstance(
        variants,
        list
    ):
        return None

    available_prices = []

    for variant in variants:

        if not isinstance(
            variant,
            dict
        ):
            continue

        # Consideriamo solo prodotto acquistabile.
        #
        # Se Shopify non restituisce il campo available,
        # non usiamo automaticamente il prodotto.

        if variant.get(
            "available"
        ) is not True:
            continue

        price = variant.get(
            "price"
        )

        if not valid_price(
            price
        ):
            continue

        available_prices.append(
            float(price)
        )

    if not available_prices:
        return None

    # Per una carta singola ci aspettiamo normalmente
    # un solo prezzo.
    #
    # Se esistono più varianti Shopify con prezzi diversi,
    # non possiamo sapere quale corrisponde alla carta.

    unique_prices = sorted(
        set(
            round(
                p,
                2
            )
            for p in available_prices
        )
    )

    if len(
        unique_prices
    ) != 1:
        return None

    return unique_prices[0]


# ============================================================
# CARD PASSION — DOWNLOAD CATALOGO
# ============================================================

def get_cardpassion_products():

    all_products = []

    page = 1

    while True:

        query = urllib.parse.urlencode({
            "limit":
                CARDPASSION_PAGE_LIMIT,

            "page":
                page
        })

        url = (
            f"{CARDPASSION_BASE_URL}"
            f"/collections/"
            f"{CARDPASSION_COLLECTION}"
            f"/products.json?"
            f"{query}"
        )

        print(
            f"Card Passion pagina {page}..."
        )

        data = http_get_json(
            url
        )

        products = data.get(
            "products"
        )

        if not isinstance(
            products,
            list
        ):
            raise RuntimeError(
                "Risposta Card Passion non valida: "
                "campo products mancante"
            )

        if not products:
            break

        all_products.extend(
            products
        )

        if len(
            products
        ) < CARDPASSION_PAGE_LIMIT:
            break

        page += 1

        # Protezione contro loop imprevisti.

        if page > 100:
            raise RuntimeError(
                "Numero pagine Card Passion anomalo"
            )

    return all_products


# ============================================================
# CARD PASSION — RACCOLTA
# ============================================================

def collect_cardpassion(cards):

    print()
    print(
        "=== CARD PASSION ==="
    )

    products = get_cardpassion_products()

    print(
        "Prodotti ricevuti:",
        len(products)
    )

    accepted = 0
    rejected = 0

    checked_at = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )

    for product in products:

        if not isinstance(
            product,
            dict
        ):
            rejected += 1
            continue

        title = str(
            product.get("title")
            or ""
        ).strip()

        handle = str(
            product.get("handle")
            or ""
        ).strip()

        if not title:
            rejected += 1
            continue

        if not handle:
            rejected += 1
            continue

        parsed = parse_cardpassion_title(
            title
        )

        if not parsed:
            rejected += 1
            continue

        price = extract_variant_price(
            product
        )

        if price is None:
            rejected += 1
            continue

        product_url = (
            f"{CARDPASSION_BASE_URL}"
            f"/products/"
            f"{handle}"
        )

        added = add_offer(

            cards,

            set_name=
                parsed["set"],

            number=
                parsed["number"],

            card_name=
                parsed["name"],

            variant=
                parsed["variant"],

            language=
                "IT",

            condition=
                "NM",

            offer={

                "store":
                    "Card Passion",

                "price":
                    price,

                "url":
                    product_url,

                "language":
                    "IT",

                "condition":
                    "NM",

                "variant":
                    parsed["variant"],

                "checkedAt":
                    checked_at,

                "sourceType":
                    "retail-store"
            }
        )

        if added:
            accepted += 1
        else:
            rejected += 1

    print(
        "Carte accettate:",
        accepted
    )

    print(
        "Prodotti esclusi:",
        rejected
    )

    if accepted == 0:

        raise RuntimeError(
            "Card Passion non ha prodotto "
            "nessuna carta valida. "
            "Il formato della fonte potrebbe "
            "essere cambiato."
        )

    return {

        "source":
            "Card Passion",

        "products":
            len(products),

        "accepted":
            accepted,

        "rejected":
            rejected,

        "ok":
            True
    }


# ============================================================
# FINALIZZAZIONE CARTE
# ============================================================

def finalize_cards(cards):

    for card in cards.values():

        offers = card.get(
            "offers",
            []
        )

        card["stats"] = calculate_stats(
            offers
        )

        dates = [

            offer.get("checkedAt")

            for offer in offers

            if offer.get("checkedAt")
        ]

        card["updatedAt"] = (
            max(dates)
            if dates
            else None
        )


# ============================================================
# RACCOLTA GENERALE
# ============================================================

def collect_retail_data():

    cards = {}

    source_stats = []

    # ========================================================
    # FONTE 1 — CARD PASSION
    # ========================================================

    result = collect_cardpassion(
        cards
    )

    source_stats.append(
        result
    )

    # ========================================================
    # FONTI FUTURE
    # ========================================================
    #
    # collect_cartemagic(cards)
    # collect_bsa_store(cards)
    #
    # Ogni nuova fonte deve usare:
    #
    # add_offer(...)
    #
    # e rispettare le stesse regole fail-closed.
    # ========================================================

    finalize_cards(
        cards
    )

    return (
        cards,
        source_stats
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=== CARDORYX RETAIL INDEX BUILDER ==="
    )

    print()

    print(
        "Raccolta fonti retail..."
    )

    cards, source_stats = collect_retail_data()

    generated = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z"
    )

    reliable_cards = sum(

        1

        for card in cards.values()

        if card.get(
            "stats",
            {}
        ).get(
            "reliable"
        )
    )

    total_offers = sum(

        len(
            card.get(
                "offers",
                []
            )
        )

        for card in cards.values()
    )

    out = {

        "schema":
            SCHEMA_VERSION,

        "generatedAt":
            generated,

        "description":
            "Cardoryx Italian retail reference index",

        "rules": {

            "minimumOffersForStats":
                MIN_OFFERS_FOR_STATS,

            "minimumIndependentStoresForStats":
                MIN_OFFERS_FOR_STATS,

            "currency":
                "EUR",

            "language":
                "IT",

            "preferredCondition":
                "NM",

            "cardmarketExcluded":
                True,

            "failClosed":
                True
        },

        "sources":
            source_stats,

        "stats": {

            "cards":
                len(cards),

            "reliableCards":
                reliable_cards,

            "offers":
                total_offers
        },

        "cards":
            cards
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # SICUREZZA
    # ========================================================
    #
    # Con almeno una fonte configurata non accettiamo un
    # aggiornamento completamente vuoto.
    #
    # Questo evita che un problema temporaneo della fonte
    # cancelli l'indice retail valido.
    # ========================================================

    if not cards:

        raise RuntimeError(
            "Indice retail vuoto: "
            "il file precedente NON verrà sovrascritto."
        )

    OUTPUT_FILE.write_text(

        json.dumps(
            out,
            ensure_ascii=False,
            separators=(
                ",",
                ":"
            )
        ),

        encoding="utf-8"
    )

    print()

    print(
        json.dumps(
            out["stats"],
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print(
        "Fonti:"
    )

    print(
        json.dumps(
            source_stats,
            indent=2,
            ensure_ascii=False
        )
    )

    print()

    print(
        "File creato:",
        OUTPUT_FILE
    )

    print(
        "Aggiornato:",
        generated
    )

    print()

    print(
        "=== FINE ==="
    )


if __name__ == "__main__":

    main()
