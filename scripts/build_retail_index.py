#!/usr/bin/env python3

import html
import json
import re
import statistics
import unicodedata
import urllib.parse
import urllib.request

from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CARDORYX — RETAIL PRICE INDEX BUILDER
# ============================================================
#
# Retail V1.2
#
# Fonte:
# - Card Passion
#
# PRINCIPI:
#
# - completamente separato da Cardmarket
# - nessun prezzo inventato
# - fail closed
# - lingua verificata
# - condizione verificata
# - variante verificata
# - una fonte non basta per statistiche affidabili
#
# ============================================================


SCHEMA_VERSION = 1

MIN_OFFERS_FOR_STATS = 3
MIN_STORES_FOR_STATS = 3

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
    "(compatible; CardoryxRetailIndex/1.2; "
    "+https://github.com/)"
)


def http_get_json(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT,
    ) as response:

        raw = response.read()

    return json.loads(
        raw.decode("utf-8")
    )


# ============================================================
# TESTO
# ============================================================

def strip_html(value):

    text = str(
        value or ""
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def norm(value):

    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    text = (
        text
        .encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
        .lower()
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    ).strip()


def norm_number(value):

    return (
        str(value or "")
        .strip()
        .upper()
        .replace(" ", "")
    )


def make_key(
    set_name,
    number,
    variant,
    language,
    condition,
):

    return "|".join(
        [
            norm(set_name),
            norm_number(number).lower(),
            norm(variant),
            norm(language),
            norm(condition),
        ]
    )


# ============================================================
# PAROLE / FRASI
# ============================================================

def phrase_in_text(
    phrase,
    text,
):

    phrase_normalized = norm(
        phrase
    )

    text_normalized = norm(
        text
    )

    if not phrase_normalized:
        return False

    pattern = (
        r"(?:^|\s)"
        + re.escape(
            phrase_normalized
        )
        + r"(?:$|\s)"
    )

    return bool(
        re.search(
            pattern,
            text_normalized,
        )
    )


def contains_any_phrase(
    text,
    phrases,
):

    return any(
        phrase_in_text(
            phrase,
            text,
        )
        for phrase in phrases
    )


# ============================================================
# PREZZI
# ============================================================

def valid_price(value):

    try:

        price = float(
            value
        )

        return (
            price > 0
            and price < 100000
        )

    except Exception:

        return False


# ============================================================
# LINGUA
# ============================================================

FOREIGN_LANGUAGE_MARKERS = [

    "lingua inglese",
    "lingua giapponese",
    "lingua cinese",
    "lingua coreana",
    "lingua francese",
    "lingua tedesca",
    "lingua spagnola",

    "english language",
    "japanese language",
    "chinese language",
    "korean language",
    "french language",
    "german language",
    "spanish language",

    "japanese",
    "japan",
    "giapponese",
    "inglese",
    "cinese",
    "coreano",

    "jpn",
    "jap",
    "eng",
    "kor",
]


ITALIAN_LANGUAGE_MARKERS = [

    "lingua italiana",
    "lingua italiano",
    "lingua ita",
    "italiano",
    "italiana",
    "italian language",
]


# Set/prodotti notoriamente non italiani che erano entrati
# erroneamente nel primo test.
#
# Questa è una protezione aggiuntiva.
# La lingua deve comunque essere verificata.

FOREIGN_SET_MARKERS = [

    "blue sky stream",
    "matchless fighter",
    "silver lance",
    "jet black spirit",
    "eevee heroes",
    "vmax climax",
    "vstar universe",
    "shiny star v",
    "dark phantasma",
    "lost abyss",
    "paradigm trigger",
    "incandescent arcana",
    "space juggler",
    "time gazer",
    "battle region",
    "star birth",
    "fusion arts",
    "towering perfection",
]


def detect_language(
    title,
    body,
    tags,
    set_name,
):

    combined = " ".join(
        [
            str(title or ""),
            str(body or ""),
            str(tags or ""),
        ]
    )

    # --------------------------------------------------------
    # Prima escludiamo segnali espliciti di lingua straniera.
    # --------------------------------------------------------

    if contains_any_phrase(
        combined,
        FOREIGN_LANGUAGE_MARKERS,
    ):
        return None

    if contains_any_phrase(
        set_name,
        FOREIGN_SET_MARKERS,
    ):
        return None

    # --------------------------------------------------------
    # Accettiamo IT solo con indicazione verificabile.
    # --------------------------------------------------------

    if contains_any_phrase(
        combined,
        ITALIAN_LANGUAGE_MARKERS,
    ):
        return "IT"

    # --------------------------------------------------------
    # FAIL CLOSED
    #
    # Nessuna indicazione sufficiente sulla lingua.
    # --------------------------------------------------------

    return None


# ============================================================
# CONDIZIONE
# ============================================================

BAD_CONDITION_MARKERS = [

    "played",
    "light played",
    "lightly played",
    "moderately played",
    "heavily played",
    "excellent",
    "good",
    "poor",
    "damaged",
    "danneggiata",
    "danneggiato",
]


NM_MINT_MARKERS = [

    "near mint",
    "near-mint",
    "nm",
    "mint",
    "pack fresh",
    "pack-fresh",
]


def detect_condition(
    title,
    body,
    tags,
):

    combined = " ".join(
        [
            str(title or ""),
            str(body or ""),
            str(tags or ""),
        ]
    )

    # --------------------------------------------------------
    # Una condizione inferiore a NM/Mint viene esclusa.
    # --------------------------------------------------------

    if contains_any_phrase(
        combined,
        BAD_CONDITION_MARKERS,
    ):
        return None

    # --------------------------------------------------------
    # NM e Mint vengono raccolte nello stesso bucket retail.
    # --------------------------------------------------------

    if contains_any_phrase(
        combined,
        NM_MINT_MARKERS,
    ):
        return "NM/MINT"

    # --------------------------------------------------------
    # FAIL CLOSED
    # --------------------------------------------------------

    return None


# ============================================================
# PRODOTTI DA ESCLUDERE
# ============================================================

GRADED_MARKERS = [

    "psa",
    "bgs",
    "cgc",
    "graad",
    "ace grading",
    "graded",
    "gradato",
    "gradata",
    "gradate",
]


SEALED_MARKERS = [

    "display",
    "booster box",
    "collection box",
    "premium collection",
    "elite trainer box",
    "etb",
    "blister",
    "bundle",
    "bustina",
    "bustine",
    "mini tin",
    "tin box",
    "mazzo precostruito",
    "mystery box",
]


def is_excluded_product(
    title,
    body,
    tags,
):

    combined = " ".join(
        [
            str(title or ""),
            str(body or ""),
            str(tags or ""),
        ]
    )

    if contains_any_phrase(
        combined,
        GRADED_MARKERS,
    ):
        return True

    if contains_any_phrase(
        combined,
        SEALED_MARKERS,
    ):
        return True

    return False


# ============================================================
# NUMERO CARTA + TITOLO CARD PASSION
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


# ============================================================
# VARIANTI
# ============================================================

def detect_variant(card_text):

    text = norm(
        card_text
    )

    # --------------------------------------------------------
    # IMPORTANTISSIMO:
    #
    # Non-Holo deve essere verificata PRIMA di Holo.
    # --------------------------------------------------------

    if (
        "non holo" in text
        or "nonholo" in text
    ):
        return "Normal"

    # --------------------------------------------------------
    # Varianti Reverse speciali.
    # --------------------------------------------------------

    if (
        "master ball reverse holo" in text
        or "master ball reverse" in text
        or "masterball reverse holo" in text
        or "masterball reverse" in text
    ):
        return "Master Ball Reverse Holo"

    if (
        "poke ball reverse holo" in text
        or "poke ball reverse" in text
        or "pokeball reverse holo" in text
        or "pokeball reverse" in text
    ):
        return "Poké Ball Reverse Holo"

    if (
        "energy reverse holo" in text
        or "energy reverse" in text
        or "energia reverse holo" in text
        or "energia reverse" in text
    ):
        return "Energy Reverse Holo"

    # --------------------------------------------------------
    # Cosmo Holo distinta dalla Holo normale.
    # --------------------------------------------------------

    if (
        "cosmo holo" in text
        or "cosmos holo" in text
    ):
        return "Cosmo Holo"

    # --------------------------------------------------------
    # Reverse standard.
    # --------------------------------------------------------

    if "reverse" in text:
        return "Reverse Holo"

    # --------------------------------------------------------
    # Varianti artistiche / rarità speciali.
    # --------------------------------------------------------

    if (
        "special illustration rare" in text
        or "illustrazione rara speciale" in text
    ):
        return "Special Illustration Rare"

    if (
        "illustration rare" in text
        or "illustrazione rara" in text
    ):
        return "Illustration Rare"

    if (
        "alternate art" in text
        or "alternative art" in text
        or "alternate artwork" in text
    ):
        return "Alternative Art"

    if (
        "full art" in text
        or "fullart" in text
    ):
        return "Full Art"

    if (
        "secret rare" in text
        or "rara segreta" in text
    ):
        return "Secret Rare"

    if (
        "hyper rare" in text
        or "hyperrare" in text
    ):
        return "Hyper Rare"

    if (
        "shiny rare" in text
        or "shiny" in text
    ):
        return "Shiny"

    if (
        "radiant" in text
        or "lucente" in text
    ):
        return "Radiant"

    if "gold" in text:
        return "Gold"

    # --------------------------------------------------------
    # Holo standard.
    # --------------------------------------------------------

    if "holo" in text:
        return "Holo"

    # --------------------------------------------------------
    # Se non esiste alcuna indicazione di finitura speciale,
    # trattiamo la carta come Normal.
    #
    # V / VMAX / VSTAR / EX / GX non sono finiture.
    # --------------------------------------------------------

    special_finish_markers = [

        "reverse",
        "holo",
        "shiny",
        "radiant",
        "lucente",
        "full art",
        "fullart",
        "illustration",
        "illustrazione",
        "alternate",
        "alternative",
        "secret",
        "segreta",
        "hyper rare",
        "hyperrare",
        "gold",
        "master ball",
        "masterball",
        "poke ball",
        "pokeball",
        "energy reverse",
        "energia reverse",
    ]

    if not any(
        marker in text
        for marker in special_finish_markers
    ):
        return "Normal"

    # --------------------------------------------------------
    # FAIL CLOSED
    # --------------------------------------------------------

    return None


# ============================================================
# PULIZIA NOME CARTA
# ============================================================

VARIANT_REMOVALS = [

    "Master Ball Reverse Holo",
    "Master Ball Reverse",
    "Masterball Reverse Holo",
    "Masterball Reverse",

    "Poké Ball Reverse Holo",
    "Poke Ball Reverse Holo",
    "Poké Ball Reverse",
    "Poke Ball Reverse",
    "Pokeball Reverse Holo",
    "Pokeball Reverse",

    "Energy Reverse Holo",
    "Energy Reverse",
    "Energia Reverse Holo",
    "Energia Reverse",

    "Cosmos Holo",
    "Cosmo Holo",

    "Non-Holo",
    "Non Holo",

    "Reverse Holo",
    "Reverse",

    "Special Illustration Rare",
    "Illustrazione Rara Speciale",

    "Illustration Rare",
    "Illustrazione Rara",

    "Alternative Art",
    "Alternate Art",
    "Alternate Artwork",

    "Full Art",

    "Secret Rare",
    "Rara Segreta",

    "Hyper Rare",

    "Shiny Rare",
    "Shiny",

    "Radiant",
    "Lucente",

    "Holo",
]


RARITY_REMOVALS = [

    "Non Comune",
    "Comune",
    "Rara",
    "Rare",
    "Uncommon",
    "Common",
]


def remove_whole_phrase(
    text,
    phrase,
):

    # --------------------------------------------------------
    # Evita il vecchio problema:
    #
    # "Gold" non deve rimuovere "Gold" da "Golduck".
    #
    # La frase viene rimossa solo se costituisce una parola
    # o sequenza di parole completa.
    # --------------------------------------------------------

    pattern = (
        r"(?<!\w)"
        + re.escape(
            phrase
        )
        + r"(?!\w)"
    )

    return re.sub(
        pattern,
        " ",
        text,
        flags=re.IGNORECASE,
    )


def clean_card_name(
    card_text,
):

    text = str(
        card_text or ""
    ).strip()

    # --------------------------------------------------------
    # Prima rimuoviamo le varianti più lunghe.
    # --------------------------------------------------------

    removals = sorted(
        VARIANT_REMOVALS,
        key=len,
        reverse=True,
    )

    for phrase in removals:

        text = remove_whole_phrase(
            text,
            phrase,
        )

    # --------------------------------------------------------
    # Rimuoviamo rarità descrittive che non fanno parte
    # dell'identità della carta.
    # --------------------------------------------------------

    rarity_removals = sorted(
        RARITY_REMOVALS,
        key=len,
        reverse=True,
    )

    for phrase in rarity_removals:

        text = remove_whole_phrase(
            text,
            phrase,
        )

    # --------------------------------------------------------
    # Pulizia finale.
    # --------------------------------------------------------

    text = re.sub(
        r"\(\s*\)",
        " ",
        text,
    )

    text = re.sub(
        r"\[\s*\]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = text.strip(
        " -–—|/"
    )

    return text.strip()


# ============================================================
# PARSER TITOLO
# ============================================================

def parse_cardpassion_title(
    title,
):

    title = str(
        title or ""
    ).strip()

    if not title:
        return None

    match = NUMBER_RE.match(
        title
    )

    if not match:
        return None

    number = norm_number(
        match.group(1)
    )

    card_text = (
        match.group(2)
        .strip()
    )

    set_name = (
        match.group(3)
        .strip()
    )

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
        card_text
    )

    if not card_name:
        return None

    return {
        "number": number,
        "name": card_name,
        "set": set_name,
        "variant": variant,
    }


# ============================================================
# PREZZO SHOPIFY
# ============================================================

def extract_variant_price(
    product,
):

    variants = product.get(
        "variants"
    )

    if not isinstance(
        variants,
        list,
    ):
        return None

    prices = []

    for variant in variants:

        if not isinstance(
            variant,
            dict,
        ):
            continue

        # ----------------------------------------------------
        # Deve essere acquistabile.
        # ----------------------------------------------------

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

        prices.append(
            round(
                float(price),
                2,
            )
        )

    if not prices:
        return None

    unique_prices = sorted(
        set(prices)
    )

    # --------------------------------------------------------
    # Più prezzi diversi nello stesso prodotto:
    # identità ambigua -> esclusione.
    # --------------------------------------------------------

    if len(
        unique_prices
    ) != 1:

        return None

    return unique_prices[0]


# ============================================================
# OFFERTE
# ============================================================

def normalize_offer(
    offer,
):

    if not isinstance(
        offer,
        dict,
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

    if language != "IT":
        return None

    if condition != "NM/MINT":
        return None

    if not variant:
        return None

    return {

        "store":
            store,

        "price":
            round(
                float(price),
                2,
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
            ).strip(),
    }


# ============================================================
# AGGIUNTA OFFERTA
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
    offer,
):

    key = make_key(
        set_name,
        number,
        variant,
        language,
        condition,
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
                [],
        }

    existing = cards[
        key
    ]["offers"]

    # --------------------------------------------------------
    # Una singola fonte deve contribuire al massimo
    # UNA offerta alla stessa identità fisica.
    #
    # Se Card Passion ha due schede apparentemente riferite
    # alla stessa identità, la seconda non aumenta il campione.
    # --------------------------------------------------------

    same_store = any(

        norm(
            item.get("store")
        )
        == norm(
            cleaned_offer.get("store")
        )

        for item in existing
    )

    if same_store:
        return False

    existing.append(
        cleaned_offer
    )

    return True


# ============================================================
# STATISTICHE
# ============================================================

def calculate_stats(
    offers,
):

    valid_offers = [

        offer

        for offer in offers

        if valid_price(
            offer.get("price")
        )
    ]

    prices = [

        offer["price"]

        for offer in valid_offers
    ]

    stores = {

        norm(
            offer.get("store")
        )

        for offer in valid_offers

        if offer.get("store")
    }

    reliable = (

        len(
            prices
        )
        >= MIN_OFFERS_FOR_STATS

        and

        len(
            stores
        )
        >= MIN_STORES_FOR_STATS
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
                None,
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
                2,
            ),

        "max":
            round(
                max(prices),
                2,
            ),

        "median":
            round(
                statistics.median(
                    prices
                ),
                2,
            ),
    }


# ============================================================
# CARD PASSION — CATALOGO
# ============================================================

def get_cardpassion_products():

    products_all = []

    page = 1

    while True:

        query = urllib.parse.urlencode(
            {
                "limit":
                    CARDPASSION_PAGE_LIMIT,

                "page":
                    page,
            }
        )

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
            list,
        ):

            raise RuntimeError(
                "Risposta Card Passion non valida: "
                "campo products mancante"
            )

        if not products:
            break

        products_all.extend(
            products
        )

        if len(
            products
        ) < CARDPASSION_PAGE_LIMIT:

            break

        page += 1

        if page > 100:

            raise RuntimeError(
                "Numero pagine Card Passion anomalo"
            )

    return products_all


# ============================================================
# CARD PASSION — RACCOLTA
# ============================================================

def collect_cardpassion(
    cards,
):

    print()
    print(
        "=== CARD PASSION ==="
    )

    products = get_cardpassion_products()

    print(
        "Prodotti ricevuti:",
        len(products),
    )

    checked_at = (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )

    counters = {

        "accepted": 0,
        "excludedProduct": 0,
        "invalidTitle": 0,
        "languageUnknown": 0,
        "conditionUnknown": 0,
        "priceUnavailable": 0,
        "duplicateStore": 0,
    }

    for product in products:

        if not isinstance(
            product,
            dict,
        ):
            continue

        title = str(
            product.get("title")
            or ""
        ).strip()

        handle = str(
            product.get("handle")
            or ""
        ).strip()

        body = strip_html(
            product.get(
                "body_html"
            )
        )

        tags = product.get(
            "tags"
        )

        if isinstance(
            tags,
            list,
        ):

            tags_text = " ".join(
                str(tag)
                for tag in tags
            )

        else:

            tags_text = str(
                tags or ""
            )

        if not title:
            counters[
                "invalidTitle"
            ] += 1
            continue

        if not handle:
            counters[
                "invalidTitle"
            ] += 1
            continue

        # ----------------------------------------------------
        # Gradate, sealed ecc.
        # ----------------------------------------------------

        if is_excluded_product(
            title,
            body,
            tags_text,
        ):
            counters[
                "excludedProduct"
            ] += 1
            continue

        # ----------------------------------------------------
        # Identità dal titolo.
        # ----------------------------------------------------

        parsed = parse_cardpassion_title(
            title
        )

        if not parsed:

            counters[
                "invalidTitle"
            ] += 1

            continue

        # ----------------------------------------------------
        # Lingua.
        # ----------------------------------------------------

        language = detect_language(
            title,
            body,
            tags_text,
            parsed["set"],
        )

        if language != "IT":

            counters[
                "languageUnknown"
            ] += 1

            continue

        # ----------------------------------------------------
        # Condizione.
        # ----------------------------------------------------

        condition = detect_condition(
            title,
            body,
            tags_text,
        )

        if condition != "NM/MINT":

            counters[
                "conditionUnknown"
            ] += 1

            continue

        # ----------------------------------------------------
        # Prezzo.
        # ----------------------------------------------------

        price = extract_variant_price(
            product
        )

        if price is None:

            counters[
                "priceUnavailable"
            ] += 1

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
                language,

            condition=
                condition,

            offer={

                "store":
                    "Card Passion",

                "price":
                    price,

                "url":
                    product_url,

                "language":
                    language,

                "condition":
                    condition,

                "variant":
                    parsed["variant"],

                "checkedAt":
                    checked_at,

                "sourceType":
                    "retail-store",
            },
        )

        if added:

            counters[
                "accepted"
            ] += 1

        else:

            counters[
                "duplicateStore"
            ] += 1

    print()
    print(
        "Risultato Card Passion:"
    )

    print(
        json.dumps(
            counters,
            indent=2,
            ensure_ascii=False,
        )
    )

    # --------------------------------------------------------
    # Se la fonte improvvisamente non produce più
    # nessuna carta verificata, NON sovrascriviamo
    # l'indice precedente.
    # --------------------------------------------------------

    if counters[
        "accepted"
    ] == 0:

        raise RuntimeError(
            "Card Passion non ha prodotto "
            "nessuna offerta retail verificata. "
            "Il file precedente NON verrà sovrascritto."
        )

    return {

        "source":
            "Card Passion",

        "products":
            len(products),

        "accepted":
            counters[
                "accepted"
            ],

        "excludedProduct":
            counters[
                "excludedProduct"
            ],

        "invalidTitle":
            counters[
                "invalidTitle"
            ],

        "languageUnknown":
            counters[
                "languageUnknown"
            ],

        "conditionUnknown":
            counters[
                "conditionUnknown"
            ],

        "priceUnavailable":
            counters[
                "priceUnavailable"
            ],

        "duplicateStore":
            counters[
                "duplicateStore"
            ],

        "ok":
            True,
    }


# ============================================================
# FINALIZZAZIONE
# ============================================================

def finalize_cards(
    cards,
):

    for card in cards.values():

        offers = card.get(
            "offers",
            [],
        )

        card[
            "stats"
        ] = calculate_stats(
            offers
        )

        dates = [

            offer.get(
                "checkedAt"
            )

            for offer in offers

            if offer.get(
                "checkedAt"
            )
        ]

        card[
            "updatedAt"
        ] = (
            max(dates)
            if dates
            else None
        )


# ============================================================
# RACCOLTA RETAIL
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
    # FUTURE FONTI
    # ========================================================
    #
    # collect_cartemagic(cards)
    # collect_altro_negozio(cards)
    #
    # Ogni fonte:
    #
    # - deve verificare variante
    # - deve verificare lingua
    # - deve verificare condizione
    # - deve usare add_offer()
    #
    # ========================================================

    finalize_cards(
        cards
    )

    return (
        cards,
        source_stats,
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

    generated = (
        datetime.now(
            timezone.utc
        )
        .isoformat(
            timespec="seconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )

    reliable_cards = sum(

        1

        for card in cards.values()

        if card.get(
            "stats",
            {},
        ).get(
            "reliable"
        )
    )

    total_offers = sum(

        len(
            card.get(
                "offers",
                [],
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
                MIN_STORES_FOR_STATS,

            "currency":
                "EUR",

            "language":
                "IT",

            "preferredCondition":
                "NM/MINT",

            "cardmarketExcluded":
                True,

            "failClosed":
                True,
        },

        "sources":
            source_stats,

        "stats": {

            "cards":
                len(cards),

            "reliableCards":
                reliable_cards,

            "offers":
                total_offers,
        },

        "cards":
            cards,
    }

    # ========================================================
    # SICUREZZA
    # ========================================================

    if not cards:

        raise RuntimeError(
            "Indice retail vuoto: "
            "il file precedente NON verrà sovrascritto."
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_FILE.write_text(

        json.dumps(
            out,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        ),

        encoding="utf-8",
    )

    print()
    print(
        "Statistiche indice:"
    )

    print(
        json.dumps(
            out["stats"],
            indent=2,
            ensure_ascii=False,
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
            ensure_ascii=False,
        )
    )

    print()
    print(
        "File creato:",
        OUTPUT_FILE,
    )

    print(
        "Aggiornato:",
        generated,
    )

    print()
    print(
        "=== FINE ==="
    )


if __name__ == "__main__":
    main()
