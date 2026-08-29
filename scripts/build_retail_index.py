#!/usr/bin/env python3

import json
import statistics
import unicodedata
import re

from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CARDORYX — RETAIL PRICE INDEX BUILDER
# ============================================================
#
# Questo indice è COMPLETAMENTE SEPARATO da Cardmarket.
#
# NON modifica:
# - data/cardmarket_play_index.json
# - scripts/build_play_index.py
# - il valore totale della collezione
#
# L'indice retail serve esclusivamente come riferimento
# informativo nei dettagli delle carte.
# ============================================================


SCHEMA_VERSION = 1

MIN_OFFERS_FOR_STATS = 3


# ============================================================
# NORMALIZZAZIONE TESTO
# ============================================================

def norm(value):

    text = unicodedata.normalize(
        'NFKD',
        str(value or '')
    ).encode(
        'ascii',
        'ignore'
    ).decode().lower()

    return re.sub(
        r'[^a-z0-9]+',
        ' ',
        text
    ).strip()


# ============================================================
# NORMALIZZAZIONE NUMERO CARTA
# ============================================================

def norm_number(value):

    value = str(
        value or ''
    ).strip()

    # Mantiene ad esempio:
    # 032
    # 032/217
    # TG01
    # SV001

    return value.upper()


# ============================================================
# CREA CHIAVE IDENTITÀ CARTA
# ============================================================

def make_key(
    set_name,
    number,
    variant,
    language,
    condition
):

    parts = [
        norm(set_name),
        norm_number(number).lower(),
        norm(variant),
        norm(language),
        norm(condition)
    ]

    return '|'.join(parts)


# ============================================================
# CONTROLLO PREZZO
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
# NORMALIZZA UNA OFFERTA RETAIL
# ============================================================

def normalize_offer(offer):

    if not isinstance(
        offer,
        dict
    ):
        return None


    store = str(
        offer.get('store')
        or ''
    ).strip()

    url = str(
        offer.get('url')
        or ''
    ).strip()

    language = str(
        offer.get('language')
        or ''
    ).strip().upper()

    condition = str(
        offer.get('condition')
        or ''
    ).strip().upper()

    variant = str(
        offer.get('variant')
        or ''
    ).strip()

    price = offer.get(
        'price'
    )


    # --------------------------------------------------------
    # FAIL-CLOSED
    # --------------------------------------------------------
    #
    # Una offerta entra nell'indice solamente se
    # possiede dati sufficientemente precisi.
    # --------------------------------------------------------

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

        'store':
            store,

        'price':
            round(
                float(price),
                2
            ),

        'url':
            url,

        'language':
            language,

        'condition':
            condition,

        'variant':
            variant,

        'checkedAt':
            str(
                offer.get(
                    'checkedAt'
                )
                or ''
            ).strip(),

        'sourceType':
            str(
                offer.get(
                    'sourceType'
                )
                or 'retail-store'
            ).strip()
    }


# ============================================================
# CALCOLO STATISTICHE
# ============================================================

def calculate_stats(
    offers
):

    prices = [

        x['price']

        for x in offers

        if valid_price(
            x.get('price')
        )
    ]


    # --------------------------------------------------------
    # Almeno 3 offerte indipendenti.
    #
    # Con meno di 3 offerte NON produciamo min/max/mediana
    # ufficiali utilizzabili da Cardoryx.
    # --------------------------------------------------------

    if len(
        prices
    ) < MIN_OFFERS_FOR_STATS:

        return {

            'reliable':
                False,

            'count':
                len(prices),

            'min':
                None,

            'max':
                None,

            'median':
                None
        }


    return {

        'reliable':
            True,

        'count':
            len(prices),

        'min':
            round(
                min(prices),
                2
            ),

        'max':
            round(
                max(prices),
                2
            ),

        'median':
            round(
                statistics.median(
                    prices
                ),
                2
            )
    }


# ============================================================
# AGGIUNGE UNA CARTA ALL'INDICE
# ============================================================

def add_card(
    index,
    *,
    set_name,
    number,
    card_name,
    variant,
    language='IT',
    condition='NM',
    offers=None
):

    offers = (
        offers
        or []
    )


    clean_offers = []


    for offer in offers:

        cleaned = normalize_offer(
            offer
        )

        if cleaned:
            clean_offers.append(
                cleaned
            )


    key = make_key(
        set_name,
        number,
        variant,
        language,
        condition
    )


    stats = calculate_stats(
        clean_offers
    )


    index[
        key
    ] = {

        'set':
            set_name,

        'number':
            norm_number(
                number
            ),

        'name':
            card_name,

        'variant':
            variant,

        'language':
            language.upper(),

        'condition':
            condition.upper(),

        'offers':
            clean_offers,

        'stats':
            stats
    }


# ============================================================
# RACCOLTA DATI
# ============================================================

def collect_retail_data():

    cards = {}


    # ========================================================
    # FONTI RETAIL
    # ========================================================
    #
    # Gli adattatori delle singole fonti verranno aggiunti
    # qui uno alla volta.
    #
    # Esempio futuro:
    #
    # collect_cardpassion(cards)
    # collect_cartemagic(cards)
    # collect_bsa_store(cards)
    #
    # NON inserire prezzi inventati.
    #
    # NON usare fallback fra varianti differenti.
    #
    # Se una fonte non permette di verificare esattamente
    # carta + variante + lingua + condizione,
    # quella offerta deve essere ignorata.
    # ========================================================


    return cards


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        '=== CARDORYX RETAIL INDEX BUILDER ==='
    )

    print()

    print(
        'Raccolta fonti retail...'
    )


    cards = collect_retail_data()


    generated = datetime.now(
        timezone.utc
    ).isoformat(
        timespec='seconds'
    ).replace(
        '+00:00',
        'Z'
    )


    reliable_cards = sum(

        1

        for card in cards.values()

        if card.get(
            'stats',
            {}
        ).get(
            'reliable'
        )
    )


    total_offers = sum(

        len(
            card.get(
                'offers',
                []
            )
        )

        for card in cards.values()
    )


    out = {

        'schema':
            SCHEMA_VERSION,

        'generatedAt':
            generated,

        'description':
            'Cardoryx Italian retail reference index',

        'rules': {

            'minimumOffersForStats':
                MIN_OFFERS_FOR_STATS,

            'currency':
                'EUR',

            'cardmarketExcluded':
                True,

            'failClosed':
                True
        },

        'stats': {

            'cards':
                len(cards),

            'reliableCards':
                reliable_cards,

            'offers':
                total_offers
        },

        'cards':
            cards
    }


    # ========================================================
    # DESTINAZIONE
    # ========================================================

    dest = (

        Path(__file__)
        .resolve()
        .parents[1]

        / 'data'

        / 'retail_prices.json'
    )


    dest.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # ========================================================
    # SCRITTURA JSON
    # ========================================================

    dest.write_text(

        json.dumps(
            out,
            ensure_ascii=False,
            separators=(
                ',',
                ':'
            )
        ),

        encoding='utf-8'
    )


    print()

    print(
        json.dumps(
            out['stats'],
            indent=2
        )
    )

    print()

    print(
        'File creato:',
        dest
    )

    print(
        'Aggiornato:',
        generated
    )

    print()

    print(
        '=== FINE ==='
    )


# ============================================================
# AVVIO
# ============================================================

if __name__ == '__main__':

    main()
