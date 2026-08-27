#!/usr/bin/env python3

import json
import re
import unicodedata
import urllib.request
from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CARDORYX — CAR MARKET PLAY INDEX BUILDER
# ============================================================

BASE = 'https://downloads.s3.cardmarket.com/productCatalog'

URLS = {
    'singles': f'{BASE}/productList/products_singles_6.json',
    'nonsingles': f'{BASE}/productList/products_nonsingles_6.json',
    'prices': f'{BASE}/priceGuide/price_guide_6.json',
}


# ============================================================
# PLAY! POKÉMON PRIZE PACK SERIES
# ============================================================

SERIES_WORDS = {
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
    10: 'ten',
}


# ============================================================
# NORMALIZZAZIONE TESTO
# ============================================================

def norm(s):

    s = unicodedata.normalize(
        'NFKD',
        str(s or '')
    ).encode(
        'ascii',
        'ignore'
    ).decode().lower()

    return re.sub(
        r'[^a-z0-9]+',
        ' ',
        s
    ).strip()


# ============================================================
# ESTRAZIONE RIGHE DAI JSON CARDMARKET
# ============================================================

def rows(root, keys):

    if isinstance(root, list):
        return root

    if isinstance(root, dict):

        for k in keys:

            if isinstance(root.get(k), list):
                return root[k]

        for v in root.values():

            if isinstance(v, list) and v:
                return v

    return []


# ============================================================
# DOWNLOAD JSON
# ============================================================

def get(url):

    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Cardoryx-IndexBuilder/2.0'
        }
    )

    with urllib.request.urlopen(
        req,
        timeout=120
    ) as r:

        return json.load(r)


# ============================================================
# LETTURA ID INTERI
# ============================================================

def iid(r, *names):

    for n in names:

        try:

            v = int(r.get(n))

            if v > 0:
                return v

        except Exception:
            pass

    return None


# ============================================================
# NOME PRODOTTO
# ============================================================

def product_name(r):

    return (
        r.get('name')
        or r.get('Name')
        or r.get('productName')
        or ''
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print('Scarico catalogo Cardmarket...')

    singles_root = get(
        URLS['singles']
    )

    nons_root = get(
        URLS['nonsingles']
    )

    prices_root = get(
        URLS['prices']
    )


    # ========================================================
    # LETTURA DATI
    # ========================================================

    singles = rows(
        singles_root,
        [
            'products',
            'product',
            'data',
            'items'
        ]
    )

    nons = rows(
        nons_root,
        [
            'products',
            'product',
            'data',
            'items'
        ]
    )

    prices = rows(
        prices_root,
        [
            'priceGuides',
            'priceGuide',
            'prices',
            'products',
            'data',
            'items'
        ]
    )


    if not singles:

        raise SystemExit(
            'Catalogo singles Cardmarket vuoto '
            'o formato non riconosciuto.'
        )


    if not prices:

        raise SystemExit(
            'Price Guide Cardmarket vuota '
            'o formato non riconosciuto.'
        )


    # ========================================================
    # INDICE PREZZI PER idProduct
    # ========================================================

    price_by = {}

    for x in prices:

        pid = iid(
            x,
            'idProduct',
            'id_product'
        )

        if pid:
            price_by[pid] = x


    # ========================================================
    # TROVA AUTOMATICAMENTE LE ESPANSIONI PRIZE PACK
    # ========================================================

    exp_to_series = {}

    evidence = {}

    for r in nons:

        n = norm(
            product_name(r)
        )

        exp = iid(
            r,
            'idExpansion',
            'id_expansion'
        )

        if not exp:
            continue


        for ser, word in SERIES_WORDS.items():

            target = (
                f'play pokemon prize pack '
                f'series {word}'
            )

            if target in n:

                exp_to_series[exp] = ser

                evidence[str(ser)] = {
                    'idExpansion': exp,
                    'product': product_name(r)
                }

                break


    if not exp_to_series:

        raise SystemExit(
            'Nessuna espansione Prize Pack trovata '
            'nel catalogo non-singles.'
        )


    print(
        'Prize Pack trovati:',
        sorted(exp_to_series.values())
    )


    # ========================================================
    # RAGGRUPPA TUTTI I SINGLES PER idMetacard
    # ========================================================

    by_meta_raw = {}

    for r in singles:

        meta = iid(
            r,
            'idMetacard',
            'id_metacard'
        )

        pid = iid(
            r,
            'idProduct',
            'id_product'
        )

        exp = iid(
            r,
            'idExpansion',
            'id_expansion'
        )


        if meta and pid:

            by_meta_raw.setdefault(
                meta,
                []
            ).append(
                (
                    pid,
                    exp,
                    r
                )
            )


    # ========================================================
    # INDICI FINALI
    # ========================================================

    by_base = {}

    by_product = {}

    by_metacard = {}

    by_name = {}

    play_count = 0


    # ========================================================
    # CAMPI PREZZO CARDMARKET
    # ========================================================

    price_fields = [

        'low',
        'trend',
        'avg',
        'avg1',
        'avg7',
        'avg30',

        'low-holo',
        'trend-holo',
        'avg-holo',
        'avg1-holo',
        'avg7-holo',
        'avg30-holo'
    ]


    generated = datetime.now(
        timezone.utc
    ).date().isoformat()


    # ========================================================
    # CREA MAPPING
    # ========================================================

    for meta, group in by_meta_raw.items():

        play = []

        bases = []


        # ----------------------------------------------------
        # DIVIDE PRODOTTI BASE E PRIZE PACK
        # ----------------------------------------------------

        for pid, exp, r in group:

            if exp in exp_to_series:

                play.append(
                    (
                        pid,
                        exp,
                        r
                    )
                )

            else:

                bases.append(
                    (
                        pid,
                        exp,
                        r
                    )
                )


        if not play:
            continue


        payloads = []


        # ----------------------------------------------------
        # CREA PAYLOAD PER OGNI VERSIONE PRIZE PACK
        # ----------------------------------------------------

        for pid, exp, r in play:

            pr = price_by.get(
                pid,
                {}
            )


            # Conserva i metadati originali Cardmarket.
            # Servono per distinguere versioni differenti
            # senza inventare associazioni.

            catalog_meta = {

                str(k): v

                for k, v in r.items()

                if isinstance(
                    v,
                    (
                        str,
                        int,
                        float,
                        bool
                    )
                )
                or v is None
            }


            payload = {

                'idProduct': pid,

                'series': str(
                    exp_to_series[exp]
                ),

                'idExpansion': exp,

                'idMetacard': meta,

                'name': product_name(r),

                'nameKey': norm(
                    product_name(r)
                ),

                'updated': generated,

                'catalog': catalog_meta,

                'prices': {

                    k: pr.get(k)

                    for k in price_fields

                    if pr.get(k) is not None
                }
            }


            payloads.append(
                payload
            )


            by_product[
                str(pid)
            ] = payload


            play_count += 1


        # ====================================================
        # INDICE DIRETTO PER idMetacard
        # ====================================================

        meta_series = {}


        for p in payloads:

            meta_series.setdefault(
                p['series'],
                []
            ).append(
                p
            )


        by_metacard[
            str(meta)
        ] = meta_series


        # ====================================================
        # INDICE TRAMITE PRODOTTO BASE
        # ====================================================

        for basepid, _, _ in bases:

            by_base[
                str(basepid)
            ] = meta_series


        # ====================================================
        # FALLBACK PER NOME
        #
        # Non assegna direttamente un prezzo.
        # Restituisce candidati che Cardoryx filtra
        # successivamente per Series.
        # ====================================================

        names = set()


        for _, _, r in bases:

            nk = norm(
                product_name(r)
            )

            if nk:
                names.add(
                    nk
                )


        for _, _, r in play:

            nk = norm(
                product_name(r)
            )

            if nk:
                names.add(
                    nk
                )


        for nk in names:

            entry = by_name.setdefault(
                nk,
                {}
            )


            for series, plist in meta_series.items():

                target = entry.setdefault(
                    series,
                    []
                )


                existing = {

                    x['idProduct']

                    for x in target
                }


                for p in plist:

                    if (
                        p['idProduct']
                        not in existing
                    ):

                        target.append(
                            p
                        )

                        existing.add(
                            p['idProduct']
                        )


    # ========================================================
    # OUTPUT JSON
    # ========================================================

    out = {

        'schema': 2,

        'generatedAt': generated,

        'source':
            'Cardmarket official Product Catalogue + Price Guide',

        'expansions': evidence,

        'stats': {

            'singles': len(
                singles
            ),

            'priceRows': len(
                prices
            ),

            'playProducts': play_count,

            'baseProductsMapped': len(
                by_base
            ),

            'metacardsMapped': len(
                by_metacard
            ),

            'namesMapped': len(
                by_name
            )
        },

        'byBaseProduct':
            by_base,

        'byProduct':
            by_product,

        'byMetacard':
            by_metacard,

        'byName':
            by_name
    }


    # ========================================================
    # DESTINAZIONE
    # ========================================================

    dest = (

        Path(__file__)
        .resolve()
        .parents[1]

        / 'data'

        / 'cardmarket_play_index.json'
    )


    dest.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    # ========================================================
    # SCRIVE JSON COMPATTO
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


    # ========================================================
    # RISULTATO
    # ========================================================

    print()

    print(
        '=== CARDORYX CARDMARKET INDEX ==='
    )

    print(
        json.dumps(
            out['stats'],
            indent=2
        )
    )

    print()

    print(
        'Prize expansions:',
        evidence
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

    print(
        '=== FINE ==='
    )


# ============================================================
# AVVIO
# ============================================================

if __name__ == '__main__':

    main()
