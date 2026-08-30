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
# 2. BSA Store
# 3. Card Game Corner
# CarteMagic: adapter conservato ma disattivato
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
    timeout=25,
    attempts=2,
    backoff_seconds=2,
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


def parse_plain_price(value):

    text = str(value or "").strip()

    if not text:
        return None

    text = (
        text
        .replace("€", "")
        .replace("EUR", "")
        .strip()
    )

    # Formati ammessi:
    # 0.90
    # 0,90
    # 12
    # 12.90
    match = re.search(
        r"^\s*(\d{1,5}(?:[.,]\d{1,2})?)\s*$",
        text,
    )

    if not match:
        return None

    raw = match.group(1).replace(",", ".")

    try:
        price = float(raw)
    except Exception:
        return None

    if not valid_price(price):
        return None

    return round(price, 2)


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

    # Alcuni negozi antepongono la serie al vero nome del set.
    # Esempi:
    # "Spada e Scudo - Astri Lucenti" -> "Astri Lucenti"
    # "Scarlatto e Violetto - 151" -> "151"
    # "Megaevoluzione - Ascesa Eroica" -> "Ascesa Eroica"
    #
    # Il prefisso viene tolto solo quando è seguito da " - ",
    # quindi il set base "Scarlatto e Violetto" resta invariato.
    series_prefixes = (
        "Spada e Scudo",
        "Scarlatto e Violetto",
        "Sole e Luna",
        "Nero e Bianco",
        "XY",
        "Megaevoluzione",
    )

    for prefix in series_prefixes:
        marker = prefix + " - "
        if text.casefold().startswith(marker.casefold()):
            text = text[len(marker):].strip()
            break

    # BSA usa anche questa categoria per lo stesso set Gran Festa.
    if text.casefold() == "gran festa - ristampa 2021":
        text = "Gran Festa"

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
# FEDERICSTORE
# ============================================================

FEDERICSTORE_BASE_URL = "https://federicstore.it"
FEDERICSTORE_CATEGORY_URL = (
    FEDERICSTORE_BASE_URL
    + "/categoria/carte-singole-pokemon/"
)
FEDERICSTORE_MAX_PAGES = 120


def federicstore_page_url(page):

    if page <= 1:
        return FEDERICSTORE_CATEGORY_URL

    return (
        FEDERICSTORE_CATEGORY_URL
        + f"page/{page}/"
    )


def federicstore_parse_title(title):

    raw = str(title or "").strip()

    # Formato reale tipico:
    # 001-165 Bulbasaur Comune Reverse (IT) – NEAR MINT
    # 003-165 Venusaur ex (IT) – NEAR MINT
    m = re.match(
        r"^\s*(?P<num>\d{1,4})-(?P<tot>\d{1,4})\s+"
        r"(?P<body>.+?)\s*"
        r"\(\s*IT\s*\)\s*"
        r"[-–—]\s*NEAR\s+MINT\s*$",
        raw,
        flags=re.IGNORECASE,
    )

    if not m:
        return None

    body = m.group("body").strip()

    variant = detect_variant(body)
    card_name = clean_card_name(body)

    if not card_name:
        return None

    number = (
        f"{int(m.group('num')):03d}/"
        f"{int(m.group('tot')):03d}"
    )

    return {
        "name": card_name,
        "number": number,
        "variant": variant,
    }


def federicstore_product_blocks(page_html):

    html_text = str(page_html or "")

    blocks = re.findall(
        r"<li\b[^>]*class=[\"'][^\"']*\bproduct\b[^\"']*[\"'][^>]*>"
        r".*?</li>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Fallback prudente per temi WooCommerce che usano <div>.
    if not blocks:
        blocks = re.findall(
            r"<div\b[^>]*class=[\"'][^\"']*\bproduct\b[^\"']*[\"'][^>]*>"
            r".*?</div>\s*</div>",
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    return blocks


def federicstore_parse_block(block):

    raw = str(block or "")

    href_match = re.search(
        r'href=[\"\'](?P<url>https?://[^\"\']+/prodotto/[^\"\']+)[\"\']',
        raw,
        flags=re.IGNORECASE,
    )

    if not href_match:
        href_match = re.search(
            r'href=[\"\'](?P<url>/prodotto/[^\"\']+)[\"\']',
            raw,
            flags=re.IGNORECASE,
        )

    if not href_match:
        return None

    url = absolute_url(
        FEDERICSTORE_BASE_URL,
        href_match.group("url"),
    )

    title = None

    for pattern in (
        r"<h2\b[^>]*>(.*?)</h2>",
        r"<h3\b[^>]*>(.*?)</h3>",
        r'class=[\"\'][^\"\']*woocommerce-loop-product__title[^\"\']*[\"\'][^>]*>(.*?)</',
    ):
        m = re.search(
            pattern,
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m:
            title = strip_html(m.group(1))
            if title:
                break

    if not title:
        # Ultimo fallback: attributo aria-label/title del link prodotto.
        m = re.search(
            r'(?:aria-label|title)=[\"\']([^\"\']+)[\"\']',
            raw,
            flags=re.IGNORECASE,
        )
        if m:
            title = html.unescape(m.group(1)).strip()

    if not title:
        return None

    visible = strip_html(raw)
    visible_n = norm(visible)
    raw_n = norm(raw)

    out_of_stock = (
        "esaurito" in visible_n
        or "outofstock" in raw_n
        or "out of stock" in visible_n
    )

    in_stock = (
        "aggiungi" in visible_n
        or "instock" in raw_n
        or "disponibile" in visible_n
    )

    if out_of_stock or not in_stock:
        available = False
    else:
        available = True

    price = parse_euro_price(visible)

    return {
        "url": url,
        "title": title,
        "available": available,
        "price": price,
    }


def collect_federicstore(cards):

    print()
    print("=== FEDERICSTORE ===", flush=True)

    stats = {
        "source": "Federicstore",
        "pages": 0,
        "products": 0,
        "accepted": 0,
        "invalidTitle": 0,
        "unavailable": 0,
        "identityAmbiguous": 0,
        "priceUnavailable": 0,
        "duplicateStore": 0,
        "errors": 0,
        "ok": True,
    }

    # Identità già definite dalle fonti precedenti.
    # Il set non viene indovinato: Federicstore viene accettato soltanto
    # quando numero completo + nome + variante identificano UNA sola carta.
    identity_index = {}

    for key, card in cards.items():

        identity_index.setdefault(
            (
                norm_number(card.get("number", "")),
                norm(card.get("name", "")),
                card.get("variant", ""),
            ),
            [],
        ).append((key, card))

    checked_at = utc_now()
    seen_urls = set()

    try:

        for page in range(1, FEDERICSTORE_MAX_PAGES + 1):

            url = federicstore_page_url(page)

            print(
                f"Federicstore pagina {page}...",
                flush=True,
            )

            page_html = http_get(
                url,
                timeout=15,
                attempts=2,
                backoff_seconds=1,
            )

            blocks = federicstore_product_blocks(
                page_html
            )

            if not blocks:
                break

            stats["pages"] += 1
            new_on_page = 0

            for block in blocks:

                item = federicstore_parse_block(block)

                if not item:
                    continue

                if item["url"] in seen_urls:
                    continue

                seen_urls.add(item["url"])
                new_on_page += 1
                stats["products"] += 1

                parsed = federicstore_parse_title(
                    item["title"]
                )

                if not parsed:
                    stats["invalidTitle"] += 1
                    continue

                if not item["available"]:
                    stats["unavailable"] += 1
                    continue

                if not valid_price(item["price"]):
                    stats["priceUnavailable"] += 1
                    continue

                candidates = identity_index.get(
                    (
                        norm_number(parsed["number"]),
                        norm(parsed["name"]),
                        parsed["variant"],
                    ),
                    [],
                )

                if len(candidates) != 1:
                    stats["identityAmbiguous"] += 1
                    continue

                key, card = candidates[0]

                stores_before = {
                    norm(x.get("store"))
                    for x in card.get("offers", [])
                }

                if norm("Federicstore") in stores_before:
                    stats["duplicateStore"] += 1
                    continue

                card.setdefault(
                    "offers",
                    [],
                ).append({
                    "store": "Federicstore",
                    "price": round(float(item["price"]), 2),
                    "url": item["url"],
                    "language": "IT",
                    "condition": "NM/MINT",
                    "variant": parsed["variant"],
                    "checkedAt": checked_at,
                    "sourceType": "retail-store",
                })

                stats["accepted"] += 1

            if new_on_page == 0:
                break

    except Exception as exc:

        stats["errors"] += 1
        stats["ok"] = False
        stats["error"] = str(exc)

    print(
        "Federicstore:",
        json.dumps(
            stats,
            ensure_ascii=False,
        ),
        flush=True,
    )

    return stats



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
        "tcgdexSetId": "sv08.5",
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
            timeout=6,
            attempts=1,
            backoff_seconds=0,
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
        timeout=6,
        attempts=1,
        backoff_seconds=0,
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
    print("=== CARD GAME CORNER ===", flush=True)

    source_started = time.monotonic()
    HARD_LIMIT_SECONDS = 90

    def time_left():
        return HARD_LIMIT_SECONDS - (
            time.monotonic() - source_started
        )

    def deadline_reached():
        return time_left() <= 0

    # Probe rapido: se il negozio non risponde in pochi secondi
    # viene saltato senza rallentare tutto Cardoryx.
    probe_url = CARDGAMECORNER_SEEDS[0]["url"]

    try:
        http_get(
            probe_url,
            timeout=6,
            attempts=1,
            backoff_seconds=0,
        )
    except Exception as exc:
        raise RuntimeError(
            "Card Game Corner non raggiungibile rapidamente: "
            f"{exc}"
        )

    if deadline_reached():
        raise RuntimeError(
            "Card Game Corner: limite tempo raggiunto dopo il probe"
        )

    prepared_seeds = []

    for seed in CARDGAMECORNER_SEEDS:

        if deadline_reached():
            break

        seed = dict(seed)

        set_id = str(
            seed.get("tcgdexSetId")
            or ""
        ).strip()

        if not set_id:
            try:
                set_id = tcgdex_find_set_id(
                    seed.get("setEn", ""),
                    seed.get("setIt", ""),
                )
            except Exception as exc:
                print(
                    "Card Game Corner / TCGdex non disponibile:",
                    exc,
                    flush=True,
                )
                continue

        if not set_id:
            print(
                "Set TCGdex non identificato:",
                seed.get("setEn", ""),
                flush=True,
            )
            continue

        # Verifica che l'ID esplicito/dinamico esista davvero.
        try:
            tcgdex_set_detail(
                "en",
                set_id,
            )
        except Exception as exc:
            print(
                "Set TCGdex non raggiungibile:",
                set_id,
                exc,
                flush=True,
            )
            continue

        seed["tcgdexSetId"] = set_id
        prepared_seeds.append(seed)

        print(
            "Set collegato:",
            seed.get("setIt") or seed.get("setEn"),
            "->",
            set_id,
            flush=True,
        )

    if not prepared_seeds:
        raise RuntimeError(
            "Card Game Corner: nessun set collegato a TCGdex"
        )

    product_entries = []
    seen_urls = set()

    for seed in prepared_seeds:

        if deadline_reached():
            break

        try:
            links = cardgamecorner_collect_product_links(
                seed["url"]
            )
        except Exception as exc:
            print(
                "Card Game Corner: errore catalogo:",
                exc,
                flush=True,
            )
            continue

        for link in links:

            if deadline_reached():
                break

            if link in seen_urls:
                continue

            seen_urls.add(link)
            product_entries.append((link, seed))

    print(
        "Prodotti individuati:",
        len(product_entries),
        flush=True,
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
        "skippedByTimeLimit": 0,
    }

    processed = 0

    for index, (url, seed) in enumerate(
        product_entries,
        start=1,
    ):

        if deadline_reached():
            counters["skippedByTimeLimit"] = (
                len(product_entries) - processed
            )
            print(
                "Card Game Corner: limite di 90s raggiunto. "
                "Interrompo la fonte senza bloccare il workflow.",
                flush=True,
            )
            break

        if index == 1 or index % 25 == 0:
            print(
                "Card Game Corner scheda "
                f"{index}/{len(product_entries)} "
                f"— tempo residuo {max(0, int(time_left()))}s",
                flush=True,
            )

        try:
            product, reason = parse_cardgamecorner_product(
                url,
                seed,
            )
        except Exception as exc:
            counters["errors"] += 1
            processed += 1

            # Non stampiamo centinaia di errori identici.
            if counters["errors"] <= 5:
                print(
                    "Errore Card Game Corner:",
                    str(exc),
                    flush=True,
                )
            continue

        processed += 1

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
                "store": "Card Game Corner",
                "price": product["price"],
                "url": product["url"],
                "language": "IT",
                "condition": "NM/MINT",
                "variant": product["variant"],
                "checkedAt": checked_at,
                "sourceType": "retail-store",
            },
        )

        if added:
            counters["accepted"] += 1
        else:
            counters["duplicateStore"] += 1

    result = {
        "source": "Card Game Corner",
        "ok": True,
        "products": len(product_entries),
        "processed": processed,
        "tcgdexIdentity": True,
        "timeLimitSeconds": HARD_LIMIT_SECONDS,
    }

    result.update(counters)

    print(
        "Card Game Corner accettate:",
        counters["accepted"],
        "— processate:",
        processed,
        "— tempo:",
        elapsed_label(source_started),
        flush=True,
    )

    return result


# ============================================================
# DIAGNOSTICA TEMPI V8
# ============================================================

def elapsed_label(started):
    return f"{time.monotonic() - started:.1f}s"


def run_source_timed(label, func, cards, hard_seconds=None):
    started = time.monotonic()
    print()
    print(f"[TEMPO] START {label}", flush=True)

    result = func(cards)

    elapsed = time.monotonic() - started
    print(f"[TEMPO] END {label}: {elapsed:.1f}s", flush=True)

    if hard_seconds is not None and elapsed > hard_seconds:
        print(
            f"[TEMPO] ATTENZIONE: {label} ha superato "
            f"il limite diagnostico di {hard_seconds}s",
            flush=True,
        )

    return result


# ============================================================
# BSA STORE — PRODUZIONE
# ============================================================

BSA_STORE_BASE_URL = "https://www.bsastore.it"
BSA_STORE_COLLECTION = "pokemon-carte-singole-ita"
BSA_STORE_PAGE_LIMIT = 250
BSA_STORE_MAX_PAGES = 40


def bsa_products_url(page):

    return (
        f"{BSA_STORE_BASE_URL}/collections/"
        f"{BSA_STORE_COLLECTION}/products.json"
        f"?limit={BSA_STORE_PAGE_LIMIT}&page={page}"
    )


def parse_bsa_title(title):

    raw = str(title or "").strip()

    # Formato tipico BSA:
    # POKEMON Bulbasaur 001/165 - ITA - Near Mint -
    # Scarlatto e Violetto - 151 - Carta Pokemon
    #
    # Varianti esplicite possono comparire dopo il numero:
    # ... 018/165 Holo - ITA - Near Mint - ...

    match = re.match(
        r"^\s*(?:POKEMON\s+)?"
        r"(?P<name>.+?)\s+"
        r"(?P<number>[A-Z0-9]{0,6}\d{1,4}/[A-Z0-9]{0,6}\d{1,4})"
        r"(?P<finish>.*?)"
        r"\s*-\s*ITA\s*"
        r"-\s*Near\s+Mint\s*"
        r"-\s*(?P<set>.+?)"
        r"\s*-\s*Carta\s+Pokemon\s*$",
        raw,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    card_name = re.sub(
        r"\s+",
        " ",
        match.group("name"),
    ).strip()

    number = norm_number(
        match.group("number")
    )

    finish = re.sub(
        r"\s+",
        " ",
        match.group("finish") or "",
    ).strip(" -")

    # V15 — BSA inserisce spesso la rarità dopo il numero.
    # La rarità non è una finitura e non deve far scartare la carta.
    finish = re.sub(
        r"\b(?:"
        r"Non\s+Comune|Comune|Rara\s+Doppia|"
        r"Rara\s+Ultra|Rara\s+Illustrazione\s+Speciale|"
        r"Rara\s+Illustrazione|Rara\s+Segreta|"
        r"Rara\s+Iper|Rara\s+Allenatore|"
        r"Rara\s+ACE\s+SPEC|Rara"
        r")\b",
        " ",
        finish,
        flags=re.IGNORECASE,
    )

    finish = re.sub(
        r"\s+",
        " ",
        finish,
    ).strip(" -")

    set_name = re.sub(
        r"\s+",
        " ",
        match.group("set"),
    ).strip()

    # Alcuni set BSA hanno nomi composti con " - "
    # (es. "Scarlatto e Violetto - 151").
    set_name = clean_set_name(
        set_name
    )

    variant_source = finish

    if not variant_source:
        variant = "Normal"
    else:
        variant = detect_variant(
            variant_source
        )

        # Se BSA espone una finitura che non sappiamo
        # classificare con certezza, non inventiamo "Normal".
        if (
            variant == "Normal"
            and norm(variant_source)
            not in {
                "",
                "normal",
                "non holo",
                "nonholo",
            }
        ):
            return None

    return {
        "name": card_name,
        "number": number,
        "variant": variant,
        "set": set_name,
        "language": "IT",
        "condition": "NM/MINT",
    }


def bsa_available_price(product):

    variants = product.get(
        "variants",
        [],
    )

    prices = []

    for variant in variants:

        if variant.get("available") is not True:
            continue

        price = parse_plain_price(
            variant.get("price")
        )

        if price is None:
            continue

        prices.append(
            price
        )

    if not prices:
        return None

    distinct = sorted(
        set(prices)
    )

    # Fail closed: se uno stesso prodotto presenta più
    # prezzi disponibili, non sappiamo quale variante Shopify
    # rappresenti esattamente la carta.
    if len(distinct) != 1:
        return None

    return distinct[0]


def collect_bsa_store(cards):

    print()
    print("=== BSA STORE ===")

    stats = {
        "source": "BSA Store",
        "products": 0,
        "accepted": 0,
        "invalidTitle": 0,
        "invalidTitleExamples": [],
        "rarityLabelsSupported": True,
        "priceUnavailable": 0,
        "duplicateStore": 0,
        "errors": 0,
        "ok": True,
    }

    page = 1
    bsa_started = time.monotonic()
    BSA_HARD_LIMIT_SECONDS = 180

    while page <= BSA_STORE_MAX_PAGES:

        if time.monotonic() - bsa_started > BSA_HARD_LIMIT_SECONDS:
            print(
                "BSA Store: limite diagnostico di 180s raggiunto; "
                "interrompo il crawl senza bloccare il workflow.",
                flush=True,
            )
            stats["errors"] += 1
            break

        url = bsa_products_url(
            page
        )

        page_started = time.monotonic()

        print(
            f"BSA Store catalogo pagina {page}...",
            flush=True,
        )

        try:

            payload = http_get_json(
                url
            )

            print(
                f"[TEMPO] BSA pagina {page}: "
                f"{elapsed_label(page_started)}",
                flush=True,
            )

        except Exception as exc:

            # Se la prima pagina non è raggiungibile,
            # la fonte viene marcata non disponibile.
            if page == 1:
                raise

            print(
                f"BSA Store: stop a pagina {page}: {exc}"
            )
            stats["errors"] += 1
            break

        products = payload.get(
            "products",
            [],
        )

        if not products:
            break

        stats["products"] += len(
            products
        )

        checked_at = utc_now()

        for product in products:

            title = str(
                product.get("title")
                or ""
            ).strip()

            identity = parse_bsa_title(
                title
            )

            if not identity:
                stats["invalidTitle"] += 1

                if (
                    len(
                        stats["invalidTitleExamples"]
                    )
                    < 30
                ):
                    stats[
                        "invalidTitleExamples"
                    ].append(
                        title
                    )

                continue

            price = bsa_available_price(
                product
            )

            if price is None:
                stats["priceUnavailable"] += 1
                continue

            handle = str(
                product.get("handle")
                or ""
            ).strip()

            if not handle:
                stats["invalidTitle"] += 1
                continue

            product_url = (
                f"{BSA_STORE_BASE_URL}/products/"
                f"{urllib.parse.quote(handle, safe='-')}"
            )

            added = add_offer(
                cards,
                set_name=identity["set"],
                number=identity["number"],
                card_name=identity["name"],
                variant=identity["variant"],
                language="IT",
                condition="NM/MINT",
                offer={
                    "store": "BSA Store",
                    "price": price,
                    "url": product_url,
                    "language": "IT",
                    "condition": "NM/MINT",
                    "variant": identity["variant"],
                    "checkedAt": checked_at,
                    "sourceType": "retail-store",
                },
            )

            if added:
                stats["accepted"] += 1
            else:
                stats["duplicateStore"] += 1

        # Shopify restituisce meno del limite nell'ultima pagina.
        if len(products) < BSA_STORE_PAGE_LIMIT:
            break

        page += 1

    if stats["accepted"] <= 0:
        raise RuntimeError(
            "BSA Store non ha prodotto nessuna offerta verificata "
            f"(prodotti={stats['products']}, "
            f"invalidTitle={stats['invalidTitle']}, "
            f"priceUnavailable={stats['priceUnavailable']})"
        )

    print()
    print(
        "BSA Store — prodotti:",
        stats["products"],
    )
    print(
        "BSA Store — accettati:",
        stats["accepted"],
    )

    return stats




# ============================================================
# MYCOMICS
# ============================================================

MYCOMICS_BASE_URL = "https://mycomics.it"

MYCOMICS_SET_SEEDS = [
    ("Astri Lucenti", "astri-lucenti"),
    ("Colpo Fusione", "colpo-fusione"),
    ("Gran Festa", "gran-festa"),
    ("Pokémon GO", "pokemon-go"),
]

MYCOMICS_MAX_ARCHIVE_PAGES = 12
MYCOMICS_HARD_LIMIT_SECONDS = 75


def mycomics_archive_url(slug, page):

    if page <= 1:
        return (
            f"{MYCOMICS_BASE_URL}"
            f"/blog/espansione-pokemon/{slug}/"
        )

    return (
        f"{MYCOMICS_BASE_URL}"
        f"/blog/espansione-pokemon/{slug}/"
        f"page/{page}/"
    )


def mycomics_shop_links(page_html):

    results = []

    pattern = re.compile(
        r'<a\b[^>]*href=["\']'
        r'(?P<url>https?://(?:www\.)?mycomics\.it'
        r'(?:/it)?/shop/[^"\']+)'
        r'["\'][^>]*>'
        r'(?P<label>.*?)'
        r'</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    seen = set()

    for match in pattern.finditer(page_html):

        url = html.unescape(
            match.group("url")
        ).strip()

        label = strip_html(
            match.group("label")
        )

        if not label:
            continue

        identity = (
            norm(url),
            norm(label),
        )

        if identity in seen:
            continue

        seen.add(identity)

        results.append(
            {
                "url": url,
                "label": label,
            }
        )

    return results


def mycomics_number_from_label(
    label,
    set_name,
):

    clean = strip_html(
        label
    )

    normalized = norm(
        clean
    )

    if "italiano" not in normalized:
        return None

    if "near mint" not in normalized:
        return None

    if norm(set_name) not in normalized:
        return None

    match = re.search(
        r"(?<!\d)"
        r"(\d{1,4}\s*/\s*\d{1,4})"
        r"(?!\d)",
        clean,
    )

    if not match:
        return None

    return norm_number(
        match.group(1)
    )


def mycomics_explicit_variant(label):

    normalized = norm(
        label
    )

    if (
        "master ball reverse" in normalized
        or "masterball reverse" in normalized
    ):
        return "Master Ball Reverse Holo"

    if (
        "poke ball reverse" in normalized
        or "pokeball reverse" in normalized
    ):
        return "Poké Ball Reverse Holo"

    if (
        "energy reverse" in normalized
        or "energia reverse" in normalized
    ):
        return "Energy Reverse Holo"

    if "reverse" in normalized:
        return "Reverse Holo"

    return None


def mycomics_existing_candidate(
    cards,
    set_name,
    number,
    explicit_variant,
):

    candidates = []

    for card in cards.values():

        if norm(
            card.get("set")
        ) != norm(
            clean_set_name(set_name)
        ):
            continue

        if norm_number(
            card.get("number")
        ) != norm_number(
            number
        ):
            continue

        if norm(
            card.get("language")
        ) != "it":
            continue

        if norm(
            card.get("condition")
        ) != norm(
            "NM/MINT"
        ):
            continue

        # MyComics può diventare anche la seconda fonte:
        # non limitiamo più il matching alle sole carte già
        # presenti in 2 negozi.
        variant = str(
            card.get("variant")
            or ""
        )

        if explicit_variant:

            if norm(
                variant
            ) != norm(
                explicit_variant
            ):
                continue

        else:

            # Se MyComics non dichiara "Reverse", non colleghiamo
            # mai una variante Reverse implicita.
            if "reverse" in norm(
                variant
            ):
                continue

        candidates.append(
            card
        )

    # Fail closed: una sola identità possibile.
    if len(candidates) != 1:
        return None

    return candidates[0]


def mycomics_product_price(
    page_html,
):

    raw = str(
        page_html
        or ""
    )

    # 1. JSON-LD / dati strutturati prodotto.
    structured_patterns = [
        r'"price"\s*:\s*"(?P<price>\d+(?:[.,]\d{1,2})?)"',
        r'"price"\s*:\s*(?P<price>\d+(?:[.,]\d{1,2})?)',
        r'property=["\']product:price:amount["\']'
        r'[^>]*content=["\'](?P<price>\d+(?:[.,]\d{1,2})?)["\']',
        r'name=["\']twitter:data1["\']'
        r'[^>]*content=["\'](?P<price>\d+(?:[.,]\d{1,2})?)',
    ]

    for pattern in structured_patterns:

        match = re.search(
            pattern,
            raw,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        price = parse_plain_price(
            match.group("price")
        )

        if price is not None:
            return price

    # 2. Solo il blocco principale del prodotto,
    #    evitando prezzi di prodotti correlati.
    summary = re.search(
        r'<div\b[^>]*class=["\']'
        r'[^"\']*\bsummary\b[^"\']*'
        r'["\'][^>]*>'
        r'(?P<body>.*?)'
        r'</div>',
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if summary:

        price = parse_euro_price(
            summary.group("body")
        )

        if price is not None:
            return price

    # 3. Fallback conservativo.
    matches = re.findall(
        r'<(?:p|div|span)\b'
        r'[^>]*class=["\']'
        r'[^"\']*\bprice\b[^"\']*'
        r'["\'][^>]*>'
        r'(?P<body>.*?)'
        r'</(?:p|div|span)>',
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )

    prices = []

    for body in matches:

        price = parse_euro_price(
            body
        )

        if price is not None:
            prices.append(
                price
            )

    prices = sorted(
        set(prices)
    )

    if len(prices) != 1:
        return None

    return prices[0]


def mycomics_availability_status(
    page_html,
):

    raw = str(
        page_html
        or ""
    )

    raw_lower = raw.lower()

    visible_text = strip_html(
        raw
    )

    normalized = norm(
        visible_text
    )

    language_ok = (
        "prodotto in italiano"
        in normalized
        or "lingua italiano"
        in normalized
        or "lingua: italiano"
        in normalized
    )

    condition_ok = (
        "near mint"
        in normalized
    )

    in_stock_signals = [
        "schema.org/instock",
        '"availability":"https://schema.org/instock"',
        '"availability": "https://schema.org/instock"',
        "stock in-stock",
        "single_add_to_cart_button",
        'name="add-to-cart"',
    ]

    out_of_stock_signals = [
        "schema.org/outofstock",
        '"availability":"https://schema.org/outofstock"',
        '"availability": "https://schema.org/outofstock"',
        "stock out-of-stock",
    ]

    has_in_stock = any(
        signal in raw_lower
        for signal in in_stock_signals
    )

    has_out_of_stock = any(
        signal in raw_lower
        for signal in out_of_stock_signals
    )

    visible_add_to_cart = (
        "aggiungi al carrello"
        in normalized
    )

    visible_unavailable = (
        "al momento il prodotto non e disponibile"
        in normalized
        or "prodotto non disponibile"
        in normalized
        or "esaurito"
        in normalized
    )

    if not language_ok or not condition_ok:
        status = "invalid-metadata"
    elif has_in_stock or visible_add_to_cart:
        status = "in-stock"
    elif has_out_of_stock:
        status = "out-of-stock"
    elif visible_unavailable:
        status = "unavailable-text-only"
    else:
        status = "unknown"

    return {
        "status": status,
        "languageOk": language_ok,
        "conditionOk": condition_ok,
        "hasInStockSignal": has_in_stock,
        "hasOutOfStockSignal": has_out_of_stock,
        "visibleAddToCart": visible_add_to_cart,
        "visibleUnavailable": visible_unavailable,
    }


def mycomics_product_is_valid(
    page_html,
):

    return (
        mycomics_availability_status(
            page_html
        )["status"]
        == "in-stock"
    )


def collect_mycomics(
    cards,
):

    print()
    print("=== MYCOMICS ===")

    stats = {
        "source": "MyComics",
        "archivePages": 0,
        "links": 0,
        "candidates": 0,
        "processed": 0,
        "accepted": 0,
        "unavailable": 0,
        "priceUnavailable": 0,
        "identityAmbiguous": 0,
        "matchedAsSecondStore": 0,
        "matchedAsThirdStore": 0,
        "availabilityInStock": 0,
        "availabilityOutOfStock": 0,
        "availabilityTextOnly": 0,
        "availabilityUnknown": 0,
        "availabilityInvalidMetadata": 0,
        "availabilityExamples": [],
        "errors": 0,
        "ok": True,
    }

    started = time.monotonic()
    queued = {}

    for set_name, slug in MYCOMICS_SET_SEEDS:

        for page in range(
            1,
            MYCOMICS_MAX_ARCHIVE_PAGES + 1,
        ):

            if (
                time.monotonic()
                - started
                > MYCOMICS_HARD_LIMIT_SECONDS
            ):
                stats["timeLimitReached"] = True
                break

            url = mycomics_archive_url(
                slug,
                page,
            )

            try:
                page_html = http_get(
                    url,
                    timeout=6,
                    attempts=1,
                )
            except urllib.error.HTTPError as exc:

                if exc.code == 404 and page > 1:
                    break

                stats["errors"] += 1
                break

            except Exception as exc:

                stats["errors"] += 1

                print(
                    f"MyComics {set_name}: "
                    f"errore rete pagina {page}: {exc}",
                    flush=True,
                )
                break

            stats["archivePages"] += 1

            links = mycomics_shop_links(
                page_html
            )

            if not links:
                break

            stats["links"] += len(
                links
            )

            for item in links:

                number = mycomics_number_from_label(
                    item["label"],
                    set_name,
                )

                if not number:
                    continue

                explicit_variant = (
                    mycomics_explicit_variant(
                        item["label"]
                    )
                )

                candidate = (
                    mycomics_existing_candidate(
                        cards,
                        set_name,
                        number,
                        explicit_variant,
                    )
                )

                if candidate is None:
                    stats["identityAmbiguous"] += 1
                    continue

                key = make_key(
                    candidate["set"],
                    candidate["number"],
                    candidate["variant"],
                    candidate["language"],
                    candidate["condition"],
                )

                if key in queued:
                    continue

                queued[key] = {
                    "candidate": candidate,
                    "url": item["url"],
                }

                stats["candidates"] += 1

            if len(links) < 20:
                break

        if (
            time.monotonic()
            - started
            > MYCOMICS_HARD_LIMIT_SECONDS
        ):
            break

    for key, item in queued.items():

        if (
            time.monotonic()
            - started
            > MYCOMICS_HARD_LIMIT_SECONDS
        ):
            stats["timeLimitReached"] = True
            break

        stats["processed"] += 1

        try:
            product_html = http_get(
                item["url"],
                timeout=6,
                attempts=1,
            )
        except Exception:
            stats["errors"] += 1
            continue

        availability = mycomics_availability_status(
            product_html
        )

        status = availability["status"]

        if status == "in-stock":
            stats["availabilityInStock"] += 1
        elif status == "out-of-stock":
            stats["availabilityOutOfStock"] += 1
            stats["unavailable"] += 1
        elif status == "unavailable-text-only":
            stats["availabilityTextOnly"] += 1
            stats["unavailable"] += 1
        elif status == "invalid-metadata":
            stats["availabilityInvalidMetadata"] += 1
            stats["unavailable"] += 1
        else:
            stats["availabilityUnknown"] += 1
            stats["unavailable"] += 1

        if len(stats["availabilityExamples"]) < 30:
            stats["availabilityExamples"].append(
                {
                    "url": item["url"],
                    "status": status,
                    "languageOk": availability["languageOk"],
                    "conditionOk": availability["conditionOk"],
                    "hasInStockSignal": availability["hasInStockSignal"],
                    "hasOutOfStockSignal": availability["hasOutOfStockSignal"],
                    "visibleAddToCart": availability["visibleAddToCart"],
                    "visibleUnavailable": availability["visibleUnavailable"],
                }
            )

        if status != "in-stock":
            continue

        price = mycomics_product_price(
            product_html
        )

        if price is None:
            stats["priceUnavailable"] += 1
            continue

        card = item["candidate"]

        stores_before = {
            norm(
                offer.get("store")
            )
            for offer in card.get(
                "offers",
                [],
            )
            if offer.get("store")
        }

        added = add_offer(
            cards,
            set_name=card["set"],
            number=card["number"],
            card_name=card["name"],
            variant=card["variant"],
            language="IT",
            condition="NM/MINT",
            offer={
                "store": "MyComics",
                "price": price,
                "url": item["url"],
                "language": "IT",
                "condition": "NM/MINT",
                "variant": card["variant"],
                "checkedAt": utc_now(),
                "sourceType": "retail-store",
            },
        )

        if added:
            stats["accepted"] += 1

            if len(
                stores_before
            ) >= 2:
                stats[
                    "matchedAsThirdStore"
                ] += 1
            elif len(
                stores_before
            ) == 1:
                stats[
                    "matchedAsSecondStore"
                ] += 1

    print(
        "MyComics:",
        json.dumps(
            stats,
            ensure_ascii=False,
        ),
        flush=True,
    )

    return stats


# ============================================================
# GS-GAMEON — V17
# ============================================================

GS_GAMEON_COLLECTION_URL = (
    "https://www.gs-gameon.com/collections/pok-mon-single/products.json"
    "?limit=250&page={page}"
)


def gs_gameon_variant(edition, rarity=""):

    edition_n = norm(edition)
    rarity_n = norm(rarity)

    if "reverse holo" in edition_n:
        return "Reverse Holo"

    if edition_n not in ("regolare", "regular", ""):
        return None

    if (
        "holo rare" in rarity_n
        or rarity_n in ("holo", "rare holo")
    ):
        return "Holo"

    return "Normal"


def gs_gameon_parse_title(title):

    value = str(title or "").strip()

    m = re.match(
        r"^(.*?)\s+-\s+(.*?)\s+\(([^()]*)\)\s+\[([^\]]+)\]\s*$",
        value,
        flags=re.IGNORECASE,
    )

    if not m:
        return None

    code = m.group(4).strip()

    number_match = re.search(
        r"(\d{1,3})\s*$",
        code,
    )

    if not number_match:
        return None

    return {
        "name": m.group(1).strip(),
        "set": clean_set_name(m.group(2).strip()),
        "rarity": m.group(3).strip(),
        "localNumber": str(int(number_match.group(1))),
        "code": code,
    }


def collect_gs_gameon(cards):

    print()
    print("=== GS-GAMEON ===", flush=True)

    stats = {
        "source": "GS-Gameon",
        "products": 0,
        "variants": 0,
        "accepted": 0,
        "invalidTitle": 0,
        "languageRejected": 0,
        "conditionRejected": 0,
        "editionRejected": 0,
        "unavailable": 0,
        "identityAmbiguous": 0,
        "priceUnavailable": 0,
        "duplicateStore": 0,
        "errors": 0,
        "ok": True,
    }

    # Exact identities already established by the other retail sources.
    identity_index = {}

    for key, card in cards.items():

        number = norm_number(
            card.get("number", "")
        )

        base = number.split("/")[0].lstrip("0") or "0"

        identity_index.setdefault(
            (
                norm(card.get("set", "")),
                base,
            ),
            [],
        ).append((key, card))

    checked_at = utc_now()

    try:
        for page in range(1, 41):

            url = GS_GAMEON_COLLECTION_URL.format(
                page=page
            )

            payload = http_get_json(url)

            products = (
                payload.get("products", [])
                if isinstance(payload, dict)
                else []
            )

            if not products:
                break

            for product in products:

                stats["products"] += 1

                parsed = gs_gameon_parse_title(
                    product.get("title")
                )

                if not parsed:
                    stats["invalidTitle"] += 1
                    continue

                target_set = norm(parsed["set"])
                target_number = parsed["localNumber"]

                candidates = identity_index.get(
                    (
                        target_set,
                        target_number,
                    ),
                    [],
                )

                # Conservative reconciliation for GS labels such as
                # "Evoluzioni Prismatiche: Supplementi".
                if not candidates:

                    compact_target = target_set.replace(
                        " supplementi",
                        ""
                    ).replace(
                        ":",
                        " "
                    )

                    compact_target = " ".join(
                        compact_target.split()
                    )

                    possible = []

                    for (
                        set_key,
                        number_key,
                    ), values in identity_index.items():

                        if number_key != target_number:
                            continue

                        compact_set = set_key.replace(
                            " supplementi",
                            ""
                        ).replace(
                            ":",
                            " "
                        )

                        compact_set = " ".join(
                            compact_set.split()
                        )

                        if compact_set == compact_target:
                            possible.extend(values)

                    candidates = possible

                for shop_variant in (
                    product.get("variants", [])
                    or []
                ):

                    stats["variants"] += 1

                    if not shop_variant.get("available"):
                        stats["unavailable"] += 1
                        continue

                    language = str(
                        shop_variant.get("option1", "")
                    ).strip()

                    condition = str(
                        shop_variant.get("option2", "")
                    ).strip()

                    edition = str(
                        shop_variant.get("option3", "")
                    ).strip()

                    if norm(language) != "italiano":
                        stats["languageRejected"] += 1
                        continue

                    if norm(condition) != "near mint":
                        stats["conditionRejected"] += 1
                        continue

                    variant = gs_gameon_variant(
                        edition,
                        parsed["rarity"],
                    )

                    if variant is None:
                        stats["editionRejected"] += 1
                        continue

                    matching = [
                        (key, card)
                        for key, card in candidates
                        if card.get("variant") == variant
                    ]

                    if len(matching) != 1:
                        stats["identityAmbiguous"] += 1
                        continue

                    key, card = matching[0]

                    raw_price = shop_variant.get("price")

                    try:
                        price = float(raw_price)
                    except (TypeError, ValueError):
                        stats["priceUnavailable"] += 1
                        continue

                    # Shopify /products.json normally returns decimal EUR.
                    # Integer cents are accepted only when clearly integer.
                    if isinstance(raw_price, int):
                        price = price / 100.0

                    price = round(price, 2)

                    if price <= 0:
                        stats["priceUnavailable"] += 1
                        continue

                    offer = {
                        "store": "GS-Gameon",
                        "price": price,
                        "url": (
                            "https://www.gs-gameon.com/products/"
                            + str(product.get("handle", ""))
                        ),
                        "language": "IT",
                        "condition": "NM/MINT",
                        "variant": variant,
                        "checkedAt": checked_at,
                        "sourceType": "retail-store",
                    }

                    stores_before = {
                        norm(x.get("store"))
                        for x in card.get("offers", [])
                    }

                    if norm("GS-Gameon") in stores_before:
                        stats["duplicateStore"] += 1
                        continue

                    card.setdefault("offers", []).append(offer)
                    stats["accepted"] += 1

            if len(products) < 250:
                break

    except Exception as exc:
        stats["ok"] = False
        stats["errors"] += 1
        stats["error"] = str(exc)

    print(
        "GS-Gameon:",
        json.dumps(stats, ensure_ascii=False),
        flush=True,
    )

    return stats


def collect_retail_data():

    cards = {}
    source_stats = []

    # --------------------------------------------------------
    # FONTE 1 — CARD PASSION
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "Card Passion",
            collect_cardpassion,
            cards,
            hard_seconds=180,
        )
    except Exception as exc:
        print(
            "Card Passion non disponibile:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "Card Passion",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # FONTE 2 — BSA STORE
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "BSA Store",
            collect_bsa_store,
            cards,
            hard_seconds=180,
        )
    except Exception as exc:
        print(
            "BSA Store non disponibile:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "BSA Store",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # FONTE 3 — MYCOMICS
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "MyComics",
            collect_mycomics,
            cards,
            hard_seconds=80,
        )
    except Exception as exc:
        print(
            "MyComics non disponibile:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "MyComics",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
            "timeLimitSeconds": 75,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # FONTE 4 — GS-GAMEON
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "GS-Gameon",
            collect_gs_gameon,
            cards,
            hard_seconds=180,
        )
    except Exception as exc:
        print(
            "GS-Gameon non disponibile:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "GS-Gameon",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # FONTE 5 — FEDERICSTORE
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "Federicstore",
            collect_federicstore,
            cards,
            hard_seconds=180,
        )
    except Exception as exc:
        print(
            "Federicstore non disponibile:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "Federicstore",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # FONTE 6 — CARD GAME CORNER
    # --------------------------------------------------------

    try:
        result = run_source_timed(
            "Card Game Corner",
            collect_cardgamecorner,
            cards,
            hard_seconds=95,
        )
    except Exception as exc:
        print(
            "Card Game Corner saltato:",
            str(exc),
            flush=True,
        )
        result = {
            "source": "Card Game Corner",
            "ok": False,
            "error": str(exc),
            "accepted": 0,
            "timeLimitSeconds": 90,
        }

    source_stats.append(result)

    # --------------------------------------------------------
    # CARTEMAGIC — DISATTIVATO
    # --------------------------------------------------------
    # Il codice dell'adapter resta nel file per eventuali test futuri,
    # ma non viene eseguito automaticamente perché il sito blocca/
    # rallenta GitHub Actions.

    source_stats.append({
        "source": "CarteMagic",
        "ok": False,
        "disabled": True,
        "reason": "Disattivato: incompatibile con esecuzione automatica GitHub Actions",
        "accepted": 0,
    })

    # --------------------------------------------------------
    # FINALIZZAZIONE
    # --------------------------------------------------------

    final_started = time.monotonic()

    finalize_cards(cards)

    print(
        f"[TEMPO] Finalizzazione: "
        f"{elapsed_label(final_started)}",
        flush=True,
    )

    return (
        cards,
        source_stats,
    )



# ============================================================
# DIAGNOSTICA RICONCILIAZIONE CARD PASSION <-> BSA
# ============================================================

def reconciliation_diagnostics(cards):

    cp_entries = []
    bsa_entries = []

    for key, card in cards.items():

        stores = {
            norm(offer.get("store"))
            for offer in card.get("offers", [])
            if offer.get("store")
        }

        base = {
            "key": key,
            "set": card.get("set", ""),
            "number": card.get("number", ""),
            "name": card.get("name", ""),
            "variant": card.get("variant", ""),
        }

        if norm("Card Passion") in stores:
            cp_entries.append(base)

        if norm("BSA Store") in stores:
            bsa_entries.append(base)

    def base_key(item):
        return (
            norm(item["set"]),
            norm_number(item["number"]),
        )

    def name_number_key(item):
        return (
            norm(item["name"]),
            norm_number(item["number"]),
        )

    cp_by_base = {}
    bsa_by_base = {}
    cp_by_name_number = {}
    bsa_by_name_number = {}

    for item in cp_entries:
        cp_by_base.setdefault(base_key(item), []).append(item)
        cp_by_name_number.setdefault(name_number_key(item), []).append(item)

    for item in bsa_entries:
        bsa_by_base.setdefault(base_key(item), []).append(item)
        bsa_by_name_number.setdefault(name_number_key(item), []).append(item)

    already_joined = 0

    for card in cards.values():
        stores = {
            norm(offer.get("store"))
            for offer in card.get("offers", [])
            if offer.get("store")
        }
        if (
            norm("Card Passion") in stores
            and norm("BSA Store") in stores
        ):
            already_joined += 1

    shared_bases = set(cp_by_base) & set(bsa_by_base)
    variant_mismatches = []

    for bk in sorted(shared_bases):

        cp_items = cp_by_base[bk]
        bsa_items = bsa_by_base[bk]

        cp_keys = {item["key"] for item in cp_items}
        bsa_keys = {item["key"] for item in bsa_items}

        unresolved_cp = [
            item for item in cp_items
            if item["key"] not in bsa_keys
        ]
        unresolved_bsa = [
            item for item in bsa_items
            if item["key"] not in cp_keys
        ]

        if unresolved_cp or unresolved_bsa:
            variant_mismatches.append({
                "set": cp_items[0]["set"],
                "number": cp_items[0]["number"],
                "cardPassion": [
                    {
                        "name": x["name"],
                        "variant": x["variant"],
                    }
                    for x in unresolved_cp
                ],
                "bsaStore": [
                    {
                        "name": x["name"],
                        "variant": x["variant"],
                    }
                    for x in unresolved_bsa
                ],
            })

    shared_name_numbers = (
        set(cp_by_name_number)
        & set(bsa_by_name_number)
    )

    set_mismatches = []
    seen = set()

    for nk in sorted(shared_name_numbers):

        for cp in cp_by_name_number[nk]:
            for bsa in bsa_by_name_number[nk]:

                if norm(cp["set"]) == norm(bsa["set"]):
                    continue

                pair = (
                    norm(cp["set"]),
                    norm(bsa["set"]),
                    norm_number(cp["number"]),
                    norm(cp["name"]),
                )

                if pair in seen:
                    continue

                seen.add(pair)

                set_mismatches.append({
                    "name": cp["name"],
                    "number": cp["number"],
                    "cardPassionSet": cp["set"],
                    "bsaSet": bsa["set"],
                    "cardPassionVariant": cp["variant"],
                    "bsaVariant": bsa["variant"],
                })

    cp_base_keys = set(cp_by_base)
    bsa_base_keys = set(bsa_by_base)

    result = {
        "alreadyJoinedCards": already_joined,
        "sharedSetNumberGroups": len(shared_bases),
        "variantMismatchGroups": len(variant_mismatches),
        "possibleSetNameMismatchGroups": len(set_mismatches),
        "onlyCardPassionBaseIdentities":
            len(cp_base_keys - bsa_base_keys),
        "onlyBsaBaseIdentities":
            len(bsa_base_keys - cp_base_keys),
        "variantMismatchExamples":
            variant_mismatches[:40],
        "setNameMismatchExamples":
            set_mismatches[:40],
    }

    print()
    print("DIAGNOSTICA RICONCILIAZIONE:")
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    return result

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

    reconciliation = reconciliation_diagnostics(
        cards
    )

    out = {

        "schema":
            SCHEMA_VERSION,

        "generatedAt":
            generated,

        "description":
            "Cardoryx Italian retail reference index",

        "reconciliationDiagnostics":
            reconciliation,

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

            "crossSourceMatching":
                "independent-any-3-stores",
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

            "multiStoreCards":
                sum(
                    1
                    for card in cards.values()
                    if card.get("stats", {}).get("stores", 0) >= 2
                ),

            "threeStoreCards":
                sum(
                    1
                    for card in cards.values()
                    if card.get("stats", {}).get("stores", 0) >= 3
                ),
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
