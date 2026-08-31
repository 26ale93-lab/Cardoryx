#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V4
# TEST ISOLATO READ-ONLY
#
# Obiettivo:
# - leggere le sitemap prodotto reali
# - salvare campioni degli URL grezzi senza filtri di percorso
# - individuare quali URL sembrano riferiti a Pokemon
#
# NON modifica retail_prices.json
# NON tocca Cardmarket
# NON crea offerte
# NON esegue matching

import json
import re
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://www.centrodelfumetto.it"
START_SITEMAPS = [
    BASE + "/sitemap_index.xml",
    BASE + "/product-sitemap.xml",
]
REPORT = Path("centro_fumetto_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/4.0)"
TIMEOUT = 20
MAX_SITEMAPS = 120

RAW_SAMPLE_LIMIT = 250
POKEMON_SAMPLE_LIMIT = 200

POKEMON_HINTS = [
    "pokemon",
    "pokémon",
    "carta-pokemon",
    "carta-pok",
    "pikachu",
    "charizard",
    "mew",
    "eevee",
]

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "application/xml,text/xml,text/html,*/*",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return (
            r.read().decode("utf-8", "replace"),
            r.geturl(),
            getattr(r, "status", None),
        )

def sitemap_urls(xml):
    return [
        unescape(x.strip())
        for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)
    ]

def looks_like_sitemap(url):
    low = url.lower()
    return low.endswith(".xml") or "sitemap" in low

def looks_like_product_sitemap(url):
    low = url.lower()
    return "product-sitemap" in low

def pokemon_score(url):
    low = unescape(url).lower()
    return sum(1 for hint in POKEMON_HINTS if hint in low)

def path_signature(url):
    path = urlparse(url).path.strip("/")
    if not path:
        return "/"
    parts = [p for p in path.split("/") if p]
    if len(parts) == 1:
        return "/" + parts[0]
    return "/" + "/".join(parts[:2])

def main():
    queue = list(START_SITEMAPS)
    seen_maps = set()

    sitemap_stats = []
    all_urls = []
    product_sitemap_urls = []
    signatures = Counter()

    while queue and len(seen_maps) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue

        seen_maps.add(sm)

        try:
            body, final, status = get(sm)
            locs = sitemap_urls(body)

            sitemap_stats.append({
                "url": sm,
                "finalUrl": final,
                "status": status,
                "locs": len(locs),
                "productSitemap": looks_like_product_sitemap(final) or looks_like_product_sitemap(sm),
            })

            current_is_product_sitemap = (
                looks_like_product_sitemap(final)
                or looks_like_product_sitemap(sm)
            )

            for u in locs:
                if looks_like_sitemap(u):
                    if u not in seen_maps:
                        queue.append(u)
                    continue

                all_urls.append(u)

                if current_is_product_sitemap:
                    product_sitemap_urls.append(u)
                    signatures[path_signature(u)] += 1

        except Exception as exc:
            sitemap_stats.append({
                "url": sm,
                "error": repr(exc),
            })

    # De-duplica mantenendo ordine
    all_urls = list(dict.fromkeys(all_urls))
    product_sitemap_urls = list(dict.fromkeys(product_sitemap_urls))

    pokemon_candidates = [
        u for u in product_sitemap_urls
        if pokemon_score(u) > 0
    ]

    pokemon_candidates = sorted(
        pokemon_candidates,
        key=lambda u: (-pokemon_score(u), u.lower())
    )

    report = {
        "schema": 4,
        "source": "Centro del Fumetto",
        "mode": "read-only raw product URL discovery",
        "rules": {
            "cardmarketTouched": False,
            "retailPricesModified": False,
            "createsNewIdentity": False,
            "productPagesFetched": False,
            "matchingPerformed": False,
            "pathFilterApplied": False,
        },
        "stats": {
            "sitemapsFetched": sum(1 for x in sitemap_stats if x.get("status") == 200),
            "sitemapErrors": sum(1 for x in sitemap_stats if "error" in x),
            "allUrls": len(all_urls),
            "productSitemapUrls": len(product_sitemap_urls),
            "pokemonHintUrls": len(pokemon_candidates),
        },
        "topPathSignatures": signatures.most_common(60),
        "sitemaps": sitemap_stats,
        "rawProductUrlSamples": product_sitemap_urls[:RAW_SAMPLE_LIMIT],
        "pokemonHintSamples": pokemon_candidates[:POKEMON_SAMPLE_LIMIT],
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))

    print("\nTop path signatures:")
    for sig, count in report["topPathSignatures"][:30]:
        print(f"{count:6d}  {sig}")

    print("\nRaw product URL samples:")
    for u in report["rawProductUrlSamples"][:50]:
        print(u)

    print("\nPokemon-hint URL samples:")
    for u in report["pokemonHintSamples"][:50]:
        print(u)

    print("\nReport:", REPORT)

if __name__ == "__main__":
    main()
