#!/usr/bin/env python3

import html
import time
import json
import re
import statistics
import unicodedata
import urllib.parse
import urllib.request

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


# ============================================================
# CARDORYX — RETAIL PRICE INDEX BUILDER
# ============================================================
#
# Fonti:
# 1. Card Passion
# 2. CarteMagic
#
# REGOLE:
# - separato da Cardmarket
# - nessun prezzo inventato
# - lingua IT verificata
# - condizione NM/Mint
# - solo offerte acquistabili
# - fail closed
# - statistiche affidabili solo con >= 3 negozi indipendenti
#
# ============================================================


SCHEMA_VERSION = 1

MIN_OFFERS_FOR_STATS = 3
MIN_STORES_FOR_STATS = 3

ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FILE = ROOT / "data" / "retail_prices.json"

HTTP_TIMEOUT = 30


# ============================================================
# CARD PASSION
# ============================================================

CARDPASSION_BASE_URL = "https://cardpassion.it"
CARDPASSION_COLLECTION = "pokemon"
CARDPASSION_PAGE_LIMIT = 250


# ============================================================
# CARTEMAGIC
# ============================================================

CARTEMAGIC_BASE_URL = "https://www.cartemagic.com"
CARTEMAGIC_CATEGORY_URL = (
    "https://www.cartemagic.com/categoria/carte-pokemon/"
)

CARTEMAGIC_MAX_PAGES = 200


# ============================================================
# HTTP
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; CardoryxRetailIndex/1.2)"
)



def http_get(
    url,
    *,
    timeout=30,
    attempts=4,
    backoff_seconds=3,
):

    last_error = None

    for attempt in range(
        1,
        attempts + 1,
    ):

        try:

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent":
                        "Mozilla/5.0 "
                        "(Cardoryx Retail Index; "
                        "+https://github.com/)",
                    "Accept":
                        "text/html,application/xhtml+xml,"
                        "application/json;q=0.9,*/*;q=0.8",
                    "Accept-Language":
                        "it-IT,it;q=0.9,en;q=0.7",
                    "Connection":
                        "close",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:

                return response.read().decode(
                    "utf-8",
                    errors="replace",
                )

        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
        ) as exc:

            last_error = exc

            # 403/404 non sono errori transitori utili da ritentare.
            if isinstance(
                exc,
                urllib.error.HTTPError,
            ) and exc.code in {
                400,
                401,
                403,
                404,
            }:
                raise

            if attempt >= attempts:
                break

            wait = (
                backoff_seconds
                * attempt
            )

            print(
                f"Rete temporaneamente non disponibile "
                f"({attempt}/{attempts}) per {url}: "
                f"{exc}"
            )

            time.sleep(wait)

    if last_error:
        raise last_error

    raise RuntimeError(
        f"Impossibile leggere {url}"
    )


def http_get_json(url):

    return json.loads(
        http_get(url)
    )


# ============================================================
# TESTO
# ============================================================

def strip_html(value):

    text = str(value or "")

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(text)

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def norm(value):

    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    text = (
        text
        .encode("ascii", "ignore")
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


def phrase_in_text(
    phrase,
    text,
):

    phrase_normalized = norm(phrase)
    text_normalized = norm(text)

    if not phrase_normalized:
        return False

    pattern = (
        r"(?:^|\s)"
        + re.escape(phrase_normalized)
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

        price = float(value)

        return (
            price > 0
            and price < 100000
        )

    except Exception:

        return False


def parse_euro_price(value):

    text = strip_html(value)

    match = re.search(
        r"(\d{1,5}(?:[.,]\d{1,2})?)\s*€",
        text,
    )

    if not match:
        return None

    raw = (
        match.group(1)
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        value = float(raw)
    except Exception:
        return None

    if not valid_price(value):
        return None

    return round(
        value,
        2,
    )


# ============================================================
# SET
# ============================================================

def clean_set_name(value):

    text = str(value or "").strip()

    text = re.sub(
        r"\s*\(\s*copia\s*\)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


# ============================================================
# VARIANTI
# ============================================================

def detect_variant(card_text):

    text = norm(card_text)

    if (
        "non holo" in text
        or "nonholo" in text
    ):
        return "Normal"

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

    if (
        "cosmo holo" in text
        or "cosmos holo" in text
    ):
        return "Cosmo Holo"

    if "reverse" in text:
        return "Reverse Holo"

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

    if "holo" in text:
        return "Holo"

    return "Normal"


# ============================================================
# NOME CARTA
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

    pattern = (
        r"(?<!\w)"
        + re.escape(phrase)
        + r"(?!\w)"
    )

    return re.sub(
        pattern,
        " ",
        text,
        flags=re.IGNORECASE,
    )


def clean_card_name(card_text):

    text = str(card_text or "").strip()

    for phrase in sorted(
        VARIANT_REMOVALS,
        key=len,
        reverse=True,
    ):

        text = remove_whole_phrase(
            text,
            phrase,
        )

    for phrase in sorted(
        RARITY_REMOVALS,
        key=len,
        reverse=True,
    ):

        text = remove_whole_phrase(
            text,
            phrase,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip(
        " -–—|/"
    )


# ============================================================
# OFFERTE
# ============================================================

def normalize_offer(offer):

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

    price = offer.get("price")

    if not store:
        return None

    if not url:
        return None

    if not valid_price(price):
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

    set_name = clean_set_name(
        set_name
    )

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

    existing = cards[key]["offers"]

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

def calculate_stats(offers):

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

        len(prices)
        >= MIN_OFFERS_FOR_STATS

        and

        len(stores)
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
# CARD PASSION
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


def parse_cardpassion_title(title):

    title = str(
        title or ""
    ).strip()

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

    set_name = clean_set_name(
        match.group(3)
    )

    if not (
        number
        and card_text
        and set_name
    ):
        return None

    variant = detect_variant(
        card_text
    )

    card_name = clean_card_name(
        card_text
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
            variant,
    }


FOREIGN_LANGUAGE_MARKERS = [

    "lingua inglese",
    "lingua giapponese",
    "lingua cinese",
    "lingua coreana",
    "lingua francese",
    "lingua tedesca",
    "lingua spagnola",

    "japanese",
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


def cardpassion_language(
    title,
    body,
    tags,
    set_name,
):

    combined = " ".join(
        [
            title,
            body,
            tags,
        ]
    )

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

    if contains_any_phrase(
        combined,
        ITALIAN_LANGUAGE_MARKERS,
    ):
        return "IT"

    return None


def cardpassion_condition(
    title,
    body,
    tags,
):

    combined = " ".join(
        [
            title,
            body,
            tags,
        ]
    )

    if contains_any_phrase(
        combined,
        BAD_CONDITION_MARKERS,
    ):
        return None

    if contains_any_phrase(
        combined,
        NM_MINT_MARKERS,
    ):
        return "NM/MINT"

    return None


def cardpassion_excluded(
    title,
    body,
    tags,
):

    combined = " ".join(
        [
            title,
            body,
            tags,
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


def cardpassion_price(product):

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

        if variant.get(
            "available"
        ) is not True:
            continue

        price = variant.get(
            "price"
        )

        if valid_price(price):

            prices.append(
                round(
                    float(price),
                    2,
                )
            )

    prices = sorted(
        set(prices)
    )

    if len(prices) != 1:
        return None

    return prices[0]


def get_cardpassion_products():

    all_products = []

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
                "Card Passion: risposta non valida"
            )

        if not products:
            break

        all_products.extend(
            products
        )

        if (
            len(products)
            < CARDPASSION_PAGE_LIMIT
        ):
            break

        page += 1

        if page > 100:
            raise RuntimeError(
                "Card Passion: troppe pagine"
            )

    return all_products


def collect_cardpassion(cards):

    print()
    print(
        "=== CARD PASSION ==="
    )

    products = get_cardpassion_products()

    checked_at = utc_now()

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
            product.get("body_html")
        )

        tags = product.get(
            "tags"
        )

        if isinstance(
            tags,
            list,
        ):

            tags_text = " ".join(
                str(x)
                for x in tags
            )

        else:
            tags_text = str(
                tags or ""
            )

        if cardpassion_excluded(
            title,
            body,
            tags_text,
        ):

            counters[
                "excludedProduct"
            ] += 1
            continue

        parsed = parse_cardpassion_title(
            title
        )

        if not parsed:

            counters[
                "invalidTitle"
            ] += 1
            continue

        language = cardpassion_language(
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

        condition = cardpassion_condition(
            title,
            body,
            tags_text,
        )

        if condition != "NM/MINT":

            counters[
                "conditionUnknown"
            ] += 1
            continue

        price = cardpassion_price(
            product
        )

        if price is None:

            counters[
                "priceUnavailable"
            ] += 1
            continue

        url = (
            f"{CARDPASSION_BASE_URL}"
            f"/products/{handle}"
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
                "NM/MINT",

            offer={

                "store":
                    "Card Passion",

                "price":
                    price,

                "url":
                    url,

                "language":
                    "IT",

                "condition":
                    "NM/MINT",

                "variant":
                    parsed["variant"],

                "checkedAt":
                    checked_at,

                "sourceType":
                    "retail-store",
            },
        )

        if added:
            counters["accepted"] += 1
        else:
            counters["duplicateStore"] += 1

    if counters[
        "accepted"
    ] == 0:

        raise RuntimeError(
            "Card Passion non ha prodotto "
            "offerte verificate"
        )

    return {

        "source":
            "Card Passion",

        "products":
            len(products),

        **counters,

        "ok":
            True,
    }


# ============================================================
# CARTEMAGIC — HTML
# ============================================================

class LinkParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.links = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):

        if tag.lower() != "a":
            return

        attrs_dict = dict(
            attrs
        )

        href = attrs_dict.get(
            "href"
        )

        if href:
            self.links.append(
                href
            )


def extract_cartemagic_product_links(
    page_html,
):

    parser = LinkParser()

    parser.feed(
        page_html
    )

    links = set()

    for href in parser.links:

        href = html.unescape(
            href
        )

        absolute = urllib.parse.urljoin(
            CARTEMAGIC_BASE_URL,
            href,
        )

        if (
            absolute.startswith(
                f"{CARTEMAGIC_BASE_URL}/prodotto/"
            )
        ):

            links.add(
                absolute.split("#")[0]
            )

    return sorted(
        links
    )


def cartemagic_page_url(page):

    if page == 1:
        return CARTEMAGIC_CATEGORY_URL

    return (
        f"{CARTEMAGIC_CATEGORY_URL}"
        f"page/{page}/"
    )


def get_cartemagic_product_links():

    all_links = set()

    previous_count = 0

    for page in range(
        1,
        CARTEMAGIC_MAX_PAGES + 1,
    ):

        url = cartemagic_page_url(
            page
        )

        print(
            f"CarteMagic catalogo pagina {page}..."
        )

        page_html = http_get(
            url
        )

        links = extract_cartemagic_product_links(
            page_html
        )

        if not links:
            break

        all_links.update(
            links
        )

        if (
            page > 1
            and len(all_links)
            == previous_count
        ):
            break

        previous_count = len(
            all_links
        )

        if "pagina successiva" not in norm(
            page_html
        ):

            # Non usiamo questo come unica condizione:
            # alcuni temi WooCommerce non mostrano questa frase.
            pass

    return sorted(
        all_links
    )


# ============================================================
# CARTEMAGIC — PARSER PRODOTTO
# ============================================================

CARTEMAGIC_TITLE_RE = re.compile(
    r"<h1[^>]*>"
    r"(.*?)"
    r"</h1>",
    re.IGNORECASE
    | re.DOTALL,
)


def extract_field(
    page_text,
    field,
):

    patterns = [

        rf"{re.escape(field)}\s*\|\s*([^\n\r|]+)",

        rf"{re.escape(field)}\s*</[^>]+>\s*"
        rf"<[^>]+>\s*([^<]+)",

        rf"{re.escape(field)}"
        rf".{{0,120}}?"
        rf"(?:</[^>]+>\s*)+"
        rf"([^<]+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            page_text,
            re.IGNORECASE
            | re.DOTALL,
        )

        if match:

            value = strip_html(
                match.group(1)
            )

            if value:
                return value

    return None


def extract_cartemagic_title(
    page_html,
):

    match = CARTEMAGIC_TITLE_RE.search(
        page_html
    )

    if not match:
        return None

    return strip_html(
        match.group(1)
    )


def extract_cartemagic_price(
    page_html,
):

    # Limitiamo la ricerca alla parte iniziale
    # per evitare prezzi di prodotti correlati.
    head = page_html[:50000]

    prices = re.findall(
        r"(\d{1,5}(?:[.,]\d{1,2})?)\s*€",
        strip_html(head),
    )

    parsed = []

    for raw in prices:

        try:

            value = float(
                raw
                .replace(".", "")
                .replace(",", ".")
            )

        except Exception:
            continue

        if valid_price(value):

            parsed.append(
                round(
                    value,
                    2,
                )
            )

    if not parsed:
        return None

    # Il primo prezzo prodotto è normalmente
    # quello mostrato nella scheda principale.
    return parsed[0]


def cartemagic_available(
    page_html,
):

    text = norm(
        strip_html(
            page_html[:60000]
        )
    )

    if "esaurito" in text:
        return False

    if (
        "disponibile" in text
        or "aggiungi al carrello" in text
        or "acquista ora" in text
    ):
        return True

    return False


def parse_cartemagic_title(
    title,
):

    if not title:
        return None

    title = (
        str(title)
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )

    match = re.match(
        r"^(.+?)\s*-\s*"
        r"([A-Za-z]*\d+[A-Za-z]*"
        r"(?:\s*/\s*[A-Za-z]*\d+[A-Za-z]*)?)"
        r"\s*$",
        title,
    )

    if not match:
        return None

    card_text = (
        match.group(1)
        .strip()
    )

    number = norm_number(
        match.group(2)
    )

    if not (
        card_text
        and number
    ):
        return None

    variant = detect_variant(
        card_text
    )

    name = clean_card_name(
        card_text
    )

    if not name:
        return None

    return {

        "name":
            name,

        "number":
            number,

        "variant":
            variant,
    }


def parse_cartemagic_product(
    url,
):

    page_html = http_get(
        url
    )

    if not cartemagic_available(
        page_html
    ):
        return None, "unavailable"

    title = extract_cartemagic_title(
        page_html
    )

    parsed_title = parse_cartemagic_title(
        title
    )

    if not parsed_title:
        return None, "invalidTitle"

    text = strip_html(
        page_html
    )

    language = extract_field(
        text,
        "Lingua",
    )

    condition = extract_field(
        text,
        "Info",
    )

    expansion = extract_field(
        text,
        "Espansione",
    )

    reverse = extract_field(
        text,
        "Carte Reverse",
    )

    if norm(language) != "it":
        return None, "language"

    if norm(condition) != "nm":
        return None, "condition"

    if not expansion:
        return None, "set"

    expansion = clean_set_name(
        expansion
    )

    # Rimuove eventuale codice set finale:
    # Paradox Rift (SV4) -> Paradox Rift
    expansion = re.sub(
        r"\s*\([A-Z0-9-]+\)\s*$",
        "",
        expansion,
        flags=re.IGNORECASE,
    ).strip()

    if not expansion:
        return None, "set"

    variant = parsed_title[
        "variant"
    ]

    reverse_norm = norm(
        reverse
    )

    # Se la pagina dichiara esplicitamente Reverse,
    # ma il titolo non specifica una variante più precisa,
    # assegniamo Reverse Holo.
    if (
        reverse_norm in {
            "si",
            "sì",
            "yes",
        }
        and variant == "Normal"
    ):

        variant = "Reverse Holo"

    if (
        reverse_norm == "no"
        and variant == "Reverse Holo"
    ):

        # Contraddizione tra titolo e attributo.
        return None, "variantConflict"

    price = extract_cartemagic_price(
        page_html
    )

    if price is None:
        return None, "price"

    return {

        "set":
            expansion,

        "number":
            parsed_title["number"],

        "name":
            parsed_title["name"],

        "variant":
            variant,

        "language":
            "IT",

        "condition":
            "NM/MINT",

        "price":
            price,

        "url":
            url,

    }, None


def collect_cartemagic(cards):

    print()
    print(
        "=== CARTEMAGIC ==="
    )

    links = get_cartemagic_product_links()

    print(
        "Prodotti individuati:",
        len(links),
    )

    if not links:

        raise RuntimeError(
            "CarteMagic: nessun prodotto trovato"
        )

    checked_at = utc_now()

    counters = {

        "accepted": 0,
        "unavailable": 0,
        "invalidTitle": 0,
        "languageRejected": 0,
        "conditionRejected": 0,
        "setUnknown": 0,
        "variantConflict": 0,
        "priceUnavailable": 0,
        "duplicateStore": 0,
        "errors": 0,
    }

    for index, url in enumerate(
        links,
        start=1,
    ):

        if (
            index == 1
            or index % 100 == 0
        ):

            print(
                f"CarteMagic scheda "
                f"{index}/{len(links)}"
            )

        try:

            product, reason = (
                parse_cartemagic_product(
                    url
                )
            )

        except Exception as exc:

            counters[
                "errors"
            ] += 1

            print(
                "Errore CarteMagic:",
                url,
                str(exc),
            )

            continue

        if product is None:

            mapping = {

                "unavailable":
                    "unavailable",

                "invalidTitle":
                    "invalidTitle",

                "language":
                    "languageRejected",

                "condition":
                    "conditionRejected",

                "set":
                    "setUnknown",

                "variantConflict":
                    "variantConflict",

                "price":
                    "priceUnavailable",
            }

            key = mapping.get(
                reason
            )

            if key:
                counters[key] += 1

            continue

        added = add_offer(

            cards,

            set_name=
                product["set"],

            number=
                product["number"],

            card_name=
                product["name"],

            variant=
                product["variant"],

            language=
                "IT",

            condition=
                "NM/MINT",

            offer={

                "store":
                    "CarteMagic",

                "price":
                    product["price"],

                "url":
                    product["url"],

                "language":
                    "IT",

                "condition":
                    "NM/MINT",

                "variant":
                    product["variant"],

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

    # Se il parser dovesse rompersi completamente,
    # fermiamo il workflow.
    if counters[
        "accepted"
    ] == 0:

        raise RuntimeError(
            "CarteMagic non ha prodotto "
            "nessuna offerta verificata"
        )

    return {

        "source":
            "CarteMagic",

        "products":
            len(links),

        **counters,

        "ok":
            True,
    }


# ============================================================
# UTILITY
# ============================================================

def utc_now():

    return (
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


# ============================================================
# FINALIZZAZIONE
# ============================================================

def finalize_cards(cards):

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
# RACCOLTA
# ============================================================

def absolute_url(base_url, href):

    return urllib.parse.urljoin(
        base_url,
        html.unescape(str(href or "").strip()),
    )


# ============================================================
# CARD GAME CORNER
# ============================================================

# Ogni seed descrive una categoria reale di Card Game Corner.
# Non contiene prezzi e non identifica singole carte:
# serve soltanto a collegare la categoria del negozio al set TCGdex.
CARDGAMECORNER_SEEDS = [
    {
        "url": (
            "https://www.cardgamecorner.com/it/prodotti/428/3873/"
            "pokemon-carte-singole-prismatic-evolutions-pokemaster-ball-reverse"
        ),
        "setEn": "Prismatic Evolutions",
        "setIt": "Evoluzioni Prismatiche",
    },
]

CARDGAMECORNER_MAX_LIST_PAGES = 20
CARDGAMECORNER_MAX_PRODUCTS = 500

TCGDEX_EN = "https://api.tcgdex.net/v2/en"
TCGDEX_IT = "https://api.tcgdex.net/v2/it"

_TCGDEX_SET_LIST_CACHE = {}
_TCGDEX_SET_DETAIL_CACHE = {}


def cardgamecorner_extract_links(page_html, base_url):

    hrefs = re.findall(
        r"href\s*=\s*[\"']([^\"']+)[\"']",
        str(page_html or ""),
        flags=re.IGNORECASE,
    )

    product_links = []
    list_links = []

    for href in hrefs:

        url = absolute_url(base_url, href)
        parsed = urllib.parse.urlparse(url)

        if parsed.netloc and "cardgamecorner.com" not in parsed.netloc.lower():
            continue

        path = parsed.path.lower()

        if "/it/info-prodotto/" in path:
            product_links.append(url)
        elif "/it/prodotti/" in path:
            list_links.append(url)

    return (
        list(dict.fromkeys(product_links)),
        list(dict.fromkeys(list_links)),
    )


def cardgamecorner_category_id(url):

    parsed = urllib.parse.urlparse(str(url or ""))
    parts = [part for part in parsed.path.split("/") if part]

    if (
        len(parts) >= 4
        and parts[0].lower() == "it"
        and parts[1].lower() in {
            "prodotti",
            "info-prodotto",
        }
    ):
        return parts[3]

    return ""


def cardgamecorner_collect_product_links(seed_url):

    category_id = cardgamecorner_category_id(seed_url)

    queue = [seed_url]
    visited = set()
    products = []

    while queue:

        if len(visited) >= CARDGAMECORNER_MAX_LIST_PAGES:
            break

        url = queue.pop(0)

        if url in visited:
            continue

        visited.add(url)
        page_html = http_get(
            url,
            timeout=35,
            attempts=4,
            backoff_seconds=4,
        )

        product_links, list_links = cardgamecorner_extract_links(
            page_html,
            url,
        )

        for product_url in product_links:

            if (
                cardgamecorner_category_id(product_url)
                != category_id
            ):
                continue

            if product_url not in products:
                products.append(product_url)

            if len(products) >= CARDGAMECORNER_MAX_PRODUCTS:
                return products

        for list_url in list_links:

            if (
                cardgamecorner_category_id(list_url)
                != category_id
            ):
                continue

            if (
                list_url not in visited
                and list_url not in queue
            ):
                queue.append(list_url)

    return products


def cardgamecorner_extract_title(page_html):

    for tag in ("h1", "h2"):

        match = re.search(
            rf"<{tag}[^>]*>(.*?)</{tag}>",
            str(page_html or ""),
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:

            title = strip_html(match.group(1))

            if title:
                return title

    return None


def cardgamecorner_parse_price(raw):

    raw = str(raw or "").strip().replace(" ", "")

    if not raw:
        return None

    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")

    try:
        value = float(raw)
    except Exception:
        return None

    if not valid_price(value):
        return None

    return round(value, 2)


def cardgamecorner_nm_it_price(page_html):

    raw = str(page_html or "")

    # Card Game Corner mostra la lingua principalmente
    # nell'attributo ALT dell'immagine della bandiera.
    raw = re.sub(
        r"<img\b[^>]*\balt\s*=\s*[\"']([^\"']+)[\"'][^>]*>",
        r" \1 ",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )

    text = strip_html(raw)

    # Esempio reale:
    # Italiano NM Unl. Common Reverse Holo EUR 3,90
    match = re.search(
        r"(?:^|\s)Italiano\s+NM\b.{0,220}?"
        r"EUR\s*([0-9]{1,5}(?:[.,][0-9]{1,2})?)",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return cardgamecorner_parse_price(
        match.group(1)
    )


def cardgamecorner_product_identity(page_html):

    title = cardgamecorner_extract_title(page_html)

    if not title:
        return None

    variant = detect_variant(title)
    card_name = clean_card_name(title)

    if not card_name:
        return None

    return {
        "name": card_name,
        "variant": variant,
    }


def tcgdex_sets(language):

    language = str(language or "").lower()

    if language not in {"en", "it"}:
        raise ValueError(
            "Lingua TCGdex non supportata"
        )

    if language in _TCGDEX_SET_LIST_CACHE:
        return _TCGDEX_SET_LIST_CACHE[language]

    base = (
        TCGDEX_IT
        if language == "it"
        else TCGDEX_EN
    )

    data = http_get_json(
        f"{base}/sets"
    )

    if not isinstance(data, list):
        raise RuntimeError(
            f"TCGdex {language}: lista set non valida"
        )

    _TCGDEX_SET_LIST_CACHE[language] = data

    return data


def tcgdex_find_set_id(set_en, set_it=""):

    targets = [
        ("en", set_en),
        ("it", set_it),
    ]

    found_ids = set()

    for language, target in targets:

        if not str(target or "").strip():
            continue

        target_norm = norm(target)

        for item in tcgdex_sets(language):

            if not isinstance(item, dict):
                continue

            if norm(item.get("name")) != target_norm:
                continue

            set_id = str(
                item.get("id")
                or ""
            ).strip()

            if set_id:
                found_ids.add(set_id)

    if len(found_ids) != 1:
        return None

    return next(iter(found_ids))


def tcgdex_set_detail(language, set_id):

    language = str(language or "").lower()
    set_id = str(set_id or "").strip()

    cache_key = (
        language,
        set_id,
    )

    if cache_key in _TCGDEX_SET_DETAIL_CACHE:
        return _TCGDEX_SET_DETAIL_CACHE[
            cache_key
        ]

    base = (
        TCGDEX_IT
        if language == "it"
        else TCGDEX_EN
    )

    data = http_get_json(
        f"{base}/sets/"
        f"{urllib.parse.quote(set_id)}"
    )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"TCGdex {language}: set non valido"
        )

    _TCGDEX_SET_DETAIL_CACHE[
        cache_key
    ] = data

    return data


def tcgdex_card_number(
    local_id,
    official_count,
):

    local_id = str(
        local_id
        or ""
    ).strip()

    if not local_id:
        return None

    if "/" in local_id:
        return norm_number(local_id)

    if local_id.isdigit():

        width = len(
            str(
                official_count
                or ""
            )
        )

        if width > 0:
            local_id = local_id.zfill(width)

    if (
        official_count
        and str(official_count).isdigit()
    ):
        return (
            f"{local_id}/"
            f"{official_count}"
        )

    return norm_number(local_id)


def tcgdex_resolve_card(
    *,
    set_id,
    fallback_set_it,
    card_name,
):

    # Prima proviamo il catalogo italiano:
    # è la fonte migliore per confrontare i nomi
    # presenti su Card Game Corner.
    details = []

    for language in ("it", "en"):

        try:
            detail = tcgdex_set_detail(
                language,
                set_id,
            )
        except Exception:
            continue

        if isinstance(detail, dict):
            details.append(
                (
                    language,
                    detail,
                )
            )

    if not details:
        return None

    matches = {}

    for language, detail in details:

        cards = detail.get(
            "cards"
        )

        if not isinstance(cards, list):
            continue

        official_count = (
            detail.get(
                "cardCount",
                {},
            ).get(
                "official"
            )
        )

        set_name = str(
            detail.get("name")
            or ""
        ).strip()

        for item in cards:

            if not isinstance(item, dict):
                continue

            if (
                norm(item.get("name"))
                != norm(card_name)
            ):
                continue

            local_id = str(
                item.get("localId")
                or ""
            ).strip()

            number = tcgdex_card_number(
                local_id,
                official_count,
            )

            if not number:
                continue

            card_id = str(
                item.get("id")
                or ""
            ).strip()

            key = (
                card_id
                or norm_number(number)
            )

            matches[key] = {
                "number": number,
                "tcgdexId": card_id,
                "setLocalName": set_name,
                "matchedLanguage": language,
            }

    if len(matches) != 1:
        return None

    resolved = next(
        iter(matches.values())
    )

    # Preferiamo il nome italiano del set quando TCGdex
    # lo espone; altrimenti usiamo la traduzione dichiarata
    # nella configurazione della categoria.
    italian_set_name = ""

    try:
        it_detail = tcgdex_set_detail(
            "it",
            set_id,
        )

        italian_set_name = str(
            it_detail.get("name")
            or ""
        ).strip()

    except Exception:
        pass

    resolved["set"] = (
        italian_set_name
        or fallback_set_it
    )

    if not resolved["set"]:
        return None

    return resolved


def parse_cardgamecorner_product(
    url,
    seed,
):

    page_html = http_get(
        url,
        timeout=35,
        attempts=4,
        backoff_seconds=4,
    )

    identity = cardgamecorner_product_identity(
        page_html
    )

    if not identity:
        return None, "invalidTitle"

    price = cardgamecorner_nm_it_price(
        page_html
    )

    if price is None:
        return None, "noItalianNM"

    set_id = seed.get(
        "tcgdexSetId"
    )

    if not set_id:
        return None, "setUnknown"

    resolved = tcgdex_resolve_card(
        set_id=set_id,
        fallback_set_it=seed.get(
            "setIt",
            "",
        ),
        card_name=identity["name"],
    )

    if not resolved:
        return None, "identityAmbiguous"

    return {
        "set": resolved["set"],
        "number": resolved["number"],
        "name": identity["name"],
        "variant": identity["variant"],
        "language": "IT",
        "condition": "NM/MINT",
        "price": price,
        "url": url,
        "tcgdexId": resolved.get(
            "tcgdexId",
            "",
        ),
    }, None


def collect_cardgamecorner(cards):

    print()
    print(
        "=== CARD GAME CORNER ==="
    )

    # Test di rete separato prima di iniziare il crawl.
    # Se GitHub Actions ha un problema DNS/rete temporaneo,
    # non abbandoniamo subito la fonte.
    probe_url = CARDGAMECORNER_SEEDS[0]["url"]
    probe_error = None

    for probe_attempt in range(1, 4):
        try:
            http_get(
                probe_url,
                timeout=35,
                attempts=3,
                backoff_seconds=4,
            )
            probe_error = None
            break
        except Exception as exc:
            probe_error = exc
            print(
                "Card Game Corner test rete "
                f"{probe_attempt}/3 fallito: {exc}"
            )
            if probe_attempt < 3:
                time.sleep(8 * probe_attempt)

    if probe_error is not None:
        raise RuntimeError(
            "Card Game Corner non raggiungibile dopo retry: "
            f"{probe_error}"
        )

    prepared_seeds = []

    for seed in CARDGAMECORNER_SEEDS:

        seed = dict(seed)

        set_id = tcgdex_find_set_id(
            seed.get(
                "setEn",
                "",
            ),
            seed.get(
                "setIt",
                "",
            ),
        )

        if not set_id:

            print(
                "Set TCGdex non identificato:",
                seed.get(
                    "setEn",
                    "",
                ),
            )

            continue

        seed[
            "tcgdexSetId"
        ] = set_id

        prepared_seeds.append(seed)

        print(
            "Set collegato:",
            seed.get(
                "setIt",
            )
            or seed.get(
                "setEn",
            ),
            "->",
            set_id,
        )

    if not prepared_seeds:
        raise RuntimeError(
            "Card Game Corner: "
            "nessun set collegato a TCGdex"
        )

    product_entries = []

    seen_urls = set()

    for seed in prepared_seeds:

        for link in cardgamecorner_collect_product_links(
            seed["url"]
        ):

            if link in seen_urls:
                continue

            seen_urls.add(link)

            product_entries.append(
                (
                    link,
                    seed,
                )
            )

    print(
        "Prodotti individuati:",
        len(product_entries),
    )

    if not product_entries:
        raise RuntimeError(
            "Card Game Corner: nessun prodotto trovato"
        )

    checked_at = utc_now()

    counters = {
        "accepted": 0,
        "invalidTitle": 0,
        "noItalianNM": 0,
        "setUnknown": 0,
        "identityAmbiguous": 0,
        "duplicateStore": 0,
        "errors": 0,
    }

    for index, (
        url,
        seed,
    ) in enumerate(
        product_entries,
        start=1,
    ):

        if (
            index == 1
            or index % 50 == 0
        ):
            print(
                "Card Game Corner scheda "
                f"{index}/"
                f"{len(product_entries)}"
            )

        try:

            product, reason = (
                parse_cardgamecorner_product(
                    url,
                    seed,
                )
            )

        except Exception as exc:

            counters[
                "errors"
            ] += 1

            print(
                "Errore Card Game Corner:",
                url,
                str(exc),
            )

            continue

        if product is None:

            if reason in counters:
                counters[reason] += 1

            continue

        added = add_offer(
            cards,
            set_name=product["set"],
            number=product["number"],
            card_name=product["name"],
            variant=product["variant"],
            language="IT",
            condition="NM/MINT",
            offer={
                "store":
                    "Card Game Corner",

                "price":
                    product["price"],

                "url":
                    product["url"],

                "language":
                    "IT",

                "condition":
                    "NM/MINT",

                "variant":
                    product["variant"],

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

    result = {
        "source":
            "Card Game Corner",

        "ok":
            True,

        "products":
            len(product_entries),

        "tcgdexIdentity":
            True,
    }

    result.update(counters)

    print(
        "Card Game Corner accettate:",
        counters["accepted"],
    )

    print(
        "Card Game Corner identità ambigue:",
        counters["identityAmbiguous"],
    )

    return result


def collect_retail_data():

    cards = {}
    source_stats = []

    # --------------------------------------------------------
    # FONTE 1 — CARD PASSION
    # --------------------------------------------------------

    result = collect_cardpassion(
        cards
    )

    source_stats.append(
        result
    )

    # --------------------------------------------------------
    # FONTE 2 — CARTEMAGIC
    # --------------------------------------------------------

    try:

        result = collect_cartemagic(
            cards
        )

    except Exception as exc:

        print()
        print(
            "CarteMagic non disponibile:"
        )

        print(
            str(exc)
        )

        result = {

            "source":
                "CarteMagic",

            "ok":
                False,

            "error":
                str(exc),

            "accepted":
                0,
        }

    source_stats.append(
        result
    )

    # --------------------------------------------------------
    # FONTE 3 — CARD GAME CORNER
    # --------------------------------------------------------

    try:

        result = collect_cardgamecorner(
            cards
        )

    except Exception as exc:

        print()
        print(
            "Card Game Corner non disponibile:"
        )

        print(
            str(exc)
        )

        result = {
            "source":
                "Card Game Corner",
            "ok":
                False,
            "error":
                str(exc),
            "accepted":
                0,
        }

    source_stats.append(
        result
    )

    
    # --------------------------------------------------------
    # FINALIZZAZIONE
    # --------------------------------------------------------

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

    cards, source_stats = (
        collect_retail_data()
    )

    generated = utc_now()

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

    if not cards:

        raise RuntimeError(
            "Indice retail vuoto: "
            "il file precedente non verrà sovrascritto"
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
        "STATISTICHE:"
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
        "FONTI:"
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
        "File:",
        OUTPUT_FILE,
    )

    print()
    print(
        "=== FINE ==="
    )


if __name__ == "__main__":
    main()
